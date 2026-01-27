# Configuration Reference

This document provides a comprehensive list of all configuration settings available in Mempaper.
These settings can be modified via the Web Dashboard (recommended) or by editing `config/config.json`.

---

## 🎨 General Appearance

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | `language` | Select | Interface language | `en` (English), `de` (German), `es` (Spanish), `fr` (French) |
| **Display Orientation** | `display_orientation` | Select | Screen layout orientation | `vertical` (Portrait), `horizontal` (Landscape) |
| **Color Mode** | `color_mode_dark` | Switch | Dark theme for dashboard | `true` (Dark), `false` (Light) |
| **Prioritize Large Memes** | `prioritize_large_scaled_meme` | Switch | Maximize meme size vs info blocks | `true` (Large Memes), `false` (Balanced) |
| **Live Block Notifications** | `live_block_notifications_enabled` | Switch | Popup on new block | `true` (On), `false` (Off) |

---

## 🌩️ Mempool Integration

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Mempool Host** | `mempool_host` | String | Mempool instance hostname | `mempool.space` (public), `192.168.1.50` (local) |
| **Use HTTPS/SSL** | `mempool_use_https` | Switch | Secure connection | `true` (https://), `false` (http://) |
| **Verify SSL Cert** | `mempool_verify_ssl` | Switch | Validate SSL certificate | `true` (Verify), `false` (Skip - for self-signed) |
| **REST Port** | `mempool_rest_port` | Number | API port | `443` (public), `80`, `3006` (local MyNode/Umbrel) |
| **WebSocket Port** | `mempool_ws_port` | Number | Real-time data port | `443` (public), `8999` (local standard) |
| **WebSocket Path** | `mempool_ws_path` | String | Websocket endpoint path | `/api/v1/ws` (default) |
| **Fee Preference** | `fee_parameter` | Select | Which fee to display | `fastestFee` (High Priority), `halfHourFee` (Standard), `hourFee` (Low Priority), `minimumFee` (No Priority) |

---

## 🖥️ Display Hardware

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **E-Ink Display Connected** | `e-ink-display-connected` | Switch | Enable hardware driver | `true` (Enable), `false` (Disable) |
| **Display Driver** | `omni_device_name` | String | Driver name (Waveshare/Omni-EPD) | `waveshare_epd.epd7in3f` (Default), `inky.impression` |
| **Display Width** | `display_width` | Number | Resolution Width (px) | `800` (Default), `600`, `648` |
| **Display Height** | `display_height` | Number | Resolution Height (px) | `480` (Default), `448`, `400` |

---

## 💰 Bitcoin Price Block

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Price Block** | `show_btc_price_block` | Switch | Display fiat price info | `true`, `false` |
| **Currency** | `btc_price_currency` | Select | Fiat currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |
| **Moscow Time Unit** | `moscow_time_unit` | Select | Format for Sats/Fiat | `sats` (e.g. 3432 sats), `hour` (e.g. 03:42) |

---

## ⛏️ Bitaxe / Mining Stats

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Bitaxe Block** | `show_bitaxe_block` | Switch | Display mining block | `true`, `false` |
| **Bitaxe Display Mode** | `bitaxe_display_mode` | Select | What to show on right side | `blocks` (Found Blocks), `difficulty` (Best Difficulty) |
| **Miner Table** | `bitaxe_miner_table` | List | Miner IP addresses | `[{"address": "192.168.1.20", "comment": "Axe 1"}]` |
| **Block Rewards Table** | `block_reward_addresses_table` | List | Addresses to watch for coinbase | `[{"address": "bc1q...", "comment": "Solo Pool"}]` |

---

## 💼 Wallet Monitoring

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Wallet Block** | `show_wallet_balances_block` | Switch | Display wallet balance info | `true`, `false` |
| **Wallet Table** | `wallet_balance_addresses_with_comments` | List | Addresses/XPUBs to watch | `[{"address": "xpub...", "type": "xpub", "comment": "Cold Storage"}]` |
| **Display Unit** | `wallet_balance_unit` | Select | Unit for balance | `sats`, `btc` |
| **Fiat Currency** | `wallet_balance_currency` | Select | Fiat value currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |

---

## 🔒 Security & Admin

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Username** | `admin_username` | String | Dashboard login username | default: `admin` |
| **Password** | `admin_password_hash` | String | *Hashed managed field* | *Managed by `setup_secure_password.py`* |

---

## ⚙️ Advanced (File-Only)

These settings are typically managed by the system or only available in `config.json` directly.

| Config Key | Default | Description |
| :--- | :--- | :--- |
| `xpub_enable_gap_limit` | `true` | Stop scanning XPUB after N unused addresses |
| `xpub_gap_limit_last_n` | `20` | Number of empty addresses before stopping |
| `network_outage_tolerance_minutes` | `45` | Minutes to retry WebSocket reconnection during outages |
| `font_regular` | `static/fonts/Roboto-Regular.ttf` | Path to regular font file |
| `font_bold` | `static/fonts/Roboto-Bold.ttf` | Path to bold font file |
