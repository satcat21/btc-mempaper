<p align="center">
  <picture>
    <img src="images/readme/header.jpg" alt="mempaper - Bitcoin Meme Block Clock" width="100%"/>
  </picture>
</p>

<h1 align="center">mempaper</h1>

<p align="center">
  <strong>A Bitcoin block clock for E-Ink displays.</strong><br/>
  Real-time network data, miner stats, and curated memes from the <a href="https://einundzwanzig.space/">Einundzwanzig community</a> in one framed screen.
</p>

<p align="center">
  <a href="#what-is-this">What is this?</a> &nbsp;&bull;&nbsp;
  <a href="#technical-stuff">Technical Stuff</a> &nbsp;&bull;&nbsp;
  <a href="#gallery">Gallery</a> &nbsp;&bull;&nbsp;
  <a href="#getting-started">Getting Started</a> &nbsp;&bull;&nbsp;
  <a href="#configuration">Configuration</a> &nbsp;&bull;&nbsp;
  <a href="#maintenance">Maintenance</a> &nbsp;&bull;&nbsp;
  <a href="docs/ARCHITECTURE.md">Architecture</a> &nbsp;&bull;&nbsp;
  <a href="#documentation">Documentation</a> &nbsp;&bull;&nbsp;
  <a href="#support-the-project">Support</a>
</p>

---

<br/>

## WHAT IS THIS?

**mempaper** is a Bitcoin block clock on E-Ink - but with style! Instead of boring blockchain monitoring, it shows the best Bitcoin memes from the Einundzwanzig community alongside real-time network data, miner stats, and wallet balances.

It connects to your local (or public) mempool instance to visualize the Bitcoin network status, mine data from your Bitaxe, and display Bitcoin memes on a beautiful e-Paper display mounted in a picture frame.

<br/>

---

<br/>

## EINUNDZWANZIG MEMES - THE SOURCE OF FUN

The memes on this display come from **[einundzwanzig-memes.space](https://einundzwanzig-memes.space)** - a community project collecting the best Bitcoin memes from the German-speaking Bitcoin scene, and a big shoutout and thank you to them for building and maintaining this awesome project. The broader **[Einundzwanzig community](https://einundzwanzig.space/)** is a major inspiration.

**Disclaimer:** This mempaper app is an independent project and has no connection or affiliation with the Einundzwanzig association.

<br/>

---

<br/>

## TECHNICAL STUFF

<table>
  <tr>
    <td width="50%">
      <strong>DISPLAY</strong><br/>
      7.3" Waveshare E-Ink (7-color)<br/>
      13.3" Waveshare E-Ink Spectra 6
    </td>
    <td width="50%">
      <strong>RESOLUTION</strong><br/>
      800x480 px (7.3")<br/>
      1600x1200 px (13.3")
    </td>
  </tr>
  <tr>
    <td>
      <strong>HARDWARE</strong><br/>
      Raspberry Pi Zero 1 WH / 2 WH
    </td>
    <td>
      <strong>SOFTWARE</strong><br/>
      Python backend (Flask + Jinja2, Flask-SocketIO, Gunicorn/gevent, Pillow/numpy)<br/>
      Web frontend (Vanilla JS + Socket.IO)<br/>
    </td>
  </tr>
  <tr>
    <td>
      <strong>POWER USAGE</strong><br/>
      ~1 Watt
    </td>
    <td>
      <strong>DATA SOURCE</strong><br/>
      mempool.space API — public or<br/>
      self-hosted mempool on your own node
    </td>
  </tr>
</table>

### Features

- **Real-time Data** - BTC price, halving countdown, network hashrate, difficulty, fees, and remaining supply via mempool.space or self-hosted mempool instance
- **Hardware Support** - Ready for Raspberry Pi (Zero/3/4/5) and Waveshare e-Paper displays (7.3" 7-color, 13.3" 6-color)
- **Web Dashboard** - Responsive interface for configuration, monitoring, and live block notifications
- **Miner Integration** - Monitor Bitaxe miner stats, aggregate hashrate, best difficulty, and found blocks
- **Wallet Monitoring** - Track on-chain balances for addresses, XPUBs, and ZPUBs with automatic address derivation
- **Block Reward Monitoring** - Track mining pool payouts and solo mining rewards for specific addresses
- **Lightning Donations** - Display incoming Lightning tips via LNbits webhook relay
- **Meme Rotation** - Curated Bitcoin memes from the Einundzwanzig community, with custom upload support
- **OPSec Mode** - One-click toggle to show a random cover image on the e-ink display instead of Bitcoin data
- **Privacy Controls** - Public mempool warnings, wallet cache wipe, User-Agent stripping
- **Security** - Argon2id password hashing, rate limiting, encrypted configuration, and basic auth for mempool
- **Auto Updates** - Scheduled software and system updates from the web UI
- **Multi-language** - English, German, Spanish, French, and Italian
- **WiFi Onboarding** - Hotspot-based setup flow for shipped devices, no SSH required

<br/>

---

<br/>

## GALLERY

### Hardware Setup

**Waveshare 7.3" e-Paper (7-color)**

<table>
  <tr>
    <td width="50%">
      <img src="images/hardware/mempaper-display-darkmode.jpg" alt="7.3 inch Display Dark Mode" width="100%"/>
      <p align="center"><em>7.3" E-Paper Display - Dark Mode</em></p>
    </td>
    <td width="50%">
      <img src="images/hardware/mempaper-display-lightmode.jpg" alt="7.3 inch Display Light Mode" width="100%"/>
      <p align="center"><em>7.3" E-Paper Display - Light Mode</em></p>
    </td>
  </tr>
</table>

**Waveshare 13.3" e-Paper (6-color)**

<table>
  <tr>
    <td width="50%">
      <img src="images/hardware/mempaper-13inch-darkmode.jpg" alt="13.3 inch Display Dark Mode" width="100%"/>
      <p align="center"><em>13.3" E-Paper Display - Dark Mode</em></p>
    </td>
    <td width="50%">
      <img src="images/hardware/mempaper-13inch-lightmode.jpg" alt="13.3 inch Display Light Mode" width="100%"/>
      <p align="center"><em>13.3" E-Paper Display - Light Mode</em></p>
    </td>
  </tr>
</table>

### Web Interface

<table>
  <tr>
    <td width="50%">
      <img src="images/screenshots/login-screen.png" alt="Login Screen" width="100%"/>
      <p align="center"><em>Secure login with Argon2id encryption</em></p>
    </td>
    <td width="50%">
      <img src="images/screenshots/dashboard-dark.png" alt="Dashboard Dark Mode" width="100%"/>
      <p align="center"><em>Dashboard - Dark Mode</em></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="images/screenshots/dashboard-light.png" alt="Dashboard Light Mode" width="100%"/>
      <p align="center"><em>Dashboard - Light Mode</em></p>
    </td>
    <td width="50%">
      <img src="images/screenshots/settings-page.png" alt="Settings Page" width="100%"/>
      <p align="center"><em>Configuration Settings</em></p>
    </td>
  </tr>
</table>

<details>
<summary><b>System Logs</b> (Click to expand)</summary>

<p align="center">
  <img src="images/screenshots/log-output.png" alt="System Logs" width="800"/>
  <br/>
  <em>Real-time system logs showing WebSocket connections and block updates</em>
</p>

</details>

### SSH Login Banner

<p align="center">
  <img src="images/screenshots/ssh-banner.png" alt="SSH Login Banner" width="700"/>
  <br/>
  <em>Live system stats on every SSH login — block height, mempool status, memes count, service uptime, and display info.</em>
</p>

<br/>

---

<br/>

## GETTING STARTED

**Three ways in — pick the one that describes you:**

| You are… | Go to |
|---|---|
| Setting up a **mempaper someone gave you** | [First-Time Setup](#first-time-setup-delivered-device) — power on, join the hotspot, connect your Wi-Fi. No SSH, no terminal. |
| **Building one yourself** from parts | [Build Your Own](#build-your-own) — shopping list, one-line installer, display wiring |
| Running a mempaper **already** | [Maintenance](#maintenance) — updates, SSH access, admin accounts |

Handing a device to someone else? See [Preparing a Device for Someone Else](#preparing-a-device-for-someone-else).

<br/>

---

### First-Time Setup (Delivered Device)

This is the flow for a device that arrives with **no Wi-Fi configured** — one prepared for shipping, or a freshly flashed card. It walks you through Wi-Fi and creating your admin account entirely from your phone; no SSH or technical knowledge is required.

> If you just ran the installer yourself, you do **not** need this. Your Pi is already on Wi-Fi and running — go straight to [Configuration](#configuration).

#### Step 1 -- Delivery State (E-Ink)

The device ships with the delivery-state image on the e-ink display.

<p align="center"><img src="images/readme/onboarding_1_delivery_state.png" alt="Delivery state e-ink screen" width="600"/></p>

#### Step 2 -- Setup Hotspot (E-Ink)

On first boot the device detects that no Wi-Fi is configured and starts an open setup hotspot. **This takes between 90 seconds and 2 minutes 21 seconds** — the Pi has to boot, initialise the Wi-Fi radio, and switch to AP mode. Once ready, the e-ink display refreshes and shows the hotspot name and a QR code.

- **SSID:** `mempaper-XXXX` (4-digit suffix derived from the device MAC)
- **Security:** Open access point — there is no Wi-Fi password. A portal password shown on the e-ink display gates the setup page itself.
- Scan the QR code with your phone to connect automatically

> **Tip:** Wait for the display to change from the delivery-state image to the hotspot screen before trying to connect. If nothing has changed after 2 minutes, the hotspot failed to start — power-cycle the device and try again.

<p align="center"><img src="images/readme/onboarding_2_hotspot.png" alt="Hotspot onboarding e-ink screen" width="600"/></p>

#### Step 3 -- Wi-Fi Setup Page

Once connected to the hotspot, open `http://10.42.0.1:5000/setup` — the QR code on the right of the e-ink screen goes to the same address. The page asks you to:

1. **Select a language** (English, German, Spanish, French, Italian)
2. **Choose your home Wi-Fi** from the scanned list, or enter a hidden SSID
3. **Enter the Wi-Fi password**
4. **Create an admin account** — username and password for the dashboard

<p align="center"><img src="images/readme/onboarding_3_wifi_setup.png" alt="WiFi setup web page" width="400"/></p>

#### Step 4 -- Connected (E-Ink)

Once the device joins your home Wi-Fi, the display shows a success screen telling you how to reach the dashboard from your network.

<p align="center"><img src="images/readme/onboarding_4_connected.png" alt="WiFi connected e-ink screen" width="600"/></p>

After 60 seconds the display switches to normal operation and renders its first dashboard image. From here, see [Configuration](#configuration).

#### Resetting a Device

Forgotten admin password, or you want to start fresh? There are two ways.

##### Option A -- Reset button on the setup page

If the device is already in hotspot/setup mode (for example its stored Wi-Fi is unavailable), the setup page has a **Reset Device** button at the bottom. It clears:

- All admin accounts
- Wallet addresses and monitoring data
- Bitaxe miner configuration
- Donation history and webhook URLs
- Mempool authentication

The device stays in setup mode so you can reconfigure Wi-Fi and create a new admin account.

##### Option B -- Power-cycle factory reset

For a full reset **including saved Wi-Fi profiles**, power-cycle the device three times:

1. **Power on** and wait for the e-ink display to refresh — on a Pi Zero this can take up to about **3 minutes 30 seconds**. Only then power off.
2. **Repeat twice more.** On the third boot the reset triggers automatically; nothing else to press.

The device recognises 3 boot timestamps inside a 15-minute window and then clears all user data (as in Option A), deletes every saved Wi-Fi profile, renders the delivery-state image, and restarts the setup hotspot.

> **Important:** Wait for the e-ink refresh each time before cutting power. That refresh is the device's own confirmation that it finished booting, recorded the timestamp, and flushed writes to the SD card — pulling power earlier risks corrupting the filesystem. Three cycles of ~3:30 still fit comfortably inside the 15-minute window.

<br/>

---

### Build Your Own

#### Shopping List

Everything needed to build a mempaper from scratch.

> **Note:** Prices are approximate and vary by region and vendor. The Raspberry Pi Zero 2 W is recommended over the original Zero W for better performance.

**Shared components (~63 EUR)** — the same whichever display you choose:

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Raspberry Pi Zero 1 WH / 2 WH** | Main controller (512MB RAM, WiFi/BT) | ~21 EUR | [Zero 1 WH](https://www.berrybase.de/raspberry-pi-zero-wh) \| [Zero 2 WH](https://www.berrybase.de/raspberry-pi-zero-2-wh) |
| **MicroSD Card** | 32GB or larger, Class 10 recommended | ~13 EUR | [SanDisk Extreme 64GB](https://www.amazon.de/dp/B09X7CXWQQ) |
| **USB-C Power Supply** | 5V/2.5A minimum | ~10 EUR | |
| **USB-C to Micro-USB Adapter** | 2-pack adapter for power routing | ~4 EUR | [Amazon](https://www.amazon.de/dp/B0B7RMFMN4) |
| **90 deg USB-C Panel Mount Cable** | Right-angle extension for clean cable routing | ~15 EUR | [Amazon](https://www.amazon.de/dp/B0BQGBWVWM) |

> **Cable Routing:** The USB-C to Micro-USB adapter and 90 deg panel mount cable allow you to cleanly route power from the Raspberry Pi to the back of the picture frame for a professional finish.

**Option A -- Waveshare 7.3" e-Paper (7-color) -- total ~215 EUR**

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Waveshare 7.3" e-Paper (F)** | 7-color e-ink display (800x480) | ~88 EUR | [Waveshare](https://www.waveshare.com/7.3inch-e-paper-hat-f.htm) \| [Amazon](https://www.amazon.de/dp/B0C3R7Q75T) |
| **Photo Frame** | 18x24cm frame for display mounting | ~47 EUR | [allesrahmen.de](https://www.allesrahmen.de/bilderrahmen-ystad-aus-massivholz-mit-distanzleiste-18x24-cmweiss-gemasert27-2043000.html) |
| **Passepartout (Mat Board)** | 180x240mm outer, 94x158mm opening | ~17 EUR | [wandstyle.com](https://www.wandstyle.com/passepartout-bianco-naturale-30-x-40-cm/psta-254-030-040p-p1) |

> **Passepartout Dimensions:** The 7.3" display has a visible area of 160x96mm. The passepartout opening is 158x94mm (2mm smaller on each side) to hold the display securely in place.

**Option B -- Waveshare 13.3" e-Paper (6-color) -- total ~518 EUR**

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Waveshare 13.3" e-Paper (E)** | 6-color Spectra 6 e-ink display (1200x1600) | ~362 EUR | [Waveshare](https://www.waveshare.com/13.3inch-e-paper-hat-plus-e.htm) \| [Amazon](https://www.amazon.de/Waveshare-13-3inch-HAT-1600x1200-Communication/dp/B0DPBW2R25) |
| **Photo Frame** | 28x35cm frame for display mounting | ~76 EUR | [allesrahmen.de](https://www.allesrahmen.de/bilderrahmen-ystad-aus-massivholz-mit-distanzleiste-28x35-cmweiss-gemasert27-1001000.html) |
| **Passepartout (Mat Board)** | 280x350mm outer, 200x268mm opening | ~17 EUR | [wandstyle.com](https://www.wandstyle.com/passepartout-bianco-naturale-30-x-40-cm/psta-254-030-040p-p1) |

<details>
<summary><b>Assembly Photos</b> (Click to expand)</summary>

<p align="center">
  <img src="images/hardware/assembly-1-components.jpg" alt="Components" width="400"/>
  <br/>
  <em>All components ready for assembly</em>
</p>

<p align="center">
  <img src="images/hardware/assembly-2-wiring.jpg" alt="Wiring" width="400"/>
  <br/>
  <em>Raspberry Pi Zero W connected to e-Paper display via SPI Control interface</em>
</p>

<p align="center">
  <img src="images/hardware/assembly-3-mounting.jpg" alt="Mounting" width="400"/>
  <br/>
  <em>Mounting display in photo frame</em>
</p>

<p align="center">
  <img src="images/hardware/assembly-4-back.jpg" alt="Complete Setup" width="400"/>
  <br/>
  <em>Photo frame back with USB-C power connector</em>
</p>

</details>

#### Installation

Flash **Raspberry Pi OS Lite 32-bit** (Trixie recommended), connect the Pi to your Wi-Fi, then paste this single command:

```bash
sudo apt install -y git \
&& git clone https://github.com/satcat21/btc-mempaper.git \
&& cd btc-mempaper && bash install.sh
```

Run it as your normal user (e.g. `pi`) — **not** as root; the script uses `sudo` where it needs to. It asks every configuration question upfront (display type, admin account, Tor, optional security features), then installs without further interruption.

> **Allow 10–20 minutes on a Pi Zero 1 WH.** On ARMv6 the installer compiles **gevent** and **Pillow** from source, because no prebuilt wheels exist for that CPU.

When the installer finishes, the device goes **straight into normal operation** — it is already on your Wi-Fi, so there is no onboarding step. Open `http://<pi-ip>:5000` and log in with the admin account you just created.

<details>
<summary><b>What the installer does</b> (click to expand)</summary>

- Creates the `mempaper` service account
- Installs all system and Python packages
- Rebuilds gevent and Pillow from source on ARMv6 (Pi Zero 1 WH) where the piwheels build is incompatible
- Copies the example config (skipped if `config/config.json` already exists)
- Configures the e-ink display (interactive prompt)
- Generates and installs the `mempaper.service` systemd unit
- Sets up Wi-Fi hotspot permissions
- Disables UFW and `nftables` — their default chains drop the DHCP broadcasts the setup hotspot depends on
- Optionally configures fail2ban
- Starts the service

**Supported OS:** Raspberry Pi OS Lite **32-bit**, either **Bookworm (Debian 12)** or **Trixie (Debian 13)**. Prefer Trixie — it receives OS security updates for longer.

</details>

**Verify it came up:**
```bash
sudo systemctl status mempaper.service
sudo journalctl -u mempaper.service -f
```

<details>
<summary><b>PC / Windows</b> — development only, no e-ink display</summary>

```powershell
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

</details>

> **Display wiring and SPI are handled by the installer.** It enables SPI, downloads the
> Waveshare driver for the model you picked, and disables Wi-Fi power saving on the Pi Zero W.
> **Changing display later** is not possible from the web UI — the Settings page shows
> the configured model read-only. Re-run `install.sh`, or run the display tool directly:
> ```bash
> cd /home/mempaper/btc-mempaper
> sudo -u mempaper .venv/bin/python tools/configure_display.py
> ```

> Prefer to do it by hand, or need to understand what the script touches?
> [Manual Installation](docs/MANUAL_INSTALL.md) lists every command `install.sh` runs.

### Preparing a Device for Someone Else

Only needed if you are handing a mempaper to somebody who should set it up themselves. This resets the device and leaves it in the delivery state:

```bash
cd /home/mempaper/btc-mempaper
sudo -u mempaper .venv/bin/python tools/delivery_state.py
```

What this does:
- renders a clean delivery image on e-ink
- leaves startup behavior in integrated mode (`mempaper.service` only)
- clears setup-mode state so the next boot starts clean

**What the recipient then experiences** is the [First-Time Setup](#first-time-setup-delivered-device) flow above — worth reading once, since it is what you are handing over:

- `mempaper.service` starts on boot and first attempts a normal Wi-Fi connection
- Finding none after the startup grace period, it brings up the `mempaper-XXXX` setup hotspot
- The recipient connects, opens `http://10.42.0.1:5000`, and enters their Wi-Fi credentials
- On success the hotspot shuts down and normal operation resumes automatically

---

<br/>

## CONFIGURATION

Navigate to **Settings** in the web interface at `http://<pi-ip>:5000`.

- **Mempool Connection** -- Default is `mempool.space`. Change IP/Port to use a local node or self-hosted mempool instance.
- **Display** -- Toggle "E-Ink Display Connected" to ON.
- **Bitaxe** -- Add miner IPs to monitor hashrate.

For advanced manual configuration, edit `config/config.json`.

### Protecting Wallet Data Against Device Theft

Wallet addresses and xpubs are stored encrypted, but the key is derived from the Pi
itself — so anyone holding the hardware can recompute it. That defends a copied SD image
and **does not defend against physical theft**. It is deliberately not advertised as
more than that.

If a stolen device must not give up your addresses and balances, run a
[Tang](https://github.com/latchset/tang) server on your LAN — a node, a NAS, or a small
Proxmox LXC. mempaper then seals its wallet data with a random 256-bit key held off the
device, so carried off your network it cannot be decrypted at all. Tang needs very
little: **3.7 MiB RAM idle** and a 12 KB key store.

If the Tang host is unreachable, mempaper still starts and runs — the wallet and donation
blocks are disabled until it returns, then restore themselves automatically.

Setup, `docker-compose.yml`, LXC sizing and the limits of this approach:
[Self-Hosting Guide → Tang](docs/SELF_HOSTING_GUIDE.md#part-8--tang-network-bound-encryption-for-wallet-data-optional).

### Info Blocks

The dashboard image is composed of a meme and a set of optional info blocks displayed alongside it. Each block can be independently enabled or disabled in Settings. If more blocks are enabled than fit the available space, a random subset is shown each refresh.

| Block | Config key | What it shows |
|-------|-----------|---------------|
| **BTC Price** | `show_btc_price_block` | Current price in fiat and Moscow Time (sats/fiat) |
| **Countdown** | `show_countdown_block` | Remaining BTC supply and percentage mined |
| **Halving** | `show_halving_block` | Estimated next halving date and blocks remaining |
| **Network** | `show_network_block` | Global hashrate and mining difficulty |
| **Bitaxe** | `show_bitaxe_block` | Aggregate hashrate and found blocks or best difficulty |
| **Wallet Balances** | `show_wallet_balances_block` | On-chain balances for addresses / XPUBs / ZPUBs |
| **Lightning Donation** | `show_donation_block` | Latest Lightning donation via LNbits webhook |

> All blocks are **on** by default except Bitaxe, Wallet Balances, and Donation, which require additional setup.

See [Configuration Reference](docs/CONFIG_REFERENCE.md) for every setting in detail.

<br/>

---

<br/>

## MAINTENANCE

Everything for running a mempaper day to day, whether you built it, were given it, or look after several.

**Service control** — over SSH:

```bash
sudo systemctl status mempaper.service       # is it running?
sudo journalctl -u mempaper.service -f       # live logs
sudo systemctl restart mempaper.service      # restart after manual config edits
```

For OS-level upkeep — safe `apt` upgrades and Python version changes — see the [Maintenance Guide](docs/MAINTENANCE_GUIDE.md).

### SSH Admin Access

Each admin generates an SSH key pair once on their own machine, then adds the public key through the web UI (**Settings → General → Advanced → SSH Access**). It gets installed for both the `mempaper` account (scoped sudo) and `pi` (full sudo).

Full procedure, including disabling password login: [Security Guide → SSH keys and password login](docs/SECURITY_GUIDE.md#4-ssh-keys-and-password-login).

### Admin Users

Multiple admin users are supported. Users are stored as Argon2id hashes in `config/config.json` under the `admin_users` key.

```bash
cd /home/mempaper/btc-mempaper
sudo -u mempaper .venv/bin/python tools/setup_user.py                # create or update
sudo -u mempaper .venv/bin/python tools/setup_user.py --list         # list users
sudo -u mempaper .venv/bin/python tools/setup_user.py --delete alice # delete a user
```

> Use the venv interpreter and the `mempaper` user, as above. A bare `python` misses
> the dependencies, and running as `pi` writes a root-owned config the service cannot read.

> The script refuses to delete the last remaining user to prevent lockout.
>
> The script can be run while the service is running -- the application picks up the config change automatically. For password resets it is safer to stop the service first: `sudo systemctl stop mempaper`.

**Existing installations** are migrated automatically on first startup: the single `admin_username` / `admin_password_hash` fields in the config are moved into the `admin_users` dict -- no manual action required.

### Software Update

mempaper can be updated directly from the web UI. Navigate to **Settings > Updates** to see the current version and available releases.

<p align="center">
  <img src="images/screenshots/software-update.png" alt="Software Update Section" width="600"/>
  <br/>
  <em>Software Update section in Settings</em>
</p>

#### Web UI Update (Recommended)

1. Open the **Software Updates** section in Settings
2. Select the desired release from the dropdown (latest is pre-selected and highlighted in orange)
3. Click **Update** and confirm
4. The app will fetch the release, install dependencies, and restart the service
5. If the e-ink display is currently refreshing, the restart waits until the display is idle
6. The page refreshes automatically once the service is back online

#### Automatic Updates

Enable scheduled updates to keep mempaper up to date without manual intervention:

| Setting | Config Key | Description |
|---------|-----------|-------------|
| **Automatic Updates** | `auto_update_enabled` | Enable/disable scheduled updates |
| **Update Time** | `auto_update_time` | Time of day to check for updates (HH:MM, default: `03:00`) |
| **Update Days** | `auto_update_days` | Days of the week to run updates (default: Mon, Wed, Fri) |

When enabled, mempaper checks for new releases at the configured time and day, installs the update, and restarts the service automatically.

#### Manual Update via SSH

The app lives in the service account's home directory and every file is owned by
`mempaper`, so run the update steps as that user — otherwise pip writes
root-owned files into the virtualenv and the service fails to start afterwards.

```bash
ssh pi@<pi-ip>
cd /home/mempaper/btc-mempaper

sudo -u mempaper git fetch --tags
sudo -u mempaper git checkout <tag>          # e.g. git checkout v2.1.0
sudo -u mempaper .venv/bin/pip install -r requirements.txt --quiet

# Re-minify only if you opted into minification at install time.
# This mirrors what the web updater does: it re-minifies when dist/ has content.
[ -n "$(ls -A static/js/dist 2>/dev/null)" ] \
  && sudo -u mempaper .venv/bin/python tools/minify.py

sudo systemctl restart mempaper.service
```

> Skipping the minify step on a device that *does* use minified assets leaves
> `static/js/dist/` holding the previous release's JavaScript — the UI then runs
> stale code against a new backend.

#### Transferring Memes via SCP

The installer adds the `pi` user to the `mempaper` group and sets `static/memes/` to group-writable (`chmod 2775`), so you can copy memes directly from another machine without switching users:

```bash
# Copy a local memes folder to the Pi
scp -r ~/memes/* pi@<pi-ip>:/home/mempaper/btc-mempaper/static/memes/
```

> **Note:** You must log out and back in (or run `newgrp mempaper`) on the Pi after installation for the group membership to take effect for any already-running SSH session.

#### Private Repositories

If your git remote points to a private repository (e.g. self-hosted GitLab), the updater falls back to local git tags — updates still work, but release notes won't be shown in the web UI.

To enable full release notes, create a `.env` file with an API token:

```bash
cp .env.example .env
nano .env
```

```env
# GitHub: Personal Access Token with "repo" scope
# GitLab: Personal Access Token with "read_api" scope
GIT_API_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx
```

#### Permissions

The web UI update requires a sudoers entry for passwordless service restart. `install.sh` sets this up for you; to install it manually:

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart mempaper.service" | sudo tee /etc/sudoers.d/mempaper-update
sudo chmod 0440 /etc/sudoers.d/mempaper-update
```

---

<br/>

## DOCUMENTATION

- [Architecture](docs/ARCHITECTURE.md) -- Diagrams: deployment topologies, what data leaves the device, codebase map, block-to-image data flow
- [Configuration Reference](docs/CONFIG_REFERENCE.md) -- Complete guide to all settings
- [Manual Installation](docs/MANUAL_INSTALL.md) -- Every command `install.sh` runs, step by step
- [Security Guide](docs/SECURITY_GUIDE.md) -- Hardening guide: installation, SSH, firewalls, threat model, audit checklist
- [Maintenance Guide](docs/MAINTENANCE_GUIDE.md) -- Safe apt upgrades, Python version management
- [Self-Hosting Guide](docs/SELF_HOSTING_GUIDE.md) -- Expose mempaper to the internet via Traefik, OIDC login, and TLS; run a Tang server so wallet data cannot be decrypted off your network
- [Cache System Documentation](docs/UNIFIED_CACHE_DOCUMENTATION.md) -- Technical cache implementation details

### Project Structure

The codebase is organised into four layers — adapters bring data in, one orchestrator schedules, one renderer produces both images, two sinks deliver them. See the [component map and directory layout](docs/ARCHITECTURE.md#codebase-map) in the Architecture doc.


<br/>

---

<br/>

## LICENSE

This project is **100% Open Source** under [GPL-3.0](LICENSE) license. Clone it, build your own mempaper, or contribute to the project!

<br/>

---

<br/>

## SUPPORT THE PROJECT


If you find this project useful and want to support its development, you can send a Lightning tip:
<p align="center">
  <img src="images/lightning-qr.jpg" alt="Lightning Donation QR Code" width="200"/>
  <br/>
  <code>khakioctopus15@primal.net</code>
</p>
Every sat helps keep the project maintained and adds new features! 

<br/>

---

<p align="center">
  <code>mempaper</code> &middot; GPL-3.0 &middot; satcat21 &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Built with love for the Bitcoin community
</p>
