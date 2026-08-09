"""
Main Application Module - mempaper Bitcoin Dashboard

This is the main Flask application that coordinates all components:
- Web server and SocketIO for real-time updates
- Integration with Bitcoin mempool for block data
- Image rendering and e-Paper display
- WebSocket management for live updates

Version: 2.0 (Refactored)
"""

import time
import io
import base64
import queue
import threading
import traceback
import urllib3
import os
import signal
import logging
import subprocess
import requests
# Strip identifying User-Agent header from all outgoing requests (privacy)
requests.utils.default_user_agent = lambda *_args, **_kw: "python-requests"
from datetime import datetime
from werkzeug.utils import secure_filename, safe_join
from flask import Flask
from flask_socketio import SocketIO
from flask_compress import Compress

# Import custom modules
from lib.mempool_api import MempoolAPI
from lib.image_renderer import ImageRenderer
from utils.translations import translations
from managers.config_manager import ConfigManager
from utils.technical_config import (TechnicalConfig, build_mempool_api_url,
                                    build_mempool_proxies)
from utils.security_config import SecurityConfig
from managers.auth_manager import AuthManager
from managers.tang_store import TangLocked
from utils.webp_probe_cache import cached_probe
from services.wifi import WifiHotspotMixin
from services.donations import DonationsMixin
from services.recovery import RecoveryMixin
from services.display_worker import DisplayWorkerMixin
from services.caching import CachingMixin
from services.updates import UpdateSchedulerMixin

# Privacy utilities for secure logging
try:
    PRIVACY_UTILS_AVAILABLE = True
except ImportError:
    PRIVACY_UTILS_AVAILABLE = False

# Disable SSL warnings for local mempool connections
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Probe WebP encoding once at startup in a subprocess.
# On ARMv6 (Pi Zero 1WH) the WebP C encoder can use NEON SIMD instructions
# that cause SIGILL. SIGILL is a signal, not a Python exception, so it kills
# the whole process even inside try/except — the subprocess isolates the crash.
def _probe_webp_encoding():
    import sys
    try:
        r = subprocess.run(
            [sys.executable, '-c',
             'from PIL import Image; import io; '
             'img=Image.new("RGB",(1,1)); buf=io.BytesIO(); img.save(buf,"WEBP")'],
            capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

_WEBP_ENCODING_OK = cached_probe('encode_ok', _probe_webp_encoding)
if not _WEBP_ENCODING_OK:
    print("⚠️  WebP encoding disabled (SIGILL on ARMv6 + NEON-compiled libwebp). Falling back to PNG.")


def _reserve_upload_path(directory, raw_filename, file_ext):
    """Return (safe_filename, path) for an upload, never overwriting an existing file.

    secure_filename() can rewrite a name (spaces, umlauts, non-ASCII scripts) into
    one that collides with a file already on disk even though the browser-side
    conflict check cleared it, silently destroying the existing image. Collisions
    get a _1/_2/… suffix instead, so both files survive; the caller returns the
    resolved name so the UI can show what was actually stored.
    """
    raw_stem = os.path.splitext(raw_filename or '')[0]
    stem = secure_filename(raw_stem) or 'image'

    os.makedirs(directory, exist_ok=True)

    candidate = f"{stem}.{file_ext}"
    counter = 1
    while os.path.exists(safe_join(directory, candidate) or os.devnull):
        candidate = f"{stem}_{counter}.{file_ext}"
        counter += 1

    # Explicit containment check at the point of use. secure_filename() already
    # strips separators and traversal, so this cannot currently fail; enforcing
    # it here means the guarantee does not depend on a sanitiser three lines up
    # continuing to behave the same way.
    path = safe_join(directory, candidate)
    if path is None:
        return None, None
    return candidate, path


def _parse_git_remote(remote_url):
    """Split a git remote into (host, owner/repo), or (None, None) if unparsable.

    Handles both https://host/owner/repo and the scp-like git@host:owner/repo
    form, which urlparse does not understand. Callers must compare the host
    rather than test for a substring: the update check decides from this whether
    to send an API token to GitHub or to a self-hosted GitLab, and a plain
    'github.com' in url test also matches hosts like github.com.example.org.
    """
    import re
    m = re.match(r'^(?:(?:https?|ssh|git)://)?(?:[^@/]+@)?([^/:]+)[:/](.+?)/?$',
                 (remote_url or '').strip())
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2)


def _safe_error(exc, context=''):
    """Log an exception server-side and hand the client a generic message.

    Returning str(exc) straight to the browser put filesystem paths, internal
    hostnames and library internals into the config UI. The detail is more
    useful in the journal anyway, where it is not readable by whoever happens
    to hold a session - so it is logged in full and only the generic string
    crosses the wire.
    """
    print(f"❌ {context or 'Request failed'}: {exc}")
    traceback.print_exc()
    return 'Internal error - check the server log for details'


def _read_reboot_time():
    """Parse the unattended-upgrades auto-reboot time from all apt conf.d files.
    Returns (hour, minute) tuple or None if auto-reboot is not configured."""
    import re, glob as _glob
    for path in sorted(_glob.glob('/etc/apt/apt.conf.d/*')):
        try:
            with open(path) as f:
                content = f.read()
            if 'Automatic-Reboot-Time' not in content:
                continue
            m = re.search(r'^(?!\s*//).*Automatic-Reboot-Time\s+"(\d{1,2}):(\d{2})"', content, re.MULTILINE)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            continue
    return None


def _in_reboot_window(h, m, reboot_hm, before_minutes=120, after_minutes=15):
    """Return True if time h:m falls in the blocked window around reboot_hm.
    Blocks [reboot - before_minutes, reboot + after_minutes) to avoid both
    interrupting a running update and scheduling during the post-reboot boot phase."""
    if reboot_hm is None:
        return False
    rh, rm = reboot_hm
    candidate   = h * 60 + m
    reboot      = rh * 60 + rm
    block_start = (reboot - before_minutes) % (24 * 60)
    block_end   = (reboot + after_minutes)  % (24 * 60)
    if block_start <= block_end:
        return block_start <= candidate < block_end
    else:  # window wraps midnight
        return candidate >= block_start or candidate < block_end


class MempaperApp(WifiHotspotMixin, DonationsMixin, RecoveryMixin,
                  DisplayWorkerMixin, CachingMixin, UpdateSchedulerMixin):
    """Main application class that coordinates all components."""
    
    def __init__(self, config_path="config/config.json"):
        """
        Initialize the mempaper application.
        
        Args:
            config_path (str): Path to configuration file
        """
        
        # Ensure required directories exist
        os.makedirs("config", exist_ok=True)
        os.makedirs("cache", exist_ok=True)

        # Setup-mode flag used by delivery onboarding flow
        self.setup_mode_flag_path = os.path.join("cache", "setup_mode.json")
        # Delivery mode flag: written by delivery_state.py before shipping.
        self._startup_timestamp = time.time()

        # Wi-Fi recovery state (runtime fallback into setup mode after sustained outage)
        self._wifi_disconnect_since = None
        self._wifi_last_reconnect_try = 0
        self._wifi_reconnect_attempts = 0
        self._wifi_last_setup_probe_try = 0
        self._wifi_setup_probe_failures = 0
        self._wifi_recovery_thread_started = False
        # Last known result of _has_saved_wifi_connections(); updated on every
        # successful nmcli read.  Avoids falsely treating a busy/transitioning NM
        # as "no saved networks" during a disconnect event.
        self._saved_wifi_known = None
        # Set to True after user submits credentials so recovery monitor probes immediately
        self._wifi_connect_pending = False
        # Signaled when _startup_wifi_check() finishes (success or failure), so the
        # recovery monitor's startup grace can end early instead of always waiting
        # its full fixed timeout even when the hotspot came up in a few seconds.
        self._startup_wifi_check_done = threading.Event()
        # Set for the duration of apply_wifi_credentials_background() so the recovery
        # monitor doesn't race it — both threads independently manage the hotspot
        # lifecycle, and without this the monitor can unmanage/re-manage wlan0 or
        # restart hostapd/dnsmasq mid-connect-attempt, emptying NM's scan cache right
        # before 'nmcli device wifi connect' runs ("No network with SSID ... found").
        self._manual_wifi_connect_in_progress = False
        # Set to True once the hotspot onboarding screen has been shown; prevents re-renders
        # every time the recovery monitor restores the hotspot after a failed probe.
        self._onboarding_hotspot_screen_shown = False
        # True while the connected onboarding screen is displayed on e-ink (suppresses other e-ink updates)
        self._onboarding_connected_active = False
        # Timestamp of the last time iw reported a station associated to our AP.
        # Used to suppress probes for a grace window after the phone screen goes off.
        self._last_ap_station_seen_ts = 0.0
        self._active_hotspot_interface = None  # set when hotspot is up, used to remove INPUT rule on teardown
        # Backoff state for restarting just the captive-portal dnsmasq when it
        # dies but the NM hotspot connection itself is still up.
        self._last_captive_reinit_try = 0.0
        self._captive_reinit_failures = 0
        
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
        Compress(self.app)
        self.app.secret_key = SecurityConfig.get_secret_key_from_env_or_generate()  # For session management
        
        # Configure session settings
        self.app.config['PERMANENT_SESSION_LIFETIME'] = SecurityConfig.SESSION_TIMEOUT
        # No SESSION_COOKIE_SECURE: LAN access is plain HTTP, and a Secure
        # cookie is never sent over HTTP.
        self.app.config['SESSION_COOKIE_HTTPONLY'] = True
        self.app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
        # Enforce upload size limit — rejects oversized requests before they hit the handler
        self.app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15 MB
        
        # TEMPORARY: Disable session cookie domain to fix gevent issues
        self.app.config['SESSION_COOKIE_DOMAIN'] = None
        self.app.config['SESSION_COOKIE_PATH'] = '/'
        
        # Ensure JSON responses are properly formatted
        self.app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
        self.app.config['JSON_SORT_KEYS'] = False

        @self.app.template_filter('inline_css')
        def inline_css_filter(filename):
            """Read a CSS file (from dist/ if available) and return content safe to inline.
            Font paths are rewritten from '../fonts/' to 'static/fonts/' for inline use."""
            dist = os.path.join('static', 'css', 'dist', filename)
            src  = os.path.join('static', 'css', filename)
            path = dist if os.path.exists(dist) else src
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read().replace("url('../fonts/", "url('static/fonts/")
            except OSError:
                return ''

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

        # Ensure a per-installation donation webhook secret exists; generate once and persist.
        if not self.config_manager.get('donation_webhook_token'):
            import secrets as _secrets
            self.config_manager.set('donation_webhook_token', _secrets.token_hex(32))
            self.config_manager.save_config()
            print("✅ Generated donation webhook token")

        # Sync meme-sync crontab entry with current config (no-op when disabled)
        self._apply_meme_sync_crontab()
        
        # Note: Cache sync and monitoring start moved to _run_background_startup for faster website availability
        print("⚙️ Block monitor initialized (sync and monitoring will start in background)")
        
        # Check e-Paper display configuration
        self._retry_auto_disabled_display()
        self.e_ink_enabled = self.config.get("e-ink-display-connected", True)
        if self.e_ink_enabled:
            print("⚙️ e-Paper display enabled")
        else:
            print("⚙️ e-Paper display disabled - running in display-less mode")
        
        # Image caching variables
        self.current_image_path = "cache/current.png"  # High-quality web image
        self.current_webp_image_path = "cache/current.webp"  # WebP version for efficient browser serving
        self.current_eink_image_path = "cache/current_eink.png"  # E-ink optimized image
        self.cache_metadata_path = "cache/cache.json"  # Persistent cache state
        
        # In-memory image cache for instant web serving (avoids disk I/O)
        self._cached_web_image_base64 = None  # Ready-to-emit data URI string
        self._cached_eink_image = None  # PIL Image for e-ink (avoids disk read-back)

        # Data-at-rest sealing against a Tang server on the LAN.
        #
        # Unlocked once, here, rather than per read: clevis is a shell script
        # and costs a process spawn of 100-300 ms, which would be felt on a Pi
        # Zero. Afterwards the key stays in memory and sealing is Fernet.
        #
        # With Tang disabled every call is a pass-through, so this costs
        # nothing and changes nothing on disk. When Tang is enabled but the
        # server cannot be reached the store stays locked and refuses to write,
        # which is what keeps a temporary outage from quietly producing clear
        # text; callers degrade instead.
        # Where the display subprocess reads the e-ink PNG from when it is
        # sealed on disk. tmpfs is RAM-backed, so the decrypted copy never
        # reaches the SD card and disappears on reboot. /run/shm is the same
        # mount under a different name on some images; a cache path is the last
        # resort and only ever used when sealing is off anyway.
        self._eink_ram_path = None
        for _ram_dir in ('/dev/shm', '/run/shm'):
            if os.path.isdir(_ram_dir):
                self._eink_ram_path = os.path.join(_ram_dir, 'mempaper-eink.png')
                break

        # The shared instance, not a private one. The config and cache managers
        # reach the store through get_shared_store during their own startup, so
        # constructing a second here would leave two objects disagreeing about
        # whether sealing is active - one sealing writes while the other passed
        # the same bytes through untouched.
        from managers.tang_store import get_shared_store
        self.tang_store = get_shared_store(self.config_manager)
        if self.tang_store.unlock():
            if self.tang_store.is_ready():
                print("🔓 Tang: sealed store unlocked")
                # A later outage should report again rather than stay quiet
                # because an earlier one already logged.
                self._tang_locked_logged.clear()
                # Seal anything still in the clear. Normally a no-op, but a
                # file can end up unsealed after a fault during a write, and
                # without this the device would keep running as though it were
                # protected. enable() is idempotent and reuses the existing key.
                try:
                    outcome = self.tang_store.enable()
                    if outcome['sealed']:
                        print(f"🔐 Tang: sealed {len(outcome['sealed'])} file(s) "
                              f"found in clear text: {outcome['sealed']}")
                    for failure in outcome['failed']:
                        print(f"⚠️ Tang: could not seal {failure['label']}: {failure['error']}")
                except Exception as e:
                    print(f"⚠️ Tang: re-seal check failed: {e}")
        else:
            print(f"🔒 Tang: {self.tang_store.reason}")
            print("🔒 Sealed data stays unavailable until the Tang server returns")
            # Almost always a startup race rather than a missing server: on a
            # cold boot this runs before wlan0 has associated, so the LAN is
            # simply not there yet. Retrying in the background turns that into
            # a few seconds of degraded operation instead of staying sealed
            # until somebody restarts the service.
            self._start_tang_unlock_retry()
        
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

        # Pushes a (fast, no-clear) e-ink refresh once startup finishes, even
        # if the cached image is already current for the block — so a reboot
        # or install.sh run visibly confirms the device came back up. Set on
        # a real new boot, or when install.sh drops its marker file; a plain
        # service restart on the same boot leaves this False.
        self._pending_boot_refresh = False

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
        self._display_worker_lock = threading.Lock()   # one display at a time; acquired non-blocking (see _display_on_epaper_async)
        self._display_worker_results = queue.Queue()   # stdout reader → caller
        self._last_display_error = None       # set on failure, cleared on success
        self._consecutive_display_failures = 0  # reset on success; auto-disable only after DISPLAY_FAILURE_DISABLE_THRESHOLD in a row

        # Dependency health check
        self._dependency_health_issues = None  # list of {name, detail} or None

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
        print("✅ mempaper application initialized successfully")


    def _run_dependency_health_check(self):
        """Verify that all required apt and pip packages are installed.

        Runs at startup in a background thread.  The check itself is fast
        (dpkg-query for apt, pip list for pip); only triggers an install
        when something is actually missing.
        """
        if os.name == 'nt':
            return

        project_dir = os.path.dirname(os.path.abspath(__file__))

        # ── apt packages ──
        apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
        if os.path.exists(apt_req_file):
            try:
                with open(apt_req_file) as f:
                    apt_pkgs = [
                        line.strip() for line in f
                        if line.strip() and not line.strip().startswith('#')
                    ]
                if apt_pkgs:
                    result = subprocess.run(
                        ['dpkg-query', '-W', '-f=${Package}\\n'] + apt_pkgs,
                        capture_output=True, text=True, timeout=10
                    )
                    installed = set(result.stdout.strip().splitlines()) if result.stdout else set()
                    missing_apt = [p for p in apt_pkgs if p not in installed]
                    if missing_apt:
                        print(f'📦 Dependency check: missing apt packages: {", ".join(missing_apt)}')
                        subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], timeout=10, capture_output=True)
                        # Scoped wrapper (installs from apt-requirements.txt, no args accepted) —
                        # a raw 'apt-get install <pkgs>' isn't in sudoers and would hang on a
                        # password prompt, silently failing under capture_output.
                        subprocess.run(['sudo', '/usr/local/bin/mempaper-apt-install'],
                                        capture_output=True, timeout=300)
                        print(f'📦 Dependency check: apt packages installed')
                    else:
                        print('✅ Dependency check: all apt packages present')
            except Exception as e:
                print(f'⚠️ Dependency check (apt): {e}')

        # ── pip packages ──
        requirements_file = os.path.join(project_dir, 'requirements.txt')
        venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
        if os.path.exists(venv_pip) and os.path.exists(requirements_file):
            try:
                # --disable-pip-version-check: without it, pip makes an HTTP call to
                # PyPI to check for a newer pip release on nearly every invocation,
                # even for this purely local package listing. Right after boot, while
                # NetworkManager is still finishing DHCP/DNS, that call can't resolve
                # and burns the full 30s timeout below for no reason — this is a
                # local-only check and never needs the network at all.
                result = subprocess.run(
                    [venv_pip, 'list', '--format=freeze', '--disable-pip-version-check'],
                    capture_output=True, text=True, timeout=30
                )
                installed_pip = {}
                if result.returncode == 0:
                    for line in result.stdout.strip().splitlines():
                        if '==' in line:
                            name, ver = line.split('==', 1)
                            installed_pip[name.lower().replace('-', '_')] = ver

                missing_pip = []
                with open(requirements_file) as f:
                    for line in f:
                        line = line.split('#')[0].strip()
                        if not line:
                            continue
                        pkg_name = line.split('==')[0].split('>=')[0].split('[')[0].strip().lower().replace('-', '_')
                        if pkg_name and pkg_name not in installed_pip:
                            missing_pip.append(line)

                if missing_pip:
                    print(f'📦 Dependency check: missing pip packages: {", ".join(missing_pip)}')
                    result = subprocess.run(
                        [venv_pip, 'install', '--disable-pip-version-check'] + missing_pip,
                        capture_output=True, timeout=600
                    )
                    if result.returncode == 0:
                        print('📦 Dependency check: pip packages installed — restart recommended')
                    else:
                        print(f'⚠️ Dependency check: pip install failed')
                else:
                    print('✅ Dependency check: all pip packages present')
            except Exception as e:
                print(f'⚠️ Dependency check (pip): {e}')

        # ── Compatibility checks ──
        # Catches an apt package silently losing compatibility after a security
        # update (e.g. the Trixie nft-vs-iptables-nft break we already hit once).
        # These validate syntax only (nft --check, dnsmasq --test) — neither
        # touches the live firewall ruleset or binds a socket, so they're safe
        # to run on every boot regardless of hotspot/network state. Pillow/image
        # encoding is intentionally not covered here (see comment near
        # self._dependency_health_issues in __init__).
        issues = []

        try:
            ruleset = (
                'table inet mempaper_healthcheck {\n'
                '    chain input {\n'
                '        type filter hook input priority 0;\n'
                '        iifname "lo" accept\n'
                '    }\n'
                '}\n'
            )
            r = subprocess.run(
                ['sudo', 'nft', '-c', '-f', '-'],
                input=ruleset, capture_output=True, text=True, timeout=5
            )
            if r.returncode != 0:
                detail = r.stderr.strip()[:200]
                issues.append({'name': 'nftables rule syntax', 'detail': detail})
                print(f'⚠️ Dependency check: nftables rule syntax check failed: {detail}')
            else:
                print('✅ Dependency check: nftables rule syntax OK')
        except Exception as e:
            issues.append({'name': 'nftables rule syntax', 'detail': str(e)})
            print(f'⚠️ Dependency check (nft): {e}')

        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as tf:
                tf.write('interface=lo\nbind-dynamic\ndhcp-range=10.255.255.10,10.255.255.100,12h\n')
                tmp_path = tf.name
            try:
                r = subprocess.run(
                    ['dnsmasq', '--test', f'--conf-file={tmp_path}'],
                    capture_output=True, timeout=5
                )
            finally:
                os.remove(tmp_path)
            if r.returncode != 0:
                detail = r.stderr.decode(errors='replace').strip()[:200]
                issues.append({'name': 'dnsmasq config syntax', 'detail': detail})
                print(f'⚠️ Dependency check: dnsmasq config syntax check failed: {detail}')
            else:
                print('✅ Dependency check: dnsmasq config syntax OK')
        except Exception as e:
            issues.append({'name': 'dnsmasq config syntax', 'detail': str(e)})
            print(f'⚠️ Dependency check (dnsmasq): {e}')

        self._dependency_health_issues = issues or None


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
        
        mempool_proxies = build_mempool_proxies(self.config)

        if not hasattr(self, '_api_clients_initialized'):
            print(f"🌐 Mempool API: {build_mempool_api_url(mempool_host, mempool_rest_port, mempool_use_https)}")
            if mempool_proxies:
                print(f"🧅 Mempool traffic routed via Tor "
                      f"({self.config.get('tor_socks_host', '127.0.0.1')}:"
                      f"{self.config.get('tor_socks_port', 9050)})")
            self._api_clients_initialized = True

        self.mempool_api = MempoolAPI(
            host=mempool_host,
            port=mempool_rest_port,
            use_https=mempool_use_https,
            verify_ssl=mempool_verify_ssl,
            username=mempool_username or None,
            password=mempool_password or None,
            proxies=mempool_proxies
        )

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
            if self.config.get("show_wallet_balances_block", True):
                threading.Thread(
                    target=self._async_wallet_refresh_and_regenerate,
                    args=(block_info['block_height'], block_info['block_hash']),
                    daemon=True
                ).start()
            
            # Display on e-Paper in background thread (don't block startup)
            if self.e_ink_enabled:
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self._eink_worker_path(), self.current_block_height, self.current_block_hash),
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
            cache_file_path = "cache/async_wallet_address_cache.sensitive.json"
            
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
        
        # Warm up wallet balance API (if configured and enabled)
        # Get wallet entries from modern table format
        wallet_entries = self.config.get("wallet_balance_addresses_with_comments", []) if self.config.get("show_wallet_balances_block", True) else []
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
    # One-shot marker: the app's own /api/system/reboot handler writes this right
    # before calling `systemctl reboot`. An authenticated, intentional reboot from
    # the web UI should never count toward the panic-recovery counter below —
    # that mechanism exists for someone who's locked out with no access except
    # the power cord, not for routine reboots via a button someone is already
    # logged in to click. Without this, a handful of ordinary UI reboots within
    # 15 minutes can trigger an unwanted full factory reset.
    GRACEFUL_REBOOT_MARKER_PATH = os.path.join('cache', 'graceful_reboot_pending')


    def _setup_instant_startup(self):
        """
        Setup instant startup mode:
        1. Check for power-cycle factory reset
        2. Load cached/default image immediately
        3. Start heavy operations in background
        4. Update interface when ready
        """

        # Consume the install.sh boot-refresh marker before the power-cycle
        # check below, so a factory reset (which already pushes the delivery
        # image itself) always wins if both happen to coincide.
        self._check_boot_refresh_marker()

        # Check for multi-power-cycle reset FIRST (before anything else).
        # If triggered, run synchronously so WiFi profiles are deleted BEFORE
        # the WiFi check thread tries to connect to them.
        factory_reset_triggered = False
        if os.name != 'nt':  # Only on Linux/Pi, not Windows dev
            if self._check_power_cycle_reset():
                factory_reset_triggered = True
                self._execute_factory_reset()
                # The delivery-image push above already covers it — don't let
                # the boot-refresh logic in _run_background_startup() re-push
                # the stale dashboard image over it.
                self._pending_boot_refresh = False

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
        def _startup_wifi_check_wrapper():
            # Signals _startup_wifi_check_done regardless of how this exits, so
            # the recovery monitor's startup grace (below) can end as soon as
            # this finishes instead of always waiting the full fixed timeout.
            try:
                self._startup_wifi_check()
            finally:
                self._startup_wifi_check_done.set()
        threading.Thread(target=_startup_wifi_check_wrapper, daemon=True).start()

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

    def _verify_block_height_once_online(self):
        """One-shot re-check of the current chain tip, run once the startup
        Wi-Fi check has resolved
        """
        self._startup_wifi_check_done.wait(timeout=90)
        try:
            block_info = self.mempool_api.get_current_block_info()
            _fb = self.mempool_api.fallback_data
            if (block_info.get('block_height') == _fb['block_height']
                    and block_info.get('block_hash') == _fb['block_hash']):
                print("⚠️ [STARTUP] Post-connectivity block check: mempool still unreachable — "
                      "the real-time websocket will catch up whenever the next block arrives")
                return

            current_bh = str(block_info.get('block_height', ''))
            cached_bh = str(self.current_block_height) if self.current_block_height is not None else None
            if cached_bh and current_bh and cached_bh != current_bh:
                print(f"⚙️ [STARTUP] Post-connectivity check: block changed {cached_bh} -> {current_bh} — catching up")
                self.current_block_height = block_info.get('block_height')
                self.current_block_hash = block_info.get('block_hash')
                self.image_is_current = False
                self._generate_new_image(
                    self.current_block_height,
                    self.current_block_hash,
                    use_new_meme=True
                )
        except Exception as e:
            print(f"⚠️ [STARTUP] Post-connectivity block check failed: {e}")

    def _run_background_startup(self):
        """Run heavy startup operations in background."""
        try:
            print("⚙️ Starting background initialization...")

            # Verify all dependencies are present (fast check, installs only if missing).
            threading.Thread(target=self._run_dependency_health_check, name='dep-health-check', daemon=True).start()

            # Wi-Fi check already started in _setup_instant_startup() thread.
            # Start Wi-Fi recovery monitor early so network failures can self-heal.
            self._start_wifi_recovery_monitor()

            # Start deferred init tasks that were moved out of __init__ to
            # reduce boot time (network calls, CPU-heavy threads).
            self._start_webhook_site_listener()
            self._start_precache_updater()

            # Check block height now (moved from __init__ to avoid 10s+ timeout when offline)
            needs_post_connectivity_recheck = False
            try:
                block_info = self.mempool_api.get_current_block_info()
                current_bh = str(block_info.get('block_height', ''))
                cached_bh = str(self.current_block_height) if self.current_block_height is not None else None

                # get_current_block_info() falls back to a sentinel (height 0 + the
                # genesis hash) on network failure instead of raising. Several other
                # startup tasks (webhook relay, precache, wallet scan) fire concurrent
                # requests to the same mempool host in this same window, so a single
                # timeout here is common — treating the sentinel as a real "block 0"
                # would look like "the block changed" and force an unnecessary
                # regenerate + e-ink push on every restart, not just real block changes.
                _fb = self.mempool_api.fallback_data
                if (block_info.get('block_height') == _fb['block_height']
                        and block_info.get('block_hash') == _fb['block_hash']):
                    print("⚠️ [STARTUP] Could not verify current block (mempool API unreachable) — keeping cached image")
                    if cached_bh:
                        self.image_is_current = True
                    needs_post_connectivity_recheck = True
                elif cached_bh and current_bh and cached_bh != current_bh:
                    print(f"⚙️ [STARTUP] Block changed since last run: {cached_bh} -> {current_bh}")
                    self.current_block_height = block_info.get('block_height')
                    self.current_block_hash = block_info.get('block_hash')
                    self.image_is_current = False
                elif cached_bh and current_bh and cached_bh == current_bh:
                    print(f"[STARTUP] Block unchanged: {current_bh} - cache is valid")
                    self.image_is_current = True
                elif not cached_bh and current_bh:
                    # No prior cache at all (fresh install / factory reset) — bootstrap
                    # from the current chain tip instead of leaving current_block_height
                    # unset. Otherwise the "regenerate real image" branch below never
                    # fires (it requires current_block_height), and the only thing that
                    # reaches the e-ink display is the text-only startup placeholder,
                    # wasting a refresh cycle before the real dashboard image is ready.
                    print(f"⚙️ [STARTUP] No prior cache — bootstrapping from current block {current_bh}")
                    self.current_block_height = block_info.get('block_height')
                    self.current_block_hash = block_info.get('block_hash')
                    self.image_is_current = False
            except Exception as e:
                print(f"[STARTUP] Failed to check current block: {e}")
                self.image_is_current = False
                needs_post_connectivity_recheck = True

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
            elif (self._pending_boot_refresh and self.e_ink_enabled
                  and not self._onboarding_connected_active
                  and os.path.exists(self.current_eink_image_path)):
                # Cached image is already current for this block, but we still
                # owe the user a refresh push to confirm the device came back
                # up after a reboot or a fresh install.
                print("🔄 Pushing fast e-ink refresh after reboot/install...")
                threading.Thread(
                    target=self._display_on_epaper_async,
                    args=(self._eink_worker_path(), self.current_block_height, self.current_block_hash),
                    daemon=True
                ).start()

            self._pending_boot_refresh = False  # consumed — one-shot per boot/install

            # The check above couldn't verify the real chain tip
            if needs_post_connectivity_recheck:
                threading.Thread(
                    target=self._verify_block_height_once_online,
                    daemon=True,
                    name='startup-block-verify'
                ).start()

            print("✅ Background initialization completed!")
            
        except Exception as e:
            print(f"⚠️ Background initialization failed: {e}")
            # Notify web clients of the error
            if hasattr(self, 'socketio') and self.socketio:
                self.socketio.emit('background_error', {
                    'message': f'Background processing failed: {e}',
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

        # Restart the persistent display worker if the display type changed - the
        # worker reads config once at its startup (see lib/display_worker.py) and
        # would otherwise keep driving the panel with the previous device's driver
        # until the next service restart.
        if old_config and old_config.get('omni_device_name') != self.config.get('omni_device_name'):
            print("🖥️ Display type changed — restarting display worker with new driver")

            def _restart_worker():
                # Wait for any in-flight push to finish rather than killing mid-refresh.
                with self._display_worker_lock:
                    self._kill_display_worker(self._display_worker)
                # Next _display_on_epaper_async call starts a fresh worker with new config.

            threading.Thread(target=_restart_worker, daemon=True).start()
        
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

        # Color settings: only trigger refresh when the affected block is currently displayed.
        # 'always'  → date text and hash frame, always visible
        # 'holiday' → hash frame + holiday text, only when today is a BTC holiday
        # <block>   → only when that block name is in self.displayed_info_blocks
        color_affecting_settings = {
            'color_date_start_light': 'always', 'color_date_end_light': 'always',
            'color_date_start_dark':  'always', 'color_date_end_dark':  'always',
            'color_holiday_start_light': 'holiday', 'color_holiday_end_light': 'holiday',
            'color_holiday_start_dark':  'holiday', 'color_holiday_end_dark':  'holiday',
            'color_btc_price_light':  'price',   'color_btc_price_dark':   'price',
            'color_countdown_light':  'countdown','color_countdown_dark':   'countdown',
            'color_halving_light':    'halving',  'color_halving_dark':     'halving',
            'color_network_light':    'network',  'color_network_dark':     'network',
            'color_bitaxe_stats_light':'bitaxe',  'color_bitaxe_stats_dark':'bitaxe',
            'color_wallets_light':    'wallet',   'color_wallets_dark':     'wallet',
            'color_donation_light':   'donation', 'color_donation_dark':    'donation',
        }
        displayed_blocks = getattr(self, 'displayed_info_blocks', []) or []
        today_is_holiday = bool(
            hasattr(self, 'image_renderer') and self.image_renderer and
            self.image_renderer.get_today_btc_holiday()
        )
        for setting, visibility in color_affecting_settings.items():
            old_value = old_config.get(setting)
            new_value = new_config.get(setting)
            if old_value == new_value or (old_value is not None and new_value is None):
                continue
            if (visibility == 'always' or
                    (visibility == 'holiday' and today_is_holiday) or
                    visibility in displayed_blocks):
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
        
        # Check for block reward address changes (independent of image refresh).
        # Runs in a background thread: scanning new addresses involves mempool API
        # calls that can take many seconds per address and must not block the HTTP response.
        threading.Thread(
            target=self._check_block_reward_address_changes,
            args=(old_config, new_config),
            daemon=True,
        ).start()

        # Reschedule auto-update timer in case the schedule settings changed.
        if hasattr(self, '_reschedule_auto_update'):
            self._reschedule_auto_update()

        # Update meme sync crontab if any of its settings changed.
        _meme_sync_keys = {'meme_sync_enabled', 'meme_sync_day', 'meme_sync_hour', 'tor_meme_downloads'}
        if any(old_config.get(k) != new_config.get(k) for k in _meme_sync_keys):
            self._apply_meme_sync_crontab(new_config)
    
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
                    self._write_eink_image(eink_img)
                self._save_images_to_disk(web_img, None)  # eink already saved above
                
                # Update cache metadata (deferred to reduce SD writes)
                self.image_is_current = True
                self._deferred_save_cache_metadata()

                # Display on e-Paper if enabled
                if self.e_ink_enabled:
                    threading.Thread(
                        target=self._display_on_epaper_async,
                        args=(self._eink_worker_path(), self.current_block_height, self.current_block_hash),
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

    def _apply_meme_sync_crontab(self, config=None):
        """Write or remove the mempaper meme-sync cron entry for the current (mempaper) user.

        Uses the standard crontab command — no sudo needed because the app runs
        as the mempaper user and manages only its own crontab.
        The entry is tagged with a comment marker so it can be found on updates.
        """
        if config is None:
            config = self.config

        MARKER = '# mempaper-meme-sync'
        enabled = config.get('meme_sync_enabled', False)
        day = str(config.get('meme_sync_day', '4'))
        hour = str(config.get('meme_sync_hour', '13'))
        tor = config.get('tor_meme_downloads', False)

        # Read existing crontab (empty crontab returns exit 1 on some systems)
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ''

        # Strip any previous mempaper meme-sync line
        lines = [ln for ln in existing.splitlines() if MARKER not in ln]

        if enabled:
            project_dir = os.path.dirname(os.path.abspath(__file__))
            # The sync script needs requests/PySocks, which live in the venv only —
            # cron runs with a bare environment, so name the interpreter by full
            # path rather than relying on anything being activated. The python3
            # fallback is for a dev checkout without a venv; on a real install
            # .venv always exists, and the script warns if it is run outside it.
            venv_python = os.path.join(project_dir, '.venv', 'bin', 'python')
            python = venv_python if os.path.exists(venv_python) else 'python3'
            script = os.path.join(project_dir, 'tools', 'sync_memes.py')
            log_dir = os.path.join(project_dir, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, 'meme-sync.log')
            tor_flag = ' --tor' if tor else ''
            lines.append(
                f'0 {hour} * * {day} '
                f'cd {project_dir} && {python} {script} --update{tor_flag} '
                f'>> {log_file} 2>&1 {MARKER}'
            )

        new_crontab = '\n'.join(lines)
        if new_crontab and not new_crontab.endswith('\n'):
            new_crontab += '\n'

        proc = subprocess.run(['crontab', '-'], input=new_crontab, text=True, capture_output=True)
        if proc.returncode != 0:
            print(f'⚠️ Failed to update meme sync crontab: {proc.stderr.strip()}')
        else:
            if enabled:
                print(f'📅 Meme sync scheduled: 0 {hour} * * {day}{"  (Tor)" if tor else ""}')
            else:
                print('📅 Meme sync crontab entry removed')

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
            self._write_eink_image(eink_img)

            # Display on e-Paper in background thread
            threading.Thread(
                target=self._display_on_epaper_async,
                args=(self._eink_worker_path(), self.current_block_height, self.current_block_hash),
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

    def _seed_bitaxe_emission_state(self):
        """Pre-fill _last_emitted_bitaxe with current values so the next
        emit does not treat existing data as new (avoids false toasts)."""
        try:
            config = self.config_manager.get_current_config()
            miner_table = config.get('bitaxe_miner_table', [])
            if not miner_table:
                return
            from lib.bitaxe_api import BitaxeAPI
            bitaxe_api = getattr(self.image_renderer, 'bitaxe_api', None) or BitaxeAPI()
            for entry in miner_table:
                ip = entry.get('address', '').strip() if isinstance(entry, dict) else ''
                if not ip:
                    continue
                try:
                    info = bitaxe_api.get_miner_info(ip)
                    self._last_emitted_bitaxe[ip] = {
                        'best_diff': info.get('best_diff', 0),
                        'online': info.get('online', False),
                    }
                except Exception:
                    pass
        except Exception:
            pass

    def _has_authenticated_clients(self):
        """True if any client is currently in the 'authenticated' room.

        Asks Socket.IO rather than keeping a parallel count: room membership
        is already maintained there, and a second copy could drift and
        silently cut a logged-in user off from updates. On any error assume a
        client is present, so a library change costs wasted requests rather
        than a dead config page.
        """
        try:
            participants = self.socketio.server.manager.get_participants('/', 'authenticated')
            return any(True for _ in participants)
        except Exception:
            return True

    # Retry cadence for a Tang server that was not reachable at startup. Starts
    # short because the usual cause is wlan0 still associating, and backs off so
    # a genuinely absent server is not polled every few seconds forever.
    TANG_RETRY_START_SECONDS = 5
    TANG_RETRY_MAX_SECONDS = 300

    def _start_tang_unlock_retry(self):
        """Keep trying to unlock in the background until the server answers."""
        if getattr(self, '_tang_retry_started', False):
            return
        self._tang_retry_started = True

        def _retry():
            delay = self.TANG_RETRY_START_SECONDS
            while True:
                time.sleep(delay)
                if not self.tang_store.is_enabled():
                    return                      # switched off while we waited
                try:
                    if self.tang_store.unlock() and self.tang_store.is_ready():
                        print("🔓 Tang: server reachable — sealed store unlocked")
                        self._tang_locked_logged.clear()
                        self._on_tang_unlocked()
                        return
                except Exception as e:
                    print(f"⚠️ Tang retry failed: {e}")
                delay = min(delay * 2, self.TANG_RETRY_MAX_SECONDS)

        threading.Thread(target=_retry, name='tang-unlock-retry', daemon=True).start()

    def _on_tang_unlocked(self):
        """Recover the state that could not be loaded while sealed.

        Startup ran with the sensitive config and caches unavailable, so the
        in-memory copies are empty rather than merely stale. Reloading the
        config is what puts the wallet and donation settings back; the re-seal
        pass covers anything a locked write left in the clear.
        """
        try:
            self.config_manager._reload_config_from_file()
            print("🔄 Tang: configuration reloaded from the sealed store")
        except Exception as e:
            print(f"⚠️ Tang: could not reload configuration: {e}")

        try:
            outcome = self.tang_store.enable()
            if outcome['sealed']:
                print(f"🔐 Tang: sealed {len(outcome['sealed'])} file(s) written "
                      f"while the server was away: {outcome['sealed']}")
        except Exception as e:
            print(f"⚠️ Tang: re-seal after recovery failed: {e}")

        try:
            self._load_donations()
        except Exception as e:
            print(f"⚠️ Tang: could not reload donations: {e}")

    _tang_locked_logged = set()

    def _log_tang_locked_once(self, what):
        """Report a skipped sealed write once per kind, not per attempt.

        Every reader and writer hits this while the Tang server is down, so
        logging each one buries the single line that matters under dozens of
        identical ones. The set is cleared when the store unlocks.
        """
        if what in self._tang_locked_logged:
            return
        self._tang_locked_logged.add(what)
        print(f"🔒 Tang unavailable — {what}")

    def _sealing_active(self):
        """True when rendered images must not be written to the card in clear."""
        store = getattr(self, 'tang_store', None)
        return store is not None and store.is_enabled()

    def _write_rendered_image(self, pil_image, path, **save_kwargs):
        """Persist a rendered image, sealed when Tang is on.

        Encoding goes through a buffer because a sealed file has to be written
        as bytes; PIL infers the format from the file extension, so callers
        pass it explicitly here.
        """
        import io
        buffer = io.BytesIO()
        pil_image.save(buffer, **save_kwargs)
        data = buffer.getvalue()

        if self._sealing_active():
            # Best effort while Tang is down: the image is already in RAM and
            # being served, so a skipped write only costs a re-render after a
            # restart. Writing it unsealed would defeat the point.
            try:
                self.tang_store.write_file(path, data)
            except TangLocked:
                self._log_tang_locked_once(f'{os.path.basename(path)} not persisted')
        else:
            with open(path, 'wb') as f:
                f.write(data)
        return data

    def _read_rendered_image(self, path):
        """Bytes of a rendered image, opening it if sealed. None when absent."""
        if self._sealing_active():
            return self.tang_store.read_file(path)
        try:
            with open(path, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def _write_eink_image(self, eink_img):
        """Persist the e-ink render and return the path the display worker reads.

        With sealing off this is the plain cache file, exactly as before.

        With sealing on, the card gets the sealed copy and the subprocess gets a
        decrypted one on tmpfs: the worker is a separate process with no key, so
        handing it the sealed file would simply fail. tmpfs keeps that copy in
        RAM, so nothing readable is committed to flash.
        """
        import io
        buffer = io.BytesIO()
        eink_img.save(buffer, format='PNG', compress_level=1)
        data = buffer.getvalue()

        if not self._sealing_active():
            with open(self.current_eink_image_path, 'wb') as f:
                f.write(data)
            return self.current_eink_image_path

        if not self._eink_ram_path:
            raise RuntimeError('No tmpfs available for the sealed e-ink image')

        # tmpfs first: it is RAM, so the panel keeps updating even while the
        # sealed copy cannot be written.
        with open(self._eink_ram_path, 'wb') as f:
            f.write(data)
        os.chmod(self._eink_ram_path, 0o600)

        # Persisting is best effort while Tang is down. Skipping it costs a
        # re-render after a restart; writing it in the clear would cost the
        # protection itself, so the write is dropped rather than downgraded.
        try:
            self.tang_store.write_file(self.current_eink_image_path, data)
        except TangLocked:
            self._log_tang_locked_once('e-ink image not persisted')
        return self._eink_ram_path

    def _eink_worker_path(self):
        """Path for the display worker, materialising from the sealed copy if needed.

        Used by callers that display an image they did not just render, such as
        a refresh after startup.
        """
        if not self._sealing_active():
            return self.current_eink_image_path
        if self._eink_ram_path and os.path.exists(self._eink_ram_path):
            return self._eink_ram_path
        data = self.tang_store.read_file(self.current_eink_image_path)
        if not data or not self._eink_ram_path:
            return self.current_eink_image_path
        with open(self._eink_ram_path, 'wb') as f:
            f.write(data)
        os.chmod(self._eink_ram_path, 0o600)
        return self._eink_ram_path

    def _emit_config_page_updates(self):
        """Push live updates to the config page via Socket.IO (bitaxe stats & found blocks)."""
        if not hasattr(self, 'socketio') or not self.socketio:
            return
        # Everything below is emitted only to the 'authenticated' room and the
        # Bitaxe branch costs one HTTP request per miner. With nobody logged in
        # the pre-cache loop was polling every miner on every cycle and throwing
        # the answers away.
        if not self._has_authenticated_clients():
            return
        try:
            config = self.config_manager.get_current_config()

            # Bitaxe stats for all configured miners (with labels)
            miner_table = config.get('bitaxe_miner_table', [])
            bitaxe_enabled = config.get('bitaxe_enabled', True) and config.get('show_bitaxe_block', True)
            if miner_table and bitaxe_enabled:
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
                    bitaxe_cache = self._precache.get('bitaxe_data', {}) if hasattr(self, '_precache') else {}
                    self.socketio.emit('bitaxe_stats_updated', {
                        'miners': miners,
                        'hashrate_ths': bitaxe_cache.get('total_hashrate_ths', 0),
                        'valid_blocks': bitaxe_cache.get('valid_blocks', 0),
                    }, room='authenticated')

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
            from lib.image_renderer import ImageRenderer
            from utils.translations import translations

            config = self.config_manager.get_current_config()
            image_renderer = ImageRenderer(config, translations)
            
            fresh_wallet_data = image_renderer.wallet_api.fetch_wallet_balances(startup_mode=startup_mode, current_block=block_height)

            # fetch_wallet_balances() already persists the result itself on success
            # (see update_cache() call at the end of that method) and deliberately
            # skips persisting when it returns an {"error": ...} dict — e.g. it lost
            # the non-blocking fetch lock to a concurrent call, or this block was
            # already scanned. Blindly re-persisting here regardless of outcome used
            # to overwrite a good cache with that near-empty error dict whenever the
            # fetch was skipped, which could pin a newly-added wallet's balance at 0
            # indefinitely if its real scan kept losing that race.
            if not isinstance(fresh_wallet_data, dict) or fresh_wallet_data.get('error'):
                return

            cached_wallet_data = image_renderer.wallet_api.get_cached_wallet_balances()
            if not isinstance(cached_wallet_data, dict):
                cached_wallet_data = {}

            fresh_btc = fresh_wallet_data.get("total_btc", 0)
            cached_btc = cached_wallet_data.get("total_btc", 0)

            if fresh_btc != cached_btc:
                print(f"⚙️ Wallet balance changed: {cached_btc:.8f} → {fresh_btc:.8f} BTC")

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
        # Fallback after a restart, before anything has been rendered. Opens the
        # sealed copy when Tang is on, so the image survives a reboot without a
        # re-render, and warms the RAM cache so later requests never touch disk.
        raw = self._read_rendered_image(self.current_image_path)
        if raw:
            data = 'data:image/png;base64,' + base64.b64encode(raw).decode()
            self._cached_web_image_base64 = data  # warm RAM cache
            return data
        return None

    def _save_images_to_disk(self, web_img, eink_img):
        """Save images to disk in background for crash recovery persistence."""
        def _save():
            try:
                if web_img is not None:
                    self._write_rendered_image(web_img, self.current_image_path, format='PNG', compress_level=1)
                    if _WEBP_ENCODING_OK:
                        try:
                            self._write_rendered_image(web_img, self.current_webp_image_path, format='WEBP', quality=82, method=4)
                        except Exception:
                            try:
                                os.remove(self.current_webp_image_path)
                            except OSError:
                                pass
                if eink_img is not None:
                    self._write_eink_image(eink_img)
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
        if age > 3600:
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
            self._write_eink_image(eink_img_patched)
            threading.Thread(
                target=self._display_on_epaper_async,
                args=(self._eink_worker_path(), block_height, block_hash),
                daemon=True
            ).start()

        # Background: save web image + metadata to disk (non-blocking)
        def _persist():
            if web_img_patched is not None:
                try:
                    self._write_rendered_image(web_img_patched, self.current_image_path, format='PNG', compress_level=1)
                except Exception as e:
                    print(f"⚠️ Background web image save failed: {e}")
                if _WEBP_ENCODING_OK:
                    try:
                        self._write_rendered_image(web_img_patched, self.current_webp_image_path, format='WEBP', quality=82, method=4)
                    except Exception:
                        try:
                            os.remove(self.current_webp_image_path)
                        except OSError:
                            pass
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
                self._write_eink_image(eink_img)
            # Web image only needed on disk for crash recovery — save in background (PNG + WebP)
            if web_img is not None:
                self._save_images_to_disk(web_img, None)
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
                    args=(self._eink_worker_path(), block_height, block_hash),
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
                'block_hash_full': block_hash,
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

                # Push updated countdown/halving data to config page preview cards
                try:
                    from lib.image_renderer import ImageRenderer as _IR
                    bh = block_height
                    sup = _IR._compute_supply_stats(bh)
                    hal = _IR._compute_halving_stats(bh, self._precache.get('network_data'))
                    self.socketio.emit('countdown_updated', {
                        'countdown': {
                            'remaining_btc': round(sup['remaining_btc'], 2),
                            'pct_mined': sup['pct_mined'],
                            'block_height': int(bh),
                        },
                        'halving': {
                            'days_remaining': hal['days_remaining'],
                            'hours_remaining': hal['hours_remaining'],
                            'estimated_date': hal['estimated_date'].isoformat() if hal.get('estimated_date') else None,
                        },
                    }, room='authenticated')
                except Exception:
                    pass

            # 🔄 Enrich notification data in background (non-blocking)
            def enrich_notification():
                try:
                    # Check if there are subscribers BEFORE making expensive API call
                    if not self.block_notification_subscribers:
                        return  # Skip enrichment if no clients subscribed
                    
                    print(f"🌐 Enriching block notification with API data...")
                    base_url = self._get_mempool_base_url()
                    # Route through Tor when configured. Without this the .onion
                    # host is handed to the system resolver, which cannot resolve
                    # it — every block logged a name-resolution failure — and a
                    # clearnet host would be contacted directly, bypassing Tor.
                    _proxies = build_mempool_proxies(self.config)
                    block_response = requests.get(
                        f"{base_url}/v1/block/{block_hash}",
                        timeout=40 if _proxies else 10,   # a circuit needs longer
                        verify=self.config.get("mempool_verify_ssl", True),
                        proxies=_proxies,
                    )
                    
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
                            'block_hash_full': block_hash,
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
        Format block hash for display: first 8 and last 8 characters, grouped in pairs.

        Args:
            block_hash (str): Full block hash

        Returns:
            str: Formatted hash like "00 00 00 00 ... ea 1f 0c 9b"
        """
        if len(block_hash) < 16:
            return block_hash  # Return as-is if too short

        # Get first 8 and last 8 characters
        first_eight = block_hash[:8]
        last_eight = block_hash[-8:]

        # Group in pairs with spaces
        first_formatted = ' '.join([first_eight[i:i+2] for i in range(0, 8, 2)])
        last_formatted = ' '.join([last_eight[i:i+2] for i in range(0, 8, 2)])

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
        """Register every route. Groups live in the routes package."""
        from routes import (setup, static_assets, pages, auth, config_api, media,
                            wallet, bitaxe, system, updates, sockets)

        for _group in (setup, static_assets, pages, auth, config_api, media,
                       wallet, bitaxe, system, updates, sockets):
            _group.register(self)
    
    def _flush_pending_caches_on_shutdown(self):
        """Persist any debounced-but-not-yet-written cache state.

        The unified secure cache (wallet balances, block-reward sync height,
        optimized-balance monitoring) and cache metadata both debounce disk
        writes and rely on a background thread to flush within ~60s / one
        pre-cache cycle. A `systemctl restart` sends SIGTERM directly with no
        grace period for that thread to run, so without this, a wallet balance
        (or other state) updated shortly before a restart can be silently lost
        — the app comes back up showing whatever was last written to disk.
        """
        print("🛑 Shutdown signal received — flushing pending cache writes...")
        try:
            from managers.unified_secure_cache import get_unified_cache
            get_unified_cache().flush()
        except Exception as e:
            print(f"⚠️ Failed to flush unified cache on shutdown: {e}")
        try:
            if getattr(self, '_disk_save_pending', False):
                self._write_cache_metadata_to_disk()
        except Exception as e:
            print(f"⚠️ Failed to flush cache metadata on shutdown: {e}")

    def _install_shutdown_flush_handler(self):
        """Flush pending cache writes before the process exits on SIGTERM."""
        def _handler(signum, frame):
            self._flush_pending_caches_on_shutdown()
            os._exit(0)
        try:
            signal.signal(signal.SIGTERM, _handler)
        except Exception as e:
            print(f"⚠️ Could not install shutdown flush handler: {e}")

    def run(self, host='0.0.0.0', port=5000, debug=False):
        """
        Run the Flask application.

        Args:
            host (str): Host to bind to
            port (int): Port to listen on
            debug (bool): Enable debug mode
        """
        print(f"🚀 Starting mempaper server on {host}:{port}")
        self._install_shutdown_flush_handler()

        # Run Flask app
        if self.socketio:
            self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        else:
            print("⚙️ Running Flask app without SocketIO")
            self.app.run(host=host, port=port, debug=debug)


# Global app instance for WSGI compatibility
_app_instance = None

def get_app_instance():
    """Get or create the global mempaperApp instance (singleton)."""
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
    print("🚀 Starting mempaper Bitcoin Dashboard (Direct Mode)")
    print("=" * 60)
    mempaper_app = MempaperApp()
    mempaper_app.run(debug=False)
