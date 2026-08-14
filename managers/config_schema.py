"""Web UI form schema: field types, labels, options and categories.

Separate from ConfigManager because it changes whenever the settings page
gains a field, which has nothing to do with how config is loaded or saved.
"""

from typing import Dict, Any


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

    from tools.configure_display import DEVICE_CONFIGS
    _current_device_id = self.config.get('omni_device_name', '')
    _current_device_info = DEVICE_CONFIGS.get(_current_device_id)
    if _current_device_info:
        # Device model names are proper nouns - not translated, same as before.
        _current_device_option = {"value": _current_device_id, "label": _current_device_info['name']}
    else:
        # No (recognized) display configured
        _current_device_option = {
            "value": _current_device_id,
            "label": t.get('no_display_drivers_installed', 'No display drivers installed'),
            "_lk": "no_display_drivers_installed",
        }

    schema = {
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
                {"value": "sats", "label": t.get("moscow_time_unit_sats", "Satoshis (e.g., 50,000 sats)"), "_lk": "moscow_time_unit_sats"},
                {"value": "hour", "label": t.get("moscow_time_unit_hour", "Time Format (e.g., 08:41)"),    "_lk": "moscow_time_unit_hour"}
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
                {"value": "blocks",     "label": t.get("bitaxe_mode_blocks",     "Found Blocks"),   "_lk": "bitaxe_mode_blocks"},
                {"value": "difficulty", "label": t.get("bitaxe_mode_difficulty", "Best Difficulty"), "_lk": "bitaxe_mode_difficulty"}
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
            "_lk": "wallet_balance_addresses_table",
            "description": t.get("wallet_balance_addresses_table_desc", "Manage your wallet addresses, XPUBs, and ZPUBs with comments and balance monitoring."),
            "_dk": "wallet_balance_addresses_table_desc",
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
                {"value": "en", "label": t.get("english", "English"),  "_lk": "english",  "flag": "<img src='/static/icons/en.svg' alt='English' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                {"value": "de", "label": t.get("german",  "Deutsch"),  "_lk": "german",   "flag": "<img src='/static/icons/de.svg' alt='Deutsch' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                {"value": "es", "label": t.get("spanish", "Español"),  "_lk": "spanish",  "flag": "<img src='/static/icons/es.svg' alt='Español' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                {"value": "fr", "label": t.get("french",  "Français"), "_lk": "french",   "flag": "<img src='/static/icons/fr.svg' alt='Français' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"},
                {"value": "it", "label": t.get("italian", "Italiano"), "_lk": "italian",  "flag": "<img src='/static/icons/it.svg' alt='Italiano' style='width:20px;height:14px;border-radius:2px;vertical-align:middle;'>"}
            ],
            "category": "general",
            "order": 1
        },
        "fee_parameter": {
            "type": "select",
            "label": t.get("fee_parameter", "Fee Used for the Block Height"),
            "description": t.get("fee_parameter_desc", "Which fee level is printed under the block height and compared against the rolling median to colour it. Pick the priority you actually transact at: a fast fee reads warm more often, a minimum fee cool."),
            "default": "minimumFee",
            "options": [
                {"value": "fastestFee",  "label": t.get("fastest",   "Fastest (~1 block)"),      "_lk": "fastest"},
                {"value": "halfHourFee", "label": t.get("half_hour", "Half Hour (~3 blocks)"),  "_lk": "half_hour"},
                {"value": "hourFee",     "label": t.get("hour",      "Hour (~6 blocks)"),        "_lk": "hour"},
                {"value": "economyFee",  "label": t.get("economy",   "Economy (~1 day)"),        "_lk": "economy"},
                {"value": "minimumFee",  "label": t.get("minimum",   "Minimum"),                 "_lk": "minimum"}
            ],
            "category": "mempool"
        },
        "fee_color_mode": {
            "type": "select",
            "label": t.get("fee_color_mode", "Block Height Color Scale"),
            "description": t.get("fee_color_mode_desc",
                                 "How the fee is turned into a color. The relative scales compare "
                                 "the current fee against a rolling median, so a cheap moment still "
                                 "looks cheap in a low-fee year."),
            "default": "relative_neutral",
            "options": [
                {"value": "relative_neutral", "label": t.get("fee_mode_neutral", "Relative — neutral at normal"), "_lk": "fee_mode_neutral"},
                {"value": "relative_rainbow", "label": t.get("fee_mode_rainbow", "Relative — blue to red"),       "_lk": "fee_mode_rainbow"},
                {"value": "absolute",         "label": t.get("fee_mode_absolute", "Fixed sat/vB thresholds"),     "_lk": "fee_mode_absolute"}
            ],
            "category": "_block_height_color"
        },
        "color_block_height_light": {
            "type": "color",
            "label": t.get("color_block_height_light", "Block Height (Light Mode)"),
            "description": t.get("color_block_height_light_desc",
                                 "Base color for the block height digits in light mode. The fee "
                                 "reading sits at the bottom of the number and a lighter tone of "
                                 "this color at the top."),
            "default": "#3C3C46",
            "category": "_block_height_color"
        },
        "color_block_height_dark": {
            "type": "color",
            "label": t.get("color_block_height_dark", "Block Height (Dark Mode)"),
            "description": t.get("color_block_height_dark_desc",
                                 "Base color for the block height digits in dark mode. This color "
                                 "sits at the top of the number and the fee reading, lightened, "
                                 "at the bottom."),
            "default": "#C8C8D2",
            "category": "_block_height_color"
        },
        "fee_baseline_days": {
            "type": "number",
            "label": t.get("fee_baseline_days", "Fee Baseline Window (days)"),
            "min": 3,
            "max": 90,
            "default": 30,
            "description": t.get("fee_baseline_days_desc",
                                 "How far back to look when deciding what a normal fee is. "
                                 "Ignored by the fixed-threshold scale."),
            "category": "mempool",
            "advanced": True,
            "order": 6
        },
        "fee_neutral_band_pct": {
            "type": "number",
            "label": t.get("fee_neutral_band_pct", "Neutral Band (%)"),
            "min": 0,
            "max": 50,
            "default": 5,
            "description": t.get("fee_neutral_band_pct_desc",
                                 "How close to the median still counts as normal, and so renders "
                                 "in the neutral color. Only used by the neutral relative scale."),
            "category": "mempool",
            "advanced": True,
            "order": 7
        },
        "mempool_host": {
            "type": "text",
            "label": t.get("mempool_host", "Mempool Server Host"),
            "placeholder": "192.168.0.119 or mempool.mydomain.com",
            "description": t.get("mempool_host_desc", "IP address or domain name of your mempool server"),
            "category": "mempool"
        },
        "mempool_is_private": {
            "type": "hidden_boolean",
            "label": "",
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
        "_mempool_actions": {
            "type": "mempool_actions",
            "label_check": t.get("check_connection", "Check Connection"),
            "_lk_check": "check_connection",
            "label_open": t.get("open_mempool", "Open Mempool"),
            "_lk_open": "open_mempool",
            "category": "mempool",
            "order": 1000
        },
        "mempool_use_tor": {
            "type": "boolean",
            "label": t.get("mempool_use_tor", "Connect via Tor"),
            "_lk": "mempool_use_tor",
            "description": t.get(
                "mempool_use_tor_desc",
                "Route all mempool traffic through a local Tor daemon. Lets you use an .onion "
                "address so the instance operator never sees your home IP. Requires Tor running "
                "on this device. Bitaxe stays on the LAN and is never proxied."
            ),
            "_dk": "mempool_use_tor_desc",
            "default": False,
            "category": "mempool",
            "order": 2
        },
        "tor_socks_host": {
            "type": "text",
            "label": t.get("tor_socks_host", "Tor SOCKS Host"),
            "_lk": "tor_socks_host",
            "placeholder": "127.0.0.1",
            "default": "127.0.0.1",
            "category": "mempool",
            "advanced": True,
            "order": 6
        },
        "tor_socks_port": {
            "type": "number",
            "label": t.get("tor_socks_port", "Tor SOCKS Port"),
            "_lk": "tor_socks_port",
            "min": 1,
            "max": 65535,
            "default": 9050,
            "description": t.get("tor_socks_port_desc", "Usually 9050 for the Tor daemon, 9150 for Tor Browser."),
            "_dk": "tor_socks_port_desc",
            "category": "mempool",
            "advanced": True,
            "order": 7
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
        "date_color_group": {
            "type": "date_color_group",
            "label": t.get("date_color_group_label", "Date Gradient Colors"),
            "_lk": "date_color_group_label",
            "category": "general",
            "order": 5,
            "advanced": True
        },
        "color_date_start_light": {
            "type": "color",
            "label": t.get("color_date_start_light", "Start Color"),
            "default": "#1c82c0",
            "category": "_date_color"
        },
        "color_date_end_light": {
            "type": "color",
            "label": t.get("color_date_end_light", "End Color"),
            "default": "#3C3C46",
            "category": "_date_color"
        },
        "color_date_start_dark": {
            "type": "color",
            "label": t.get("color_date_start_dark", "Start Color"),
            "default": "#4FC3F7",
            "category": "_date_color"
        },
        "color_date_end_dark": {
            "type": "color",
            "label": t.get("color_date_end_dark", "End Color"),
            "default": "#C8C8D2",
            "category": "_date_color"
        },
        "holiday_color_group": {
            "type": "holiday_color_group",
            "label": t.get("holiday_color_group_label", "Holiday Text Gradient Colors"),
            "_lk": "holiday_color_group_label",
            "category": "general",
            "order": 6,
            "advanced": True
        },
        "color_holiday_start_light": {
            "type": "color",
            "label": t.get("color_holiday_start_light", "Start Color"),
            "default": "#F7931A",
            "category": "_holiday_color"
        },
        "color_holiday_end_light": {
            "type": "color",
            "label": t.get("color_holiday_end_light", "End Color"),
            "default": "#C62828",
            "category": "_holiday_color"
        },
        "color_holiday_start_dark": {
            "type": "color",
            "label": t.get("color_holiday_start_dark", "Start Color"),
            "default": "#F7931A",
            "category": "_holiday_color"
        },
        "color_holiday_end_dark": {
            "type": "color",
            "label": t.get("color_holiday_end_dark", "End Color"),
            "default": "#FF6F6F",
            "category": "_holiday_color"
        },
        "block_height_color_group": {
            "type": "block_height_color_group",
            "label": t.get("block_height_color_group_label", "Block Height Color & Scale"),
            "_lk": "block_height_color_group_label",
            "description": t.get("block_height_color_group_desc",
                                 "The base color of the block height digits and how the current "
                                 "fee is turned into the other end of the gradient."),
            "category": "general",
            "order": 7,
            "advanced": True
        },
        "omni_device_name": {
            "type": "select",
            "label": t.get("display_type", "Display Device Type"),
            "_lk": "display_type",
            "options": [_current_device_option],
            "disabled": True,
            "category": "eink_display"
        },
        "eink_dark_mode": {
            "type": "toggle",
            "label": t.get("eink_dark_mode", "E-Ink Theme"),
            "description": t.get("eink_dark_mode_desc", "Select theme for the e-ink display."),
            "options": [
                {"value": False, "label": t.get("theme_light", "Light"), "_lk": "theme_light", "_tk": "theme_light_tooltip", "icon": "/static/icons/light.svg"},
                {"value": True,  "label": t.get("theme_dark",  "Dark"),  "_lk": "theme_dark",  "_tk": "theme_dark_tooltip",  "icon": "/static/icons/dark.svg"},
            ],
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
            "type": "toggle",
            "label":  t.get("color_mode_dark", "Web Theme"),
            "description":  t.get("color_mode_dark_desc", "Select theme for the web interface."),
            "options": [
                {"value": False, "label": t.get("theme_light", "Light"), "_lk": "theme_light", "_tk": "theme_light_tooltip", "icon": "/static/icons/light.svg"},
                {"value": True,  "label": t.get("theme_dark",  "Dark"),  "_lk": "theme_dark",  "_tk": "theme_dark_tooltip",  "icon": "/static/icons/dark.svg"},
            ],
            "default": True,
            "category": "general",
            "order": 3
        },
        "meme_management": {
            "type": "meme_management",
            "label": t.get("meme_management", "Meme Management"),
            "category": "meme_management"
        },
        # --- Network-bound encryption (Tang) ---
        "tang_enabled": {
            "type": "boolean",
            "label": t.get("tang_enabled", "Network-Bound Encryption (Tang)"),
            "_lk": "tang_enabled",
            "description": t.get("tang_enabled_desc", "Seal wallet addresses, balance caches and rendered images with a key held on a Tang server on your LAN, so a stolen device cannot decrypt them. If the server is unreachable those blocks are disabled until it returns; the rest of mempaper keeps running. Requires the clevis package and a reachable Tang server."),
            "_dk": "tang_enabled_desc",
            "default": False,
            "category": "general",
            "advanced": True,
            "order": 40
        },
        "tang_url": {
            "type": "text",
            "label": t.get("tang_url", "Tang Server URL"),
            "_lk": "tang_url",
            "placeholder": "http://192.168.1.50:7500",
            "default": "",
            "description": t.get("tang_url_desc", "Address of the Tang server on your local network. Never expose this to the internet - reachability is what grants access."),
            "_dk": "tang_url_desc",
            "category": "general",
            "advanced": True,
            "order": 41
        },
        "tang_thumbprint": {
            "type": "text",
            "label": t.get("tang_thumbprint", "Tang Key Thumbprint"),
            "_lk": "tang_thumbprint",
            "placeholder": "faYWs5gMZ4MOKVmw_70zIvgZuzPd6AZnrsF86OgewnI",
            "default": "",
            # 43 characters of base64 is unreadable noise at rest. Shortened
            # like a wallet address, full value on click.
            "masked": True,
            "description": t.get("tang_thumbprint_desc", "Signing-key thumbprint of your Tang server, from tang-show-keys. Pinning it stops anything else on the LAN from impersonating the server. Leave empty only if you accept that risk."),
            "_dk": "tang_thumbprint_desc",
            "category": "general",
            "advanced": True,
            "order": 42
        },
        "tang_check": {
            "type": "tang_check",
            "label": t.get("tang_check", "Tang Connection"),
            "label_check": t.get("check_tang_connection", "Check Tang Connection"),
            "_lk": "tang_check",
            "description": t.get("tang_check_desc", "Tests the whole path against the values above: reaches the server, reads its signing key, then seals and unseals a throwaway key. Nothing is written and no wallet data is touched."),
            "_dk": "tang_check_desc",
            "category": "general",
            "advanced": True,
            "order": 43
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
        # --- Meme sync schedule ---
        "meme_sync_enabled": {
            "type": "boolean",
            "label": t.get("meme_sync_enabled", "Auto-Sync Memes"),
            "description": t.get("meme_sync_enabled_desc", "Schedule a weekly check for new memes on einundzwanzig-memes.space. Writes a crontab entry for the mempaper user — no manual crontab editing needed."),
            "default": False,
            "category": "meme_sync"
        },
        "meme_sync_day": {
            "type": "select",
            "label": t.get("meme_sync_day", "Day"),
            "description": t.get("meme_sync_day_desc", "Day of the week to check for new memes."),
            "options": [
                {"value": "0", "label": t.get("day_sunday",    "Sunday")},
                {"value": "1", "label": t.get("day_monday",    "Monday")},
                {"value": "2", "label": t.get("day_tuesday",   "Tuesday")},
                {"value": "3", "label": t.get("day_wednesday", "Wednesday")},
                {"value": "4", "label": t.get("day_thursday",  "Thursday")},
                {"value": "5", "label": t.get("day_friday",    "Friday")},
                {"value": "6", "label": t.get("day_saturday",  "Saturday")},
            ],
            "default": "4",
            "category": "meme_sync"
        },
        "meme_sync_hour": {
            "type": "select",
            "label": t.get("meme_sync_hour", "Time"),
            "description": t.get("meme_sync_hour_desc", "Hour of day to run the sync (24-hour clock)."),
            "options": [{"value": str(h), "label": f"{h:02d}:00"} for h in range(24)],
            "default": "13",
            "category": "meme_sync"
        },
        "tor_meme_downloads": {
            "type": "boolean",
            "label": t.get("tor_meme_downloads", "Route via Tor"),
            "description": t.get("tor_meme_downloads_desc", "Hide your IP from the meme server by routing downloads through Tor (SOCKS5 127.0.0.1:9050). Requires: sudo apt install tor — the Tor daemon must be running."),
            "default": False,
            "category": "meme_sync"
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
                {"value": "latest",  "label": t.get("donation_mode_latest",  "Latest donation"),                       "_lk": "donation_mode_latest"},
                {"value": "highest", "label": t.get("donation_mode_highest", "Largest donation"),                      "_lk": "donation_mode_highest"},
                {"value": "auto",    "label": t.get("donation_mode_auto",    "Auto (latest → largest after 432 blocks)"), "_lk": "donation_mode_auto"},
            ],
            "default": "latest",
            "category": "donation"
        },
        "donation_webhook_hint": {
            "type": "info_text",
            "html": _donation_webhook_hint_html,
            "_html_builder": "donation_webhook",
            "category": "donation",
            "always_visible": True,
            "advanced": True
        },
        "webhook_relay_ws_url": {
            "type": "string",
            "label": t.get("webhook_relay_ws_url", "Webhook Relay WebSocket URL"),
            "placeholder": t.get("webhook_relay_ws_url_placeholder", "wss://your-host/ws/your-token"),
            "description": t.get("webhook_relay_ws_url_desc", "For Option B \u2014 paste the full WebSocket URL from your webhook-tester instance."),
            "default": "",
            "category": "donation",
            "sensitive": False,
            "advanced": True
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

        # ── Auto Update Settings ───────────────────────────────
        "auto_update_enabled": {
            "type": "boolean",
            "label": t.get("auto_update_enabled", "Automatic Updates"),
            "description": t.get("auto_update_enabled_desc", "Automatically install mempaper releases and system package updates on a schedule"),
            "default": False,
            "category": "updates",
            "order": 0
        },
        "auto_update_time": {
            "type": "time",
            "label": t.get("auto_update_time", "Update Time"),
            "description": t.get("auto_update_time_desc", "Time of day to run automatic updates (HH:MM)"),
            "default": "05:00",
            "category": "updates",
            "order": 1
        },
        "auto_update_days": {
            "type": "multiselect",
            "label": t.get("auto_update_days", "Update Days"),
            "description": t.get("auto_update_days_desc", "Days of the week to run automatic updates"),
            "default": ["mon", "wed", "fri"],
            "options": [
                {"value": "mon", "label": t.get("day_monday",   "Monday"),    "_lk": "day_monday"},
                {"value": "tue", "label": t.get("day_tuesday",  "Tuesday"),   "_lk": "day_tuesday"},
                {"value": "wed", "label": t.get("day_wednesday","Wednesday"), "_lk": "day_wednesday"},
                {"value": "thu", "label": t.get("day_thursday", "Thursday"),  "_lk": "day_thursday"},
                {"value": "fri", "label": t.get("day_friday",   "Friday"),    "_lk": "day_friday"},
                {"value": "sat", "label": t.get("day_saturday", "Saturday"), "_lk": "day_saturday"},
                {"value": "sun", "label": t.get("day_sunday", "Sunday"),     "_lk": "day_sunday"},
            ],
            "category": "updates",
            "order": 2
        },
    }
    # Add translation keys to every field so the client can update labels on language switch.
    # Convention: field label key = field key, description key = field key + "_desc".
    # Fields may set _lk/_dk explicitly (when the translation key differs from the schema key).
    for fk, fv in schema.items():
        if '_lk' not in fv:
            fv['_lk'] = fk
        if '_dk' not in fv:
            fv['_dk'] = fk + '_desc'
    return schema
