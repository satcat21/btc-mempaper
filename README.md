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

### Shopping List

Here are the components needed to build your own mempaper display.

> **Note:** Prices are approximate and may vary by region and vendor. The Raspberry Pi Zero 2 W is recommended over the original Zero W for better performance.

#### Shared Components (~63 EUR)

These components are the same regardless of which display you choose:

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Raspberry Pi Zero 1 WH / 2 WH** | Main controller (512MB RAM, WiFi/BT) | ~21 EUR | [Zero 1 WH](https://www.berrybase.de/raspberry-pi-zero-wh) \| [Zero 2 WH](https://www.berrybase.de/raspberry-pi-zero-2-wh) |
| **MicroSD Card** | 32GB or larger, Class 10 recommended | ~13 EUR | [SanDisk Extreme 64GB](https://www.amazon.de/dp/B09X7CXWQQ) |
| **USB-C Power Supply** | 5V/2.5A minimum | ~10 EUR | |
| **USB-C to Micro-USB Adapter** | 2-pack adapter for power routing | ~4 EUR | [Amazon](https://www.amazon.de/dp/B0B7RMFMN4) |
| **90 deg USB-C Panel Mount Cable** | Right-angle extension for clean cable routing | ~15 EUR | [Amazon](https://www.amazon.de/dp/B0BQGBWVWM) |

> **Cable Routing:** The USB-C to Micro-USB adapter and 90 deg panel mount cable allow you to cleanly route power from the Raspberry Pi to the back of the picture frame for a professional finish.

#### Option A -- Waveshare 7.3" e-Paper (7-color) -- Total ~215 EUR

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Waveshare 7.3" e-Paper (F)** | 7-color e-ink display (800x480) | ~88 EUR | [Waveshare](https://www.waveshare.com/7.3inch-e-paper-hat-f.htm) \| [Amazon](https://www.amazon.de/dp/B0C3R7Q75T) |
| **Photo Frame** | 18x24cm frame for display mounting | ~47 EUR | [allesrahmen.de](https://www.allesrahmen.de/bilderrahmen-ystad-aus-massivholz-mit-distanzleiste-18x24-cmweiss-gemasert27-2043000.html) |
| **Passepartout (Mat Board)** | 180x240mm outer, 94x158mm opening | ~17 EUR | [wandstyle.com](https://www.wandstyle.com/passepartout-bianco-naturale-30-x-40-cm/psta-254-030-040p-p1) |

> **Passepartout Dimensions:** The 7.3" display has a visible area of 160x96mm. The passepartout opening is 158x94mm (2mm smaller on each side) to hold the display securely in place.

#### Option B -- Waveshare 13.3" e-Paper (6-color) -- Total ~518 EUR

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

### Quick Start

#### 1. Installation

> **Supported OS:** Raspberry Pi OS Lite **32-bit** — both **Bookworm (Debian 12)** and **Trixie (Debian 13)** are supported. On Pi Zero 1 WH (ARMv6) with Trixie/Python 3.13, piwheels does not yet provide ARMv6 wheels for Python 3.13 and PyPI wheels target ARMv7+. The installer automatically detects this and rebuilds **gevent** and **Pillow** from source so their C extensions are compiled for the device's ARMv6 CPU. This takes 10–20 minutes on first install. Ship with Trixie — it receives OS security updates longer than Bookworm.

**Raspberry Pi (one-click installer)**

On a fresh Raspberry Pi OS, run these once before cloning:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git locales-all
```

Then clone and run the installer:

```bash
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
bash install.sh
```

Run as your normal user (e.g. `pi`) — **not** as root. The script uses `sudo` internally where needed.

The installer takes care of everything:
- Creates the `mempaper` service account
- Installs all system and Python packages
- Rebuilds Pillow from source on Pi Zero 1 WH (armv6l) if the piwheels wheel is incompatible
- Copies the example config (skipped if `config/config.json` already exists)
- Configures the e-ink display (interactive prompt)
- Generates and installs the `mempaper.service` systemd unit
- Sets up Wi-Fi hotspot permissions
- Optionally configures UFW firewall and fail2ban
- Starts the service

When the service starts the Pi enters **hotspot onboarding mode**. Connect to the `mempaper-XXXX` Wi-Fi network from your phone or laptop, then open [http://10.42.0.1:5000](http://10.42.0.1:5000) to complete setup.

**Service management after install:**
```bash
sudo journalctl -u mempaper.service -f       # live logs
sudo systemctl restart mempaper.service       # restart after config changes
sudo systemctl status mempaper.service        # status
```

**PC / Windows (development only)**
```powershell
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 2. Configure SSH Admin Access (for shipped devices)

  Admins need SSH access for full system maintenance. Each admin generates a key pair **once on their own machine** — the private key never leaves their machine.

  **Admin: generate your key pair (run on your laptop, not the Pi):**
  ```bash
  ssh-keygen -t ed25519 -C "your-name-mempaper"
  cat ~/.ssh/id_ed25519.pub   # copy this output
  ```

  **On the device:** log into the web UI → General → SSH Access → paste the public key → click **Add Key**.

  This writes the key to both the `mempaper` user (scoped sudo) and the `pi` user (full sudo). Each user gets their own key entry; keys can be removed via the same UI.

  **Connect after delivery:**
  ```bash
  ssh mempaper@<pi-ip>   # scoped maintenance (apt-get upgrade, restart, reboot)
  ssh pi@<pi-ip>         # full root access (apt dist-upgrade, system config, etc.)
  ```

  > **Note:** SSH must be enabled on the Pi. On Raspberry Pi OS, enable it via `sudo raspi-config` → Interface Options → SSH, or by placing an empty file named `ssh` in the `/boot` partition before first boot.

  **Harden SSH (disable password login, key-only):**

  Edit `/etc/ssh/sshd_config` on the Pi:
  ```bash
  sudo nano /etc/ssh/sshd_config
  ```
  Set or uncomment these lines:
  ```
  PubkeyAuthentication yes
  PasswordAuthentication no
  PermitRootLogin no
  AuthorizedKeysFile .ssh/authorized_keys
  ```
  Apply:
  ```bash
  sudo systemctl restart ssh
  ```
  > **Important:** Verify key login works in a second terminal **before** closing your current session, or you will be locked out.

  **Restrict SSH to LAN only (firewall):**

  The `sshd_config` changes above disable password login but don't restrict *which IPs* can reach SSH. Without an explicit firewall rule, LAN-only access relies entirely on your router not forwarding port 22 — fine for typical home deployment, but fragile. Lock it down on the device itself with `ufw`:

  ```bash
  sudo apt install ufw -y

  # Allow SSH only from private LAN ranges
  sudo ufw allow from 10.0.0.0/8 to any port 22
  sudo ufw allow from 172.16.0.0/12 to any port 22
  sudo ufw allow from 192.168.0.0/16 to any port 22

  # Allow mempaper web UI from anywhere
  sudo ufw allow 5000/tcp

  sudo ufw --force enable
  ```

  > For standard home router setups NAT already blocks inbound SSH, but explicit rules are the safer default.

  **Verify installation:**

  ```bash
  sudo systemctl status mempaper.service
  sudo journalctl -u mempaper.service -f
  ```

  **Expected behavior after delivery prep:**
  - `mempaper.service` runs on boot
  - On power-on, app first attempts normal Wi-Fi connection
  - If no Wi-Fi is available after startup grace, app starts setup hotspot automatically
  - User connects to `mempaper-XXXX`, opens `http://192.168.12.1:5000`, enters Wi-Fi credentials
  - On successful connection, setup hotspot is disabled and normal operation resumes automatically

6. **Disable Wi-Fi Power Saving (Raspberry Pi Zero W)**

  The BCM43430 Wi-Fi chip on the Pi Zero W has power management **enabled by default**. This causes the chip to miss router beacons during idle periods, leading to the router deauthenticating the Pi and dropping the connection. Disabling it prevents intermittent disconnects.

  ```bash
  sudo tee /etc/NetworkManager/conf.d/99-disable-powersave.conf << 'EOF'
  [connection]
  wifi.powersave = 2
  EOF
  sudo systemctl restart NetworkManager
  ```

  Verify it took effect:
  ```bash
  iwconfig wlan0 | grep Power
  # Should show: Power Management:off
  ```

  > `wifi.powersave = 2` means "disabled" in NetworkManager's enum (0 = default, 1 = ignore, 2 = disable, 3 = enable). The file is placed in the NM drop-in directory `/etc/NetworkManager/conf.d/` and survives reboots and NM restarts.

### Display Setup (Raspberry Pi)

mempaper supports Waveshare e-Paper displays. The **Waveshare 7.3inch F (7-color)** is the primary target.

#### 1. Enable SPI Interface
```bash
sudo raspi-config
# Navigate to: 3 Interface Options -> I4 SPI -> Yes
```

#### 2. Configure Display

Run the configuration tool to select your display. It automatically downloads and installs the required driver files:

```bash
python tools/configure_display.py
```

Supported native displays:
- **13.3" E-Paper E (Spectra 6 / epd13in3E)** -- 6-color, recommended
- **7.3" F (7-color / epd7in3f)**

The driver files are placed in `display/drivers/<device>/` and loaded automatically. Driver files are MIT licensed by Waveshare Electronics (see [display/drivers/README.md](display/drivers/README.md)).

**Option: Omni-EPD**
Use this if you need support for many different display types or prefer the abstraction layer.

```bash
git clone https://github.com/robweber/omni-epd.git
cd omni-epd
pip3 install --upgrade pip setuptools wheel
pip3 install --prefer-binary .
```

> **Note:** Service setup is covered in the [Quick Start](#quick-start) section above.

### User Management

Multiple admin users are supported. Users are stored as Argon2id hashes in `config/config.json` under the `admin_users` key.

```bash
python tools/setup_user.py                # Create or update a user
python tools/setup_user.py --list         # List all configured users
python tools/setup_user.py --delete alice # Delete a user
```

> The script refuses to delete the last remaining user to prevent lockout.
>
> The script can be run while the service is running -- the application picks up the config change automatically. For password resets it is safer to stop the service first: `sudo systemctl stop mempaper`.

**Existing installations** are migrated automatically on first startup: the single `admin_username` / `admin_password_hash` fields in the config are moved into the `admin_users` dict -- no manual action required.

### Delivery Mode (Shipment)

Prepare a reset device for shipment:

```bash
python tools/delivery_state.py
```

What this does:
- renders a clean delivery image on e-ink
- leaves startup behavior in integrated mode (`mempaper.service` only)
- clears setup-mode state so the next boot starts clean

At next boot, `mempaper.service` automatically enables setup hotspot if Wi-Fi cannot connect.

### Onboarding / First-Time Setup

When a customer powers on a freshly prepared device for the first time, the following onboarding flow guides them through WiFi configuration and admin account creation -- no SSH or technical knowledge required.

#### Step 1 -- Delivery State (E-Ink)

The device ships with the delivery-state image on the e-ink display.

<p align="center"><img src="images/readme/onboarding_1_delivery_state.png" alt="Delivery state e-ink screen" width="600"/></p>

#### Step 2 -- Setup Hotspot (E-Ink)

On first boot, the device detects that no WiFi is configured and automatically starts a WPA2 setup hotspot. **This takes between 90 seconds and 2 minutes 21 seconds** -- the Pi needs to boot, initialize the WiFi radio, and switch to AP mode. Once ready, the e-ink display refreshes and shows the hotspot SSID, password, and a QR code to connect.

- **SSID:** `mempaper-XXXX` (4-digit suffix derived from the device MAC)
- **Security:** WPA2 (password = 8 hex chars derived from device MAC)
- Scan the QR code with your phone to connect automatically

> **Tip:** Wait until the e-ink display updates from the delivery-state image to the hotspot screen before trying to connect. If the display does not refresh after 2 minutes, the hotspot may have failed to start -- simply power-cycle the device and try again.

<p align="center"><img src="images/readme/onboarding_2_hotspot.png" alt="Hotspot onboarding e-ink screen" width="600"/></p>

#### Step 3 -- WiFi Setup Web Page

After connecting to the hotspot, open `http://10.42.0.1:5000/setup` in your browser (this URL is also available as a QR code on the right side of the e-ink screen). The setup page allows the user to:

1. **Select a language** (English, German, Spanish, French, Italian)
2. **Choose your home WiFi** from a scanned list (or enter a hidden SSID)
3. **Enter the WiFi password**
4. **Create an admin account** (username + password for the dashboard)

<p align="center"><img src="images/readme/onboarding_3_wifi_setup.png" alt="WiFi setup web page" width="400"/></p>

#### Step 4 -- Connection Success (E-Ink)

Once the device connects to the home WiFi, the e-ink display shows a success screen with instructions on how to access the dashboard from the home network.

<p align="center"><img src="images/readme/onboarding_4_connected.png" alt="WiFi connected e-ink screen" width="600"/></p>

After 60 seconds, the display switches to normal operation mode and shows the first dashboard image.

#### Device Reset

If the user forgets their admin password or needs to start fresh, there are two reset options:

##### Option A -- Reset Button (Setup Page)

If the device is in hotspot/setup mode (e.g. stored WiFi unavailable), the setup web page shows a **"Reset Device"** button at the bottom. This clears:

- All admin accounts
- Wallet addresses and monitoring data
- Bitaxe miner configuration
- Donation history and webhook URLs
- Mempool authentication
- Mobile app tokens

The device remains in setup mode so the user can reconfigure WiFi and create a new admin account.

##### Option B -- Power-Cycle Factory Reset

For a full factory reset (including WiFi profiles and e-ink display), the user can power-cycle the device rapidly:

1. **Power on** the device, wait **2 minutes**, then **power off**
2. **Repeat** two more times (3 power cycles total)
3. **Power on** a 4th time -- the device now detects the pattern and resets

The device detects 3 recent boot timestamps within a 15-minute window and automatically:

- Clears all user data (same as Option A)
- Deletes all saved WiFi profiles
- Renders and displays the delivery-state e-ink image
- Starts the setup hotspot for fresh onboarding

> **Important:** Wait the full 2 minutes before powering off each time. The device needs enough time to boot, record the timestamp, and flush all writes to the SD card. Cutting power too early risks corrupting the filesystem.

---

<br/>

## CONFIGURATION

Navigate to **Settings** in the web interface ([http://mempaper-ip:5000](http://mempaper-ip:5000)).

- **Mempool Connection** -- Default is `mempool.space`. Change IP/Port to use a local node or self-hosted mempool instance.
- **Display** -- Toggle "E-Ink Display Connected" to ON.
- **Bitaxe** -- Add miner IPs to monitor hashrate.

For advanced manual configuration, edit `config/config.json`.

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

See [Configuration Reference](docs/CONFIG_REFERENCE.md) for detailed explanation of all settings.

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

```bash
ssh pi@mempaper.local
cd ~/btc-mempaper
git fetch --tags
git checkout <tag>                                    # e.g. git checkout v2.1.0
.venv/bin/pip install -r requirements.txt --quiet
sudo systemctl restart mempaper.service
```

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

The web UI update requires a sudoers entry for passwordless service restart. This is automatically installed by `install_wifi_permissions.sh` (see [Quick Start step 5](#quick-start)). To install it manually:

```bash
echo "$(whoami) ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart mempaper.service" | sudo tee /etc/sudoers.d/mempaper-update
sudo chmod 0440 /etc/sudoers.d/mempaper-update
```

---

<br/>

## DOCUMENTATION

- [Configuration Reference](docs/CONFIG_REFERENCE.md) -- Complete guide to all settings
- [Security Guide](docs/SECURITY_GUIDE.md) -- Hardening guide: installation, SSH, UFW, threat model, audit checklist
- [Maintenance Guide](docs/MAINTENANCE_GUIDE.md) -- Safe apt upgrades, Python version management
- [Self-Hosting Guide](docs/SELF_HOSTING_GUIDE.md) -- Expose mempaper to the internet via Traefik, OIDC login, and TLS
- [Cache System Documentation](docs/UNIFIED_CACHE_DOCUMENTATION.md) -- Technical cache implementation details

### Project Structure

The codebase is organized into functional modules:

```
btc-mempaper/
|
|-- Entry Points
|   |-- mempaper_app.py          Main Flask application (core logic)
|   |-- serve.py                 Development server (quick start)
|   |-- wsgi.py                  Production WSGI entry point
|   +-- gunicorn.conf.py         Production server configuration
|
|-- lib/                         Core Business Logic
|   |-- mempool_api.py           Mempool.space API client
|   |-- btc_price_api.py         Bitcoin price data
|   |-- bitaxe_api.py            Bitaxe miner integration
|   |-- wallet_balance_api.py    Wallet balance & XPUB tracking
|   |-- block_monitor.py         Block height monitoring
|   |-- block_reward_cache.py    Persistent block reward storage
|   |-- image_renderer.py        Dashboard image generation
|   |-- display_subprocess.py    Display refresh handler
|   |-- websocket_client.py      Real-time mempool WebSocket
|   |-- address_derivation.py    HD wallet address derivation
|   +-- btc_holidays.py          Bitcoin historical events
|
|-- managers/                    Configuration & Security
|   |-- config_manager.py        Configuration management
|   |-- config_observer.py       Config change monitoring
|   |-- auth_manager.py          Authentication & rate limiting
|   |-- secure_config_manager.py Encrypted configuration storage
|   |-- secure_password_manager.py   Argon2id password hashing
|   |-- secure_cache_manager.py  Encrypted cache files
|   |-- unified_secure_cache.py  Unified cache encryption
|   +-- mobile_token_manager.py  Mobile API token management
|
|-- utils/                       Utilities & Helpers
|   |-- translations.py          Multi-language support (en, de, es, it, fr)
|   |-- color_lut.py             E-Paper color palette mapping
|   |-- epd_color_fix.py         Waveshare 7-color optimizations
|   |-- privacy_utils.py         Bitcoin address masking for logs
|   |-- security_config.py       Security constants & settings
|   +-- technical_config.py      Technical constants & defaults
|
|-- tools/                       Developer & maintenance tools
|   |-- minify.py                JS minifier (generates static/js/dist/)
|   |-- configure_display.py     Display configuration wizard
|   |-- setup_user.py            Create / update / delete admin users
|   |-- delivery_state.py        Prepare device for delivery
|   |-- diagnose_mempool_api.py  Mempool API diagnostics
|   |-- generate_service_file.py Generate systemd service config
|   |-- backup_manager.py        Backup & maintenance utility
|   |-- reset_cache_rpi.sh       Cache reset for Raspberry Pi
|   |-- install_wifi_permissions.sh  Polkit + sudoers rules for Wi-Fi hotspot
|   +-- 90-mempaper-wifi.rules       Polkit rule for NetworkManager
|
|-- display/                     Display Drivers & Config
|   |-- waveshare_display.py     Native Waveshare driver integration
|   |-- show_image.py            Image display handler
|   |-- prepare_image.py         Image preparation pipeline
|   +-- drivers/                 Bundled Waveshare EPD drivers (MIT)
|       |-- epd13in3E.py         13.3" 6-color driver
|       |-- epd7in3f.py          7.3" 7-color driver
|       +-- epdconfig.py         Shared SPI/GPIO config
|
|-- config/                      User configuration
|-- cache/                       Runtime cache storage
|-- static/                      Web assets, memes, OPSec images
|-- templates/                   HTML templates
+-- docs/                        Documentation
```

**Architecture:**
- **Entry Points** load configuration, initialize **lib/** APIs, render via **display/**
- **managers/** handle security, authentication, and configuration
- **utils/** provide shared functionality across the application
- **tools/** contains developer and maintenance utilities (setup, diagnostics, deployment helpers)

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
