"""
Main Application Module - Mempaper Bitcoin Dashboard

This is the main Flask application that coordinates all components:
- Web server and SocketIO for real-time updates
- Integration with Bitcoin mempool for block data
- Image rendering and e-Paper display
- WebSocket management for live updates

Version: 2.0 (Refactored)
"""

import json
import io
import base64
import threading
import multiprocessing
import urllib3
import os
import time
from werkzeug.utils import secure_filename
from flask import Flask, send_file, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO

# Import custom modules
from mempool_api import MempoolAPI
from websocket_client import MempoolWebSocket
from image_renderer import ImageRenderer
from translations import translations
from config_manager import ConfigManager
from technical_config import TechnicalConfig
from security_config import SecurityConfig
from auth_manager import AuthManager, require_auth, require_web_auth, require_rate_limit

# Privacy utilities for secure logging
try:
    from privacy_utils import BitcoinPrivacyMasker
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
    
    @staticmethod
    def mask_wallet_data_for_logging(wallet_data):
        """
        Create a privacy-safe copy of wallet data for logging.
        
        Args:
            wallet_data (dict): Original wallet data
            
        Returns:
            dict: Privacy-masked copy safe for logging
        """
        if not PRIVACY_UTILS_AVAILABLE or not wallet_data:
            return wallet_data
        
        # Create a deep copy to avoid modifying original data
        import copy
        masked_data = copy.deepcopy(wallet_data)
        
        # Mask addresses
        if 'addresses' in masked_data:
            for addr_info in masked_data['addresses']:
                if 'address' in addr_info:
                    addr_info['address'] = BitcoinPrivacyMasker.mask_address(addr_info['address'])
        
        # Mask XPUBs
        if 'xpubs' in masked_data:
            for xpub_info in masked_data['xpubs']:
                if 'xpub' in xpub_info:
                    xpub_info['xpub'] = BitcoinPrivacyMasker.mask_xpub(xpub_info['xpub'])
        
        return masked_data
    
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
            print("⚡ Skipping SocketIO initialization for faster startup")
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
            is_pi_zero = os.path.exists('/proc/device-tree/model') and 'Zero' in open('/proc/device-tree/model', 'rb').read().decode('utf-8', errors='ignore')
            
            socketio_config = {
                'cors_allowed_origins': '*', 
                'async_mode': async_mode,  # Auto-detect: gevent for production, threading for development
                'transports': ['polling'],  # Use polling only to avoid transport negotiation issues
                'ping_timeout': 90 if is_pi_zero else 60,      # Longer timeout for Pi Zero
                'ping_interval': 30 if is_pi_zero else 25,     # Longer interval for Pi Zero
                'max_http_buffer_size': 5000000 if is_pi_zero else 10000000,  # 5MB for Pi Zero, 10MB for others
                'engineio_logger': False,  # Reduce log noise
                'allow_upgrades': False,   # Disable transport upgrades to prevent negotiation issues
                'cookie': False,           # Disable cookies for better compatibility
                'always_connect': True,    # Force connection acceptance
                'cors_credentials': False  # Disable credentials for CORS
            }
            print(f"⚡ SocketIO async mode: {async_mode} ({'production' if is_production else 'development'})")
            if is_pi_zero:
                print("🍓 Raspberry Pi Zero detected - using optimized settings")
            self.socketio = SocketIO(self.app, **socketio_config)
    
    def _init_app_components(self):
        """Initialize the main application components."""
        # Initialize Flask app first
        self._init_flask_app()
        
        # Initialize SocketIO
        self._init_socketio()
        
        # Initialize authentication manager with config_manager for secure password handling
        self.auth_manager = AuthManager(self.config_manager)
        
        # Initialize browser console log streaming for authenticated users
        from browser_console_logger import LogStreamManager
        self.log_stream_manager = LogStreamManager(self.socketio, self.auth_manager)
        
        # Enable console log streaming if configured (default: disabled for performance)
        console_logging_enabled = self.config.get("enable_browser_console_logging", False)
        if console_logging_enabled:
            import logging
            log_level = getattr(logging, self.config.get("browser_console_log_level", "INFO").upper(), logging.INFO)
            self.log_stream_manager.setup_log_streaming(enable=True, log_level=log_level)
        
        # Get translations for configured language
        lang = self.config.get("language", "en")
        self.translations = translations.get(lang, translations["en"])
        
        # Initialize API clients
        self._init_api_clients()
        
        # Initialize image renderer
        self.image_renderer = ImageRenderer(self.config, self.translations)
        
        # Initialize block reward monitor
        from block_monitor import initialize_block_monitor
        self.block_monitor = initialize_block_monitor(self.config_manager)
        
        # Sync cache to current blockchain height (important for recovery after downtime)
        if self.block_monitor:
            print("🔄 Performing cache sync to current blockchain height...")
            try:
                self.block_monitor.sync_cache_to_current()
                print("✅ Cache sync completed successfully")
            except Exception as e:
                print(f"⚠️ Cache sync failed: {e}")
        
        # Start block monitoring if addresses are configured and not skipped for fast startup
        block_table_addresses = self.config.get("block_reward_addresses_table", [])
        has_addresses = bool(block_table_addresses)
        
        skip_block_monitoring = self.config.get("skip_block_monitoring_on_startup", False)
        
        if has_addresses and not skip_block_monitoring:
            self.block_monitor.start_monitoring()
            total_addresses = len(block_table_addresses)
            print(f"📡 Block reward monitoring started for {total_addresses} addresses")
        elif skip_block_monitoring:
            print("⚡ Skipping block monitoring for faster startup")
        elif not has_addresses:
            print("ⓘ No block reward addresses configured")
        
        # Check e-Paper display configuration
        self.e_ink_enabled = self.config.get("e-ink-display-connected", True)
        if self.e_ink_enabled:
            print("✓ e-Paper display enabled")
        else:
            print("ⓘ e-Paper display disabled - running in display-less mode")
        
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
        
        # Block tracker for e-ink display race condition prevention
        self.block_tracker = {}
        
        # E-ink display process management for cancellation
        self.active_display_processes = {}  # {block_height: subprocess.Popen}
        self.display_process_lock = threading.Lock()
        
        # Image generation lock to prevent concurrent generation
        self.generation_lock = threading.Lock()
        
        # Load persistent cache state from file
        self._load_cache_metadata()
        
        # Note: Configuration change callbacks registered at end of __init__
        
        # Setup Flask routes
        self._setup_routes()

        # Check if instant startup is enabled
        enable_instant_startup = self.config.get("enable_instant_startup", False)
        
        if enable_instant_startup:
            print("⚡ Instant startup enabled - website will be available immediately")
            # Initialize websocket_client to None - will be set up in background
            self.websocket_client = None
            self._setup_instant_startup()
        else:
            # Traditional startup process
            self._init_websocket()
            
            # Generate initial image on startup (skip for faster PC testing if disabled)
            skip_initial_image = self.config.get("skip_initial_image_generation", False)
            if skip_initial_image:
                print("⚡ Skipping initial image generation for faster startup")
                print("   Image will be generated on first web request")
            else:
                self._generate_initial_image()

        # Register callbacks for configuration changes (done after all components are initialized)
        self.config_manager.add_change_callback(self._on_config_file_changed)
        self.config_manager.add_change_callback(self._on_config_change)
        # On Windows, force config reload and callback notification after registering callbacks
        if os.name == 'nt':
            self.config_manager._reload_config_from_file()
            self.config_manager._notify_change_callbacks(self.config_manager.config)
        print("✓ Mempaper application initialized successfully")
    
    def _init_api_clients(self):
        # Mempool API setup
        mempool_ip = self.config.get("mempool_ip", "127.0.0.1")
        mempool_rest_port = self.config.get("mempool_rest_port", "4081")
        self.mempool_api = MempoolAPI(mempool_ip, mempool_rest_port)
        print("✓ Mempool API client initialized")
    
    def _init_websocket(self):
        """Initialize WebSocket connection for real-time updates."""
        # Skip WebSocket for faster PC startup if configured
        skip_websocket = self.config.get("skip_websocket_on_startup", False)
        if skip_websocket:
            print("⚡ Skipping WebSocket initialization for faster startup")
            self.websocket_client = None
            return
            
        mempool_ip = self.config.get("mempool_ip", "127.0.0.1")
        mempool_ws_port = self.config.get("mempool_ws_port", "8999")
        
        # Create WebSocket client with callback
        self.websocket_client = MempoolWebSocket(
            mempool_ip, 
            mempool_ws_port, 
            on_new_block_callback=self.on_new_block_received
        )
        
        # Configure backup-aware settings (adjust duration based on your backup schedule)
        backup_duration_minutes = self.config.get("backup_duration_minutes", 45)  # Default 45 minutes
        self.websocket_client.set_backup_schedule(max_backup_duration_minutes=backup_duration_minutes)
        
        print("✓ WebSocket client initialized with backup-aware reconnection")
        print(f"  📋 Max backup duration: {backup_duration_minutes} minutes")
    
    def _generate_initial_image(self):
        """Generate initial dashboard image on startup - optimized for fast start."""
        # If we already have cache metadata loaded, verify it's still current
        if (self.current_block_height is not None and 
            self.image_is_current and 
            os.path.exists(self.current_image_path)):
            
            try:
                block_info = self.mempool_api.get_current_block_info()
                
                if (self.current_block_height == block_info['block_height'] and
                    self.current_block_hash == block_info['block_hash']):
                    print(f"📸 Cache metadata restored: Block {self.current_block_height} is still current")
                    print("✓ Skipping initial image generation (cache is up-to-date)")
                    return
                else:
                    print(f"📊 Block changed since cache: {self.current_block_height} → {block_info['block_height']}")
                    self.image_is_current = False
            except Exception as e:
                print(f"⚠️ Could not verify current block, will regenerate: {e}")
                self.image_is_current = False
        
        # Check if we have a recent cached image first
        if os.path.exists(self.current_image_path):
            file_age = time.time() - os.path.getmtime(self.current_image_path)
            if file_age < 3600:  # Less than 1 hour old
                # Check if the cached image is for the current block
                try:
                    block_info = self.mempool_api.get_current_block_info()
                    
                    # If we don't know what block our cached image is for, or it's for a different block
                    if (self.current_block_height is None or 
                        self.current_block_height != block_info['block_height']):
                        print(f"📸 Cached image exists (age: {int(file_age/60)} minutes) but for different block")
                        print("🔄 Will refresh on first client request")
                        self.image_is_current = False
                    else:
                        print(f"📸 Using existing cached image (age: {int(file_age/60)} minutes)")
                        print("✓ Image is current for block {}, skipping generation".format(block_info['block_height']))
                        self.current_block_height = block_info['block_height']
                        self.current_block_hash = block_info['block_hash']
                        self.image_is_current = True  # Mark as current since it's for the right block
                        # Save metadata to ensure persistence
                        self._save_cache_metadata()
                    return
                except Exception as e:
                    print(f"⚠️ Could not verify block info, marking image as potentially outdated: {e}")
                    self.image_is_current = False
                    return
        
        try:
            print("🎨 Generating initial dashboard image...")
            
            # Warm up APIs before generating the first image to ensure complete data
            self._warm_up_apis()
            
            # Get current block info from mempool API
            block_info = self.mempool_api.get_current_block_info()
            
            # Generate image but skip e-Paper display for faster startup
            print(f"🎨 Generating new dashboard image for block {block_info['block_height']}...")
            
            # Render both web and e-ink images 
            # Note: Address derivation is complete, so balance calculation should work normally
            web_img, eink_img, meme_path = self.image_renderer.render_dual_images(
                block_info['block_height'], 
                block_info['block_hash'], 
                mempool_api=self.mempool_api,
                startup_mode=False  # Address derivation complete - calculate real balances
            )
            
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
            
            print("✓ Initial dashboard image generated and cached")
            
            # Display on e-Paper in background thread (don't block startup)
            if self.e_ink_enabled:
                print("🖥️ Starting e-Paper display in background...")
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                    daemon=True
                ).start()
            else:
                print("ⓘ Skipping e-Paper display (disabled in config)")
            
        except Exception as e:
            print(f"⚠️ Failed to generate initial image: {e}")
            print("   Image will be generated on first user request")
    
    def _warm_up_apis(self):
        """
        Warm up all API clients by fetching initial data to ensure they're ready.
        This prevents the first image from showing incomplete data.
        """
        print("🔄 Warming up API clients with initial data fetch...")
        
        # Warm up BTC price API
        try:
            price_data = self.image_renderer.fetch_btc_price()
            if price_data and not price_data.get("error"):
                print("✓ BTC price API warmed up successfully")
            else:
                print("⚠️ BTC price API warm-up returned no data (may work on retry)")
        except Exception as e:
            print(f"⚠️ BTC price API warm-up failed: {e}")
        
        # Warm up wallet balance API (if configured)
        wallet_entries = self.config.get("wallet_balance_addresses", [])
        if wallet_entries:
            try:
                # Use startup_mode=True to utilize cached data from address derivation phase
                print("🚀 [WARMUP] Using cached wallet data from address derivation...")
                #TODO: use cache here!
                # balance_data = self.image_renderer.fetch_wallet_balances(startup_mode=True)
                balance_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                if balance_data and not balance_data.get("error"):
                    total_btc = balance_data.get("total_btc", 0)
                    print(f"✓ Wallet balance API warmed up successfully ({total_btc:.8f} BTC)")
                else:
                    print("⚠️ Wallet balance API warm-up returned no data (may work on retry)")
            except Exception as e:
                print(f"⚠️ Wallet balance API warm-up failed: {e}")
        else:
            print("ⓘ No wallet addresses configured, skipping wallet API warm-up")
        
        # Warm up Bitaxe API (if configured) 
        bitaxe_ip = self.config.get("bitaxe_ip", "")
        if bitaxe_ip and bitaxe_ip != "192.168.1.1":
            try:
                bitaxe_data = self.image_renderer.fetch_bitaxe_stats()
                if bitaxe_data and not bitaxe_data.get("error"):
                    print("✓ Bitaxe API warmed up successfully")
                else:
                    print("⚠️ Bitaxe API warm-up returned no data (may work on retry)")
            except Exception as e:
                print(f"⚠️ Bitaxe API warm-up failed: {e}")
        else:
            print("ⓘ No Bitaxe configured, skipping Bitaxe API warm-up")
        
        print("✓ API warm-up phase completed")

    def _setup_instant_startup(self):
        """
        Setup instant startup mode:
        1. Load cached/default image immediately 
        2. Start heavy operations in background
        3. Update interface when ready
        """
        print("🚀 Setting up instant startup mode...")
        
        # Check if we have a cached image to show immediately
        has_cached_image = (os.path.exists(self.current_image_path) and 
                           os.path.exists(self.current_eink_image_path))
        
        if has_cached_image:
            cache_age = (time.time() - os.path.getmtime(self.current_image_path)) / 60
            print(f"📸 Found cached image (age: {cache_age:.1f} minutes) - website ready immediately")
            # Image metadata already loaded in _load_cache_metadata()
        else:
            print("📸 No cached image found - will create placeholder")
            self._create_placeholder_image()
        
        # Start background processing after a short delay to let the web server start
        background_delay = self.config.get("background_processing_delay", 2)
        print(f"⏳ Background processing will start in {background_delay} seconds...")
        
        threading.Timer(background_delay, self._run_background_startup).start()
        print("🌐 Website is now ready for immediate access!")

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
                font_path = self.config.get("font_bold", "fonts/Roboto-Bold.ttf")
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
            
            print("📸 Created informative placeholder images for instant startup")
            
            # Set basic cache state
            self.image_is_current = False
            self.current_block_height = None
            self.current_block_hash = None
            
        except Exception as e:
            print(f"⚠️ Failed to create placeholder image: {e}")

    def _run_background_startup(self):
        """Run heavy startup operations in background."""
        try:
            print("🔄 Starting background initialization...")
            
            # Initialize WebSocket connection
            self._init_websocket()
            
            # Start WebSocket listener now that client is initialized
            if hasattr(self, 'websocket_client') and self.websocket_client:
                print("🚀 Starting WebSocket listener (background initialization)")
                self.websocket_client.start_listener_thread()
            
            # Warm up APIs
            print("🔄 Warming up API clients...")
            self._warm_up_apis()
            
            # Generate fresh image
            print("🔄 Generating fresh dashboard image...")
            self._generate_initial_image()
            
            # Notify web clients that fresh content is available
            if hasattr(self, 'socketio') and self.socketio:
                self.socketio.emit('background_ready', {
                    'message': 'Background processing complete',
                    'block_height': self.current_block_height,
                    'timestamp': time.time()
                })
            
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
        
        # Cancel any older display processes when a newer block arrives
        if block_height:
            self._cancel_older_display_processes(int(block_height))
        
        def display_in_subprocess():
            process = None
            try:
                display_start = time.time()
                print(f"🔄 Starting e-paper display for: {image_path} at {time.strftime('%H:%M:%S', time.localtime(display_start))}")
                if block_height:
                    print(f"   Block: {block_height} | Hash: {block_hash}")
                    # Check if we already have a newer or equal block in tracking
                    current_height = self.block_tracker.get('block_height', 0)
                    if current_height and int(block_height) < int(current_height):
                        print(f"⚠️  SKIPPING older block display: {block_height} < current {current_height}")
                        return
                
                # Use subprocess to avoid GPIO conflicts between threads
                script_path = os.path.join(os.path.dirname(__file__), "display_subprocess.py")
                
                # Start the subprocess
                process = subprocess.Popen([
                    sys.executable, script_path, image_path
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=os.path.dirname(__file__))
                
                # Register the process for potential cancellation
                if block_height:
                    with self.display_process_lock:
                        self.active_display_processes[int(block_height)] = process
                        print(f"📋 Registered display process for block {block_height} (PID: {process.pid})")
                
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
                            print(f"📋 E-ink display tracking updated: Block {block_height}")
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
            print(f"🖥️ E-paper display started in background")
            
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
                            print(f"⚡ Force killed display process for block {block_height}")
                    
                    # Remove from tracking
                    self.active_display_processes.pop(block_height, None)
                    
                except Exception as e:
                    print(f"⚠️ Error cancelling display process for block {block_height}: {e}")
                    # Still remove from tracking even if cancellation failed
                    self.active_display_processes.pop(block_height, None)
    
    def _reinitialize_after_config_change(self):
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
        
        # Invalidate cached image since config changed (especially language)
        self.image_is_current = False
        print("🔄 Image cache invalidated due to configuration change")
        
        # Note: Image regeneration is handled by _on_config_change() callback
        # to avoid duplicate generation processes
        
        print("✓ Components reinitialized after configuration change")
    
    def _on_config_file_changed(self, new_config=None):
        """Handle configuration file changes (external edits)."""
        print("📝 Configuration file changed externally - reloading...")
        
        # Update local config reference
        self.config = self.config_manager.get_current_config()
        
        # Update auth manager config
        self.auth_manager.config = self.config
        
        # Reinitialize components
        self._reinitialize_after_config_change()
        
        # Notify connected web clients of config change
        try:
            if self.socketio:
                self.socketio.emit('config_reloaded', {
                    'message': 'Configuration reloaded from file',
                    'timestamp': int(time.time() * 1000)
                })
                print("📡 Web clients notified of configuration reload")
            else:
                print("⚡ SocketIO disabled - skipping web client notification")
        except Exception as e:
            print(f"⚠️ Failed to notify web clients: {e}")
    
    def _background_image_generation(self):
        """Generate image in background thread."""
        # Use lock to prevent concurrent generation
        if not self.generation_lock.acquire(blocking=False):
            print("⏳ Image generation already in progress, skipping")
            return
            
        try:
            print("🔄 Starting background image generation...")
            block_info = self.mempool_api.get_current_block_info()
            
            # Check if we already have this block
            if (self.current_block_height == block_info['block_height'] and 
                self.current_block_hash == block_info['block_hash'] and 
                self.image_is_current):
                print(f"✅ Image already current for block {block_info['block_height']}, skipping generation")
                return
            
            print(f"🔄 Need to generate: cached_height={self.current_block_height}, current_height={block_info['block_height']}, is_current={self.image_is_current}")
                
            self._generate_new_image(
                block_info['block_height'],
                block_info['block_hash'],
                skip_epaper=False  # Allow e-Paper update in background
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
        if self.config.get("orientation", "vertical") == "horizontal":
            width, height = 800, 480
        else:
            width, height = 480, 800
            
        # Create simple placeholder
        img = Image.new('RGB', (width, height), color='#667eea')
        draw = ImageDraw.Draw(img)
        
        # Simple text
        try:
            font = ImageFont.truetype(self.config.get("font_bold", "fonts/Roboto-Bold.ttf"), 48)
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
                    
                    # Check if cached images are recent (within 2 hours)
                    cache_time = metadata.get('timestamp', 0)
                    age_hours = (time.time() - cache_time) / 3600
                    
                    if age_hours < 2 and self.current_block_height:
                        self.image_is_current = True
                        print(f"📸 Restored cache state: Block {self.current_block_height} (age: {age_hours:.1f}h)")
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
                'current_meme_path': getattr(self, 'current_meme_path', None)  # Add meme caching
            }
            
            with open(self.cache_metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            print(f"💾 Cache metadata saved for block {self.current_block_height}")
        except Exception as e:
            print(f"⚠️ Error saving cache metadata: {e}")
    
    def _on_config_change(self, new_config):
        """
        Handle configuration changes that affect image rendering.
        Triggers immediate image regeneration with cached meme for visual settings.
        """
        print("🔧 Configuration change detected, checking if image refresh needed...")
        
        # Define settings that affect image rendering and require immediate refresh
        image_affecting_settings = {
            # Hardware settings
            'display_orientation', 'display_width', 'display_height', 'e-ink-display-connected',
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
            print(f"🎨 Image-affecting settings changed: {', '.join(changed_settings)}")
            print("🔄 Triggering immediate image refresh with cached meme...")
            
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
                print("📸 No cached image state available, will regenerate on next update")
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
                print(f"🎨 Regenerating images with cached meme for block {self.current_block_height}")
                
                # Verify cached meme still exists
                if not os.path.exists(self.current_meme_path):
                    print(f"⚠️ Cached meme {self.current_meme_path} no longer exists, will select new one")
                    self.current_meme_path = None
                    # Fall back to normal generation
                    self._generate_new_image(self.current_block_height, self.current_block_hash, skip_epaper=False)
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
                print("🔄 Starting async wallet refresh in background...")
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

        except Exception as e:
            print(f"❌ Error regenerating image with cached meme: {e}")
            # Fall back to normal generation
            self._generate_new_image(self.current_block_height, self.current_block_hash, skip_epaper=False)
    
    def async_wallet_refresh(self, block_height, block_hash, startup_mode=False):
        """Fetch fresh wallet data and regenerate image if balance changed."""
        print(f"🚀 [WALLET] Starting wallet refresh for block {block_height}...")
        try:
            # Fetch fresh wallet data
            print("🔍 [WALLET] Fetching fresh wallet data...")
            fresh_wallet_data = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode)
            
            # Log wallet data with privacy masking
            masked_fresh_data = MempaperApp.mask_wallet_data_for_logging(fresh_wallet_data)
            print(f"✅ [WALLET] Fresh wallet data: {masked_fresh_data}")
            
            # Get cached wallet data
            print("📖 [WALLET] Loading cached wallet data...")
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
            
            # Log cached data with privacy masking
            masked_cached_data = MempaperApp.mask_wallet_data_for_logging(cached_wallet_data)
            print(f"📋 [WALLET] Cached wallet data: {masked_cached_data}")
            
            # Ensure both are dicts before accessing .get()
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            
            # Compare only BTC/sats balance
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            
            print(f"⚖️ [WALLET] Balance comparison: Fresh={fresh_btc} BTC, Cached={cached_btc} BTC")

            if fresh_btc != cached_btc:
                # Regenerate image
                print("🔄 [WALLET] Wallet data changed, updating cache and regenerating image...")
                self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                
                # Emit WebSocket event for balance update
                if hasattr(self, 'socketio') and self.socketio:
                    self.socketio.emit('wallet_balance_updated', fresh_wallet_data)
                    print("📡 [WALLET] Balance update broadcasted via WebSocket")
                
                # Regenerate image with updated wallet data
                web_img, eink_img, content_path = self.image_renderer.render_dual_images(
                    block_height, block_hash,
                    mempool_api=self.mempool_api,
                    startup_mode=startup_mode
                )
                # Save images
                if web_img is not None:
                    web_img.save(self.current_image_path)
                if eink_img is not None:
                    eink_img.save(self.current_eink_image_path)
                print("✅ [WALLET] Image regenerated with updated wallet data")
            else:
                print("✅ [WALLET] No wallet balance change detected, keeping current image")
                # Still update the cache to keep timestamp fresh
                self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                
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
            print(f"🚀 [THREAD] Starting safe wallet refresh for block {block_height}...")
            
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
            from config_manager import ConfigManager
            from image_renderer import ImageRenderer
            from translations import translations
            
            # Load config and initialize image renderer with wallet API
            config_manager = ConfigManager()
            config = config_manager.get_current_config()
            image_renderer = ImageRenderer(config, translations)
            
            print(f"🔄 [PROCESS] Wallet refresh process started for block {block_height}")
            
            # Fetch fresh wallet data
            print("🔍 [PROCESS] Fetching fresh wallet data...")
            fresh_wallet_data = image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode)
            
            # Log wallet data with privacy masking
            masked_fresh_data = MempaperApp.mask_wallet_data_for_logging(fresh_wallet_data)
            print(f"✅ [PROCESS] Fresh wallet data: {masked_fresh_data}")
            
            # Get cached wallet data
            print("📖 [PROCESS] Loading cached wallet data...")
            cached_wallet_data = image_renderer.wallet_api.get_cached_wallet_balances()
            
            # Log cached data with privacy masking  
            masked_cached_data = MempaperApp.mask_wallet_data_for_logging(cached_wallet_data)
            print(f"📋 [PROCESS] Cached wallet data: {masked_cached_data}")
            
            # Ensure both are dicts before accessing .get()
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            
            # Compare only BTC/sats balance
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            
            print(f"⚖️ [PROCESS] Balance comparison: Fresh={fresh_btc} BTC, Cached={cached_btc} BTC")

            if fresh_btc != cached_btc:
                print("🔄 [PROCESS] Wallet data changed, updating cache...")
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

    def _generate_new_image(self, block_height: int, block_hash: str, skip_epaper: bool = False):
        """Generate a new dashboard image and cache it."""
        print(f"🎨 Generating new dashboard image for block {block_height}...")
        
        # Render both web and e-ink images
        web_img, eink_img, content_path = self.image_renderer.render_dual_images(
            block_height, 
            block_hash, 
            mempool_api=self.mempool_api
        )
        
        # Save both images for caching
        if web_img is not None:
            web_img.save(self.current_image_path)
            print(f"💾 Web image saved to {self.current_image_path}")
        if eink_img is not None:
            eink_img.save(self.current_eink_image_path)
            print(f"💾 E-ink image saved to {self.current_eink_image_path}")
        
        # Update cache state
        self.current_block_height = block_height
        self.current_block_hash = block_hash
        self.current_meme_path = content_path  # Cache the selected content path (meme)
        self.image_is_current = True
        
        # Save persistent cache metadata to survive app restarts
        self._save_cache_metadata()
        
        # Start async wallet refresh in background for all image generations
        print("🔄 Starting async wallet refresh in background...")
        # Use threading approach to avoid multiprocessing pickle issues
        threading.Thread(
            target=self._safe_wallet_refresh_thread,
            args=(block_height, block_hash, False),  # False for startup_mode
            daemon=True
        ).start()
        print("✅ Async wallet refresh thread started")
        
        # Display on e-Paper (only if enabled, not skipped, and actually new content)
        if self.e_ink_enabled and not skip_epaper:
            # Check if this block is actually new for the e-ink display
            if (self.last_eink_block_height != block_height or 
                self.last_eink_block_hash != block_hash):
                print(f"🖥️ New block for e-ink: {block_height} (was: {self.last_eink_block_height})")
                # Run e-Paper display in background to not block the response
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self.current_eink_image_path, block_height, block_hash),
                    daemon=True
                ).start()
                print("🖥️ E-Paper display started in background")
            else:
                print(f"✅ E-ink already shows block {block_height}, skipping display update")
        elif skip_epaper:
            print("ⓘ Skipping e-Paper display (skip_epaper=True)")
        else:
            print("ⓘ Skipping e-Paper display (disabled in config)")
        
        return web_img  # Return web image for web clients
    
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
        print(f"🎯 WebSocket: New block received - Height: {block_height}")
        print(f"📦 Block hash: {block_hash}")
        self.regenerate_dashboard(block_height, block_hash)
    
    def regenerate_dashboard(self, block_height, block_hash):
        """
        Generate new dashboard image and update displays.
        
        Args:
            block_height (str): Bitcoin block height
            block_hash (str): Bitcoin block hash
        """
        try:
            # Use cached wallet data for fast image generation
            print("⚡ Generating dashboard image with cached wallet data...")
            img = self._generate_new_image(block_height, block_hash)
            
            # Emit to web clients via WebSocket only if generation was successful
            if img:
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                
                with self.app.app_context():
                    try:
                        image_data = 'data:image/png;base64,' + base64.b64encode(buf.read()).decode()
                        # Validate image data before sending
                        if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                            self.socketio.emit('new_image', {'image': image_data})
                            print("📡 New image sent to web clients via WebSocket")
                        else:
                            print("⚠️ Invalid image data generated, not sending to clients")
                    except Exception as e:
                        print(f"⚠️ Failed to encode image for WebSocket: {e}")
            # Start async wallet refresh in background
            print("🔄 Starting async wallet refresh in background...")
            # Use threading approach to avoid multiprocessing pickle issues
            threading.Thread(
                target=self._safe_wallet_refresh_thread,
                args=(block_height, block_hash, False),  # False for startup_mode
                daemon=True
            ).start()
            print("✅ Async wallet refresh thread started")

        except Exception as e:
            print(f"❌ Error regenerating dashboard for block {block_height}: {e}")
            import traceback
            traceback.print_exc()
    
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
            # Always serve existing image if available (even if outdated)
            if os.path.exists(self.current_image_path):
                # For outdated images, start background refresh but serve current one
                if not self._has_valid_cached_image():
                    print("📷 Serving cached image, starting background refresh")
                    threading.Thread(
                        target=self._background_image_generation,
                        daemon=True
                    ).start()
                else:
                    print("📷 Serving up-to-date cached image")
                
                return send_file(self.current_image_path, mimetype='image/png')
            
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
            orientation = self.config.get("orientation", "vertical")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('dashboard.html', 
                                 translations=current_translations,
                                 display_icon=display_icon,
                                 e_ink_enabled=self.e_ink_enabled,
                                 orientation=orientation,
                                 console_logging_enabled=self.config.get('enable_browser_console_logging', False))
        
        @self.app.route('/config')
        @require_web_auth(self.auth_manager)
        def config_page():
            """Serve the configuration page."""
            # Get current language
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('config.html', translations=current_translations)
        
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
        @self.app.route('/api/test-wallet-config', methods=['GET'])
        def test_wallet_config():
            """Test endpoint to check wallet configuration (no auth required for debugging)"""
            try:
                print("🧪 [DEBUG] Test wallet config endpoint called")
                
                # Get regular configuration
                config_data = self.config_manager.get_current_config()
                print(f"🧪 [DEBUG] Regular config has {len(config_data)} keys")
                
                wallet_addresses = config_data.get('wallet_balance_addresses_with_comments', [])
                print(f"🧪 [DEBUG] Found {len(wallet_addresses)} wallet addresses in regular config")
                
                # Also try secure config directly
                secure_addresses = None
                if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api.secure_config_manager:
                    secure_config = self.image_renderer.wallet_api.secure_config_manager.load_secure_config()
                    if secure_config and 'wallet_balance_addresses_with_comments' in secure_config:
                        secure_addresses = secure_config['wallet_balance_addresses_with_comments']
                        print(f"🧪 [DEBUG] Found {len(secure_addresses)} wallet addresses in secure config")

                # Try to get cached balances if wallet API is available
                balances_result = None
                if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                    try:
                        print("🧪 [DEBUG] Attempting to get cached wallet balances...")
                        
                        # Use the wallet API to get cached data directly
                        cached_data = self.image_renderer.wallet_api.get_cached_wallet_data()
                        print(f"🧪 [DEBUG] Cached wallet data: {cached_data}")
                        
                        balances_result = cached_data
                    except Exception as balance_error:
                        print(f"🧪 [DEBUG] Error getting cached balances: {balance_error}")
                        balances_result = {'error': str(balance_error)}

                return jsonify({
                    'success': True,
                    'wallet_addresses_from_regular_config': wallet_addresses,
                    'wallet_addresses_from_secure_config': secure_addresses,
                    'cached_balances': balances_result,
                    'regular_config_keys': list(config_data.keys()),
                    'message': f'Found {len(wallet_addresses)} wallet addresses'
                })
            except Exception as e:
                print(f"🧪 [DEBUG] Error in test endpoint: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({
                    'success': False,
                    'error': str(e)
                })

        @self.app.route('/api/test-wallet-balance', methods=['GET'])
        def test_wallet_balance():
            """Test endpoint to get wallet balances (no auth required for debugging)"""
            try:
                print("🧪 [DEBUG] Test wallet balance endpoint called")
                
                # Get wallet addresses from config
                config_data = self.config_manager.get_current_config()
                wallet_addresses = config_data.get('wallet_balance_addresses_with_comments', [])
                
                if not wallet_addresses:
                    return jsonify({
                        'success': False,
                        'message': 'No wallet addresses found in configuration'
                    })
                
                print(f"🧪 [DEBUG] Testing balances for {len(wallet_addresses)} addresses")
                
                # Use the wallet API to get balances directly
                if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                    try:
                        # Extract just the address strings
                        address_list = []
                        for addr_entry in wallet_addresses:
                            if isinstance(addr_entry, dict) and 'address' in addr_entry:
                                address_list.append(addr_entry['address'])
                            elif isinstance(addr_entry, str):
                                address_list.append(addr_entry)
                        
                        print(f"🧪 [DEBUG] Address list for balance lookup: {address_list}")
                        
                        # Get balances using the wallet API
                        balances = []
                        for address in address_list:
                            try:
                                balance = self.image_renderer.wallet_api.get_address_balance(address)
                                balances.append(balance)
                                print(f"🧪 [DEBUG] Balance for {address[:10]}...: {balance}")
                            except Exception as addr_error:
                                print(f"🧪 [DEBUG] Error getting balance for {address}: {addr_error}")
                                balances.append(0.0)
                        
                        # Also get cached data
                        cached_data = self.image_renderer.wallet_api.get_cached_wallet_data()
                        
                        return jsonify({
                            'success': True,
                            'addresses': wallet_addresses,
                            'balances': balances,
                            'cached_data': cached_data,
                            'message': f'Retrieved balances for {len(address_list)} addresses'
                        })
                        
                    except Exception as api_error:
                        print(f"🧪 [DEBUG] Error using wallet API: {api_error}")
                        return jsonify({
                            'success': False,
                            'error': str(api_error),
                            'addresses': wallet_addresses
                        })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Wallet API not available',
                        'addresses': wallet_addresses
                    })
                    
            except Exception as e:
                print(f"🧪 [DEBUG] Error in test balance endpoint: {e}")
                import traceback
                traceback.print_exc()
                return jsonify({
                    'success': False,
                    'error': str(e)
                })

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
                    if secure_config:
                        print(f"📋 [DEBUG] Secure config keys: {list(secure_config.keys())}")
                    if secure_config and 'wallet_balance_addresses_with_comments' in secure_config:
                        wallet_addresses = secure_config['wallet_balance_addresses_with_comments']
                        config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                        print(f"📋 [DEBUG] Added {len(wallet_addresses)} wallet addresses to config response")
                        
                        # ENHANCEMENT: Include cached balances in the configuration
                        try:
                            if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                                print("📋 [DEBUG] Attempting to include cached balances in config...")
                                cached_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                                print(f"📋 [DEBUG] Cached wallet data: {cached_data}")
                                
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
                                    
                                    print(f"📋 [DEBUG] Address balance lookup: {address_balances}")
                                    
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
        
        @self.app.route('/api/config', methods=['POST'])
        @require_auth(self.auth_manager)
        def save_config():
            """Save configuration changes."""
            try:
                # Refresh session on any authenticated activity
                self.auth_manager.refresh_session()
                
                new_config = request.json
                if self.config_manager.save_config(new_config):
                    # Update local config reference
                    self.config = self.config_manager.get_current_config()
                    
                    # Update auth manager config
                    self.auth_manager.config = self.config
                    
                    # Reinitialize components if needed
                    self._reinitialize_after_config_change()
                    
                    return jsonify({'success': True, 'message': 'Configuration saved successfully'})
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
                print("🔌 Client connected to WebSocket")
                
                # Auto-enable console logging for authenticated clients if configured
                try:
                    if self.log_stream_manager and self.config.get('enable_browser_console_logging', False):
                        # Check if client is authenticated
                        from flask import session
                        if session.get('authenticated', False):
                            client_id = request.sid
                            print(f"🛠️ Auto-enabling console logging for authenticated client: {client_id}")
                            self.log_stream_manager.handle_client_connect(client_id)
                            self.socketio.emit('console_log_enabled', {
                                'message': 'Console logging automatically enabled'
                            }, room=client_id)
                        else:
                            print("🔒 Console logging disabled - client not authenticated")
                except Exception as e:
                    print(f"⚠️ Error in auto-console logging setup: {e}")
            
            @self.socketio.on('disconnect')
            def handle_disconnect():
                """Handle client disconnection."""
                print("🔌 Client disconnected from WebSocket")
                
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
                print("📱 Client requested latest image")
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
                    print("🎨 No current image available, starting background generation")
                    threading.Thread(
                        target=self._background_image_generation,
                        daemon=True
                    ).start()
                    
                    # If we have any cached image (even outdated), send it while generating new one
                    if os.path.exists(self.current_image_path):
                        print("📷 Sending existing image while generating fresh one")
                        with open(self.current_image_path, 'rb') as f:
                            image_data = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                            if len(image_data) > 50 and image_data.startswith('data:image/png;base64,'):
                                self.socketio.emit('new_image', {'image': image_data})
                    else:
                        print("⚠️ No cached image available at all")
                        
                except Exception as e:
                    print(f"❌ Error handling latest image request: {e}")
                    # Don't send invalid data to client
            
            @self.socketio.on('enable_console_logs')
            def handle_enable_console_logs():
                """Handle client request to enable console log streaming (now automatic when configured)."""
                print("🔌 Client requested console log streaming (automatic when configured)")
                try:
                    # Check if user is authenticated
                    if not self.auth_manager.is_authenticated():
                        print("⚠️ Unauthorized attempt to enable console logs")
                        self.socketio.emit('console_log_error', {'error': 'Authentication required'})
                        return
                    
                    # Check if console logging is enabled in config
                    config = self.config_manager.get_current_config()
                    if not config.get('enable_browser_console_logging', False):
                        print("⚠️ Browser console logging is disabled in configuration")
                        self.socketio.emit('console_log_error', {'error': 'Console logging disabled in configuration - enable it in Settings'})
                        return
                    
                    # Console logging should already be enabled automatically on connect
                    # Just confirm the status
                    if self.log_stream_manager:
                        client_id = request.sid
                        # Re-enable in case it was missed during connection
                        self.log_stream_manager.handle_client_connect(client_id)
                        print(f"✅ Console log streaming confirmed for client {client_id}")
                        self.socketio.emit('console_log_status', {'status': 'enabled', 'message': 'Console logging is automatic when enabled in Settings'})
                    else:
                        print("❌ Log stream manager not available")
                        self.socketio.emit('console_log_error', {'error': 'Log streaming not available'})
                        
                except Exception as e:
                    print(f"❌ Error confirming console logs: {e}")
                    self.socketio.emit('console_log_error', {'error': 'Failed to confirm console logging'})
            
            @self.socketio.on('disable_console_logs')
            def handle_disable_console_logs():
                """Handle client request to disable console log streaming."""
                print("🔌 Client requested to disable console log streaming")
                try:
                    # Remove client from log streaming
                    if self.log_stream_manager:
                        client_id = request.sid
                        self.log_stream_manager.handle_client_disconnect(client_id)
                        print(f"✅ Console log streaming disabled for client {client_id}")
                        self.socketio.emit('console_log_status', {'status': 'disabled'})
                    else:
                        print("❌ Log stream manager not available")
                        
                except Exception as e:
                    print(f"❌ Error disabling console logs: {e}")
                    self.socketio.emit('console_log_error', {'error': 'Failed to disable console logging'})
        else:
            print("⚡ SocketIO event handlers skipped (SocketIO disabled)")
    
    def start_websocket_listener(self):
        """Start the WebSocket listener for real-time block updates."""
        # Check if WebSocket client exists and is initialized
        if hasattr(self, 'websocket_client') and self.websocket_client:
            self.websocket_client.start_listener_thread()
        else:
            # WebSocket not initialized yet (could be instant startup mode)
            enable_instant_startup = self.config.get("enable_instant_startup", False)
            if enable_instant_startup:
                print("⚡ WebSocket listener deferred (instant startup - will initialize in background)")
            else:
                print("⚡ WebSocket listener skipped (WebSocket disabled)")
    
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
            print("⚡ Running Flask app without SocketIO")
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
