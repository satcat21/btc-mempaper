"""
Main Application Module - Mempaper Bitcoin Dashboard

This is the main Flask application that coordinates all components:
- Web server and SocketIO for real-time updates
- Integration with Bitcoin mempool for block data
- Image rendering and e-Paper display
- WebSocket management for live updates

Version: 2.0 (Refactored)
"""

import time
import json
import io
import base64
import threading
import multiprocessing
import urllib3
import os
import logging
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, send_file, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO

# Import custom modules
from lib.mempool_api import MempoolAPI
from lib.websocket_client import MempoolWebSocket
from lib.image_renderer import ImageRenderer
from utils.translations import translations
from managers.config_manager import ConfigManager
from utils.technical_config import TechnicalConfig
from utils.security_config import SecurityConfig
from managers.secure_cache_manager import SecureCacheManager
from managers.auth_manager import AuthManager, require_auth, require_web_auth, require_rate_limit, require_mobile_auth
from managers.mobile_token_manager import MobileTokenManager

# Privacy utilities for secure logging
try:
    from utils.privacy_utils import BitcoinPrivacyMasker
    PRIVACY_UTILS_AVAILABLE = True
except ImportError:
    PRIVACY_UTILS_AVAILABLE = False

# Disable SSL warnings for local mempool connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MempaperApp:
    """Main application class that coordinates all components."""
    
    def __init__(self, config_path="config/config.json"):
        """
        Initialize the Mempaper application.
        
        Args:
            config_path (str): Path to configuration file
        """
        
        # Ensure required directories exist
        os.makedirs("config", exist_ok=True)
        os.makedirs("cache", exist_ok=True)
        
        # Initialize configuration manager
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_current_config()
        
        # Merge in hardcoded technical settings
        technical_settings = TechnicalConfig.get_all_technical_settings()
        self.config.update(technical_settings)
        
        # Log technical configuration for debugging
        TechnicalConfig.log_technical_settings()
        
        # Initialize Flask app and SocketIO
        self._init_app_components()
        
        # Note: Callback registration moved to end of __init__ to avoid issues during initialization

        # --- CHECK BLOCK HEIGHT ON STARTUP BUT DON'T FORCE REGENERATION ---
        # Let _generate_initial_image handle this logic properly
        try:
            block_info = self.mempool_api.get_current_block_info()
            # Safely compare block heights (converting to string to avoid type mismatch)
            current_bh = str(block_info.get('block_height', ''))
            cached_bh = str(self.current_block_height) if hasattr(self, 'current_block_height') and self.current_block_height is not None else None
            
            if (cached_bh and current_bh and cached_bh != current_bh):
                print(f"⚙️ [STARTUP] Block changed since last run: {cached_bh} → {current_bh}")
                self.image_is_current = False  # Mark as outdated for _generate_initial_image to handle
            elif cached_bh and current_bh and cached_bh == current_bh:
                print(f"👁️ [STARTUP] Block unchanged: {current_bh} - cache is valid")
                self.image_is_current = True  # Mark as current - no regeneration needed
        except Exception as e:
            print(f"⚠️ [STARTUP] Failed to check current block: {e}")
            self.image_is_current = False  # Mark as outdated if we can't verify
    
    def _init_flask_app(self):
        """Initialize Flask application and configure it."""
        # Initialize Flask app
        self.app = Flask(__name__, static_folder="static")
        self.app.secret_key = SecurityConfig.get_secret_key_from_env_or_generate()  # For session management
        
        # Configure session settings for longer-lived sessions
        self.app.config['PERMANENT_SESSION_LIFETIME'] = SecurityConfig.SESSION_TIMEOUT
        self.app.config['SESSION_COOKIE_SECURE'] = False  # Set to True for HTTPS
        self.app.config['SESSION_COOKIE_HTTPONLY'] = True
        self.app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    def _init_socketio(self):
        """Initialize SocketIO with proper configuration."""
        # Configure SocketIO with extended timeouts for 48-hour sessions
        skip_socketio = self.config.get("skip_socketio_on_startup", False)
        if skip_socketio:
            print("⚙️ Skipping SocketIO initialization for faster startup")
            self.socketio = None
        else:
            # Auto-detect async mode based on environment and available packages
            is_production = os.getenv('FLASK_ENV') == 'production' or os.getenv('GUNICORN_CMD_ARGS') is not None
            
            # Check if gevent is available
            try:
                import gevent
                gevent_available = True
            except ImportError:
                gevent_available = False
            
            # Use gevent only if available and in production, otherwise use threading
            async_mode = "gevent" if (is_production and gevent_available) else "threading"
            
            # Raspberry Pi Zero WH optimizations (512MB RAM, single core)
            # is_pi_zero = os.path.exists('/proc/device-tree/model') and 'Zero' in open('/proc/device-tree/model', 'rb').read().decode('utf-8', errors='ignore')
            
            socketio_config = {
                'cors_allowed_origins': '*', 
                'async_mode': async_mode,  # Auto-detect: gevent for production, threading for development
                'ping_timeout': 120,       # Increase timeout to 2 minutes
                'ping_interval': 45,       # Increase ping interval  
                'max_http_buffer_size': 10000000,  # 10MB buffer
                'engineio_logger': False,  # Disable engineio logger to suppress transport warnings
                'logger': False,           # Disable SocketIO logger to reduce noise
                'always_connect': True,    # Force connection acceptance
                'manage_session': False,   # Don't manage Flask sessions for SocketIO
                'cors_credentials': False, # Disable credentials for CORS to simplify
                'transports': ['websocket', 'polling']  # Explicitly allow websocket and polling
            }
            print(f"🚀 SocketIO async mode: {async_mode} ({'production' if is_production else 'development'})")
            # if is_pi_zero:
            #     print("🍓 Raspberry Pi Zero detected - using optimized settings")
            
            # Suppress Engine.IO transport warnings at Python logging level
            logging.getLogger('engineio').setLevel(logging.CRITICAL)
            logging.getLogger('engineio.server').setLevel(logging.CRITICAL)
            logging.getLogger('socketio').setLevel(logging.CRITICAL)
            logging.getLogger('socketio.server').setLevel(logging.CRITICAL)
            
            self.socketio = SocketIO(self.app, **socketio_config)
    
    def _init_app_components(self):
        """Initialize the main application components."""
        # Initialize Flask app first
        self._init_flask_app()
        
        # Initialize SocketIO
        self._init_socketio()
        
        # Initialize authentication manager with config_manager for secure password handling
        self.auth_manager = AuthManager(self.config_manager)
        
        # Initialize secure cache manager for mobile token storage
        self.secure_cache_manager = SecureCacheManager("cache/mobile_tokens.json")
        
        # Initialize mobile token manager for Flutter app authentication
        self.mobile_token_manager = MobileTokenManager(self.secure_cache_manager)
        
        # Initialize block notification subscription tracking
        self.block_notification_subscribers = set()  # Track clients subscribed to block notifications
        
        # Get translations for configured language
        lang = self.config.get("language", "en")
        self.translations = translations.get(lang, translations["en"])
        
        # Initialize API clients
        self._init_api_clients()
        
        # Initialize image renderer
        self.image_renderer = ImageRenderer(self.config, self.translations)
        
        # Initialize block reward monitor (with block callbacks as backup to WebSocket)
        from lib.block_monitor import initialize_block_monitor
        self.block_monitor = initialize_block_monitor(
            self.config_manager, 
            self.on_new_block_received,  # Use same callback as WebSocket for consistency
            self.on_new_block_notification if hasattr(self, 'on_new_block_notification') else None
        )
        
        # Sync cache to current blockchain height (important for recovery after downtime)
        if self.block_monitor:
            try:
                self.block_monitor.sync_cache_to_current()
            except Exception as e:
                print(f"⚠️ Cache sync failed: {e}")
        
        # Start block monitoring if addresses are configured and not skipped for fast startup
        skip_block_monitoring = self.config.get("skip_block_monitoring_on_startup", False)
        if not skip_block_monitoring:
            self.block_monitor.start_monitoring()
            block_table_addresses = self.config.get("block_reward_addresses_table", [])
            total_addresses = len(block_table_addresses)
            if total_addresses > 0:
                print(f"👁️ Block reward monitoring started for {total_addresses} addresses")
            # else:
            #     print("📡 Block monitoring started (no reward addresses configured, will still trigger updates on new blocks)")
        else:
            print("⚙️ Skipping block monitoring for faster startup")
        
        # Check e-Paper display configuration
        self.e_ink_enabled = self.config.get("e-ink-display-connected", True)
        if self.e_ink_enabled:
            print("⚙️ e-Paper display enabled")
        else:
            print("⚙️ e-Paper display disabled - running in display-less mode")
        
        # Image caching variables
        self.current_image_path = "cache/current.png"  # High-quality web image
        self.current_eink_image_path = "cache/current_eink.png"  # E-ink optimized image
        self.cache_metadata_path = "cache/cache.json"  # Persistent cache state
        
        self.current_block_height = None
        self.current_block_hash = None
        self.current_meme_path = None  # Cache current meme for config-triggered regeneration
        self.image_is_current = False
        
        # E-ink display tracking to prevent unnecessary updates
        self.last_eink_block_height = None
        self.last_eink_block_hash = None
        
        # Track currently displayed info blocks and their data for smart regeneration
        self.displayed_info_blocks = []  # List of block types shown: ['wallet', 'bitaxe', 'price']
        self.displayed_bitaxe_data = None  # Cache Bitaxe data shown in current image
        
        # Block tracker for e-ink display race condition prevention
        self.block_tracker = {}
        
        # E-ink display process management for cancellation
        self.active_display_processes = {}  # {block_height: subprocess.Popen}
        self.display_process_lock = threading.Lock()
        
        # Image generation lock to prevent concurrent generation
        self.generation_lock = threading.Lock()
        
        # Block processing lock to prevent duplicate block processing
        self._block_processing_lock = threading.Lock()
        
        # 🚀 Pre-cached data for fast image generation (refreshed in background)
        self._precache = {
            'price_data': None,
            'bitaxe_data': None,
            'price_last_update': 0,
            'bitaxe_last_update': 0,
            'last_price_value': None,  # Track last price to detect changes
            'last_bitaxe_blocks': None,  # Track last Bitaxe blocks to detect changes
            'lock': threading.Lock()
        }
        
        # Load persistent cache state from file
        self._load_cache_metadata()
        
        # Start background pre-cache updater
        self._start_precache_updater()
        
        # Note: Configuration change callbacks registered at end of __init__
        
        # Setup Flask routes
        self._setup_routes()

        # Initialize websocket_client to None - will be set up in background
        self.websocket_client = None
        self._setup_instant_startup()

        # Register callbacks for configuration changes (done after all components are initialized)
        self.config_manager.add_change_callback(self._on_config_file_changed)
        self.config_manager.add_change_callback(self._on_config_change)
        # On Windows, force config reload and callback notification after registering callbacks
        if os.name == 'nt':
            self.config_manager._reload_config_from_file()
            self.config_manager._notify_change_callbacks(self.config_manager.config)
        print("✅ Mempaper application initialized successfully")
    
    def _init_api_clients(self):
        # Mempool API setup with HTTPS support
        mempool_host = self.config.get("mempool_host", "127.0.0.1")
        mempool_rest_port = self.config.get("mempool_rest_port", "4081")
        mempool_use_https = self.config.get("mempool_use_https", False)
        mempool_verify_ssl = self.config.get("mempool_verify_ssl", True)
        
        protocol = 'HTTPS' if mempool_use_https else 'HTTP'
        print(f"🌐 Mempool API: {protocol}://{mempool_host}:{mempool_rest_port}/api")
        
        self.mempool_api = MempoolAPI(
            host=mempool_host,
            port=mempool_rest_port,
            use_https=mempool_use_https,
            verify_ssl=mempool_verify_ssl
        )
    
    def _init_websocket(self):
        """Initialize WebSocket connection for real-time updates."""
        # Skip WebSocket for faster PC startup if configured
        skip_websocket = self.config.get("skip_websocket_on_startup", False)
        if skip_websocket:
            print("⚙️ Skipping WebSocket initialization for faster startup")
            self.websocket_client = None
            return
            
        # Get WebSocket configuration
        mempool_host = self.config.get("mempool_host", "127.0.0.1")
        mempool_ws_port = self.config.get("mempool_ws_port", "8999")
        mempool_ws_path = self.config.get("mempool_ws_path", "/api/v1/ws")
        mempool_use_https = self.config.get("mempool_use_https", False)
        mempool_verify_ssl = self.config.get("mempool_verify_ssl", True)
        
        # WebSocket URL already logged by block_monitor
        # print(f"📶 Using mempool host for WebSocket: {mempool_host}")
        
        # Create WebSocket client with proper protocol and path
        self.websocket_client = MempoolWebSocket(
            host=mempool_host,
            port=mempool_ws_port,
            path=mempool_ws_path,
            use_wss=mempool_use_https,  # Use WSS if HTTPS is enabled
            on_new_block_callback=self.on_new_block_received,
            verify_ssl=mempool_verify_ssl
        )
        
        # Configure network outage tolerance (how long to retry before giving up)
        network_outage_tolerance_minutes = self.config.get("network_outage_tolerance_minutes", 45)  # Default 45 minutes
        self.websocket_client.set_network_tolerance(max_outage_minutes=network_outage_tolerance_minutes)
        
        # Connection details logged by websocket_client and block_monitor
    
    def _generate_initial_image(self):
        """Generate initial dashboard image on startup - optimized for fast start."""
        
        # FIRST: Check if wallet monitoring is enabled
        from managers.config_manager import ConfigManager
        config_manager = ConfigManager()
        
        wallet_monitoring_enabled = config_manager.get("show_wallet_balances_block", True)
        
        if not wallet_monitoring_enabled:
            pass  # Wallet monitoring disabled - skip bootstrap check silently
        else:
            # Check if wallet bootstrap is needed at startup - smart cache-based decision
            print("💾 Checking if wallet bootstrap is needed at startup...")
            try:
                # Get wallet addresses from config - use correct config keys
                wallet_addresses = []
                
                # Try the correct wallet balance config keys from the debug output
                # Get wallet addresses from modern table format only
                wallet_addresses = config_manager.get("wallet_balance_addresses_with_comments", [])
                if wallet_addresses:
                    print(f"👁️ [DEBUG] Found {len(wallet_addresses)} wallet entries in 'wallet_balance_addresses_with_comments'")
                else:
                    # Fallback check for any legacy configurations (just for debugging)
                    legacy_addresses = config_manager.get("wallet_balance_addresses", [])
                    if legacy_addresses:
                        print(f"⚠️ [DEBUG] Found {len(legacy_addresses)} entries in legacy 'wallet_balance_addresses' field - these should be migrated to the table format")
                        wallet_addresses = legacy_addresses
                
                if not wallet_addresses:
                    print(f"👁️ [DEBUG] No wallet addresses found in configuration")
                
                # Debug: show what we found
                if wallet_addresses:
                    for i, entry in enumerate(wallet_addresses[:3]):  # Show first 3
                        if isinstance(entry, dict):
                            address = entry.get("address", "")
                            comment = entry.get("comment", "")
                            print(f"   [DEBUG] Entry {i}: {address[:20]}... ({comment})")
                        else:
                            print(f"   [DEBUG] Entry {i}: {str(entry)[:20]}...")
                else:
                    print(f"👁️ [DEBUG] No wallet addresses found in any config source")
                
                extended_keys = []
                
                for entry in wallet_addresses:
                    if isinstance(entry, dict):
                        address = entry.get("address", "")
                    else:
                        address = str(entry)
                    
                    # Check if it's an extended key (XPUB/ZPUB are typically 100+ characters)
                    if len(address) > 50 and (address.lower().startswith(('xpub', 'zpub', 'ypub'))):
                        extended_keys.append(address)
                
                if not wallet_addresses:
                    print("⚙️ No wallet addresses configured - skipping bootstrap")
                elif not extended_keys:
                    # For regular addresses, try to get cached data
                    try:
                        wallet_data = self.wallet_balance_api.get_cached_wallet_balances()
                        if wallet_data and 'addresses' in wallet_data:
                            total_balance = wallet_data.get('total_btc', 0)
                            print(f"✅ [STARTUP] Regular addresses only: {len(wallet_data.get('addresses', []))} addresses, {total_balance} BTC total")
                        else:
                            print(f"✅ [STARTUP] Regular addresses configured but no cached balance data")
                    except Exception as cache_e:
                        print(f"✅ [STARTUP] Regular addresses configured (cache check failed: {cache_e})")
                else:
                    # Extended keys found - check if we have valid cached address derivation
                    print(f"🔑 [STARTUP] Found {len(extended_keys)} extended key(s) - checking cache status...")
                    
                    bootstrap_needed = False
                    current_height = 0
                    current_hash = "unknown"
                    
                    # Get current block info for cache validation
                    try:
                        current_block_info = self.mempool_api.get_current_block_info()
                        current_height = current_block_info['block_height']
                        current_hash = current_block_info['block_hash']
                    except Exception as e:
                        print(f"⚠️ Could not get current block info: {e}")
                    
                    # Check async wallet address cache for each extended key
                    for xpub in extended_keys:
                        cache_status = self._check_async_wallet_cache_status(xpub, current_height)
                        
                        if cache_status == "missing":
                            print(f"🚀 [STARTUP] No cached addresses found for {xpub[:20]}... - bootstrap needed")
                            bootstrap_needed = True
                            break
                        elif cache_status == "outdated":
                            print(f"⚙️ [STARTUP] Cached addresses outdated for {xpub[:20]}... - bootstrap needed")
                            bootstrap_needed = True
                            break
                        # elif cache_status == "valid":
                        #     print(f"✅ [STARTUP] Valid cached addresses found for {xpub[:20]}... - bootstrap not needed")
                        # else:
                        elif cache_status != "valid":
                            print(f"⚠️ [STARTUP] Unknown cache status for {xpub[:20]}... - bootstrap needed as fallback")
                            bootstrap_needed = True
                            break
                    
                    if bootstrap_needed:
                        print("🚀 [STARTUP] Triggering bootstrap detection for extended keys...")
                        threading.Thread(
                            target=self._safe_wallet_refresh_thread,
                            args=(current_height, current_hash, True),  # True for startup_mode
                            daemon=True
                        ).start()
                        print("✅ [STARTUP] Bootstrap detection started in background")
                    else:
                        print("✅ [STARTUP] All extended keys have valid cached data")
            except Exception as e:
                print(f"⚠️ Could not check wallet status: {e}")
        
        # Get current block info for image cache comparison
        try:
            current_block_info = self.mempool_api.get_current_block_info()
            current_height = current_block_info['block_height']
            current_hash = current_block_info['block_hash']
        except Exception as e:
            print(f"⚠️ Could not get current block info: {e}")
            # Proceed with generation if we can't get block info
            current_height = None
            current_hash = None
        
        # If we have valid cache metadata and current block info
        if (self.current_block_height is not None and 
            self.image_is_current and 
            os.path.exists(self.current_image_path) and
            os.path.exists(self.current_eink_image_path) and
            current_height is not None):
            
            # Check if cache is for the current block
            if (self.current_block_height == current_height and
                self.current_block_hash == current_hash):
                print(f"💾 Cache is current for block {current_height} - skipping generation")
                return
            else:
                print(f"👁️ Block changed: {self.current_block_height} → {current_height}")
                self.image_is_current = False
        
        # Check for recent cached image as fallback
        elif os.path.exists(self.current_image_path) and current_height is not None:
            file_age = time.time() - os.path.getmtime(self.current_image_path)
            if file_age < 3600:  # Less than 1 hour old
                # If we don't know what block our cached image is for, mark as outdated
                # Use string comparison to avoid type mismatches
                if (self.current_block_height is None or 
                    str(self.current_block_height) != str(current_height)):
                    self.image_is_current = False
                    # Do NOT return here - allow generation to proceed
                else:
                    self.current_block_height = current_height
                    self.current_block_hash = current_hash
                    self.image_is_current = True
                    self._save_cache_metadata()
                    return
        
        # Check if we have a recent cached image first
        if os.path.exists(self.current_image_path):
            file_age = time.time() - os.path.getmtime(self.current_image_path)
            if file_age < 3600:  # Less than 1 hour old
                # Check if the cached image is for the current block
                try:
                    block_info = self.mempool_api.get_current_block_info()
                    
                    # If we don't know what block our cached image is for, or it's for a different block
                    # Use string comparison to avoid type mismatches
                    if (self.current_block_height is None or 
                        str(self.current_block_height) != str(block_info['block_height'])):
                        self.image_is_current = False
                        # Do NOT return here - allow generation to proceed
                    else:
                        self.current_block_height = block_info['block_height']
                        self.current_block_hash = block_info['block_hash']
                        self.image_is_current = True  # Mark as current since it's for the right block
                        # Save metadata to ensure persistence
                        self._save_cache_metadata()
                        return
                except Exception as e:
                    print(f"⚠️ Could not verify block info, marking image as potentially outdated: {e}")
                    self.image_is_current = False
                    # Allow generation to proceed

        
        try:
            print("⚙️ Generating initial dashboard image with cached data...")
            
            # Get current block info from mempool API
            try:
                block_info = self.mempool_api.get_current_block_info()
                # Check for invalid block data
                if block_info.get('block_height') is None:
                     raise ValueError("Block height is None")
            except Exception as e:
                print(f"⚠️ Could not obtain block info ({e}) - using Genesis block defaults")
                block_info = {
                     'block_height': 0,
                     'block_hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
                }

            # Check for Genesis block to override meme
            override_meme = None
            if block_info['block_height'] == 0:
                 potential_meme = os.path.join("static", "memes", "0.jpg")
                 if os.path.exists(potential_meme):
                      print(f"🖼️ Genesis block detected: Forcing use of {potential_meme}")
                      override_meme = potential_meme
            
            # IMMEDIATE IMAGE GENERATION: Use cached wallet data for instant startup
            print(f"⚙️ [IMMEDIATE] Generating dashboard with cached data for block {block_info['block_height']}...")
            
            # Render both web and e-ink images using cached data (startup_mode=True)
            web_img, eink_img, meme_path, displayed_blocks = self.image_renderer.render_dual_images(
                block_info['block_height'], 
                block_info['block_hash'],
                mempool_api=self.mempool_api,
                startup_mode=True,  # This forces use of cached data only
                override_content_path=override_meme
            )
            
            # Track displayed info blocks
            self.displayed_info_blocks = displayed_blocks
            
            # Save both images for caching
            if web_img is not None:
                web_img.save(self.current_image_path)
                print(f"💾 Web image saved to {self.current_image_path}")
            if eink_img is not None:
                eink_img.save(self.current_eink_image_path)
                print(f"💾 E-ink image saved to {self.current_eink_image_path}")
            
            # Update cache state
            self.current_block_height = block_info['block_height']
            self.current_block_hash = block_info['block_hash']
            self.current_meme_path = meme_path  # Cache the selected meme
            self.image_is_current = True
            
            # Save persistent cache metadata
            self._save_cache_metadata()
            
            print("✅ Initial dashboard image generated and cached with existing data")
            
            # ASYNC WALLET REFRESH: Update wallet balances in background and regenerate if changed
            print("⚙️ [ASYNC] Starting background wallet balance refresh...")
            threading.Thread(
                target=self._async_wallet_refresh_and_regenerate,
                args=(block_info['block_height'], block_info['block_hash']),
                daemon=True
            ).start()
            print("✅ [ASYNC] Background wallet refresh started - will regenerate image if balance changed")
            
            # Display on e-Paper in background thread (don't block startup)
            if self.e_ink_enabled:
                print("🖥️ Starting e-Paper display in background...")
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                    daemon=True
                ).start()
            else:
                print("⚙️ Skipping e-Paper display (disabled in config)")
            
        except Exception as e:
            print(f"⚠️ Failed to generate initial image: {e}")
            print("   Image will be generated on first user request")
    
    def _async_wallet_refresh_and_regenerate(self, block_height: int, block_hash: str):
        """
        Async method to refresh wallet balances and regenerate image if balance changed.
        This provides optimal UX by serving cached data immediately, then updating if needed.
        """
        try:
            print(f"⚙️ [ASYNC-REFRESH] Starting wallet balance refresh for block {block_height}")
            
            # Get cached wallet data for comparison
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
            cached_balance = cached_wallet_data.get('total_btc', 0) if cached_wallet_data else 0
            
            print(f"💾 [ASYNC-REFRESH] Cached balance: {cached_balance:.8f} BTC")
            
            # Fetch fresh wallet balances (this might take time for XPUB derivation)
            print("⚙️ [ASYNC-REFRESH] Fetching fresh wallet balances...")
            fresh_wallet_data = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=False, current_block=block_height)
            
            if fresh_wallet_data and not fresh_wallet_data.get('error'):
                fresh_balance = fresh_wallet_data.get('total_btc', 0)
                print(f"💾 [ASYNC-REFRESH] Fresh balance: {fresh_balance:.8f} BTC")
                
                # Compare balances (use small epsilon for floating point comparison)
                balance_changed = abs(fresh_balance - cached_balance) > 0.00000001  # 1 satoshi precision
                
                if balance_changed:
                    print(f"⚙️ [ASYNC-REFRESH] Balance changed: {cached_balance:.8f} → {fresh_balance:.8f} BTC")
                    print("⚙️ [ASYNC-REFRESH] Updating cache first, then regenerating image...")
                    
                    # Update cache with fresh data BEFORE regenerating
                    self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                    
                    # Regenerate image (will use the just-updated cache via startup_mode=True)
                    self._generate_new_image(
                        block_height, 
                        block_hash, 
                        skip_epaper=False,  # Update e-Paper with new balance
                        use_new_meme=False  # Keep same meme to minimize change
                    )
                    
                    print("✅ [ASYNC-REFRESH] Image regenerated with updated wallet balance")
                    return  # Early return since cache was already updated
                else:
                    print("✅ [ASYNC-REFRESH] Balance unchanged - no image regeneration needed")
                
                # Update cache with fresh data (only if we didn't already update it above)
                # This updates timestamp and fiat values (which change with BTC price)
                # even though BTC balance is the same - ready for next block's image
                if not balance_changed:
                    print("💾 [ASYNC-REFRESH] Updating cache with fresh timestamp and current fiat values...")
                    self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                    print("✅ [ASYNC-REFRESH] Cache updated - fresh fiat values ready for next block")
                
            else:
                error_msg = fresh_wallet_data.get('error', 'Unknown error') if fresh_wallet_data else 'No data returned'
                print(f"⚠️ [ASYNC-REFRESH] Failed to fetch fresh wallet data: {error_msg}")
                print("💾 [ASYNC-REFRESH] Keeping existing cached image")
                
        except Exception as e:
            print(f"❌ [ASYNC-REFRESH] Error during async wallet refresh: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_async_wallet_cache_status(self, xpub: str, current_block_height: int) -> str:
        """
        Check the status of async wallet address cache for an extended key.
        
        Args:
            xpub: Extended public key (xpub/zpub)
            current_block_height: Current blockchain height
            
        Returns:
            "missing": No cache file exists
            "outdated": Cache exists but is outdated (>24 hours or different block context)
            "valid": Cache exists and is current
            "error": Could not determine status
        """
        try:
            # Check if async cache manager is available
            if not hasattr(self.image_renderer, 'wallet_api') or not hasattr(self.image_renderer.wallet_api, 'async_cache_manager'):
                return "missing"
            
            cache_manager = self.image_renderer.wallet_api.async_cache_manager
            cache_file_path = "cache/async_wallet_address_cache.secure.json"
            
            if not os.path.exists(cache_file_path):
                return "missing"
            
            # Try different cache key patterns
            test_counts = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200]
            cached_addresses, final_count = self._find_cached_addresses(cache_manager, xpub, test_counts)
            
            if not cached_addresses:
                return "missing"
            
            # Check cache age (consider outdated if >24 hours)
            cache_age_hours = (time.time() - os.path.getmtime(cache_file_path)) / 3600
            if cache_age_hours > 24:
                return "outdated"
            
            # Cache exists and is recent
            print(f"   💾 Found {final_count} cached addresses (age: {cache_age_hours:.1f}h)")
            return "valid"
            
        except Exception as e:
            print(f"⚠️ Error checking cache status for {xpub[:20]}...: {e}")
            return "error"
    
    def _find_cached_addresses(self, cache_manager, xpub: str, test_counts: list) -> tuple:
        """Helper method to find cached addresses with different count patterns."""
        # Try gap limit cache keys first
        for test_count in test_counts:
            cache_key = f"{xpub}:gap_limit:{test_count}"
            addresses = cache_manager.get_addresses(cache_key)
            if addresses:
                return addresses, test_count
        
        # Try regular derivation cache keys as fallback
        for test_count in [20, 40, 60, 80, 100]:
            cache_key = f"{xpub}:{test_count}"
            addresses = cache_manager.get_addresses(cache_key)
            if addresses:
                return addresses, test_count
        
        return None, 0
    
    def _warm_up_apis(self):
        """
        Warm up all API clients by fetching initial data to ensure they're ready.
        This prevents the first image from showing incomplete data.
        """
        # print("⚙️ Warming up API clients with initial data fetch...")
        
        # Warm up BTC price API
        try:
            price_data = self.image_renderer.fetch_btc_price()
            # Silently warm up - only log errors
            if not price_data or price_data.get("error"):
                print("⚠️ BTC price API warm-up returned no data (may work on retry)")
        except Exception as e:
            print(f"⚠️ BTC price API warm-up failed: {e}")
        
        # Warm up wallet balance API (if configured)
        # Get wallet entries from modern table format  
        wallet_entries = self.config.get("wallet_balance_addresses_with_comments", [])
        # Extract actual addresses from table format for validation
        wallet_addresses = []
        for entry in wallet_entries:
            if isinstance(entry, dict) and entry.get("address"):
                wallet_addresses.append(entry["address"].strip())
            elif isinstance(entry, str):
                wallet_addresses.append(entry.strip())
        
        if wallet_addresses:
            try:
                # Use cached data to warm up wallet API
                balance_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                # Silently warm up - only log errors
                if not balance_data or balance_data.get("error"):
                    print("⚠️ Wallet balance API warm-up returned no data (may work on retry)")
            except Exception as e:
                print(f"⚠️ Wallet balance API warm-up failed: {e}")
        
        # Warm up Bitaxe API (if configured) 
        bitaxe_ip = self.config.get("bitaxe_ip", "")
        if bitaxe_ip and bitaxe_ip != "192.168.1.1":
            try:
                bitaxe_data = self.image_renderer.fetch_bitaxe_stats()
                # Silently warm up - only log errors
                if not bitaxe_data or bitaxe_data.get("error"):
                    print("⚠️ Bitaxe API warm-up returned no data (may work on retry)")
            except Exception as e:
                print(f"⚠️ Bitaxe API warm-up failed: {e}")

    def _setup_instant_startup(self):
        """
        Setup instant startup mode:
        1. Load cached/default image immediately 
        2. Start heavy operations in background
        3. Update interface when ready
        """
        # print("🚀 Setting up instant startup mode...")
        
        # Check if we have a cached image to show immediately
        has_cached_image = (os.path.exists(self.current_image_path) and 
                           os.path.exists(self.current_eink_image_path))
        
        if has_cached_image:
            cache_age = (time.time() - os.path.getmtime(self.current_image_path)) / 60
            print(f"💾 Found cached image (age: {cache_age:.1f} minutes)")
            # Image metadata already loaded in _load_cache_metadata()
        else:
            print("💾 No cached image found - will create placeholder")
            self._create_placeholder_image()
        
        # Start background processing after a short delay to let the web server start
        background_delay = self.config.get("background_processing_delay", 2)
        # print(f"⚙️ Background processing will start in {background_delay} seconds...")
        
        threading.Timer(background_delay, self._run_background_startup).start()
        print("🌐 Website is now ready!")

    def _create_placeholder_image(self):
        """Create a simple placeholder image for instant startup."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Create a simple placeholder
            width, height = 800, 480
            img = Image.new('RGB', (width, height), color=self.get_color("background", web_quality=True))
            draw = ImageDraw.Draw(img)
            
            # Try to use the configured font, fallback to default
            try:
                font_path = self.config.get("font_bold", "static/fonts/Roboto-Bold.ttf")
                font = ImageFont.truetype(font_path, 48)
                medium_font = ImageFont.truetype(font_path, 32)
                small_font = ImageFont.truetype(font_path, 24)
            except:
                font = ImageFont.load_default()
                medium_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
            
            # Draw Bitcoin symbol at the top
            btc_symbol = "₿"
            bbox = draw.textbbox((0, 0), btc_symbol, font=font)
            symbol_width = bbox[2] - bbox[0]
            symbol_x = (width - symbol_width) // 2
            draw.text((symbol_x, 80), btc_symbol, fill='#f7931a', font=font)
            
            # Draw main title
            title = "Mempaper Dashboard"
            bbox = draw.textbbox((0, 0), title, font=medium_font)
            title_width = bbox[2] - bbox[0]
            title_x = (width - title_width) // 2
            title_y = 160
            draw.text((title_x, title_y), title, fill='black', font=medium_font)
            
            # Draw loading message
            loading_msg = self.translations.get("loading_bitcoin_data", "Loading Bitcoin data...")
            bbox = draw.textbbox((0, 0), loading_msg, font=small_font)
            loading_width = bbox[2] - bbox[0]
            loading_x = (width - loading_width) // 2
            loading_y = title_y + 60
            draw.text((loading_x, loading_y), loading_msg, fill='gray', font=small_font)
            
            # Draw progress indicator
            progress_msg = "● ● ● ●"
            bbox = draw.textbbox((0, 0), progress_msg, font=small_font)
            progress_width = bbox[2] - bbox[0]
            progress_x = (width - progress_width) // 2
            progress_y = loading_y + 40
            draw.text((progress_x, progress_y), progress_msg, fill='#f7931a', font=small_font)
            
            # Draw bottom message
            bottom_msg = "Website ready • Background processing in progress"
            bbox = draw.textbbox((0, 0), bottom_msg, font=small_font)
            bottom_width = bbox[2] - bbox[0]
            bottom_x = (width - bottom_width) // 2
            bottom_y = height - 80
            draw.text((bottom_x, bottom_y), bottom_msg, fill='#666666', font=small_font)
            
            # Save placeholder images
            img.save(self.current_image_path)
            img.save(self.current_eink_image_path)
            
            print("💾 Created informative placeholder images for instant startup")
            
            # Set basic cache state
            self.image_is_current = False
            self.current_block_height = None
            self.current_block_hash = None
            
        except Exception as e:
            print(f"⚠️ Failed to create placeholder image: {e}")

    def _run_background_startup(self):
        """Run heavy startup operations in background."""
        try:
            print("⚙️ Starting background initialization...")
            
            # Initialize WebSocket connection
            self._init_websocket()
            
            # Start WebSocket listener now that client is initialized
            if hasattr(self, 'websocket_client') and self.websocket_client:
                self.websocket_client.start_listener_thread()
            else:
                print("⚠️ WebSocket client not available - using block monitor for updates")
            
            # Warm up APIs
            # print("⚙️ Warming up API clients...")
            self._warm_up_apis()
            
            # Don't force image regeneration here - let block monitor handle new blocks naturally
            # The cached image is served immediately, and new blocks will trigger updates via WebSocket/monitor
            # print("💾 Background initialization complete - block monitor will handle updates")
            
            print("✅ Background initialization completed!")
            
        except Exception as e:
            print(f"⚠️ Background initialization failed: {e}")
            # Notify web clients of the error
            if hasattr(self, 'socketio') and self.socketio:
                self.socketio.emit('background_error', {
                    'message': f'Background processing failed: {e}',
                    'timestamp': time.time()
                })

    def _display_on_epaper_async(self, image_path, block_height=None, block_hash=None):
        """Display image on e-Paper using subprocess to avoid GPIO conflicts."""
        import threading
        import time
        import subprocess
        import sys
        import signal
        
        # Early check: Skip display if block is already superseded
        if block_height:
            current_block = getattr(self, 'current_block_height', 0) or 0
            if int(block_height) < int(current_block):
                print(f"⏭️ Skipping e-paper display for old block {block_height} (current: {current_block})")
                return
        
        # Cancel any older display processes when a newer block arrives
        if block_height:
            self._cancel_older_display_processes(int(block_height))
        
        def display_in_subprocess():
            process = None
            try:
                display_start = time.time()
                print(f"⚙️ Starting e-paper display for: {image_path} at {time.strftime('%H:%M:%S', time.localtime(display_start))}")
                if block_height:
                    print(f"   Block: {block_height} | Hash: {block_hash}")
                    # Always update display when block height differs from what's shown on e-ink
                    current_eink_height = getattr(self, 'last_eink_block_height', 0) or 0
                    if current_eink_height != int(block_height):
                        print(f"👁️ E-ink display needs update: showing {current_eink_height}, new block {block_height}")
                    else:
                        print(f"📋 E-ink display block height matches: {block_height}")
                
                # Use subprocess to avoid GPIO conflicts between threads
                script_path = os.path.join(os.path.dirname(__file__), "lib", "display_subprocess.py")
                
                # Start the subprocess
                process = subprocess.Popen([
                    sys.executable, script_path, image_path
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.path.dirname(__file__))
                
                # Register the process for potential cancellation
                if block_height:
                    with self.display_process_lock:
                        self.active_display_processes[int(block_height)] = process
                        print(f"⚙️ Registered display process for block {block_height} (PID: {process.pid})")
                
                # Wait for completion with timeout
                try:
                    stdout, stderr = process.communicate(timeout=120)
                    return_code = process.returncode
                finally:
                    # Unregister the process
                    if block_height:
                        with self.display_process_lock:
                            self.active_display_processes.pop(int(block_height), None)
                
                display_duration = time.time() - display_start
                
                # Check if process was intentionally cancelled (SIGTERM/SIGKILL)
                was_cancelled = return_code in [-15, -9, 15, 1]  # Unix SIGTERM/SIGKILL or Windows terminate
                
                if return_code == 0:
                    print(f"✅ E-paper display completed in {display_duration:.2f}s")
                    if stdout.strip():
                        for line in stdout.strip().split('\n'):
                            if line.strip():
                                print(f"   {line.strip()}")
                    
                    # Update tracking only on successful display and only if this block is newer
                    if block_height and block_hash:
                        current_height = getattr(self, 'last_eink_block_height', 0) or 0
                        if int(block_height) >= int(current_height):
                            self.last_eink_block_height = block_height
                            self.last_eink_block_hash = block_hash
                            print(f"💾 E-ink display tracking updated: Block {block_height}")
                        else:
                            print(f"📋 E-ink display tracking NOT updated: Block {block_height} is older than current {current_height}")
                    
                    # Emit success to WebSocket clients
                    if hasattr(self, 'socketio'):
                        self.socketio.emit('display_update', {
                            'status': 'success',
                            'message': f'Display updated in {display_duration:.1f}s',
                            'block_height': block_height,
                            'timestamp': time.time()
                        })
                elif was_cancelled:
                    # Don't log cancellation as error - it's expected behavior
                    pass
                else:
                    print(f"⚠️ E-paper display failed after {display_duration:.2f}s")
                    if stderr.strip():
                        print(f"   Error: {stderr.strip()}")
                    
                    # Emit failure to WebSocket clients
                    if hasattr(self, 'socketio'):
                        self.socketio.emit('display_update', {
                            'status': 'error', 
                            'message': f'Display error: {stderr}',
                            'timestamp': time.time()
                        })
                    
            except subprocess.TimeoutExpired:
                print(f"❌ E-paper display timed out after 120s")
                # Kill the process if it's still running
                if process and process.poll() is None:
                    process.kill()
                # Unregister the process
                if block_height:
                    with self.display_process_lock:
                        self.active_display_processes.pop(int(block_height), None)
                if hasattr(self, 'socketio'):
                    self.socketio.emit('display_update', {
                        'status': 'error',
                        'message': 'Display timeout',
                        'timestamp': time.time()
                    })
            except Exception as e:
                # Check if this was a cancellation (process terminated externally)
                if process and process.returncode in [-15, -9]:  # SIGTERM or SIGKILL
                    print(f"🛑 E-paper display for block {block_height} was cancelled (newer block arrived)")
                    return  # Don't emit error for intentional cancellation
                
                print(f"❌ E-paper display error: {e}")
                # Unregister the process
                if block_height:
                    with self.display_process_lock:
                        self.active_display_processes.pop(int(block_height), None)
                if hasattr(self, 'socketio'):
                    self.socketio.emit('display_update', {
                        'status': 'error',
                        'message': f'Display error: {str(e)}',
                        'timestamp': time.time()
                    })
        
        try:
            # Run display in single background thread to avoid conflicts
            display_thread = threading.Thread(target=display_in_subprocess, daemon=True)
            display_thread.start()
            
        except Exception as e:
            print(f"❌ Error starting e-paper display: {e}")
            if hasattr(self, 'socketio'):
                self.socketio.emit('display_update', {
                    'status': 'error',
                    'message': f'Thread error: {str(e)}',
                    'timestamp': time.time()
                })
    
    def _cancel_older_display_processes(self, new_block_height):
        """Cancel any running display processes for older blocks."""
        import signal
        import subprocess
        
        with self.display_process_lock:
            processes_to_cancel = []
            for block_height, process in list(self.active_display_processes.items()):
                if block_height < new_block_height:
                    processes_to_cancel.append((block_height, process))
            
            for block_height, process in processes_to_cancel:
                try:
                    if process.poll() is None:  # Process is still running
                        print(f"🛑 Cancelling older display process for block {block_height} (PID: {process.pid})")
                        
                        # Try graceful termination first
                        if os.name == 'nt':  # Windows
                            process.terminate()
                        else:  # Unix-like systems
                            process.send_signal(signal.SIGTERM)
                        
                        # Wait a short time for graceful shutdown
                        try:
                            process.wait(timeout=2)
                            print(f"✅ Gracefully terminated display process for block {block_height}")
                        except subprocess.TimeoutExpired:
                            # Force kill if graceful termination fails
                            process.kill()
                            print(f"⚙️ Force killed display process for block {block_height}")
                    
                    # Remove from tracking
                    self.active_display_processes.pop(block_height, None)
                    
                except Exception as e:
                    print(f"⚠️ Error cancelling display process for block {block_height}: {e}")
                    # Still remove from tracking even if cancellation failed
                    self.active_display_processes.pop(block_height, None)
    
    def _extract_wallet_addresses_from_config(self, config):
        """
        Extract all wallet addresses from configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Set of addresses and XPUB keys
        """
        wallet_addresses = set()
        
        # Get wallet balance addresses from modern table format (primary and only source)
        wallet_table = config.get("wallet_balance_addresses_with_comments", [])
        for entry in wallet_table:
            if isinstance(entry, dict):
                address = entry.get("address", "")
                if address:
                    wallet_addresses.add(address.strip())
            elif isinstance(entry, str):
                wallet_addresses.add(entry.strip())
        
        return wallet_addresses
    
    def _cleanup_removed_wallet_caches(self, old_config, new_config):
        """
        Clean up cache entries for wallet addresses that were removed from configuration.
        
        Args:
            old_config: Previous configuration
            new_config: New configuration
        """
        try:
            # Extract wallet addresses from both configs
            old_addresses = self._extract_wallet_addresses_from_config(old_config)
            new_addresses = self._extract_wallet_addresses_from_config(new_config)
            
            # Find addresses that were removed
            removed_addresses = old_addresses - new_addresses
            
            if not removed_addresses:
                # print("🧹 No removed wallet addresses - cache cleanup not needed")
                return
            
            print(f"🧹 Cleaning up cache for {len(removed_addresses)} removed wallet address(es)")
            
            # Initialize cache managers for comprehensive cleanup
            async_cache_cleared = False
            unified_cache_cleared = False
            
            # 1. Clear async address cache manager
            try:
                from managers.config_observer import AsyncAddressCacheManager
                async_cache = AsyncAddressCacheManager()
                
                # Clear cache entries for each removed address
                for address in removed_addresses:
                    print(f"   🗑️ Cleaning cache for: {address[:20]}...")
                    
                    # Clear patterns for the removed address/XPUB (async cache)
                    if hasattr(async_cache, 'invalidate_cache'):
                        # Use the actual method name from AsyncAddressCacheManager
                        async_cache.invalidate_cache(address[:20])
                        print(f"      ✅ Cleared async cache patterns for: {address[:20]}...")
                        async_cache_cleared = True
                    else:
                        print(f"      ⚠️ Async cache manager does not support pattern clearing")
                        
            except ImportError:
                print("   ⚠️ Async cache manager not available - skipping async cache cleanup")
            except Exception as e:
                print(f"   ⚠️ Error during async cache cleanup: {e}")
            
            # 2. Clear unified secure cache for XPUBs/ZPUBs and addresses
            try:
                from managers.unified_secure_cache import get_unified_cache
                unified_cache = get_unified_cache()
                
                for address in removed_addresses:
                    # Clear optimized balance cache for XPUBs/ZPUBs
                    if address.startswith(('xpub', 'zpub')) and hasattr(self, 'wallet_api'):
                        try:
                            if hasattr(self.wallet_api, 'unified_cache'):
                                # Clear optimized balance cache
                                optimized_cache = self.wallet_api.unified_cache.get_cache("optimized_balance_cache")
                                if optimized_cache:
                                    cache_key = self.wallet_api._get_optimized_balance_cache_key(address)
                                    if cache_key in optimized_cache:
                                        del optimized_cache[cache_key]
                                        self.wallet_api.unified_cache.save_cache("optimized_balance_cache", optimized_cache)
                                        print(f"      ✅ Cleared optimized balance cache for: {address[:20]}...")
                                        unified_cache_cleared = True
                                
                                # Clear address derivation cache for XPUBs/ZPUBs
                                address_cache = self.wallet_api.unified_cache.get_cache("address_derivation_cache")
                                if address_cache:
                                    keys_to_remove = [key for key in address_cache.keys() if address[:20] in key]
                                    for key in keys_to_remove:
                                        del address_cache[key]
                                        print(f"      ✅ Cleared address derivation cache entry: {key[:50]}...")
                                        unified_cache_cleared = True
                                    if keys_to_remove:
                                        self.wallet_api.unified_cache.save_cache("address_derivation_cache", address_cache)
                                
                                # Clear general wallet cache entries
                                wallet_cache = self.wallet_api.unified_cache.get_cache("wallet_cache")
                                if wallet_cache:
                                    keys_to_remove = [key for key in wallet_cache.keys() if address[:20] in key]
                                    for key in keys_to_remove:
                                        del wallet_cache[key]
                                        print(f"      ✅ Cleared wallet cache entry: {key[:50]}...")
                                        unified_cache_cleared = True
                                    if keys_to_remove:
                                        self.wallet_api.unified_cache.save_cache("wallet_cache", wallet_cache)
                                        
                        except Exception as e:
                            print(f"      ⚠️ Could not clear unified cache for XPUB/ZPUB: {e}")
                    
                    # For regular addresses, clear any cache entries containing the address
                    else:
                        try:
                            # Check all cache types for entries containing this address
                            cache_types = ["address_derivation_cache", "wallet_cache", "balance_cache"]
                            for cache_type in cache_types:
                                try:
                                    cache_data = unified_cache.get_cache(cache_type)
                                    if cache_data:
                                        keys_to_remove = [key for key in cache_data.keys() if address in key]
                                        for key in keys_to_remove:
                                            del cache_data[key]
                                            print(f"      ✅ Cleared {cache_type} entry: {key[:50]}...")
                                            unified_cache_cleared = True
                                        if keys_to_remove:
                                            unified_cache.save_cache(cache_type, cache_data)
                                except Exception as cache_e:
                                    print(f"      ⚠️ Could not clear {cache_type}: {cache_e}")
                                    
                        except Exception as e:
                            print(f"      ⚠️ Could not clear unified cache for address: {e}")
                
                # 3. Force wallet API to refresh derived addresses for any remaining XPUBs/ZPUBs
                try:
                    if hasattr(self, 'wallet_api') and removed_addresses:
                        # Check if any of the removed addresses were XPUBs/ZPUBs
                        removed_xpubs = [addr for addr in removed_addresses if addr.startswith(('xpub', 'zpub'))]
                        if removed_xpubs:
                            print(f"   ⚙️ Triggering wallet API refresh for remaining addresses...")
                            # This will force re-derivation of addresses for remaining XPUBs
                            if hasattr(self.wallet_api, '_reinitialize_cache'):
                                self.wallet_api._reinitialize_cache()
                                unified_cache_cleared = True
                except Exception as e:
                    print(f"   ⚠️ Could not trigger wallet API refresh: {e}")
                
                # Report cleanup results
                cleanup_status = []
                if async_cache_cleared:
                    cleanup_status.append("async cache")
                if unified_cache_cleared:
                    cleanup_status.append("unified cache")
                
                if cleanup_status:
                    print(f"✅ Cache cleanup completed for removed addresses ({', '.join(cleanup_status)} cleared)")
                else:
                    print(f"⚠️ No cache entries found for removed addresses (cache may already be clean)")
                
            except ImportError:
                print("   ⚠️ Unified cache not available - skipping unified cache cleanup")
            except Exception as e:
                print(f"   ⚠️ Error during unified cache cleanup: {e}")
                
        except Exception as e:
            print(f"❌ Failed to cleanup removed wallet caches: {e}")
    
    def _reinitialize_after_config_change(self, old_config=None):
        """Reinitialize components after configuration changes."""
        # Update translations
        lang = self.config.get("language", "en")
        self.translations = translations.get(lang, translations["en"])
        
        # Update e-ink display status
        self.e_ink_enabled = self.config.get("e-ink-display-connected", True)
        
        # Reinitialize image renderer with new config
        self.image_renderer = ImageRenderer(self.config, self.translations)
        
        # Reinitialize API clients
        self._init_api_clients()
        
        # Only invalidate cached image if the config actually affects image generation
        # Language changes, orientation changes, etc. need image regeneration
        # But other changes like API settings don't require image invalidation
        image_affecting_changes = False
        if old_config and self.config:
            image_affecting_settings = [
                'language', 'web_orientation', 'eink_orientation', 'prioritize_large_scaled_meme',
                'display_width', 'display_height', 'show_btc_price_block',
                'btc_price_currency', 'show_bitaxe_block', 'show_wallet_balances_block',
                'wallet_balance_unit', 'wallet_balance_currency', 'color_mode_dark',
                'moscow_time_unit'
            ]
            
            for setting in image_affecting_settings:
                if old_config.get(setting) != self.config.get(setting):
                    image_affecting_changes = True
                    print(f"⚙️ Image-affecting setting changed: {setting}")
                    break
        
        if image_affecting_changes:
            self.image_is_current = False
            print("⚙️ Image cache invalidated due to configuration change")
        else:
            print("✅ Configuration reloaded without affecting image cache")
        
        # Note: Image regeneration is handled by _on_config_change() callback
        # to avoid duplicate generation processes
        
        print("✅ Components reinitialized after configuration change")
    
    def _on_config_file_changed(self, new_config=None):
        """Handle configuration file changes (external edits)."""
        print("📝 Configuration file changed externally - reloading...")
        
        # Store old config for comparison
        old_config = dict(self.config) if hasattr(self, 'config') else None
        
        # Update local config reference
        self.config = self.config_manager.get_current_config()
        
        # Update auth manager config
        self.auth_manager.config = self.config
        
        # Clean up cache for removed wallet addresses before reinitializing
        if old_config:
            self._cleanup_removed_wallet_caches(old_config, self.config)
        
        # Reinitialize components
        self._reinitialize_after_config_change(old_config)
        
        # Notify connected web clients of config change
        try:
            if self.socketio:
                self.socketio.emit('config_reloaded', {
                    'message': 'Configuration reloaded from file',
                    'timestamp': int(time.time() * 1000)
                })
                print("📡 Web clients notified of configuration reload")
            else:
                print("⚙️ SocketIO disabled - skipping web client notification")
        except Exception as e:
            print(f"⚠️ Failed to notify web clients: {e}")
    
    def _background_image_generation(self):
        """Generate image in background thread."""
        # Use lock to prevent concurrent generation
        if not self.generation_lock.acquire(blocking=False):
            print("⚙️ Image generation already in progress, skipping")
            return
            
        try:
            print("⚙️ Starting background image generation...")
            block_info = self.mempool_api.get_current_block_info()
            
            # Check if we already have this block
            if (self.current_block_height == block_info['block_height'] and 
                self.current_block_hash == block_info['block_hash'] and 
                self.image_is_current):
                print(f"✅ Image already current for block {block_info['block_height']}, skipping generation")
                return
            
            print(f"⚙️ Need to generate: cached_height={self.current_block_height}, current_height={block_info['block_height']}, is_current={self.image_is_current}")
            
            # Use new meme if block height changed, keep existing if same block
            use_new_meme = (self.current_block_height != block_info['block_height'])
            if use_new_meme:
                print(f"🎭 Block changed ({self.current_block_height} → {block_info['block_height']}) - will select new meme")
            else:
                print(f"🎭 Same block ({block_info['block_height']}) - will keep existing meme if available")
                
            self._generate_new_image(
                block_info['block_height'],
                block_info['block_hash'],
                skip_epaper=False,  # Allow e-Paper update in background
                use_new_meme=use_new_meme
            )
            print("✅ Background image generation completed")
            
            # Only emit to web clients if this is a new block
            with self.app.app_context():
                try:
                    with open(self.current_image_path, 'rb') as f:
                        image_data = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                        # Validate image data before sending
                        if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                            self.socketio.emit('new_image', {'image': image_data})
                            print("📡 Fresh image sent to web clients")
                        else:
                            print("⚠️ Invalid image data generated, not sending to clients")
                except Exception as e:
                    print(f"⚠️ Failed to read generated image: {e}")
                    
        except Exception as e:
            print(f"❌ Background image generation failed: {e}")
        finally:
            self.generation_lock.release()
    
    def _generate_placeholder_image(self):
        """Generate a simple placeholder image quickly."""
        from PIL import Image, ImageDraw, ImageFont
        
        # Use current orientation settings
        if self.config.get("web_orientation", "vertical") == "horizontal":
            width, height = 800, 480
        else:
            width, height = 480, 800
            
        # Create simple placeholder
        img = Image.new('RGB', (width, height), color='#667eea')
        draw = ImageDraw.Draw(img)
        
        # Simple text
        try:
            font = ImageFont.truetype(self.config.get("font_bold", "static/fonts/Roboto-Bold.ttf"), 48)
        except:
            font = ImageFont.load_default()
            
        text = "Loading Dashboard..."
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        draw.text((x, y), text, fill='white', font=font)
        
        return img
    
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
        """Save current cache state to persistent file."""
        try:
            metadata = {
                'block_height': self.current_block_height,
                'block_hash': self.current_block_hash,
                'timestamp': time.time(),
                'image_path': self.current_image_path,
                'eink_image_path': self.current_eink_image_path,
                'current_meme_path': getattr(self, 'current_meme_path', None),  # Add meme caching
                'last_eink_block_height': self.last_eink_block_height,  # Persist e-ink display state
                'last_eink_block_hash': self.last_eink_block_hash,  # Persist e-ink display hash
                'displayed_info_blocks': getattr(self, 'displayed_info_blocks', []),  # Track which blocks are shown
                'displayed_bitaxe_data': getattr(self, 'displayed_bitaxe_data', None)  # Cache Bitaxe state
            }
            
            with open(self.cache_metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            print(f"💾 Cache metadata saved for block {self.current_block_height}")
        except Exception as e:
            print(f"⚠️ Error saving cache metadata: {e}")
    
    def _start_precache_updater(self):
        """Start background thread that keeps slow-changing data fresh."""
        def update_precache():
            """Background worker to refresh price and bitaxe data between blocks."""
            # Initial pre-fill on startup
            # print("🚀 Pre-cache updater started - warming cache...")
            self._update_precache_data()
            
            # Get update interval from config (default 5 minutes to reduce RPi load)
            update_interval = self.config.get("precache_update_interval_seconds", 300)
            
            while True:
                try:
                    # Update every N seconds (default 5 minutes)
                    time.sleep(update_interval)
                    self._update_precache_data()
                except Exception as e:
                    print(f"⚠️ Pre-cache update error: {e}")
                    time.sleep(update_interval)  # Continue despite errors
        
        threading.Thread(target=update_precache, daemon=True, name="PreCacheUpdater").start()
        # print("✅ Pre-cache background updater started")
    
    def _update_precache_data(self):
        """Update pre-cached data (price, bitaxe) in background."""
        with self._precache['lock']:
            now = time.time()
            update_interval = self.config.get("precache_update_interval_seconds", 300)
            
            # Update price data if stale
            if now - self._precache['price_last_update'] > update_interval:
                try:
                    price_data = self.image_renderer.fetch_btc_price()
                    if price_data:
                        self._precache['price_data'] = price_data
                        self._precache['price_last_update'] = now
                        
                        # Only log if price actually changed
                        currency = price_data.get('currency', 'USD')
                        price = price_data.get('price_in_selected_currency', 0)
                        if price != self._precache['last_price_value']:
                            print(f"💰 Pre-cache updated: Price {price:,.0f} {currency}")
                            self._precache['last_price_value'] = price
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache price: {e}")
            
            # Update Bitaxe data if enabled and stale
            if self.config.get("bitaxe_enabled", False) and now - self._precache['bitaxe_last_update'] > update_interval:
                try:
                    bitaxe_data = self.image_renderer.fetch_bitaxe_info()
                    if bitaxe_data:
                        self._precache['bitaxe_data'] = bitaxe_data
                        self._precache['bitaxe_last_update'] = now
                        
                        # Only log if Bitaxe data actually changed
                        blocks = bitaxe_data.get('valid_blocks', 0)
                        difficulty = bitaxe_data.get('best_difficulty', 0)
                        if blocks != self._precache['last_bitaxe_blocks']:
                            print(f"⛏️ Pre-cache updated: Bitaxe {blocks} blocks, diff {difficulty}")
                            self._precache['last_bitaxe_blocks'] = blocks
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache Bitaxe: {e}")
    
    def _get_precached_data(self):
        """Get pre-cached data with fallback to fresh fetch if needed."""
        with self._precache['lock']:
            now = time.time()
            
            # Use cached price if fresh (<120s old), otherwise fetch new
            if self._precache['price_data'] and (now - self._precache['price_last_update'] < 120):
                price_data = self._precache['price_data']
                print("⚡ Using pre-cached price data (fast!)")
            else:
                print("🔄 Pre-cache stale, fetching fresh price...")
                price_data = self.image_renderer.fetch_btc_price()
                self._precache['price_data'] = price_data
                self._precache['price_last_update'] = now
            
            # Use cached Bitaxe if fresh (<120s old), otherwise fetch new
            if self.config.get("bitaxe_enabled", False):
                if self._precache['bitaxe_data'] and (now - self._precache['bitaxe_last_update'] < 120):
                    bitaxe_data = self._precache['bitaxe_data']
                    print("⚡ Using pre-cached Bitaxe data (fast!)")
                else:
                    print("🔄 Pre-cache stale, fetching fresh Bitaxe...")
                    bitaxe_data = self.image_renderer.fetch_bitaxe_info()
                    self._precache['bitaxe_data'] = bitaxe_data
                    self._precache['bitaxe_last_update'] = now
            else:
                bitaxe_data = None
            
            return price_data, bitaxe_data
    
    def _on_config_change(self, new_config):
        """
        Handle configuration changes that affect image rendering.
        Triggers immediate image regeneration with cached meme for visual settings.
        """
        print("🔧 Configuration change detected, checking if image refresh needed...")
        
        # Define settings that affect image rendering and require immediate refresh
        image_affecting_settings = {
            # Hardware settings
            'web_orientation', 'eink_orientation', 'display_width', 'display_height', 'e-ink-display-connected',
            'omni_device_name', 'block_height_area',
            
            # Design settings (colors, fonts)
            'font_regular', 'font_bold', 'color_mode_dark',
            
            # Price/time display settings
            'moscow_time_unit',
            
            # Holiday settings
            'hide_holiday_if_large_meme',
            
            # General settings that affect display
            'language',
            
            # Mempool fee settings
            'fee_parameter'
        }
        
        # Compare old and new config for image-affecting changes
        old_config = self.config
        config_changed = False
        changed_settings = []
        
        for setting in image_affecting_settings:
            old_value = old_config.get(setting)
            new_value = new_config.get(setting)
            if old_value != new_value:
                config_changed = True
                changed_settings.append(f"{setting}: {old_value} → {new_value}")
        
        if config_changed:
            print(f"⚙️ Image-affecting settings changed: {', '.join(changed_settings)}")
            print("⚙️ Triggering immediate image refresh with cached meme...")
            
            # Update config references
            self.config = new_config
            
            # Update translations if language changed
            if 'language' in [s.split(':')[0] for s in changed_settings]:
                lang = new_config.get("language", "en")
                self.translations = translations.get(lang, translations["en"])
                print(f"🌐 Updated translations to language: {lang}")
            
            # Recreate image renderer with new config
            self.image_renderer = ImageRenderer(self.config, self.translations)
            
            # Check if we have a current image and cached meme to regenerate with
            if (self.image_is_current and 
                self.current_block_height and 
                self.current_block_hash and 
                hasattr(self, 'current_meme_path') and 
                self.current_meme_path):
                
                # Generate new images with cached meme
                self._regenerate_image_with_cached_meme()
            else:
                print("💾 No cached image state available, will regenerate on next update")
        else:
            # Update config reference even if no image refresh needed
            self.config = new_config
            print("📝 Configuration updated (no image refresh required)")
        
        # Check for block reward address changes (independent of image refresh)
        self._check_block_reward_address_changes(old_config, new_config)
    
    def _check_block_reward_address_changes(self, old_config, new_config):
        """Check if block reward addresses have changed and update cache accordingly."""
        try:
            # Get old addresses from table
            old_table = set()
            for entry in old_config.get("block_reward_addresses_table", []):
                if isinstance(entry, dict) and entry.get("address"):
                    old_table.add(entry["address"])
            old_addresses = old_table
            
            # Get new addresses from table
            new_table = set()
            for entry in new_config.get("block_reward_addresses_table", []):
                if isinstance(entry, dict) and entry.get("address"):
                    new_table.add(entry["address"])
            new_addresses = new_table
            
            # Check for changes
            if old_addresses != new_addresses:
                added_addresses = new_addresses - old_addresses
                removed_addresses = old_addresses - new_addresses
                
                if added_addresses:
                    print(f"➕ New block reward addresses detected: {', '.join(added_addresses)}")
                
                if removed_addresses:
                    print(f"➖ Removed block reward addresses: {', '.join(removed_addresses)}")
                
                # Update block monitor and cache
                if hasattr(self, 'block_monitor') and self.block_monitor:
                    self.block_monitor._update_monitored_addresses()
                    print("✅ Block reward cache updated with new address list")
                
        except Exception as e:
            print(f"⚠️ Error checking block reward address changes: {e}")
    
    def _regenerate_image_with_cached_meme(self):
        """Regenerate images using cached meme when configuration changes."""
        try:
            with self.generation_lock:
                print(f"⚙️ Regenerating images with cached meme for block {self.current_block_height}")
                
                # Verify cached meme still exists
                if not os.path.exists(self.current_meme_path):
                    print(f"⚠️ Cached meme {self.current_meme_path} no longer exists, will select new one")
                    self.current_meme_path = None
                    # Fall back to normal generation
                    self._generate_new_image(self.current_block_height, self.current_block_hash, skip_epaper=False, use_new_meme=False)
                    return
                
                # Generate images with the cached meme
                web_img, eink_img, meme_path = self.image_renderer.render_dual_images_with_cached_meme(
                    self.current_block_height,
                    self.current_block_hash,
                    self.current_meme_path,
                    mempool_api=self.mempool_api
                )
                
                # Save both images for caching
                if web_img is not None:
                    web_img.save(self.current_image_path)
                    print(f"💾 Regenerated web image saved to {self.current_image_path}")
                if eink_img is not None:
                    eink_img.save(self.current_eink_image_path)
                    print(f"💾 Regenerated e-ink image saved to {self.current_eink_image_path}")
                
                # Update cache metadata
                self._save_cache_metadata()

                # Display on e-Paper if enabled
                if self.e_ink_enabled:
                    print("🖥️ Refreshing e-Paper display with updated image...")
                    # Start e-Paper display in background thread
                    threading.Thread(
                        target=self._display_on_epaper_async,
                        args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                        daemon=True
                    ).start()
                
                # Emit update to connected web clients
                self.socketio.emit('image_updated', {
                    'message': 'Image refreshed due to configuration change',
                    'block_height': self.current_block_height,
                    'timestamp': time.time()
                })
                
                print("✅ Image regeneration completed successfully")
                
                shared_data = {
                    "holiday_info": None,  # or fetch as needed
                    "configured_fee": None,  # or fetch as needed
                    "api_block_height": None,  # or fetch as needed
                    "meme_path": self.current_meme_path,
                    "btc_price_data": None,  # or fetch as needed
                    "bitaxe_data": None,     # or fetch as needed
                    "wallet_data": None,     # or fetch as needed
                    "info_blocks": [],       # or build as needed
                }
                # Now, start async wallet refresh in background using threading (no multiprocessing issues)
                # Skip if wallet monitoring is disabled
                if self.config.get("show_wallet_balances_block", True):
                    print("⚙️ Starting async wallet refresh in background...")
                    try:
                        # Use a simple approach that avoids multiprocessing issues
                        # This runs in a thread but the actual work happens in subprocess via image_renderer
                        threading.Thread(
                            target=self._safe_wallet_refresh_thread,
                            args=(self.current_block_height, self.current_block_hash, False),
                            daemon=True
                        ).start()
                        print("✅ Wallet refresh thread started")
                    except Exception as proc_e:
                        print(f"❌ Failed to start wallet refresh thread: {proc_e}")
                # Wallet monitoring disabled - skip refresh silently

        except Exception as e:
            print(f"❌ Error regenerating image with cached meme: {e}")
            # Fall back to normal generation
            self._generate_new_image(self.current_block_height, self.current_block_hash, skip_epaper=False, use_new_meme=False)
    
    def async_wallet_refresh(self, block_height, block_hash, startup_mode=False):
        """Fetch fresh wallet data and regenerate image if balance changed."""
        print(f"🚀 [WALLET] Starting wallet refresh for block {block_height}...")
        try:
            # Fetch fresh wallet data
            print("👁️ [WALLET] Fetching fresh wallet data...")
            fresh_wallet_data = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=block_height)
            
            # Log wallet data with privacy masking
            # masked_fresh_data = MempaperApp.mask_wallet_data_for_logging(fresh_wallet_data)
            # print(f"✅ [WALLET] Fresh wallet data: {masked_fresh_data}")
            
            # Get cached wallet data
            print("📖 [WALLET] Loading cached wallet data...")
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
            
            # Log cached data with privacy masking
            # masked_cached_data = MempaperApp.mask_wallet_data_for_logging(cached_wallet_data)
            # print(f"📋 [WALLET] Cached wallet data: {masked_cached_data}")
            
            # Ensure both are dicts before accessing .get()
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            
            # Compare BTC balance
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            wallet_changed = fresh_btc != cached_btc
            
            # Compare Bitaxe data if enabled and displayed
            bitaxe_changed = False
            if self.config.get("bitaxe_enabled", False) and 'bitaxe' in self.displayed_info_blocks:
                fresh_bitaxe = self.image_renderer.fetch_bitaxe_info()
                cached_bitaxe = self.displayed_bitaxe_data or {}
                
                fresh_blocks = fresh_bitaxe.get('valid_blocks', 0) if fresh_bitaxe else 0
                cached_blocks = cached_bitaxe.get('valid_blocks', 0)
                fresh_difficulty = fresh_bitaxe.get('best_difficulty', 0) if fresh_bitaxe else 0
                cached_difficulty = cached_bitaxe.get('best_difficulty', 0)
                
                if fresh_blocks != cached_blocks or fresh_difficulty != cached_difficulty:
                    bitaxe_changed = True
                    print(f"⚖️ [BITAXE] Data changed: Blocks {cached_blocks}→{fresh_blocks}, Difficulty {cached_difficulty}→{fresh_difficulty}")
                    # Update displayed Bitaxe cache
                    self.displayed_bitaxe_data = fresh_bitaxe
            
            # Determine if regeneration is needed based on what's displayed
            needs_regeneration = False
            regeneration_reason = []
            
            if wallet_changed and 'wallet' in self.displayed_info_blocks:
                needs_regeneration = True
                regeneration_reason.append(f"wallet balance {cached_btc:.8f}→{fresh_btc:.8f} BTC")
                print(f"⚖️ [WALLET] Balance changed and wallet block is displayed")
            elif wallet_changed:
                print(f"ℹ️ [WALLET] Balance changed ({cached_btc:.8f}→{fresh_btc:.8f} BTC) but wallet block not displayed, skipping regeneration")
            
            if bitaxe_changed:
                needs_regeneration = True
                regeneration_reason.append("Bitaxe data")
                print(f"⚖️ [BITAXE] Data changed and Bitaxe block is displayed")
            
            # Update caches regardless of regeneration
            self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
            
            if needs_regeneration:
                reason_str = ", ".join(regeneration_reason)
                print(f"🔄 [REFRESH] Regenerating image due to: {reason_str}")
                print("🎭 [REFRESH] Preserving current meme and info block selection")
                
                # Emit WebSocket event for balance update
                if hasattr(self, 'socketio') and self.socketio:
                    self.socketio.emit('wallet_balance_updated', fresh_wallet_data)
                    print("📡 [WALLET] Balance update broadcasted via WebSocket")
                
                # Get pre-cached data for fast rendering
                precached_price, precached_bitaxe = self._get_precached_data()
                
                # Regenerate with SAME meme and info blocks (preserve_layout=True)
                web_img, eink_img, content_path, displayed_blocks = self.image_renderer.render_dual_images(
                    block_height, block_hash,
                    mempool_api=self.mempool_api,
                    startup_mode=startup_mode,
                    override_content_path=self.current_meme_path,  # Keep same meme
                    preserve_info_blocks=self.displayed_info_blocks,  # Keep same info blocks
                    precached_price=precached_price,
                    precached_bitaxe=precached_bitaxe
                )
                # Update displayed blocks tracking
                self.displayed_info_blocks = displayed_blocks
                # Save images
                if web_img is not None:
                    web_img.save(self.current_image_path)
                if eink_img is not None:
                    eink_img.save(self.current_eink_image_path)
                print("✅ [REFRESH] Image regenerated with updated data")
            else:
                print("✅ [REFRESH] No visible data changes, keeping current image")
                
            # Update cache metadata
            self._save_cache_metadata()
            print("✅ [WALLET] Wallet refresh completed successfully")
            
        except Exception as e:
            print(f"❌ [WALLET] Error during wallet refresh: {e}")
            import traceback
            traceback.print_exc()

    def _safe_wallet_refresh_thread(self, block_height, block_hash, startup_mode=False):
        """Safe wallet refresh that runs in thread but uses subprocess for actual work."""
        try:
            # print(f"🚀 [THREAD] Starting safe wallet refresh for block {block_height}...")
            
            # Call the existing process-based refresh logic directly
            self._run_wallet_refresh_process(block_height, block_hash, startup_mode)
            
        except Exception as e:
            print(f"❌ [THREAD] Error in safe wallet refresh: {e}")
            import traceback
            traceback.print_exc()

    def _run_wallet_refresh_process(self, block_height, block_hash, startup_mode=False):
        """Wrapper to run wallet refresh in separate process to avoid gunicorn timeouts."""
        try:
            # Re-initialize components in the new process
            from managers.config_manager import ConfigManager
            from lib.image_renderer import ImageRenderer
            from utils.translations import translations
            
            # Load config and initialize image renderer with wallet API
            config_manager = ConfigManager()
            config = config_manager.get_current_config()
            image_renderer = ImageRenderer(config, translations)
            
            print(f"⚙️ [PROCESS] Wallet refresh process started for block {block_height}")
            
            # Fetch fresh wallet data
            print("👁️ [PROCESS] Fetching fresh wallet data...")
            fresh_wallet_data = image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=block_height)
            
            # Log wallet data with privacy masking
            # masked_fresh_data = MempaperApp.mask_wallet_data_for_logging(fresh_wallet_data)
            # print(f"✅ [PROCESS] Fresh wallet data: {masked_fresh_data}")
            
            # Get cached wallet data
            # print("📖 [PROCESS] Loading cached wallet data...")
            cached_wallet_data = image_renderer.wallet_api.get_cached_wallet_balances()
            
            # Log cached data with privacy masking  
            # masked_cached_data = MempaperApp.mask_wallet_data_for_logging(cached_wallet_data)
            # print(f"📋 [PROCESS] Cached wallet data: {masked_cached_data}")
            
            # Ensure both are dicts before accessing .get()
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            
            # Compare only BTC/sats balance
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            
            # print(f"⚖️ [PROCESS] Balance comparison: Fresh={fresh_btc} BTC, Cached={cached_btc} BTC")

            if fresh_btc != cached_btc:
                print("⚙️ [PROCESS] Wallet data changed, updating cache...")
                image_renderer.wallet_api.update_cache(fresh_wallet_data)
                print("✅ [PROCESS] Cache updated - image will be refreshed on next request")
            else:
                print("✅ [PROCESS] No wallet balance change detected")
                # Still update the cache to keep timestamp fresh
                image_renderer.wallet_api.update_cache(fresh_wallet_data)
                
            print("✅ [PROCESS] Wallet refresh process completed successfully")
            
        except Exception as e:
            print(f"❌ [PROCESS] Error during wallet refresh process: {e}")
            import traceback
            traceback.print_exc()

    def _generate_new_image(self, block_height: int, block_hash: str, skip_epaper: bool = False, use_new_meme: bool = True):
        """Generate a new dashboard image and cache it."""
        print(f"⚙️ Generating new dashboard image for block {block_height} with CACHED wallet data...")
        
        # 🚀 Get pre-cached data for instant image generation
        precached_price, precached_bitaxe = self._get_precached_data()
        
        # Decide whether to use cached meme or pick a new one
        if use_new_meme or not hasattr(self, 'current_meme_path') or not self.current_meme_path or not os.path.exists(self.current_meme_path):
            print("⚙️ Selecting new random meme for this block...")
            web_img, eink_img, content_path, displayed_blocks = self.image_renderer.render_dual_images(
                block_height,
                block_hash,
                mempool_api=self.mempool_api,
                startup_mode=True,  # Use cached wallet data for instant response
                precached_price=precached_price,  # Use pre-cached price
                precached_bitaxe=precached_bitaxe  # Use pre-cached Bitaxe
            )
            # Cache the selected meme and displayed blocks for this block
            self.current_meme_path = content_path
            self.displayed_info_blocks = displayed_blocks
            # Cache current Bitaxe state if displayed
            if 'bitaxe' in displayed_blocks and precached_bitaxe:
                self.displayed_bitaxe_data = precached_bitaxe
        else:
            print(f"🎭 Using cached meme for consistency: {os.path.basename(self.current_meme_path)}")
            web_img, eink_img, content_path = self.image_renderer.render_dual_images_with_cached_meme(
                block_height,
                block_hash,
                self.current_meme_path,
                mempool_api=self.mempool_api
            )
        
        # Save both images for caching
        # Race condition check: Verify block is still current before saving
        current_stored_height = getattr(self, 'current_block_height', 0) or 0
        if block_height < current_stored_height:
            print(f"⏭️ Skipping image save for old block {block_height} (current: {current_stored_height})")
            return  # Abort - newer block already processed
        
        if web_img is not None:
            web_img.save(self.current_image_path)
            print(f"💾 Web image saved to {self.current_image_path}")
        if eink_img is not None:
            eink_img.save(self.current_eink_image_path)
            print(f"💾 E-ink image saved to {self.current_eink_image_path}")
        
        # Update cache state
        self.current_block_height = block_height
        self.current_block_hash = block_hash
        self.image_is_current = True
        
        # Save persistent cache metadata to survive app restarts
        self._save_cache_metadata()
        
        # 🚀 PERFORMANCE FIX: Return web image IMMEDIATELY, then start background tasks
        # This ensures web clients get instant response (~3 seconds) instead of waiting for e-ink display (~25 seconds)
        print("🚀 Returning web image immediately for fast web response")
        
        # 🚀 IMMEDIATE E-INK UPDATE - Start e-ink display right after web image is ready
        # This reduces total update time from web→eink by running them sequentially but without delay
        if self.e_ink_enabled and not skip_epaper:
            current_eink_height = getattr(self, 'last_eink_block_height', 0) or 0
            if int(block_height or 0) != int(current_eink_height):
                print(f"⚡ Starting e-ink update for block {block_height}")
                with self.display_process_lock:
                    active_blocks = list(self.active_display_processes.keys())
                    if not any(active_block >= block_height for active_block in active_blocks):
                        # Start e-ink display immediately (no delay)
                        threading.Thread(
                            target=self._display_on_epaper_async,
                            args=(self.current_eink_image_path, block_height, block_hash),
                            daemon=True
                        ).start()
                    else:
                        print(f"⏳ E-ink display already in progress for block >= {block_height}")
        
        # Start wallet refresh in background (lower priority)
        def start_wallet_refresh():
            """Start wallet refresh in background."""
            if self.config.get("show_wallet_balances_block", True):
                # Check if wallet refresh is already in progress (prevent concurrent scans)
                if hasattr(self.image_renderer, 'wallet_api') and hasattr(self.image_renderer.wallet_api, '_fetch_lock'):
                    if self.image_renderer.wallet_api._fetch_lock.locked():
                        print("⏸️ Wallet refresh already in progress, skipping duplicate scan")
                        return
                
                print("⚙️ Starting async wallet refresh in background...")
                threading.Thread(
                    target=self._safe_wallet_refresh_thread,
                    args=(block_height, block_hash, False),
                    daemon=True
                ).start()
                print("✅ Async wallet refresh thread started")
        
        # Schedule wallet refresh to run after a short delay to prioritize e-ink
        threading.Thread(target=start_wallet_refresh, daemon=True).start()
        
        return web_img  # Return web image for web clients IMMEDIATELY
    
    def get_prioritized_content_path(self):
        """
        """
        # Fallback to regular meme selection
        print("🎭 Using meme fallback")
        return None  # Let image renderer handle meme selection
    

    def on_new_block_received(self, block_height, block_hash):
        """
        Handle new block data received from WebSocket.
        
        Args:
            block_height (str): New block height
            block_hash (str): New block hash
        """
        # Block info already logged by block_monitor
        # print(f"👁️ WebSocket: New block received - Height: {block_height}")
        # print(f"👁️ Block hash: {block_hash}")
        
        # Convert block_height to integer if it's a string
        try:
            if isinstance(block_height, str):
                # Handle potential decimal notation like "918.724"
                if '.' in block_height:
                    block_height_int = int(float(block_height))
                    print(f"⚙️ [DEBUG] Converted block height from {block_height} to {block_height_int}")
                else:
                    block_height_int = int(block_height)
            else:
                block_height_int = int(block_height)
        except (ValueError, TypeError) as e:
            print(f"❌ [DEBUG] Failed to convert block height {block_height}: {e}")
            return
        
        # 🔧 FIX: Prevent duplicate block processing and race conditions
        current_height = getattr(self, 'current_block_height', None)
        try:
            current_height_int = int(current_height) if current_height is not None else None
        except (ValueError, TypeError):
            current_height_int = None

        if current_height_int is not None and block_height_int <= current_height_int:
            return
        
        # Acquire lock to prevent concurrent block processing
        if not self._block_processing_lock.acquire(blocking=False):
            return
        
        try:
            # Double-check after acquiring lock
            current_height = getattr(self, 'current_block_height', None)
            try:
                current_height_int = int(current_height) if current_height is not None else None
            except (ValueError, TypeError):
                current_height_int = None

            if current_height_int is not None and block_height_int <= current_height_int:
                return
            
            # Block notification already sent by block_monitor callback
            # No need to send duplicate notification here
            
            # Always regenerate dashboard and update e-ink display immediately after new block
            self.image_is_current = False  # Invalidate cache to force regeneration
            self.regenerate_dashboard(block_height_int, block_hash)
            
        finally:
            self._block_processing_lock.release()
    
    def on_new_block_notification(self, block_height, block_hash):
        """
        Handle new block notification to web clients (INSTANT, no API wait).
        Sends basic notification immediately, enriches data in background.
        
        Args:
            block_height (int): New block height
            block_hash (str): New block hash
        """
        try:
            # 🚀 INSTANT NOTIFICATION - Send basic data immediately (no API wait)
            notification_data = {
                'block_height': block_height,
                'block_hash': self._format_block_hash_for_display(block_hash),
                'timestamp': int(time.time()),  # Use current time as approximate
                'pool_name': 'Loading...',  # Will be updated in background
                'total_reward_btc': 3.125,  # Current default subsidy
                'total_fees_btc': 0,  # Will be updated
                'subsidy_btc': 3.125,
                'median_fee_sat_vb': 0  # Will be updated
            }
            
            # print(f"⚡ Sending INSTANT block notification for {block_height} (enrichment in background)")
            
            # Send instant notification to subscribed clients
            with self.app.app_context():
                if self.block_notification_subscribers:
                    for client_id in self.block_notification_subscribers.copy():
                        self.socketio.emit('new_block_notification', notification_data, room=client_id)
                    print(f"📡 Instant notification sent to {len(self.block_notification_subscribers)} clients")
            
            # 🔄 Enrich notification data in background (non-blocking)
            def enrich_notification():
                try:
                    # Check if there are subscribers BEFORE making expensive API call
                    if not self.block_notification_subscribers:
                        return  # Skip enrichment if no clients subscribed
                    
                    print(f"🌐 Enriching block notification with API data...")
                    base_url = self._get_mempool_base_url()
                    block_response = requests.get(f"{base_url}/block/{block_hash}", timeout=10, verify=False)
                    
                    if block_response.ok:
                        block_data = block_response.json()
                        timestamp = block_data.get('timestamp', int(time.time()))
                        total_fees = block_data.get('extras', {}).get('totalFees', 0)
                        subsidy = block_data.get('extras', {}).get('reward', 3.125 * 100000000)
                        pool_name = block_data.get('extras', {}).get('pool', {}).get('name', 'Unknown')
                        median_fee = block_data.get('extras', {}).get('medianFee', 0)
                        
                        enriched_data = {
                            'block_height': block_height,
                            'block_hash': self._format_block_hash_for_display(block_hash),
                            'timestamp': timestamp,
                            'pool_name': pool_name,
                            'total_reward_btc': (subsidy + total_fees) / 100000000,
                            'total_fees_btc': total_fees / 100000000,
                            'subsidy_btc': subsidy / 100000000,
                            'median_fee_sat_vb': median_fee,
                            'enriched': True  # Flag to indicate this is enriched data
                        }
                        
                        print(f"✅ Block notification enriched: {pool_name}")
                        
                        # Send updated notification
                        with self.app.app_context():
                            if self.block_notification_subscribers:
                                for client_id in self.block_notification_subscribers.copy():
                                    self.socketio.emit('new_block_notification', enriched_data, room=client_id)
                                print(f"📡 Enriched notification sent to {len(self.block_notification_subscribers)} clients")
                except Exception as e:
                    print(f"⚠️ Failed to enrich notification: {e}")
            
            # Run enrichment in background thread
            threading.Thread(target=enrich_notification, daemon=True).start()
                
        except Exception as e:
            print(f"⚠️ Error sending new block notification: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_mempool_base_url(self):
        """Get mempool API base URL from configuration with HTTPS support."""
        mempool_host = self.config.get("mempool_host", "127.0.0.1")
        mempool_rest_port = self.config.get("mempool_rest_port", "8080")
        mempool_use_https = self.config.get("mempool_use_https", False)
        
        # Build URL with proper protocol
        protocol = "https" if mempool_use_https else "http"
        
        # Check if host looks like a domain (contains dots but not just IP)
        # Skip port for domains using standard ports (80/443)
        is_domain = "." in mempool_host and not mempool_host.replace(".", "").isdigit()
        
        if is_domain:
            if (mempool_use_https and mempool_rest_port in ["443", "80"]) or \
               (not mempool_use_https and mempool_rest_port in ["80", "443"]):
                return f"{protocol}://{mempool_host}/api"
            else:
                return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
        else:
            # Always include port for IP addresses
            return f"{protocol}://{mempool_host}:{mempool_rest_port}/api"
    
    def _format_block_hash_for_display(self, block_hash):
        """
        Format block hash for display: first 6 and last 6 characters, grouped in pairs.
        
        Args:
            block_hash (str): Full block hash
            
        Returns:
            str: Formatted hash like "00 00 00 ... ea 1f 0c"
        """
        if len(block_hash) < 12:
            return block_hash  # Return as-is if too short
        
        # Get first 6 and last 6 characters
        first_six = block_hash[:6]
        last_six = block_hash[-6:]
        
        # Group in pairs with spaces
        first_formatted = ' '.join([first_six[i:i+2] for i in range(0, 6, 2)])
        last_formatted = ' '.join([last_six[i:i+2] for i in range(0, 6, 2)])
        
        return f"{first_formatted} ... {last_formatted}"
    
    def regenerate_dashboard(self, block_height, block_hash):
        """
        Generate new dashboard image and update displays.
        
        Args:
            block_height (str): Bitcoin block height
            block_hash (str): Bitcoin block hash
        """
        
        # 🔧 FIX: Prevent concurrent regeneration calls
        if not self.generation_lock.acquire(blocking=False):
            return
            
        try:
            # Check if we already have this block cached to avoid unnecessary regeneration
            if (self.current_block_height == block_height and 
                self.current_block_hash == block_hash and 
                self.image_is_current and 
                os.path.exists(self.current_image_path) and
                os.path.exists(self.current_eink_image_path)):
                print(f"💾 Dashboard already current for block {block_height} - no regeneration needed")
                return
        
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    # Check if any gap limit detection is currently running
                    active_bootstrap = False
                    if hasattr(self, 'wallet_api') and hasattr(self.wallet_api, '_active_gap_limit_detection'):
                        active_bootstrap = len(self.wallet_api._active_gap_limit_detection) > 0
                    
                    if active_bootstrap:
                        print(f"⏳ Bootstrap detection running - using cached wallet data for immediate display... (attempt {attempt})")
                    else:
                        print(f"⚙️ Generating dashboard image with cached wallet data... (attempt {attempt})")
                        
                    img = self._generate_new_image(block_height, block_hash, use_new_meme=True)  # New block = new meme
                    if img:
                        buf = io.BytesIO()
                        img.save(buf, format='PNG')
                        buf.seek(0)
                        with self.app.app_context():
                            try:
                                image_data = 'data:image/png;base64,' + base64.b64encode(buf.read()).decode()
                                if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                                    self.socketio.emit('new_image', {'image': image_data})
                                    print("📶 New image sent to web clients via WebSocket")
                                else:
                                    print("⚠️ Invalid image data generated, not sending to clients")
                            except Exception as e:
                                print(f"⚠️ Failed to encode image for WebSocket: {e}")
                        # ✅ Background tasks (wallet refresh + e-ink display) are already started in _generate_new_image
                        print("✅ Image generated and background tasks started automatically")
                        break
                    else:
                        print(f"❌ Image generation returned None (attempt {attempt})")
                except Exception as e:
                    print(f"❌ Error regenerating dashboard for block {block_height} (attempt {attempt}): {e}")
                    import traceback
                    traceback.print_exc()
                if attempt < max_retries:
                    print(f"🔁 Retrying image generation in 2 seconds...")
                    time.sleep(2)
                else:
                    print(f"❌ All {max_retries} attempts to generate dashboard image failed for block {block_height}")
                
        finally:
            # Always release the generation lock
            self.generation_lock.release()
    
    def _setup_routes(self):
        """Setup Flask routes."""
        
        # Add optimized static file serving with cache headers for memes
        @self.app.route('/static/memes/<filename>')
        def serve_meme_with_cache(filename):
            """Serve meme files with proper cache headers to reduce browser overhead."""
            from flask import Response
            import os
            from datetime import datetime, timedelta
            
            file_path = os.path.join('static', 'memes', filename)
            
            if not os.path.exists(file_path):
                return "File not found", 404
            
            # Get file stats for ETag and Last-Modified
            file_stat = os.stat(file_path)
            file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
            etag = f'"{file_stat.st_mtime}-{file_stat.st_size}"'
            
            # Check if client has cached version (If-None-Match header)
            if request.headers.get('If-None-Match') == etag:
                return Response(status=304)  # Not Modified
            
            # Check if client has cached version (If-Modified-Since header)
            if_modified_since = request.headers.get('If-Modified-Since')
            if if_modified_since:
                try:
                    client_cache_time = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S GMT')
                    if file_mtime <= client_cache_time:
                        return Response(status=304)  # Not Modified
                except ValueError:
                    pass  # Invalid date format, serve the file
            
            # Serve file with cache headers
            response = send_file(file_path)
            
            # Set cache headers for 1 hour (3600 seconds)
            response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
            response.headers['ETag'] = etag
            response.headers['Last-Modified'] = file_mtime.strftime('%a, %d %b %Y %H:%M:%S GMT')
            
            # Add immutable cache for files that don't change (optional)
            # Uncomment the next line for longer caching if memes rarely change
            # response.headers['Cache-Control'] = 'public, max-age=86400, immutable'  # 24 hours
            
            return response
        
        @self.app.route('/image')
        @require_web_auth(self.auth_manager)
        def image():
            """Return current dashboard image (optimized for fast serving)."""
            # Get client info for debugging repeated requests
            client_ip = request.remote_addr
            user_agent = request.headers.get('User-Agent', 'Unknown')
            
            # Always serve existing image if available (even if outdated)
            if os.path.exists(self.current_image_path):
                # For outdated images, start background refresh but serve current one
                if not self._has_valid_cached_image():
                    print(f"📷 Serving cached image, starting background refresh (client: {client_ip})")
                    threading.Thread(
                        target=self._background_image_generation,
                        daemon=True
                    ).start()
                else:
                    # Only log if there are frequent requests (throttle logging)
                    if not hasattr(self, '_last_image_serve_log'):
                        self._last_image_serve_log = {}
                    
                    now = time.time()
                    last_log_time = self._last_image_serve_log.get(client_ip, 0)
                    
                    # Log once per 5 minutes per client to reduce log spam
                    if now - last_log_time > 300:
                        print(f"📷 Serving up-to-date cached image (client: {client_ip})")
                        self._last_image_serve_log[client_ip] = now
                
                # Serve file with proper cache headers
                response = send_file(self.current_image_path, mimetype='image/png')
                
                # Set cache headers to reduce unnecessary requests (5 minute cache)
                response.headers['Cache-Control'] = 'public, max-age=300'
                
                # Add ETag for conditional requests
                if os.path.exists(self.current_image_path):
                    file_mtime = os.path.getmtime(self.current_image_path)
                    etag = f'"{int(file_mtime)}"'
                    response.headers['ETag'] = etag
                    
                    # Check if client has valid cached version
                    if request.headers.get('If-None-Match') == etag:
                        return '', 304  # Not Modified - no need to send data
                
                return response
            
            # No cached image at all - generate minimal placeholder and start background generation
            print("⚠️ No cached image - generating placeholder and starting background generation")
            try:
                # Start background generation immediately
                threading.Thread(
                    target=self._background_image_generation,
                    daemon=True
                ).start()
                
                # Generate and return placeholder quickly
                placeholder_img = self._generate_placeholder_image()
                buf = io.BytesIO()
                placeholder_img.save(buf, format='PNG')
                buf.seek(0)
                return send_file(buf, mimetype='image/png')
                
            except Exception as e:
                print(f"❌ Failed to generate placeholder image: {e}")
                return "Image generation failed", 503
        
        @self.app.route('/')
        @require_web_auth(self.auth_manager)
        def dashboard():
            """Serve the main dashboard web page."""
            display_status = "enabled" if self.e_ink_enabled else "disabled"
            display_icon = "🖥️" if self.e_ink_enabled else "🚫"
            
            # Get current language and orientation
            lang = self.config.get("language", "en")
            # Use web_orientation for the dashboard view
            orientation = self.config.get("web_orientation", "vertical")
            current_translations = translations.get(lang, translations["en"])
            
            # Get current block height for cache-busting
            block_height = self.current_block_height if self.current_block_height else 0
            
            return render_template('dashboard.html', 
                                 translations=current_translations,
                                 display_icon=display_icon,
                                 e_ink_enabled=self.e_ink_enabled,
                                 # This orientation determines the CSS class for layout
                                 orientation=orientation,
                                 live_block_notifications_enabled=self.config.get('live_block_notifications_enabled', False),
                                 block_height=block_height)
        
        @self.app.route('/config')
        @require_web_auth(self.auth_manager)
        def config_page():
            """Serve the configuration page."""
            # Get current language
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('config.html', 
                                 translations=current_translations,
                                 live_block_notifications_enabled=self.config.get('live_block_notifications_enabled', False))
        
        @self.app.route('/login')
        def login_page():
            """Serve the login page."""
            # Get current language
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('login.html', translations=current_translations)
        
        @self.app.route('/api/login', methods=['POST'])
        @require_rate_limit(self.auth_manager)
        def login():
            """Handle login requests."""
            try:
                data = request.json
                username = data.get('username', '')
                password = data.get('password', '')
                
                if self.auth_manager.login(username, password):
                    return jsonify({'success': True, 'message': 'Login successful'})
                else:
                    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400
        
        @self.app.route('/api/logout', methods=['POST'])
        def logout():
            """Handle logout requests."""
            self.auth_manager.logout()
            return jsonify({'success': True, 'message': 'Logout successful'})

        # Mobile API Token Endpoints
        @self.app.route('/api/mobile/token/generate', methods=['POST'])
        @require_auth(self.auth_manager)
        def generate_mobile_token():
            """Generate a new API token for mobile app authentication."""
            try:
                data = request.json or {}
                device_name = data.get('device_name', 'Unknown Device')
                validity_days = data.get('validity_days', 90)
                
                # Validate input
                if not device_name or len(device_name.strip()) == 0:
                    return jsonify({'success': False, 'message': 'Device name is required'}), 400
                
                if not isinstance(validity_days, int) or validity_days < 1 or validity_days > 365:
                    return jsonify({'success': False, 'message': 'Validity days must be between 1 and 365'}), 400
                
                token = self.mobile_token_manager.generate_token(device_name.strip(), validity_days)
                
                if token:
                    return jsonify({
                        'success': True,
                        'token': token,
                        'device_name': device_name.strip(),
                        'validity_days': validity_days,
                        'message': f'Token generated for {device_name.strip()}'
                    })
                else:
                    return jsonify({'success': False, 'message': 'Failed to generate token'}), 500
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/mobile/token/validate', methods=['POST'])
        def validate_mobile_token():
            """Validate a mobile API token."""
            try:
                data = request.json or {}
                token = data.get('token', '')
                
                if not token:
                    return jsonify({'success': False, 'message': 'Token is required'}), 400
                
                is_valid = self.mobile_token_manager.validate_token(token)
                
                if is_valid:
                    return jsonify({
                        'success': True,
                        'valid': True,
                        'message': 'Token is valid'
                    })
                else:
                    return jsonify({
                        'success': True,
                        'valid': False,
                        'message': 'Token is invalid or expired'
                    })
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/mobile/token/list', methods=['GET'])
        @require_auth(self.auth_manager)
        def list_mobile_tokens():
            """List all active mobile tokens."""
            try:
                tokens = self.mobile_token_manager.list_tokens()
                return jsonify({
                    'success': True,
                    'tokens': tokens,
                    'count': len(tokens)
                })
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/mobile/token/revoke', methods=['POST'])
        @require_auth(self.auth_manager)
        def revoke_mobile_token():
            """Revoke a specific mobile token."""
            try:
                data = request.json or {}
                token_preview = data.get('token_preview', '')
                
                if not token_preview:
                    return jsonify({'success': False, 'message': 'Token preview is required'}), 400
                
                # Find the full token by preview
                tokens = self.mobile_token_manager.tokens
                target_token = None
                
                for token in tokens:
                    preview = token[:8] + '...' + token[-4:]
                    if preview == token_preview:
                        target_token = token
                        break
                
                if target_token:
                    revoked = self.mobile_token_manager.revoke_token(target_token)
                    if revoked:
                        return jsonify({
                            'success': True,
                            'message': 'Token revoked successfully'
                        })
                    else:
                        return jsonify({'success': False, 'message': 'Failed to revoke token'}), 500
                else:
                    return jsonify({'success': False, 'message': 'Token not found'}), 404
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/mobile/auth', methods=['POST'])
        def mobile_authenticate():
            """Authenticate using mobile API token and return session info."""
            try:
                data = request.json or {}
                token = data.get('token', '')
                
                if not token:
                    return jsonify({'success': False, 'message': 'Token is required'}), 400
                
                is_valid = self.mobile_token_manager.validate_token(token)
                
                if is_valid:
                    # Create a temporary session for mobile access
                    session['mobile_authenticated'] = True
                    session['mobile_token'] = token
                    session['authentication_time'] = time.time()
                    
                    return jsonify({
                        'success': True,
                        'message': 'Mobile authentication successful',
                        'session_info': {
                            'authenticated': True,
                            'mobile': True,
                            'timestamp': time.time()
                        }
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Invalid or expired token'
                    }), 401
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        # Mobile Block Data API Endpoints
        @self.app.route('/api/mobile/block/current', methods=['GET'])
        @require_mobile_auth(self.mobile_token_manager)
        def get_current_block_mobile():
            """Get current block information for mobile widget."""
            try:
                # Get current block data from mempool
                if hasattr(self, 'mempool_websocket') and self.mempool_websocket:
                    current_block = self.mempool_websocket.get_current_block()
                else:
                    # Fallback to API
                    current_block = self.mempool_api.get_latest_block()
                
                if current_block:
                    # Format for mobile widget
                    mobile_data = {
                        'block_height': current_block.get('height'),
                        'block_hash': current_block.get('id', '')[:16] + '...',  # Truncated for mobile
                        'timestamp': current_block.get('timestamp'),
                        'total_fees_btc': current_block.get('extras', {}).get('totalFees', 0) / 100000000,  # Convert sats to BTC
                        'median_fee_sat_vb': current_block.get('extras', {}).get('medianFee', 0),
                        'tx_count': current_block.get('tx_count', 0),
                        'size': current_block.get('size', 0),
                        'weight': current_block.get('weight', 0)
                    }
                    
                    return jsonify({
                        'success': True,
                        'block': mobile_data,
                        'timestamp': time.time()
                    })
                else:
                    return jsonify({'success': False, 'message': 'Block data not available'}), 503
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/mobile/price/current', methods=['GET'])
        @require_mobile_auth(self.mobile_token_manager)
        def get_current_price_mobile():
            """Get current Bitcoin price for mobile widget."""
            try:
                # Get price data from BTC price API
                price_data = self.btc_price_api.get_bitcoin_price()
                
                if price_data:
                    mobile_price_data = {
                        'usd_price': price_data.get('usd_price'),
                        'price_in_selected_currency': price_data.get('price_in_selected_currency'),
                        'currency': price_data.get('currency', 'USD'),
                        'moscow_time': price_data.get('moscow_time'),
                        'timestamp': time.time()
                    }
                    
                    return jsonify({
                        'success': True,
                        'price': mobile_price_data
                    })
                else:
                    return jsonify({'success': False, 'message': 'Price data not available'}), 503
                    
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/mobile/widget/data', methods=['GET'])
        @require_mobile_auth(self.mobile_token_manager)
        def get_widget_data_mobile():
            """Get all widget data in one request for mobile efficiency."""
            try:
                widget_data = {
                    'success': True,
                    'timestamp': time.time(),
                    'block': None,
                    'price': None,
                    'status': 'ok'
                }
                
                # Get block data
                try:
                    if hasattr(self, 'mempool_websocket') and self.mempool_websocket:
                        current_block = self.mempool_websocket.get_current_block()
                    else:
                        current_block = self.mempool_api.get_latest_block()
                    
                    if current_block:
                        widget_data['block'] = {
                            'height': current_block.get('height'),
                            'hash': current_block.get('id', '')[:16] + '...',
                            'timestamp': current_block.get('timestamp'),
                            'total_fees_btc': current_block.get('extras', {}).get('totalFees', 0) / 100000000,
                            'median_fee_sat_vb': current_block.get('extras', {}).get('medianFee', 0),
                            'tx_count': current_block.get('tx_count', 0)
                        }
                except Exception as e:
                    print(f"Failed to get block data for widget: {e}")
                
                # Get price data
                try:
                    price_data = self.btc_price_api.get_bitcoin_price()
                    if price_data:
                        widget_data['price'] = {
                            'usd_price': price_data.get('usd_price'),
                            'price_in_selected_currency': price_data.get('price_in_selected_currency'),
                            'currency': price_data.get('currency', 'USD'),
                            'moscow_time': price_data.get('moscow_time')
                        }
                except Exception as e:
                    print(f"Failed to get price data for widget: {e}")
                
                return jsonify(widget_data)
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/session/status', methods=['GET'])
        def session_status():
            """Get current session status and remaining time."""
            # Don't require auth since we need to check if we're authenticated
            session_info = self.auth_manager.get_session_info()
            
            # Add debug information
            debug_info = {
                'flask_session_keys': list(session.keys()),
                'flask_session_id': session.get('_id', 'no-id'),
                'app_secret_key_length': len(self.app.secret_key) if self.app.secret_key else 0,
                'current_timestamp': time.time()
            }
            
            return jsonify({
                **session_info,
                'debug': debug_info
            })
        
        @self.app.route('/api/session/refresh', methods=['POST'])
        @require_auth(self.auth_manager)
        def session_refresh():
            """Refresh the current session to extend its lifetime."""
            if self.auth_manager.refresh_session():
                return jsonify({
                    'success': True,
                    'message': 'Session refreshed successfully',
                    'session_info': self.auth_manager.get_session_info()
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Session could not be refreshed'
                }), 401

        @self.app.route('/api/config', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_config():
            """Get current configuration including secure wallet addresses."""
            try:
                print("📋 [DEBUG] Config API called - checking for wallet addresses...")
                
                # Get current language and translations
                lang = self.config.get("language", "en")
                current_translations = translations.get(lang, translations["en"])
                
                # Get the regular configuration
                config_data = self.config_manager.get_current_config()
                
                # Add wallet addresses from secure configuration if available
                if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api.secure_config_manager:
                    secure_config = self.image_renderer.wallet_api.secure_config_manager.load_secure_config()
                    print(f"📋 [DEBUG] Secure config loaded: {secure_config is not None}")
                    # if secure_config:
                    #     print(f"📋 [DEBUG] Secure config keys: {list(secure_config.keys())}")
                    if secure_config and 'wallet_balance_addresses_with_comments' in secure_config:
                        wallet_addresses = secure_config['wallet_balance_addresses_with_comments']
                        config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                        print(f"📋 [DEBUG] Added {len(wallet_addresses)} wallet addresses to config response")
                        
                        # ENHANCEMENT: Include cached balances in the configuration
                        try:
                            if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                                print("📋 [DEBUG] Attempting to include cached balances in config...")
                                cached_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                                # print(f"📋 [DEBUG] Cached wallet data: {cached_data}")
                                
                                # Merge balances into wallet addresses
                                if cached_data and 'addresses' in cached_data:
                                    address_balances = {}
                                    # Create lookup for address balances
                                    for addr_info in cached_data['addresses']:
                                        if 'address' in addr_info and 'balance_btc' in addr_info:
                                            address_balances[addr_info['address']] = addr_info['balance_btc']
                                    
                                    # Create lookup for xpub balances  
                                    if 'xpubs' in cached_data:
                                        for xpub_info in cached_data['xpubs']:
                                            if 'xpub' in xpub_info and 'balance_btc' in xpub_info:
                                                address_balances[xpub_info['xpub']] = xpub_info['balance_btc']
                                    
                                    # print(f"📋 [DEBUG] Address balance lookup: {address_balances}")
                                    
                                    # Add balances to wallet addresses
                                    for addr_entry in wallet_addresses:
                                        if 'address' in addr_entry:
                                            address = addr_entry['address']
                                            if address in address_balances:
                                                addr_entry['cached_balance'] = address_balances[address]
                                                print(f"📋 [DEBUG] Added balance {address_balances[address]} for {address[:10]}...")
                                            else:
                                                addr_entry['cached_balance'] = 0.0
                                                print(f"📋 [DEBUG] No balance found for {address[:10]}...")
                                    
                                    config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                                    config_data['wallet_total_balance'] = cached_data.get('total_btc', 0.0)
                                    print(f"📋 [DEBUG] Enhanced config with cached balances, total: {cached_data.get('total_btc', 0.0)}")
                                    
                        except Exception as balance_error:
                            print(f"📋 [DEBUG] Error adding cached balances to config: {balance_error}")
                            # Continue without cached balances if there's an error
                        
                        for i, addr in enumerate(wallet_addresses):
                            address_display = addr.get('address', 'N/A')[:10] + '...' if addr.get('address') else 'N/A'
                            balance_display = addr.get('cached_balance', 'N/A')
                            print(f"📋 [DEBUG] Address {i}: {address_display} ({addr.get('comment', 'No comment')}) - Balance: {balance_display}")
                    else:
                        print("📋 [DEBUG] No wallet_balance_addresses_with_comments found in secure config")
                else:
                    print("📋 [DEBUG] No wallet API or secure config manager available")
                
                return jsonify({
                    'config': config_data,
                    'schema': self.config_manager.get_config_schema(current_translations),
                    'categories': self.config_manager.get_categories(current_translations),
                    'color_options': self.config_manager.get_color_options()
                })
            except Exception as e:
                print(f"Error in get_config: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/translations/<language>', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_translations(language):
            """Get translations for a specific language."""
            try:
                from utils.translations import translations
                language_translations = translations.get(language, translations["en"])
                return jsonify({
                    'success': True,
                    'translations': language_translations
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/config', methods=['POST'])
        @require_auth(self.auth_manager)
        def save_config():
            """Save configuration changes."""
            try:
                # Refresh session on any authenticated activity
                self.auth_manager.refresh_session()
                
                # Store old config for comparison
                old_config = dict(self.config) if hasattr(self, 'config') else None
                
                new_config = request.json
                if self.config_manager.save_config(new_config):
                    # Update local config reference
                    self.config = self.config_manager.get_current_config()
                    
                    # Update auth manager config
                    self.auth_manager.config = self.config
                    
                    # Clean up cache for removed wallet addresses before reinitializing
                    if old_config:
                        self._cleanup_removed_wallet_caches(old_config, new_config)
                    
                    # Reinitialize components if needed
                    self._reinitialize_after_config_change(old_config)
                    
                    return jsonify({'success': True, 'message': 'Configuration 2 saved successfully'})
                else:
                    return jsonify({'success': False, 'message': 'Failed to save configuration'}), 500
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400
        
        @self.app.route('/api/upload-meme', methods=['POST'])
        @require_auth(self.auth_manager)
        def upload_meme():
            """Handle meme image uploads."""
            try:
                if 'file' not in request.files:
                    return jsonify({'success': False, 'message': 'No file provided'}), 400
                
                file = request.files['file']
                if file.filename == '':
                    return jsonify({'success': False, 'message': 'No file selected'}), 400
                
                # Validate file type
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
                if file_ext not in allowed_extensions:
                    return jsonify({
                        'success': False, 
                        'message': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                    }), 400
                
                # Secure filename and save
                filename = secure_filename(file.filename)
                upload_path = os.path.join('static', 'memes', filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                
                # Save file
                file.save(upload_path)
                
                return jsonify({
                    'success': True, 
                    'message': f'Meme uploaded successfully: {filename}',
                    'filename': filename
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/memes', methods=['GET'])
        @require_auth(self.auth_manager)
        def list_memes():
            """List all uploaded memes with pagination and lazy loading support."""
            try:
                # Get pagination parameters
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 50, type=int)  # Limit to 50 memes per request
                metadata_only = request.args.get('metadata_only', 'false').lower() == 'true'
                
                memes_dir = os.path.join('static', 'memes')
                if not os.path.exists(memes_dir):
                    return jsonify({'memes': [], 'total': 0, 'page': page, 'per_page': per_page})
                
                # Get all meme files
                all_files = []
                for filename in os.listdir(memes_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        all_files.append(filename)
                
                # Sort files for consistent pagination
                all_files.sort()
                
                # Calculate pagination
                total_files = len(all_files)
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                page_files = all_files[start_idx:end_idx]
                
                memes = []
                for filename in page_files:
                    file_path = os.path.join(memes_dir, filename)
                    try:
                        file_size = os.path.getsize(file_path)
                        file_stat = os.stat(file_path)
                        
                        meme_data = {
                            'filename': filename,
                            'size': file_size,
                            'url': f'/static/memes/{filename}',
                            'last_modified': file_stat.st_mtime
                        }
                        
                        # Only include full URL if not metadata_only mode
                        if not metadata_only:
                            meme_data['url'] = f'/static/memes/{filename}'
                        
                        memes.append(meme_data)
                    except OSError:
                        # Skip files that can't be read
                        continue
                
                return jsonify({
                    'memes': memes,
                    'total': total_files,
                    'page': page,
                    'per_page': per_page,
                    'has_next': end_idx < total_files,
                    'has_prev': page > 1
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/download-meme/<filename>', methods=['GET'])
        @require_auth(self.auth_manager)
        def download_meme(filename):
            """Download a specific meme file."""
            try:
                # Secure the filename
                filename = secure_filename(filename)
                file_path = os.path.join('static', 'memes', filename)
                
                if not os.path.exists(file_path):
                    return jsonify({'success': False, 'message': 'File not found'}), 404
                
                return send_file(file_path, as_attachment=True, download_name=filename)
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/delete-meme/<filename>', methods=['DELETE'])
        @require_auth(self.auth_manager)
        def delete_meme(filename):
            """Delete a specific meme file."""
            try:
                # Secure the filename
                filename = secure_filename(filename)
                file_path = os.path.join('static', 'memes', filename)
                
                if not os.path.exists(file_path):
                    return jsonify({'success': False, 'message': 'File not found'}), 404
                
                # Delete the file
                os.remove(file_path)
                
                return jsonify({
                    'success': True, 
                    'message': f'Meme deleted successfully: {filename}'
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/rename-meme', methods=['POST'])
        @require_auth(self.auth_manager)
        def rename_meme():
            """Rename a meme file."""
            try:
                data = request.json
                if not data or 'old_filename' not in data or 'new_filename' not in data:
                    return jsonify({'success': False, 'message': 'Missing filename parameters'}), 400
                
                old_filename = secure_filename(data['old_filename'])
                new_filename = secure_filename(data['new_filename'])
                
                if old_filename == new_filename:
                    return jsonify({'success': False, 'message': 'New filename is the same as old filename'}), 400
                
                old_path = os.path.join('static', 'memes', old_filename)
                new_path = os.path.join('static', 'memes', new_filename)
                
                if not os.path.exists(old_path):
                    return jsonify({'success': False, 'message': f'File not found: {old_filename}'}), 404
                
                if os.path.exists(new_path):
                    return jsonify({'success': False, 'message': f'A file with the name {new_filename} already exists'}), 400
                
                # Rename the file
                os.rename(old_path, new_path)
                
                return jsonify({
                    'success': True,
                    'message': f'Meme renamed from {old_filename} to {new_filename}',
                    'old_filename': old_filename,
                    'new_filename': new_filename
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/meme-hashes', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_meme_hashes():
            """Get SHA-256 hashes of all existing memes for duplicate detection."""
            try:
                import hashlib
                
                memes_dir = os.path.join('static', 'memes')
                if not os.path.exists(memes_dir):
                    return jsonify({'hashes': {}})
                
                hashes = {}
                for filename in os.listdir(memes_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        file_path = os.path.join(memes_dir, filename)
                        try:
                            # Calculate SHA-256 hash of file content
                            sha256_hash = hashlib.sha256()
                            with open(file_path, "rb") as f:
                                # Read file in chunks for efficiency
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            
                            file_hash = sha256_hash.hexdigest()
                            hashes[file_hash] = filename
                        except Exception as e:
                            print(f"Error hashing {filename}: {e}")
                            continue
                
                return jsonify({'hashes': hashes})
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/wallet_balance', methods=['POST'])
        @require_auth(self.auth_manager)
        def refresh_wallet_balances():
            """Refresh wallet balances for the provided addresses."""
            try:
                request_data = request.json
                if not request_data or 'addresses' not in request_data:
                    return jsonify({'success': False, 'message': 'No addresses provided'}), 400
                
                addresses = request_data['addresses']
                if not isinstance(addresses, list):
                    return jsonify({'success': False, 'message': 'Addresses must be a list'}), 400
                
                # Extract just the address strings for the wallet API
                address_list = []
                for addr_entry in addresses:
                    if isinstance(addr_entry, dict) and 'address' in addr_entry:
                        address_list.append(addr_entry['address'])
                    elif isinstance(addr_entry, str):
                        address_list.append(addr_entry)
                
                if not address_list:
                    return jsonify({'success': True, 'balances': []})
                
                # Use the wallet API to fetch balances
                try:
                    balances = []
                    for address in address_list:
                        # Determine address type and use appropriate method
                        address = address.strip()
                        if not address:
                            balances.append(0.0)
                            continue
                            
                        try:
                            if address.startswith(('xpub', 'zpub', 'ypub')):
                                # Use xpub balance method for extended public keys
                                balance = self.image_renderer.wallet_api.get_xpub_balance(address)
                            else:
                                # Use regular address balance method
                                balance = self.image_renderer.wallet_api.get_address_balance(address)
                            
                            balances.append(balance)
                            
                        except Exception as addr_error:
                            print(f"Error fetching balance for {address}: {addr_error}")
                            balances.append(0.0)
                    
                    # Emit WebSocket event with updated cache after manual refresh
                    cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                    if hasattr(self, 'socketio') and self.socketio and cached_wallet_data:
                        self.socketio.emit('wallet_balance_updated', cached_wallet_data)
                        print("📡 [MANUAL] Balance update broadcasted via WebSocket")
                    
                    return jsonify({
                        'success': True,
                        'balances': balances
                    })
                    
                except Exception as wallet_error:
                    print(f"Wallet balance API error: {wallet_error}")
                    # Return zeros if wallet API fails
                    return jsonify({
                        'success': True,
                        'balances': [0.0] * len(address_list),
                        'warning': 'Could not fetch live balances, showing cached/zero values'
                    })
                
            except Exception as e:
                print(f"Error in refresh_wallet_balances: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/wallet_balance_cached', methods=['POST'])
        @require_auth(self.auth_manager)
        def get_cached_wallet_balances():
            """Get cached wallet balances for the provided addresses."""
            try:
                request_data = request.json
                if not request_data or 'addresses' not in request_data:
                    return jsonify({'success': False, 'message': 'No addresses provided'}), 400
                
                addresses = request_data['addresses']
                if not isinstance(addresses, list):
                    return jsonify({'success': False, 'message': 'Addresses must be a list'}), 400
                
                # Extract just the address strings for the wallet API
                address_list = []
                for addr_entry in addresses:
                    if isinstance(addr_entry, dict) and 'address' in addr_entry:
                        address_list.append(addr_entry['address'])
                    elif isinstance(addr_entry, str):
                        address_list.append(addr_entry)
                
                if not address_list:
                    return jsonify({'success': True, 'balances': []})
                
                # Get cached wallet data
                cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                
                balances = []
                for address in address_list:
                    address = address.strip()
                    if not address:
                        balances.append(0.0)
                        continue
                    
                    balance = 0.0  # Default balance
                    
                    if cached_wallet_data:
                        # Check if address is an xpub/ypub/zpub
                        if address.startswith(('xpub', 'zpub', 'ypub')):
                            # Look for xpub data in cache (array format)
                            xpub_entries = cached_wallet_data.get('xpubs', [])
                            for xpub_entry in xpub_entries:
                                if xpub_entry.get('xpub') == address:
                                    balance = xpub_entry.get('balance_btc', 0.0)
                                    break
                        else:
                            # Look for regular address in cache (array format)
                            address_entries = cached_wallet_data.get('addresses', [])
                            for addr_entry in address_entries:
                                if addr_entry.get('address') == address:
                                    balance = addr_entry.get('balance_btc', 0.0)
                                    break
                    
                    balances.append(balance)
                
                return jsonify({
                    'success': True,
                    'balances': balances,
                    'cached': True
                })
                
            except Exception as e:
                print(f"Error in get_cached_wallet_balances: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/block-rewards/<address>/found-blocks', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_found_blocks_count(address):
            """Get the number of found blocks for a specific Bitcoin address."""
            try:
                if not address:
                    return jsonify({'success': False, 'message': 'No address provided'}), 400
                
                # Get found blocks count from block monitor
                found_blocks = 0
                
                if hasattr(self, 'block_monitor') and self.block_monitor:
                    # Check if this address is in the monitored addresses
                    current_config = self.config_manager.get_current_config()
                    
                    # Support both table format and legacy format
                    monitored_addresses = set()
                    
                    # New table format
                    block_reward_table = current_config.get("block_reward_addresses_table", [])
                    for entry in block_reward_table:
                        if isinstance(entry, dict) and entry.get("address"):
                            monitored_addresses.add(entry["address"])
                    
                    if address in monitored_addresses:
                        # Use new cache system for fast retrieval
                        found_blocks = self.block_monitor.get_coinbase_count(address)
                    else:
                        found_blocks = 0
                
                return jsonify({
                    'success': True,
                    'address': address,
                    'found_blocks': found_blocks
                })
                
            except Exception as e:
                print(f"Error in get_found_blocks_count: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500
        
        # WebSocket event handlers (only if SocketIO is enabled)
        if self.socketio:
            @self.socketio.on('connect')
            def handle_connect():
                """Handle client connection."""
                pass
            
            @self.socketio.on('disconnect')
            def handle_disconnect(*args):
                """Handle client disconnection."""
                # Remove client from block notification subscribers
                client_id = request.sid
                self.block_notification_subscribers.discard(client_id)
                # Disconnect logged silently - normal client behavior
                
                # Clean up console log streaming for disconnected client
                try:
                    if self.log_stream_manager:
                        client_id = request.sid
                        self.log_stream_manager.handle_client_disconnect(client_id)
                except Exception as e:
                    # Silent cleanup - don't log errors for normal disconnections
                    pass
            
            @self.socketio.on('request_latest_image')
            def handle_request_latest_image():
                """Handle client request for latest image - avoid unnecessary regeneration."""
                print("📶 Client requested latest image")
                try:
                    # First check if we have a current cached image
                    if os.path.exists(self.current_image_path):
                        # Check if image is current and valid
                        if self._has_valid_cached_image():
                            print("✅ Serving current cached image (no regeneration needed)")
                            with open(self.current_image_path, 'rb') as f:
                                image_data = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                                # Validate image data before sending
                                if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                                    self.socketio.emit('new_image', {'image': image_data})
                                    print("📡 Current image sent to requesting client")
                                    return
                        else:
                            print("⚠️ Cached image exists but is outdated")
                    
                    # Only generate new image if we don't have a current one
                    print("⚙️ No current image available, starting background generation")
                    threading.Thread(
                        target=self._background_image_generation,
                        daemon=True
                    ).start()
                    
                    # If we have any cached image (even outdated), send it while generating new one
                    if os.path.exists(self.current_image_path):
                        print("📶 Sending existing image while generating fresh one")
                        with open(self.current_image_path, 'rb') as f:
                            image_data = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                            if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                                self.socketio.emit('new_image', {'image': image_data})
                    else:
                        print("⚠️ No cached image available at all")
                        
                except Exception as e:
                    print(f"❌ Error handling latest image request: {e}")
                    # Don't send invalid data to client
            
            @self.socketio.on('subscribe_block_notifications')
            def handle_subscribe_block_notifications(data):
                """Handle client request to subscribe to live block notifications."""
                print("📶 Client requested to subscribe to block notifications")
                try:
                    # Check if user is authenticated
                    if not self.auth_manager.is_authenticated():
                        print("⚠️ Unauthorized attempt to subscribe to block notifications")
                        self.socketio.emit('block_notification_error', {'error': 'Authentication required'})
                        return
                    
                    # Add client to subscribers
                    client_id = request.sid
                    self.block_notification_subscribers.add(client_id)
                    print(f"✅ Client {client_id} subscribed to block notifications")
                    self.socketio.emit('block_notification_status', {'status': 'subscribed', 'message': 'Subscribed to live block notifications'})
                        
                except Exception as e:
                    print(f"❌ Error subscribing to block notifications: {e}")
                    self.socketio.emit('block_notification_error', {'error': 'Failed to subscribe to block notifications'})
            
            @self.socketio.on('unsubscribe_block_notifications')
            def handle_unsubscribe_block_notifications():
                """Handle client request to unsubscribe from live block notifications."""
                print("📶 Client requested to unsubscribe from block notifications")
                try:
                    # Remove client from subscribers
                    client_id = request.sid
                    self.block_notification_subscribers.discard(client_id)
                    print(f"✅ Client {client_id} unsubscribed from block notifications")
                    self.socketio.emit('block_notification_status', {'status': 'unsubscribed'})
                        
                except Exception as e:
                    print(f"❌ Error unsubscribing from block notifications: {e}")
                    self.socketio.emit('block_notification_error', {'error': 'Failed to unsubscribe from block notifications'})
                    
            @self.socketio.on_error_default
            def default_error_handler(e):
                """Handle SocketIO errors."""
                print(f"⚠️ SocketIO error: {e}")
                
            @self.socketio.on('connect_error')
            def handle_connect_error(data):
                """Handle connection errors."""
                print(f"🚫 SocketIO connection error: {data}")
                
        else:
            print("⚙️ SocketIO event handlers skipped (SocketIO disabled)")
    
    def start_websocket_listener(self):
        """Start the WebSocket listener for real-time block updates."""
        # Check if WebSocket client exists and is initialized
        if hasattr(self, 'websocket_client') and self.websocket_client:
            self.websocket_client.start_listener_thread()
        else:
            # WebSocket not initialized yet (could be instant startup mode)
            enable_instant_startup = self.config.get("enable_instant_startup", False)
            if enable_instant_startup:
                print("⚙️ WebSocket listener deferred (instant startup - will initialize in background)")
            else:
                print("⚙️ WebSocket listener skipped (WebSocket disabled)")
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """
        Run the Flask application.
        
        Args:
            host (str): Host to bind to
            port (int): Port to listen on
            debug (bool): Enable debug mode
        """
        print(f"🚀 Starting Mempaper server on {host}:{port}")
        
        # Start WebSocket listener
        self.start_websocket_listener()
        
        # Run Flask app
        if self.socketio:
            self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        else:
            print("⚙️ Running Flask app without SocketIO")
            self.app.run(host=host, port=port, debug=debug)


# Global app instance for WSGI compatibility
_app_instance = None

def get_app_instance():
    """Get or create the global MempaperApp instance (singleton)."""
    global _app_instance
    if _app_instance is None:
        _app_instance = MempaperApp()
    return _app_instance

def create_app():
    """Create and return Flask app instance for WSGI compatibility."""
    return get_app_instance().app

def get_socketio():
    """Get SocketIO instance for external use."""
    return get_app_instance().socketio


if __name__ == '__main__':
    # Create and run the application directly
    print("🚀 Starting Mempaper Bitcoin Dashboard (Direct Mode)")
    print("=" * 60)
    mempaper_app = MempaperApp()
    mempaper_app.run(debug=False)
