"""
Configuration Manager Module

Handles loading, saving, and validation of configuration settings
for the Mempaper application with web interface support, dynamic reloading,
and optional encryption for sensitive data.

Version: 2.1 - Added secure configuration support
"""

import json
import logging
import os
import threading
import time
from typing import Dict, Any, List, Callable, Optional

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


# Device native resolution mapping (width x height in landscape orientation).
# Mirrors DEVICE_DIMENSIONS in lib/image_renderer.py — keep in sync.
DEVICE_DIMENSIONS = {
    "epd13in3E": (1600, 1200),
    "epd13in3k": (1600, 1200),
    "epd7in3f":  (800,  480),
    "waveshare_epd.epd13in3E": (1600, 1200),
    "waveshare_epd.epd13in3k": (1600, 1200),
    "waveshare_epd.epd7in3f":  (800,  480),
    "waveshare_epd.epd5in83_v2": (648, 480),
    "waveshare_epd.epd4in2":   (400, 300),
    "waveshare_epd.epd2in7":   (264, 176),
    "inky.auto":               (600, 448),
    "inky.impression":         (600, 448),
    "inky.what_red":           (400, 300),
    "inky.what_yellow":        (400, 300),
    "inky.what_black":         (400, 300),
    "omni_epd.mock":           (800, 600),
}


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
    
    def remove_change_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove a previously registered change callback."""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
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
            print("🛑 Config file watching stopped")
    
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
            
            # Merge secure config if available
            if self.secure_manager:
                try:
                    secure_config = self.secure_manager.load_secure_config()
                    if secure_config:
                        # Merge secure fields into the config
                        for key, value in secure_config.items():
                            if key in self.secure_manager.sensitive_fields:
                                merged_config[key] = value
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
    
    def update_config_from_web(self, new_config: Dict[str, Any]) -> bool:
        """
        Update configuration from web interface with immediate application.
        
        Args:
            new_config: New configuration dictionary
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            with self.config_lock:
                # Validate the new configuration
                validated_config = self.validate_config(new_config)
                
                # Save to file
                if self.save_config(validated_config):
                    # Update in-memory config immediately
                    old_config = self.config.copy()
                    self.config = validated_config
                    
                    print("✅ Configuration updated from web interface")
                    
                    # Notify callbacks immediately (don't wait for file watcher)
                    self._notify_change_callbacks(validated_config)
                    
                    return True
                else:
                    print("❌ Failed to save config to file")
                    return False
                    
        except Exception as e:
            print(f"❌ Error updating config from web: {e}")
            return False
    
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
            "mempool_host": "127.0.0.1",
            "mempool_rest_port": 4081,
            "mempool_ws_port": 8999,
            "mempool_ws_path": "/api/v1/ws",
            "mempool_use_https": False,
            "mempool_verify_ssl": True,
            "mempool_username": "",
            "mempool_password": "",
            "network_outage_tolerance_minutes": 45,  # Time to retry connection before giving up
            "fee_parameter": "minimumFee",
            "display_width": 800,
            "display_height": 480,
            "e-ink-display-connected": True,
            "omni_device_name": "epd7in3f",  # Default to native Waveshare 7.3" driver
            "admin_username": "admin",
            "admin_password": "mempaper2025",
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
            "opsec_mode_enabled": False,
            # --- Donation block ---
            "show_donation_block": False,
            "donation_display_mode": "latest",
            "webhook_relay_ws_url": "",
            "color_donation_light": "#F7931A",
            "color_donation_dark": "#F7931A",
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
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(validated_config, f, indent=2, ensure_ascii=False)
                
                # Update in-memory config with the newly saved config
                self.config = validated_config
            
            print(f"✅ Configuration saved to {self.config_path}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to save configuration: {e}")
            return False
    
    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize configuration settings.
        
        Args:
            config (Dict): Configuration to validate
            
        Returns:
            Dict: Validated configuration
        """
        validated = self.get_default_config()
        
        # Language validation
        valid_languages = ["en", "de", "es", "fr", "it"]
        if config.get("language", "").lower() in valid_languages:
            validated["language"] = config["language"].lower()
        
        # Display orientation validation
        valid_orientations = ["vertical", "horizontal"]
        if config.get("web_orientation", "") in valid_orientations:
            validated["web_orientation"] = config["web_orientation"]
        if config.get("eink_orientation", "") in valid_orientations:
            validated["eink_orientation"] = config["eink_orientation"]
        

        # Boolean settings
        bool_settings = [
            "prioritize_large_scaled_meme",
            "e-ink-display-connected",
            "show_btc_price_block",
            "show_countdown_block",
            "show_halving_block",
            "show_network_block",
            "show_bitaxe_block",
            "show_wallet_balances_block",
            "show_donation_block",
            "color_mode_dark",
            "eink_dark_mode",
            "mempool_use_https",
            "mempool_verify_ssl",
            "opsec_mode_enabled",
            "public_dashboard",
        ]
        for setting in bool_settings:
            if setting in config:
                validated[setting] = bool(config[setting])

        # Note: Removed simple list settings - wallet addresses now use table format only
        
        # Special handling for wallet_balance_addresses_with_comments (list of objects)
        if "wallet_balance_addresses_with_comments" in config:
            if isinstance(config["wallet_balance_addresses_with_comments"], list):
                validated_entries = []
                for item in config["wallet_balance_addresses_with_comments"]:
                    if isinstance(item, dict):
                        # Validate object structure
                        if "address" in item and isinstance(item["address"], str) and item["address"].strip():
                            entry = {
                                "address": item["address"].strip(),
                                "comment": str(item.get("comment", "")).strip() or "Address",
                                "type": str(item.get("type", "")).strip() or "address"
                            }
                            validated_entries.append(entry)
                validated["wallet_balance_addresses_with_comments"] = validated_entries
            else:
                validated["wallet_balance_addresses_with_comments"] = []

        # Special handling for bitaxe_miner_table (list of objects)
        if "bitaxe_miner_table" in config:
            if isinstance(config["bitaxe_miner_table"], list):
                validated_entries = []
                for item in config["bitaxe_miner_table"]:
                    if isinstance(item, dict) and "address" in item:
                        entry = {
                            "address": str(item.get("address", "")).strip(),
                            "comment": str(item.get("comment", "")).strip() or "Bitaxe Miner"
                        }
                        if entry["address"]:  # Only add non-empty addresses
                            validated_entries.append(entry)
                validated["bitaxe_miner_table"] = validated_entries
            else:
                validated["bitaxe_miner_table"] = []

        # Special handling for block_reward_addresses_table (list of objects)
        if "block_reward_addresses_table" in config:
            if isinstance(config["block_reward_addresses_table"], list):
                validated_entries = []
                for item in config["block_reward_addresses_table"]:
                    if isinstance(item, dict) and "address" in item:
                        entry = {
                            "address": str(item.get("address", "")).strip(),
                            "comment": str(item.get("comment", "")).strip() or "Block Reward Address"
                        }
                        if entry["address"]:  # Only add non-empty addresses
                            validated_entries.append(entry)
                validated["block_reward_addresses_table"] = validated_entries
            else:
                validated["block_reward_addresses_table"] = []

        # Currency validation for BTC price
        valid_currencies = ["USD", "EUR", "GBP", "CAD", "CHF", "AUD", "JPY"]
        if config.get("btc_price_currency", "").upper() in valid_currencies:
            validated["btc_price_currency"] = config["btc_price_currency"].upper()
            
        # Currency validation for wallet balance
        if config.get("wallet_balance_currency", "").upper() in valid_currencies:
            validated["wallet_balance_currency"] = config["wallet_balance_currency"].upper()

        # Balance unit validation
        valid_units = ["btc", "sats"]
        if config.get("wallet_balance_unit", "").lower() in valid_units:
            validated["wallet_balance_unit"] = config["wallet_balance_unit"].lower()

        # String settings
        string_settings = [
            "mempool_host",
            "mempool_ws_path",
            "mempool_username",
            "mempool_password",
            "omni_device_name",
            "admin_username",
            "admin_password"
        ]
        for setting in string_settings:
            if setting in config and isinstance(config[setting], str):
                validated[setting] = config[setting].strip()

        # Integer settings with validation (including backwards compatibility)
        int_settings = {
            "mempool_rest_port": (1, 65535),
            "mempool_ws_port": (1, 65535),
            "network_outage_tolerance_minutes": (5, 10080),  # 5 min to 1 week
            "display_width": (100, 2000),
            "display_height": (100, 2000)
        }
        for setting, (min_val, max_val) in int_settings.items():
            if setting in config:
                try:
                    value = int(config[setting])
                    if min_val <= value <= max_val:
                        validated[setting] = value
                except (ValueError, TypeError):
                    pass

        # Auto-populate display dimensions from device when a known device is selected.
        # This runs AFTER manual int_settings so device dimensions always take precedence.
        device_name = validated.get("omni_device_name", "")
        if device_name and device_name in DEVICE_DIMENSIONS:
            validated["display_width"], validated["display_height"] = DEVICE_DIMENSIONS[device_name]
            print(f"⚙️ Auto-set display dimensions for {device_name}: "
                  f"{validated['display_width']}×{validated['display_height']}")

        # Float settings with validation
        float_settings = {}
        for setting, (min_val, max_val) in float_settings.items():
            if setting in config:
                try:
                    value = float(config[setting])
                    if min_val <= value <= max_val:
                        validated[setting] = round(value, 2)
                except (ValueError, TypeError):
                    pass
        
        # Backwards compatibility: old field names to new field names
        field_mappings = {
            "width": "display_width",
            "height": "display_height", 
            "omni_device_name": "omni_device_name"
        }
        for old_name, new_name in field_mappings.items():
            if old_name in config and new_name not in validated:
                if new_name in ["display_width", "display_height"]:
                    try:
                        value = int(config[old_name])
                        if 100 <= value <= 2000:
                            validated[new_name] = value
                    except (ValueError, TypeError):
                        pass
                else:
                    validated[new_name] = config[old_name]
        
        # String settings
        string_settings = [
            "omni_device_name", 
            "admin_username",
            "font_regular",
            "font_bold"
        ]
        for setting in string_settings:
            if setting in config and isinstance(config[setting], str):
                validated[setting] = config[setting].strip()
        
        # Special handling for secure password system
        # Check if we currently have a hashed password (from stored config)
        current_config = self.get_current_config()
        has_password_hash = current_config and "admin_password_hash" in current_config
        
        # If admin_password_hash exists in incoming config, preserve it
        if "admin_password_hash" in config:
            validated["admin_password_hash"] = config["admin_password_hash"]
            # Remove default cleartext password when using secure hash
            if "admin_password" in validated:
                del validated["admin_password"]
        
        # If we have an existing password hash, preserve it and handle new password changes
        elif has_password_hash:
            # If incoming config has a new plaintext password, hash it
            if "admin_password" in config and isinstance(config["admin_password"], str):
                new_password = config["admin_password"].strip()
                # Only hash if password is provided and not empty/default
                # Empty string means "don't change password" (e.g., username-only update)
                if new_password and new_password != "mempaper2025":  # Don't hash default password
                    # Hash the new password and update
                    try:
                        from argon2 import PasswordHasher
                        ph = PasswordHasher()
                        new_hash = ph.hash(new_password)
                        
                        # Verify the hash works correctly
                        ph.verify(new_hash, new_password)
                        validated["admin_password_hash"] = new_hash
                        print(f"🔒 Admin password updated and hashed securely")
                    except Exception as e:
                        print(f"⚠️ Failed to hash new password: {e}")
                        # Keep existing hash if hashing fails
                        validated["admin_password_hash"] = current_config["admin_password_hash"]
                else:
                    # Keep existing hash if empty password (username-only change)
                    validated["admin_password_hash"] = current_config["admin_password_hash"]
            else:
                # No password field in config = preserve existing hash (username-only change)
                validated["admin_password_hash"] = current_config["admin_password_hash"]
            
            # Remove cleartext password when using secure hash
            if "admin_password" in validated:
                del validated["admin_password"]
        
        # Handle cleartext admin_password only if no hash exists anywhere
        elif "admin_password" in config:
            if isinstance(config["admin_password"], str):
                validated["admin_password"] = config["admin_password"].strip()

        # Preserve admin_users dict (multi-user format: {username: argon2_hash})
        if "admin_users" in config and isinstance(config["admin_users"], dict):
            validated["admin_users"] = {
                k: v for k, v in config["admin_users"].items()
                if isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
            }
        elif current_config and isinstance(current_config.get("admin_users"), dict):
            validated["admin_users"] = dict(current_config["admin_users"])

        # Single value settings that should be passed through directly
        passthrough_settings = [
            "language", "web_orientation", "eink_orientation", "fee_parameter",
            "moscow_time_unit", "bitaxe_display_mode",
            "color_holiday_light", "color_holiday_end_light",
            "color_holiday_dark", "color_holiday_end_dark",
            "color_btc_price_light", "color_btc_price_dark",
            "color_bitaxe_stats_light", "color_bitaxe_stats_dark",
            "color_wallets_light", "color_wallets_dark",
            "webhook_relay_ws_url", "donation_display_mode",
            "color_donation_light", "color_donation_dark",
            "color_countdown_light", "color_countdown_dark",
            "color_halving_light", "color_halving_dark",
            "color_network_light", "color_network_dark",
        ]
        for setting in passthrough_settings:
            if setting in config:
                validated[setting] = config[setting]
        
        # Gap limit and bootstrap search validation
        gap_limit_bool_settings = [
            "xpub_enable_gap_limit",
            "xpub_enable_bootstrap_search"
        ]
        for setting in gap_limit_bool_settings:
            if setting in config:
                validated[setting] = bool(config[setting])
        
        # Gap limit and bootstrap integer settings with validation
        gap_limit_int_settings = {
            "xpub_gap_limit_last_n": (5, 100),  # 5 to 100 consecutive unused addresses
            "xpub_gap_limit_increment": (1, 50),  # 1 to 50 addresses per increment
            "xpub_bootstrap_max_addresses": (20, 1000),  # 20 to 1000 max bootstrap addresses
            "xpub_bootstrap_increment": (1, 50)  # 1 to 50 addresses per bootstrap increment
        }
        for setting, (min_val, max_val) in gap_limit_int_settings.items():
            if setting in config:
                try:
                    value = int(config[setting])
                    if min_val <= value <= max_val:
                        validated[setting] = value
                except (ValueError, TypeError):
                    pass
        
        return validated
    
    def get_config_schema(self, translations: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Get configuration schema for web interface.
        
        Args:
            translations (Dict): Translation dictionary for current language
        
        Returns:
            Dict containing field definitions and options
        """
        # Use English as fallback if no translations provided
        t = translations or {}

        # Build donation webhook hint HTML.
        # Pre-extract translations so no backslashes appear inside f-string {} expressions
        # (Python < 3.12 forbids backslashes in f-string expressions).
        _wh_opt_title = t.get('webhook_options_title', 'Choose how to receive donations:')
        _wh_a_title   = t.get('webhook_option_a_title', 'Option A \u2014 Direct webhook')
        _wh_a_sub     = t.get('webhook_option_a_subtitle', '(same network)')
        _wh_a_desc    = t.get('webhook_option_a_desc', 'In LNbits open <em>Pay Links</em> &rarr; <em>New Pay Link</em> &rarr; <em>Advanced options</em> &rarr; <em>Webhook URL</em> and enter:')
        _wh_a_note    = t.get('webhook_option_a_note', 'Click to copy &middot; Only works if mempaper is reachable from your wallet server.')
        _wh_b_title   = t.get('webhook_option_b_title', 'Option B \u2014 Self-hosted webhook-tester')
        _wh_b_sub     = t.get('webhook_option_b_subtitle', '(works over the internet)')
        _wh_b_step1   = t.get('webhook_option_b_step1', 'Deploy <a href="https://github.com/satcat21/event-hub" target="_blank" style="color:inherit">event-hub</a> on a server reachable from the internet.')
        _wh_b_step2   = t.get('webhook_option_b_step2', 'Create a session \u2014 note the token UUID. Set the LNbits Webhook URL to <code>https://your-host/{token}</code>.')
        _wh_b_step3   = t.get('webhook_option_b_step3', 'Paste the full WebSocket URL (e.g. <code>wss://your-host/ws/{token}</code>) in the field below.')
        _donation_webhook_hint_html = (
            f'<div style="margin-bottom:8px"><strong>{_wh_opt_title}</strong></div>'
            '<div style="border:1px solid rgba(128,128,128,.3);border-radius:6px;padding:10px 12px;margin-bottom:10px">'
            f'<div style="font-weight:600;margin-bottom:4px">{_wh_a_title} <small style="opacity:.65;font-weight:400">{_wh_a_sub}</small></div>'
            f'<div style="margin-bottom:6px;font-size:.9em">{_wh_a_desc}</div>'
            '<code class="info-copyable" onclick="navigator.clipboard.writeText(this.textContent).then(()=>this.classList.add(\'copied\'))" title="Click to copy">{BASE_URL}/api/donation-webhook</code>'
            f'<div style="font-size:.8em;opacity:.6;margin-top:4px">{_wh_a_note}</div>'
            '</div>'
            '<div style="border:1px solid rgba(128,128,128,.3);border-radius:6px;padding:10px 12px">'
            f'<div style="font-weight:600;margin-bottom:6px">{_wh_b_title} <small style="opacity:.65;font-weight:400">{_wh_b_sub}</small></div>'
            '<ol style="margin:0;padding-left:1.4em;font-size:.9em;line-height:1.7">'
            f'<li>{_wh_b_step1}</li>'
            f'<li>{_wh_b_step2}</li>'
            f'<li>{_wh_b_step3}</li>'
            '</ol>'
            '</div>'
        )

        return {
            # --- Info block config additions ---
            "show_btc_price_block": {
                "type": "boolean",
                "label": t.get("show_btc_price_block", "Show BTC Price Block"),
                "description": t.get("show_btc_price_block_desc", "Show the current Bitcoin price info block if space allows."),
                "default": True,
                "category": "price_stats"
            },
            "btc_price_currency": {
                "type": "select",
                "label": t.get("btc_price_currency", "BTC Price Currency"),
                "description": t.get("btc_price_currency_desc", "Fiat currency for BTC price display and Moscow time calculation"),
                "default": "USD",
                "options": [
                    {"value": "USD", "label": "US Dollar (USD)", "symbol": "$"},
                    {"value": "EUR", "label": "Euro (EUR)", "symbol": "€"},
                    {"value": "GBP", "label": "British Pound (GBP)", "symbol": "£"},
                    {"value": "CAD", "label": "Canadian Dollar (CAD)", "symbol": "C$"},
                    {"value": "CHF", "label": "Swiss Franc (CHF)", "symbol": "CHF"},
                    {"value": "AUD", "label": "Australian Dollar (AUD)", "symbol": "A$"},
                    {"value": "JPY", "label": "Japanese Yen (JPY)", "symbol": "¥"}
                ],
                "category": "price_stats"
            },
            "moscow_time_unit": {
                "type": "select",
                "label": t.get("moscow_time_unit", "Moscow Time Display Unit"),
                "description": t.get("moscow_time_unit_desc", "How to display Moscow time: as satoshis or as time format (HH:MM)"),
                "default": "sats",
                "options": [
                    {"value": "sats", "label": t.get("moscow_time_unit_sats", "Satoshis (e.g., 50,000 sats)")},
                    {"value": "hour", "label": t.get("moscow_time_unit_hour", "Time Format (e.g., 08:41)")}
                ],
                "category": "price_stats"
            },
            "color_btc_price_light": {
                "type": "color",
                "label": t.get("color_btc_price_light", "BTC Price (Light Mode)"),
                "description": t.get("color_btc_price_light_desc", "Color for BTC price text in light mode"),
                "default": "#17805B",
                "category": "price_stats",
                "order": 1000
            },
            "color_btc_price_dark": {
                "type": "color",
                "label": t.get("color_btc_price_dark", "BTC Price (Dark Mode)"),
                "description": t.get("color_btc_price_dark_desc", "Color for BTC price text in dark mode"),
                "default": "#00c896",
                "category": "price_stats",
                "order": 1001
            },
            # --- Countdown block ---
            "show_countdown_block": {
                "type": "boolean",
                "label": t.get("show_countdown_block", "Show Countdown Block"),
                "description": t.get("show_countdown_block_desc", "Show Bitcoin supply countdown block with remaining BTC and percentage mined."),
                "default": True,
                "category": "countdown"
            },
            "color_countdown_light": {
                "type": "color",
                "label": t.get("color_countdown_light", "Countdown (Light Mode)"),
                "description": t.get("color_countdown_light_desc", "Color for countdown values in light mode"),
                "default": "#C55A00",
                "category": "countdown",
                "order": 1000
            },
            "color_countdown_dark": {
                "type": "color",
                "label": t.get("color_countdown_dark", "Countdown (Dark Mode)"),
                "description": t.get("color_countdown_dark_desc", "Color for countdown values in dark mode"),
                "default": "#FF9E40",
                "category": "countdown",
                "order": 1001
            },
            # --- Halving block ---
            "show_halving_block": {
                "type": "boolean",
                "label": t.get("show_halving_block", "Show Halving Block"),
                "description": t.get("show_halving_block_desc", "Show next Bitcoin halving date and countdown block."),
                "default": True,
                "category": "halving"
            },
            "color_halving_light": {
                "type": "color",
                "label": t.get("color_halving_light", "Halving (Light Mode)"),
                "description": t.get("color_halving_light_desc", "Color for halving countdown values in light mode"),
                "default": "#1565C0",
                "category": "halving",
                "order": 1000
            },
            "color_halving_dark": {
                "type": "color",
                "label": t.get("color_halving_dark", "Halving (Dark Mode)"),
                "description": t.get("color_halving_dark_desc", "Color for halving countdown values in dark mode"),
                "default": "#4FC3F7",
                "category": "halving",
                "order": 1001
            },
            # --- Network block ---
            "show_network_block": {
                "type": "boolean",
                "label": t.get("show_network_block", "Show Network Block"),
                "description": t.get("show_network_block_desc", "Show global Bitcoin network hashrate and current mining difficulty."),
                "default": True,
                "category": "network_stats"
            },
            "color_network_light": {
                "type": "color",
                "label": t.get("color_network_light", "Network Stats (Light Mode)"),
                "description": t.get("color_network_light_desc", "Color for network stats values in light mode"),
                "default": "#6A1B9A",
                "category": "network_stats",
                "order": 1000
            },
            "color_network_dark": {
                "type": "color",
                "label": t.get("color_network_dark", "Network Stats (Dark Mode)"),
                "description": t.get("color_network_dark_desc", "Color for network stats values in dark mode"),
                "default": "#CE93D8",
                "category": "network_stats",
                "order": 1001
            },
            "show_bitaxe_block": {
                "type": "boolean",
                "label": t.get("show_bitaxe_block", "Show Bitaxe Hashrate/Blocks Block"),
                "description": t.get("show_bitaxe_block_desc", "Show Bitaxe hashrate and valid blocks info block if space allows."),
                "default": False,
                "category": "bitaxe_stats"
            },
            "bitaxe_display_mode": {
                "type": "select",
                "label": t.get("bitaxe_display_mode", "Bitaxe Display Mode"),
                "description": t.get("bitaxe_display_mode_desc", "Choose what to display on the right side of the Bitaxe info block"),
                "default": "blocks",
                "options": [
                    {"value": "blocks", "label": t.get("bitaxe_mode_blocks", "Found Blocks")},
                    {"value": "difficulty", "label": t.get("bitaxe_mode_difficulty", "Best Difficulty")}
                ],
                "category": "bitaxe_stats"
            },
            "bitaxe_miner_table": {
                "type": "bitaxe_table",
                "label": t.get("bitaxe_miner_table", "Bitaxe Monitoring Table"),
                "description": t.get("bitaxe_miner_table_desc", "Manage your Bitaxe miner IP addresses with comments for easy identification."),
                "default": [],
                "category": "bitaxe_stats"
            },
            "block_reward_addresses_table": {
                "type": "block_reward_table",
                "label": t.get("block_reward_addresses_table", "Block Reward Monitoring Table"),
                "description": t.get("block_reward_addresses_table_desc", "Manage BTC addresses to monitor for block rewards with comments and found blocks tracking."),
                "default": [],
                "category": "bitaxe_stats"
            },
            "color_bitaxe_stats_light": {
                "type": "color",
                "label": t.get("color_bitaxe_stats_light", "Bitaxe Stats (Light Mode)"),
                "description": t.get("color_bitaxe_stats_light_desc", "Color for Bitaxe stats text in light mode"),
                "default": "#B89C1D",
                "category": "bitaxe_stats",
                "order": 1000
            },
            "color_bitaxe_stats_dark": {
                "type": "color",
                "label": t.get("color_bitaxe_stats_dark", "Bitaxe Stats (Dark Mode)"),
                "description": t.get("color_bitaxe_stats_dark_desc", "Color for Bitaxe stats text in dark mode"),
                "default": "#ffe566",
                "category": "bitaxe_stats",
                "order": 1001
            },
            "show_wallet_balances_block": {
                "type": "boolean",
                "label": t.get("show_wallet_balances_block", "Show Wallet Balances Block"),
                "description": t.get("show_wallet_balances_block_desc", "Show wallet balances info block if space allows."),
                "default": False,
                "category": "wallet_monitoring"
            },
            "wallet_balance_addresses_with_comments": {
                "type": "wallet_table",
                "label": t.get("wallet_balance_addresses_table", "Wallet Monitoring Table"),
                "description": t.get("wallet_balance_addresses_table_desc", "Manage your wallet addresses, XPUBs, and ZPUBs with comments and balance monitoring."),
                "category": "wallet_monitoring",
                "order": 3
            },
            "wallet_balance_unit": {
                "type": "select",
                "label": t.get("wallet_balance_unit", "Balance Display Unit"),
                "description": t.get("wallet_balance_unit_desc", "Unit to display wallet balances in"),
                "default": "sats",
                "options": [
                    {"value": "btc", "label": "Bitcoin (BTC)"},
                    {"value": "sats", "label": "Satoshis (sats)"}
                ],
                "category": "wallet_monitoring",
                "order": 2
            },
            "wallet_balance_currency": {
                "type": "select",
                "label": t.get("wallet_balance_currency", "BTC Price Currency"),
                "description": t.get("wallet_balance_currency_desc", "Fiat currency for wallet balance display"),
                "default": "EUR",
                "options": [
                    {"value": "USD", "label": "US Dollar (USD)", "symbol": "$"},
                    {"value": "EUR", "label": "Euro (EUR)", "symbol": "€"},
                    {"value": "GBP", "label": "British Pound (GBP)", "symbol": "£"},
                    {"value": "CAD", "label": "Canadian Dollar (CAD)", "symbol": "C$"},
                    {"value": "CHF", "label": "Swiss Franc (CHF)", "symbol": "CHF"},
                    {"value": "AUD", "label": "Australian Dollar (AUD)", "symbol": "A$"},
                    {"value": "JPY", "label": "Japanese Yen (JPY)", "symbol": "¥"}
                ],
                "category": "wallet_monitoring",
                "order": 1
            },
            "color_wallets_light": {
                "type": "color",
                "label": t.get("color_wallets_light", "Wallet Stats (Light Mode)"),
                "description": t.get("color_wallets_light_desc", "Color for wallet balances text in light mode"),
                "default": "#1565C0",
                "category": "wallet_monitoring",
                "order": 1000
            },
            "color_wallets_dark": {
                "type": "color",
                "label": t.get("color_wallets_dark", "Wallet Stats (Dark Mode)"),
                "description": t.get("color_wallets_dark_desc", "Color for wallet balances text in dark mode"),
                "default": "#09a3ba",
                "category": "wallet_monitoring",
                "order": 1001
            },
            "language": {
                "type": "select",
                "label": t.get("language", "Language"),
                "options": [
                    {"value": "en", "label": t.get("english", "English"), "flag": "<img src='/static/icons/en.svg' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                    {"value": "de", "label": t.get("german", "Deutsch"), "flag": "<img src='/static/icons/de.svg' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                    {"value": "es", "label": t.get("spanish", "Español"), "flag": "<img src='/static/icons/es.svg' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                    {"value": "fr", "label": t.get("french", "Français"), "flag": "<img src='/static/icons/fr.svg' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                    {"value": "it", "label": t.get("italian", "Italiano"), "flag": "<img src='/static/icons/it.svg' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"}
                ],
                "category": "general",
                "order": 1
            },
            "web_orientation": {
                "type": "toggle",
                "label": t.get("web_orientation", "Web Orientation"),
                "description": t.get("web_orientation_desc", "Orientation for the web dashboard"),
                "options": [
                    {"value": "vertical", "label": t.get("vertical", "Portrait"), "icon": "/static/icons/vertical.svg"},
                    {"value": "horizontal", "label": t.get("horizontal", "Landscape"), "icon": "/static/icons/horizontal.svg"}
                ],
                "default": "vertical",
                "category": "general",
                "order": 6,
                "advanced": True
            },
            "eink_orientation": {
                "type": "toggle",
                "label": t.get("eink_orientation", "E-ink Orientation"),
                "description": t.get("eink_orientation_desc", "Orientation for the E-ink display"),
                "options": [
                    {"value": "vertical", "label": t.get("vertical", "Portrait"), "icon": "/static/icons/vertical.svg"},
                    {"value": "horizontal", "label": t.get("horizontal", "Landscape"), "icon": "/static/icons/horizontal.svg"}
                ],
                "default": "vertical",
                "category": "eink_display"
            },
            "mempool_host": {
                "type": "text",
                "label": t.get("mempool_host", "Mempool Server Host"),
                "placeholder": "192.168.0.119 or mempool.mydomain.com",
                "description": t.get("mempool_host_desc", "IP address or domain name of your mempool server"),
                "category": "mempool"
            },
            "mempool_rest_port": {
                "type": "number",
                "label": t.get("mempool_rest_port", "REST API Port"),
                "min": 1,
                "max": 65535,
                "description": t.get("mempool_rest_port_desc", "Port for mempool REST API"),
                "category": "mempool",
                "advanced": True,
                "order": 1
            },
            "mempool_ws_port": {
                "type": "number",
                "label": t.get("mempool_ws_port", "WebSocket Port"),
                "min": 1,
                "max": 65535,
                "description": t.get("mempool_ws_port_desc", "Port for real-time mempool updates"),
                "category": "mempool",
                "advanced": True,
                "order": 2
            },
            "fee_parameter": {
                "type": "select",
                "label": t.get("fee_parameter", "Fee Parameter for Block Height Color"),
                "description": t.get("fee_parameter_desc", "Which fee level to use for determining block height color"),
                "default": "minimumFee",
                "options": [
                    {"value": "fastestFee", "label": t.get("fastest", "Fastest (~1 block)")},
                    {"value": "halfHourFee", "label": t.get("half_hour", "Half Hour (~3 blocks)")},
                    {"value": "hourFee", "label": t.get("hour", "Hour (~6 blocks)")},
                    {"value": "economyFee", "label": t.get("economy", "Economy (~1 day)")},
                    {"value": "minimumFee", "label": t.get("minimum", "Minimum")}
                ],
                "category": "mempool"
            },
            "mempool_use_https": {
                "type": "boolean",
                "label": t.get("mempool_use_https", "Use HTTPS/WSS"),
                "description": t.get("mempool_use_https_desc", "Use secure HTTPS for REST API and WSS for WebSocket connections"),
                "default": False,
                "category": "mempool",
                "advanced": True,
                "order": 4
            },
            "mempool_verify_ssl": {
                "type": "boolean",
                "label": t.get("mempool_verify_ssl", "Verify SSL Certificates"),
                "description": t.get("mempool_verify_ssl_desc", "Verify SSL certificates when using HTTPS (disable for self-signed certificates)"),
                "default": True,
                "category": "mempool",
                "advanced": True,
                "order": 5
            },
            "mempool_ws_path": {
                "type": "text",
                "label": t.get("mempool_ws_path", "WebSocket Path"),
                "placeholder": "/api/v1/ws",
                "description": t.get("mempool_ws_path_desc", "WebSocket endpoint path for real-time updates"),
                "default": "/api/v1/ws",
                "category": "mempool",
                "advanced": True,
                "order": 3
            },
            "mempool_username": {
                "type": "text",
                "label": t.get("mempool_username", "Mempool Username"),
                "placeholder": "mempool",
                "description": t.get("mempool_username_desc", "Optional username for Basic authentication (leave empty if not required)"),
                "category": "mempool",
                "advanced": True,
                "order": 6
            },
            "mempool_password": {
                "type": "password",
                "label": t.get("mempool_password", "Mempool Password"),
                "placeholder": "your-secret-password",
                "description": t.get("mempool_password_desc", "Optional password for Basic authentication (leave empty if not required)"),
                "category": "mempool",
                "secure": True,
                "advanced": True,
                "order": 7
            },
            "e-ink-display-connected": {
                "type": "boolean",
                "label": t.get("display_connected", "e-Paper Display Connected"),
                "description": t.get("display_connected_desc", "Enable/disable physical e-paper display"),
                "category": "eink_display"
            },
            "prioritize_large_scaled_meme": {
                "type": "boolean",
                "label": t.get("prioritize_large_scaled_meme", "Prioritize Large Scaled Memes"),
                "description": t.get("prioritize_large_scaled_meme_desc", "When enabled, maximize meme display space by hiding stats if necessary."),
                "default": False,
                "category": "general",
                "order": 4
            },
            "holiday_color_group": {
                "type": "holiday_color_group",
                "label": t.get("holiday_color_group_label", "Holiday Text Gradient Colors"),
                "category": "general",
                "order": 5,
                "advanced": True
            },
            "color_holiday_light": {
                "type": "color",
                "label": t.get("color_holiday_light", "Start Color"),
                "default": "#F7931A",
                "category": "_holiday_color"
            },
            "color_holiday_end_light": {
                "type": "color",
                "label": t.get("color_holiday_end_light", "End Color"),
                "default": "#C62828",
                "category": "_holiday_color"
            },
            "color_holiday_dark": {
                "type": "color",
                "label": t.get("color_holiday_dark", "Start Color"),
                "default": "#F7931A",
                "category": "_holiday_color"
            },
            "color_holiday_end_dark": {
                "type": "color",
                "label": t.get("color_holiday_end_dark", "End Color"),
                "default": "#FF6F6F",
                "category": "_holiday_color"
            },
            "omni_device_name": {
                "type": "select",
                "label": t.get("display_type", "Display Device Type"),
                "description": t.get("display_type_desc", "Select your specific e-paper display model"),
                "options": [
                    # Native Waveshare Displays (recommended - best performance)
                    {"value": "epd13in3E", "label": "★ Waveshare 13.3\" 6-Color (Spectra 6) - Native Driver"},
                    {"value": "epd7in3f", "label": "★ Waveshare 7.3\" 7-Color - Native Driver"},
                    {"value": "epd13in3k", "label": "★ Waveshare 13.3\" B/W - Native Driver"},
                    
                    # Inky Displays
                    {"value": "inky.auto", "label": "Inky AutoDetect"},
                    {"value": "inky.impression", "label": "Inky Impression 7 Color"},
                    {"value": "inky.phat_red", "label": "Inky pHAT Red/Black/White - 212x104"},
                    {"value": "inky.phat_yellow", "label": "Inky pHAT Yellow/Black/White - 212x104"},
                    {"value": "inky.phat_black", "label": "Inky pHAT Black/White - 212x104"},
                    {"value": "inky.phat1608_red", "label": "Inky pHAT Red/Black/White - 250x122"},
                    {"value": "inky.phat1608_yellow", "label": "Inky pHAT Yellow/Black/White - 250x122"},
                    {"value": "inky.phat1608_black", "label": "Inky pHAT Black/White - 250x122"},
                    {"value": "inky.what_red", "label": "Inky wHAT Red/Black/White"},
                    {"value": "inky.what_yellow", "label": "Inky wHAT Yellow/Black/White"},
                    {"value": "inky.what_black", "label": "Inky wHAT Black/White"},
                    
                    # Mock Display
                    {"value": "omni_epd.mock", "label": "Mock Display (Testing - No Hardware)"},
                    
                    # Waveshare 4 inch Displays
                    {"value": "waveshare_epd.epd4in01f", "label": "Waveshare 4.01\" 7-Color HAT"},
                    {"value": "waveshare_epd.epd4in2", "label": "Waveshare 4.2\" E-Paper"},
                    {"value": "waveshare_epd.epd4in2b", "label": "Waveshare 4.2\" B (Red)"},
                    {"value": "waveshare_epd.epd4in2b_V2", "label": "Waveshare 4.2\" B V2 (Red)"},
                    {"value": "waveshare_epd.epd4in2c", "label": "Waveshare 4.2\" C (Yellow)"},
                    {"value": "waveshare_epd.epd4in37g", "label": "Waveshare 4.37\" G (4-Color)"},
                    
                    # Waveshare 5 inch Displays
                    {"value": "waveshare_epd.epd5in65f", "label": "Waveshare 5.65\" F (7-Color)"},
                    {"value": "waveshare_epd.epd5in83", "label": "Waveshare 5.83\" E-Paper HAT"},
                    {"value": "waveshare_epd.epd5in83_V2", "label": "Waveshare 5.83\" V2"},
                    {"value": "waveshare_epd.epd5in83b", "label": "Waveshare 5.83\" B (Red)"},
                    {"value": "waveshare_epd.epd5in83b_V2", "label": "Waveshare 5.83\" B V2 (Red)"},
                    {"value": "waveshare_epd.epd5in83c", "label": "Waveshare 5.83\" C (Yellow)"},
                    
                    # Waveshare Large IT8951 Displays
                    {"value": "waveshare_epd.it8951", "label": "Waveshare 6\" E-Ink (IT8951)"},
                    
                    # Waveshare 7 inch Displays
                    {"value": "waveshare_epd.epd7in3e", "label": "Waveshare 7.3\" E (Color)"},
                    {"value": "waveshare_epd.epd7in3f", "label": "Waveshare 7.3\" F (7-Color) ⭐"},
                    {"value": "waveshare_epd.epd7in3g", "label": "Waveshare 7.3\" G (4-Color)"},
                    {"value": "waveshare_epd.epd7in5", "label": "Waveshare 7.5\" E-Paper HAT"},
                    {"value": "waveshare_epd.epd7in5_V2", "label": "Waveshare 7.5\" V2"},
                    {"value": "waveshare_epd.epd7in5_HD", "label": "Waveshare 7.5\" HD"},
                    {"value": "waveshare_epd.epd7in5b", "label": "Waveshare 7.5\" B (Red)"},
                    {"value": "waveshare_epd.epd7in5b_V2", "label": "Waveshare 7.5\" B V2 (Red)"},
                    {"value": "waveshare_epd.epd7in5b_HD", "label": "Waveshare 7.5\" HD B (Red)"},
                    {"value": "waveshare_epd.epd7in5c", "label": "Waveshare 7.5\" C (Yellow)"},

                    # Waveshare Large Displays (10"+)
                    {"value": "waveshare_epd.epd10in2", "label": "Waveshare 10.2\" E-Paper - 960x640"},
                    {"value": "waveshare_epd.epd12in48", "label": "Waveshare 12.48\" E-Paper - 1304x984"},
                    {"value": "waveshare_epd.epd13in3E", "label": "Waveshare 13.3\" E (Spectra 6 E6) 6-Color - 1600x1200 ⭐"},
                    {"value": "waveshare_epd.epd13in3k", "label": "Waveshare 13.3\" K (Black & White) - 1600x1200"}
                ],
                "category": "eink_display"
            },
            "eink_dark_mode": {
                "type": "boolean",
                "label": t.get("eink_dark_mode", "Dark Mode E-Ink"),
                "description": t.get("eink_dark_mode_desc", "Enable dark mode for the e-ink display."),
                "default": False,
                "category": "eink_display"
            },
            "public_dashboard": {
                "type": "boolean",
                "label": t.get("public_dashboard", "Public Dashboard"),
                "description": t.get("public_dashboard_desc", "Allow unauthenticated users to view the dashboard. Admin login is still required to access settings."),
                "default": False,
                "category": "general",
                "order": 2
            },
            "color_mode_dark": {
                "type": "boolean",
                "label":  t.get("color_mode_dark", "Dark Mode"),
                "description":  t.get("color_mode_dark_desc", "Enable dark mode for the webinterface."),
                "default": True,
                "category": "general",
                "order": 3
            },
            "meme_management": {
                "type": "meme_management",
                "label": t.get("meme_management", "Meme Management"),
                "category": "meme_management"
            },
            "opsec_mode_enabled": {
                "type": "boolean",
                "label": t.get("opsec_mode_enabled", "OPSec Mode"),
                "description": t.get("opsec_mode_enabled_desc", "When enabled, the e-ink display shows a random cover image (family photo) instead of Bitcoin data. The web dashboard remains unaffected. Images rotate every 2 hours."),
                "default": False,
                "category": "opsec"
            },
            "opsec_management": {
                "type": "opsec_management",
                "label": t.get("opsec_management", "OPSec Images"),
                "category": "opsec"
            },
            # --- Donation block ---
            "show_donation_block": {
                "type": "boolean",
                "label": t.get("show_donation_block", "Show Donation Block"),
                "description": t.get("show_donation_block_desc", "Display the latest Lightning donation (amount + message) as an info block on the dashboard."),
                "default": False,
                "category": "donation"
            },
            "donation_display_mode": {
                "type": "select",
                "label": t.get("donation_display_mode", "Display mode"),
                "description": t.get("donation_display_mode_desc", "Choose whether to show the most recent donation or the largest one ever received."),
                "options": [
                    {"value": "latest",  "label": t.get("donation_mode_latest",  "Latest donation")},
                    {"value": "highest", "label": t.get("donation_mode_highest", "Largest donation")},
                    {"value": "auto",    "label": t.get("donation_mode_auto",    "Auto (latest → largest after 432 blocks)")},
                ],
                "default": "latest",
                "category": "donation"
            },
            "donation_webhook_hint": {
                "type": "info_text",
                "html": _donation_webhook_hint_html,
                "category": "donation",
                "always_visible": True
            },
            "webhook_relay_ws_url": {
                "type": "string",
                "label": t.get("webhook_relay_ws_url", "Webhook Relay WebSocket URL"),
                "placeholder": t.get("webhook_relay_ws_url_placeholder", "wss://your-host/ws/your-token"),
                "description": t.get("webhook_relay_ws_url_desc", "For Option B \u2014 paste the full WebSocket URL from your webhook-tester instance."),
                "default": "",
                "category": "donation",
                "sensitive": False
            },
            "color_donation_light": {
                "type": "color",
                "label": t.get("color_donation_light", "Donation (Light Mode)"),
                "description": t.get("color_donation_light_desc", "Color for donation amount and message text in light mode"),
                "default": "#F7931A",
                "category": "donation",
                "order": 1000
            },
            "color_donation_dark": {
                "type": "color",
                "label": t.get("color_donation_dark", "Donation (Dark Mode)"),
                "description": t.get("color_donation_dark_desc", "Color for donation amount and message text in dark mode"),
                "default": "#F7931A",
                "category": "donation",
                "order": 1001
            },
            "donation_history": {
                "type": "donation_history",
                "label": t.get("donation_history", "Donation History"),
                "category": "donation"
            },
        }

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
            {"id": "general", "label": t.get("general_settings", "General Settings"), "icon": "/static/icons/settings.svg"},
            {"id": "mempool", "label": t.get("mempool_settings", "Mempool"), "icon": "/static/icons/bottom_drawer.svg"},
            {"id": "eink_display", "label": t.get("eink_display", "E-Ink Display"), "icon": "/static/icons/photo_frame.svg"},
            {"id": "price_stats", "label": t.get("price_stats", "Price Stats"), "icon": "/static/icons/price_change.svg"},
            {"id": "countdown", "label": t.get("countdown_settings", "Countdown"), "icon": "/static/icons/price_change.svg"},
            {"id": "halving", "label": t.get("halving_settings", "Halving"), "icon": "/static/icons/price_change.svg"},
            {"id": "network_stats", "label": t.get("network_settings", "Network"), "icon": "/static/icons/calculate.svg"},
            {"id": "wallet_monitoring", "label": t.get("wallet_monitoring", "Wallet Monitoring"), "icon": "/static/icons/wallet.svg"},
            {"id": "bitaxe_stats", "label": t.get("bitaxe_stats", "Bitaxe Stats"), "icon": "/static/icons/calculate.svg"},
            {"id": "donation", "label": t.get("donation_settings", "Lightning Donation"), "icon": "/static/icons/price_change.svg"},
            {"id": "meme_management", "label": t.get("meme_management", "Meme Management"), "icon": "/static/icons/mood.svg"},
            {"id": "opsec", "label": t.get("opsec_settings", "OPSec"), "icon": "/static/icons/opsec.svg"},
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
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """
        Update specific configuration values.
        
        Args:
            updates (Dict): Configuration updates
            
        Returns:
            bool: True if successful
        """
        current_config = self.get_current_config()
        current_config.update(updates)
        return self.save_config(current_config)
