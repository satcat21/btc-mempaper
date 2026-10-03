"""Whether the device should reach the network at all.

A device with no saved Wi-Fi, or one in setup mode, has no route to anything:
its only interface is the setup hotspot. Every request made in that state can
only fail - and over Tor it does not fail fast. tor keeps running without an
uplink and accepts the SOCKS connection, so each request sits until its
timeout, and tor_recovery reads the run of failures as a broken circuit and
restarts tor. On a Pi Zero all of that competes with the one thing that
matters in this state: bringing up the setup hotspot and drawing its QR codes.

So while offline, outgoing HTTP is refused before it starts, the block
websocket waits instead of connecting, and none of it counts as a Tor failure.
Requests to this machine itself still go through.

    set_offline(True, 'no saved Wi-Fi')   # at startup, or when setup mode starts
    set_offline(False)                    # once connected to a real network
"""

import threading
from urllib.parse import urlparse

_offline = threading.Event()
_reason = ''
_LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def set_offline(offline, reason=''):
    """Switch the gate. Logged only when the state actually changes."""
    global _reason
    if offline:
        _reason = reason or 'offline'
        if not _offline.is_set():
            _offline.set()
            print(f'📴 Network requests paused ({_reason})')
    elif _offline.is_set():
        _offline.clear()
        _reason = ''
        print('📶 Network requests resumed')


def is_offline():
    return _offline.is_set()


def _is_local(url):
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS or host.startswith('127.')


def install():
    """Route every requests call through the gate. Idempotent.

    Patched at the Session level because requests.get() and friends all end
    up there, so every HTTP client in the app - mempool, price, wallet,
    Bitaxe, webhook relay - is covered without touching each one.
    """
    import requests

    original = requests.Session.request
    if getattr(original, '_mempaper_network_gate', False):
        return

    def request(self, method, url, *args, **kwargs):
        if _offline.is_set() and not _is_local(url):
            raise requests.exceptions.ConnectionError(
                f'not attempted, device offline ({_reason}): {url}')
        return original(self, method, url, *args, **kwargs)

    request._mempaper_network_gate = True
    requests.Session.request = request
