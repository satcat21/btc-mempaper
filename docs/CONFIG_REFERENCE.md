# Configuration Reference

This document provides a comprehensive list of all configuration settings available in mempaper.
These settings can be modified via the Web Dashboard (recommended) or by editing `config/config.json`.

---

## General appearance

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | `language` | Select | Interface language | `en` (English), `de` (German), `es` (Spanish), `fr` (French), `it` (Italian) |
| **Number Format** | `number_format` | Select | How every figure is punctuated — block height, fee, hashrate, balances and the SSH banner all follow it. Independent of the interface language | `eu` (62.923 · 0,51, default), `us` (62,923 · 0.51) |
| **Prioritize Large Memes** | `prioritize_large_scaled_meme` | Switch | Maximize meme size vs info blocks | `true` (Large Memes), `false` (Balanced) |

---

## Theming

Everything that decides how the display and the dashboard look, in one place.
Colors that belong to a single info block stay with that block instead.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Web Theme** | `color_mode_dark` | Switch | Dark theme for dashboard | `true` (Dark), `false` (Light) |
| **E-Ink Theme** | `eink_dark_mode` | Switch | Invert colors for E-ink | `true` (Inverted/Night), `false` (Standard) |
| **Date & Block Hash Gradient** | `color_date_start_*`<br>`color_date_end_*` | Group | Gradient across the date line and the hash frame, per theme | `#1c82c0` → `#c040a8` (light) |
| **Holiday & Block Hash Gradient** | `color_holiday_start_*`<br>`color_holiday_end_*` | Group | Gradient used on Bitcoin holidays, per theme | `#D17300` → `#C62828` (light) |
| **Fee Used for the Block Height** | `fee_parameter` | Select | Which fee is printed under the block height **and** compared against the rolling median to color it. Each tier keeps its own median, so this is the scale the group below is measured in, not just a label. Pick the priority you actually transact at — see [Block height color scale](#block-height-color-scale) | `fastestFee` (High Priority), `halfHourFee` (Standard), `hourFee` (Low Priority), `economyFee` (Economy), `minimumFee` (No Priority) |
| **Block Height Color & Scale** | `color_block_height_*`<br>`fee_color_mode` | Group | The color an ordinary block reads as, plus the scale turning a fee into a color. See [Block height color scale](#block-height-color-scale) | `#545454` / `#919191`, scale `relative` |

---

## Color customization

| Web Label | Config Key | Type | Description | Default Light / Dark |
| :--- | :--- | :--- | :--- | :--- |
| **Date Gradient Start** | `color_date_start_light`<br>`color_date_start_dark` | Color | Gradient start color for the date display | `#1c82c0` / `#4FC3F7` |
| **Date Gradient End** | `color_date_end_light`<br>`color_date_end_dark` | Color | Gradient end color for the date display | `#c040a8` / `#BA68C8` |
| **Holiday Start Color** | `color_holiday_start_light`<br>`color_holiday_start_dark` | Color | Gradient start color for holiday events | `#D17300` / `#F7931A` |
| **Holiday End Color** | `color_holiday_end_light`<br>`color_holiday_end_dark` | Color | Gradient end color for holiday events | `#C62828` / `#FF6F6F` |
| **BTC Price Color** | `color_btc_price_light`<br>`color_btc_price_dark` | Color | Text color for Bitcoin price | `#147A38` / `#22C55E` |
| **Countdown Color** | `color_countdown_light`<br>`color_countdown_dark` | Color | Text color for supply countdown | `#C62828` / `#F02D2D` |
| **Halving Color** | `color_halving_light`<br>`color_halving_dark` | Color | Text color for halving countdown | `#1565C0` / `#2979FF` |
| **Network Color** | `color_network_light`<br>`color_network_dark` | Color | Text color for network stats | `#6A1B9A` / `#B23CE8` |
| **Bitaxe Color** | `color_bitaxe_stats_light`<br>`color_bitaxe_stats_dark` | Color | Text color for mining stats | `#8C6D0F` / `#FFC400` |
| **Wallet Color** | `color_wallets_light`<br>`color_wallets_dark` | Color | Text color for wallet balances | `#00838F` / `#00BCD4` |
| **Donation Color** | `color_donation_light`<br>`color_donation_dark` | Color | Text color for donation block | `#B35C00` / `#F7931A` |

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

### Block height color scale

The block height number is colored by the current fee. The **relative** scales
compare that fee against the median of the last 30 days rather
than against fixed thresholds, so "cheap" keeps meaning cheap when the whole fee
market moves.

Set the base color and pick the scale together under **Theming → Block Height
Color & Scale**. That panel previews the digits in both themes at whatever fee
you drag the slider to, with the track itself painted in the scale it selects
from, and its colors are computed from the renderer's own tables, so what you see
is what the panel draws. Which fee is measured is set by **Fee Used for the Block
Height** (`fee_parameter`) directly above it — switching tier re-scales the whole
preview, because each tier is judged against its own median. The window behind
"normal" (30 days) and the neutral band (5%) are fixed in code, not settings.

![Fee color scale](diagrams/fee-color-scale.svg)

| Mode | Behaviour |
|---|---|
| `relative` *(default)* | Your color at the median, cool below it, warm above. Blue → green → **your color** → yellow → amber → orange → red |
| `constant` | Your color, whatever the fee is doing. No baseline involved |
| `manual` | Five fixed colors at thresholds you set, in real sat/vB. Ignores the baseline entirely |

Notes that matter in practice:

- **Both ends of the gradient are fee readings** — the previous block at the top,
  the current one at the bottom — so the digits show the move, not just the level.
  The bottom end is the very figure printed beneath the height, so the color
  always belongs to the number you can read.
- **`fee_parameter` chooses which fee is measured**, and each tier is measured
  against *its own* history. `fastestFee` is compared to what `fastestFee` has
  been costing, not to what blocks cost — otherwise every reading would carry a
  constant offset set by the tier rather than by the market, and a `minimumFee`
  device would read cheap more or less permanently. *"Is next-block inclusion
  expensive right now"* and *"is a minimum-fee transaction worth broadcasting"*
  are different questions, and the color answers the one you asked.
- **Fractions of a sat/vB are read and printed.** The tiers come from mempool's
  `/v1/fees/precise`, which does not floor them at 1 sat/vB, so a quiet mempool
  shows `0.8` rather than being rounded up to `1`. Below 10 sat/vB the label
  keeps one decimal; above it, whole numbers. A mempool backend older than v2.5
  has no such endpoint and falls back to whole numbers everywhere.
- **The base color is yours, one per theme.** See below. It is what an *ordinary*
  block reads as, and defaults to a neutral grey so it does not compete with the
  fee hues on either side of it.
- **The scale is logarithmic.** Each whole step is a doubling, so 1→2 sat/vB
  occupies as much of the range as 20→40. A linear ratio axis would squash the
  entire cheap half into a sliver.
- **The floor comes from the network, not a constant.** A fee at or under the
  mempool's current `minimumFee` reads as the cheapest color whatever the ratio
  says, because nothing is waiting to be undercut. That figure is read live, so
  it follows a relay minimum of 0.1 sat/vB as readily as one of 1, and drops to
  no floor at all once the mempool has cleared entirely. It applies only while
  the median is above it: at a median of 0.5, a 1 sat/vB block is twice the
  going rate and is colored as such.
- **The median is used, not the mean.** One inscription weekend at 300 sat/vB
  would drag a mean upward for a month and make genuinely expensive blocks look
  ordinary; the median barely moves.
- **No baseline yet, no guessing.** A day needs at least 6 samples before it
  counts, and until at least one day does, `relative` falls back to the `manual`
  thresholds rather than inventing a ratio from a handful of minutes.

##### Where the baseline lives

There is no history to fetch. mempool publishes past *block* medians, but
`/v1/fees/recommended` is point-in-time — nothing reports what `fastestFee` was
last Tuesday — so the window is accumulated locally, from the readings mempaper
already polls. All five tiers are recorded on every sample, so changing
`fee_parameter` reads an already-warm window instead of starting cold.

| File | Holds |
|---|---|
| `cache/fee_tier_today.json` | Today's raw samples, flushed about hourly so a restart before midnight does not lose the day |
| `cache/fee_tier_history.json` | One median per tier per *finished* day, up to 30 |

A day closes at the local date change and is reduced to one median per tier. The
baseline is the median **of those daily medians**, so every day weighs the same
however many samples it contributed: a device booted at 20:00 cannot outvote a
full day, and one frantic hour cannot move the window. Days the device was off
are simply absent — nothing is interpolated, and the window repairs itself as new
days arrive and old ones age out.

The first flat example on the config page's block-height preview *is* the current
baseline: in `relative` mode the preview scenarios are multiples of it, and the
steady one is the baseline times 1.0. If it reads `20`, there is no baseline yet.

> Older builds kept a single `cache/fee_history.json` — a median of mined-block
> medians, shared by every tier. It is no longer read or written, and can be
> deleted.

#### The base color

`color_block_height_light` and `color_block_height_dark` set the color an
**ordinary** block reads as — one within 5% of the median,
which has nothing to report. Each end of the gradient falls back to it
independently, so it can appear at the top, the bottom, or both.

Both ends are fee readings: the previous block at the top, the current one at the
bottom. Tone follows the theme, so the bottom — where the fee label sits — is
always the readable end:

| Theme | Top (last block) | Bottom (this block) |
|---|---|---|
| Dark | full value | 45% toward white |
| Light | 45% toward white | 15% toward black |

A substituted end takes the tone of the end it lands on, except where that end is
the theme's anchor — the top on dark, the bottom on light — where the picked color
is drawn exactly, so the color picker always shows something that appears on screen.

Worked example against a 20 sat/vB median. These are the values the renderer
actually emits for a web image:

| Move | Reads as | Light theme (`#3C3C46`) | Dark theme (`#C8C8D2`) |
|---|---|---|---|
| 20 → 20 | ordinary, both blocks | `#939399` → `#3C3C46` | `#C8C8D2` → `#E0E0E6` |
| 8 → 8 | cheap, and staying cheap | `#72BEED` → `#0074BE` | `#0089E0` → `#72BEED` |
| 8 → 40 | just spiked | `#72BEED` → `#D14B05` | `#0089E0` → `#FAA376` |
| 40 → 8 | just crashed | `#FAA376` → `#0074BE` | `#F75907` → `#72BEED` |
| 40 → 40 | dear, and staying dear | `#FAA376` → `#D14B05` | `#F75907` → `#FAA376` |

The fee ends are deliberately softened from the raw scale — deepened on a light
theme, lightened on a dark one — so a dashboard full of color stays legible
instead of shouting. Any hex works for the base color; a neutral grey is only the
default because "nothing to report" should not draw the eye.

The ramp spans the digits themselves — the cap top to the baseline — so half the
glyph height is an even blend of the two, and both ends are drawn at full strength.
Mapping it onto the text layout box instead would waste the ends of the ramp on the
descender space digits never occupy, leaving the top 17% pre-blended and the bottom
26% short.

e-ink gets the same colors as the web image. The panel's own driver dithers them
onto the six or seven inks it has, which is what produces the intermediate and
lighter tones the gradient needs — a steady dear fee prints as roughly half red,
a quarter yellow and a fifth white, reading as a warm gradient rather than a slab
of one ink.

Both ends used to snap to a printable ink outright, to keep thin digits from
speckling. That cost more than it saved: two fees an hour apart landed on the same
ink, so the gradient printed flat, and a cheap fee took the panel's blue at 2.4:1
against a black background, leaving the fee under the number barely readable. The
worst case is now 6.4:1 on a dark panel.

One weak spot remains on a light panel: a fee around 1.3x the median deepens to an
amber that measures 2.5:1 on white. Yellow is simply hard to read on white — the
same is true of the web image on a light theme.

#### Custom thresholds for `absolute`

`fee_color_stops` (file-only) replaces the built-in table:

```json
"fee_color_stops": [[0, "#00d250"], [10, "#82d20a"], [30, "#ffa000"], [120, "#e61414"]]
```

Pairs of `[sat/vB, "#rrggbb"]`, interpolated in between. A malformed list falls
back to the built-in table whole rather than partially, so a typo cannot leave
you with a half-custom scale.

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
| **Display Width** | `display_width` | Number | Resolution Width (pixels) -- Auto-set by device selection | Automatically determined from the selected device. Held landscape-native; the canvas is always rendered portrait |
| **Display Height** | `display_height` | Number | Resolution Height (pixels) -- Auto-set by device selection | Automatically determined from the selected device. Held landscape-native; the canvas is always rendered portrait |
> **Changing the display model is not possible from this page.** The selector shows the configured model read-only; it can download missing drivers for that model, but not switch to another. Run `sudo -u mempaper .venv/bin/python tools/configure_display.py` on the Pi — it updates the model, downloads the matching drivers and sets the resolution. Re-running `install.sh` also works; it calls the same script.

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
| **Automatic download** | `meme_sync_enabled` | Switch | Enable the weekly scheduled download | `true`, `false` (default) |
| **Route via Tor** | `tor_meme_downloads` | Switch | Append `--tor` so the download uses the Tor SOCKS proxy, keeping your IP off the meme host | `true` (default), `false` |

These two switches and a **Sync now** button sit on one line under
**Meme Management → Advanced**, below the meme grid — not in a section of their
own. Tor is on by default: the download otherwise tells the meme host which IP
runs a mempaper and when it syncs, and a weekly unattended job is exactly the
case where a slower transport costs least.

`meme_sync_day`, `meme_sync_hour` and `meme_sync_minute` have **no form
control**. They are shown as read-only text beside the switches, because "is
this scheduled, and when" is worth answering while editing them by hand is not:
the installer randomises them per device for a reason (below), and a control
over them is an invitation to undo it. `validate_config` carries all three
across a save, along with `meme_sync_schedule_randomised`.

**`install.sh` randomises the day, hour and minute per device** at install time
and sets `meme_sync_schedule_randomised` so it never does so again. Without
that, every mempaper in the world would inherit the same Thursday 13:00 default
and hit einundzwanzig-memes.space in the same hour. The minute
(`meme_sync_minute`) is randomised separately and has no web UI field — with the
hour spread but the minute fixed at `0`, every device sharing an hour still
fired on the stroke of it. Changing the schedule in the web UI overrides the day
and hour and is never overwritten by a later install run.

The cron entry itself is written by `utils/meme_sync_cron.py`, which both
`install.sh` and the app call so the line has exactly one definition. **The
installer writes the entry even when the feature is disabled**, commented out,
so `crontab -l` shows the schedule the device would use rather than nothing at
all. Enabling the toggle in the web UI rewrites the block live — there is no
need to uncomment it by hand, and edits made that way are overwritten on the
next config change.

Any hand-written cron line invoking `tools/sync_memes.py` or
`tools/download_all_memes.py` is removed when the block is written. Entries
predating this module carry no marker comment, so without that sweep a device
would end up running two downloaders against the same directory.

> **The sync script (`tools/sync_memes.py`) is currently a placeholder** and
> downloads nothing. It accepts the full command line, prints why there is
> nothing to report and exits 0, so a scheduled run shows as succeeding rather
> than failing. The downloader it will eventually call is not part of this
> repository, so everything around it — the schedule, the cron entry, the web
> button — is deployed and working ahead of the implementation. When that lands,
> no crontab needs rewriting: the entry already invokes this file with the
> arguments the real version will take. `tor_meme_downloads` is likewise
> accepted and recorded now, and takes effect then.

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

### Network-bound encryption (Tang)

Found under **Settings → General → Advanced**. Seals wallet addresses, balance
caches, the donation history and the rendered images with a key held on a Tang
server on your LAN, so a stolen device cannot decrypt them — carried off the
network there is nothing to guess. Requires the `clevis` package, which
`install.sh` installs whether or not you use this.

| Web Label | Config Key | Type | Description | Allowed Values / Examples |
| :--- | :--- | :--- | :--- | :--- |
| **Network-Bound Encryption (Tang)** | `tang_enabled` | Switch | Seal sensitive data against a Tang server. If the server is unreachable the device still boots, the affected blocks are disabled, and they restore themselves when it returns | `true`, `false` (default: `false`) |
| **Tang Server URL** | `tang_url` | String | Address of the Tang server on your LAN. Never expose it to the internet — reachability *is* the access control | `http://192.168.1.50:7500` |
| **Tang Key Thumbprint** | `tang_thumbprint` | String | Signing-key thumbprint, from `tang-show-keys`. Pinning it stops anything else on the LAN impersonating the server. Empty means trust-on-first-use | `faYWs5gMZ4MOKVmw_70zIvgZuzPd6AZnrsF86OgewnI` |
| **Check Tang Connection** | *(button)* | Action | Tests the whole path against the values in the form: reaches the server, reads its signing key, then seals and unseals a throwaway key. Writes nothing | — |

> **Enable this before entering wallet addresses.** Deleted data lingers in freed
> flash blocks, so sealing later cannot reach xpubs already written to the card in
> clear text. See
> [Self-Hosting Guide → Tang](SELF_HOSTING_GUIDE.md#part-8--tang-network-bound-encryption-for-wallet-data-optional).

> **Turning it off needs the server.** Disabling rewrites every sealed file in the
> clear, which requires the key. If the Tang server is gone for good the web UI
> offers to discard the sealed data instead — permanently, after confirmation
> listing exactly what is lost.

What gets sealed when `tang_enabled` is on:

| File | Contents |
| :--- | :--- |
| `config/config.sensitive.json` | Wallet addresses and xpubs |
| `cache/cache.sensitive.json` | Balance and block-reward caches |
| `cache/async_wallet_address_cache.sensitive.json` | Derived wallet addresses |
| `cache/donations.json` | Lightning donation history |
| `cache/current.png`, `cache/current.webp` | Rendered dashboard image |
| `cache/current_eink.png` | Rendered e-ink image |

`config/tang_key.jwe` holds the sealed data key (mode `0600`). It is useless
without the Tang server. **Back up the server's key store** — `/var/lib/tang` on
Debian 13, `/var/db/tang` on Debian 12 — because losing it makes every sealed
device unrecoverable.

Not covered by Tang: `admin_password_hash`, `admin_users`, `secret_key` and
`mempool_password` stay readable so the device can boot and be logged into while
the server is unreachable. The password hashes are Argon2id and safe to store
openly; the other two are secrets, and that trade is deliberate.

---

## Advanced (file-only)

These settings are typically managed by the system or only available in `config.json` directly.

Editing them by hand is the normal way to use them: **stop the service first**
(`sudo systemctl stop mempaper`), edit `config/config.json`, start it again.
Saving anything in the web UI rewrites the whole file from memory, so an edit
made while the service is running can be overwritten without warning.

| Config Key | Type | Default | Accepted values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `precache_update_interval_seconds` | Number | `300` | Any number of seconds above `0` | How often the background loop refreshes price, Bitaxe, network and fee data. Lower = fresher data but more CPU and API calls. 300s is tuned for a Pi Zero |
| `precache_render_max_age_seconds` | Number | `120` | Any number of seconds above `0`; keep below the update interval | How stale cached price, Bitaxe or network data may be when an image is rendered before it is fetched again. Below the update interval on purpose: a current image is worth more than a saved request |
| `precache_fee_max_age_seconds` | Number | `90` | Any number of seconds above `0` | Same, for fees. Shorter because fees move fastest |
| `bitaxe_offline_retry_seconds` | Number | `30` | Any number of seconds above `0` | When every configured miner reports offline, retry after this instead of the full interval — that reading is often just the LAN not being up yet after a reboot |
| `cache_metadata_write_interval_seconds` | Number | `300` | Any number of seconds above `0` — `0` does **not** mean "always", it falls back to the default | Debounce for cache-metadata writes, limiting SD card wear |
| `disable_config_file_watching` | Boolean | `false` | `true`, `false` | Disable automatic config reload on file change. Set to `true` for faster startup on development machines |
| `network_outage_tolerance_minutes` | Number | `45` | `5`–`10080` minutes | Minutes to retry WebSocket reconnection during outages. Read by the backup tool's WebSocket client, not by the block monitor, which retries with its own backoff for as long as it runs |
| `tor_auto_restart` | Boolean | `false` | `true`, `false` | Last rung of the Tor recovery ladder: after ~35 minutes in which nothing has reached the mempool host over Tor, let mempaper restart the tor service. Needs a sudoers rule that `install.sh` does not write — mempaper logs the exact line when the rung is first reached. The two cheaper rungs (rotating the SOCKS circuit, then `SIGNAL NEWNYM`) need no configuration and run regardless |
| `xpub_enable_gap_limit` | Boolean | `true` | `true`, `false` | Stop scanning XPUB after N unused addresses |
| `xpub_gap_limit_last_n` | Number | `20` | `5`–`100` addresses | Number of consecutive empty addresses before stopping scan |
| `xpub_gap_limit_increment` | Number | `10` | `1`–`50` addresses | How many addresses to scan per increment step |
| `xpub_enable_bootstrap_search` | Boolean | `false` | `true`, `false` | Perform a wider initial address scan to find all used addresses (slower but more thorough) |
| `xpub_bootstrap_max_addresses` | Number | `100` | `20`–`1000` addresses | Maximum addresses to scan during bootstrap search |
| `xpub_bootstrap_increment` | Number | `10` | `1`–`50` addresses | Addresses per step during bootstrap search |
| `font_regular` | String | `static/fonts/Roboto-Regular.ttf` | Path to a `.ttf`, relative to the app directory or absolute | Path to regular font file |
| `font_bold` | String | `static/fonts/Roboto-Bold.ttf` | Path to a `.ttf`, relative to the app directory or absolute | Path to bold font file |
| `eink_auto_disabled` | Boolean | `false` | `true`, `false` — written by the app, not normally set by hand | Set when three consecutive refresh failures switch the display off, so startup knows the shutdown was automatic rather than the operator's choice. See [Display hardware](#display-hardware) |
| `meme_sync_schedule_randomised` | Boolean | *(set by `install.sh`)* | `true`, `false` | Marks that the installer has already picked a random day and hour for this device, so a later install run leaves your schedule alone. See [Meme sync](#meme-sync) |

A value outside its accepted range is **discarded, not clamped**: the range-checked
keys are dropped by validation and the timing keys fall back inside the pre-cache
loop. Either way the shipped default applies and nothing warns you, so confirm a
hand-edited setting took effect rather than assuming it did.
