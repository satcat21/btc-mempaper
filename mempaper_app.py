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
import queue
import threading
import traceback
import urllib3
import os
import logging
import subprocess
import hashlib
import shutil
import requests
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Flask, send_file, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, join_room, leave_room

# Import custom modules
from lib.mempool_api import MempoolAPI
from lib.websocket_client import MempoolWebSocket
from lib.image_renderer import ImageRenderer
from utils.translations import translations
from managers.config_manager import ConfigManager
from utils.technical_config import TechnicalConfig, build_mempool_api_url
from utils.security_config import SecurityConfig
from utils.color_lut import ColorLUT
from managers.secure_cache_manager import SecureCacheManager
from managers.auth_manager import AuthManager, require_auth, require_web_auth, allow_public_or_auth, require_rate_limit, require_mobile_auth
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

        # Setup-mode flag used by delivery onboarding flow
        self.setup_mode_flag_path = os.path.join("cache", "setup_mode.json")
        self._startup_timestamp = time.time()

        # Wi-Fi recovery state (runtime fallback into setup mode after sustained outage)
        self._wifi_disconnect_since = None
        self._wifi_last_reconnect_try = 0
        self._wifi_reconnect_attempts = 0
        self._wifi_last_setup_probe_try = 0
        self._wifi_recovery_thread_started = False
        # Set to True after user submits credentials so recovery monitor probes immediately
        self._wifi_connect_pending = False
        # Set to True once the hotspot onboarding screen has been shown; prevents re-renders
        # every time the recovery monitor restores the hotspot after a failed probe.
        self._onboarding_hotspot_screen_shown = False
        # True while the connected onboarding screen is displayed on e-ink (suppresses other e-ink updates)
        self._onboarding_connected_active = False
        # Timestamp of the last time iw reported a station associated to our AP.
        # Used to suppress probes for a grace window after the phone screen goes off.
        self._last_ap_station_seen_ts = 0.0
        
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
        
        # TEMPORARY: Disable session cookie domain to fix gevent issues
        self.app.config['SESSION_COOKIE_DOMAIN'] = None
        self.app.config['SESSION_COOKIE_PATH'] = '/'
        
        # Ensure JSON responses are properly formatted
        self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        self.app.config['JSON_SORT_KEYS'] = False
    
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
        
        # Summary: Cache loading complete
        print("💾 Secure caches loaded")
        
        # Note: Cache sync and monitoring start moved to _run_background_startup for faster website availability
        print("⚙️ Block monitor initialized (sync and monitoring will start in background)")
        
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
        
        # In-memory image cache for instant web serving (avoids disk I/O)
        self._cached_web_image_base64 = None  # Ready-to-emit data URI string
        self._cached_eink_image = None  # PIL Image for e-ink (avoids disk read-back)
        
        # 🚀 Pre-rendered next-block images (ready before block arrives)
        self._prerendered = {
            'block_height': None,        # Expected next block height
            'web_base64': None,          # Pre-rendered web image as base64 data URI
            'eink_img': None,            # Pre-rendered e-ink PIL Image
            'web_img': None,             # Pre-rendered web PIL Image (for disk save)
            'meme_path': None,           # Meme used in pre-render
            'displayed_blocks': None,    # Info blocks shown
            'mode_signature': None,      # Layout mode signature at pre-render time
            'timestamp': 0,              # When pre-rendered
            'lock': threading.Lock(),    # Prevent concurrent pre-renders
        }
        # Deferred disk persistence (batch writes instead of per-event)
        self._disk_save_pending = False
        self._last_disk_save_time = 0
        
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
        
        # Lightning donation state: latest + history (most recent first)
        self._donations_file = os.path.join("cache", "donations.json")
        self._latest_donation = None   # {amount_sats, message, timestamp}
        self._highest_donation = None  # donation with the highest amount_sats ever received
        self._donation_history = []    # list of {amount_sats, message, timestamp}, newest first
        # Block height at which the most-recent donation was received (used by "auto" display mode).
        self._latest_donation_block_height = None
        self._load_donations()
        # Webhook listener moved to _run_background_startup() to reduce CPU
        # contention on single-core Pi Zero during boot.

        # Block tracker for e-ink display race condition prevention
        self.block_tracker = {}
        
        # Persistent e-ink display worker (avoids ~10s Python startup per block)
        self._display_worker = None           # subprocess.Popen, kept alive
        self._display_worker_lock = threading.Lock()   # one display at a time
        self._display_worker_results = queue.Queue()   # stdout reader → caller

        # Flag: an e-ink refresh was requested while the display was busy (e.g. donation during block update)
        self._pending_eink_refresh = False

        # Image generation lock to prevent concurrent generation
        self.generation_lock = threading.Lock()
        
        # Block processing lock to prevent duplicate block processing
        self._block_processing_lock = threading.Lock()
        
        # 🚀 Pre-cached data for fast image generation (refreshed in background)
        self._precache = {
            'price_data': None,
            'bitaxe_data': None,
            'fee_data': None,  # Fee recommendations cache
            'block_height': None,  # Current block height cache
            'network_data': None,  # Network hashrate, difficulty, timeAvg
            'price_last_update': 0,
            'bitaxe_last_update': 0,
            'fee_last_update': 0,
            'network_last_update': 0,
            'last_price_value': None,  # Track last price to detect changes
            'last_bitaxe_blocks': None,  # Track last Bitaxe blocks to detect changes
            'last_fee_value': None,  # Track last fee to detect changes
            'last_hashrate': None,  # Track last hashrate to detect changes
            # Pre-selection for the next render (only used in prioritize_large_scaled_meme mode)
            'next_meme_path': None,       # Pre-selected meme for the upcoming render
            'selected_block_types': None, # Pre-selected info block types for that meme
            'lock': threading.Lock()
        }
        
        # Load persistent cache state from file
        self._load_cache_metadata()
        
        # Pre-cache updater moved to _run_background_startup() to reduce CPU
        # contention on single-core Pi Zero during boot.

        # Note: Configuration change callbacks registered at end of __init__
        
        # Setup Flask routes
        self._setup_routes()

        # Initialize websocket_client to None - will be set up in background
        self.websocket_client = None
        self._setup_instant_startup()

        # Register callbacks for configuration changes (done after all components are initialized)
        # _on_config_change must run BEFORE _on_config_file_changed so it can compare against
        # self.config (old value) before _on_config_file_changed overwrites it with the new config.
        self.config_manager.add_change_callback(self._on_config_change)
        self.config_manager.add_change_callback(self._on_config_file_changed)
        # On Windows, force config reload and callback notification after registering callbacks
        if os.name == 'nt':
            self.config_manager._reload_config_from_file()
            self.config_manager._notify_change_callbacks(self.config_manager.config)
        print("✅ Mempaper application initialized successfully")

    def _has_saved_wifi_connections(self):
        """Return True if NetworkManager has at least one saved Wi-Fi connection."""
        result = self._nmcli_read(['-t', '-f', 'TYPE', 'connection', 'show'])
        if result is None or result.returncode != 0:
            return False
        return any(line.strip() == 'wifi' for line in result.stdout.splitlines())

    def _startup_wifi_check(self):
        """Called once at startup.
                - If already connected: nothing to do.
                - If disconnected and no saved networks: start hotspot immediately.
                - If disconnected and saved networks exist: give NetworkManager a short
                    startup grace window to connect, then start hotspot if still offline.

        Includes retries with back-off because NetworkManager may not be fully
        ready right after boot on the Pi Zero W.
        """
        if os.name == 'nt':
            return
        if shutil.which('nmcli') is None:
            return

        # Wait for NetworkManager to become operational.  On the Pi Zero W it
        # can take 10-30s after systemd starts the service before nmcli
        # commands actually succeed.
        interface = None
        for wait in range(12):  # up to ~60s (0+1+2+...+10 ≈ 55s with sleeps)
            interface = self._detect_wifi_interface()
            if interface:
                # Verify NM is actually responding (not just that /sys/class/net exists)
                probe = self._nmcli_read(['-t', '-f', 'RUNNING', 'general', 'status'])
                if probe is not None and probe.returncode == 0:
                    break
            delay = min(wait + 1, 5)
            print(f'⏳ Waiting for NetworkManager to be ready (attempt {wait + 1}/12, retry in {delay}s)...')
            time.sleep(delay)
        else:
            print('⚠️ NetworkManager not ready after retries — will rely on recovery monitor')
            return

        # Remove any stale setup-hotspot profiles before checking connectivity —
        # an old autoconnect profile could mask a real outage or broadcast the
        # wrong SSID before the app had a chance to recreate it.
        self._cleanup_legacy_setup_hotspots()
        status = self._current_wifi_status(interface)
        if status.get('connected'):
            print('📡 Wi-Fi connected at startup — skipping setup hotspot')
            return

        has_saved = self._has_saved_wifi_connections()
        if not has_saved:
            # No saved Wi-Fi at all: factory / freshly-flashed device.
            print('📶 No saved Wi-Fi networks — starting setup hotspot for first-time provisioning')
            if not self._bring_up_setup_hotspot_with_retry(interface):
                self._write_setup_mode_flag(True, ssid=self._setup_ssid_from_mac(interface), interface=interface)
                print('⚠️ Hotspot failed at startup — recovery monitor will retry')
            return

        # Saved Wi-Fi exists but we are currently offline.
        startup_wait = int(self.config.get('wifi_startup_connect_wait_seconds', 45))
        startup_wait = max(0, startup_wait)
        poll_seconds = 5
        print(
            '📡 Saved Wi-Fi networks exist but not connected at startup — '
            f'waiting up to {startup_wait}s before enabling setup hotspot'
        )

        deadline = time.time() + startup_wait
        last_connect_try = 0.0
        while time.time() < deadline:
            now = time.time()
            if now - last_connect_try >= 10:
                last_connect_try = now
                self._nmcli(['device', 'connect', interface], timeout=20)

            probe = self._current_wifi_status(interface)
            if probe.get('connected'):
                print('✅ Wi-Fi connected during startup grace window')
                return
            time.sleep(poll_seconds)

        print('📶 Startup grace expired without Wi-Fi — enabling setup hotspot')
        if not self._bring_up_setup_hotspot_with_retry(interface):
            self._write_setup_mode_flag(True, ssid=self._setup_ssid_from_mac(interface), interface=interface)
            print('⚠️ Hotspot failed at startup — recovery monitor will retry')

    def _bring_up_setup_hotspot_with_retry(self, interface, max_attempts=4):
        """Try to bring up the setup hotspot with retries and back-off.

        NetworkManager can reject AP-mode activation right after boot if the
        Wi-Fi radio or driver isn't fully initialised yet.  Retrying after a
        short delay makes the first-boot experience much more reliable.
        """
        for attempt in range(1, max_attempts + 1):
            if self._bring_up_setup_hotspot(interface):
                return True
            if attempt < max_attempts:
                delay = attempt * 5  # 5s, 10s, 15s
                print(f'⚠️ Hotspot attempt {attempt}/{max_attempts} failed — retrying in {delay}s')
                time.sleep(delay)
        return False

    def _is_setup_mode_enabled(self):
        if not os.path.exists(self.setup_mode_flag_path):
            return False
        try:
            with open(self.setup_mode_flag_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return bool(data.get('enabled', False))
        except Exception:
            return False

    def _setup_mode_payload(self):
        payload = {
            'enabled': False,
            'ssid': 'mempaper-0000',
            'interface': 'wlan0',
        }
        if not os.path.exists(self.setup_mode_flag_path):
            return payload
        try:
            with open(self.setup_mode_flag_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                payload.update(data)
        except Exception:
            pass
        return payload

    def _perform_user_data_reset(self):
        """Clear admin credentials and all sensitive user data.

        Called from the setup-page reset button and from the multi-power-cycle
        factory reset path.  Reuses the same logic as delivery_state.py but
        runs inside the live app process.
        """
        # 1. Clear admin users (same keys as delivery_state.clear_admin_users)
        keys_to_remove = [
            'admin_users', 'admin_password_hash', 'admin_username',
            # Wallet / monitoring
            'wallet_balance_addresses_with_comments',
            'block_reward_addresses_table',
            # Bitaxe
            'bitaxe_miner_table',
            # Donation webhook
            'webhook_relay_ws_url',
            # Mempool auth
            'mempool_username',
            'mempool_password',
        ]

        full_cfg = self.config_manager.get_current_config()
        removed = [k for k in keys_to_remove if k in full_cfg]

        # Reset list/table fields to empty instead of deleting (keeps schema intact)
        list_fields = {
            'wallet_balance_addresses_with_comments': [],
            'block_reward_addresses_table': [],
            'bitaxe_miner_table': [],
        }
        for k in keys_to_remove:
            if k in list_fields:
                full_cfg[k] = list_fields[k]
            else:
                full_cfg.pop(k, None)

        # Also reset the show-* toggles so cleared blocks don't show empty
        full_cfg['show_wallet_balances_block'] = False
        full_cfg['show_bitaxe_block'] = False
        full_cfg['show_donation_block'] = False

        # Persist via secure config manager (handles encrypted fields)
        if self.config_manager.secure_manager:
            self.config_manager.secure_manager.save_secure_config(full_cfg)
        else:
            cfg_path = os.path.join('config', 'config.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(full_cfg, f, indent=2)

        # Update in-memory config
        for k in keys_to_remove:
            if k in list_fields:
                self.config[k] = list_fields[k]
                self.config_manager.config[k] = list_fields[k]
            else:
                self.config.pop(k, None)
                self.config_manager.config.pop(k, None)
        self.config['show_wallet_balances_block'] = False
        self.config['show_bitaxe_block'] = False
        self.config['show_donation_block'] = False

        # 2. Clear donation cache files
        for path in [self._donations_file,
                     os.path.join('cache', 'donations.json')]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self._latest_donation = None
        self._highest_donation = None
        self._donation_history = []

        # 3. Clear wallet / observer / secure caches
        for cache_file in ['cache/wallet_balances.json',
                           'cache/observer_cache.json',
                           'cache/bitaxe_cache.json',
                           'cache/async_wallet_address_cache.secure.json',
                           'cache/cache.secure.json',
                           'cache/mobile_tokens.secure.json',
                           'cache/mobile_tokens.json']:
            try:
                if os.path.exists(cache_file):
                    os.remove(cache_file)
            except OSError:
                pass

        if removed:
            print(f"🧹 Cleared sensitive data: {', '.join(removed)}")
        else:
            print("ℹ️ No sensitive data found to clear")

    def _write_setup_mode_flag(self, enabled, ssid=None, interface=None):
        try:
            os.makedirs(os.path.dirname(self.setup_mode_flag_path), exist_ok=True)
        except Exception:
            pass

        if not enabled:
            try:
                if os.path.exists(self.setup_mode_flag_path):
                    os.remove(self.setup_mode_flag_path)
            except OSError:
                pass
            return

        payload = {
            'enabled': True,
            'ssid': ssid,
            'interface': interface,
            'timestamp': int(time.time()),
        }
        try:
            with open(self.setup_mode_flag_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            print(f"⚠️ Could not write setup mode flag: {e}")

    def _detect_wifi_interface(self):
        result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status'])
        if result is not None and result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split(':')
                if len(parts) < 2:
                    continue
                device, dev_type = parts[0], parts[1]
                if device and dev_type == 'wifi':
                    return device

        preferred = '/sys/class/net/wlan0'
        if os.path.exists(preferred):
            return 'wlan0'

        net_root = '/sys/class/net'
        if not os.path.isdir(net_root):
            return 'wlan0'

        for iface in sorted(os.listdir(net_root)):
            if os.path.isdir(os.path.join(net_root, iface, 'wireless')):
                return iface
        return 'wlan0'

    def _has_ap_station(self, interface):
        """Return True if at least one client device is associated with our AP.

        Uses 'iw dev <iface> station dump' which lists connected stations.
        Falls back to False (allow probe) if iw is unavailable.
        """
        if shutil.which('iw') is None:
            return False
        try:
            result = subprocess.run(
                ['iw', 'dev', interface, 'station', 'dump'],
                capture_output=True, text=True, timeout=5,
            )
            # Any output means at least one station is associated
            return bool(result.returncode == 0 and result.stdout.strip())
        except Exception:
            return False

    def _nmcli(self, args, timeout=25):
        """Run nmcli with sudo for write operations (connection add/delete/up/down, radio)."""
        if shutil.which('nmcli') is None:
            return None
        # Use 'sudo nmcli' on Linux so the service user (non-root) can manage
        # NM connections.  The passwordless sudoers rule is installed by
        # scripts/install_wifi_permissions.sh.
        cmd = (['sudo', 'nmcli'] if os.name != 'nt' else ['nmcli']) + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

    def _nmcli_read(self, args, timeout=10):
        """Run nmcli without sudo for read-only queries (device status, connection list).

        Avoids PAM session logging that occurs with every sudo invocation.
        Plain nmcli is sufficient for status reads — no elevated privileges needed.
        """
        if shutil.which('nmcli') is None:
            return None
        try:
            return subprocess.run(
                ['nmcli'] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception:
            return None

    def _is_setup_hotspot_connection(self, connection_name):
        """Return True when the active connection is a setup hotspot profile."""
        conn = (connection_name or '').strip()
        if not conn:
            return False
        return conn == 'mempaper-setup' or conn.startswith('mempaper-setup_')

    def _cleanup_legacy_setup_hotspots(self, ssid=None):
        """Remove any setup-hotspot NM profiles (current or legacy naming, or matching SSID)."""
        result = self._nmcli_read(['-t', '-f', 'NAME,UUID,TYPE', 'connection', 'show'])
        if result is None or result.returncode != 0:
            return

        to_delete = []  # list of (name, uuid) tuples
        for line in result.stdout.splitlines():
            # Format: NAME:UUID:TYPE  — split on first 2 colons only so a
            # connection name containing ':' doesn't break the parse.
            parts = line.split(':', 2)
            if len(parts) < 3:
                continue
            name      = parts[0].strip()
            uuid      = parts[1].strip()
            conn_type = parts[2].strip()
            if conn_type != 'wifi':
                continue

            is_setup = (
                name == 'mempaper-setup'
                or name.startswith('mempaper-setup_')
                or name.startswith('mempaper-setup-')
                or name.startswith('mempaper-setup ')   # NM duplicate suffix "mempaper-setup 2" etc.
            )

            # Also match by SSID for profiles with unexpected names
            if not is_setup and ssid:
                detail = self._nmcli_read(['connection', 'show', uuid])
                if detail and detail.returncode == 0:
                    for prop in detail.stdout.splitlines():
                        if '802-11-wireless.ssid' in prop and ':' in prop:
                            if prop.split(':', 1)[1].strip() == ssid:
                                is_setup = True
                            break

            if is_setup:
                to_delete.append((name, uuid))

        for name, uuid in to_delete:
            # Delete by UUID — unambiguous even when multiple profiles share a name.
            self._nmcli(['connection', 'down', uuid])
            self._nmcli(['connection', 'delete', uuid])

    def _current_wifi_status(self, interface):
        result = self._nmcli_read(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
        if result is None or result.returncode != 0:
            return {'connected': False, 'connection': ''}

        for line in result.stdout.splitlines():
            parts = line.split(':')
            if len(parts) < 4:
                continue
            dev, dev_type, state, connection = parts[0], parts[1], parts[2], parts[3]
            if dev == interface and dev_type == 'wifi':
                connected = state.startswith('connected') and not self._is_setup_hotspot_connection(connection)
                return {'connected': connected, 'connection': connection}

        return {'connected': False, 'connection': ''}

    def _mac_digest(self, interface):
        """Return the hex SHA-256 digest of the interface MAC address."""
        mac_path = f'/sys/class/net/{interface}/address'
        mac_address = '00:00:00:00:00:00'
        try:
            with open(mac_path, 'r', encoding='utf-8') as f:
                mac_address = f.read().strip().lower()
        except OSError:
            pass
        return hashlib.sha256(mac_address.replace(':', '').encode('utf-8')).hexdigest()

    def _setup_ssid_from_mac(self, interface):
        digest = self._mac_digest(interface)
        suffix = f"{int(digest[:8], 16) % 10000:04d}"
        return f"mempaper-{suffix}"

    def _setup_password_from_mac(self, interface):
        """Derive a deterministic 8-char hex WPA2 password from the MAC address.

        Uses bytes 8-16 of the SHA-256 digest so the password is independent
        of the SSID suffix (bytes 0-8) and not guessable from the visible SSID.
        """
        digest = self._mac_digest(interface)
        return digest[8:16]   # 8 lowercase hex chars, always valid WPA2

    def _bring_up_setup_hotspot(self, interface):
        ssid     = self._setup_ssid_from_mac(interface)
        password = self._setup_password_from_mac(interface)
        print(f'📶 Setup hotspot: WPA2 AP "{ssid}" (password derived from device MAC)')

        # Aggressively remove every profile that could collide before adding a new one.
        self._cleanup_legacy_setup_hotspots(ssid=ssid)
        self._nmcli(['radio', 'wifi', 'on'])
        # Disconnect the interface from any active client connection so NM is
        # not fighting over wlan0 when we try to switch it to AP mode.
        self._nmcli(['device', 'disconnect', interface])

        # Create the base AP profile.  autoconnect=no prevents NM from activating
        # the incomplete profile between add and the security modify below.
        add = self._nmcli([
            'connection', 'add',
            'type', 'wifi',
            'ifname', interface,
            'con-name', 'mempaper-setup',
            'autoconnect', 'no',
            'ssid', ssid,
            '802-11-wireless.mode', 'ap',
            '802-11-wireless.band', 'bg',
            'ipv4.method', 'shared',
            'ipv6.method', 'ignore',
            'connection.autoconnect-priority', '-999',
        ])
        if add is None or add.returncode != 0:
            err = (add.stderr.strip() if add and add.stderr else '') or (add.stdout.strip() if add else 'no result')
            print(f'❌ Wi-Fi recovery: failed to create hotspot profile — {err}')
            return False

        # Apply WPA2-PSK security in a separate modify step.  Some NM versions
        # silently drop wifi-sec.* parameters when passed to connection add for
        # AP-mode connections; doing it via modify guarantees they are stored.
        sec = self._nmcli([
            'connection', 'modify', 'mempaper-setup',
            'wifi-sec.key-mgmt', 'wpa-psk',
            'wifi-sec.psk',      password,
            'wifi-sec.proto',    'rsn',   # WPA2 only (not WPA1)
            'wifi-sec.pairwise', 'ccmp',  # AES
            'wifi-sec.group',    'ccmp',  # AES
        ])
        if sec is None or sec.returncode != 0:
            err = (sec.stderr.strip() if sec and sec.stderr else '') or (sec.stdout.strip() if sec else 'no result')
            print(f'⚠️ Wi-Fi recovery: security modify warning — {err}')
            # Non-fatal: continue and try to bring up; NM may still apply WPA2

        up = self._nmcli(['connection', 'up', 'mempaper-setup'])
        if up is None or up.returncode != 0:
            err = (up.stderr.strip() if up and up.stderr else '') or (up.stdout.strip() if up else 'no result')
            print(f'❌ Wi-Fi recovery: failed to enable setup hotspot — {err}')
            return False

        # Redirect port 80/443 → Flask port so captive-portal probes
        # (which hit port 80) actually reach our /generate_204 handler.
        self._add_captive_portal_redirect(interface)

        self._write_setup_mode_flag(True, ssid=ssid, interface=interface)
        print(f"📶 Wi-Fi recovery: setup hotspot enabled ({ssid})")
        if self.e_ink_enabled and not self._onboarding_hotspot_screen_shown:
            self._onboarding_hotspot_screen_shown = True
            threading.Thread(
                target=self._display_onboarding_hotspot_screen,
                args=(ssid, password, interface),
                daemon=True,
            ).start()
        return True

    def _bring_down_setup_hotspot(self):
        self._onboarding_hotspot_screen_shown = False
        self._remove_captive_portal_redirect()
        self._cleanup_legacy_setup_hotspots()
        self._nmcli(['connection', 'down', 'mempaper-setup'])
        self._nmcli(['connection', 'delete', 'mempaper-setup'])
        self._write_setup_mode_flag(False)

    def _add_captive_portal_redirect(self, interface):
        """Add iptables PREROUTING rules to redirect port 80/443 → Flask port.

        Android (and some iOS) captive-portal probes hit port 80.  Without this
        redirect they get "connection refused" and the OS drops the network.
        """
        port = self._get_web_port()
        for src_port in (80, 443):
            try:
                subprocess.run(
                    ['sudo', 'iptables', '-t', 'nat', '-A', 'PREROUTING',
                     '-i', interface, '-p', 'tcp', '--dport', str(src_port),
                     '-j', 'REDIRECT', '--to-port', str(port)],
                    capture_output=True, timeout=10,
                )
            except Exception:
                pass
        print(f"🔀 Captive-portal redirect: ports 80/443 → {port}")

    def _remove_captive_portal_redirect(self):
        """Remove all mempaper captive-portal iptables PREROUTING rules."""
        port = self._get_web_port()
        for src_port in (80, 443):
            # Delete until no matching rule remains (handles duplicates)
            for _ in range(5):
                try:
                    result = subprocess.run(
                        ['sudo', 'iptables', '-t', 'nat', '-D', 'PREROUTING',
                         '-p', 'tcp', '--dport', str(src_port),
                         '-j', 'REDIRECT', '--to-port', str(port)],
                        capture_output=True, timeout=10,
                    )
                    if result.returncode != 0:
                        break
                except Exception:
                    break

    def _get_web_port(self):
        """Return the configured HTTP port (default 5000)."""
        return int(self.config.get('web_port', 5000))

    def _get_hotspot_ip(self, interface):
        """Detect the actual IP assigned to the hotspot AP interface.

        Tries (in order):
          1. nmcli connection show  — most reliable, uses the NM profile
          2. ip addr show <iface>   — works even without nmcli
          3. Fallback to 10.42.0.1 (NetworkManager shared default)
        """
        import re

        # 1. Ask NetworkManager for the address it handed to the profile.
        result = self._nmcli_read(['-t', '-f', 'IP4.ADDRESS', 'connection', 'show', 'mempaper-setup'])
        if result and result.returncode == 0:
            for line in result.stdout.splitlines():
                # format: IP4.ADDRESS[1]:10.42.0.1/24
                if 'IP4.ADDRESS' in line:
                    addr = line.split(':', 1)[-1].strip().split('/')[0]
                    if addr:
                        return addr

        # 2. Parse the kernel interface address.
        try:
            res = subprocess.run(
                ['ip', '-4', 'addr', 'show', interface],
                capture_output=True, text=True, timeout=5,
            )
            if res.returncode == 0:
                m = re.search(r'inet (\d+\.\d+\.\d+\.\d+)/', res.stdout)
                if m:
                    addr = m.group(1)
                    return addr
        except Exception:
            pass

        # 3. NetworkManager shared default.
        return '10.42.0.1'

    def _display_onboarding_hotspot_screen(self, ssid, password, interface):
        """Render the two-QR hotspot screen and push it to the e-ink display.

        Tries to stamp QR codes onto the existing delivery-state image so the
        onboarding screen shows the same meme/date as the delivery image.
        Falls back to the standalone onboarding screen if the delivery image
        is not available.
        """
        # Give NM a couple of seconds to finish assigning the AP address.
        time.sleep(2)
        port       = self._get_web_port()
        hotspot_ip = self._get_hotspot_ip(interface)
        portal_url = f'http://{hotspot_ip}:{port}/setup'
        try:
            delivery_eink = os.path.join('cache', 'delivery_eink.png')
            if os.path.exists(delivery_eink):
                from PIL import Image as _Image
                from lib.onboarding_renderer import stamp_qr_codes_on_image
                base_img = _Image.open(delivery_eink).convert('RGB')
                _, path = stamp_qr_codes_on_image(
                    base_img, ssid, password, portal_url, self.config,
                    eink=True)
            else:
                from lib.onboarding_renderer import render_hotspot_screen
                _, path = render_hotspot_screen(ssid, password, portal_url, self.config)
            if path:
                print(f'📺 Displaying hotspot onboarding screen on e-ink ({portal_url})')
                self._display_on_epaper_async(path, None, None)
        except Exception as e:
            print(f'⚠️ Could not render hotspot onboarding screen: {e}')

    def _display_onboarding_connected_screen(self):
        """Render the post-connection QR screen, display it, then restore normal
        operation after 60 seconds."""
        import socket as _socket

        # Suppress other e-ink updates while the connected screen is showing
        self._onboarding_connected_active = True

        # Give the OS a moment to assign an IP after the connection settles.
        time.sleep(3)

        ip = None
        for _ in range(5):
            try:
                s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
                s.settimeout(2)
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
                s.close()
                break
            except Exception:
                time.sleep(2)

        port       = self._get_web_port()
        access_url = f'http://{ip}:{port}' if ip else f'http://<pi-ip>:{port}'

        try:
            from lib.onboarding_renderer import render_connected_screen
            # Render e-ink version for the display
            eink_img, path = render_connected_screen(access_url, self.config, timeout_seconds=60,
                                                     translations=self.translations)
            if path:
                print(f'📺 Displaying connected onboarding screen on e-ink ({access_url})')
                self._display_on_epaper_async(path, None, None)

            # Render web version (same screen) and serve it as the dashboard image
            # so the browser shows the connected screen instead of a stale/broken template.
            try:
                web_img, _ = render_connected_screen(access_url, self.config, timeout_seconds=60,
                                                     eink=False, translations=self.translations)
                if web_img:
                    web_img.save(self.current_image_path)
                    self._cache_web_image(web_img)
                    print('📺 Connected screen also set as web dashboard image')
            except Exception:
                pass  # non-fatal — web image is cosmetic
        except Exception as e:
            print(f'⚠️ Could not render connected onboarding screen: {e}')
            return

        # Wait for the e-ink display to finish rendering (~40s) before starting
        # the 60-second countdown.  The display worker thread holds this lock
        # for the entire refresh duration; acquiring it here blocks until done.
        with self._display_worker_lock:
            pass  # lock released = display finished
        print('📺 Connected screen displayed on e-ink — starting 60s countdown')
        time.sleep(60)
        # After onboarding, always force a fresh image generation.
        # The cached image is likely stale (old block height, old language)
        # because it was rendered before the WiFi setup / language change.
        self._onboarding_connected_active = False
        try:
            print('⚙️ Onboarding complete — forcing fresh dashboard image generation')
            self.image_is_current = False
            self.last_eink_block_height = None
            self.last_eink_block_hash = None
            self._background_image_generation(force_eink=True)
        except Exception as e:
            print(f'⚠️ Could not generate fresh image after onboarding: {e}')

    def _start_wifi_recovery_monitor(self):
        if self._wifi_recovery_thread_started:
            return

        if os.name == 'nt':
            return

        enabled = bool(self.config.get('wifi_recovery_enabled', True))
        if not enabled:
            print('⚙️ Wi-Fi recovery monitor disabled in config')
            return

        if shutil.which('nmcli') is None:
            print('⚙️ Wi-Fi recovery monitor disabled (nmcli not available)')
            return

        self._wifi_recovery_thread_started = True

        def _loop():
            interface = self._detect_wifi_interface()
            poll_seconds = int(self.config.get('wifi_recovery_poll_seconds', 30))
            reconnect_interval_seconds = int(self.config.get('wifi_reconnect_interval_seconds', 60))
            setup_probe_interval_seconds = int(self.config.get('wifi_setup_probe_interval_seconds', 180))
            min_attempts = int(self.config.get('wifi_recovery_min_attempts', 10))
            outage_seconds = int(self.config.get('wifi_recovery_outage_seconds', 1800))
            startup_grace_seconds = int(self.config.get('wifi_recovery_startup_grace_seconds', 90))

            print(
                f"📡 Wi-Fi recovery monitor started on {interface} "
                f"(threshold: {outage_seconds}s + {min_attempts} attempts)"
            )

            while True:
                try:
                    now = time.time()
                    status = self._current_wifi_status(interface)
                    connected = bool(status.get('connected'))
                    active_connection = status.get('connection', '')

                    if connected:
                        self._wifi_disconnect_since = None
                        self._wifi_reconnect_attempts = 0
                        self._wifi_last_setup_probe_try = 0

                        if self._is_setup_mode_enabled():
                            print(f"✅ Wi-Fi recovered on {active_connection}; disabling setup hotspot")
                            self._bring_down_setup_hotspot()
                            # Wait for DHCP/DNS to settle before normal network operations resume.
                            print('⏳ Waiting 15s for DHCP/DNS to settle…')
                            time.sleep(15)

                        # When connected, poll slowly — no action needed until a drop occurs.
                        time.sleep(max(60, poll_seconds * 4))
                        continue

                    # Disconnected from normal Wi-Fi.
                    if self._wifi_disconnect_since is None:
                        self._wifi_disconnect_since = now
                        self._wifi_reconnect_attempts = 0
                        self._wifi_last_reconnect_try = 0
                        self._wifi_last_setup_probe_try = 0
                        print('⚠️ Wi-Fi disconnected, starting recovery attempts')

                    disconnected_for = now - self._wifi_disconnect_since

                    if self._is_setup_mode_enabled():
                        # If the setup flag is set but the hotspot is not actually broadcasting
                        # (e.g. NM rejected it at boot), bring it up unconditionally.
                        hotspot_actually_up = self._is_setup_hotspot_connection(active_connection)
                        if not hotspot_actually_up:
                            print('📶 Setup mode flagged but hotspot not active — bringing up')
                            self._bring_up_setup_hotspot(interface)
                            time.sleep(max(5, poll_seconds))
                            continue

                        # Immediate probe if user just submitted credentials via setup page.
                        pending = self._wifi_connect_pending
                        if pending:
                            self._wifi_connect_pending = False
                            self._wifi_last_setup_probe_try = 0  # force probe now

                        # Only do timed probes when no client is connected to the AP.
                        # Tearing down the hotspot while a phone is using it causes the
                        # phone to detect "no internet" and drop the connection.
                        has_ap_client = self._has_ap_station(interface)
                        if has_ap_client:
                            self._last_ap_station_seen_ts = now

                        # Grace window: treat the AP as occupied for N seconds after the
                        # phone was last seen — phones disassociate briefly when the screen
                        # goes off, which would otherwise trigger an immediate probe.
                        ap_client_grace = int(self.config.get('wifi_ap_client_grace_seconds', 120))
                        recently_had_client = (now - self._last_ap_station_seen_ts) < ap_client_grace

                        # Skip timed probes entirely when no saved client networks exist.
                        # There is nothing to connect to, so probing only disrupts the hotspot.
                        has_saved_networks = self._has_saved_wifi_connections()

                        if pending or (
                            has_saved_networks
                            and not has_ap_client
                            and not recently_had_client
                            and now - self._wifi_last_setup_probe_try >= setup_probe_interval_seconds
                        ):
                            self._wifi_last_setup_probe_try = now
                            self._nmcli(['connection', 'down', 'mempaper-setup'])
                            # Give NM a moment to free the radio before trying to connect
                            time.sleep(2)
                            reconnect = self._nmcli(['device', 'connect', interface], timeout=40)
                            if reconnect is not None and reconnect.returncode == 0:
                                # NM accepted the command — give it up to 15s to fully connect
                                for _ in range(5):
                                    time.sleep(3)
                                    probe_status = self._current_wifi_status(interface)
                                    if probe_status.get('connected'):
                                        print('✅ Wi-Fi recovered during setup mode probe; disabling setup hotspot')
                                        self._bring_down_setup_hotspot()
                                        # Wait for DHCP/DNS to fully settle before the app
                                        # starts using the network (WebSocket, API calls).
                                        print('⏳ Waiting 15s for DHCP/DNS to settle…')
                                        time.sleep(15)
                                        time.sleep(max(5, poll_seconds))
                                        break
                                else:
                                    self._bring_up_setup_hotspot(interface)
                                    self._wifi_last_setup_probe_try = now - setup_probe_interval_seconds + 30
                                continue
                            else:
                                # Back off shorter than full interval so we retry sooner
                                self._bring_up_setup_hotspot(interface)
                                self._wifi_last_setup_probe_try = now - setup_probe_interval_seconds + 20

                        time.sleep(max(5, poll_seconds))
                        continue

                    # Keep trying normal reconnection before entering setup mode.
                    if now - self._wifi_last_reconnect_try >= reconnect_interval_seconds:
                        self._wifi_last_reconnect_try = now
                        reconnect = self._nmcli(['device', 'connect', interface], timeout=20)
                        self._wifi_reconnect_attempts += 1
                        if reconnect is not None and reconnect.returncode == 0:
                            pass  # NM accepted reconnect; wait for next poll to confirm

                    # If there are no saved client networks there is nothing to reconnect to
                    # — start the setup hotspot as soon as the startup grace window has
                    # passed (no need to wait for the full outage threshold).
                    no_saved = not self._has_saved_wifi_connections()

                    # Conservative trigger: only after startup grace + sustained outage + repeated attempts.
                    if (
                        (now - self._startup_timestamp) >= startup_grace_seconds
                        and (
                            no_saved
                            or (
                                disconnected_for >= outage_seconds
                                and self._wifi_reconnect_attempts >= min_attempts
                            )
                        )
                    ):
                        reason = 'no saved networks' if no_saved else f'offline {int(disconnected_for)}s, attempts {self._wifi_reconnect_attempts}'
                        print(f'📶 Wi-Fi recovery threshold reached; switching to setup hotspot ({reason})')
                        self._bring_up_setup_hotspot(interface)

                    time.sleep(max(5, poll_seconds))
                except Exception as e:
                    print(f"⚠️ Wi-Fi recovery monitor error: {e}")
                    time.sleep(30)

        threading.Thread(target=_loop, name='wifi-recovery-monitor', daemon=True).start()

    def _get_prerender_mode_signature(self):
        """Return the pre-render compatibility signature for layout-sensitive settings."""
        return {
            "prioritize_large_scaled_meme": bool(self.config.get("prioritize_large_scaled_meme", False)),
        }
    
    def _init_api_clients(self):
        # Mempool API setup with HTTPS support
        mempool_host = self.config.get("mempool_host", "127.0.0.1")
        mempool_rest_port = self.config.get("mempool_rest_port", "4081")
        mempool_use_https = self.config.get("mempool_use_https", False)
        mempool_verify_ssl = self.config.get("mempool_verify_ssl", True)
        mempool_username = self.config.get("mempool_username", "")
        mempool_password = self.config.get("mempool_password", "")
        
        if not hasattr(self, '_api_clients_initialized'):
            print(f"🌐 Mempool API: {build_mempool_api_url(mempool_host, mempool_rest_port, mempool_use_https)}")
            self._api_clients_initialized = True
        
        self.mempool_api = MempoolAPI(
            host=mempool_host,
            port=mempool_rest_port,
            use_https=mempool_use_https,
            verify_ssl=mempool_verify_ssl,
            username=mempool_username or None,
            password=mempool_password or None
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
        mempool_username = self.config.get("mempool_username", "")
        mempool_password = self.config.get("mempool_password", "")
        
        # WebSocket URL already logged by block_monitor
        
        # Create WebSocket client with proper protocol and path
        self.websocket_client = MempoolWebSocket(
            host=mempool_host,
            port=mempool_ws_port,
            path=mempool_ws_path,
            use_wss=mempool_use_https,  # Use WSS if HTTPS is enabled
            on_new_block_callback=self.on_new_block_received,
            verify_ssl=mempool_verify_ssl,
            username=mempool_username or None,
            password=mempool_password or None
        )
        
        # Configure network outage tolerance (how long to retry before giving up)
        network_outage_tolerance_minutes = self.config.get("network_outage_tolerance_minutes", 45)  # Default 45 minutes
        self.websocket_client.set_network_tolerance(max_outage_minutes=network_outage_tolerance_minutes)
        
        # Connection details logged by websocket_client and block_monitor
    
    def _load_donations(self):
        """Load persisted donation history from disk on startup."""
        try:
            if os.path.exists(self._donations_file):
                with open(self._donations_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._donation_history = data.get("history", [])
                self._latest_donation = self._donation_history[0] if self._donation_history else None
                if self._donation_history:
                    self._highest_donation = None
                    for d in reversed(self._donation_history):
                        if (self._highest_donation is None or
                                d.get("amount_sats", 0) > self._highest_donation.get("amount_sats", 0)):
                            self._highest_donation = d
                self._latest_donation_block_height = data.get("latest_donation_block_height", None)
                print(f"⚡ Loaded {len(self._donation_history)} donation(s) from {self._donations_file}")
        except Exception as e:
            print(f"⚠️ Could not load donations file: {e}")

    def _get_active_donation(self):
        """Return the donation to display based on donation_display_mode config.

        Modes:
          latest  — always show the most-recent donation.
          highest — always show the all-time largest donation.
          auto    — show latest for 432 blocks after the last donation; fall back
                    to highest when 432 blocks have passed without a new donation.

        The returned dict always includes:
          _guaranteed — True for the first 144 blocks after the latest donation
                        (renderer pre-reserves space and shows unconditionally).
                        False afterwards (block competes with others for space).
        """
        mode = self.config.get("donation_display_mode", "latest")

        # Within 144 blocks (~24h) of the last received donation: guarantee display
        guaranteed = False
        if (self._latest_donation is not None
                and self._latest_donation_block_height is not None
                and self.current_block_height is not None):
            try:
                blocks_since = int(self.current_block_height) - int(self._latest_donation_block_height)
                guaranteed = blocks_since <= 144
            except (TypeError, ValueError):
                guaranteed = True  # safe default when comparison fails

        def _tag(d):
            if d is None:
                return None
            d = dict(d)
            d["_guaranteed"] = guaranteed
            return d

        if mode == "highest":
            return _tag(self._highest_donation)
        if mode == "auto":
            if self._latest_donation is None:
                d = self._highest_donation
                effective = "highest"
            else:
                donation_bh = self._latest_donation_block_height
                current_bh = self.current_block_height
                if donation_bh is None or current_bh is None:
                    d = self._latest_donation
                    effective = "latest"
                else:
                    try:
                        blocks_since = int(current_bh) - int(donation_bh)
                    except (TypeError, ValueError):
                        d = self._latest_donation
                        effective = "latest"
                    else:
                        if blocks_since <= 432:
                            d = self._latest_donation
                            effective = "latest"
                        else:
                            d = self._highest_donation
                            effective = "highest"
            if d is not None:
                d = dict(d)
                d["_effective_mode"] = effective
                d["_guaranteed"] = guaranteed
            return d
        # default: "latest"
        return _tag(self._latest_donation)

    def _save_donations(self):
        """Persist donation history to disk."""
        try:
            os.makedirs(os.path.dirname(self._donations_file), exist_ok=True)
            with open(self._donations_file, "w", encoding="utf-8") as f:
                json.dump({
                    "history": self._donation_history,
                    "latest_donation_block_height": self._latest_donation_block_height,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save donations file: {e}")

    def _process_donation_payload(self, data: dict):
        """Parse a raw LNbits payment payload and trigger display + socket updates."""
        from datetime import datetime as _dt

        # LNbits sends amount in millisatoshis.
        # For LNURL-pay the user's comment is in extra.comment (not memo).
        amount_msats = data.get("amount", 0)
        amount_sats = max(1, round(amount_msats / 1000)) if amount_msats else 0
        extra = data.get("extra") or {}
        message = (
            extra.get("comment")
            or extra.get("description")
            or data.get("memo")
            or data.get("comment")
            or ""
        ).strip()

        donation = {
            "amount_sats": amount_sats,
            "message": message,
            "timestamp": _dt.utcnow().isoformat(),
        }
        self._latest_donation = donation
        self._donation_history.insert(0, donation)
        if (self._highest_donation is None or
                amount_sats > self._highest_donation.get("amount_sats", 0)):
            self._highest_donation = donation
        # Record block height for the "auto" display-mode countdown.
        self._latest_donation_block_height = self.current_block_height
        self._save_donations()

        print(f"⚡ Donation received: {amount_sats} sats — \"{message}\" (block height: {self._latest_donation_block_height})")

        if self.socketio:
            self.socketio.emit('donation_received', donation, room='authenticated')

        # Refresh the display if the donation block is enabled
        if self.config.get("show_donation_block", False):
            self.image_renderer._donation_data = self._get_active_donation()
            self.image_is_current = False
            # Invalidate pre-render so next block shows updated donation
            self._invalidate_prerender()
            threading.Thread(
                target=self._background_image_generation,
                kwargs={"force_eink": True, "use_cached_block": True, "force_new_meme": True},
                daemon=True
            ).start()

    def _start_webhook_site_listener(self):
        """Start a background thread that connects to a webhook relay via WebSocket.

        The thread reconnects automatically with exponential back-off whenever
        the connection drops.  Call _restart_webhook_site_listener() to force an
        immediate reconnect with a new URL (e.g. after config change).
        """
        import websocket as _ws

        self._webhook_site_wake = threading.Event()  # set to interrupt sleep
        self._webhook_site_ws = None                 # current WebSocketApp (for close on restart)

        def _run():
            backoff = 5
            while True:
                self._webhook_site_wake.clear()
                url = self.config.get("webhook_relay_ws_url", "").strip()
                if not url:
                    # No URL — wait up to 30 s or until woken by a config change
                    self._webhook_site_wake.wait(timeout=30)
                    continue

                print(f"⚡ webhook relay listener: connecting to {url}")

                def _on_message(ws, raw):
                    try:
                        outer = json.loads(raw)
                        # Check for payload field first (webhook relay format), then content/body
                        data = outer.get("payload")
                        if not data:
                            content = outer.get("content") or outer.get("body") or ""
                            data = json.loads(content) if content and isinstance(content, str) else content
                        print(f"⚡ webhook relay event — data: {str(data)[:300]!r}")
                        self._process_donation_payload(data)
                    except Exception as e:
                        print(f"⚠️ webhook relay parse error: {e} — raw: {raw[:200]!r}")

                def _on_open(ws):
                    backoff_ref[0] = 5  # reset back-off on successful connect
                    print("✅ webhook relay WebSocket connected")

                def _on_error(ws, err):
                    print(f"⚠️ webhook relay WebSocket error: {err}")

                def _on_close(ws, code, msg):
                    print(f"⚡ webhook relay WebSocket closed (code={code})")

                backoff_ref = [backoff]
                try:
                    ws = _ws.WebSocketApp(
                        url,
                        on_open=_on_open,
                        on_message=_on_message,
                        on_error=_on_error,
                        on_close=_on_close,
                    )
                    self._webhook_site_ws = ws
                    ws.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as e:
                    print(f"⚠️ webhook relay listener exception: {e}")
                finally:
                    self._webhook_site_ws = None

                backoff = backoff_ref[0]
                # Wait before reconnecting, but allow early wake on URL change
                print(f"⚡ webhook relay listener: reconnecting in {backoff} s…")
                self._webhook_site_wake.wait(timeout=backoff)
                backoff = min(backoff * 2, 60)

        threading.Thread(target=_run, name="webhook-relay-listener", daemon=True).start()
        print("⚡ webhook relay listener thread started")

    def _restart_webhook_site_listener(self):
        """Force an immediate reconnect (e.g. after the WebSocket URL changes in config)."""
        ws = getattr(self, '_webhook_site_ws', None)
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        wake = getattr(self, '_webhook_site_wake', None)
        if wake:
            wake.set()  # interrupt any sleep

    def _generate_initial_image(self):
        """Generate initial dashboard image on startup - optimized for fast start."""
        
        # FIRST: Check if wallet monitoring is enabled
        from managers.config_manager import ConfigManager
        config_manager = ConfigManager()
        
        wallet_monitoring_enabled = config_manager.get("show_wallet_balances_block", True)
        
        if wallet_monitoring_enabled:
            # Check if wallet bootstrap is needed at startup - smart cache-based decision
            try:
                # Get wallet addresses from modern table format
                wallet_addresses = config_manager.get("wallet_balance_addresses_with_comments", [])
                
                extended_keys = []
                
                for entry in wallet_addresses:
                    if isinstance(entry, dict):
                        address = entry.get("address", "")
                    else:
                        address = str(entry)
                    
                    # Check if it's an extended key (XPUB/ZPUB are typically 100+ characters)
                    if len(address) > 50 and (address.lower().startswith(('xpub', 'zpub', 'ypub'))):
                        extended_keys.append(address)
                
                if not wallet_addresses or not extended_keys:
                    pass  # No extended keys - no bootstrap needed
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
            print(f"⚙️ Generating initial dashboard image with cached data...")
            
            # Get current block info from mempool API
            try:
                block_info = self.mempool_api.get_current_block_info()
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
                      override_meme = potential_meme

            # Sync latest donation data to renderer
            self.image_renderer._donation_data = self._get_active_donation()

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
            
            # Cache in RAM for instant web serving, save to disk for persistence
            self._cache_web_image(web_img)
            self._cached_eink_image = eink_img
            self._save_images_to_disk(web_img, eink_img)
            
            # Update cache state
            self.current_block_height = block_info['block_height']
            self.current_block_hash = block_info['block_hash']
            self.current_meme_path = meme_path  # Cache the selected meme
            self.image_is_current = True
            
            # Save persistent cache metadata
            self._save_cache_metadata()
            
            print("✅ Initial dashboard image generated and cached")
            
            # ASYNC WALLET REFRESH: Update wallet balances in background and regenerate if changed
            threading.Thread(
                target=self._async_wallet_refresh_and_regenerate,
                args=(block_info['block_height'], block_info['block_hash']),
                daemon=True
            ).start()
            
            # Display on e-Paper in background thread (don't block startup)
            if self.e_ink_enabled:
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                    daemon=True
                ).start()
            
            # Pre-render next block in background
            threading.Thread(target=self._prerender_next_block, daemon=True).start()
            
        except Exception as e:
            print(f"⚠️ Failed to generate initial image: {e}")
            print("   Image will be generated on first user request")
    
    def _async_wallet_refresh_and_regenerate(self, block_height: int, block_hash: str):
        """
        Async method to refresh wallet balances and regenerate image if balance changed.
        This provides optimal UX by serving cached data immediately, then updating if needed.
        """
        try:
            # Get cached wallet data for comparison
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
            cached_balance = cached_wallet_data.get('total_btc', 0) if cached_wallet_data else 0
            
            # Fetch fresh wallet balances (this might take time for XPUB derivation)
            fresh_wallet_data = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=False, current_block=block_height)
            
            if fresh_wallet_data and not fresh_wallet_data.get('error'):
                fresh_balance = fresh_wallet_data.get('total_btc', 0)
                
                # Compare balances (use small epsilon for floating point comparison)
                balance_changed = abs(fresh_balance - cached_balance) > 0.00000001  # 1 satoshi precision
                
                if balance_changed:
                    print(f"⚙️ [ASYNC-REFRESH] Balance changed: {cached_balance:.8f} → {fresh_balance:.8f} BTC - regenerating")
                    
                    # Update cache with fresh data BEFORE regenerating
                    self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                    
                    # Regenerate image (will use the just-updated cache via startup_mode=True)
                    self._generate_new_image(
                        block_height, 
                        block_hash, 
                        skip_epaper=False,
                        use_new_meme=False
                    )
                    return
                
                # Update cache with fresh timestamp and fiat values even if BTC balance unchanged
                self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
                
            else:
                error_msg = fresh_wallet_data.get('error', 'Unknown error') if fresh_wallet_data else 'No data returned'
                print(f"⚠️ [ASYNC-REFRESH] Failed to fetch fresh wallet data: {error_msg}")
                
        except Exception as e:
            print(f"❌ [ASYNC-REFRESH] Error during async wallet refresh: {e}")
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
        
        # Warm up Bitaxe API only when Bitaxe block is actually enabled for display.
        bitaxe_ip = self.config.get("bitaxe_ip", "")
        show_bitaxe_block = self.config.get("show_bitaxe_block", True)
        bitaxe_enabled = self.config.get("bitaxe_enabled", True)
        if show_bitaxe_block and bitaxe_enabled and bitaxe_ip and bitaxe_ip != "192.168.1.1":
            try:
                bitaxe_data = self.image_renderer.fetch_bitaxe_stats()
                # Silently warm up - only log errors
                if not bitaxe_data or bitaxe_data.get("error"):
                    print("⚠️ Bitaxe API warm-up returned no data (may work on retry)")
            except Exception as e:
                print(f"⚠️ Bitaxe API warm-up failed: {e}")

    # ── Multi-power-cycle factory reset detection ─────────────────────────────
    BOOT_TIMESTAMPS_PATH = os.path.join('cache', 'boot_timestamps.json')
    POWER_CYCLE_RESET_THRESHOLD = 3   # number of boots within the window
    POWER_CYCLE_RESET_WINDOW = 900    # seconds (15 minutes — 3 cycles × ~3.5 min + 4th boot)

    def _check_power_cycle_reset(self):
        """Detect rapid power-cycling (3 boots in 10 min) and trigger factory reset.

        On each startup the current timestamp is appended to a small JSON file.
        If the file already contains enough recent timestamps, a full factory
        reset is triggered: admin + sensitive data cleared, saved WiFi profiles
        deleted, and the delivery-state e-ink image rendered.

        Returns True if a reset was triggered (caller should skip normal startup).
        """
        now = time.time()
        timestamps = []

        # Log system uptime so we know exactly how long from power-on to this point.
        # Only count as a power-cycle boot if uptime is low (< 5 min).
        # A service restart (systemctl restart) won't reset system uptime,
        # so it will be ignored and not count towards the reset threshold.
        uptime_seconds = None
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
            print(f'⏱️ System uptime at boot timestamp write: {uptime_seconds:.1f}s '
                  f'— safe to power off after this point')
        except (OSError, ValueError, IndexError):
            pass  # Not on Linux (dev machine)

        max_boot_uptime = 300  # 5 minutes — cold boot on Pi Zero takes ~80-120s
        if uptime_seconds is not None and uptime_seconds > max_boot_uptime:
            print(f'🔄 Power-cycle reset check: skipped (uptime {uptime_seconds:.0f}s > {max_boot_uptime}s — '
                  f'this is a service restart, not a cold boot)')
            return False

        # Load existing boot timestamps
        try:
            if os.path.exists(self.BOOT_TIMESTAMPS_PATH):
                with open(self.BOOT_TIMESTAMPS_PATH, 'r', encoding='utf-8') as f:
                    timestamps = json.load(f)
                if not isinstance(timestamps, list):
                    timestamps = []
        except (json.JSONDecodeError, OSError):
            timestamps = []

        # Keep only timestamps within the detection window
        timestamps = [ts for ts in timestamps if (now - ts) < self.POWER_CYCLE_RESET_WINDOW]
        timestamps.append(now)

        # Persist updated timestamps and force filesystem sync so the data
        # survives the next hard power-off without corrupting the SD card.
        try:
            os.makedirs(os.path.dirname(self.BOOT_TIMESTAMPS_PATH), exist_ok=True)
            with open(self.BOOT_TIMESTAMPS_PATH, 'w', encoding='utf-8') as f:
                json.dump(timestamps, f)
                f.flush()
                os.fsync(f.fileno())
            os.sync()  # flush all pending filesystem writes to SD card
        except OSError:
            pass

        print(f'🔄 Power-cycle reset check: {len(timestamps)}/{self.POWER_CYCLE_RESET_THRESHOLD} '
              f'boots in {self.POWER_CYCLE_RESET_WINDOW}s window')

        if len(timestamps) >= self.POWER_CYCLE_RESET_THRESHOLD:
            print(f'🔄 Power-cycle reset detected! ({len(timestamps)} boots in {self.POWER_CYCLE_RESET_WINDOW}s window)')
            print('🔄 Triggering factory reset...')

            # Clear the timestamps file so the next boot is clean
            try:
                os.remove(self.BOOT_TIMESTAMPS_PATH)
            except OSError:
                pass

            # Caller runs _execute_factory_reset() synchronously so WiFi
            # profiles are deleted before the WiFi check thread starts.
            return True

        return False

    def _execute_factory_reset(self):
        """Full factory reset: clear data, delete WiFi, render delivery image.

        Runs in a background thread because the delivery-state image render
        and e-ink display update take ~40-60 seconds.
        """
        try:
            # 1. Clear admin + sensitive user data
            print('🧹 Factory reset: clearing user data...')
            self._perform_user_data_reset()

            # 2. Clear saved WiFi profiles using the app's own nmcli wrapper
            #    (delivery_state's nmcli_cmd has different sudo handling that
            #    may silently fail inside the running service)
            print('🧹 Factory reset: clearing saved WiFi profiles...')
            self._factory_reset_clear_wifi()

            # 3. Render the delivery-state image and push via the app's display worker
            print('🎨 Factory reset: rendering delivery state image...')
            try:
                import scripts.delivery_state as ds
                config = self.config_manager.get_current_config()
                image_path = ds.render_delivery_image(config)
                # Use the app's own display worker (not ds.show_on_eink) to avoid
                # GPIO conflicts with the already-running display subprocess.
                if self.e_ink_enabled:
                    print('🖥️ Factory reset: pushing delivery image to e-ink...')
                    self._display_on_epaper_async(image_path, None, None)
            except Exception as e:
                print(f'⚠️ Could not render delivery image: {e}')

            print('✅ Factory reset complete. Device is in delivery state.')

        except Exception as e:
            print(f'❌ Factory reset failed: {e}')
            import traceback
            traceback.print_exc()

    def _factory_reset_clear_wifi(self):
        """Delete all saved client WiFi profiles.

        Uses 'sudo nmcli' for both listing and deleting because system-owned
        WiFi connections (created via 'sudo nmcli device wifi connect') are
        not visible to unprivileged nmcli queries.
        """
        try:
            # Must use sudo to see system-owned connections
            result = self._nmcli(['-t', '-f', 'NAME,TYPE', 'connection', 'show'])
            if result is None:
                print('⚠️ WiFi cleanup: nmcli command failed to execute')
                return
            if result.returncode != 0:
                print(f'⚠️ WiFi cleanup: nmcli list failed: {(result.stderr or result.stdout or "").strip()}')
                return

            print(f'🔍 WiFi cleanup: nmcli output: {result.stdout.strip()!r}')

            deleted = []
            failed = []
            for line in result.stdout.splitlines():
                parts = line.strip().split(':', 1)
                if len(parts) < 2:
                    continue
                name, conn_type = parts[0], parts[1]
                if conn_type not in ('wifi', '802-11-wireless'):
                    continue
                if name.startswith('mempaper-setup'):
                    continue
                print(f'🧹 Deleting WiFi profile: {name}')
                r = self._nmcli(['connection', 'delete', name])
                if r is not None and r.returncode == 0:
                    deleted.append(name)
                else:
                    err = (r.stderr or r.stdout or '').strip() if r else 'no result'
                    failed.append(f'{name}: {err}')
                    print(f'⚠️ Failed to delete WiFi profile {name}: {err}')

            if deleted:
                print(f'🧹 Deleted {len(deleted)} WiFi profile(s): {", ".join(deleted)}')
            elif not failed:
                print('ℹ️ No saved WiFi profiles to delete')
        except Exception as e:
            print(f'⚠️ WiFi cleanup failed: {e}')
            import traceback
            traceback.print_exc()

    def _setup_instant_startup(self):
        """
        Setup instant startup mode:
        1. Check for power-cycle factory reset
        2. Load cached/default image immediately
        3. Start heavy operations in background
        4. Update interface when ready
        """

        # Check for multi-power-cycle reset FIRST (before anything else).
        # If triggered, run synchronously so WiFi profiles are deleted BEFORE
        # the WiFi check thread tries to connect to them.
        factory_reset_triggered = False
        if os.name != 'nt':  # Only on Linux/Pi, not Windows dev
            if self._check_power_cycle_reset():
                factory_reset_triggered = True
                self._execute_factory_reset()

        # Check if we have a cached image to show immediately
        has_cached_image = (os.path.exists(self.current_image_path) and
                           os.path.exists(self.current_eink_image_path))

        if has_cached_image and not factory_reset_triggered:
            cache_age = (time.time() - os.path.getmtime(self.current_image_path)) / 60
            print(f"💾 Found cached image (age: {cache_age:.1f} minutes)")
            # Image metadata already loaded in _load_cache_metadata()
        else:
            print("💾 No cached image found - will create placeholder")
            self._create_placeholder_image()

        # Start Wi-Fi check immediately in a separate thread so the hotspot
        # comes up as fast as possible (critical for first-boot / delivery reset).
        threading.Thread(target=self._startup_wifi_check, daemon=True).start()

        # Start remaining background processing after a minimal delay
        background_delay = self.config.get("background_processing_delay", 0.5)
        threading.Timer(background_delay, self._run_background_startup).start()
        print("🌐 Website is now ready!")

    def _create_placeholder_image(self):
        """Create a simple placeholder image for instant startup."""
        try:
            from PIL import Image, ImageDraw, ImageFont

            # Use configured display dimensions, respecting orientation
            display_w = self.config.get("display_width", 800)
            display_h = self.config.get("display_height", 480)
            if self.config.get("web_orientation", "vertical") == "vertical":
                width, height = min(display_w, display_h), max(display_w, display_h)
            else:
                width, height = max(display_w, display_h), min(display_w, display_h)
            # Use background color that respects dark mode setting
            is_dark_mode = self.config.get("color_mode_dark", False)
            bg_color = (46, 50, 78) if is_dark_mode else (255, 255, 255)  # Dark: #2e324e, Light: white
            text_color = (255, 255, 255) if is_dark_mode else (0, 0, 0)  # White text for dark, black for light
            
            img = Image.new('RGB', (width, height), color=bg_color)
            draw = ImageDraw.Draw(img)
            
            # Try to use the configured font, fallback to default
            unicode_fonts = True
            try:
                font_path = self.config.get("font_bold", "static/fonts/Roboto-Bold.ttf")
                font = ImageFont.truetype(font_path, 48)
                medium_font = ImageFont.truetype(font_path, 32)
                small_font = ImageFont.truetype(font_path, 24)
            except:
                font = ImageFont.load_default()
                medium_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
                unicode_fonts = False

            # Draw main title
            title = "mempaper"
            bbox = draw.textbbox((0, 0), title, font=medium_font)
            title_width = bbox[2] - bbox[0]
            title_x = (width - title_width) // 2
            title_y = 120
            draw.text((title_x, title_y), title, fill=text_color, font=medium_font)
            
            # Draw loading message
            loading_msg = self.translations.get("loading_bitcoin_data", "Loading Bitcoin data...")
            bbox = draw.textbbox((0, 0), loading_msg, font=small_font)
            loading_width = bbox[2] - bbox[0]
            loading_x = (width - loading_width) // 2
            loading_y = title_y + 60
            gray_text = (160, 160, 160) if is_dark_mode else (128, 128, 128)
            draw.text((loading_x, loading_y), loading_msg, fill=gray_text, font=small_font)
            
            # Draw progress dots (ASCII-safe)
            progress_msg = ". . . ."
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
            bottom_gray = (140, 140, 140) if is_dark_mode else (102, 102, 102)
            draw.text((bottom_x, bottom_y), bottom_msg, fill=bottom_gray, font=small_font)
            
            # Cache placeholder in RAM and save to disk
            self._cache_web_image(img)
            self._cached_eink_image = img
            self._save_images_to_disk(img, img)
            
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

            # Wi-Fi check already started in _setup_instant_startup() thread.
            # Start Wi-Fi recovery monitor early so network failures can self-heal.
            self._start_wifi_recovery_monitor()

            # Start deferred init tasks that were moved out of __init__ to
            # reduce boot time (network calls, CPU-heavy threads).
            self._start_webhook_site_listener()
            self._start_precache_updater()

            # Check block height now (moved from __init__ to avoid 10s+ timeout when offline)
            try:
                block_info = self.mempool_api.get_current_block_info()
                current_bh = str(block_info.get('block_height', ''))
                cached_bh = str(self.current_block_height) if self.current_block_height is not None else None

                if cached_bh and current_bh and cached_bh != current_bh:
                    print(f"⚙️ [STARTUP] Block changed since last run: {cached_bh} -> {current_bh}")
                    self.current_block_height = block_info.get('block_height')
                    self.current_block_hash = block_info.get('block_hash')
                    self.image_is_current = False
                elif cached_bh and current_bh and cached_bh == current_bh:
                    print(f"[STARTUP] Block unchanged: {current_bh} - cache is valid")
                    self.image_is_current = True
            except Exception as e:
                print(f"[STARTUP] Failed to check current block: {e}")
                self.image_is_current = False

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
            self._init_websocket()
            
            # Warm up APIs
            self._warm_up_apis()
            
            # If blocks were missed during downtime, regenerate now that APIs are warmed up
            if not self.image_is_current and self.current_block_height and self.current_block_hash:
                print(f"⚙️ Image outdated at startup — regenerating for block {self.current_block_height}...")
                self._generate_new_image(
                    self.current_block_height,
                    self.current_block_hash,
                    use_new_meme=True
                )

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
        """Display image on e-Paper via persistent worker process."""
        import subprocess
        import sys

        # Skip immediately if this block is already superseded
        if block_height:
            current_block = getattr(self, 'current_block_height', 0) or 0
            if int(block_height) < int(current_block):
                print(f"⏭️ Skipping e-paper display for old block {block_height} (current: {current_block})")
                return

        def display_in_worker():
            display_start = time.time()
            print(f"⚙️ Starting e-paper display for block {block_height} at {time.strftime('%H:%M:%S')}")

            with self._display_worker_lock:
                try:
                    worker = self._get_or_start_display_worker()
                except Exception as e:
                    print(f"❌ Could not start display worker: {e}")
                    self._emit_display_error(str(e))
                    return

                try:
                    worker.stdin.write(json.dumps({"image_path": image_path}) + "\n")
                    worker.stdin.flush()
                except Exception as e:
                    print(f"❌ Failed to send command to display worker: {e}")
                    self._display_worker = None  # force restart next time
                    self._emit_display_error(str(e))
                    return

                try:
                    result = self._display_worker_results.get(timeout=120)
                except queue.Empty:
                    device_name = self.config.get("omni_device_name", "unknown")
                    print(f"❌ E-paper display timed out after 120s")
                    print(f"   The selected display driver '{device_name}' may be incorrect.")
                    print(f"   Run: python scripts/configure_display.py")
                    self._display_worker = None  # worker may be stuck; restart next time
                    self._emit_display_error(
                        f'Display timed out after 120s. The driver "{device_name}" may be incorrect. '
                        f'Check Settings → Display.'
                    )
                    return

            display_duration = time.time() - display_start

            if result.get("worker_died"):
                print(f"❌ Display worker died unexpectedly")
                self._display_worker = None
                self._emit_display_error("Worker process died")
                return

            if result.get("success"):
                print(f"✅ E-paper display completed in {display_duration:.2f}s")

                # Warn if display refresh took abnormally long (likely wrong driver)
                if display_duration > 80:
                    device_name = self.config.get("omni_device_name", "unknown")
                    print(f"⚠️ Display refresh took {display_duration:.0f}s — this is unusually slow.")
                    print(f"   The selected display driver '{device_name}' may be incorrect.")
                    print(f"   Run: python scripts/configure_display.py")
                    if hasattr(self, 'socketio') and self.socketio:
                        self.socketio.emit('display_update', {
                            'status': 'warning',
                            'message': f'Display refresh took {display_duration:.0f}s (expected ~40s). '
                                       f'The display driver "{device_name}" may be incorrect. '
                                       f'Check Settings → Display.',
                            'block_height': block_height,
                            'timestamp': time.time()
                        })

                # Update block tracking if this result is still current
                if block_height and block_hash:
                    current_height = getattr(self, 'last_eink_block_height', 0) or 0
                    latest_block = getattr(self, 'current_block_height', 0) or 0
                    if int(block_height) >= int(current_height):
                        self.last_eink_block_height = block_height
                        self.last_eink_block_hash = block_hash
                        # Only log if this is actually the latest block (avoid confusion)
                        if int(block_height) >= int(latest_block):
                            print(f"💾 E-ink display tracking updated: Block {block_height}")

                # Execute any refresh that was queued while we were busy
                if getattr(self, '_pending_eink_refresh', False):
                    self._pending_eink_refresh = False
                    print(f"📌 Executing pending e-ink refresh...")
                    threading.Thread(
                        target=self._display_on_epaper_async,
                        args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                        daemon=True
                    ).start()

                if hasattr(self, 'socketio'):
                    self.socketio.emit('display_update', {
                        'status': 'success',
                        'message': f'Display updated in {display_duration:.1f}s',
                        'block_height': block_height,
                        'timestamp': time.time()
                    })
            else:
                error = result.get("error", "unknown error")
                print(f"⚠️ E-paper display failed after {display_duration:.2f}s: {error}")
                if result.get("traceback"):
                    for line in result["traceback"].splitlines():
                        print(f"   {line}")
                self._emit_display_error(error)

        threading.Thread(target=display_in_worker, daemon=True).start()

    def _get_or_start_display_worker(self):
        """Return the running display worker, starting it if necessary."""
        import subprocess
        import sys

        if self._display_worker and self._display_worker.poll() is None:
            return self._display_worker

        # Start fresh worker
        script_path = os.path.join(os.path.dirname(__file__), "lib", "display_worker.py")
        # Drain any stale results from a previous worker
        while not self._display_worker_results.empty():
            try:
                self._display_worker_results.get_nowait()
            except queue.Empty:
                break

        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(__file__)
        )
        self._display_worker = proc

        # Start background thread that reads worker stdout into the results queue
        threading.Thread(
            target=self._read_display_worker_stdout,
            args=(proc,),
            daemon=True
        ).start()
        
        # Start background thread to forward worker stderr to our logs
        threading.Thread(
            target=self._read_display_worker_stderr,
            args=(proc,),
            daemon=True
        ).start()

        # Wait for the worker to finish loading drivers (ready signal)
        try:
            ready = self._display_worker_results.get(timeout=30)
            if ready.get("status") != "ready":
                raise RuntimeError(f"Unexpected worker signal: {ready}")
        except queue.Empty:
            proc.kill()
            raise RuntimeError("Display worker failed to become ready within 30s")

        print(f"⚙️ Display worker started (PID {proc.pid})")
        return proc

    def _read_display_worker_stdout(self, proc):
        """Background thread: pipe worker stdout lines into the results queue."""
        # Patterns to suppress (verbose hardware status messages)
        suppress_patterns = [
            "Write PON", "Write DRF", "Write POF",
            "e-Paper busy", "e-Paper busy H", "e-Paper busy H release",
            "EPD init...", "bcm2835 init success", "Display Done!!"
        ]
        
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    try:
                        self._display_worker_results.put(json.loads(line))
                    except json.JSONDecodeError:
                        # Filter out verbose hardware status messages
                        if not any(pattern in line for pattern in suppress_patterns):
                            # Log non-JSON output from worker (debugging info)
                            print(f"   [worker] {line}")
        finally:
            # Check if there's stderr output to provide better error context
            stderr_output = ""
            try:
                # Try to read any remaining stderr (non-blocking)
                if proc.stderr:
                    remaining = proc.stderr.read()
                    if remaining:
                        stderr_output = remaining.strip()
            except Exception:
                pass
            
            # Notify any waiting caller that the worker died
            error_msg = "Worker process died"
            if stderr_output:
                error_msg = f"Worker process died: {stderr_output[:200]}"  # Limit length
            self._display_worker_results.put({
                "worker_died": True, 
                "success": False,
                "error": error_msg
            })

    def _read_display_worker_stderr(self, proc):
        """Background thread: forward worker stderr to our logs with prefix."""
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    # Forward stderr from worker to our logs
                    print(f"   [worker stderr] {line}")
        except Exception:
            pass

    def _emit_display_error(self, message):
        if hasattr(self, 'socketio'):
            self.socketio.emit('display_update', {
                'status': 'error',
                'message': f'Display error: {message}',
                'timestamp': time.time()
            })
    
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
                'moscow_time_unit', 'show_donation_block'
            ]
            
            for setting in image_affecting_settings:
                if old_config.get(setting) != self.config.get(setting):
                    image_affecting_changes = True
                    print(f"⚙️ Image-affecting setting changed: {setting}")
                    break
        
        if image_affecting_changes:
            self.image_is_current = False
    
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
    
    def _background_image_generation(self, force_eink=False, use_cached_block=False, force_new_meme=False):
        """Generate image in background thread.

        Args:
            force_eink: When True, the e-ink display is refreshed even if the
                        block height hasn't changed (e.g. after a donation arrives).
            use_cached_block: When True, skip the mempool API call and use the
                              already-cached block height/hash (saves ~5 s for
                              events like donations where the block hasn't changed).
            force_new_meme: When True, always pick a new random meme even if the
                            block height hasn't changed (e.g. after a donation arrives).
        """
        # Use lock to prevent concurrent generation
        if not self.generation_lock.acquire(blocking=False):
            print("⚙️ Image generation already in progress, skipping")
            return

        try:
            print("⚙️ Starting background image generation...")

            if use_cached_block and self.current_block_height and self.current_block_hash:
                block_info = {
                    'block_height': self.current_block_height,
                    'block_hash':   self.current_block_hash,
                }
            else:
                block_info = self.mempool_api.get_current_block_info()

            # Check if we already have this block
            if (self.current_block_height == block_info['block_height'] and
                self.current_block_hash == block_info['block_hash'] and
                self.image_is_current):
                return

            # Use new meme if block height changed OR explicitly requested (e.g. donation)
            use_new_meme = force_new_meme or (self.current_block_height != block_info['block_height'])

            self._generate_new_image(
                block_info['block_height'],
                block_info['block_hash'],
                skip_epaper=False,  # Allow e-Paper update in background
                use_new_meme=use_new_meme,
                force_eink=force_eink
            )
            
            # Emit to web clients from RAM cache
            with self.app.app_context():
                try:
                    image_data = self._get_web_image_base64()
                    if image_data and len(image_data) > 50:
                        self.socketio.emit('new_image', {'image': image_data})
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
            
            with open(self.cache_metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            self._last_disk_save_time = time.time()
            self._disk_save_pending = False
        except Exception as e:
            print(f"⚠️ Error saving cache metadata: {e}")
    
    def _start_precache_updater(self):
        """Start background thread that keeps slow-changing data fresh."""
        def update_precache():
            """Background worker to refresh price and bitaxe data between blocks."""
            # Initial pre-fill on startup
            self._update_precache_data()

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

    def _update_precache_data(self):
        """Update pre-cached data (price, bitaxe, fees) in background."""
        data_changed = False
        with self._precache['lock']:
            now = time.time()
            update_interval = self.config.get("precache_update_interval_seconds", 300)

            # In prioritize_large_scaled_meme mode, pre-select the next meme and the
            # info block types that will actually be shown.  Data is then only fetched
            # for the pre-selected types, eliminating wasted API calls.
            if self.config.get("prioritize_large_scaled_meme", False):
                next_meme = self.image_renderer.pick_random_meme()
                selected = self.image_renderer._preselect_info_blocks(next_meme)
                # selected: None (shouldn't happen here), [] (meme fills screen), or list
                self._precache['next_meme_path'] = next_meme
                self._precache['selected_block_types'] = selected if selected is not None else []
                _selected = self._precache['selected_block_types']
            else:
                # Clear meme-first preselection artifacts when switching back to balanced mode.
                self._precache['next_meme_path'] = None
                self._precache['selected_block_types'] = None
                _selected = None  # None → fetch all (default layout shows all blocks)

            # Helper: should a specific block type's data be fetched?
            def _need_type(*types):
                return _selected is None or any(t in _selected for t in types)

            # Update price data if stale
            if _need_type('price', 'wallet') and now - self._precache['price_last_update'] > update_interval:
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
                            data_changed = True
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache price: {e}")
            
            # Update Bitaxe data only when the Bitaxe block will be shown and data is stale.
            if _need_type('bitaxe') and self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True) and now - self._precache['bitaxe_last_update'] > update_interval:
                try:
                    bitaxe_data = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                    if bitaxe_data:
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
            
            # Update network stats when at least one network-dependent block will be shown.
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
                except Exception as e:
                    print(f"⚠️ Failed to pre-cache network stats: {e}")

            # Update fee data if stale (fees change more frequently, so use shorter interval)
            fee_update_interval = min(update_interval, 60)  # Update fees at least every 60s
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
                    price_data = self.image_renderer.fetch_btc_price()
                    self._precache['price_data'] = price_data
                    self._precache['price_last_update'] = now
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
    
    def _on_config_change(self, new_config):
        """
        Handle configuration changes that affect image rendering.
        Triggers immediate image regeneration with cached meme for visual settings.
        """
        print("🔧 Configuration change detected, checking if image refresh needed...")
        
        # Define settings that affect image rendering and require full regeneration
        image_affecting_settings = {
            # Hardware settings
            'web_orientation', 'eink_orientation', 'display_width', 'display_height', 'e-ink-display-connected',
            'omni_device_name', 'block_height_area',

            # Meme layout settings
            'prioritize_large_scaled_meme',

            # Block visibility / content settings
            'show_btc_price_block', 'btc_price_currency',
            'show_bitaxe_block',
            'show_wallet_balances_block', 'wallet_balance_unit', 'wallet_balance_currency',

            # Design settings (colors, fonts)
            'font_regular', 'font_bold', 'color_mode_dark',

            # Price/time display settings
            'moscow_time_unit',

            # Holiday settings
            'hide_holiday_if_large_meme',

            # E-ink display settings
            'eink_dark_mode',

            # General settings that affect display
            'language',

            # Mempool fee settings
            'fee_parameter',

            # Donation display settings
            'show_donation_block', 'donation_display_mode',
        }

        # Compare old and new config for image-affecting changes
        old_config = self.config

        # Restart webhook relay listener immediately if its URL changed
        if old_config.get("webhook_relay_ws_url") != new_config.get("webhook_relay_ws_url"):
            print("⚡ webhook relay URL changed — restarting listener")
            self._restart_webhook_site_listener()
        config_changed = False
        changed_settings = []
        opsec_toggled = old_config.get('opsec_mode_enabled') != new_config.get('opsec_mode_enabled')
        prioritize_layout_toggled = (
            old_config.get('prioritize_large_scaled_meme') != new_config.get('prioritize_large_scaled_meme')
        )

        for setting in image_affecting_settings:
            old_value = old_config.get(setting)
            new_value = new_config.get(setting)
            # Ignore transitions from a real value to absent (None) — that means
            # the field was an auto-set default not stored in config.json, not a
            # deliberate user change.
            if old_value != new_value and not (old_value is not None and new_value is None):
                config_changed = True
                changed_settings.append(setting)

        if config_changed:
            print(f"⚙️ Settings changed ({', '.join(changed_settings)}) — triggering image refresh")

            # Update config references
            self.config = new_config

            # Update translations if language changed
            if 'language' in changed_settings:
                lang = new_config.get("language", "en")
                self.translations = translations.get(lang, translations["en"])
                print(f"🌐 Updated translations to language: {lang}")

            # Recreate image renderer with new config
            self.image_renderer = ImageRenderer(self.config, self.translations)

            # Force current image refresh path to run even if block height/hash are unchanged.
            self.image_is_current = False

            # If layout mode toggled, clear stale preselection artifacts immediately.
            if prioritize_layout_toggled:
                print("🎭 prioritize_large_scaled_meme toggled — forcing current + next image refresh")
                with self._precache['lock']:
                    self._precache['next_meme_path'] = None
                    self._precache['selected_block_types'] = None
                # Prime pre-cache now so the very next pre-render uses the new layout mode.
                try:
                    self._update_precache_data()
                except Exception as e:
                    print(f"⚠️ Failed to refresh pre-cache after layout toggle: {e}")

            # Discard stale pre-rendered image so the next block doesn't use it
            self._invalidate_prerender()

            # Trigger immediate refresh regardless of image_is_current state.
            # Run in a background thread to avoid blocking the save response.
            if (self.current_block_height and
                self.current_block_hash and
                hasattr(self, 'current_meme_path') and
                self.current_meme_path and
                os.path.exists(self.current_meme_path)):

                # Fast path: reuse cached meme, force e-ink update
                threading.Thread(
                    target=self._regenerate_image_with_cached_meme,
                    daemon=True
                ).start()
            else:
                # No cached meme yet — full generation with forced e-ink
                print("💾 No cached meme available, starting full background generation...")
                threading.Thread(
                    target=self._background_image_generation,
                    kwargs={"force_eink": True, "use_cached_block": True},
                    daemon=True
                ).start()
        elif opsec_toggled:
            # OPSec mode changed but nothing else — fast path: only update e-ink display,
            # web image stays unchanged (data hasn't changed, no block update).
            opsec_enabled = new_config.get('opsec_mode_enabled', False)
            print(f"🔒 OPSec mode {'enabled' if opsec_enabled else 'disabled'} — refreshing e-ink only...")
            self.config = new_config
            self.image_renderer = ImageRenderer(self.config, self.translations)
            threading.Thread(
                target=self._refresh_eink_for_opsec_toggle,
                args=(opsec_enabled,),
                daemon=True
            ).start()
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
                self.image_renderer._donation_data = self._get_active_donation()
                precached_price, precached_bitaxe, precached_fee, _, precached_network = self._get_precached_data()
                web_img, eink_img, meme_path = self.image_renderer.render_dual_images_with_cached_meme(
                    self.current_block_height,
                    self.current_block_hash,
                    self.current_meme_path,
                    mempool_api=self.mempool_api,
                    precached_price=precached_price,
                    precached_bitaxe=precached_bitaxe,
                    precached_fee=precached_fee,
                    precached_network=precached_network
                )

                # Cache in RAM and save to disk in background
                self._cache_web_image(web_img)
                self._cached_eink_image = eink_img
                if eink_img is not None:
                    eink_img.save(self.current_eink_image_path, compress_level=1)
                self._save_images_to_disk(web_img, None)  # eink already saved above
                
                # Update cache metadata (deferred to reduce SD writes)
                self.image_is_current = True
                self._deferred_save_cache_metadata()

                # Display on e-Paper if enabled
                if self.e_ink_enabled:
                    threading.Thread(
                        target=self._display_on_epaper_async,
                        args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                        daemon=True
                    ).start()
                
                # Push fresh image to connected web clients from RAM cache
                try:
                    image_data = self._get_web_image_base64()
                    if image_data:
                        self.socketio.emit('new_image', {'image': image_data})
                except Exception as e:
                    print(f"⚠️ Failed to send image to web clients: {e}")
                
                # Start async wallet refresh in background
                if self.config.get("show_wallet_balances_block", True):
                    try:
                        threading.Thread(
                            target=self._safe_wallet_refresh_thread,
                            args=(self.current_block_height, self.current_block_hash, False),
                            daemon=True
                        ).start()
                    except Exception as proc_e:
                        print(f"❌ Failed to start wallet refresh thread: {proc_e}")

                # Re-build pre-rendered next-block image with updated settings
                threading.Thread(target=self._prerender_next_block, daemon=True).start()

        except Exception as e:
            print(f"❌ Error regenerating image with cached meme: {e}")
            # Fall back to normal generation
            self._generate_new_image(self.current_block_height, self.current_block_hash, skip_epaper=False, use_new_meme=False)

    def _refresh_eink_for_opsec_toggle(self, opsec_enabled):
        """
        Fast e-ink-only refresh when opsec mode is toggled.
        - Enabled:  renders the opsec cover image and pushes it to the display.
        - Disabled: converts the existing web image to 7-color e-ink format and
                    pushes it — no API calls, no web image regeneration.
        """
        if not self.e_ink_enabled:
            print("🖥️ E-ink not connected — skipping opsec display refresh")
            return

        try:
            if opsec_enabled:
                # Render a fresh opsec cover image
                eink_img = self.image_renderer.render_opsec_eink_image()
                if eink_img is None:
                    print("⚠️ No opsec image available — falling back to full regeneration")
                    if self.image_is_current and self.current_block_height and self.current_block_hash:
                        self._regenerate_image_with_cached_meme()
                    return
                print("🔒 OPSec e-ink image rendered")
            else:
                # OPSec disabled: re-render the full dashboard through the normal e-ink
                # pipeline. Converting the web image with convert_to_7color gives wrong
                # colours because the web image was rendered for a full RGB display.
                print("🔓 OPSec disabled — re-rendering dashboard for e-ink")
                if self.current_block_height and self.current_block_hash:
                    threading.Thread(
                        target=self._regenerate_image_with_cached_meme,
                        daemon=True
                    ).start()
                return  # _regenerate_image_with_cached_meme handles save + display push

            # Save the new e-ink image (only reached for the opsec-enabled path)
            eink_img.save(self.current_eink_image_path, compress_level=1)

            # Display on e-Paper in background thread
            threading.Thread(
                target=self._display_on_epaper_async,
                args=(self.current_eink_image_path, self.current_block_height, self.current_block_hash),
                daemon=True
            ).start()

            # Notify web clients so the UI can reflect the opsec state change
            self.socketio.emit('image_updated', {
                'message': 'E-ink display refreshed for opsec mode change',
                'block_height': self.current_block_height,
                'timestamp': time.time()
            })

        except Exception as e:
            print(f"❌ Error in opsec e-ink refresh: {e}")

    # Track previous emission values for change detection
    _last_emitted_bitaxe = {}   # {ip: {'best_diff': ..., 'online': ...}}
    _last_emitted_blocks = {}   # {address: count}

    def _emit_config_page_updates(self):
        """Push live updates to the config page via Socket.IO (bitaxe stats & found blocks)."""
        if not hasattr(self, 'socketio') or not self.socketio:
            return
        try:
            config = self.config_manager.get_current_config()

            # Bitaxe stats for all configured miners (with labels)
            miner_table = config.get('bitaxe_miner_table', [])
            if miner_table:
                from lib.bitaxe_api import BitaxeAPI
                bitaxe_api = getattr(self.image_renderer, 'bitaxe_api', None) or BitaxeAPI()
                miners = {}
                for entry in miner_table:
                    ip = entry.get('address', '').strip() if isinstance(entry, dict) else ''
                    if not ip:
                        continue
                    label = entry.get('comment', '').strip() if isinstance(entry, dict) else ''
                    try:
                        info = bitaxe_api.get_miner_info(ip)
                        prev = self._last_emitted_bitaxe.get(ip, {})
                        miners[ip] = {
                            'best_diff': info.get('best_diff', 0),
                            'online': info.get('online', False),
                            'label': label or ip,
                            'prev_best_diff': prev.get('best_diff', 0),
                            'prev_online': prev.get('online', False),
                        }
                        self._last_emitted_bitaxe[ip] = {
                            'best_diff': info.get('best_diff', 0),
                            'online': info.get('online', False),
                        }
                    except Exception:
                        miners[ip] = {'best_diff': 0, 'online': False, 'label': label or ip, 'prev_best_diff': 0, 'prev_online': False}
                if miners:
                    self.socketio.emit('bitaxe_stats_updated', {'miners': miners}, room='authenticated')

            # Found blocks for all configured addresses (with labels)
            block_reward_table = config.get('block_reward_addresses_table', [])
            if block_reward_table and hasattr(self, 'block_monitor') and self.block_monitor:
                blocks = {}
                for entry in block_reward_table:
                    address = entry.get('address', '').strip() if isinstance(entry, dict) else ''
                    if not address:
                        continue
                    label = entry.get('comment', '').strip() if isinstance(entry, dict) else ''
                    try:
                        count = self.block_monitor.get_coinbase_count(address) if hasattr(self.block_monitor, 'get_coinbase_count') else 0
                        prev_count = self._last_emitted_blocks.get(address, 0)
                        blocks[address] = {
                            'count': count,
                            'prev_count': prev_count,
                            'label': label or address[:12] + '...',
                        }
                        self._last_emitted_blocks[address] = count
                    except Exception:
                        blocks[address] = {'count': 0, 'prev_count': 0, 'label': label or address[:12] + '...'}
                if blocks:
                    self.socketio.emit('found_blocks_updated', {'blocks': blocks}, room='authenticated')
        except Exception as e:
            print(f"⚠️ Error emitting config page updates: {e}")

    def async_wallet_refresh(self, block_height, block_hash, startup_mode=False):
        """Fetch fresh wallet data and regenerate image if balance changed."""
        print(f"🚀 [WALLET] Starting wallet refresh for block {block_height}...")
        try:
            # Fetch fresh wallet data
            print("👁️ [WALLET] Fetching fresh wallet data...")
            fresh_wallet_data = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=block_height)
            
            # Log wallet data with privacy masking
            # masked_fresh_data = MempaperApp.mask_wallet_data_for_logging(fresh_wallet_data)
            
            # Get cached wallet data
            print("📖 [WALLET] Loading cached wallet data...")
            cached_wallet_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
            
            # Log cached data with privacy masking
            # masked_cached_data = MempaperApp.mask_wallet_data_for_logging(cached_wallet_data)
            
            # Ensure both are dicts before accessing .get()
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            wallet_changed = fresh_btc != cached_btc
            
            # Compare Bitaxe data only if block is enabled and currently displayed.
            bitaxe_changed = False
            if self.config.get("show_bitaxe_block", True) and self.config.get("bitaxe_enabled", True) and 'bitaxe' in self.displayed_info_blocks:
                fresh_bitaxe = self.image_renderer.bitaxe_api.fetch_bitaxe_stats()
                cached_bitaxe = self.displayed_bitaxe_data or {}
                
                fresh_blocks = fresh_bitaxe.get('valid_blocks', 0) if fresh_bitaxe else 0
                cached_blocks = cached_bitaxe.get('valid_blocks', 0)
                fresh_difficulty = fresh_bitaxe.get('best_difficulty', 0) if fresh_bitaxe else 0
                cached_difficulty = cached_bitaxe.get('best_difficulty', 0)
                
                if fresh_blocks != cached_blocks or fresh_difficulty != cached_difficulty:
                    bitaxe_changed = True
                    self.displayed_bitaxe_data = fresh_bitaxe
            
            # Determine if regeneration is needed
            needs_regeneration = False
            regeneration_reason = []
            
            if wallet_changed and 'wallet' in self.displayed_info_blocks:
                needs_regeneration = True
                regeneration_reason.append(f"wallet {cached_btc:.8f}→{fresh_btc:.8f} BTC")
            
            if bitaxe_changed:
                needs_regeneration = True
                regeneration_reason.append("Bitaxe data")
            
            # Update caches regardless of regeneration
            self.image_renderer.wallet_api.update_cache(fresh_wallet_data)
            
            if needs_regeneration:
                reason_str = ", ".join(regeneration_reason)
                print(f"🔄 [REFRESH] Regenerating image: {reason_str}")
                
                # Emit WebSocket events for config page live updates
                if hasattr(self, 'socketio') and self.socketio:
                    # Include previous balances for change-detection toasts
                    emit_data = dict(fresh_wallet_data)
                    emit_data['prev_total_btc'] = cached_btc
                    if isinstance(cached_wallet_data, dict):
                        emit_data['prev_addresses'] = cached_wallet_data.get('addresses', [])
                        emit_data['prev_xpubs'] = cached_wallet_data.get('xpubs', [])
                    self.socketio.emit('wallet_balance_updated', emit_data, room='authenticated')
                    self._emit_config_page_updates()
                
                # Get pre-cached data for fast rendering
                precached_price, precached_bitaxe, precached_fee, precached_block_height, precached_network = self._get_precached_data()

                # Sync latest donation data to renderer
                self.image_renderer._donation_data = self._get_active_donation()

                # Regenerate with SAME meme and info blocks (preserve_layout=True)
                web_img, eink_img, content_path, displayed_blocks = self.image_renderer.render_dual_images(
                    block_height, block_hash,
                    mempool_api=self.mempool_api,
                    startup_mode=startup_mode,
                    override_content_path=self.current_meme_path,  # Keep same meme
                    preserve_info_blocks=self.displayed_info_blocks,  # Keep same info blocks
                    precached_price=precached_price,
                    precached_bitaxe=precached_bitaxe,
                    precached_fee=precached_fee,
                    precached_block_height=precached_block_height,
                    precached_network=precached_network
                )
                # Update displayed blocks tracking
                self.displayed_info_blocks = displayed_blocks
                # Cache in RAM and save to disk in background
                self._cache_web_image(web_img)
                self._cached_eink_image = eink_img
                self._save_images_to_disk(web_img, eink_img)
            else:
                pass  # No visible data changes
                
            # Defer cache metadata save to reduce SD card writes
            self._deferred_save_cache_metadata()
            
        except Exception as e:
            print(f"❌ [WALLET] Error during wallet refresh: {e}")
            traceback.print_exc()

    def _safe_wallet_refresh_thread(self, block_height, block_hash, startup_mode=False):
        """Safe wallet refresh that runs in thread but uses subprocess for actual work."""
        try:
            self._run_wallet_refresh_process(block_height, block_hash, startup_mode)
        except Exception as e:
            print(f"❌ [THREAD] Error in safe wallet refresh: {e}")
            traceback.print_exc()

    def _run_wallet_refresh_process(self, block_height, block_hash, startup_mode=False):
        """Run wallet refresh in separate process to avoid gunicorn timeouts."""
        try:
            from managers.config_manager import ConfigManager
            from lib.image_renderer import ImageRenderer
            from utils.translations import translations
            
            config_manager = ConfigManager()
            config = config_manager.get_current_config()
            image_renderer = ImageRenderer(config, translations)
            
            fresh_wallet_data = image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=block_height)
            cached_wallet_data = image_renderer.wallet_api.get_cached_wallet_balances()
            
            if not isinstance(fresh_wallet_data, dict):
                fresh_wallet_data = {}
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}
            
            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)
            
            if fresh_btc != cached_btc:
                print(f"⚙️ Wallet balance changed: {cached_btc:.8f} → {fresh_btc:.8f} BTC")
            
            # Always update cache to keep timestamp fresh
            image_renderer.wallet_api.update_cache(fresh_wallet_data)
                
        except Exception as e:
            print(f"❌ Wallet refresh failed: {e}")
            traceback.print_exc()

    def _cache_web_image(self, img):
        """Cache a PIL web image as a ready-to-emit base64 data URI string."""
        if img is None:
            return
        buf = io.BytesIO()
        img.save(buf, format='PNG', compress_level=1)
        self._cached_web_image_base64 = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    def _encode_pil_to_base64(self, img):
        """Encode a PIL image to a base64 data URI string without caching."""
        if img is None:
            return None
        buf = io.BytesIO()
        img.save(buf, format='PNG', compress_level=1)
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    def _get_web_image_base64(self):
        """Get the web image as base64 data URI, from RAM cache or disk fallback."""
        if self._cached_web_image_base64:
            return self._cached_web_image_base64
        # Fallback: read from disk (e.g. after restart before first generation)
        if os.path.exists(self.current_image_path):
            with open(self.current_image_path, 'rb') as f:
                data = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                self._cached_web_image_base64 = data  # warm RAM cache
                return data
        return None

    def _save_images_to_disk(self, web_img, eink_img):
        """Save images to disk in background for crash recovery persistence."""
        def _save():
            try:
                if web_img is not None:
                    web_img.save(self.current_image_path, compress_level=1)
                if eink_img is not None:
                    eink_img.save(self.current_eink_image_path, compress_level=1)
            except Exception as e:
                print(f"⚠️ Background image save failed: {e}")
        threading.Thread(target=_save, daemon=True).start()

    def _prerender_next_block(self):
        """Pre-render the dashboard image for the expected next block.
        
        Uses current pre-cached data (price, fees, bitaxe, wallet, meme) and
        next_height = current_block_height + 1.  The block hash is not yet known,
        so a placeholder is used for the decorative hash frame.
        
        Called in background after every successful block processing.
        """
        if not self._prerendered['lock'].acquire(blocking=False):
            return  # Another pre-render already running
        try:
            current = self.current_block_height
            if current is None:
                return
            next_height = int(current) + 1
            mode_signature = self._get_prerender_mode_signature()

            # Skip if already pre-rendered for this height with valid data
            if (self._prerendered['block_height'] == next_height
                    and self._prerendered['web_base64']
                    and self._prerendered.get('mode_signature') == mode_signature):
                return

            # Consume the pre-selected meme and block types (if any) — clear after use
            # so the next _update_precache_data cycle picks fresh ones.
            with self._precache['lock']:
                precached_meme = self._precache.get('next_meme_path')
                precached_selected = self._precache.get('selected_block_types')
                self._precache['next_meme_path'] = None
                self._precache['selected_block_types'] = None

            # Gather pre-cached data (filtered to pre-selected types when applicable)
            precached_price, precached_bitaxe, precached_fee, _, precached_network = self._get_precached_data()

            # Use a deterministic placeholder hash for the decorative frame
            placeholder_hash = "0" * 64

            # Sync donation data
            self.image_renderer._donation_data = self._get_active_donation()

            web_img, eink_img, content_path, displayed_blocks = self.image_renderer.render_dual_images(
                next_height,
                placeholder_hash,
                mempool_api=self.mempool_api,
                startup_mode=True,
                override_content_path=precached_meme,
                # Pass pre-selected types only when the list is non-empty; an empty list or
                # None lets render_dual_images run _preselect_info_blocks itself.
                preserve_info_blocks=precached_selected if precached_selected else None,
                precached_price=precached_price,
                precached_bitaxe=precached_bitaxe,
                precached_fee=precached_fee,
                precached_block_height=next_height,
                precached_network=precached_network,
                skip_hash_frame=True
            )

            # Encode and store in RAM
            web_base64 = self._encode_pil_to_base64(web_img)

            self._prerendered['block_height'] = next_height
            self._prerendered['web_base64'] = web_base64
            self._prerendered['eink_img'] = eink_img
            self._prerendered['web_img'] = web_img
            self._prerendered['meme_path'] = content_path
            self._prerendered['displayed_blocks'] = displayed_blocks
            self._prerendered['timestamp'] = time.time()
            self._prerendered['mode_signature'] = mode_signature

            print(f"🚀 Pre-rendered image ready for next block {next_height}")
        except Exception as e:
            print(f"⚠️ Pre-render failed: {e}")
        finally:
            self._prerendered['lock'].release()

    def _use_prerendered_image(self, block_height, block_hash):
        """Try to use a pre-rendered image for instant block delivery.
        
        Returns True if pre-rendered image was used, False otherwise.
        """
        pr = self._prerendered
        if pr['block_height'] != block_height or not pr['web_base64']:
            return False

        # Do not use pre-rendered images produced under a different layout mode.
        if pr.get('mode_signature') != self._get_prerender_mode_signature():
            print("⚠️ Pre-render mode mismatch detected — regenerating with current config")
            return False

        # Pre-rendered image matches! Use it instantly.
        age = time.time() - pr['timestamp']
        if age > 600:  # Too old (>10 min), data may be stale
            print(f"⚠️ Pre-rendered image for block {block_height} is {age:.0f}s old, regenerating")
            return False

        # Reject pre-renders from a different calendar day (date/holiday would be wrong)
        pre_date = datetime.fromtimestamp(pr['timestamp']).date()
        if pre_date != datetime.now().date():
            print(f"⚠️ Pre-rendered image is from {pre_date}, today is {datetime.now().date()} — regenerating")
            return False

        print(f"⚡ Using pre-rendered image for block {block_height} (ready {age:.1f}s ago)")

        # Patch hash frame onto pre-rendered images (fast ~10ms per image)
        web_img_patched = pr['web_img'].copy() if pr['web_img'] is not None else None
        if web_img_patched is not None:
            self.image_renderer._apply_orientation_settings(self.image_renderer.web_orientation)
            self.image_renderer.patch_hash_frame_on_image(web_img_patched, block_hash, web_quality=True)

        eink_img_patched = None
        if self.e_ink_enabled:
            if self.config.get("opsec_mode_enabled", False):
                # OPSec active: always show a fresh opsec cover, not the pre-rendered dashboard
                eink_img_patched = self.image_renderer.render_opsec_eink_image()
            elif pr['eink_img'] is not None:
                eink_img_patched = pr['eink_img'].copy()
                self.image_renderer._apply_orientation_settings(self.image_renderer.eink_orientation)
                self.image_renderer.patch_hash_frame_on_image(eink_img_patched, block_hash, web_quality=False)
                self.image_renderer._apply_orientation_settings(self.image_renderer.web_orientation)

        # Promote to current (with patched hash frame)
        if web_img_patched is not None:
            self._cache_web_image(web_img_patched)
        else:
            self._cached_web_image_base64 = pr['web_base64']
        self._cached_eink_image = eink_img_patched or pr['eink_img']
        self.current_meme_path = pr['meme_path']
        self.displayed_info_blocks = pr['displayed_blocks']

        # Update state
        self.current_block_height = block_height
        self.current_block_hash = block_hash
        self.image_is_current = True

        # Emit to web clients IMMEDIATELY (with correct hash frame)
        with self.app.app_context():
            try:
                image_data = self._get_web_image_base64()
                self.socketio.emit('new_image', {'image': image_data})
                print("📶 Pre-rendered image sent to web clients instantly")
            except Exception as e:
                print(f"⚠️ Failed to emit pre-rendered image: {e}")

        # Start e-ink display immediately
        if self.e_ink_enabled and eink_img_patched is not None:
            eink_img_patched.save(self.current_eink_image_path, compress_level=1)
            threading.Thread(
                target=self._display_on_epaper_async,
                args=(self.current_eink_image_path, block_height, block_hash),
                daemon=True
            ).start()

        # Background: save web image + metadata to disk (non-blocking)
        def _persist():
            if web_img_patched is not None:
                try:
                    web_img_patched.save(self.current_image_path, compress_level=1)
                except Exception as e:
                    print(f"⚠️ Background web image save failed: {e}")
            self._deferred_save_cache_metadata()
        threading.Thread(target=_persist, daemon=True).start()

        # Clear pre-rendered state
        pr['block_height'] = None
        pr['web_base64'] = None
        pr['eink_img'] = None
        pr['web_img'] = None

        # Background: pre-render next block and wallet refresh
        def _post_block_tasks():
            self._prerender_next_block()

            # Start wallet refresh
            if self.config.get("show_wallet_balances_block", True):
                try:
                    threading.Thread(
                        target=self._safe_wallet_refresh_thread,
                        args=(block_height, block_hash, False),
                        daemon=True
                    ).start()
                except Exception:
                    pass

        threading.Thread(target=_post_block_tasks, daemon=True).start()
        return True

    def _generate_new_image(self, block_height: int, block_hash: str, skip_epaper: bool = False, use_new_meme: bool = True, force_eink: bool = False):
        """Generate a new dashboard image and cache it."""
        print(f"⚙️ Generating dashboard image for block {block_height}...")

        # Sync latest donation data to renderer
        self.image_renderer._donation_data = self._get_active_donation()

        # 🚀 Get pre-cached data for instant image generation
        precached_price, precached_bitaxe, precached_fee, precached_block_height, precached_network = self._get_precached_data()
        
        # Decide whether to use cached meme or pick a new one
        if use_new_meme or not hasattr(self, 'current_meme_path') or not self.current_meme_path or not os.path.exists(self.current_meme_path):
            print("⚙️ Selecting new random meme for this block...")
            web_img, eink_img, content_path, displayed_blocks = self.image_renderer.render_dual_images(
                block_height,
                block_hash,
                mempool_api=self.mempool_api,
                startup_mode=True,  # Use cached wallet data for instant response
                override_content_path=None,
                precached_price=precached_price,  # Use pre-cached price
                precached_bitaxe=precached_bitaxe,  # Use pre-cached Bitaxe
                precached_fee=precached_fee,  # Use pre-cached fee
                precached_block_height=precached_block_height,  # Use pre-cached block height
                precached_network=precached_network  # Use pre-cached network stats
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
                mempool_api=self.mempool_api,
                precached_price=precached_price,
                precached_bitaxe=precached_bitaxe,
                precached_fee=precached_fee,
                precached_network=precached_network
            )
        
        # Save images: cache in RAM instantly, persist to disk in background
        # Race condition check: Verify block is still current before saving
        current_stored_height = getattr(self, 'current_block_height', 0) or 0
        if block_height < current_stored_height:
            print(f"⏭️ Skipping image save for old block {block_height} (current: {current_stored_height})")
            return  # Abort - newer block already processed
        
        try:
            # Cache web image in RAM for instant serving to web clients
            self._cache_web_image(web_img)
            self._cached_eink_image = eink_img
            # E-ink display subprocess needs file on disk — save synchronously
            if eink_img is not None:
                eink_img.save(self.current_eink_image_path, compress_level=1)
            # Web image only needed on disk for crash recovery — save in background
            if web_img is not None:
                threading.Thread(
                    target=lambda: web_img.save(self.current_image_path, compress_level=1),
                    daemon=True
                ).start()
            print(f"💾 Images cached for block {block_height}")
        except Exception as e:
            print(f"❌ Failed to save images: {e}")
            traceback.print_exc()
            return
        
        # Update cache state
        self.current_block_height = block_height
        self.current_block_hash = block_hash
        self.image_is_current = True
        
        # Defer cache metadata save to reduce SD card writes
        self._deferred_save_cache_metadata()
        
        # Start e-ink display update in background
        # Skip if the onboarding connected screen is still showing — the fresh
        # generation after the 60s timer will push the correct image.
        if self._onboarding_connected_active:
            print('⏭️ Skipping e-ink update — onboarding connected screen is active')
        elif self.e_ink_enabled and not skip_epaper:
            current_eink_height = getattr(self, 'last_eink_block_height', 0) or 0
            if int(block_height or 0) != int(current_eink_height) or force_eink:
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self.current_eink_image_path, block_height, block_hash),
                    daemon=True
                ).start()
        
        # Start wallet refresh in background (lower priority)
        def start_wallet_refresh():
            """Start wallet refresh in background."""
            if self.config.get("show_wallet_balances_block", True):
                # Check if wallet refresh is already in progress (prevent concurrent scans)
                if hasattr(self.image_renderer, 'wallet_api') and hasattr(self.image_renderer.wallet_api, '_fetch_lock'):
                    if self.image_renderer.wallet_api._fetch_lock.locked():
                        return
                
                threading.Thread(
                    target=self._safe_wallet_refresh_thread,
                    args=(block_height, block_hash, False),
                    daemon=True
                ).start()
        
        # Schedule wallet refresh to run after a short delay to prioritize e-ink
        threading.Thread(target=start_wallet_refresh, daemon=True).start()
        
        # Pre-render next block's image in background
        threading.Thread(target=self._prerender_next_block, daemon=True).start()
        
        return web_img  # Return web image for web clients IMMEDIATELY
    
    def on_new_block_received(self, block_height, block_hash):
        """
        Handle new block data received from WebSocket.
        
        Args:
            block_height (str): New block height
            block_hash (str): New block hash
        """
        # Convert block_height to integer if it's a string
        try:
            if isinstance(block_height, str):
                block_height_int = int(float(block_height)) if '.' in block_height else int(block_height)
            else:
                block_height_int = int(block_height)
        except (ValueError, TypeError) as e:
            print(f"❌ Failed to convert block height {block_height}: {e}")
            return
        
        # 🔧 FIX: Prevent duplicate block processing and race conditions
        current_height = getattr(self, 'current_block_height', None)
        try:
            current_height_int = int(current_height) if current_height is not None else None
        except (ValueError, TypeError):
            current_height_int = None

        if current_height_int is not None and block_height_int <= current_height_int:
            return
        
        # Note: Block notification is sent by block_monitor callback before this is called
        # No need to send duplicate notification here
        
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
            
            # 🚀 Try pre-rendered image first for instant delivery
            self.image_is_current = False
            try:
                used_prerender = self._use_prerendered_image(block_height_int, block_hash)
            except Exception as e:
                print(f"⚠️ Pre-rendered image failed, falling back to fresh generation: {e}")
                used_prerender = False
            if used_prerender:
                return  # Pre-rendered image used — all tasks handled

            # Fallback: generate fresh image (no pre-render available)
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
                    block_response = requests.get(f"{base_url}/v1/block/{block_hash}", timeout=10, verify=False)
                    
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
            traceback.print_exc()
    
    def _get_mempool_base_url(self):
        """Get mempool API base URL from configuration."""
        return build_mempool_api_url(
            self.config.get("mempool_host", "127.0.0.1"),
            self.config.get("mempool_rest_port", "8080"),
            self.config.get("mempool_use_https", False)
        )
    
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
                        print(f"⏳ Bootstrap detection running - using cached wallet data (attempt {attempt})")
                        
                    img = self._generate_new_image(block_height, block_hash, use_new_meme=True)
                    if img:
                        with self.app.app_context():
                            try:
                                image_data = self._get_web_image_base64()
                                if image_data and len(image_data) > 50:
                                    self.socketio.emit('new_image', {'image': image_data})
                                    print("📶 New image sent to web clients via WebSocket")
                                else:
                                    print("⚠️ Invalid image data generated, not sending to clients")
                            except Exception as e:
                                print(f"⚠️ Failed to encode image for WebSocket: {e}")
                        # Background tasks (wallet refresh + e-ink display) are already started in _generate_new_image
                        break
                    else:
                        print(f"❌ Image generation returned None (attempt {attempt})")
                except Exception as e:
                    print(f"❌ Error regenerating dashboard for block {block_height} (attempt {attempt}): {e}")
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

        def setup_mode_enabled():
            return self._is_setup_mode_enabled()

        def setup_mode_payload():
            return self._setup_mode_payload()

        def detect_wifi_interface():
            return self._detect_wifi_interface()

        def run_nmcli(args):
            """Run nmcli with sudo for setup operations.

            In AP (hotspot) mode, plain nmcli often returns empty scan results
            because the unprivileged user cannot read driver scan data.  Using
            sudo mirrors the approach in ``_nmcli()`` and delivery_state.py.
            """
            cmd = (['sudo', 'nmcli'] if os.name != 'nt' else ['nmcli']) + args
            try:
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=25,
                )
            except Exception:
                return None

        def scan_wifi_networks(interface):
            import time as _time
            import shutil as _shutil

            # In AP mode nmcli rescan is blocked by NM; use 'iw' for a fresh
            # passive scan instead, then fall back to the cached NM results.
            if _shutil.which('iw'):
                subprocess.run(
                    ['sudo', 'iw', 'dev', interface, 'scan', 'passive'],
                    capture_output=True, timeout=15,
                )
                _time.sleep(2)   # give NM a moment to pick up new scan results
            else:
                run_nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
                _time.sleep(2)

            result = run_nmcli([
                '-t',
                '-f',
                'IN-USE,SSID,SIGNAL,SECURITY',
                'device',
                'wifi',
                'list',
                'ifname',
                interface,
            ])
            if result is None or result.returncode != 0:
                return []

            # Get our own hotspot SSID so we can exclude it from the list
            own_ssid = self._setup_ssid_from_mac(interface) if self._is_setup_mode_enabled() else None

            networks = []
            seen = set()
            for line in result.stdout.splitlines():
                parts = line.split(':')
                if len(parts) < 4:
                    continue
                in_use = parts[0].strip()
                ssid = parts[1].strip()
                signal = parts[2].strip()
                security = parts[3].strip()
                if not ssid or ssid in seen:
                    continue
                # Never show our own hotspot in the client-network list
                if own_ssid and ssid == own_ssid:
                    continue
                seen.add(ssid)
                try:
                    signal_int = int(signal)
                except ValueError:
                    signal_int = 0
                networks.append({
                    'ssid': ssid,
                    'signal': signal_int,
                    'security': security,
                    'in_use': in_use == '*',
                    'open': security in ('', '--'),
                })

            networks.sort(key=lambda n: n.get('signal', 0), reverse=True)
            return networks

        def current_wifi_status(interface):
            result = run_nmcli(['-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'])
            if result is None or result.returncode != 0:
                return {'connected': False, 'connection': ''}

            for line in result.stdout.splitlines():
                parts = line.split(':')
                if len(parts) < 4:
                    continue
                dev, dev_type, state, connection = parts[0], parts[1], parts[2], parts[3]
                if dev == interface and dev_type == 'wifi':
                    connected = state.startswith('connected') and not self._is_setup_hotspot_connection(connection)
                    return {
                        'connected': connected,
                        'connection': connection,
                    }

            return {'connected': False, 'connection': ''}

        # Tracks async Wi-Fi connect state so JS can poll after response is sent.
        _wifi_connect_state = {'status': 'idle', 'message': '', 'connection': ''}

        def apply_wifi_credentials_background(interface, ssid, password, hidden):
            """Runs in a background thread AFTER the HTTP response has been sent."""
            _wifi_connect_state['status'] = 'connecting'
            _wifi_connect_state['message'] = f'Connecting to {ssid}...'

            # Short delay so the HTTP response definitely leaves the socket first.
            time.sleep(1)

            # Fully tear down the hotspot: remove iptables redirects, delete ALL
            # stale mempaper-setup profiles (there can be many duplicates), and
            # free wlan0 for client mode.
            print(f'📶 Tearing down setup hotspot to connect to {ssid}...')
            self._remove_captive_portal_redirect()
            self._cleanup_legacy_setup_hotspots()
            # Ensure the interface is fully disconnected from AP mode
            self._nmcli(['device', 'disconnect', interface])

            # The radio needs time to transition from AP back to managed/station
            # mode.  On RPi Zero W this can take several seconds.
            print('⏳ Waiting for radio to transition from AP to client mode...')
            time.sleep(5)

            # Force a fresh scan so NM discovers nearby networks after the
            # radio has been in AP mode (no scan results exist yet).
            self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
            time.sleep(3)

            # 'nmcli device wifi connect' creates a new NM profile which requires
            # settings.modify.system — must use sudo nmcli, not plain nmcli.
            connect_cmd = ['device', 'wifi', 'connect', ssid, 'ifname', interface]
            if password:
                connect_cmd += ['password', password]
            if hidden:
                connect_cmd += ['hidden', 'yes']

            # Try up to 3 times — the first attempt often fails because the
            # radio hasn't fully settled after AP teardown.
            max_attempts = 3
            connect_result = None
            for attempt in range(1, max_attempts + 1):
                print(f'📡 WiFi connect attempt {attempt}/{max_attempts} to {ssid}...')
                connect_result = self._nmcli(connect_cmd, timeout=45)
                if connect_result is not None and connect_result.returncode == 0:
                    print(f'✅ nmcli connect command succeeded on attempt {attempt}')
                    break
                error_hint = ''
                if connect_result is not None:
                    error_hint = (connect_result.stderr or connect_result.stdout or '').strip()
                print(f'⚠️ WiFi connect attempt {attempt} failed: {error_hint}')
                if attempt < max_attempts:
                    # Rescan and retry after a short delay
                    time.sleep(5)
                    self._nmcli(['device', 'wifi', 'rescan', 'ifname', interface])
                    time.sleep(3)

            if connect_result is None or connect_result.returncode != 0:
                error_msg = 'Failed to connect to Wi-Fi network'
                if connect_result is not None and connect_result.stderr:
                    error_msg = connect_result.stderr.strip() or error_msg
                elif connect_result is not None and connect_result.stdout:
                    error_msg = connect_result.stdout.strip() or error_msg
                print(f'❌ WiFi connect failed after {max_attempts} attempts: {error_msg}')
                _wifi_connect_state['status'] = 'failed'
                _wifi_connect_state['message'] = error_msg
                # Restore hotspot so user can try again.
                self._bring_up_setup_hotspot(interface)
                return

            # Give NetworkManager a moment to fully establish the connection
            # (DHCP lease, DNS, etc.).
            print('⏳ Waiting for DHCP/DNS to settle...')
            time.sleep(8)

            # Poll for connection status (NM may still be negotiating)
            connected = False
            final_status = {}
            for poll in range(6):
                final_status = current_wifi_status(interface)
                if final_status.get('connected'):
                    connected = True
                    break
                time.sleep(3)

            if connected:
                try:
                    if os.path.exists(self.setup_mode_flag_path):
                        os.remove(self.setup_mode_flag_path)
                except OSError:
                    pass
                _wifi_connect_state['status'] = 'connected'
                _wifi_connect_state['connection'] = final_status.get('connection', ssid)
                _wifi_connect_state['message'] = f'Connected to {final_status.get("connection", ssid)}'
                print(f'✅ Setup Wi-Fi connected to {final_status.get("connection", ssid)}')
                # Clean up all leftover mempaper-setup profiles
                self._cleanup_legacy_setup_hotspots()
                self._nmcli(['connection', 'delete', 'mempaper-setup'])
                if self.e_ink_enabled:
                    threading.Thread(
                        target=self._display_onboarding_connected_screen,
                        daemon=True,
                    ).start()
            else:
                # nmcli reported success but device status doesn't show connected.
                # The profile IS saved — try activating it by name as a last resort.
                print(f'⚠️ nmcli succeeded but device not connected yet — trying connection up by name...')
                self._nmcli(['connection', 'up', ssid, 'ifname', interface], timeout=30)
                time.sleep(10)
                final_status = current_wifi_status(interface)
                if final_status.get('connected'):
                    try:
                        if os.path.exists(self.setup_mode_flag_path):
                            os.remove(self.setup_mode_flag_path)
                    except OSError:
                        pass
                    _wifi_connect_state['status'] = 'connected'
                    _wifi_connect_state['connection'] = final_status.get('connection', ssid)
                    _wifi_connect_state['message'] = f'Connected to {final_status.get("connection", ssid)}'
                    print(f'✅ Setup Wi-Fi connected via fallback: {final_status.get("connection", ssid)}')
                    self._cleanup_legacy_setup_hotspots()
                    self._nmcli(['connection', 'delete', 'mempaper-setup'])
                    if self.e_ink_enabled:
                        threading.Thread(
                            target=self._display_onboarding_connected_screen,
                            daemon=True,
                        ).start()
                else:
                    _wifi_connect_state['status'] = 'failed'
                    _wifi_connect_state['message'] = 'Connection attempt did not complete — check credentials'
                    self._bring_up_setup_hotspot(interface)
        
        # Add CORS headers to all responses (MUST BE FIRST)
        @self.app.after_request
        def add_cors_headers(response):
            """Add CORS headers to allow cross-origin requests."""
            try:
                # Get the origin from the request, or use wildcard if not present
                origin = request.headers.get('Origin')
                if origin:
                    response.headers['Access-Control-Allow-Origin'] = origin
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
                else:
                    response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            except Exception as e:
                print(f"❌ Error adding CORS headers: {type(e).__name__}: {str(e)}")
                traceback.print_exc()
            return response
        
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

        @self.app.route('/setup')
        def setup_wifi_page():
            """Public Wi-Fi onboarding page (only available in setup mode)."""
            if not setup_mode_enabled():
                return redirect(url_for('dashboard'))

            setup_data = setup_mode_payload()
            # Collect setup_* keys from all languages for client-side i18n
            setup_i18n = {}
            for lang_code, lang_dict in translations.items():
                setup_i18n[lang_code] = {k: v for k, v in lang_dict.items()
                                         if k.startswith('setup_') or k == 'onboarding_select_language'}
            return render_template(
                'setup_wifi.html',
                ssid=setup_data.get('ssid', 'mempaper-0000'),
                dark_mode=self.config.get('color_mode_dark', True),
                setup_i18n_json=json.dumps(setup_i18n, ensure_ascii=False),
            )

        # Captive-portal detection endpoints used by Android / iOS / Windows.
        @self.app.route('/generate_204')
        @self.app.route('/hotspot-detect.html')
        @self.app.route('/ncsi.txt')
        @self.app.route('/connecttest.txt')
        @self.app.route('/library/test/success.html')  # iOS
        @self.app.route('/success.txt')                # macOS Sonoma
        @self.app.route('/canonical.html')             # Windows 11
        def captive_portal_redirect():
            if setup_mode_enabled():
                # Auto-open mode: force captive-portal redirects so devices
                # launch the setup page immediately after joining the hotspot.
                auto_open_portal = bool(
                    self.config.get('wifi_setup_auto_open_portal', True)
                )

                # Some mobile OSes aggressively drop Wi-Fi networks that fail
                # internet checks. In stable mode, answer probe endpoints
                # with expected success content so clients stay connected.
                prefer_stable_connection = bool(
                    self.config.get('wifi_setup_prefer_stable_connection', True)
                )

                user_agent = (request.headers.get('User-Agent') or '').lower()
                is_android_client = 'android' in user_agent

                # Android clients can be more aggressive about dropping
                # captive/no-internet networks. If stability mode is enabled,
                # prefer stable probe responses for Android instead of redirects.
                if auto_open_portal and not (prefer_stable_connection and is_android_client):
                    return redirect(url_for('setup_wifi_page'), code=302)

                if prefer_stable_connection:
                    path = request.path
                    if path == '/generate_204':
                        return '', 204
                    if path in ('/hotspot-detect.html', '/library/test/success.html'):
                        return '<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>', 200
                    if path == '/ncsi.txt':
                        return 'Microsoft NCSI', 200
                    if path == '/connecttest.txt':
                        return 'Microsoft Connect Test', 200
                    if path == '/success.txt':
                        return 'success', 200
                    if path == '/canonical.html':
                        return '<html><body>Success</body></html>', 200

                return redirect(url_for('setup_wifi_page'), code=302)
            return '', 204

        # Catch-all: any request to an unknown host while in setup mode
        # triggers the captive portal popup on Android / iOS / Windows.
        #
        # IMPORTANT: captive-portal probe paths (e.g. /generate_204) must be
        # allowed through so the dedicated route handler can return the correct
        # status code.  If we redirect them here, Android sees a 302 instead of
        # 204, marks the network as "no internet", and disconnects.
        _CAPTIVE_PROBE_PATHS = {
            '/generate_204',
            '/hotspot-detect.html',
            '/ncsi.txt',
            '/connecttest.txt',
            '/library/test/success.html',
            '/success.txt',
            '/canonical.html',
        }

        @self.app.before_request
        def captive_portal_catch_all():
            if not setup_mode_enabled():
                return None
            # Let captive-portal probe paths reach their dedicated handler
            if request.path in _CAPTIVE_PROBE_PATHS:
                return None
            host = request.host.split(':')[0]
            # Pass through requests already destined for the Pi
            local_hosts = {'192.168.12.1', '10.42.0.1', 'localhost', '127.0.0.1'}
            if host in local_hosts:
                return None
            # Anything else: redirect to setup page
            return redirect(url_for('setup_wifi_page'), code=302)

        @self.app.route('/api/setup/wifi/scan', methods=['GET'])
        def setup_wifi_scan():
            if not setup_mode_enabled():
                return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

            interface = detect_wifi_interface()
            networks = scan_wifi_networks(interface)
            status = current_wifi_status(interface)

            return jsonify({
                'success': True,
                'interface': interface,
                'networks': networks,
                'status': status,
            })

        @self.app.route('/api/setup/wifi/connect', methods=['POST'])
        def setup_wifi_connect():
            if not setup_mode_enabled():
                return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

            data = request.json or {}
            ssid = (data.get('ssid') or '').strip()
            password = data.get('password', '')
            hidden = bool(data.get('hidden', False))
            language = (data.get('language') or '').strip()

            if not ssid:
                return jsonify({'success': False, 'message': 'SSID is required'}), 400
            if password and len(password) < 8:
                return jsonify({'success': False, 'message': 'Wi-Fi password must be at least 8 characters'}), 400

            # Persist selected language to config so the whole app uses it.
            if language and language in ('en', 'de', 'es', 'fr', 'it'):
                self.config_manager.set('language', language)
                self.config_manager.save_config()
                self.config['language'] = language
                self.translations = translations.get(language, translations['en'])
                # Recreate image renderer so dashboard images use the new language
                self.image_renderer = ImageRenderer(self.config, self.translations)

            interface = detect_wifi_interface()

            # Reset state and fire background thread BEFORE touching the radio.
            # This ensures the HTTP response is sent while hotspot is still up.
            _wifi_connect_state['status'] = 'connecting'
            _wifi_connect_state['message'] = f'Connecting to {ssid}...'
            _wifi_connect_state['connection'] = ''
            self._wifi_connect_pending = True  # signal recovery monitor to probe immediately on failure
            threading.Thread(
                target=apply_wifi_credentials_background,
                args=(interface, ssid, password, hidden),
                daemon=True,
            ).start()

            return jsonify({
                'success': True,
                'connecting': True,
                'message': f'Connecting to {ssid}... please wait',
            })

        @self.app.route('/api/setup/wifi/connect_status', methods=['GET'])
        def setup_wifi_connect_status():
            """Poll this after posting to /connect to find out the result."""
            return jsonify({
                'success': True,
                'status': _wifi_connect_state['status'],
                'message': _wifi_connect_state['message'],
                'connection': _wifi_connect_state['connection'],
            })

        @self.app.route('/api/setup/status', methods=['GET'])
        def setup_wifi_status():
            interface = detect_wifi_interface()
            return jsonify({
                'success': True,
                'setup_mode': setup_mode_enabled(),
                'interface': interface,
                'wifi': current_wifi_status(interface),
            })

        @self.app.route('/api/setup/admin_needed', methods=['GET'])
        def setup_admin_needed():
            """Return whether first-time admin creation is still required.
            Safe to call at any time — never exposes credentials."""
            needed = not self.auth_manager.password_manager.is_password_set()
            return jsonify({'success': True, 'admin_needed': needed})

        @self.app.route('/api/setup/create_admin', methods=['POST'])
        def setup_create_admin():
            """Create the first admin user.  Only allowed when no user exists yet,
            so this endpoint cannot be used to hijack an already-configured device."""
            if not setup_mode_enabled():
                return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

            # Hard guard: refuse if any user already exists.
            if self.auth_manager.password_manager.is_password_set():
                return jsonify({
                    'success': False,
                    'message': 'Admin user already configured — use the settings page to manage users.',
                }), 403

            data = request.json or {}
            username = (data.get('username') or '').strip()
            password = data.get('password', '')
            confirm  = data.get('confirm_password', '')

            if not username:
                return jsonify({'success': False, 'message': 'Username is required'}), 400
            if len(username) < 3:
                return jsonify({'success': False, 'message': 'Username must be at least 3 characters'}), 400
            if len(password) < 8:
                return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
            if password != confirm:
                return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

            ok = self.auth_manager.password_manager.create_user(username, password)
            if not ok:
                return jsonify({'success': False, 'message': 'Failed to save user — check logs'}), 500

            print(f"✅ Setup: first admin user '{username}' created via onboarding portal")
            return jsonify({'success': True, 'message': f"User '{username}' created successfully"})

        @self.app.route('/api/setup/reset_device', methods=['POST'])
        def setup_reset_device():
            """Reset admin credentials and sensitive user data.

            Only allowed while the device is in setup/hotspot mode so that a
            user who forgot their admin password can recover without SSH access.
            """
            if not setup_mode_enabled():
                return jsonify({'success': False, 'message': 'Setup mode is not active'}), 403

            try:
                self._perform_user_data_reset()
                print("✅ Setup: device reset via onboarding portal")
                return jsonify({'success': True, 'message': 'Device reset successful'})
            except Exception as e:
                print(f"❌ Setup reset failed: {e}")
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/image')
        @allow_public_or_auth(self.auth_manager, self.config_manager)
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
        @allow_public_or_auth(self.auth_manager, self.config_manager)
        def dashboard():
            """Serve the main dashboard web page."""
            if setup_mode_enabled() and not self.auth_manager.is_authenticated():
                return redirect(url_for('setup_wifi_page'))

            display_status = "enabled" if self.e_ink_enabled else "disabled"
            display_icon = "🖥️" if self.e_ink_enabled else "🚫"
            
            # Get current language and orientation
            lang = self.config.get("language", "en")
            # Use web_orientation for the dashboard view
            orientation = self.config.get("web_orientation", "vertical")
            current_translations = translations.get(lang, translations["en"])
            
            # Get current block height for cache-busting
            block_height = self.current_block_height if self.current_block_height else 0
            
            # Check if user is authenticated (for showing/hiding logout button)
            is_authenticated = self.auth_manager.is_authenticated()
            
            return render_template('dashboard.html',
                                 translations=current_translations,
                                 display_icon=display_icon,
                                 e_ink_enabled=self.e_ink_enabled,
                                 # This orientation determines the CSS class for layout
                                 orientation=orientation,
                                 block_height=block_height,
                                 is_authenticated=is_authenticated,
                                 show_wallet=self.config.get('show_wallet_balances_block', False),
                                 show_bitaxe=self.config.get('show_bitaxe_block', False),
                                 show_donations=self.config.get('show_donation_block', False),
                                 dark_mode=self.config.get('color_mode_dark', True))
        
        @self.app.route('/config')
        @require_web_auth(self.auth_manager)
        def config_page():
            """Serve the configuration page."""
            # Get current language
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('config.html', 
                                 translations=current_translations,
                                 dark_mode=self.config.get('color_mode_dark', True))
        
        @self.app.route('/login')
        def login_page():
            """Serve the login page."""
            # If already authenticated, redirect to config page
            if self.auth_manager.is_authenticated():
                return redirect(url_for('config_page'))
            
            # Get current language
            lang = self.config.get("language", "en")
            current_translations = translations.get(lang, translations["en"])
            
            return render_template('login.html', translations=current_translations,
                                 dark_mode=self.config.get('color_mode_dark', True),
                                 public_dashboard=self.config.get('public_dashboard', False))
        
        @self.app.route('/api/login', methods=['POST', 'OPTIONS'])
        @require_rate_limit(self.auth_manager)
        def login():
            """Handle login requests."""
            
            # Handle CORS preflight
            if request.method == 'OPTIONS':
                response = jsonify({'status': 'ok'})
                response.headers['Access-Control-Allow-Origin'] = '*'
                response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
                return response
            
            try:
                # Try to parse JSON
                try:
                    data = request.json
                except Exception as json_err:
                    return jsonify({'success': False, 'message': 'Invalid JSON in request'}), 400
                
                username = data.get('username', '')
                password = data.get('password', '')
                
                # Try to authenticate
                try:
                    auth_result = self.auth_manager.login(username, password)
                except Exception as auth_err:
                    traceback.print_exc()
                    return jsonify({'success': False, 'message': f'Authentication error: {str(auth_err)}'}), 500
                
                if auth_result:
                    # Determine redirect: if public dashboard is on, login is only for config access
                    public_dashboard = self.config.get('public_dashboard', False)
                    redirect_url = '/config' if public_dashboard else '/'
                    response_data = {'success': True, 'message': 'Login successful', 'redirect': redirect_url}
                    
                    # Create response with explicit handling
                    try:
                        response = jsonify(response_data)
                        
                        # Explicitly set headers
                        response.headers['Content-Type'] = 'application/json'
                        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                        
                        # Force session to be saved
                        session.modified = True
                        
                        return response
                        
                    except Exception as resp_err:
                        traceback.print_exc()
                        # Try to return a simple response
                        try:
                            return '{"success": true, "message": "Login successful"}', 200, {'Content-Type': 'application/json'}
                        except:
                            raise resp_err
                else:
                    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
                    
            except Exception as e:
                traceback.print_exc()
                try:
                    return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500
                except:
                    # If even jsonify fails, return raw JSON
                    return '{"success": false, "message": "Server error"}', 500, {'Content-Type': 'application/json'}
        
        @self.app.route('/api/logout', methods=['POST'])
        def logout():
            """Handle logout requests."""
            public_dashboard = self.config.get('public_dashboard', False)
            self.auth_manager.logout()
            return jsonify({
                'success': True,
                'message': 'Logout successful',
                'public_dashboard': public_dashboard
            })

        # User management endpoints
        @self.app.route('/api/users', methods=['GET'])
        @require_auth(self.auth_manager)
        def list_users():
            try:
                users = self.auth_manager.password_manager.list_users()
                return jsonify({'success': True, 'users': users})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/users', methods=['POST'])
        @require_auth(self.auth_manager)
        def create_user():
            try:
                data = request.json or {}
                username = (data.get('username') or '').strip()
                password = data.get('password', '')
                if not username:
                    return jsonify({'success': False, 'message': 'Username is required'}), 400
                if len(password) < 8:
                    return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
                if self.auth_manager.password_manager.create_user(username, password):
                    return jsonify({'success': True})
                return jsonify({'success': False, 'message': 'Failed to create user'}), 500
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/users/<username>/password', methods=['POST'])
        @require_auth(self.auth_manager)
        def change_user_password(username):
            try:
                data = request.json or {}
                password = data.get('password', '')
                if len(password) < 8:
                    return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
                users = self.auth_manager.password_manager.list_users()
                if username not in users:
                    return jsonify({'success': False, 'message': 'User not found'}), 404
                if self.auth_manager.password_manager.create_user(username, password):
                    return jsonify({'success': True})
                return jsonify({'success': False, 'message': 'Failed to update password'}), 500
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/users/<username>/rename', methods=['POST'])
        @require_auth(self.auth_manager)
        def rename_user(username):
            try:
                data = request.json or {}
                new_username = (data.get('new_username') or '').strip()
                if not new_username:
                    return jsonify({'success': False, 'message': 'New username is required'}), 400
                users_dict = self.auth_manager.password_manager._get_users()
                if username not in users_dict:
                    return jsonify({'success': False, 'message': 'User not found'}), 404
                if new_username in users_dict and new_username != username:
                    return jsonify({'success': False, 'message': 'Username already taken'}), 409
                with self.config_manager.config_lock:
                    u = dict(self.config_manager.config.get('admin_users') or {})
                    u[new_username] = u.pop(username)
                    self.config_manager.config['admin_users'] = u
                self.config_manager.save_config()
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        @self.app.route('/api/users/<username>', methods=['DELETE'])
        @require_auth(self.auth_manager)
        def delete_user(username):
            try:
                users = self.auth_manager.password_manager.list_users()
                if username not in users:
                    return jsonify({'success': False, 'message': 'User not found'}), 404
                if len(users) <= 1:
                    return jsonify({'success': False, 'message': 'Cannot delete the last user'}), 400
                with self.config_manager.config_lock:
                    u = dict(self.config_manager.config.get('admin_users') or {})
                    u.pop(username, None)
                    self.config_manager.config['admin_users'] = u
                self.config_manager.save_config()
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 400

        # Lightning Donation Webhook
        @self.app.route('/api/donation-webhook', methods=['POST'])
        def donation_webhook():
            """Receive LNbits payment webhook and broadcast donation to connected clients."""
            # force=True parses JSON regardless of Content-Type header,
            # which LNbits sometimes omits.
            data = request.get_json(force=True, silent=True) or {}

            # Debug: log raw body + parsed fields so misconfigured LNbits is easy to diagnose
            raw_body = request.get_data(as_text=True)
            print(f"⚡ Donation webhook received — body: {raw_body[:500]!r}")

            self._process_donation_payload(data)
            return jsonify({'success': True}), 200

        @self.app.route('/api/donations', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_donations():
            """Return donation history (most recent first)."""
            return jsonify({
                'donations': self._donation_history,
                'latest': self._latest_donation,
            })

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
                # Get current language and translations
                lang = self.config.get("language", "en")
                current_translations = translations.get(lang, translations["en"])
                
                # Get the regular configuration
                config_data = self.config_manager.get_current_config()
                
                # Add wallet addresses from secure configuration if available
                if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api.secure_config_manager:
                    secure_config = self.image_renderer.wallet_api.secure_config_manager.load_secure_config()
                    if secure_config and 'wallet_balance_addresses_with_comments' in secure_config:
                        wallet_addresses = secure_config['wallet_balance_addresses_with_comments']
                        config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                        
                        # Include cached balances in the configuration
                        try:
                            if hasattr(self.image_renderer, 'wallet_api') and self.image_renderer.wallet_api:
                                cached_data = self.image_renderer.wallet_api.get_cached_wallet_balances()
                                
                                if cached_data and 'addresses' in cached_data:
                                    address_balances = {}
                                    for addr_info in cached_data['addresses']:
                                        if 'address' in addr_info and 'balance_btc' in addr_info:
                                            address_balances[addr_info['address']] = addr_info['balance_btc']
                                    
                                    if 'xpubs' in cached_data:
                                        for xpub_info in cached_data['xpubs']:
                                            if 'xpub' in xpub_info and 'balance_btc' in xpub_info:
                                                address_balances[xpub_info['xpub']] = xpub_info['balance_btc']
                                    
                                    for addr_entry in wallet_addresses:
                                        if 'address' in addr_entry:
                                            address = addr_entry['address']
                                            addr_entry['cached_balance'] = address_balances.get(address, 0.0)
                                    
                                    config_data['wallet_balance_addresses_with_comments'] = wallet_addresses
                                    config_data['wallet_total_balance'] = cached_data.get('total_btc', 0.0)
                                    
                        except Exception as balance_error:
                            pass  # Continue without cached balances if there's an error
                
                from flask import session as _session
                return jsonify({
                    'config': config_data,
                    'schema': self.config_manager.get_config_schema(current_translations),
                    'categories': self.config_manager.get_categories(current_translations),
                    'color_options': self.config_manager.get_color_options(),
                    'current_user': _session.get('username', '')
                })
            except Exception as e:
                print(f"Error in get_config: {e}")
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
                
                new_config = request.json or {}
                if not isinstance(new_config, dict):
                    return jsonify({'success': False, 'message': 'Invalid configuration payload'}), 400

                # Handle admin username rename server-side so the admin_users mapping and
                # the current session stay in sync even for legacy sessions missing username.
                old_admin_username = str((old_config or {}).get('admin_username') or '').strip()
                requested_admin_username = str(new_config.get('admin_username') or '').strip()
                session_username = str(session.get('username') or '').strip()

                if requested_admin_username:
                    new_config['admin_username'] = requested_admin_username

                if old_admin_username and requested_admin_username and requested_admin_username != old_admin_username:
                    with self.config_manager.config_lock:
                        admin_users = dict(self.config_manager.config.get('admin_users') or {})

                    if admin_users:
                        if not session_username:
                            return jsonify({'success': False, 'message': 'Session username is missing'}), 401

                        if session_username not in admin_users:
                            return jsonify({'success': False, 'message': 'Authenticated user not found'}), 403

                        rename_source = session_username

                        if requested_admin_username in admin_users and requested_admin_username != rename_source:
                            return jsonify({'success': False, 'message': 'Username already taken'}), 409

                        if requested_admin_username != rename_source:
                            admin_users[requested_admin_username] = admin_users.pop(rename_source)
                        new_config['admin_users'] = admin_users

                if self.config_manager.save_config(new_config):
                    if requested_admin_username and (
                        requested_admin_username != old_admin_username or not session_username
                    ):
                        session['username'] = requested_admin_username

                    # Get validated new config from manager
                    validated_new_config = self.config_manager.get_current_config()

                    # Trigger image-affecting change detection BEFORE updating self.config,
                    # so _on_config_change can compare old vs new correctly (opsec mode, etc.)
                    self._on_config_change(validated_new_config)

                    # Update local config reference (may already be set by _on_config_change)
                    self.config = self.config_manager.get_current_config()

                    # Update auth manager config
                    self.auth_manager.config = self.config

                    # Clean up cache for removed wallet addresses before reinitializing
                    if old_config:
                        self._cleanup_removed_wallet_caches(old_config, new_config)

                    # Reinitialize components if needed
                    self._reinitialize_after_config_change(old_config)

                    # Push updated dynamic data (bitaxe, found blocks) to config page immediately
                    self._emit_config_page_updates()

                    # Fetch fresh wallet balances in background and push when ready
                    def _bg_wallet_refresh_after_save():
                        try:
                            # Snapshot current cache BEFORE fetching fresh data so the
                            # frontend can compare and only toast on genuine changes.
                            cached_before = self.image_renderer.wallet_api.get_cached_wallet_balances() or {}
                            fresh = self.image_renderer.wallet_api.fetch_wallet_balances(startup_mode=True)
                            if fresh and not fresh.get('error'):
                                self.image_renderer.wallet_api.update_cache(fresh)
                                if hasattr(self, 'socketio') and self.socketio:
                                    emit_data = dict(fresh)
                                    emit_data['after_config_save'] = True
                                    emit_data['prev_addresses'] = cached_before.get('addresses', [])
                                    emit_data['prev_xpubs'] = cached_before.get('xpubs', [])
                                    self.socketio.emit('wallet_balance_updated', emit_data, room='authenticated')
                        except Exception as e:
                            print(f"⚠️ Background wallet refresh after config save failed: {e}")
                    threading.Thread(target=_bg_wallet_refresh_after_save, daemon=True).start()

                    return jsonify({
                        'success': True,
                        'message': 'Configuration saved successfully',
                        'current_user': session.get('username', '')
                    })
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

                # Validate that PIL (or its ImageMagick fallback) can actually open the file.
                # This catches missing codec support (e.g. WebP on Pi without libwebp-dev)
                # before the broken file makes it into the meme pool.
                try:
                    self.image_renderer._open_image_robust(upload_path)
                except Exception as img_err:
                    os.remove(upload_path)
                    hint = ''
                    if file_ext == 'webp':
                        hint = (' WebP requires libwebp support in Pillow. '
                                'Run: sudo apt install libwebp-dev && '
                                'pip install --no-binary :all: pillow')
                    return jsonify({
                        'success': False,
                        'message': f'Image cannot be opened by the server: {img_err}.{hint}'
                    }), 400

                self.image_renderer.invalidate_meme_cache()

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
                search = request.args.get('search', '', type=str).strip().lower()
                
                memes_dir = os.path.join('static', 'memes')
                if not os.path.exists(memes_dir):
                    return jsonify({'memes': [], 'total': 0, 'page': page, 'per_page': per_page})
                
                # Use cached file list + metadata from image_renderer
                all_files = list(self.image_renderer.get_cached_meme_files())
                
                # If search term provided, filter by cached metadata and filename
                if search:
                    meta_map = self.image_renderer.get_cached_meme_meta()
                    filtered = []
                    for filename in all_files:
                        stem = os.path.splitext(filename)[0]
                        searchable = meta_map.get(stem, [])
                        if (any(search in s for s in searchable)
                                or search in filename.lower()):
                            filtered.append(filename)
                    all_files = filtered
                
                # Already sorted by the cache
                
                # Calculate pagination
                total_files = len(all_files)
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                page_files = all_files[start_idx:end_idx]
                
                tags_map = self.image_renderer.get_cached_meme_tags()
                api_tags_map = self.image_renderer.get_cached_meme_api_tags()
                memes = []
                for filename in page_files:
                    file_path = os.path.join(memes_dir, filename)
                    try:
                        file_size = os.path.getsize(file_path)
                        file_stat = os.stat(file_path)
                        stem = os.path.splitext(filename)[0]

                        meme_data = {
                            'filename': filename,
                            'size': file_size,
                            'url': f'/static/memes/{filename}',
                            'thumb_url': f'/api/thumb/{filename}?v={int(file_stat.st_mtime)}',
                            'last_modified': file_stat.st_mtime,
                            'tags': tags_map.get(stem, []),
                            'api_tags': api_tags_map.get(stem, [])
                        }

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
        
        @self.app.route('/api/thumb/<filename>', methods=['GET'])
        def serve_meme_thumb(filename):
            """Serve a cached 200×200 WebP thumbnail, generating it on first request."""
            # Auth check without session refresh — avoids Set-Cookie which blocks browser caching
            if not self.auth_manager.is_authenticated():
                return jsonify({'error': 'Authentication required'}), 401

            from PIL import Image

            filename = secure_filename(filename)
            orig_path = os.path.join('static', 'memes', filename)
            if not os.path.exists(orig_path):
                return "Not found", 404

            thumb_dir = os.path.join('static', 'memes', 'thumbs')
            os.makedirs(thumb_dir, exist_ok=True)

            stem = os.path.splitext(filename)[0]
            thumb_path = os.path.join(thumb_dir, f'{stem}.webp')

            orig_mtime = os.stat(orig_path).st_mtime
            thumb_ok = (
                os.path.exists(thumb_path)
                and os.stat(thumb_path).st_mtime >= orig_mtime
            )

            if not thumb_ok:
                try:
                    with Image.open(orig_path) as img:
                        # Preserve animation frames for GIFs by only taking frame 0
                        img.seek(0) if hasattr(img, 'seek') else None
                        img = img.convert('RGBA')
                        img.thumbnail((200, 200), Image.LANCZOS)
                        img.save(thumb_path, 'WEBP', quality=70)
                except Exception:
                    # Thumbnail generation failed — fall back to the original
                    response = send_file(orig_path)
                    response.headers['Cache-Control'] = 'private, max-age=3600'
                    return response

            # Build an ETag from the thumb file's mtime
            thumb_mtime = int(os.stat(thumb_path).st_mtime)
            etag = f'"{thumb_mtime}"'

            # Return 304 if the browser already has this version
            if request.headers.get('If-None-Match') == etag:
                from flask import Response as _Response
                return _Response(status=304, headers={
                    'ETag': etag,
                    'Cache-Control': 'private, max-age=31536000, immutable',
                })

            response = send_file(thumb_path, mimetype='image/webp')
            response.headers['ETag'] = etag
            # immutable + long max-age: browser skips the request entirely until ?v=mtime changes
            response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
            return response

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
                
                # Delete the file and its thumbnail
                os.remove(file_path)
                stem = os.path.splitext(filename)[0]
                thumb_path = os.path.join('static', 'memes', 'thumbs', f'{stem}.webp')
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)

                self.image_renderer.invalidate_meme_cache()

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

                old_stem = os.path.splitext(old_filename)[0]
                new_stem = os.path.splitext(new_filename)[0]

                # Track rename so metadata stays linked to UUID
                self.image_renderer.record_rename(old_stem, new_stem)

                # Update user tags key if it exists
                import json as _json
                user_tags_path = os.path.join('static', 'memes', '_user_tags.json')
                if os.path.exists(user_tags_path):
                    try:
                        with open(user_tags_path, encoding='utf-8') as fh:
                            user_tags = _json.load(fh)
                        if old_stem in user_tags:
                            user_tags[new_stem] = user_tags.pop(old_stem)
                            with open(user_tags_path, 'w', encoding='utf-8') as fh:
                                _json.dump(user_tags, fh, ensure_ascii=False, indent=2)
                    except (OSError, _json.JSONDecodeError):
                        pass

                self.image_renderer.invalidate_meme_cache()
                
                return jsonify({
                    'success': True,
                    'message': f'Meme renamed from {old_filename} to {new_filename}',
                    'old_filename': old_filename,
                    'new_filename': new_filename
                })
                
            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/meme-tags', methods=['POST'])
        @require_auth(self.auth_manager)
        def update_meme_tags():
            """Update tags for a meme."""
            try:
                data = request.json
                if not data or 'filename' not in data or 'tags' not in data:
                    return jsonify({'success': False, 'message': 'Missing filename or tags'}), 400
                filename = data['filename']
                tags = data['tags']
                if not isinstance(tags, list):
                    return jsonify({'success': False, 'message': 'Tags must be a list'}), 400
                stem = os.path.splitext(filename)[0]
                self.image_renderer.set_meme_tags(stem, tags)
                return jsonify({'success': True, 'tags': tags})
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
        
        @self.app.route('/api/opsec-thumb/<filename>', methods=['GET'])
        def serve_opsec_thumb(filename):
            """Serve a cached 200×200 WebP thumbnail for an OPSec image, generating on first request."""
            if not self.auth_manager.is_authenticated():
                return jsonify({'error': 'Authentication required'}), 401

            from PIL import Image

            filename = secure_filename(filename)
            orig_path = os.path.join('static', 'opsec', filename)
            if not os.path.exists(orig_path):
                return "Not found", 404

            thumb_dir = os.path.join('static', 'opsec', 'thumbs')
            os.makedirs(thumb_dir, exist_ok=True)

            stem = os.path.splitext(filename)[0]
            thumb_path = os.path.join(thumb_dir, f'{stem}.webp')

            orig_mtime = os.stat(orig_path).st_mtime
            thumb_ok = (
                os.path.exists(thumb_path)
                and os.stat(thumb_path).st_mtime >= orig_mtime
            )

            if not thumb_ok:
                try:
                    with Image.open(orig_path) as img:
                        img.seek(0) if hasattr(img, 'seek') else None
                        img = img.convert('RGBA')
                        img.thumbnail((200, 200), Image.LANCZOS)
                        img.save(thumb_path, 'WEBP', quality=70)
                except Exception:
                    response = send_file(orig_path)
                    response.headers['Cache-Control'] = 'private, max-age=3600'
                    return response

            thumb_mtime = int(os.stat(thumb_path).st_mtime)
            etag = f'"{thumb_mtime}"'

            if request.headers.get('If-None-Match') == etag:
                from flask import Response as _Response
                return _Response(status=304, headers={
                    'ETag': etag,
                    'Cache-Control': 'private, max-age=31536000, immutable',
                })

            response = send_file(thumb_path, mimetype='image/webp')
            response.headers['ETag'] = etag
            response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
            return response

        @self.app.route('/api/upload-opsec', methods=['POST'])
        @require_auth(self.auth_manager)
        def upload_opsec():
            """Handle OPSec image uploads."""
            try:
                if 'file' not in request.files:
                    return jsonify({'success': False, 'message': 'No file provided'}), 400

                file = request.files['file']
                if file.filename == '':
                    return jsonify({'success': False, 'message': 'No file selected'}), 400

                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

                if file_ext not in allowed_extensions:
                    return jsonify({
                        'success': False,
                        'message': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                    }), 400

                filename = secure_filename(file.filename)
                upload_path = os.path.join('static', 'opsec', filename)
                os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                file.save(upload_path)

                return jsonify({
                    'success': True,
                    'message': f'OPSec image uploaded successfully: {filename}',
                    'filename': filename
                })

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/opsec-images', methods=['GET'])
        @require_auth(self.auth_manager)
        def list_opsec_images():
            """List all uploaded OPSec images with pagination support."""
            try:
                page = request.args.get('page', 1, type=int)
                per_page = request.args.get('per_page', 50, type=int)

                opsec_dir = os.path.join('static', 'opsec')
                if not os.path.exists(opsec_dir):
                    return jsonify({'images': [], 'total': 0, 'page': page, 'per_page': per_page, 'has_next': False, 'has_prev': False})

                all_filenames = sorted([
                    f for f in os.listdir(opsec_dir)
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
                ])

                total_files = len(all_filenames)
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                page_filenames = all_filenames[start_idx:end_idx]

                images = []
                for filename in page_filenames:
                    file_path = os.path.join(opsec_dir, filename)
                    try:
                        file_stat = os.stat(file_path)
                        file_size = file_stat.st_size
                        file_mtime = int(file_stat.st_mtime)
                    except Exception:
                        file_size = 0
                        file_mtime = 0
                    images.append({'filename': filename, 'size': file_size, 'url': f'/static/opsec/{filename}', 'thumb_url': f'/api/opsec-thumb/{filename}?v={file_mtime}'})

                return jsonify({
                    'images': images,
                    'total': total_files,
                    'page': page,
                    'per_page': per_page,
                    'has_next': end_idx < total_files,
                    'has_prev': page > 1,
                })

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/delete-opsec/<filename>', methods=['DELETE'])
        @require_auth(self.auth_manager)
        def delete_opsec(filename):
            """Delete a specific OPSec image."""
            try:
                filename = secure_filename(filename)
                file_path = os.path.join('static', 'opsec', filename)

                if not os.path.exists(file_path):
                    return jsonify({'success': False, 'message': 'File not found'}), 404

                os.remove(file_path)
                stem = os.path.splitext(filename)[0]
                thumb_path = os.path.join('static', 'opsec', 'thumbs', f'{stem}.webp')
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                return jsonify({'success': True, 'message': f'OPSec image deleted: {filename}'})

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/opsec-hashes', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_opsec_hashes():
            """Get SHA-256 hashes of all existing OPSec images for duplicate detection."""
            try:
                import hashlib

                opsec_dir = os.path.join('static', 'opsec')
                if not os.path.exists(opsec_dir):
                    return jsonify({'hashes': {}})

                hashes = {}
                for filename in os.listdir(opsec_dir):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        file_path = os.path.join(opsec_dir, filename)
                        try:
                            sha256_hash = hashlib.sha256()
                            with open(file_path, "rb") as f:
                                for byte_block in iter(lambda: f.read(4096), b""):
                                    sha256_hash.update(byte_block)
                            hashes[sha256_hash.hexdigest()] = filename
                        except Exception as e:
                            print(f"Error hashing OPSec image {filename}: {e}")
                            continue

                return jsonify({'hashes': hashes})

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/download-opsec/<filename>', methods=['GET'])
        @require_auth(self.auth_manager)
        def download_opsec(filename):
            """Download a specific OPSec image file."""
            try:
                from flask import send_file
                filename = secure_filename(filename)
                file_path = os.path.join('static', 'opsec', filename)

                if not os.path.exists(file_path):
                    return jsonify({'success': False, 'message': 'File not found'}), 404

                return send_file(os.path.abspath(file_path), as_attachment=True, download_name=filename)

            except Exception as e:
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/rename-opsec', methods=['POST'])
        @require_auth(self.auth_manager)
        def rename_opsec():
            """Rename an OPSec image file."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'message': 'No data provided'}), 400

                old_filename = secure_filename(data.get('old_filename', ''))
                new_filename = secure_filename(data.get('new_filename', ''))

                if not old_filename or not new_filename:
                    return jsonify({'success': False, 'message': 'Invalid filenames'}), 400

                old_path = os.path.join('static', 'opsec', old_filename)
                new_path = os.path.join('static', 'opsec', new_filename)

                if not os.path.exists(old_path):
                    return jsonify({'success': False, 'message': 'File not found'}), 404

                if os.path.exists(new_path):
                    return jsonify({'success': False, 'message': 'A file with that name already exists'}), 409

                if old_filename == new_filename:
                    return jsonify({'success': False, 'message': 'New name is the same as old name'}), 400

                os.rename(old_path, new_path)
                return jsonify({
                    'success': True,
                    'message': f'OPSec image renamed: {old_filename} → {new_filename}',
                    'old_filename': old_filename,
                    'new_filename': new_filename
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
                        self.socketio.emit('wallet_balance_updated', cached_wallet_data, room='authenticated')
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
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500
        
        @self.app.route('/api/bitaxe/<ip>/best-diff', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_bitaxe_best_diff(ip):
            """Get the best difficulty for a specific Bitaxe miner."""
            try:
                if not ip:
                    return jsonify({'success': False, 'message': 'No IP provided'}), 400

                from lib.bitaxe_api import BitaxeAPI
                bitaxe_api = getattr(self.image_renderer, 'bitaxe_api', None) or BitaxeAPI()
                miner_info = bitaxe_api.get_miner_info(ip)

                best_diff = miner_info.get('best_diff', 0)
                online = miner_info.get('online', False)

                return jsonify({
                    'success': True,
                    'ip': ip,
                    'best_diff': best_diff,
                    'online': online
                })

            except Exception as e:
                print(f"Error in get_bitaxe_best_diff: {e}")
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500

        # ── Software Update Endpoints ────────────────────────────────

        @self.app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint for update polling."""
            return jsonify({
                'status': 'ok',
                'started': self._startup_timestamp,
            })

        @self.app.route('/api/update/current', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_current_version():
            """Get the currently checked-out git tag/commit."""
            try:
                project_dir = os.path.dirname(os.path.abspath(__file__))

                # Get current tag (if on a tag)
                try:
                    current_tag = subprocess.check_output(
                        ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                        cwd=project_dir, stderr=subprocess.DEVNULL
                    ).decode().strip()
                except subprocess.CalledProcessError:
                    current_tag = None

                # Get current commit hash
                current_commit = subprocess.check_output(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    cwd=project_dir, stderr=subprocess.DEVNULL
                ).decode().strip()

                return jsonify({
                    'success': True,
                    'current_tag': current_tag,
                    'current_commit': current_commit
                })
            except Exception as e:
                print(f"Error getting current version: {e}")
                return jsonify({'success': False, 'message': str(e)}), 500

        @self.app.route('/api/update/releases', methods=['GET'])
        @require_auth(self.auth_manager)
        def get_available_releases():
            """Fetch available releases from the git remote (GitHub or GitLab)."""
            try:
                project_dir = os.path.dirname(os.path.abspath(__file__))

                # Minimum version that supports web GUI updates — older releases
                # lack this feature and installing them would lock out the user.
                min_version = (1, 6, 0)

                def _parse_version(tag):
                    """Parse 'v1.7.0' into (1, 7, 0) tuple, or None on failure."""
                    try:
                        return tuple(int(x) for x in tag.lstrip('v').split('.'))
                    except (ValueError, AttributeError):
                        return None

                # Read remote URL from git config
                remote_url = subprocess.check_output(
                    ['git', 'remote', 'get-url', 'origin'],
                    cwd=project_dir, text=True
                ).strip().rstrip('.git').rstrip('/')

                is_gitlab = 'github.com' not in remote_url
                repo_url = remote_url
                platform = 'GitLab' if is_gitlab else 'GitHub'

                # Try fetching releases from the hosting API first
                # Optional: GIT_API_TOKEN in .env for private repo access
                api_token = os.getenv('GIT_API_TOKEN')
                if not api_token:
                    try:
                        from dotenv import dotenv_values
                        env_path = os.path.join(project_dir, '.env')
                        env_vars = dotenv_values(env_path)
                        api_token = env_vars.get('GIT_API_TOKEN')
                    except Exception:
                        pass

                api_releases = None
                try:
                    if 'github.com' in remote_url:
                        parts = remote_url.split('github.com/')[-1]
                        api_url = f'https://api.github.com/repos/{parts}/releases'
                        headers = {'Accept': 'application/vnd.github.v3+json'}
                        if api_token:
                            headers['Authorization'] = f'Bearer {api_token}'
                    else:
                        from urllib.parse import urlparse
                        parsed = urlparse(remote_url)
                        project_path = parsed.path.lstrip('/')
                        api_url = f'{parsed.scheme}://{parsed.hostname}/api/v4/projects/{requests.utils.quote(project_path, safe="")}/releases'
                        headers = {}
                        if api_token:
                            headers['PRIVATE-TOKEN'] = api_token

                    resp = requests.get(api_url, headers=headers, timeout=15)
                    resp.raise_for_status()
                    api_releases = resp.json()
                except requests.RequestException:
                    pass  # Fall back to local git tags

                if api_releases is not None:
                    # Build result from API response (has release notes, dates, etc.)
                    result = []
                    for rel in api_releases:
                        tag_name = rel.get('tag_name', '')
                        ver = _parse_version(tag_name)
                        if ver is not None and ver < min_version:
                            continue
                        result.append({
                            'tag': tag_name,
                            'name': rel.get('name', '') or tag_name,
                            'published_at': rel.get('released_at', '') if is_gitlab else rel.get('published_at', ''),
                            'body': rel.get('description', '') if is_gitlab else rel.get('body', ''),
                            'prerelease': rel.get('upcoming_release', False) if is_gitlab else rel.get('prerelease', False),
                            'draft': False if is_gitlab else rel.get('draft', False)
                        })
                else:
                    # Fallback: use local git tags (works for private repos)
                    subprocess.run(
                        ['git', 'fetch', '--tags', '--force'],
                        cwd=project_dir, capture_output=True, timeout=30
                    )
                    tag_output = subprocess.check_output(
                        ['git', 'tag', '-l', '--sort=-version:refname'],
                        cwd=project_dir, text=True
                    ).strip()

                    result = []
                    for tag_name in tag_output.splitlines():
                        tag_name = tag_name.strip()
                        if not tag_name:
                            continue
                        ver = _parse_version(tag_name)
                        if ver is not None and ver < min_version:
                            continue
                        # Get tag date
                        try:
                            date_str = subprocess.check_output(
                                ['git', 'log', '-1', '--format=%aI', tag_name],
                                cwd=project_dir, text=True
                            ).strip()
                        except subprocess.SubprocessError:
                            date_str = ''
                        result.append({
                            'tag': tag_name,
                            'name': tag_name,
                            'published_at': date_str,
                            'body': '',
                            'prerelease': False,
                            'draft': False
                        })

                return jsonify({'success': True, 'releases': result, 'repo_url': repo_url, 'platform': platform})
            except Exception as e:
                print(f"Error fetching releases: {e}")
                return jsonify({'success': False, 'message': f'Failed to fetch releases: {e}'}), 502

        @self.app.route('/api/update/install', methods=['POST'])
        @require_auth(self.auth_manager)
        def install_update():
            """Install a specific release by checking out its git tag."""
            if getattr(self, '_update_running', False):
                return jsonify({'success': False, 'message': 'Update already in progress'}), 409

            data = request.json or {}
            tag = data.get('tag', '').strip()
            if not tag:
                return jsonify({'success': False, 'message': 'No tag specified'}), 400

            project_dir = os.path.dirname(os.path.abspath(__file__))

            # Verify the tag exists before starting background work
            try:
                subprocess.check_call(
                    ['git', 'fetch', '--tags', '--force'],
                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
                subprocess.check_call(
                    ['git', 'rev-parse', f'refs/tags/{tag}'],
                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
            except subprocess.CalledProcessError:
                return jsonify({'success': False, 'message': f'Tag {tag} not found'}), 404

            def _emit(event, data):
                if self.socketio:
                    self.socketio.emit(event, data, room='authenticated')

            def _run_update():
                self._update_running = True
                try:
                    # Save rollback point
                    rollback_commit = subprocess.check_output(
                        ['git', 'rev-parse', 'HEAD'],
                        cwd=project_dir, stderr=subprocess.DEVNULL
                    ).decode().strip()

                    try:
                        rollback_tag = subprocess.check_output(
                            ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                            cwd=project_dir, stderr=subprocess.DEVNULL
                        ).decode().strip()
                    except subprocess.CalledProcessError:
                        rollback_tag = None

                    # Check if dependency files changed between current and target
                    deps_changed = False
                    apt_deps_changed = False
                    pillow_changed = False
                    try:
                        diff_result = subprocess.run(
                            ['git', 'diff', '--name-only', 'HEAD', f'refs/tags/{tag}', '--',
                             'requirements.txt', 'apt-requirements.txt'],
                            cwd=project_dir, capture_output=True, text=True
                        )
                        changed_files = diff_result.stdout.strip()
                        deps_changed = 'requirements.txt' in changed_files
                        apt_deps_changed = 'apt-requirements.txt' in changed_files
                        if deps_changed:
                            diff_content = subprocess.run(
                                ['git', 'diff', 'HEAD', f'refs/tags/{tag}', '--', 'requirements.txt'],
                                cwd=project_dir, capture_output=True, text=True
                            )
                            import re
                            pillow_changed = bool(re.search(r'^\+.*pillow==', diff_content.stdout, re.IGNORECASE | re.MULTILINE))
                    except Exception:
                        deps_changed = True
                        apt_deps_changed = True

                    # Git checkout
                    _emit('update_output', {'line': self.translations.get('checking_out_code', 'Checking out {tag}...').format(tag=tag), 'phase': 'git', 'header': True})
                    subprocess.check_call(
                        ['git', 'reset', '--hard'],
                        cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                    )
                    subprocess.check_call(
                        ['git', 'checkout', f'refs/tags/{tag}'],
                        cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                    )
                    _emit('update_output', {'line': self.translations.get('checked_out', 'Checked out {tag}').format(tag=tag), 'phase': 'git', 'header': True})

                    # Install apt dependencies if changed
                    apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                    if apt_deps_changed and os.path.exists(apt_req_file):
                        _emit('update_output', {'line': self.translations.get('installing_system_deps', 'Installing system dependencies...'), 'phase': 'apt', 'header': True})
                        try:
                            with open(apt_req_file) as f:
                                apt_pkgs = [
                                    line.strip() for line in f
                                    if line.strip() and not line.strip().startswith('#')
                                ]
                            if apt_pkgs:
                                proc = subprocess.Popen(
                                    ['sudo', 'apt-get', 'install', '-y', '--no-upgrade'] + apt_pkgs,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1
                                )
                                for line in proc.stdout:
                                    _emit('update_output', {'line': line.rstrip('\n'), 'phase': 'apt'})
                                proc.wait()
                                if proc.returncode != 0:
                                    _emit('update_output', {'line': self.translations.get('system_deps_warning', 'Warning: some system dependencies failed to install'), 'phase': 'apt', 'header': True})
                                else:
                                    _emit('update_output', {'line': self.translations.get('system_deps_installed', 'System dependencies installed'), 'phase': 'apt', 'header': True})
                        except Exception as apt_err:
                            _emit('update_output', {'line': f'Warning: {apt_err}', 'phase': 'apt'})

                    # Install pip dependencies
                    venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
                    requirements_file = os.path.join(project_dir, 'requirements.txt')

                    if os.path.exists(venv_pip) and os.path.exists(requirements_file):
                        _emit('update_output', {'line': self.translations.get('installing_python_deps', 'Installing Python dependencies...'), 'phase': 'pip', 'header': True})
                        try:
                            proc = subprocess.Popen(
                                [venv_pip, 'install', '-r', requirements_file],
                                cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1
                            )
                            for line in proc.stdout:
                                _emit('update_output', {'line': line.rstrip('\n'), 'phase': 'pip'})
                            proc.wait()
                            if proc.returncode != 0:
                                # Rollback on pip failure
                                _emit('update_output', {'line': self.translations.get('pip_install_failed_rollback', 'pip install failed, rolling back...'), 'phase': 'pip', 'header': True})
                                subprocess.check_call(
                                    ['git', 'checkout', rollback_commit],
                                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                                )
                                _emit('update_done', {
                                    'success': False,
                                    'error': self.translations.get('dep_install_failed_rollback', 'Dependency installation failed. Rolled back to previous version.')
                                })
                                return
                            _emit('update_output', {'line': self.translations.get('python_deps_installed', 'Python dependencies installed'), 'phase': 'pip', 'header': True})
                        except subprocess.TimeoutExpired:
                            subprocess.check_call(
                                ['git', 'checkout', rollback_commit],
                                cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                            )
                            _emit('update_done', {
                                'success': False,
                                'error': self.translations.get('pip_timed_out_rollback_msg', 'pip install timed out. Rolled back to previous version.')
                            })
                            return

                    # Write flag file if Pillow version changed
                    if pillow_changed:
                        try:
                            flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
                            with open(flag_path, 'w') as f:
                                f.write('1')
                            _emit('update_output', {'line': self.translations.get('pillow_rebuild_scheduled', 'Pillow will be rebuilt from source after restart'), 'phase': 'pip', 'header': True})
                        except Exception:
                            pass

                    # Done — notify frontend, then restart
                    _emit('update_done', {
                        'success': True,
                        'tag': tag,
                        'rollback_tag': rollback_tag,
                        'rollback_commit': rollback_commit
                    })

                    # Wait for any ongoing e-ink display refresh to finish before restarting
                    _emit('update_output', {'line': 'Waiting for e-ink display to finish...', 'phase': 'restart', 'header': True})
                    acquired = self._display_worker_lock.acquire(timeout=150)
                    if acquired:
                        self._display_worker_lock.release()
                        print("✅ Display idle — safe to restart")
                    else:
                        print("⚠️ Display lock timeout after 150s — restarting anyway")

                    time.sleep(2)
                    try:
                        subprocess.run(
                            ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                            timeout=30
                        )
                    except Exception as restart_err:
                        print(f"Service restart failed: {restart_err}")

                except Exception as e:
                    print(f"Update error: {e}")
                    traceback.print_exc()
                    _emit('update_done', {'success': False, 'error': str(e)})
                finally:
                    self._update_running = False

            threading.Thread(target=_run_update, daemon=True).start()
            return jsonify({'success': True, 'message': 'Update started'})

        # ── Display Driver Install Endpoint ──────────────────────

        @self.app.route('/api/display/install-drivers', methods=['POST'])
        @require_auth(self.auth_manager)
        def install_display_drivers():
            """Install display drivers for the configured device."""
            try:
                data = request.json or {}
                device_id = data.get('device_id', '').strip()
                if not device_id:
                    return jsonify({'success': False, 'message': 'No device_id specified'}), 400

                from scripts.configure_display import (
                    DEVICE_CONFIGS, DRIVER_DOWNLOADS, _drivers_missing, install_drivers
                )

                if device_id not in DEVICE_CONFIGS:
                    return jsonify({'success': False, 'message': f'Unknown device: {device_id}'}), 400

                # Check if this device needs downloadable drivers
                if device_id not in DRIVER_DOWNLOADS:
                    return jsonify({
                        'success': True,
                        'message': 'No driver download required for this device',
                        'installed': False,
                        'restart_required': False
                    })

                missing = _drivers_missing(device_id)
                if not missing:
                    return jsonify({
                        'success': True,
                        'message': 'Drivers already installed',
                        'installed': False,
                        'restart_required': False
                    })

                print(f"📦 Installing display drivers for {device_id}...")
                ok = install_drivers(device_id)

                if ok:
                    print(f"✅ Display drivers installed for {device_id}")
                    # Schedule service restart so new drivers are loaded
                    def _delayed_restart():
                        time.sleep(2)
                        try:
                            subprocess.run(
                                ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                                timeout=30
                            )
                        except Exception as e:
                            print(f"Service restart failed: {e}")

                    threading.Thread(target=_delayed_restart, daemon=True).start()

                    return jsonify({
                        'success': True,
                        'message': f'Drivers installed for {DEVICE_CONFIGS[device_id]["name"]}. Service restarting...',
                        'installed': True,
                        'restart_required': True
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Driver download failed. Check internet connection.'
                    }), 500

            except Exception as e:
                print(f"Driver install error: {e}")
                traceback.print_exc()
                return jsonify({'success': False, 'message': str(e)}), 500

        # ── System Package Update Endpoint ────────────────────────

        @self.app.route('/api/system/update-packages', methods=['POST'])
        @require_auth(self.auth_manager)
        def update_system_packages():
            """Run apt update && apt upgrade -y in background, streaming output via SocketIO."""
            if getattr(self, '_apt_running', False):
                return jsonify({'success': False, 'message': 'System update already in progress'}), 409

            def _is_root_readonly():
                """Check if / is mounted read-only."""
                try:
                    with open('/proc/mounts') as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 4 and parts[1] == '/':
                                return 'ro' in parts[3].split(',')
                except Exception:
                    pass
                return False

            def _emit(event, data):
                if self.socketio:
                    self.socketio.emit(event, data, room='authenticated')

            def _run_apt():
                self._apt_running = True
                was_readonly = False
                try:
                    # Check if root filesystem is read-only and remount rw if needed
                    if _is_root_readonly():
                        was_readonly = True
                        _emit('apt_output', {'line': self.translations.get('remounting_filesystem', 'Remounting filesystem...'), 'phase': 'prepare', 'header': True})
                        rc = subprocess.call(['sudo', 'mount', '-o', 'remount,rw', '/'])
                        if rc != 0:
                            _emit('apt_done', {
                                'success': False,
                                'error': self.translations.get('remount_failed', 'Failed to remount filesystem read-write')
                            })
                            return

                    phase_labels = {
                        'update': self.translations.get('fetching_package_list', 'Fetching package list (apt update)...'),
                        'upgrade': self.translations.get('installing_upgrades', 'Installing upgrades (apt upgrade)...'),
                    }
                    for phase, cmd in [
                        ('update', ['sudo', 'apt-get', 'update']),
                        ('upgrade', ['sudo', 'apt-get', 'upgrade', '-y']),
                    ]:
                        _emit('apt_output', {'line': phase_labels.get(phase, f'apt {phase}'), 'phase': phase, 'header': True})

                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        for line in proc.stdout:
                            _emit('apt_output', {'line': line.rstrip('\n'), 'phase': phase})

                        proc.wait()
                        if proc.returncode != 0:
                            _emit('apt_done', {
                                'success': False,
                                'error': f'apt {phase} failed (exit code {proc.returncode})'
                            })
                            return

                    # Ensure all packages from apt-requirements.txt are installed
                    project_dir = os.path.dirname(os.path.abspath(__file__))
                    apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                    if os.path.exists(apt_req_file):
                        with open(apt_req_file) as f:
                            apt_pkgs = [
                                line.strip() for line in f
                                if line.strip() and not line.strip().startswith('#')
                            ]
                        if apt_pkgs:
                            _emit('apt_output', {'line': self.translations.get('installing_mempaper_deps', 'Installing mempaper dependencies...'), 'phase': 'deps', 'header': True})
                            proc = subprocess.Popen(
                                ['sudo', 'apt-get', 'install', '-y', '--no-upgrade'] + apt_pkgs,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                bufsize=1
                            )
                            for line in proc.stdout:
                                _emit('apt_output', {'line': line.rstrip('\n'), 'phase': 'deps'})
                            proc.wait()
                            if proc.returncode != 0:
                                _emit('apt_output', {'line': self.translations.get('mempaper_deps_warning', 'Warning: some mempaper dependencies failed to install'), 'phase': 'deps', 'header': True})

                    _emit('apt_done', {'success': True})
                except Exception as e:
                    print(f"System update error: {e}")
                    _emit('apt_done', {'success': False, 'error': str(e)})
                finally:
                    # Restore read-only if it was read-only before
                    if was_readonly:
                        _emit('apt_output', {'line': self.translations.get('restoring_readonly', 'Restoring read-only filesystem...'), 'phase': 'cleanup', 'header': True})
                        subprocess.call(['sudo', 'mount', '-o', 'remount,ro', '/'])
                    self._apt_running = False

            threading.Thread(target=_run_apt, daemon=True).start()
            return jsonify({'success': True, 'message': 'System update started'})

        # WebSocket event handlers (only if SocketIO is enabled)
        if self.socketio:
            @self.socketio.on('connect')
            def handle_connect():
                """Handle client connection. Join 'authenticated' room if logged in."""
                if self.auth_manager.is_authenticated():
                    join_room('authenticated')
            
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
                try:
                    # Try serving from RAM cache first (instant)
                    image_data = self._get_web_image_base64()
                    if image_data and self._has_valid_cached_image():
                        self.socketio.emit('new_image', {'image': image_data})
                        return
                    
                    # No current image — generate in background
                    threading.Thread(
                        target=self._background_image_generation,
                        daemon=True
                    ).start()
                    
                    # Send stale image while generating fresh one
                    if image_data:
                        self.socketio.emit('new_image', {'image': image_data})
                        
                except Exception as e:
                    print(f"❌ Error handling latest image request: {e}")
            
            @self.socketio.on('subscribe_block_notifications')
            def handle_subscribe_block_notifications(data):
                """Handle client request to subscribe to live block notifications."""
                try:
                    # Check if user is authenticated
                    if not self.auth_manager.is_authenticated():
                        print("⚠️ Unauthorized attempt to subscribe to block notifications")
                        self.socketio.emit('block_notification_error', {'error': 'Authentication required'})
                        return
                    
                    # Add client to subscribers
                    client_id = request.sid
                    if client_id not in self.block_notification_subscribers:
                        self.block_notification_subscribers.add(client_id)
                        print(f"📡 Client subscribed to block notifications ({len(self.block_notification_subscribers)} total)")
                    else:
                        self.block_notification_subscribers.add(client_id)
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
        # DISABLED: websocket_client causes duplicate block processing
        # block_monitor already has WebSocket functionality built-in
        print("⚙️ start_websocket_listener() called but disabled (using block_monitor's WebSocket)")
        return
        
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
    
    def _start_pillow_rebuild_if_needed(self):
        """Rebuild Pillow from source in the background if a previous update changed its version."""
        project_dir = os.path.dirname(os.path.abspath(__file__))
        flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
        if not os.path.exists(flag_path):
            return

        venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
        if not os.path.exists(venv_pip):
            return

        def _rebuild():
            try:
                print("📦 Rebuilding Pillow from source for native WebP support (this may take ~15 min on Pi Zero)...")
                subprocess.check_call(
                    [venv_pip, 'install', '--force-reinstall', '--no-cache-dir', '--no-binary', ':all:', 'Pillow'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=3600
                )
                os.remove(flag_path)
                print("✅ Pillow rebuilt from source. Restarting service to activate...")
                subprocess.run(
                    ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                    timeout=30
                )
            except subprocess.TimeoutExpired:
                print("⚠️ Pillow source build timed out. Will retry on next restart.")
            except Exception as e:
                print(f"⚠️ Pillow source rebuild failed: {e}. ImageMagick fallback remains active.")
                try:
                    os.remove(flag_path)
                except OSError:
                    pass

        threading.Thread(target=_rebuild, daemon=True).start()

    def _start_auto_update_scheduler(self):
        """Start background thread that checks for and runs automatic updates."""
        import datetime

        def _auto_update_loop():
            day_map = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
            last_run_date = None
            _logged_status = False

            while True:
                try:
                    time.sleep(60)  # Check every minute

                    enabled = self.config.get('auto_update_enabled', False)
                    if not _logged_status:
                        target_time = self.config.get('auto_update_time', self.config.get('auto_update_hour', '03:00'))
                        days = self.config.get('auto_update_days', [])
                        print(f"🕐 Auto-update scheduler active — enabled={enabled}, time={target_time}, days={days}")
                        _logged_status = True

                    if not enabled:
                        continue

                    now = datetime.datetime.now()
                    # Support both new "HH:MM" format and legacy hour-only int
                    raw_time = self.config.get('auto_update_time', self.config.get('auto_update_hour', '03:00'))
                    if isinstance(raw_time, int):
                        target_hour, target_minute = raw_time, 0
                    else:
                        parts = str(raw_time).split(':')
                        target_hour = int(parts[0])
                        target_minute = int(parts[1]) if len(parts) > 1 else 0
                    allowed_days = self.config.get('auto_update_days', ['mon', 'wed', 'fri'])

                    # Only run once per day, at the configured time
                    today = now.date()
                    if last_run_date == today:
                        continue
                    if now.hour != target_hour or now.minute != target_minute:
                        continue
                    if now.weekday() not in [day_map.get(d, -1) for d in allowed_days]:
                        continue

                    # Guard against concurrent updates
                    if getattr(self, '_update_running', False) or getattr(self, '_apt_running', False):
                        continue

                    last_run_date = today
                    print(f"🔄 Auto-update triggered at {now.strftime('%Y-%m-%d %H:%M')}")

                    project_dir = os.path.dirname(os.path.abspath(__file__))
                    needs_restart = False

                    # Phase 1: System packages (apt update + upgrade) — always runs
                    try:
                        print("🔄 Auto-update: running apt update && apt upgrade...")
                        subprocess.run(['sudo', 'apt-get', 'update'], capture_output=True, timeout=300)
                        subprocess.run(['sudo', 'apt-get', 'upgrade', '-y'], capture_output=True, timeout=600)

                        # Install mempaper apt dependencies
                        apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                        if os.path.exists(apt_req_file):
                            with open(apt_req_file) as f:
                                apt_pkgs = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                            if apt_pkgs:
                                subprocess.run(
                                    ['sudo', 'apt-get', 'install', '-y', '--no-upgrade'] + apt_pkgs,
                                    capture_output=True, timeout=300
                                )
                        print("✅ Auto-update: system packages done")
                    except Exception as e:
                        print(f"⚠️ Auto-update: apt failed: {e}")

                    # Phase 2: Mempaper software update — only if a newer release exists
                    try:
                        subprocess.run(
                            ['git', 'fetch', '--tags', '--force'],
                            cwd=project_dir, capture_output=True, timeout=60, check=True
                        )

                        # Get latest tag by version sort
                        tags_output = subprocess.check_output(
                            ['git', 'tag', '-l', '--sort=-version:refname'],
                            cwd=project_dir, text=True
                        ).strip()

                        if not tags_output:
                            print("⚠️ Auto-update: no tags found, skipping software update")
                        else:
                            latest_tag = tags_output.splitlines()[0].strip()

                            # Get current tag
                            try:
                                current_tag = subprocess.check_output(
                                    ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                                    cwd=project_dir, stderr=subprocess.DEVNULL, text=True
                                ).strip()
                            except subprocess.CalledProcessError:
                                current_tag = None

                            if current_tag == latest_tag:
                                print(f"✅ Auto-update: already on latest release ({latest_tag}), skipping")
                            else:
                                print(f"🔄 Auto-update: upgrading from {current_tag} to {latest_tag}...")

                                # Check dependency changes
                                deps_changed = False
                                apt_deps_changed = False
                                pillow_changed = False
                                try:
                                    diff_result = subprocess.run(
                                        ['git', 'diff', '--name-only', 'HEAD', f'refs/tags/{latest_tag}', '--',
                                         'requirements.txt', 'apt-requirements.txt'],
                                        cwd=project_dir, capture_output=True, text=True
                                    )
                                    changed_files = diff_result.stdout.strip()
                                    deps_changed = 'requirements.txt' in changed_files
                                    apt_deps_changed = 'apt-requirements.txt' in changed_files
                                    if deps_changed:
                                        import re
                                        diff_content = subprocess.run(
                                            ['git', 'diff', 'HEAD', f'refs/tags/{latest_tag}', '--', 'requirements.txt'],
                                            cwd=project_dir, capture_output=True, text=True
                                        )
                                        pillow_changed = bool(re.search(r'^\+.*pillow==', diff_content.stdout, re.IGNORECASE | re.MULTILINE))
                                except Exception:
                                    deps_changed = True
                                    apt_deps_changed = True

                                # Git checkout
                                subprocess.run(
                                    ['git', 'reset', '--hard'],
                                    cwd=project_dir, capture_output=True, check=True
                                )
                                subprocess.run(
                                    ['git', 'checkout', f'refs/tags/{latest_tag}'],
                                    cwd=project_dir, capture_output=True, check=True
                                )

                                # Install apt deps if changed
                                if apt_deps_changed:
                                    apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                                    if os.path.exists(apt_req_file):
                                        with open(apt_req_file) as f:
                                            pkgs = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                                        if pkgs:
                                            subprocess.run(
                                                ['sudo', 'apt-get', 'install', '-y', '--no-upgrade'] + pkgs,
                                                capture_output=True, timeout=300
                                            )

                                # Install pip deps
                                venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
                                requirements_file = os.path.join(project_dir, 'requirements.txt')
                                if os.path.exists(venv_pip) and os.path.exists(requirements_file):
                                    result = subprocess.run(
                                        [venv_pip, 'install', '-r', requirements_file],
                                        cwd=project_dir, capture_output=True, timeout=600
                                    )
                                    if result.returncode != 0:
                                        print(f"⚠️ Auto-update: pip install failed, rolling back...")
                                        subprocess.run(
                                            ['git', 'checkout', current_tag or 'HEAD~1'],
                                            cwd=project_dir, capture_output=True, check=True
                                        )
                                    else:
                                        needs_restart = True

                                # Flag Pillow rebuild if needed
                                if pillow_changed:
                                    flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
                                    with open(flag_path, 'w') as f:
                                        f.write('1')

                                if needs_restart:
                                    print(f"✅ Auto-update: upgraded to {latest_tag}. Restarting service...")
                                    subprocess.run(
                                        ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                                        timeout=30
                                    )
                    except Exception as e:
                        print(f"⚠️ Auto-update: software update failed: {e}")

                except Exception as e:
                    print(f"⚠️ Auto-update scheduler error: {e}")

        threading.Thread(target=_auto_update_loop, daemon=True, name='auto-update-scheduler').start()

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """
        Run the Flask application.

        Args:
            host (str): Host to bind to
            port (int): Port to listen on
            debug (bool): Enable debug mode
        """
        print(f"🚀 Starting Mempaper server on {host}:{port}")

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
        # Start background tasks (runs under both gunicorn and direct mode)
        _app_instance._start_pillow_rebuild_if_needed()
        _app_instance._start_auto_update_scheduler()
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
