"""Background fetch of posts from the Nostr accounts the operator follows.
"""

import threading

from lib.nostr_images import FETCH_INTERVAL_SECONDS, configured_accounts, get_store

# Settings whose change should not wait for the next fetch: a newly added
# account should show its posts, a removed one lose them, now.
NOSTR_FETCH_KEYS = ('nostr_enabled', 'nostr_accounts', 'nostr_relays', 'nostr_use_tor')


class NostrMixin:
    """Runs one fetch every FETCH_INTERVAL_SECONDS while Nostr is switched on."""

    def _start_nostr_fetcher(self):
        if getattr(self, '_nostr_wake', None) is not None:
            return
        self._nostr_wake = threading.Event()

        def loop():
            # Same reason as the precache updater: requests fired before the
            # network question is settled only fail and cost the Pi Zero CPU.
            self._startup_wifi_check_done.wait(timeout=90)
            while True:
                config = self.config
                if config.get('nostr_enabled', False):
                    store = get_store()
                    if configured_accounts(config):
                        store.fetch(config)
                    else:
                        # Still run, to clear out the posts of accounts that
                        # were removed from the list.
                        store.fetch(config, log=lambda *_: None)
                self._nostr_wake.wait(FETCH_INTERVAL_SECONDS)
                self._nostr_wake.clear()

        threading.Thread(target=loop, name='nostr-fetch', daemon=True).start()

    def trigger_nostr_fetch(self):
        """Run a fetch now instead of at the next interval."""
        wake = getattr(self, '_nostr_wake', None)
        if wake is not None:
            wake.set()
