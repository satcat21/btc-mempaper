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
        if now - self._last_disk_save_time < 300:
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
            update_interval = self.config.get("precache_update_interval_seconds", 300)
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

                    # Refresh pre-rendered next-block image with latest data
                    self._prerender_next_block()
                except Exception as e:
                    print(f"⚠️ Pre-cache update error: {e}")
                    time.sleep(update_interval)  # Continue despite errors
        
        threading.Thread(target=update_precache, daemon=True, name="PreCacheUpdater").start()
    
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

    def _update_precache_data(self):
        """Update pre-cached data (price, bitaxe, fees) in background."""
        data_changed = False
        with self._precache['lock']:
            now = time.time()
            update_interval = self.config.get("precache_update_interval_seconds", 300)

            # In prioritize_large_scaled_meme mode, pre-select the next meme and the
            # info block types that will actually be shown, so _get_precached_data()
            # (the on-demand render path) can skip fetching data for blocks that
            # won't be drawn this cycle.
            if self.config.get("prioritize_large_scaled_meme", False):
                next_meme = self.image_renderer.pick_random_meme()
                selected = self.image_renderer._preselect_info_blocks(next_meme)
                # selected: None (shouldn't happen here), [] (meme fills screen), or list
                self._precache['next_meme_path'] = next_meme
                self._precache['selected_block_types'] = selected if selected is not None else []
            else:
                # Clear meme-first preselection artifacts when switching back to balanced mode.
                self._precache['next_meme_path'] = None
                self._precache['selected_block_types'] = None

            # Mirrors _get_precached_data()'s _need_type(): None (balanced mode, or
            # types not yet preselected this cycle) always fetches, same as before.
            _selected = self._precache.get('selected_block_types')

            def _need_type(*types):
                return _selected is None or any(t in _selected for t in types)

            # Update price data if stale
            if _need_type('price', 'wallet') and now - self._precache['price_last_update'] > update_interval:
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
            _bitaxe_interval = min(update_interval, 30) if _bitaxe_was_all_offline else update_interval
            if _need_type('bitaxe') and self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True) and now - self._precache['bitaxe_last_update'] > _bitaxe_interval:
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
            _need_network = _need_type('countdown', 'halving', 'network') and (
                self.config.get("show_countdown_block", True)
                or self.config.get("show_halving_block", True)
                or self.config.get("show_network_block", True)
            )
            if _need_network and now - self._precache['network_last_update'] > update_interval:
                try:
                    hd = self.mempool_api.get_hashrate_and_difficulty()
                    da = self.mempool_api.get_difficulty_adjustment()
                    if hd:
                        network_data = {
                            "currentHashrate": hd.get("currentHashrate", 0),
                            "currentDifficulty": hd.get("currentDifficulty", 0),
                            "timeAvg": da.get("timeAvg", 600000) if da else 600000,
                        }
                        self._precache['network_data'] = network_data
                        self._precache['network_last_update'] = now
                        hashrate = network_data["currentHashrate"]
                        if hashrate != self._precache['last_hashrate']:
                            print(f"🌐 Pre-cache updated: Hashrate {hashrate/1e18:.2f} EH/s")
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
            if now - self._precache['fee_last_update'] > fee_update_interval:
                try:
                    fee_param = self.config.get("fee_parameter", "minimumFee")
                    fee_data = self.mempool_api.get_fee_recommendations()
                    block_height = self.mempool_api.get_tip_height()
                    
                    if fee_data:
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

        # Invalidate pre-rendered image so it gets regenerated with fresh data
        if data_changed:
            self._invalidate_prerender()
    
    def _get_precached_data(self):
        """Get pre-cached data with fallback to fresh fetch if needed.

        When prioritize_large_scaled_meme is active, only fetches data for the
        pre-selected block types stored in _precache['selected_block_types'].
        """
        with self._precache['lock']:
            now = time.time()

            # Determine which block types will actually be shown.
            # None  → all blocks (default layout)
            # list  → only those types (pre-selected for prioritize_large_scaled_meme)
            _selected = self._precache.get('selected_block_types')  # None or list

            def _need_type(*types):
                return _selected is None or any(t in _selected for t in types)

            # Price — needed by price block and wallet fiat conversion
            if _need_type('price', 'wallet'):
                if self._precache['price_data'] and (now - self._precache['price_last_update'] < 120):
                    price_data = self._precache['price_data']
                else:
                    print("🔄 Pre-cache stale, fetching fresh price...")
                    fresh_price_data = self.image_renderer.fetch_btc_price()
                    self._store_fresh_price_data(fresh_price_data, now)
                    # Fall back to the last known-good cached price on error rather
                    # than clobbering it with the error dict.
                    price_data = self._precache['price_data'] or fresh_price_data
            else:
                price_data = None

            # Bitaxe — skip when block is disabled or not in pre-selected types
            if _need_type('bitaxe') and self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True):
                if self._precache['bitaxe_data'] and (now - self._precache['bitaxe_last_update'] < 120):
                    bitaxe_data = self._precache['bitaxe_data']
                else:
                    print("🔄 Pre-cache stale, fetching fresh Bitaxe...")
                    bitaxe_data = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                    self._precache['bitaxe_data'] = bitaxe_data
                    self._precache['bitaxe_last_update'] = now
            else:
                bitaxe_data = None

            # Fees — always needed (hash frame at bottom uses current fee rate)
            if self._precache['fee_data'] and (now - self._precache['fee_last_update'] < 90):
                fee_data = self._precache['fee_data']
                block_height = self._precache['block_height']
            else:
                print("🔄 Pre-cache stale, fetching fresh fees...")
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
            _need_network = _need_type('countdown', 'halving', 'network') and (
                self.config.get("show_countdown_block", True)
                or self.config.get("show_halving_block", True)
                or self.config.get("show_network_block", True)
            )
            if _need_network:
                if self._precache['network_data'] and (now - self._precache['network_last_update'] < 120):
                    network_data = self._precache['network_data']
                else:
                    print("🔄 Pre-cache stale, fetching fresh network stats...")
                    try:
                        hd = self.mempool_api.get_hashrate_and_difficulty()
                        da = self.mempool_api.get_difficulty_adjustment()
                        if hd:
                            network_data = {
                                "currentHashrate": hd.get("currentHashrate", 0),
                                "currentDifficulty": hd.get("currentDifficulty", 0),
                                "timeAvg": da.get("timeAvg", 600000) if da else 600000,
                            }
                            self._precache['network_data'] = network_data
                            self._precache['network_last_update'] = now
                        else:
                            network_data = self._precache.get('network_data')
                    except Exception as e:
                        print(f"⚠️ Failed to fetch fresh network stats: {e}")
                        network_data = self._precache.get('network_data')
            else:
                network_data = None

            return price_data, bitaxe_data, fee_data, block_height, network_data
