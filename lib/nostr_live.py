"""Live subscriptions: relays push new posts of the followed accounts the
moment they are published, instead of being asked every few minutes.

One connection per relay - the configured ones, plus the relays most of the
followed accounts say they write to - each in its own thread. A subscription
stays open after the relay has sent what it had, so the relay keeps sending
whatever arrives. Connections over Tor drop now and then; each thread
reconnects on its own, through a fresh circuit, and asks again from the last
post it saw. A slow catch-up fetch stays in place for anything missed.

An open, quiet WebSocket costs next to nothing; what this saves is the TLS
handshake over Tor to every relay every five minutes.
"""

import json
import random
import threading
import time
import uuid

from lib import nostr_images as N

# Relays added beyond the configured ones, for accounts that publish elsewhere.
_LIVE_OUTBOX_RELAYS = 4
# A relay that has been quiet this long is pinged, so a dead connection shows.
_PING_AFTER = 60
# Pause before reconnecting, doubled after each failure up to the maximum.
_BACKOFF_START = 10
_BACKOFF_MAX = 300
# Overlap when resuming, so a post published during the reconnect is caught.
_RESUME_OVERLAP = 120


class NostrLive:
    """The set of live connections for one configuration."""

    def __init__(self, store, on_new_post=None):
        self.store = store
        self.on_new_post = on_new_post
        self._lock = threading.Lock()
        self._generation = 0
        self._stop = threading.Event()
        self._state = {}            # relay -> {'connected': bool, 'since': int}

    # -- control ----------------------------------------------------------

    def restart(self, config):
        """Stop the current connections and open new ones for this config."""
        self.stop()
        if not config.get('nostr_enabled', False) or not config.get('nostr_live', True):
            return
        accounts = [pk for pk, _ in N.configured_accounts(config)]
        if not accounts:
            return
        plan = self._plan(accounts, config)
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._stop = threading.Event()
            stop = self._stop
            self._state = {relay: {'connected': False, 'since': int(time.time()) - _RESUME_OVERLAP}
                           for relay in plan}
        for relay, authors in plan.items():
            threading.Thread(target=self._run, args=(relay, authors, config, generation, stop),
                             name=f'nostr-live-{relay[6:30]}', daemon=True).start()
        print(f'🟣 Nostr live: subscribing on {len(plan)} relay(s) for {len(accounts)} account(s)')

    def stop(self):
        with self._lock:
            self._generation += 1
            self._stop.set()
            self._state = {}

    def status(self):
        """{'connected': n, 'total': m} for the settings page."""
        with self._lock:
            return {'connected': sum(1 for s in self._state.values() if s['connected']),
                    'total': len(self._state)}

    def any_connected(self):
        return self.status()['connected'] > 0

    def _plan(self, accounts, config):
        """relay -> the followed accounts to ask it about."""
        plan = {relay: list(accounts) for relay in N.configured_relays(config)}
        profiles = N.NostrPostStore._profiles()
        by_relay = {}
        for pk in accounts:
            for relay in profiles.get(pk, {}).get('relays', []):
                if relay not in plan:
                    by_relay.setdefault(relay, []).append(pk)
        for relay in sorted(by_relay, key=lambda r: -len(by_relay[r]))[:_LIVE_OUTBOX_RELAYS]:
            plan[relay] = by_relay[relay]
        return plan

    # -- one relay --------------------------------------------------------

    def _current(self, generation):
        return generation == self._generation

    def _run(self, relay, authors, config, generation, stop):
        import websocket
        backoff = _BACKOFF_START
        circuit = 'nostr-live'
        failures = 0
        while self._current(generation) and not stop.is_set():
            ws = None
            try:
                since = self._state.get(relay, {}).get('since', int(time.time()) - _RESUME_OVERLAP)
                ws = websocket.create_connection(relay, timeout=30,
                                                 **N._ws_proxy_kwargs(config, circuit))
                sub = uuid.uuid4().hex[:16]
                filters = N._author_filters(authors, kinds=N._IMAGE_KINDS, since=lambda g: since)
                ws.send(json.dumps(['REQ', sub] + filters))
                self._set(relay, generation, connected=True)
                if failures:
                    print(f'🟣 Nostr live: {relay} connected again')
                failures = 0
                backoff = _BACKOFF_START
                last_traffic = time.monotonic()
                while self._current(generation) and not stop.is_set():
                    ws.settimeout(15)
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        if time.monotonic() - last_traffic > _PING_AFTER:
                            ws.ping()       # raises when the connection is gone
                            last_traffic = time.monotonic()
                        continue
                    last_traffic = time.monotonic()
                    if not raw:
                        break
                    try:
                        msg = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(msg, list) or len(msg) < 2:
                        continue
                    if msg[0] == 'EVENT' and msg[1] == sub and len(msg) >= 3 and isinstance(msg[2], dict):
                        self._event(relay, msg[2], config, generation)
                    elif msg[0] == 'CLOSED' and msg[1] == sub:
                        break           # the relay ended it; subscribe afresh
            except Exception as e:
                failures += 1
                if failures == 1:
                    code, text, _ = N._describe_relay_error(e)
                    print(f'⚠️ Nostr live: {relay}: {text} - reconnecting')
            finally:
                self._set(relay, generation, connected=False)
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass
            if not self._current(generation) or stop.is_set():
                return
            # A different exit each time over Tor: the one refused before may
            # simply be blocked by the relay.
            circuit = f'nostr-live-{uuid.uuid4().hex[:8]}'
            stop.wait(backoff + random.uniform(0, backoff / 2))
            backoff = min(backoff * 2, _BACKOFF_MAX)

    def _set(self, relay, generation, **values):
        with self._lock:
            if self._current(generation) and relay in self._state:
                self._state[relay].update(values)

    def _event(self, relay, event, config, generation):
        created = event.get('created_at')
        if isinstance(created, int):
            with self._lock:
                if self._current(generation) and relay in self._state:
                    state = self._state[relay]
                    # Resume from here after a reconnect, with some overlap.
                    state['since'] = max(state['since'], created - _RESUME_OVERLAP)
        try:
            post = self.store.ingest_live(event, config)
        except Exception as e:
            print(f'⚠️ Nostr live: could not take post from {relay}: {e}')
            return
        if post is not None and self.on_new_post is not None:
            try:
                self.on_new_post(post)
            except Exception as e:
                print(f'⚠️ Nostr live: new-post handler failed: {e}')


_live = None
_live_lock = threading.Lock()


def get_live(on_new_post=None):
    global _live
    with _live_lock:
        if _live is None:
            _live = NostrLive(N.get_store(), on_new_post=on_new_post)
        elif on_new_post is not None:
            _live.on_new_post = on_new_post
        return _live
