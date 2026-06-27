# CONFIGURATION REFERENCE

This document provides a comprehensive list of all configuration settings available in mempaper.
These settings can be modified via the Web Dashboard (recommended) or by editing `config/config.json`.

---

## GENERAL APPEARANCE

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | `language` | Select | Interface language | `en` (English), `de` (German), `es` (Spanish), `fr` (French), `it` (Italian) |
| **Web Orientation** | `web_orientation` | Toggle | Web dashboard orientation | `vertical` (Portrait), `horizontal` (Landscape) |
| **E-ink Orientation** | `eink_orientation` | Toggle | E-ink display orientation | `vertical` (Portrait), `horizontal` (Landscape) |
| **Color Mode** | `color_mode_dark` | Switch | Dark theme for dashboard | `true` (Dark), `false` (Light) |
| **E-Ink Dark Mode** | `eink_dark_mode` | Switch | Invert colors for E-ink | `true` (Inverted/Night), `false` (Standard) |
| **Prioritize Large Memes** | `prioritize_large_scaled_meme` | Switch | Maximize meme size vs info blocks | `true` (Large Memes), `false` (Balanced) |

---

## COLOR CUSTOMIZATION

| Web Label | Config Key | Type | Description | Default Light / Dark |
| :--- | :--- | :--- | :--- | :--- |
| **Date Gradient Start** | `color_date_start_light`<br>`color_date_start_dark` | Color | Gradient start color for the date display | `#1c82c0` / `#4FC3F7` |
| **Date Gradient End** | `color_date_end_light`<br>`color_date_end_dark` | Color | Gradient end color for the date display | `#c040a8` / `#BA68C8` |
| **Holiday Start Color** | `color_holiday_start_light`<br>`color_holiday_start_dark` | Color | Gradient start color for holiday events | `#F7931A` / `#F7931A` |
| **Holiday End Color** | `color_holiday_end_light`<br>`color_holiday_end_dark` | Color | Gradient end color for holiday events | `#C62828` / `#FF6F6F` |
| **BTC Price Color** | `color_btc_price_light`<br>`color_btc_price_dark` | Color | Text color for Bitcoin price | `#17805B` / `#00C896` |
| **Countdown Color** | `color_countdown_light`<br>`color_countdown_dark` | Color | Text color for supply countdown | `#C55A00` / `#FF9E40` |
| **Halving Color** | `color_halving_light`<br>`color_halving_dark` | Color | Text color for halving countdown | `#1565C0` / `#4FC3F7` |
| **Network Color** | `color_network_light`<br>`color_network_dark` | Color | Text color for network stats | `#6A1B9A` / `#CE93D8` |
| **Bitaxe Color** | `color_bitaxe_stats_light`<br>`color_bitaxe_stats_dark` | Color | Text color for mining stats | `#B89C1D` / `#FFE566` |
| **Wallet Color** | `color_wallets_light`<br>`color_wallets_dark` | Color | Text color for wallet balances | `#1565C0` / `#09A3BA` |
| **Donation Color** | `color_donation_light`<br>`color_donation_dark` | Color | Text color for donation block | `#F7931A` / `#F7931A` |

---

## MEMPOOL INTEGRATION

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Mempool Host** | `mempool_host` | String | Mempool instance hostname | `mempool.space` (public), `192.168.1.50` (local) |
| **Private/Self-Hosted** | `mempool_is_private` | Switch | Marks the instance as self-hosted on your local network; disables privacy warnings for wallet monitoring | `true` (private), `false` (public, default) |
| **Use HTTPS/SSL** | `mempool_use_https` | Switch | Secure connection | `true` (https://), `false` (http://) |
| **Verify SSL Cert** | `mempool_verify_ssl` | Switch | Validate SSL certificate | `true` (Verify), `false` (Skip -- for self-signed) |
| **REST Port** | `mempool_rest_port` | Number | API port | `443` (public), `80`, `3006` (local MyNode/Umbrel) |
| **WebSocket Port** | `mempool_ws_port` | Number | Real-time data port | `443` (public), `8999` (local standard) |
| **WebSocket Path** | `mempool_ws_path` | String | Websocket endpoint path | `/api/v1/ws` (default) |
| **Username** | `mempool_username` | String | Optional Basic auth username | Leave empty if not required |
| **Password** | `mempool_password` | String | Optional Basic auth password | Leave empty if not required |
| **Fee Preference** | `fee_parameter` | Select | Which fee to display | `fastestFee` (High Priority), `halfHourFee` (Standard), `hourFee` (Low Priority), `economyFee` (Economy), `minimumFee` (No Priority) |

---

## DISPLAY HARDWARE

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **E-Ink Display Connected** | `e-ink-display-connected` | Switch | Enable hardware driver | `true` (Enable), `false` (Disable) |
| **Display Driver** | `omni_device_name` | String | Driver name (Native or Omni-EPD) | `epd13in3E` (Recommended -- Waveshare 13.3"), `epd7in3f` (Default -- Waveshare 7.3"), `inky.impression`, `inky.auto` |
| **Display Width** | `display_width` | Number | Resolution Width (pixels) -- Auto-set by device selection | Automatically determined from selected device or orientation |
| **Display Height** | `display_height` | Number | Resolution Height (pixels) -- Auto-set by device selection | Automatically determined from selected device or orientation |
| **Skip Clear Display** | `skip_clear_display` | Boolean | Skip clearing before refresh (faster) | `true` (Fast ~39s, default), `false` (Full clear ~70s) |

---

## BITCOIN PRICE BLOCK

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Price Block** | `show_btc_price_block` | Switch | Display fiat price info | `true`, `false` |
| **Currency** | `btc_price_currency` | Select | Fiat currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |
| **Moscow Time Unit** | `moscow_time_unit` | Select | Format for Sats/Fiat | `sats` (e.g. 3432 sats), `hour` (e.g. 03:42) |

---

## BITAXE / MINING STATS

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Bitaxe Block** | `show_bitaxe_block` | Switch | Display mining block | `true`, `false` |
| **Bitaxe Display Mode** | `bitaxe_display_mode` | Select | What to show on right side | `blocks` (Found Blocks), `difficulty` (Best Difficulty) |
| **Miner Table** | `bitaxe_miner_table` | List | Miner IP addresses | `[{"address": "192.168.1.20", "comment": "Axe 1"}]` |
| **Block Rewards Table** | `block_reward_addresses_table` | List | Addresses to watch for coinbase | `[{"address": "bc1q...", "comment": "Solo Pool"}]` |

---

## WALLET MONITORING

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Wallet Block** | `show_wallet_balances_block` | Switch | Display wallet balance info | `true`, `false` |
| **Wallet Table** | `wallet_balance_addresses_with_comments` | List | Addresses/XPUBs to watch | `[{"address": "xpub...", "type": "xpub", "comment": "Cold Storage"}]` |
| **Display Unit** | `wallet_balance_unit` | Select | Unit for balance | `sats`, `btc` |
| **Fiat Currency** | `wallet_balance_currency` | Select | Fiat value currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |

---

## BTC COUNTDOWN BLOCK

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Countdown Block** | `show_countdown_block` | Switch | Display remaining BTC supply and % mined | `true`, `false` |

---

## HALVING BLOCK

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Halving Block** | `show_halving_block` | Switch | Display next halving date and block countdown | `true`, `false` |

---

## NETWORK BLOCK

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Network Block** | `show_network_block` | Switch | Display global hashrate and mining difficulty | `true`, `false` |

---

## DONATION BLOCK

Displays the latest (or largest) Lightning donation received via a LNbits webhook. Requires a webhook URL to be configured -- either a direct connection (same network) or via a self-hosted [event-hub](https://github.com/satcat21/event-hub) relay.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Donation Block** | `show_donation_block` | Switch | Display Lightning donation block | `true`, `false` |
| **Display Mode** | `donation_display_mode` | Select | Which donation to show | `latest` (most recent), `highest` (largest ever), `auto` (latest then largest after 432 blocks) |
| **Webhook Relay URL** | `webhook_relay_ws_url` | String | WebSocket URL for Option B relay | `wss://your-host/ws/your-token` (leave empty for direct webhook) |

---

## SOFTWARE UPDATES

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Automatic Updates** | `auto_update_enabled` | Switch | Enable scheduled automatic updates | `true`, `false` (default: `false`) |
| **Update Time** | `auto_update_time` | Time | Time of day to run automatic updates | `HH:MM` format, e.g. `03:00` (default), `14:30` |
| **Update Days** | `auto_update_days` | Multi-select | Days of the week to check for updates | `["mon", "wed", "fri"]` (default). Valid: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` |

When automatic updates are enabled, mempaper checks for new releases at the configured time on the selected days. If a newer release is available, it is installed automatically and the service restarts. The restart is delayed if the e-ink display is currently refreshing to prevent display corruption.

---

## OPSEC MODE

When OPSec Mode is enabled the e-ink display shows a randomly selected cover image (e.g. a family photo) instead of Bitcoin data. The web dashboard is **not** affected and always shows normal BTC data.

Upload OPSec images via the **Meme Management** section of the config page, in the **OPSec Images** sub-section below the meme gallery.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **OPSec Mode** | `opsec_mode_enabled` | Switch | Show cover image on e-ink instead of BTC data | `true` (OPSec on), `false` (normal, default) |

---

## SECURITY AND ADMIN

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Username** | `admin_username` | String | Dashboard login username | default: `admin` |
| **Password** | `admin_password_hash` | String | *Hashed managed field* | *Managed by `setup_secure_password.py`* |
| **Public Dashboard** | `public_dashboard` | Switch | Allow unauthenticated users to view the dashboard (settings still require login) | `true`, `false` (default: `false`) |

---

## ADVANCED (FILE-ONLY)

These settings are typically managed by the system or only available in `config.json` directly.

| Config Key | Default | Description |
| :--- | :--- | :--- |
| `precache_update_interval_seconds` | `300` | How often to fetch price/Bitaxe data (seconds). Lower = fresher data but more CPU/API calls. 300s = 5 min (recommended for RPi Zero) |
| `disable_config_file_watching` | `false` | Disable automatic config reload on file change. Set to `true` for faster startup on development machines |
| `network_outage_tolerance_minutes` | `45` | Minutes to retry WebSocket reconnection during outages |
| `xpub_enable_gap_limit` | `true` | Stop scanning XPUB after N unused addresses |
| `xpub_gap_limit_last_n` | `20` | Number of consecutive empty addresses before stopping scan |
| `xpub_gap_limit_increment` | `10` | How many addresses to scan per increment step |
| `xpub_enable_bootstrap_search` | `false` | Perform a wider initial address scan to find all used addresses (slower but more thorough) |
| `xpub_bootstrap_max_addresses` | `100` | Maximum addresses to scan during bootstrap search |
| `xpub_bootstrap_increment` | `10` | Addresses per step during bootstrap search |
| `font_regular` | `static/fonts/Roboto-Regular.ttf` | Path to regular font file |
| `font_bold` | `static/fonts/Roboto-Bold.ttf` | Path to bold font file |
