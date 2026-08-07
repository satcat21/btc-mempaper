# Configuration Reference

This document provides a comprehensive list of all configuration settings available in mempaper.
These settings can be modified via the Web Dashboard (recommended) or by editing `config/config.json`.

---

## General appearance

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | `language` | Select | Interface language | `en` (English), `de` (German), `es` (Spanish), `fr` (French), `it` (Italian) |
| **Color Mode** | `color_mode_dark` | Switch | Dark theme for dashboard | `true` (Dark), `false` (Light) |
| **E-Ink Dark Mode** | `eink_dark_mode` | Switch | Invert colors for E-ink | `true` (Inverted/Night), `false` (Standard) |
| **Prioritize Large Memes** | `prioritize_large_scaled_meme` | Switch | Maximize meme size vs info blocks | `true` (Large Memes), `false` (Balanced) |

---

## Color customization

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

## Mempool integration

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Mempool Host** | `mempool_host` | String | Mempool instance hostname. A `.onion` address enables Tor automatically and switches to http on port 80, since onion names cannot resolve without a proxy and the circuit already encrypts | `mempool.space` (public), `192.168.1.50` (local), `...onion` (via Tor) |
| **Private/Self-Hosted** | `mempool_is_private` | Switch | Marks the instance as self-hosted on your local network; disables privacy warnings for wallet monitoring | `true` (private), `false` (public, default) |
| **Connect via Tor** | `mempool_use_tor` | Switch | Route mempool traffic through the local Tor daemon (installed by `install.sh`), so a `.onion` host works and the instance never sees your IP. Only mempool traffic is proxied -- Bitaxe miners stay on the LAN. **Turn this off when pointing at a self-hosted mempool on your LAN:** Tor refuses to route private addresses, so a `192.168.x.x` host fails entirely while it is on | `true` (via Tor), `false` (direct, default) |
| **Tor SOCKS Host** | `tor_socks_host` | String | Address of the Tor SOCKS proxy (Advanced) | `127.0.0.1` (default) |
| **Tor SOCKS Port** | `tor_socks_port` | Number | Port of the Tor SOCKS proxy (Advanced) | `9050` (Tor daemon, default), `9150` (Tor Browser) |
| **Use HTTPS/SSL** | `mempool_use_https` | Switch | Secure connection. Not used over Tor -- the onion circuit already encrypts and authenticates, so the setting is disabled while Tor is on | `true` (https://), `false` (http://) |
| **Verify SSL Cert** | `mempool_verify_ssl` | Switch | Validate SSL certificate. Not used over Tor, for the same reason | `true` (Verify), `false` (Skip -- for self-signed) |
| **REST Port** | `mempool_rest_port` | Number | API port. Remembered separately for clearnet and Tor -- see below | `443` (public), `80` (onion), `4081`/`3006` (local mempool, MyNode/Umbrel) |
| **WebSocket Port** | `mempool_ws_port` | Number | Real-time data port. Also remembered per transport | `443` (public), `80` (onion), `8999` (local standard) |
| **WebSocket Path** | `mempool_ws_path` | String | Websocket endpoint path | `/api/v1/ws` (default) |
| **Username** | `mempool_username` | String | Optional Basic auth username | Leave empty if not required |
| **Password** | `mempool_password` | String | Optional Basic auth password | Leave empty if not required |
| **Fee Preference** | `fee_parameter` | Select | Which fee to display | `fastestFee` (High Priority), `halfHourFee` (Standard), `hourFee` (Low Priority), `economyFee` (Economy), `minimumFee` (No Priority) |

### Ports are remembered per transport

Clearnet and Tor each keep their own ports permanently, and the **Connect via
Tor** switch decides which pair is live. Toggling Tor therefore never destroys a
custom port: switch on, and the fields change to the Tor pair; switch off, and
your previous values come back exactly as they were.

| Config Key | Default | Applies when |
| :--- | :--- | :--- |
| `mempool_use_https_clearnet` | `true` | Tor **off** |
| `mempool_rest_port_clearnet` | `443` | Tor **off** |
| `mempool_ws_port_clearnet` | `443` | Tor **off** |
| `mempool_rest_port_tor` | `80` | Tor **on** |
| `mempool_ws_port_tor` | `80` | Tor **on** |

Editing a port writes to whichever slot is active, so a value typed while Tor is
on belongs to the Tor slot and leaves the clearnet one untouched. `mempool_use_https`,
`mempool_rest_port` and `mempool_ws_port` are the *live* values projected from the
active slot — those are what the rest of the app reads.

There is no HTTPS setting for Tor. An onion address **is** the service's public
key, so the circuit already encrypts and authenticates the endpoint; TLS on top
would add handshake cost a Pi Zero can ill afford and protect nothing. Tor
traffic is always plain HTTP.

Selecting a **known onion preset** overrides the Tor slot's port, because the
service dictates its own: a port carried over from a clearnet instance would be
refused by a hidden service listening on 80.

---

## Display hardware

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **E-Ink Display Connected** | `e-ink-display-connected` | Switch | Enable hardware driver | `true` (Enable), `false` (Disable) |
| **Display Driver** | `omni_device_name` | String | Driver name (Native or Omni-EPD) | `epd13in3E` (Recommended -- Waveshare 13.3"), `epd7in3f` (Default -- Waveshare 7.3"), `inky.impression`, `inky.auto` |
| **Display Width** | `display_width` | Number | Resolution Width (pixels) -- Auto-set by device selection | Automatically determined from selected device or orientation |
| **Display Height** | `display_height` | Number | Resolution Height (pixels) -- Auto-set by device selection | Automatically determined from selected device or orientation |
> **Changing the display model is not possible from this page.** The selector shows the configured model read-only; it can download missing drivers for that model, but not switch to another. Re-run `install.sh`, or `sudo -u mempaper .venv/bin/python tools/configure_display.py`.

### Automatic disable and recovery

Three consecutive refresh failures — a wrong driver, an SPI error, a dead panel —
switch `e-ink-display-connected` off and persist it, so the device stops retrying
a display that cannot work.

**The next service restart or reboot turns it back on and tries again.** Without
that, a transient fault leaves the panel dark permanently and the only cure is
the dashboard, which is no help on a device handed to someone who never logs in.
A retry costs at most three failed refreshes before the threshold trips again, so
a genuinely dead panel does not spin.

Only an automatic disable is retried. Switching the display off yourself in
Settings clears `eink_auto_disabled`, and a reboot then leaves it off — your
choice is never overridden. The marker is also cleared the moment a refresh
succeeds.

---

## Bitcoin price block

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Price Block** | `show_btc_price_block` | Switch | Display fiat price info | `true`, `false` |
| **Currency** | `btc_price_currency` | Select | Fiat currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |
| **Moscow Time Unit** | `moscow_time_unit` | Select | Format for Sats/Fiat | `sats` (e.g. 3432 sats), `hour` (e.g. 03:42) |

---

## Bitaxe / mining stats

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Bitaxe Block** | `show_bitaxe_block` | Switch | Display mining block | `true`, `false` |
| **Bitaxe Display Mode** | `bitaxe_display_mode` | Select | What to show on right side | `blocks` (Found Blocks), `difficulty` (Best Difficulty) |
| **Miner Table** | `bitaxe_miner_table` | List | Miner IP addresses | `[{"address": "192.168.1.20", "comment": "Axe 1"}]` |
| **Block Rewards Table** | `block_reward_addresses_table` | List | Addresses to watch for coinbase | `[{"address": "bc1q...", "comment": "Solo Pool"}]` |

---

## Wallet monitoring

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Wallet Block** | `show_wallet_balances_block` | Switch | Display wallet balance info | `true`, `false` |
| **Wallet Table** | `wallet_balance_addresses_with_comments` | List | Addresses/XPUBs to watch | `[{"address": "xpub...", "type": "xpub", "comment": "Cold Storage"}]` |
| **Display Unit** | `wallet_balance_unit` | Select | Unit for balance | `sats`, `btc` |
| **Fiat Currency** | `wallet_balance_currency` | Select | Fiat value currency | `USD`, `EUR`, `GBP`, `CAD`, `CHF`, `AUD`, `JPY` |

---

## BTC countdown block

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Countdown Block** | `show_countdown_block` | Switch | Display remaining BTC supply and % mined | `true`, `false` |

---

## Halving block

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Halving Block** | `show_halving_block` | Switch | Display next halving date and block countdown | `true`, `false` |

---

## Network block

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Network Block** | `show_network_block` | Switch | Display global hashrate and mining difficulty | `true`, `false` |

---

## Donation block

Displays the latest (or largest) Lightning donation received via a LNbits webhook. Requires a webhook URL to be configured -- either a direct connection (same network) or via a self-hosted [event-hub](https://github.com/satcat21/event-hub) relay.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Show Donation Block** | `show_donation_block` | Switch | Display Lightning donation block | `true`, `false` |
| **Display Mode** | `donation_display_mode` | Select | Which donation to show | `latest` (most recent), `highest` (largest ever), `auto` (latest then largest after 432 blocks) |
| **Webhook Relay URL** | `webhook_relay_ws_url` | String | WebSocket URL for Option B relay | `wss://your-host/ws/your-token` (leave empty for direct webhook) |

---

## Software updates

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Automatic Updates** | `auto_update_enabled` | Switch | Enable scheduled automatic updates | `true`, `false` (default: `false`) |
| **Update Time** | `auto_update_time` | Time | Time of day to run automatic updates | `HH:MM` format, e.g. `03:00` (default), `14:30` |
| **Update Days** | `auto_update_days` | Multi-select | Days of the week to check for updates | `["mon", "wed", "fri"]` (default). Valid: `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun` |

When automatic updates are enabled, mempaper checks for new releases at the configured time on the selected days. If a newer release is available, it is installed automatically and the service restarts. The restart is delayed if the e-ink display is currently refreshing to prevent display corruption.

---

## Meme sync

Fetches new memes from einundzwanzig-memes.space on a weekly schedule, via a
cron entry for the `mempaper` user that mempaper writes and keeps in step with
these settings.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Weekly Meme Sync** | `meme_sync_enabled` | Switch | Enable the scheduled download | `true`, `false` (default) |
| **Sync Day** | `meme_sync_day` | Select | Day of the week, in cron numbering | `"0"` (Sun) … `"6"` (Sat), default `"4"` (Thu) |
| **Sync Hour** | `meme_sync_hour` | Select | Hour of the day, 24-hour | `"0"` … `"23"`, default `"13"` |
| **Download over Tor** | `tor_meme_downloads` | Switch | Append `--tor` so the download uses the Tor SOCKS proxy, keeping your IP off the meme host too | `true`, `false` (default) |

**`install.sh` randomises the day and hour per device** at install time and sets
`meme_sync_schedule_randomised` so it never does so again. Without that, every
mempaper in the world would inherit the same Thursday 13:00 default and hit
einundzwanzig-memes.space in the same hour. Changing the schedule in the web UI
overrides it and is never overwritten by a later install run.

> The sync script (`tools/sync_memes.py`) is currently a **placeholder** —
> the upstream API endpoint does not exist yet. A scheduled run reports what it
> would have done and exits 0, so the job shows as succeeding rather than
> failing in the cron log until the implementation lands.

---

## OPSec mode

When OPSec Mode is enabled the e-ink display shows a randomly selected cover image (e.g. a family photo) instead of Bitcoin data. The web dashboard is **not** affected and always shows normal BTC data.

Upload OPSec images via the **Meme Management** section of the config page, in the **OPSec Images** sub-section below the meme gallery.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **OPSec Mode** | `opsec_mode_enabled` | Switch | Show cover image on e-ink instead of BTC data | `true` (OPSec on), `false` (normal, default) |

---

## Security and admin

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Admin Username** | `admin_username` | String | Dashboard login username | default: `admin` |
| **Password** | `admin_password_hash` | String | *Hashed managed field* | *Managed by `setup_secure_password.py`* |
| **Public Dashboard** | `public_dashboard` | Switch | Allow unauthenticated users to view the dashboard (settings still require login) | `true`, `false` (default: `false`) |

---

## Advanced (file-only)

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
| `eink_auto_disabled` | `false` | Set when three consecutive refresh failures switch the display off, so startup knows the shutdown was automatic rather than the operator's choice. See [Display hardware](#display-hardware) |
| `web_orientation` | `vertical` | Layout used for the browser dashboard. Hidden in the web UI — the renderer reads it to decide whether to swap width and height |
| `eink_orientation` | `vertical` | Layout rendered to the panel, also used by the display worker to decide rotation. Hidden in the web UI; config stores landscape dimensions and `vertical` swaps them at render time |
