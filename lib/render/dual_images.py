"""The two public entry points producing the web and e-ink images from a single layout pass, including the cached-meme fast path.
"""



class DualImageMixin:
    """The two public entry points producing the web and e-ink images from a single layout pass, including the cached-meme fast path."""

    def render_dual_images(self, block_height, block_hash, mempool_api=None,  startup_mode=False, override_content_path=None, preserve_info_blocks=None, precached_price=None, precached_bitaxe=None, precached_fee=None, precached_block_height=None, precached_network=None, skip_hash_frame=False):
        """
        Render both web-quality and e-ink optimized images efficiently.
        Optimized to share common elements and reduce API calls.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            startup_mode (bool): If True, use cached data only and skip expensive gap limit detection
            override_content_path (str, optional): Force specific meme/image path
            preserve_info_blocks (list, optional): List of block types to preserve ['wallet', 'bitaxe', 'price']
            precached_price (dict, optional): Pre-cached price data to avoid API call
            precached_bitaxe (dict, optional): Pre-cached Bitaxe data to avoid API call
            precached_fee (dict, optional): Pre-cached fee recommendations to avoid API call
            precached_block_height (int, optional): Pre-cached block height to avoid API call
            
        Returns:
            tuple: (web_image, eink_image, content_path, displayed_blocks) - PIL.Image objects, content path, and displayed block types
        """
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info - use pre-cached if available
        if precached_fee and precached_block_height is not None:
            fee_param = self.config.get("fee_parameter", "minimumFee")
            configured_fee = precached_fee.get(fee_param, 1)
            # Always prefer the explicitly passed block_height over stale pre-cached value
            api_block_height = block_height if block_height is not None else precached_block_height
        else:
            configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        
        # Try overrides first, then Twitter content, fallback to memes
        content_path = override_content_path
        
        # Fallback to random meme if no override and no content path yet
        if not content_path:
            content_path = self.pick_random_meme()
        
        # Determine which block types to build:
        #   preserve_info_blocks set → keep an existing layout (config change / wallet refresh)
        #   prioritize_large_scaled_meme → pre-select only the types that fit the meme
        #   otherwise (default layout) → all enabled blocks (renderer will randomise)
        #
        # active_types:
        #   None  = build all enabled blocks (renderer randomises)
        #   []    = meme fills screen — nothing to build
        #   list  = pre-selected / preserved types in display order
        info_blocks = []
        bitaxe_data = None
        btc_price_data = None
        wallet_data = None
        network_data = None
        displayed_blocks = []
        config = self.config

        if preserve_info_blocks is not None:
            active_types = preserve_info_blocks
            print(f"🎭 Preserving info block layout: {active_types}")
        else:
            active_types = self._preselect_info_blocks(content_path, block_height)
            if active_types is not None and not active_types:
                print("ℹ️ Meme fills available space — skipping info block data fetch")

        # Fetch shared network data only when at least one of the three network-dependent
        # blocks will actually be shown.
        _network_types = {'countdown', 'halving', 'network'}
        _need_network = (
            (active_types is None and (
                config.get("show_countdown_block", True)
                or config.get("show_halving_block", True)
                or config.get("show_network_block", True)
            )) or
            (active_types and any(t in _network_types for t in active_types))
        )
        if _need_network:
            if precached_network:
                network_data = precached_network
            elif mempool_api:
                network_data = mempool_api.get_network_stats()

        # Unified block builder — handles both "all enabled" and "specific types" paths.
        def _add_block(block_type):
            nonlocal btc_price_data, bitaxe_data
            if block_type == 'price' and config.get("show_btc_price_block", True):
                btc_price_data = precached_price or self.btc_price_api.fetch_btc_price()
                info_blocks.append((self.render_btc_price_block, btc_price_data))
                displayed_blocks.append('price')
            elif block_type == 'countdown' and config.get("show_countdown_block", True):
                _supply = self._compute_supply_stats(block_height)
                info_blocks.append((self.render_countdown_block, _supply))
                displayed_blocks.append('countdown')
            elif block_type == 'halving' and config.get("show_halving_block", True):
                _halving = self._compute_halving_stats(block_height, network_data)
                info_blocks.append((self.render_halving_block, _halving))
                displayed_blocks.append('halving')
            elif block_type == 'network' and config.get("show_network_block", True):
                info_blocks.append((self.render_network_block, network_data or {}))
                displayed_blocks.append('network')
            elif block_type == 'bitaxe' and config.get("show_bitaxe_block", True):
                bitaxe_data = precached_bitaxe or self.bitaxe_api.fetch_bitaxe_stats()
                info_blocks.append((self.render_bitaxe_block, bitaxe_data))
                displayed_blocks.append('bitaxe')
            elif block_type == 'donation' and config.get("show_donation_block", False):
                _donation_data = getattr(self, '_donation_data', None)
                if _donation_data:
                    info_blocks.append((self.render_donation_block, _donation_data))
                    displayed_blocks.append('donation')
            # 'wallet' is intentionally excluded — handled separately below

        if active_types is None:
            # Default layout: add all enabled blocks; renderer will randomise order.
            for bt in ('price', 'countdown', 'halving', 'network', 'bitaxe'):
                _add_block(bt)
            # Donation included like any other block; renderer handles guarantee vs. random
            _add_block('donation')
        else:
            for bt in active_types:
                _add_block(bt)

        # Wallet block — always positioned last (or at its preserved index) and needs
        # fiat conversion, so it is handled outside the unified loop.
        _want_wallet = config.get("show_wallet_balances_block", True) and (
            active_types is None or 'wallet' in (active_types or [])
        )
        if _want_wallet:
            if startup_mode:
                wallet_data = self.wallet_api.get_cached_wallet_balances()
                if wallet_data is None or wallet_data.get("error"):
                    print("⚠️ [STARTUP-IMG] No cached wallet data available, using default values for immediate display")
                    wallet_data = {
                        "total_btc": 0,
                        "total_fiat": 0,
                        "fiat_currency": config.get("fiat_currency", "USD"),
                        "unit": config.get("btc_unit", "BTC"),
                        "show_fiat": config.get("show_fiat_balance", False),
                        "addresses": [],
                        "xpubs": [],
                    }
                else:
                    print(f"✅ [STARTUP-IMG] Using cached wallet data: {wallet_data.get('total_btc', 0):.8f} BTC")
            else:
                wallet_data = self.wallet_api.get_cached_wallet_balances()
                if wallet_data is None or wallet_data.get("error"):
                    print("⚠️ [IMG] No cached wallet data available or error occurred, using default values")
                    wallet_data = {
                        "total_btc": 0,
                        "total_fiat": 0,
                        "fiat_currency": "USD",
                        "addresses": [],
                        "xpubs": [],
                    }
                else:
                    pass
            
            # Only try to convert to fiat if we have valid wallet data
            if wallet_data.get("total_btc") is not None and not wallet_data.get("error"):
                if btc_price_data:
                    wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data.get("fiat_currency", "USD"))
                else:
                    btc_price_data = self.btc_price_api.fetch_btc_price()
                    if btc_price_data:
                        wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data.get("fiat_currency", "USD"))
                    else:
                        print("⚠️ Failed to fetch BTC price data for wallet balance updates. Use cache as it is.")

            # Add wallet block at its correct position
            if active_types is not None and 'wallet' in active_types:
                wallet_index = active_types.index('wallet')
                info_blocks.insert(wallet_index, (self.render_wallet_balances_block, wallet_data))
            else:
                info_blocks.append((self.render_wallet_balances_block, wallet_data))
            displayed_blocks.append('wallet')

        # When blocks were pre-selected (active_types is a list), pass them directly to
        # the renderer as 'selected_info_blocks' so it skips the random re-shuffle.
        _pre_selected_layout = active_types is not None and bool(active_types)

        # Pass all shared data to both renders
        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "precached_fee": precached_fee,
            "api_block_height": api_block_height,
            "meme_path": content_path,
            "btc_price_data": btc_price_data,
            "bitaxe_data": bitaxe_data,
            "wallet_data": wallet_data,
            "info_blocks": info_blocks,
            "displayed_blocks": displayed_blocks,
            "preserve_layout": preserve_info_blocks is not None,
            # Pre-populate selected_info_blocks to skip renderer re-shuffle when the
            # block order was already decided here (pre-selection or preservation).
            "selected_info_blocks": info_blocks if _pre_selected_layout else None,
        }

        # === GENERATE WEB IMAGE ===
        self._apply_layout_settings()
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True, startup_mode=startup_mode,
            skip_hash_frame=skip_hash_frame
        )
        
        # === GENERATE E-INK IMAGE ===
        eink_img = None
        if self.e_ink_enabled:
            self._apply_layout_settings()
            if self.config.get("opsec_mode_enabled", False):
                # OPSec mode: show a random family/cover photo instead of BTC data
                eink_img = self.render_opsec_eink_image()
            else:
                eink_img = self._render_image_with_shared_data(
                    block_height, block_hash, mempool_api,
                    shared_data, web_quality=False, startup_mode=startup_mode,
                    skip_hash_frame=skip_hash_frame
                )

        self._apply_layout_settings()

        print(f"✅ Image generated for block {block_height}")
        return web_img, eink_img, content_path, displayed_blocks  # Return images, content path, and displayed block types
    
    def render_dual_images_with_cached_meme(self, block_height, block_hash, cached_meme_path, mempool_api=None,
                                             precached_price=None, precached_bitaxe=None, precached_fee=None,
                                             precached_network=None):
        """
        Render both web-quality and e-ink optimized images using a specific cached meme.
        Used when configuration changes require image refresh but meme should stay the same.
        
        Args:
            block_height (str): Current Bitcoin block height
            block_hash (str): Current Bitcoin block hash
            cached_meme_path (str): Path to the cached meme to use
            mempool_api (MempoolAPI, optional): Mempool API instance for formatting
            precached_price (dict, optional): Pre-cached price data as fallback
            precached_bitaxe (dict, optional): Pre-cached Bitaxe data as fallback
            precached_fee (dict, optional): Pre-cached fee data as fallback
            
        Returns:
            tuple: (web_image, eink_image, meme_path) - Both PIL.Image objects and used meme path
        """
        # === SHARED DATA COLLECTION (done once) ===
        # Get holiday info once
        holiday_info = self.get_today_btc_holiday()
        
        # Get fee info - use pre-cached as fallback if API fails
        if precached_fee is not None:
            fee_param = self.config.get("fee_parameter", "minimumFee")
            configured_fee = precached_fee.get(fee_param, 1)
            api_block_height = block_height
        else:
            configured_fee, api_block_height = self.get_fee_and_block_info(mempool_api)
        # Always prefer the explicitly passed block_height over API-fetched value
        if block_height is not None:
            api_block_height = block_height
        
        # Use the provided cached meme path
        meme_path = cached_meme_path
        
        # Fetch info block data ONCE
        btc_price_data = None
        bitaxe_data = None
        wallet_data = None
        network_data = precached_network

        config = self.config

        # When the meme-first layout is active, check upfront whether any info block
        # could actually fit below the cached meme.  If not, skip all data fetching —
        # unless donation is guaranteed (renderer will pre-reserve space for it).
        _donation_data_pre = getattr(self, '_donation_data', None)
        _donation_guaranteed_pre = (
            isinstance(_donation_data_pre, dict)
            and bool(_donation_data_pre.get('_guaranteed'))
            and config.get("show_donation_block", False)
        )
        _skip_info_blocks = (
            config.get("prioritize_large_scaled_meme", False)
            and meme_path is not None
            and not self._info_blocks_can_fit(meme_path, block_height)
            and not _donation_guaranteed_pre
        )
        if _skip_info_blocks:
            print("ℹ️ Meme fills available space — skipping info block data fetch")

        # Fetch live network stats if not precached and any of the new blocks are enabled
        _need_network = (
            config.get("show_countdown_block", True)
            or config.get("show_halving_block", True)
            or config.get("show_network_block", True)
        )
        if _need_network and not _skip_info_blocks and network_data is None and mempool_api:
            network_data = mempool_api.get_network_stats()

        # Build info blocks ONCE
        info_blocks = []
        if not _skip_info_blocks:
            if config.get("show_btc_price_block", True):
                btc_price_data = precached_price or self.btc_price_api.fetch_btc_price()
                info_blocks.append((self.render_btc_price_block, btc_price_data))
            if config.get("show_countdown_block", True):
                _supply = self._compute_supply_stats(block_height)
                info_blocks.append((self.render_countdown_block, _supply))
            if config.get("show_halving_block", True):
                _halving = self._compute_halving_stats(block_height, network_data)
                info_blocks.append((self.render_halving_block, _halving))
            if config.get("show_network_block", True):
                info_blocks.append((self.render_network_block, network_data or {}))
            if config.get("show_bitaxe_block", True):
                bitaxe_data = precached_bitaxe or self.bitaxe_api.fetch_bitaxe_stats()
                info_blocks.append((self.render_bitaxe_block, bitaxe_data))
            if config.get("show_wallet_balances_block", True):
                wallet_data = self.wallet_api.get_cached_wallet_balances()
                if wallet_data is None or wallet_data.get("error"):
                    wallet_data = {
                        "total_btc": 0,
                        "total_fiat": 0,
                        "fiat_currency": "USD",
                        "addresses": [],
                        "xpubs": [],
                    }

                # Only try to convert to fiat if we have valid wallet data
                if wallet_data.get("total_btc") is not None and not wallet_data.get("error"):
                    if btc_price_data:
                        wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data.get("fiat_currency", "USD"))
                    else:
                        btc_price_data = self.btc_price_api.fetch_btc_price()
                        if btc_price_data:
                            wallet_data["total_fiat"] = self.wallet_api._convert_to_fiat(wallet_data["total_btc"], wallet_data.get("fiat_currency", "USD"))
                        else:
                            print("⚠️ Failed to fetch BTC price data for wallet balance updates. Use cache as it is.")

                info_blocks.append((self.render_wallet_balances_block, wallet_data))
        # Add donation when info blocks are not skipped, OR when donation is guaranteed
        # (even if the meme fills the screen, the renderer will pre-reserve space).
        if not _skip_info_blocks or _donation_guaranteed_pre:
            _donation_data = getattr(self, '_donation_data', None)
            if _donation_data and config.get("show_donation_block", False):
                info_blocks.append((self.render_donation_block, _donation_data))

        shared_data = {
            "holiday_info": holiday_info,
            "configured_fee": configured_fee,
            "precached_fee": precached_fee,
            "api_block_height": api_block_height,
            "meme_path": meme_path,
            "btc_price_data": btc_price_data,
            "bitaxe_data": bitaxe_data,
            "wallet_data": wallet_data,
            "info_blocks": info_blocks,
            # ...add any other shared data...
        }

        # === GENERATE WEB IMAGE ===
        self._apply_layout_settings()
        web_img = self._render_image_with_shared_data(
            block_height, block_hash, mempool_api,
            shared_data, web_quality=True
        )
        
        # === GENERATE E-INK IMAGE ===
        self._apply_layout_settings()
        if self.config.get("opsec_mode_enabled", False):
            # OPSec mode: show a random family/cover photo instead of BTC data
            eink_img = self.render_opsec_eink_image()
        else:
            eink_img = self._render_image_with_shared_data(
                block_height, block_hash, mempool_api,
                shared_data, web_quality=False
            )

        # Restore default
        self._apply_layout_settings()

        return web_img, eink_img, meme_path
