"""Configuration validation and normalisation.

Holds the rules that keep a saved config coherent - notably the mempool
transport slots, where clearnet and Tor each own their ports and
mempool_use_tor selects which pair is live.
"""

from typing import Dict, Any
from utils.technical_config import (is_onion_host, normalize_host,
                                    MEMPOOL_DEFAULT_ONION, MEMPOOL_ONION_PRESETS,
                                    MEMPOOL_ONION_SUPERSEDED, DEVICE_DIMENSIONS)


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
        "eink_auto_disabled",
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
        "mempool_use_tor",
        "mempool_is_private",
        "opsec_mode_enabled",
        "public_dashboard",
        "auto_update_enabled",
    ]
    for setting in bool_settings:
        if setting in config:
            validated[setting] = bool(config[setting])

    # Reaching validation means a human saved the config, so whatever they chose
    # for the display is deliberate. Drop the auto-disable marker: startup only
    # retries a display *we* switched off, and must never override the operator.
    # The auto-disable path itself writes through save_config(), which does not
    # validate, so its own marker survives.
    if "e-ink-display-connected" in config:
        validated["eink_auto_disabled"] = False

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
        "tor_socks_host",
        "mempool_username",
        "mempool_password",
        "omni_device_name",
        "admin_username",
        "admin_password",
    ]
    for setting in string_settings:
        if setting in config and isinstance(config[setting], str):
            validated[setting] = config[setting].strip()

    # Validate auto_update_time (HH:MM format, 00:00–23:59)
    if "auto_update_time" in config and isinstance(config["auto_update_time"], str):
        import re
        m = re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', config["auto_update_time"].strip())
        if m:
            validated["auto_update_time"] = config["auto_update_time"].strip()

    # Integer settings with validation (including backwards compatibility)
    int_settings = {
        "mempool_rest_port": (1, 65535),
        "mempool_ws_port": (1, 65535),
        "tor_socks_port": (1, 65535),
        "network_outage_tolerance_minutes": (5, 10080),  # 5 min to 1 week
        "display_width": (100, 2000),
        "display_height": (100, 2000),
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
        _w, _h = DEVICE_DIMENSIONS[device_name]
        _changed = (config.get("display_width"), config.get("display_height")) != (_w, _h)
        validated["display_width"], validated["display_height"] = _w, _h
        # Every save runs this, and the answer is fixed per device, so only a
        # real change is worth reporting.
        if _changed:
            print(f"⚙️ Auto-set display dimensions for {device_name}: {_w}×{_h}")

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
    
    # Auto-update days (list of day abbreviations)
    valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if "auto_update_days" in config and isinstance(config["auto_update_days"], list):
        validated["auto_update_days"] = [d for d in config["auto_update_days"] if d in valid_days]

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
        "color_date_start_light", "color_date_end_light",
        "color_date_start_dark", "color_date_end_dark",
        "color_holiday_start_light", "color_holiday_end_light",
        "color_holiday_start_dark", "color_holiday_end_dark",
        "color_btc_price_light", "color_btc_price_dark",
        "color_bitaxe_stats_light", "color_bitaxe_stats_dark",
        "color_wallets_light", "color_wallets_dark",
        "webhook_relay_ws_url", "donation_webhook_token", "donation_display_mode",
        "color_donation_light", "color_donation_dark",
        "color_countdown_light", "color_countdown_dark",
        "color_halving_light", "color_halving_dark",
        "color_network_light", "color_network_dark",
    ]
    for setting in passthrough_settings:
        if setting in config:
            validated[setting] = config[setting]

    # Preserve runtime-generated tokens that are never sent by the web UI.
    # Falls back to the current in-memory value so a web save never erases them.
    if 'donation_webhook_token' not in validated:
        existing = self.config.get('donation_webhook_token', '')
        if existing:
            validated['donation_webhook_token'] = existing
    
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

    # Users paste whole URLs into the host field; keep only the hostname so
    # build_mempool_api_url() does not end up with a doubled scheme.
    if "mempool_host" in validated:
        _clean = normalize_host(validated["mempool_host"])
        if _clean != validated["mempool_host"]:
            print(f"🌐 Normalized mempool_host to '{_clean}'")
        validated["mempool_host"] = _clean

    _host = validated.get("mempool_host", "")

    # Migrate an onion address that a previous release shipped as official
    # and has since replaced. Config files are user data and survive
    # updates, so without this an existing install stays pointed at a dead
    # hidden service even though the new address shipped in the update.
    if _host and _host in MEMPOOL_ONION_SUPERSEDED:
        print(f"🧅 Onion address '{_host[:16]}…' has been superseded — "
              f"migrating to the current official address.")
        _host = MEMPOOL_DEFAULT_ONION
        validated["mempool_host"] = _host

    # Tor on with no host at all — fall back to the official onion rather
    # than leaving an unusable blank. A host that is already set is never
    # replaced: a self-hosted instance may have its own hidden service.
    if validated.get("mempool_use_tor", False) and not _host:
        _host = MEMPOOL_DEFAULT_ONION
        validated["mempool_host"] = _host
        print(f"🧅 Tor enabled with no host set — defaulting to the official "
              f"mempool onion service.")

    # An .onion host cannot be resolved by the OS resolver, so it is only
    # reachable through the SOCKS proxy — the host itself implies Tor.
    # Resolved before the transport slots below, which key off the result.
    if is_onion_host(_host) and not validated.get("mempool_use_tor", False):
        validated["mempool_use_tor"] = True
        print("🧅 mempool_host is an .onion address — enabling Tor routing, "
              "since onion names cannot resolve without it.")

    # ── Transport slots ───────────────────────────────────────────────────
    # Clearnet and Tor each own their scheme and ports permanently, and
    # mempool_use_tor selects which pair is live. A single set of fields
    # plus a snapshot taken on transition would have to infer from history
    # whether a submitted port was typed by the user or merely echoed back
    # by the form; two slots need no such guess, and switching destroys
    # nothing. mempool_use_https / _rest_port / _ws_port remain the live
    # values, so every consumer reads them unchanged.
    try:
        _prev_cfg = self.config or {}
    except Exception:
        _prev_cfg = {}

    _tor = bool(validated.get("mempool_use_tor", False))
    _slot = "tor" if _tor else "clearnet"

    # No https flag for Tor: the onion address is the service's public key,
    # so the circuit already authenticates it. Tor traffic is always http.
    _slot_defaults = {
        "mempool_use_https_clearnet": True, "mempool_rest_port_clearnet": 443,
        "mempool_ws_port_clearnet": 443,
        "mempool_rest_port_tor": 80, "mempool_ws_port_tor": 80,
    }
    _known = False
    for _k, _d in _slot_defaults.items():
        # Internal fields: the form never submits them, so carry them across
        # a save rather than letting them fall back to defaults.
        if _k in config:
            validated[_k] = config[_k]; _known = True
        elif _k in _prev_cfg:
            validated[_k] = _prev_cfg[_k]; _known = True
        else:
            validated[_k] = _d

    if not _known:
        # Config predates the slots: adopt its ports as the live slot's,
        # leaving the other at its default.
        validated[f"mempool_rest_port_{_slot}"] = validated.get("mempool_rest_port", 443)
        validated[f"mempool_ws_port_{_slot}"] = validated.get("mempool_ws_port", 443)
        if not _tor:
            validated["mempool_use_https_clearnet"] = bool(validated.get("mempool_use_https", True))

    # An edit belongs to whichever slot is live — except on the save that
    # flips Tor, where the form still carries the *previous* slot's numbers.
    # Taking them would write clearnet ports into the Tor slot.
    _tor_flipped = _tor != bool(_prev_cfg.get("mempool_use_tor", False))
    if not _tor_flipped:
        if "mempool_rest_port" in config:
            validated[f"mempool_rest_port_{_slot}"] = validated.get("mempool_rest_port")
        if "mempool_ws_port" in config:
            validated[f"mempool_ws_port_{_slot}"] = validated.get("mempool_ws_port")
        # Only clearnet has a scheme to choose.
        if not _tor and "mempool_use_https" in config:
            validated["mempool_use_https_clearnet"] = bool(validated.get("mempool_use_https"))

    # A known onion service dictates its own port, so the Tor slot is not
    # the user's to set for it: a port carried over from a clearnet instance
    # refuses every connection against a service listening on 80.
    _preset = next((p for p in MEMPOOL_ONION_PRESETS if p["host"] == _host), None)
    if _preset:
        validated["mempool_rest_port_tor"] = _preset["port"]
        validated["mempool_ws_port_tor"] = _preset["port"]

    # Project the live slot onto the fields the rest of the app reads.
    validated["mempool_use_https"] = False if _tor else bool(validated["mempool_use_https_clearnet"])
    validated["mempool_rest_port"] = validated[f"mempool_rest_port_{_slot}"]
    validated["mempool_ws_port"] = validated[f"mempool_ws_port_{_slot}"]

    if _tor_flipped:
        print(f"🧅 Tor {'enabled' if _tor else 'disabled'} — using the "
              f"{_slot} transport: "
              f"{'https' if validated['mempool_use_https'] else 'http'} on "
              f"port {validated['mempool_rest_port']}.")

    return validated
