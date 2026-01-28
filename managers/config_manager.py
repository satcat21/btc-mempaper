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


class ConfigFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handles file system events for configuration file changes."""
    
    def __init__(self, config_manager):
        """Initialize with reference to config manager."""
        super().__init__() if WATCHDOG_AVAILABLE else None
        self.config_manager = config_manager
        self.last_modified = time.time()
        self.debounce_delay = 1.0  # 1 second debounce to avoid multiple reloads
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not WATCHDOG_AVAILABLE:
            return
            
        if event.is_directory:
            return
            
        # Check if it's our config file
        if os.path.abspath(event.src_path) == os.path.abspath(self.config_manager.config_path):
            current_time = time.time()
            
            # Debounce multiple rapid changes
            if current_time - self.last_modified > self.debounce_delay:
                self.last_modified = current_time
                
                # Reload configuration after a short delay
                threading.Timer(0.5, self.config_manager._reload_config_from_file).start()


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
                # print("🔐 Secure configuration manager initialized")
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
            
            # print(f"👁 Watching config file for changes: {self.config_path}")
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
                    print("📝 Config file changed but content is identical")
                    
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
            # print(f"✅ Plain configuration loaded from {self.config_path}")
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
                # print(f"✅ Secure configuration loaded from encrypted files")
                # Only update with sensitive fields from secure config
                sensitive_fields = {'wallet_balance_addresses_with_comments', 
                                  'block_reward_addresses_table', 'admin_password_hash', 'secret_key'}
                for key, value in secure_config.items():
                    if key in sensitive_fields:
                        merged_config[key] = value
                # print(f"⚙️ Added sensitive fields from secure configuration")
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
            "display_orientation": "vertical",
            "prioritize_large_scaled_meme": False,
            "mempool_host": "127.0.0.1",
            "mempool_rest_port": 4081,
            "mempool_ws_port": 8999,
            "mempool_ws_path": "/api/v1/ws",
            "mempool_use_https": False,
            "mempool_verify_ssl": True,
            "network_outage_tolerance_minutes": 45,  # Time to retry connection before giving up
            "fee_parameter": "minimumFee",
            "display_width": 800,
            "display_height": 480,
            "e-ink-display-connected": True,
            "omni_device_name": "waveshare_epd.epd7in3f",
            "admin_username": "admin",
            "admin_password": "mempaper2025",
            # --- Info block config additions ---
            "show_btc_price_block": True,
            "btc_price_currency": "USD",  # USD, EUR, GBP, CAD, CHF, AUD, JPY
            "show_bitaxe_block": True,
            "bitaxe_display_mode": "blocks",  # "blocks" or "difficulty"
            "bitaxe_miner_table": [],  # List of {address, comment} objects for table view
            "block_reward_addresses_table": [],  # List of {address, comment} objects for block reward monitoring
            "show_wallet_balances_block": True,
            "wallet_balance_addresses_with_comments": [],  # List of {address, comment, type} objects for table view
            "wallet_balance_unit": "sats",  # "btc" or "sats"
            "wallet_balance_currency": "EUR",  # USD, EUR, GBP, CAD, CHF, AUD, JPY - fiat currency for wallet balance display
            "prioritize_large_scaled_meme": False,
            "color_mode_dark": True,
            "live_block_notifications_enabled": True  # Enable live block notifications by default
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
                
                # Update in-memory config if we saved current config
                if config is None:
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
        if config.get("display_orientation", "") in valid_orientations:
            validated["display_orientation"] = config["display_orientation"]
        

        # Boolean settings
        bool_settings = [
            "prioritize_large_scaled_meme",
            "e-ink-display-connected",
            "show_btc_price_block",
            "show_bitaxe_block",
            "show_wallet_balances_block",
            "color_mode_dark",
            "eink_dark_mode",
            "live_block_notifications_enabled",
            "mempool_use_https",
            "mempool_verify_ssl"
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
        
        # Single value settings that should be passed through directly
        passthrough_settings = ["language", "display_orientation", "fee_parameter", "moscow_time_unit", "bitaxe_display_mode"]
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
            "show_bitaxe_block": {
                "type": "boolean",
                "label": t.get("show_bitaxe_block", "Show Bitaxe Hashrate/Blocks Block"),
                "description": t.get("show_bitaxe_block_desc", "Show Bitaxe hashrate and valid blocks info block if space allows."),
                "default": True,
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
            "show_wallet_balances_block": {
                "type": "boolean",
                "label": t.get("show_wallet_balances_block", "Show Wallet Balances Block"),
                "description": t.get("show_wallet_balances_block_desc", "Show wallet balances info block if space allows."),
                "default": True,
                "category": "wallet_monitoring"
            },
            "wallet_balance_addresses_with_comments": {
                "type": "wallet_table",
                "label": t.get("wallet_balance_addresses_table", "Wallet Monitoring Table"),
                "description": t.get("wallet_balance_addresses_table_desc", "Manage your wallet addresses, XPUBs, and ZPUBs with comments and balance monitoring."),
                "category": "wallet_monitoring"
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
                "category": "wallet_monitoring"
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
                "category": "wallet_monitoring"
            },
            "language": {
                "type": "select",
                "label": t.get("language", "Language"),
                "options": [
                    {"value": "en", "label": t.get("english", "English"), "flag": "🇺🇸"},
                    {"value": "de", "label": t.get("german", "Deutsch"), "flag": "🇩🇪"},
                    {"value": "es", "label": t.get("spanish", "Español"), "flag": "🇪🇸"},
                    {"value": "fr", "label": t.get("french", "Français"), "flag": "🇫🇷"},
                    {"value": "it", "label": t.get("italian", "Italiano"), "flag": "🇮🇹"}
                ],
                "category": "general"
            },
            "display_orientation": {
                "type": "toggle",
                "label": t.get("display_orientation", "Display Orientation"),
                "options": [
                    {"value": "vertical", "label": t.get("vertical", "Portrait"), "icon": "/static/icons/vertical.svg"},
                    {"value": "horizontal", "label": t.get("horizontal", "Landscape"), "icon": "/static/icons/horizontal.svg"}
                ],
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
                "category": "mempool"
            },
            "mempool_ws_port": {
                "type": "number", 
                "label": t.get("mempool_ws_port", "WebSocket Port"),
                "min": 1,
                "max": 65535,
                "description": t.get("mempool_ws_port_desc", "Port for real-time mempool updates"),
                "category": "mempool"
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
                "category": "mempool"
            },
            "mempool_verify_ssl": {
                "type": "boolean",
                "label": t.get("mempool_verify_ssl", "Verify SSL Certificates"),
                "description": t.get("mempool_verify_ssl_desc", "Verify SSL certificates when using HTTPS (disable for self-signed certificates)"),
                "default": True,
                "category": "mempool"
            },
            "mempool_ws_path": {
                "type": "text",
                "label": t.get("mempool_ws_path", "WebSocket Path"),
                "placeholder": "/api/v1/ws",
                "description": t.get("mempool_ws_path_desc", "WebSocket endpoint path for real-time updates"),
                "default": "/api/v1/ws",
                "category": "mempool"
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
                "description": t.get("prioritize_large_scaled_meme_desc", "When enabled, maximize meme display space by hiding holiday info and stats if necessary. Holiday takes priority over stats when both can't fit."),
                "default": False,
                "category": "general"
            },
            "omni_device_name": {
                "type": "select",
                "label": t.get("display_type", "Display Device Type"),
                "description": t.get("display_type_desc", "Select your specific e-paper display model"),
                "options": [
                    # Inky Displays
                    {"value": "inky.auto", "label": "Inky AutoDetect (try this first)"},
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
                    
                    # Waveshare Small Displays (1-2 inch)
                    {"value": "waveshare_epd.epd1in02", "label": "Waveshare 1.02\" E-Ink"},
                    {"value": "waveshare_epd.epd1in54", "label": "Waveshare 1.54\" E-Ink"},
                    {"value": "waveshare_epd.epd1in54_V2", "label": "Waveshare 1.54\" E-Ink V2"},
                    {"value": "waveshare_epd.epd1in54b", "label": "Waveshare 1.54\" B (Red)"},
                    {"value": "waveshare_epd.epd1in54b_V2", "label": "Waveshare 1.54\" B V2 (Red)"},
                    {"value": "waveshare_epd.epd1in54c", "label": "Waveshare 1.54\" C (Yellow)"},
                    {"value": "waveshare_epd.epd1in64g", "label": "Waveshare 1.64\" G (4-Color)"},
                    
                    # Waveshare 2 inch Displays
                    {"value": "waveshare_epd.epd2in13", "label": "Waveshare 2.13\" E-Paper HAT"},
                    {"value": "waveshare_epd.epd2in13_V2", "label": "Waveshare 2.13\" V2"},
                    {"value": "waveshare_epd.epd2in13_V3", "label": "Waveshare 2.13\" V3"},
                    {"value": "waveshare_epd.epd2in13b", "label": "Waveshare 2.13\" B (Red)"},
                    {"value": "waveshare_epd.epd2in13b_V3", "label": "Waveshare 2.13\" B V3 (Red)"},
                    {"value": "waveshare_epd.epd2in13c", "label": "Waveshare 2.13\" C (Yellow)"},
                    {"value": "waveshare_epd.epd2in13d", "label": "Waveshare 2.13\" D"},
                    {"value": "waveshare_epd.epd2in36g", "label": "Waveshare 2.36\" G (4-Color)"},
                    {"value": "waveshare_epd.epd2in66", "label": "Waveshare 2.66\" E-Paper"},
                    {"value": "waveshare_epd.epd2in66b", "label": "Waveshare 2.66\" B (Red)"},
                    {"value": "waveshare_epd.epd2in7", "label": "Waveshare 2.7\" E-Paper HAT"},
                    {"value": "waveshare_epd.epd2in7b", "label": "Waveshare 2.7\" B (Red)"},
                    {"value": "waveshare_epd.epd2in7b_V2", "label": "Waveshare 2.7\" B V2 (Red)"},
                    {"value": "waveshare_epd.epd2in9", "label": "Waveshare 2.9\" E-Paper"},
                    {"value": "waveshare_epd.epd2in9_V2", "label": "Waveshare 2.9\" V2"},
                    {"value": "waveshare_epd.epd2in9b", "label": "Waveshare 2.9\" B (Red)"},
                    {"value": "waveshare_epd.epd2in9b_V3", "label": "Waveshare 2.9\" B V3 (Red)"},
                    {"value": "waveshare_epd.epd2in9c", "label": "Waveshare 2.9\" C (Yellow)"},
                    {"value": "waveshare_epd.epd2in9d", "label": "Waveshare 2.9\" D"},
                    
                    # Waveshare 3-4 inch Displays
                    {"value": "waveshare_epd.epd3in0g", "label": "Waveshare 3\" G (4-Color)"},
                    {"value": "waveshare_epd.epd3in7", "label": "Waveshare 3.7\" E-Paper HAT"},
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
                    {"value": "waveshare_epd.epd7in5c", "label": "Waveshare 7.5\" C (Yellow)"}
                ],
                "category": "eink_display"
            },
            "display_width": {
                "type": "number",
                "label": t.get("width", "Display Width (pixels)"),
                "description": t.get("width_desc", "Display width in pixels"),
                "min": 100,
                "max": 2000,
                "category": "eink_display"
            },
            "display_height": {
                "type": "number",
                "label": t.get("height", "Display Height (pixels)"),
                "description": t.get("height_desc", "Display height in pixels"),
                "min": 100,
                "max": 2000,
                "category": "eink_display"
            },
            "eink_dark_mode": {
                "type": "boolean",
                "label": t.get("eink_dark_mode", "Dark Mode E-Ink"),
                "description": t.get("eink_dark_mode_desc", "Enable dark mode for the e-ink display."),
                "default": False,
                "category": "eink_display"
            },
            "admin_username": {
                "type": "text",
                "label": t.get("admin_username", "Admin Username"),
                "placeholder": "Administrator username",
                "description": t.get("admin_username_desc", "Username for accessing the settings page"),
                "category": "general"
            },
            "admin_password": {
                "type": "password",
                "label": t.get("admin_password", "Admin Password"),
                "placeholder": "Administrator password",
                "description": t.get("admin_password_desc", "Password for admin authentication"),
                "category": "general"
            },
            "color_mode_dark": {
                "type": "boolean",
                "label":  t.get("color_mode_dark", "Dark Mode"),
                "description":  t.get("color_mode_dark_desc", "Enable dark mode for the webinterface."),
                "default": True,
                "category": "general"
            },
            "live_block_notifications_enabled": {
                "type": "boolean",
                "label": t.get("enable_live_block_notifications", "Enable Live Block Notifications"),
                "description": t.get("enable_live_block_notifications_desc", "Show real-time toast notifications when new Bitcoin blocks are found. Provides immediate feedback on block discovery with mining pool and reward information."),
                "default": True,
                "category": "general"
            },
            "meme_management": {
                "type": "meme_management",
                "label": t.get("meme_management", "Meme Management"),
                "category": "meme_management"
            }
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
            {"id": "wallet_monitoring", "label": t.get("wallet_monitoring", "Wallet Monitoring"), "icon": "/static/icons/wallet.svg"},
            {"id": "bitaxe_stats", "label": t.get("bitaxe_stats", "Bitaxe Stats"), "icon": "/static/icons/calculate.svg"},
            {"id": "meme_management", "label": t.get("meme_management", "Meme Management"), "icon": "/static/icons/mood.svg"}
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
