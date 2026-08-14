"""Cached images and the precache: metadata on disk, the periodic refresh
loop for price/fee/network data, and prerender invalidation.
"""

from datetime import datetime
from utils.atomic_io import atomic_write_json
import json
import os
import threading
import time


class CachingMixin:
    """Cached images and the precache: metadata on disk, the periodic refresh"""

    def _interval(self, key):
        """Read a pre-cache timing value, in seconds.

        Every interval is a config key whose default lives in
        get_default_config, so there is one authoritative value per setting
        rather than a literal repeated at each call site. See
        docs/CONFIG_REFERENCE.md, Advanced.

        Falls back to the shipped default when the key is missing or not a
        usable number, so a hand-edited config cannot stall the pre-cache loop.
        An unknown key raises rather than defaulting silently: that means a
        typo in the caller, which is a bug to fix, not to paper over.
        """
        value = self.config.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return value
        return self.config_manager.get_default_config()[key]

    def _need_block_type(self, *types):
        """True when any of these info-block types will be drawn this cycle.

        In prioritize_large_scaled_meme mode the updater pre-selects which
        blocks fit beside the meme, and both it and the render path skip
        fetching data for the rest. None means no preselection is in force
        (balanced layout, or not yet chosen this cycle), so everything is
        fetched — the behaviour before preselection existed.
        """
        selected = self._precache.get('selected_block_types')
        return selected is None or any(t in selected for t in types)

    def _precache_fresh(self, name, max_age, now=None):
        """True when <name>_data is cached and <name>_last_update is younger than max_age.

        Both the background updater and the render path ask this question, and
        they used to answer it inline with different hardcoded numbers - the
        updater at the update interval, the render path at 120 s or 90 s - so a
        render landing between the two thresholds refetched data the updater
        still considered fresh.
        """
        if not self._precache.get(f'{name}_data'):
            return False
        age = (now or time.time()) - self._precache.get(f'{name}_last_update', 0)
        return age < max_age

    def _has_valid_cached_image(self) -> bool:
        """Check if we have a valid cached image for the current block."""
        if not (os.path.exists(self.current_image_path) and 
                self.image_is_current and 
                self.current_block_height is not None):
            return False
            
        # If we're confident the image is current, don't keep checking mempool API
        # This prevents unnecessary API calls and race conditions
        return True
    
    def _load_cache_metadata(self):
        """Load persistent cache metadata from file to survive app restarts."""
        try:
            if os.path.exists(self.cache_metadata_path):
                with open(self.cache_metadata_path, 'r') as f:
                    metadata = json.load(f)
                    
                # Validate that cached images still exist
                if (os.path.exists(self.current_image_path) and 
                    os.path.exists(self.current_eink_image_path)):
                    
                    self.current_block_height = metadata.get('block_height')
                    self.current_block_hash = metadata.get('block_hash')
                    self.current_meme_path = metadata.get('current_meme_path')  # Restore meme cache
                    self.last_eink_block_height = metadata.get('last_eink_block_height')  # Restore e-ink display state
                    self.last_eink_block_hash = metadata.get('last_eink_block_hash')  # Restore e-ink display hash
                    
                    # For smooth transition, if e-ink tracking fields are missing, initialize them from cache
                    if self.last_eink_block_height is None and self.current_block_height:
                        self.last_eink_block_height = self.current_block_height
                        self.last_eink_block_hash = self.current_block_hash
                        print(f"📋 Initialized e-ink tracking from cache: Block {self.last_eink_block_height}")
                    
                    # Check if cached images are recent (within 2 hours)
                    cache_time = metadata.get('timestamp', 0)
                    age_hours = (time.time() - cache_time) / 3600
                    
                    # Only mark as current if age is reasonable - we'll validate block height later
                    if age_hours < 2 and self.current_block_height:
                        # Don't mark as current yet - let _generate_initial_image validate block height
                        self.image_is_current = False  # Will be validated against current block
                        print(f"💾 Cache metadata loaded: Block {self.current_block_height} (age: {age_hours:.1f}h) - will validate")
                    else:
                        print(f"⏰ Cache metadata too old ({age_hours:.1f}h), will refresh")
                        self.image_is_current = False
                else:
                    print("📁 Cache metadata exists but image files missing")
            else:
                print("📁 No cache metadata found (first run)")
        except Exception as e:
            print(f"⚠️ Error loading cache metadata: {e}")
            # Safe fallback
            self.current_block_height = None
            self.current_block_hash = None
            self.image_is_current = False
    
    def _save_cache_metadata(self):
        """Save current cache state to persistent file (immediate write)."""
        self._write_cache_metadata_to_disk()

    def _deferred_save_cache_metadata(self):
        """Deferred disk save — writes at most once per 5 minutes to reduce SD card wear."""
        now = time.time()
        if now - self._last_disk_save_time < self._interval('cache_metadata_write_interval_seconds'):
            self._disk_save_pending = True
            return
        self._write_cache_metadata_to_disk()

    def _write_cache_metadata_to_disk(self):
        """Actually write cache metadata to disk."""
        try:
            metadata = {
                'block_height': self.current_block_height,
                'block_hash': self.current_block_hash,
                'timestamp': time.time(),
                'image_path': self.current_image_path,
                'eink_image_path': self.current_eink_image_path,
                'current_meme_path': getattr(self, 'current_meme_path', None),
                'last_eink_block_height': self.last_eink_block_height,
                'last_eink_block_hash': self.last_eink_block_hash,
                'displayed_info_blocks': getattr(self, 'displayed_info_blocks', []),
                'displayed_bitaxe_data': getattr(self, 'displayed_bitaxe_data', None)
            }
            
            atomic_write_json(self.cache_metadata_path, metadata, indent=2)
            self._last_disk_save_time = time.time()
            self._disk_save_pending = False
        except Exception as e:
            print(f"⚠️ Error saving cache metadata: {e}")
    
    def _start_precache_updater(self):
        """Start background thread that keeps slow-changing data fresh."""
        def update_precache():
            """Background worker to refresh price and bitaxe data between blocks."""
            # Wait for the startup Wi-Fi check to finish (connected OR fell back to
            # setup hotspot — either way, the "is the network up" question is settled)
            # instead of firing off price/bitaxe/network requests blind at t=0. That
            # burst of guaranteed-to-fail attempts was pure wasted CPU on a single-core
            # Pi Zero, competing with the boot-confirmation e-ink push for the same
            # core right when the display worker needs it for its driver imports.
            # Bounded wait: if the event is somehow never set, don't block forever.
            self._startup_wifi_check_done.wait(timeout=90)

            # Initial pre-fill on startup. A failed fetch here
            # doesn't reset price_last_update/network_last_update, so without a retry
            # the next attempt wouldn't happen until the full precache_update_interval_seconds
            # (5 min) later, leaving the price/network preview cards empty that whole time.
            # Retry quickly with backoff until both succeed, or give up after ~3 minutes.
            def _bitaxe_ready():
                if not (self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True)):
                    return True
                bd = self._precache.get('bitaxe_data')
                if not bd:
                    return False
                return bd.get('miners_total', 0) == 0 or bd.get('miners_online', 0) > 0

            startup_retry_delay = 10
            for _ in range(8):
                self._update_precache_data()
                if self._precache.get('price_data') and self._precache.get('network_data') and _bitaxe_ready():
                    break
                time.sleep(startup_retry_delay)
                startup_retry_delay = min(startup_retry_delay * 2, 30)

            # Get update interval from config (default 5 minutes to reduce RPi load)
            update_interval = self._interval('precache_update_interval_seconds')
            last_date = datetime.now().date()

            while True:
                try:
                    # Update every N seconds (default 5 minutes)
                    time.sleep(update_interval)
                    self._update_precache_data()
                    # Flush any pending cache metadata to disk
                    if self._disk_save_pending:
                        self._write_cache_metadata_to_disk()

                    # Detect date change (midnight rollover) — regenerate the
                    # currently displayed image so date and holiday update immediately,
                    # then invalidate + rebuild the pre-render for the next block.
                    current_date = datetime.now().date()
                    if current_date != last_date:
                        print(f"📅 Date changed ({last_date} → {current_date}) — refreshing displayed image")
                        last_date = current_date
                        # Close yesterday's fee samples into one median per
                        # tier. Done here rather than on the next sample so a
                        # day ends on time even if the next reading is late,
                        # and so the only disk write the window makes lands on
                        # the tick that was already doing work.
                        _baseline = getattr(self.image_renderer, 'fee_baseline', None)
                        if _baseline is not None:
                            try:
                                _baseline.roll_over()
                            except Exception as e:
                                print(f"⚠️ Failed to close the fee day: {e}")
                        if hasattr(self, 'socketio') and self.socketio:
                            self.socketio.emit('date_changed', {
                                'date': current_date.isoformat()
                            }, room='authenticated')
                        self._invalidate_prerender()
                        if (self.current_block_height and self.current_block_hash
                                and hasattr(self, 'current_meme_path')
                                and self.current_meme_path
                                and os.path.exists(self.current_meme_path)):
                            self._regenerate_image_with_cached_meme()
                        else:
                            self._background_image_generation(force_eink=True, use_cached_block=True)

                    self._check_tang_reachable()

                    # Refresh pre-rendered next-block image with latest data
                    self._prerender_next_block()
                except Exception as e:
                    print(f"⚠️ Pre-cache update error: {e}")
                    time.sleep(update_interval)  # Continue despite errors
        
        threading.Thread(target=update_precache, daemon=True, name="PreCacheUpdater").start()
    
    # Last reachability answer, so only changes reach the log.
    _tang_reachable = None

    def _check_tang_reachable(self):
        """Warn while the Tang server is away but the store is still open.

        Only that case. A store that failed to open is already handled by
        _start_tang_unlock_retry(), which retries and reports when it succeeds -
        checking here too would duplicate both the request and the log line.

        The gap is the opposite state. Once the key is open it lives in memory,
        so the server can vanish and nothing notices: every read keeps working
        and the device looks healthy, while a restart or a power cut would leave
        it degraded. That is worth saying at the time rather than discovering it
        at the next boot.

        One HTTP GET to the advertisement endpoint - what clevis would contact
        anyway - rather than a full unseal, so a reachable server costs
        milliseconds on a LAN and an unreachable one is bounded by ADV_TIMEOUT.
        """
        store = getattr(self, 'tang_store', None)
        if store is None or not store.is_enabled() or not store.is_ready():
            return

        try:
            _, url, _ = store.tang.settings()
            store.tang.fetch_advertisement(url)
            reachable, detail = True, ''
        except Exception as e:
            reachable, detail = False, str(e)

        if reachable == self._tang_reachable:
            return
        first_check, self._tang_reachable = self._tang_reachable is None, reachable

        if reachable:
            # Nothing to say the first time we look and all is well.
            if not first_check:
                print("🔓 Tang: server reachable again")
        else:
            print(f"⚠️ Tang: server unreachable — {detail}")
            print("⚠️ Sealed data is still open in memory, but a restart would lock it")

        if hasattr(self, 'socketio') and self.socketio:
            try:
                self.socketio.emit('tang_status', {
                    'reachable': reachable,
                    'state': store.state,
                    'reason': '' if reachable else detail,
                }, room='authenticated')
            except Exception:
                pass

    def _invalidate_prerender(self):
        """Invalidate the pre-rendered next-block image so it gets regenerated."""
        with self._prerendered['lock']:
            self._prerendered['block_height'] = None
            self._prerendered['web_base64'] = None
            self._prerendered['eink_img'] = None
            self._prerendered['web_img'] = None
            self._prerendered['meme_path'] = None
            self._prerendered['displayed_blocks'] = None
            self._prerendered['timestamp'] = 0
            self._prerendered['mode_signature'] = self._get_prerender_mode_signature()

    def _store_fresh_price_data(self, price_data, now):
        """Cache a successful price fetch and notify config-page clients if it changed.

        Called from both the periodic pre-cache updater and the on-demand
        image-render fetch, which share the same price_data/price_last_update
        cache slot — only accepting real (non-error) data here, in one place,
        ensures a price obtained via either path is (a) never mistaken for a
        successful update when it's really a network error, and (b) always
        announced over the websocket exactly once when it changes. Caller
        must hold self._precache['lock']. Returns True if the price changed.
        """
        if not price_data or price_data.get('error'):
            return False
        self._precache['price_data'] = price_data
        self._precache['price_last_update'] = now
        if price_data.get('all_prices'):
            self._precache['all_prices'] = price_data['all_prices']

        currency = price_data.get('currency', 'USD')
        price = price_data.get('price_in_selected_currency', 0)
        if price == self._precache['last_price_value']:
            return False

        print(f"💰 Pre-cache updated: Price {price:,.0f} {currency}")
        self._precache['last_price_value'] = price
        if hasattr(self, 'socketio') and self.socketio:
            self.socketio.emit('price_stats_updated', {
                'price': price,
                'currency': currency,
                'moscow_time': price_data.get('moscow_time', 0),
            }, room='authenticated')
        return True

    def _check_for_missed_block(self, tip_height):
        """Notice when the chain has moved on without us and catch up.

        New blocks arrive over a single WebSocket. When that connection dies in
        a way it cannot detect, no block event is ever delivered again and the
        device sits on a stale height indefinitely.

        This is not specific to Tor, though Tor makes it far likelier: a circuit
        can keep TCP nominally alive while carrying nothing, and a reconnect can
        hang in the SOCKS handshake. Clearnet reaches the same state through a
        router dropping an idle NAT mapping, a Wi-Fi roam leaving the socket
        alive but unrouted, or a reverse proxy in front of a self-hosted mempool
        closing an idle connection without a FIN arriving. Ping/pong catches many
        of these, but not a reconnect that never completes — nothing sets a
        connect timeout, so that attempt can block forever.

        Observed in the wild on Tor: the socket dropped, announced a reconnect,
        and no further block was seen while REST calls over the same proxy kept
        working perfectly.

        The pre-cache loop already fetches the tip height every cycle for the
        fee display, so comparing it against the block we last rendered costs
        nothing and bounds any stall to one pre-cache interval — whatever the
        transport, and whatever wedged the socket.
        """
        try:
            if not tip_height:
                return
            tip = int(tip_height)
            current = self.current_block_height
            if current is None or tip <= int(current):
                return
        except (TypeError, ValueError):
            return

        print(f"⚠️ Chain is at {tip} but the last block seen was {current} — "
              f"the block WebSocket has gone quiet, catching up")
        self._recover_missed_block(tip)

    def _recover_missed_block(self, tip_height):
        """Process a block the WebSocket never delivered, and kick the socket.

        Only the hash needs fetching: the WebSocket carries it, the tip-height
        endpoint does not, and the caller already has the height. Asking for
        the hash alone rather than get_current_block_info, which re-resolves
        both, halves the requests — worth it over Tor. Once resolved this goes
        through the ordinary new-block path, so pre-rendering, the e-ink
        refresh and client notifications behave exactly as they would have.
        """
        try:
            block_hash = self.mempool_api.get_tip_hash()
            if not block_hash:
                print("⚠️ Catch-up aborted: could not resolve the block hash")
                return
        except Exception as e:
            print(f"⚠️ Catch-up aborted: {e}")
            return
        height = tip_height

        # Force the monitor to rebuild its connection. Without this the socket
        # stays wedged and every future block needs this same recovery.
        try:
            monitor = getattr(self, 'block_monitor', None)
            if monitor is not None and getattr(monitor, 'ws', None) is not None:
                monitor.ws.close()
                print("⚙️ Closed the stale block WebSocket to force a reconnect")
        except Exception as e:
            print(f"⚠️ Could not close the stale WebSocket: {e}")

        self.on_new_block_received(height, block_hash)

    def _update_precache_data(self):
        """Update pre-cached data (price, bitaxe, fees) in background."""
        data_changed = False
        tip_height_seen = None
        with self._precache['lock']:
            now = time.time()
            update_interval = self._interval('precache_update_interval_seconds')

            # In prioritize_large_scaled_meme mode, pre-select the next meme and the
            # info block types that will actually be shown, so _get_precached_data()
            # (the on-demand render path) can skip fetching data for blocks that
            # won't be drawn this cycle.
            if self.config.get("prioritize_large_scaled_meme", False):
                # Only pre-select when nothing is already queued. This runs every
                # precache_update_interval_seconds (5 min) but a block arrives only
                # every ~10 min, so re-picking each pass threw away roughly half of
                # the selections -- and each discarded one still consumed a slot in
                # the recent-meme window and the no-repeat cycle. The render path
                # clears next_meme_path once it has consumed it.
                pending = self._precache.get('next_meme_path')
                if pending and not os.path.exists(pending):
                    pending = None  # file vanished (meme sync/delete) -- pick again
                if not pending:
                    next_meme = self.image_renderer.pick_random_meme()
                    selected = self.image_renderer._preselect_info_blocks(next_meme)
                    # selected: None (shouldn't happen here), [] (meme fills screen), or list
                    self._precache['next_meme_path'] = next_meme
                    self._precache['selected_block_types'] = selected if selected is not None else []
            else:
                # Clear meme-first preselection artifacts when switching back to balanced mode.
                self._precache['next_meme_path'] = None
                self._precache['selected_block_types'] = None

            # Update price data if stale
            if self._need_block_type('price', 'wallet') and now - self._precache['price_last_update'] > update_interval:
                try:
                    price_data = self.image_renderer.fetch_btc_price()
                    if self._store_fresh_price_data(price_data, now):
                        data_changed = True
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache price: {e}")
            
            # Update Bitaxe data whenever the block is enabled and data is stale. If every
            # configured miner came back offline last time, only trust that for a short
            # window — fetch_bitaxe_stats() has no way to tell "miners are genuinely
            # down" apart from "the Pi's own LAN wasn't reachable yet" (e.g. right after a
            # reboot), and locking that reading in for the full update_interval (5 min by
            # default) makes a transient miss look like a stuck-stale summary card.
            _last_bitaxe = self._precache.get('bitaxe_data') or {}
            _bitaxe_was_all_offline = _last_bitaxe.get('miners_total', 0) > 0 and _last_bitaxe.get('miners_online', 0) == 0
            _bitaxe_interval = (min(update_interval, self._interval('bitaxe_offline_retry_seconds'))
                                if _bitaxe_was_all_offline else update_interval)
            if self._need_block_type('bitaxe') and self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True) and now - self._precache['bitaxe_last_update'] > _bitaxe_interval:
                try:
                    bitaxe_data = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                    if bitaxe_data and not bitaxe_data.get('error'):
                        self._precache['bitaxe_data'] = bitaxe_data
                        self._precache['bitaxe_last_update'] = now
                        
                        # Only log if Bitaxe data actually changed
                        blocks = bitaxe_data.get('valid_blocks', 0)
                        difficulty = bitaxe_data.get('best_difficulty', 0)
                        if blocks != self._precache['last_bitaxe_blocks']:
                            print(f"⛏️ Pre-cache updated: Bitaxe {blocks} blocks, diff {difficulty}")
                            self._precache['last_bitaxe_blocks'] = blocks
                            data_changed = True
                            self._emit_config_page_updates()
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache Bitaxe: {e}")
            
            # Update network stats when at least one network-dependent block is enabled.
            _need_network = self._need_block_type('countdown', 'halving', 'network') and (
                self.config.get("show_countdown_block", True)
                or self.config.get("show_halving_block", True)
                or self.config.get("show_network_block", True)
            )
            if _need_network and now - self._precache['network_last_update'] > update_interval:
                try:
                    network_data = self.mempool_api.get_network_stats()
                    if network_data:
                        self._precache['network_data'] = network_data
                        # A partial result is still worth caching for its pace fields,
                        # but leave the timestamp so the next cycle retries hashrate.
                        if not network_data.get('error'):
                            self._precache['network_last_update'] = now
                        hashrate = network_data.get("currentHashrate")
                        if hashrate is not None and hashrate != self._precache['last_hashrate']:
                            print(f"🌐 Pre-cache updated: Hashrate {self.image_renderer._format_hashrate(hashrate)}")
                            self._precache['last_hashrate'] = hashrate
                            data_changed = True
                            if hasattr(self, 'socketio') and self.socketio:
                                self.socketio.emit('network_stats_updated', {
                                    'hashrate': network_data['currentHashrate'],
                                    'difficulty': network_data['currentDifficulty'],
                                }, room='authenticated')
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache network stats: {e}")

            # Update fee data if stale
            fee_update_interval = update_interval
            sampled_fees = False
            # Carried out of the lock so the baseline can be fed from the same
            # reading, without a second request for the same five numbers.
            sampled_fee_data = None
            if now - self._precache['fee_last_update'] > fee_update_interval:
                sampled_fees = True
                try:
                    fee_param = self.config.get("fee_parameter", "minimumFee")
                    fee_data = self.mempool_api.get_fee_recommendations()
                    block_height = self.mempool_api.get_tip_height()
                    # Checked after the lock is released — see below.
                    tip_height_seen = block_height

                    if fee_data:
                        sampled_fee_data = fee_data
                        self._precache['fee_data'] = fee_data
                        self._precache['block_height'] = block_height
                        self._precache['fee_last_update'] = now

                        # Only log if fee actually changed
                        fee_value = fee_data.get(fee_param, 1)
                        if fee_value != self._precache['last_fee_value']:
                            print(f"💾 Pre-cache updated: Fee {fee_value} sat/vB ({fee_param})")
                            self._precache['last_fee_value'] = fee_value
                            data_changed = True
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache fees: {e}")

        # Feed the rolling baseline that the relative colour scales compare
        # against. All five tiers from the reading we already have - no extra
        # request, and no cold window when fee_parameter changes. Costs one
        # append to a list in RAM; the day is reduced to five medians and
        # written out once, at the rollover below.
        if sampled_fees and sampled_fee_data:
            baseline = getattr(self.image_renderer, 'fee_baseline', None)
            if baseline is not None:
                try:
                    baseline.sample(sampled_fee_data)
                except Exception as e:
                    print(f"⚠️ Failed to sample fee baseline: {e}")

        # Invalidate pre-rendered image so it gets regenerated with fresh data
        if data_changed:
            self._invalidate_prerender()

        # Deliberately outside the lock. Catching up runs the full new-block
        # path, which re-enters _get_precached_data and takes this same lock —
        # and it is a plain Lock, not an RLock, so doing this inside would
        # deadlock the pre-cache thread while holding it, blocking every render.
        self._check_for_missed_block(tip_height_seen)

    def _get_precached_data(self):
        """Get pre-cached data with fallback to fresh fetch if needed.

        When prioritize_large_scaled_meme is active, only fetches data for the
        pre-selected block types stored in _precache['selected_block_types'].
        """
        with self._precache['lock']:
            now = time.time()
            _render_age = self._interval('precache_render_max_age_seconds')
            _fee_age = self._interval('precache_fee_max_age_seconds')

            # One summary line at the end rather than four scattered prints;
            # this runs every five minutes and usually refreshes all of them.
            _refreshed = []

            # Price — needed by price block and wallet fiat conversion
            if self._need_block_type('price', 'wallet'):
                if self._precache_fresh('price', _render_age, now):
                    price_data = self._precache['price_data']
                else:
                    _refreshed.append("price")
                    fresh_price_data = self.image_renderer.fetch_btc_price()
                    self._store_fresh_price_data(fresh_price_data, now)
                    # Fall back to the last known-good cached price on error rather
                    # than clobbering it with the error dict.
                    price_data = self._precache['price_data'] or fresh_price_data
            else:
                price_data = None

            # Bitaxe — skip when block is disabled or not in pre-selected types
            if self._need_block_type('bitaxe') and self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True):
                if self._precache_fresh('bitaxe', _render_age, now):
                    bitaxe_data = self._precache['bitaxe_data']
                else:
                    _refreshed.append("Bitaxe")
                    bitaxe_data = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                    self._precache['bitaxe_data'] = bitaxe_data
                    self._precache['bitaxe_last_update'] = now
            else:
                bitaxe_data = None

            # Fees — always needed (hash frame at bottom uses current fee rate)
            if self._precache_fresh('fee', _fee_age, now):
                fee_data = self._precache['fee_data']
                block_height = self._precache['block_height']
            else:
                _refreshed.append("fees")
                try:
                    fee_data = self.mempool_api.get_fee_recommendations()
                    block_height = self.mempool_api.get_tip_height()
                    self._precache['fee_data'] = fee_data
                    self._precache['block_height'] = block_height
                    self._precache['fee_last_update'] = now
                except Exception as e:
                    print(f"⚠️ Failed to fetch fresh fees: {e}")
                    fee_data = None
                    block_height = None

            # Network stats — only when at least one network-dependent block is selected
            _need_network = self._need_block_type('countdown', 'halving', 'network') and (
                self.config.get("show_countdown_block", True)
                or self.config.get("show_halving_block", True)
                or self.config.get("show_network_block", True)
            )
            if _need_network:
                if self._precache_fresh('network', _render_age, now):
                    network_data = self._precache['network_data']
                else:
                    _refreshed.append("network")
                    try:
                        network_data = self.mempool_api.get_network_stats()
                        if network_data:
                            self._precache['network_data'] = network_data
                            self._precache['network_last_update'] = now
                        else:
                            network_data = self._precache.get('network_data')
                    except Exception as e:
                        print(f"⚠️ Failed to fetch fresh network stats: {e}")
                        network_data = self._precache.get('network_data')
            else:
                network_data = None

            if _refreshed:
                print("🔄 Pre-cache refreshed: " + ", ".join(_refreshed))

            return price_data, bitaxe_data, fee_data, block_height, network_data
