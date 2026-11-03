"""One pooled requests.Session per thread, for the app's HTTP clients.

requests.get() builds a Session, opens a connection and throws both away. For
HTTPS that also means a fresh SSL context, which re-reads certifi's CA bundle,
and a full TLS handshake: tens of milliseconds of CPU on a Pi Zero, every call.
The pre-cache loop, block monitor and block reward scanner make several calls
a minute between them, so the handshakes alone were a steady load.

A pooled session keeps the connection and the SSL context. Per thread rather
than one shared, because Session is not documented as thread safe; the loops
that make most of the calls live for the life of the process, so they keep
theirs. Under gevent, threading.local is greenlet-local, which is the same.

Cookies are refused, so a call behaves as the stateless requests.get() did.
network_gate patches Session.request on the class, so it covers these too.
"""
import threading
from http.cookiejar import DefaultCookiePolicy

import requests

_local = threading.local()

# requests keeps one pool per distinct proxy URL, and a Tor circuit rotation
# stamps new credentials into that URL. Rotations are rare (failures only), but
# a process runs for months, so old pools are dropped past this many.
_MAX_PROXY_POOLS = 8


def http_session() -> requests.Session:
    """This thread's pooled session."""
    session = getattr(_local, 'session', None)
    if session is None:
        session = requests.Session()
        session.cookies.set_policy(DefaultCookiePolicy(allowed_domains=[]))
        _local.session = session
    else:
        for adapter in session.adapters.values():
            managers = getattr(adapter, 'proxy_manager', None)
            if managers and len(managers) > _MAX_PROXY_POOLS:
                for manager in managers.values():
                    try:
                        manager.clear()
                    except Exception:
                        pass
                managers.clear()
    return session
