"""
Configuration Manager Module

Handles loading, saving, and validation of configuration settings
for the mempaper application with web interface support, dynamic reloading,
and optional encryption for sensitive data.
"""

import json
import logging
import os
import threading
from typing import Dict, Any, List, Callable

from utils.atomic_io import atomic_write_json

# File watching functionality (install with: pip install watchdog)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    print("⚠ watchdog not installed - config auto-reload disabled. Install with: pip install watchdog")
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = None

# Secure configuration support (optional)
try:
    from managers.secure_config_manager import SecureConfigManager
    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    SECURE_CONFIG_AVAILABLE = False
    SecureConfigManager = None


class ConfigFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handles file system events for configuration file changes."""

    def __init__(self, config_manager):
        """Initialize with reference to config manager."""
        super().__init__() if WATCHDOG_AVAILABLE else None
        self.config_manager = config_manager
        self._debounce_lock = threading.Lock()
        self._debounce_timer = None
        self.debounce_delay = 1.0  # seconds to wait after last event before reloading

    def on_modified(self, event):
        """Handle file modification events."""
        if not WATCHDOG_AVAILABLE:
            return

        if event.is_directory:
            return

        # Check if it's our config file
        if os.path.abspath(event.src_path) == os.path.abspath(self.config_manager.config_path):
            # Cancel any pending reload and restart the timer — only the last
            # event in a burst triggers a reload (cancel-and-restart debounce).
            with self._debounce_lock:
                if self._debounce_timer is not None:
                    self._debounce_timer.cancel()
                self._debounce_timer = threading.Timer(
                    self.debounce_delay, self._fire_reload
                )
                self._debounce_timer.start()

    def _fire_reload(self):
        """Called once after the debounce window; clears the timer and reloads."""
        with self._debounce_lock:
            self._debounce_timer = None
        self.config_manager._reload_config_from_file()


class ConfigManager:
    """Manages application configuration with validation, web interface support, and dynamic reloading."""
    
    def __init__(self, config_path="config/config.json", enable_secure_config=True):
        """
        Initialize configuration manager with file watching and optional encryption.
        
        Args:
            config_path (str): Path to configuration file
            enable_secure_config (bool): Enable secure configuration management
        """
        self.config_path = config_path
        self.config_key_path = "config/.config_key"
        self.enable_secure_config = enable_secure_config
        
        # Rename the old .secure.json files before anything opens them. The
        # name claimed a protection the device-key scheme never delivered.
        if SECURE_CONFIG_AVAILABLE:
            try:
                from managers.secure_config_manager import migrate_legacy_filenames
                migrate_legacy_filenames()
            except Exception as e:
                print(f"⚠️ Legacy filename migration skipped: {e}")

        # Initialize secure config manager if available and enabled
        self.secure_manager = None
        if enable_secure_config and SECURE_CONFIG_AVAILABLE:
            try:
                self.secure_manager = SecureConfigManager(self.config_path)
            except Exception as e:
                print(f"⚠️ Failed to initialize secure config manager: {e}")
                self.secure_manager = None
        elif enable_secure_config and not SECURE_CONFIG_AVAILABLE:
            print("⚠️ Secure configuration requested but not available (install cryptography)")
        
        self.config = self.load_config()

        # Bring an existing install onto the current encryption scheme. Only
        # rewrites when the data was read with a superseded key.
        if self.secure_manager:
            try:
                self.secure_manager.migrate_to_current_scheme()
                self.secure_manager.migrate_encrypted_to_plaintext()
            except Exception as e:
                print(f"⚠️ Secure config migration skipped: {e}")

        self.config_lock = threading.RLock()  # Thread-safe config access
        self.change_callbacks = []  # List of callbacks to call when config changes
        self.file_observer = None
        
        # On Windows, force config reload and callback notification immediately after loading config
        if os.name == 'nt':
            self._reload_config_from_file()
            self._notify_change_callbacks(self.config)
        
        # Check if file watching should be disabled (for faster PC startup)
        disable_watching = self.config.get("disable_config_file_watching", False)
        self.watching_enabled = not disable_watching
        
        if disable_watching:
            print("⚙️ Config file watching disabled for faster startup")
        
        # Start file watching (only if enabled)
        self._start_file_watching()
    
    def add_change_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """
        Add a callback function to be called when configuration changes.
        
        Args:
            callback: Function that accepts the new config dict as parameter
        """
        self.change_callbacks.append(callback)
    
    def _start_file_watching(self):
        """Start watching the config file for changes."""
        if not WATCHDOG_AVAILABLE or not self.watching_enabled:
            print("⚠ File watching disabled (watchdog not available or disabled)")
            return
        
        try:
            self.file_observer = Observer()
            event_handler = ConfigFileHandler(self)
            
            # Watch the directory containing the config file
            watch_dir = os.path.dirname(os.path.abspath(self.config_path)) or "."
            self.file_observer.schedule(event_handler, watch_dir, recursive=False)
            self.file_observer.start()
            
        except Exception as e:
            print(f"⚠ Could not start file watching: {e}")
            self.file_observer = None
    
    def _stop_file_watching(self):
        """Stop watching the config file."""
        if self.file_observer:
            self.file_observer.stop()
            self.file_observer.join()
            self.file_observer = None
            logging.getLogger(__name__).debug("Config file watching stopped")
    
    def _reload_config_from_file(self):
        """Reload configuration from file and notify callbacks."""
        try:
            with self.config_lock:
                old_config = self.config.copy()
                new_config = self.load_config()
                
                # Check if config actually changed
                if new_config != old_config:
                    self.config = new_config
                    print("⚙️ Configuration reloaded from file")
                    
                    # Notify all registered callbacks
                    self._notify_change_callbacks(new_config)
                else:
                    pass  # file touched but content unchanged — no action needed
                    
        except Exception as e:
            print(f"❌ Error reloading config: {e}")
    
    def _notify_change_callbacks(self, new_config: Dict[str, Any]):
        """Notify all registered callbacks about config changes."""
        for callback in self.change_callbacks:
            try:
                callback(new_config)
            except Exception as e:
                print(f"❌ Error in config change callback {callback.__name__}: {e}")
    
    def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration (thread-safe), including secure fields for web interface."""
        with self.config_lock:
            # Start with a copy of the regular config
            merged_config = self.config.copy()
            
            # Merge secure config if available. The cached accessor skips the
            # re-read and decrypt while the files are untouched: this runs
            # several times per outgoing HTTP request via the mempool helpers
            # in block_monitor and block_reward_cache.
            if self.secure_manager:
                try:
                    secure_config = self.secure_manager.get_sensitive_fields_cached()
                    if secure_config:
                        merged_config.update(secure_config)
                except Exception as e:
                    logging.warning(f"Could not load secure config for web interface: {e}")
            
            return merged_config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key (thread-safe).
        
        Args:
            key: Configuration key to retrieve
            default: Default value if key not found
            
        Returns:
            Configuration value or default (with fallback to default config)
        """
        with self.config_lock:
            # First check current config
            if key in self.config:
                return self.config[key]
            
            # If not found, check default config
            default_config = self.get_default_config()
            if key in default_config:
                return default_config[key]
            
            # Finally return provided default
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value by key (thread-safe).
        
        Args:
            key: Configuration key to set
            value: Value to set
        """
        with self.config_lock:
            self.config[key] = value
    
    def remove(self, key: str) -> None:
        """
        Remove a configuration key (thread-safe).
        
        Args:
            key: Configuration key to remove
        """
        with self.config_lock:
            if key in self.config:
                del self.config[key]
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load configuration from file with fallback defaults.
        Supports both encrypted and plain configuration files.
        
        Returns:
            Dict containing configuration settings
        """
        # Start with default config as base
        merged_config = self.get_default_config()
        
        # Load plain config (contains non-sensitive fields)
        plain_config = None
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                plain_config = json.load(f)
        except FileNotFoundError:
            print(f"⚠ Config file not found: {self.config_path}")
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in config file: {e}")
        
        # Update with plain config values
        if plain_config:
            merged_config.update(plain_config)
        
        # Try secure config for sensitive fields only
        if self.secure_manager:
            secure_config = self.secure_manager.load_secure_config()
            if secure_config is not None:
                # Only update with sensitive fields from secure config
                if self.secure_manager:
                    sensitive_fields = self.secure_manager.sensitive_fields
                else:
                    sensitive_fields = {'wallet_balance_addresses_with_comments',
                                        'block_reward_addresses_table', 'admin_password_hash',
                                        'admin_users', 'secret_key', 'mempool_password'}
                for key, value in secure_config.items():
                    if key in sensitive_fields:
                        merged_config[key] = value
                return merged_config
        
        print(f"📝 Configuration loaded: {len(merged_config)} fields")
        return merged_config
    
    def get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration settings.
        
        Returns:
            Dict containing default configuration
        """
        return {
            "language": "en",
            "web_orientation": "vertical",
            "eink_orientation": "vertical",
            "prioritize_large_scaled_meme": False,
            "mempool_is_private": False,
            "mempool_host": "mempool.space",
            "mempool_rest_port": 443,
            "mempool_ws_port": 443,
            "mempool_ws_path": "/api/v1/ws",
            "mempool_use_https": True,
            "mempool_verify_ssl": True,
            "mempool_use_tor": False,
            "mempool_use_https_clearnet": True,
            "mempool_rest_port_clearnet": 443,
            "mempool_ws_port_clearnet": 443,
            "mempool_rest_port_tor": 80,
            "mempool_ws_port_tor": 80,
            "tor_socks_host": "127.0.0.1",
            "tor_socks_port": 9050,
            "mempool_username": "",
            "mempool_password": "",
            "network_outage_tolerance_minutes": 45,  # Time to retry connection before giving up

            # Pre-cache timing. All in seconds, all file-only — the web UI does
            # not expose them. Defaults are tuned for a single-core Pi Zero:
            # long enough to keep API traffic and CPU low, short enough that a
            # rendered image is never meaningfully out of date.
            #
            # The two max-age values govern the render path: how stale cached
            # data may be before a render fetches it again. Keeping them below
            # the update interval means a render occasionally refreshes ahead of
            # the background loop, which is the intended trade — a fresh image
            # matters more than one saved request. Fees get a shorter window
            # because they move fastest.
            "precache_update_interval_seconds": 300,
            "precache_render_max_age_seconds": 120,
            "precache_fee_max_age_seconds": 90,
            # Every configured miner reporting offline may just mean the LAN was
            # not up yet, so that reading is retried sooner than a normal cycle.
            "bitaxe_offline_retry_seconds": 30,
            # Debounce for cache-metadata writes, to limit SD card wear.
            "cache_metadata_write_interval_seconds": 300,
            "fee_parameter": "minimumFee",
            "display_width": 800,
            "display_height": 480,
            "e-ink-display-connected": True,
            # Set only when repeated failures switch the display off; startup
            # retries such a device so it can recover without dashboard access.
            "eink_auto_disabled": False,
            "omni_device_name": "epd7in3f",  # Default to native Waveshare 7.3" driver
            "public_dashboard": False,
            # --- Info block config additions ---
            "show_btc_price_block": True,
            "btc_price_currency": "USD",  # USD, EUR, GBP, CAD, CHF, AUD, JPY
            # --- Countdown block (BTC supply scarcity) ---
            "show_countdown_block": True,
            "color_countdown_light": "#C55A00",
            "color_countdown_dark": "#FF9E40",
            # --- Halving block ---
            "show_halving_block": True,
            "color_halving_light": "#1565C0",
            "color_halving_dark": "#4FC3F7",
            # --- Network block (global hashrate + difficulty) ---
            "show_network_block": True,
            "color_network_light": "#6A1B9A",
            "color_network_dark": "#CE93D8",
            "show_bitaxe_block": False,
            "bitaxe_display_mode": "blocks",  # "blocks" or "difficulty"
            "bitaxe_miner_table": [],  # List of {address, comment} objects for table view
            "block_reward_addresses_table": [],  # List of {address, comment} objects for block reward monitoring
            "show_wallet_balances_block": False,
            "wallet_balance_addresses_with_comments": [],  # List of {address, comment, type} objects for table view
            "wallet_balance_unit": "sats",  # "btc" or "sats"
            "wallet_balance_currency": "EUR",  # USD, EUR, GBP, CAD, CHF, AUD, JPY - fiat currency for wallet balance display
            "prioritize_large_scaled_meme": False,
            "color_mode_dark": True,
            "tang_enabled": False,
            "tang_url": "",
            "tang_thumbprint": "",

            "opsec_mode_enabled": False,
            # --- Meme sync schedule ---
            "meme_sync_enabled": False,
            "meme_sync_day": "4",   # Thursday (cron: 0=Sun … 6=Sat)
            "meme_sync_hour": "13", # 13:00
            "tor_meme_downloads": False,
            # --- Donation block ---
            "show_donation_block": False,
            "donation_display_mode": "latest",
            "webhook_relay_ws_url": "",
            "color_donation_light": "#F7931A",
            "color_donation_dark": "#F7931A",
            # --- Auto Update ---
            "auto_update_enabled": False,
            "auto_update_time": "05:00",
            "auto_update_days": ["mon", "wed", "fri"],
        }
    
    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """
        Save configuration to file with validation.
        Supports both encrypted and plain configuration storage.
        
        Args:
            config: Configuration to save (uses current config if None)
            
        Returns:
            bool: True if successful, False otherwise
        """
        config_to_save = config if config is not None else self.config
        
        try:
            # Temporarily disable file watching during save to prevent reload race condition
            file_watching_was_enabled = self.watching_enabled
            self.watching_enabled = False
            
            # Validate configuration
            validated_config = self.validate_config(config_to_save)
            
            # Save using secure config manager if available
            if self.secure_manager:
                success = self.secure_manager.save_secure_config(validated_config)
                if success:
                    with self.config_lock:
                        # Update in-memory config directly instead of reloading
                        self.config = validated_config
                    print(f"✅ Secure configuration saved")
                    
                    # Re-enable file watching after a delay to avoid immediate reload
                    if file_watching_was_enabled:
                        threading.Timer(2.0, lambda: setattr(self, 'watching_enabled', True)).start()
                        print(f"⏰ File watching will be re-enabled in 2 seconds")
                    
                    return True
                else:
                    print(f"⚠️ Failed to save secure config, falling back to plain config")
            
            # Fallback to plain config save
            # Create backup of current config
            if os.path.exists(self.config_path):
                backup_path = f"{self.config_path}.backup"
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(backup_content)
            
            # Save new configuration
            with self.config_lock:
                atomic_write_json(self.config_path, validated_config, indent=2, ensure_ascii=False)

                # Update in-memory config with the newly saved config
                self.config = validated_config
            
            print(f"✅ Configuration saved to {self.config_path}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            return False
    
    def validate_config(self, config: Dict[str, Any]):
        """Delegates to managers.config_validation."""
        from managers.config_validation import validate_config as _impl
        return _impl(self, config)
    
    def get_config_schema(self, translations: Dict[str, str]=None):
        """Delegates to managers.config_schema."""
        from managers.config_schema import get_config_schema as _impl
        return _impl(self, translations)

    def get_categories(self, translations: Dict[str, str] = None) -> List[Dict[str, str]]:
        """
        Get configuration categories for organized display.
        
        Args:
            translations (Dict): Translation dictionary for current language
        
        Returns:
            List of category definitions
        """
        # Use English as fallback if no translations provided
        t = translations or {}
        return [
            {"id": "general",          "_lk": "general_settings",  "label": t.get("general_settings",  "General Settings"),    "icon": "/static/icons/settings.svg"},
            {"id": "mempool",          "_lk": "mempool_settings",  "label": t.get("mempool_settings",  "Mempool"),             "icon": "/static/icons/bottom_drawer.svg"},
            {"id": "eink_display",     "_lk": "eink_display",      "label": t.get("eink_display",      "E-Ink Display"),       "icon": "/static/icons/photo_frame.svg"},
            {"id": "price_stats",      "_lk": "price_stats",       "label": t.get("price_stats",       "Price Stats"),         "icon": "/static/icons/price.svg"},
            {"id": "countdown",        "_lk": "countdown_settings","label": t.get("countdown_settings","Countdown"),           "icon": "/static/icons/countdown.svg"},
            {"id": "halving",          "_lk": "halving_settings",  "label": t.get("halving_settings",  "Halving"),             "icon": "/static/icons/halving.svg"},
            {"id": "network_stats",    "_lk": "network_settings",  "label": t.get("network_settings",  "Network"),             "icon": "/static/icons/network.svg"},
            {"id": "wallet_monitoring","_lk": "wallet_monitoring", "label": t.get("wallet_monitoring", "Wallet Monitoring"),   "icon": "/static/icons/wallet.svg"},
            {"id": "bitaxe_stats",     "_lk": "bitaxe_stats",      "label": t.get("bitaxe_stats",      "Bitaxe Stats"),        "icon": "/static/icons/bitaxe.svg"},
            {"id": "donation",         "_lk": "donation_settings", "label": t.get("donation_settings", "Lightning Donation"),  "icon": "/static/icons/donation.svg"},
            {"id": "meme_management",  "_lk": "meme_management",   "label": t.get("meme_management",   "Meme Management"),     "icon": "/static/icons/mood.svg"},
            {"id": "opsec",            "_lk": "opsec_settings",    "label": t.get("opsec_settings",    "OPSec"),               "icon": "/static/icons/opsec.svg"},
            {"id": "wifi",             "_lk": "wifi_settings",     "label": t.get("wifi_settings",     "WiFi"),                "icon": "/static/icons/wifi.svg"},
            {"id": "updates",          "_lk": "updates_settings",  "label": t.get("updates_settings",  "Updates"),             "icon": "/static/icons/update.svg"},
        ]
    
    def get_color_options(self) -> List[Dict[str, str]]:
        """
        Get available color options from ColorLUT system.
        
        Returns:
            List of color options with value, label, and web RGB for preview
        """
        # Fallback color options that work without ColorLUT
        fallback_options = [
            {"value": "forest_green", "label": "Forest Green", "category": "Greens", "preview_color": "#228B22"},
            {"value": "lime_green", "label": "Lime Green", "category": "Greens", "preview_color": "#32CD32"},
            {"value": "dark_green", "label": "Dark Green", "category": "Greens", "preview_color": "#006400"},
            {"value": "fire_brick", "label": "Fire Brick", "category": "Reds", "preview_color": "#B22222"},
            {"value": "crimson", "label": "Crimson", "category": "Reds", "preview_color": "#DC143C"},
            {"value": "dark_red", "label": "Dark Red", "category": "Reds", "preview_color": "#8B0000"},
            {"value": "peru", "label": "Peru", "category": "Oranges/Browns", "preview_color": "#CD853F"},
            {"value": "chocolate", "label": "Chocolate", "category": "Oranges/Browns", "preview_color": "#D2691E"},
            {"value": "saddle_brown", "label": "Saddle Brown", "category": "Oranges/Browns", "preview_color": "#8B4513"},
            {"value": "steel_blue", "label": "Steel Blue", "category": "Blues", "preview_color": "#4682B4"},
            {"value": "royal_blue", "label": "Royal Blue", "category": "Blues", "preview_color": "#4169E1"},
            {"value": "navy_blue", "label": "Navy Blue", "category": "Blues", "preview_color": "#000080"},
            {"value": "goldenrod", "label": "Goldenrod", "category": "Yellows/Golds", "preview_color": "#DAA520"},
            {"value": "gold", "label": "Gold", "category": "Yellows/Golds", "preview_color": "#FFD700"},
            {"value": "dark_goldenrod", "label": "Dark Goldenrod", "category": "Yellows/Golds", "preview_color": "#B8860B"},
            {"value": "black", "label": "Black", "category": "Neutrals", "preview_color": "#000000"},
            {"value": "gray", "label": "Gray", "category": "Neutrals", "preview_color": "#808080"},
            {"value": "dark_gray", "label": "Dark Gray", "category": "Neutrals", "preview_color": "#A9A9A9"}
        ]
        
        try:
            # Try to use ColorLUT if available
            from utils.color_lut import ColorLUT
            
            options = []
            categories = ColorLUT.get_color_categories()
            
            for category_name, colors in categories.items():
                for color_value, color_name in colors.items():
                    # Get web RGB for color preview
                    web_rgb = ColorLUT.get_color(color_value, display_type="web")
                    rgb_hex = "#{:02x}{:02x}{:02x}".format(*web_rgb)
                    
                    options.append({
                        "value": color_value,
                        "label": color_name,
                        "category": category_name,
                        "preview_color": rgb_hex
                    })
            
            return options
            
        except Exception as e:
            # Use fallback if ColorLUT fails
            print(f"⚠️ Using fallback color options due to error: {e}")
            return fallback_options
