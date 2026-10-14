"""Background fetch of posts from the Nostr accounts the operator follows,
and the live subscriptions that make most of those fetches unnecessary.
"""

import threading
import time

from lib.nostr_images import FETCH_INTERVAL_SECONDS, configured_accounts, get_store

# Settings whose change should not wait for the next fetch: a newly added
# account should show its posts, a removed one lose them, now.
NOSTR_FETCH_KEYS = ('nostr_enabled', 'nostr_accounts', 'nostr_relays', 'nostr_use_tor',
                    'nostr_pool_minutes', 'nostr_live', 'nostr_skip_sensitive',
                    'nostr_max_per_account')

# With live subscriptions connected, a fetch only catches up on what a dropped
# connection may have missed.
CATCHUP_INTERVAL_SECONDS = 30 * 60
# A post arriving live redoes the next block's pre-render at most this often:
# a busy hour must not keep a Pi Zero rendering.
_RERENDER_MIN_SECONDS = 60


class NostrMixin:
    """Fetches while Nostr is switched on - every FETCH_INTERVAL_SECONDS, or
    every CATCHUP_INTERVAL_SECONDS while live subscriptions are connected."""

    def _start_nostr_fetcher(self):
        if getattr(self, '_nostr_wake', None) is not None:
            return
        self._nostr_wake = threading.Event()
        self._nostr_restart_live = True
        from lib.nostr_live import get_live
        live = get_live(on_new_post=self._on_new_nostr_post)

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
                    # After the fetch: the profiles it loaded say which relays
                    # the accounts write to, and the live plan uses them.
                    if self._nostr_restart_live:
                        self._nostr_restart_live = False
                        live.restart(config)
                else:
                    live.stop()
                    self._nostr_restart_live = True
                interval = (CATCHUP_INTERVAL_SECONDS if live.any_connected()
                            else FETCH_INTERVAL_SECONDS)
                self._nostr_wake.wait(interval)
                self._nostr_wake.clear()

        threading.Thread(target=loop, name='nostr-fetch', daemon=True).start()

    def trigger_nostr_fetch(self):
        """Run a fetch now instead of at the next interval, and renew the live
        subscriptions - called when the Nostr settings change."""
        wake = getattr(self, '_nostr_wake', None)
        if wake is not None:
            self._nostr_restart_live = True
            wake.set()

    def _on_new_nostr_post(self, post):
        """A post just arrived live. If the image prepared for the next block
        is a meme or a repeat, prepare it again so the new post is shown."""
        if not self.config.get('nostr_enabled', False):
            return
        now = time.time()
        if now - getattr(self, '_nostr_rerender_at', 0) < _RERENDER_MIN_SECONDS:
            return
        store = get_store()
        choice = getattr(self, '_prerender_choice', None)
        chosen = choice.get('meme_path') if choice else None
        if chosen and store.is_unseen_choice(chosen):
            return      # the next block already shows a post nobody has seen yet
        self._nostr_rerender_at = now
        # Give back the turn of whatever was picked for that block and will
        # now not be shown.
        if chosen:
            store.revert_pick(chosen)
        self._prerender_choice = None
        precache = getattr(self, '_precache', None)
        if precache is not None:
            with precache['lock']:
                pending = precache.get('next_meme_path')
                if pending:
                    store.revert_pick(pending)
                precache['next_meme_path'] = None
                precache['selected_block_types'] = None
        if hasattr(self, '_invalidate_prerender'):
            self._invalidate_prerender()
        print(f'🟣 Nostr live: new post {post["key"][:12]} - preparing the next block again')
        threading.Thread(target=self._prerender_next_block, daemon=True).start()
