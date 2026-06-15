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
  <a href="#gallery">Gallery</a> &nbsp;&bull;&nbsp;
  <a href="#technical-stuff">Technical Stuff</a> &nbsp;&bull;&nbsp;
  <a href="#quick-start">Quick Start</a> &nbsp;&bull;&nbsp;
  <a href="#onboarding--first-time-setup">Onboarding</a> &nbsp;&bull;&nbsp;
  <a href="#configuration">Configuration</a> &nbsp;&bull;&nbsp;
  <a href="#documentation">Documentation</a>
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
      Custom Python - by Bitcoiners for Bitcoiners
    </td>
  </tr>
  <tr>
    <td>
      <strong>POWER USAGE</strong><br/>
      ~1 Watt
    </td>
    <td>
      <strong>DATA SOURCE</strong><br/>
      mempool.space or self-hosted full node
    </td>
  </tr>
</table>

<br/>

---

<br/>

## FEATURES

- **Real-time Data** - Blocks, difficulty, hashrate, and fees from mempool.space integration
- **Hardware Support** - Ready for Raspberry Pi (Zero/3/4/5) and Waveshare e-Paper displays
- **Web Dashboard** - Responsive interface for configuration and monitoring
- **Miner Integration** - Monitor Bitaxe miner stats and aggregate hashrate
- **Wallet Monitoring** - Track balances and block rewards (XPUB support included)
- **Security** - Argon2id password hashing, rate limiting, and encrypted configuration
- **OPSec Mode** - One-click toggle to show a random cover image on the e-ink display instead of Bitcoin data

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

<br/>

---

<br/>

## SHOPPING LIST

Here are the components needed to build your own mempaper display.

> **Note:** Prices are approximate and may vary by region and vendor. The Raspberry Pi Zero 2 W is recommended over the original Zero W for better performance.

### Shared Components (~63 EUR)

These components are the same regardless of which display you choose:

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Raspberry Pi Zero 1 WH / 2 WH** | Main controller (512MB RAM, WiFi/BT) | ~21 EUR | [Zero 1 WH](https://www.berrybase.de/raspberry-pi-zero-wh) \| [Zero 2 WH](https://www.berrybase.de/raspberry-pi-zero-2-wh) |
| **MicroSD Card** | 32GB or larger, Class 10 recommended | ~13 EUR | [SanDisk Extreme 64GB](https://www.amazon.de/dp/B09X7CXWQQ) |
| **USB-C Power Supply** | 5V/2.5A minimum | ~10 EUR | |
| **USB-C to Micro-USB Adapter** | 2-pack adapter for power routing | ~4 EUR | [Amazon](https://www.amazon.de/dp/B0B7RMFMN4) |
| **90 deg USB-C Panel Mount Cable** | Right-angle extension for clean cable routing | ~15 EUR | [Amazon](https://www.amazon.de/dp/B0BQGBWVWM) |

> **Cable Routing:** The USB-C to Micro-USB adapter and 90 deg panel mount cable allow you to cleanly route power from the Raspberry Pi to the back of the picture frame for a professional finish.

### Option A -- Waveshare 7.3" e-Paper (7-color) -- Total ~215 EUR

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Waveshare 7.3" e-Paper (F)** | 7-color e-ink display (800x480) | ~88 EUR | [Waveshare](https://www.waveshare.com/7.3inch-e-paper-hat-f.htm) \| [Amazon](https://www.amazon.de/dp/B0C3R7Q75T) |
| **Photo Frame** | 18x24cm frame for display mounting | ~47 EUR | [allesrahmen.de](https://www.allesrahmen.de/bilderrahmen-ystad-aus-massivholz-mit-distanzleiste-18x24-cmweiss-gemasert27-2043000.html) |
| **Passepartout (Mat Board)** | 180x240mm outer, 94x158mm opening | ~17 EUR | [wandstyle.com](https://www.wandstyle.com/passepartout-bianco-naturale-30-x-40-cm/psta-254-030-040p-p1) |

> **Passepartout Dimensions:** The 7.3" display has a visible area of 160x96mm. The passepartout opening is 158x94mm (2mm smaller on each side) to hold the display securely in place.

### Option B -- Waveshare 13.3" e-Paper (6-color) -- Total ~518 EUR

| Component | Description | Price | Link |
|-----------|-------------|-------|------|
| **Waveshare 13.3" e-Paper (E)** | 6-color Spectra 6 e-ink display (1200x1600) | ~362 EUR | [Waveshare](https://www.waveshare.com/13.3inch-e-paper-hat-plus-e.htm) \| [Amazon](https://www.amazon.de/Waveshare-13-3inch-HAT-1600x1200-Communication/dp/B0DPBW2R25) |
| **Photo Frame** | 28x35cm frame for display mounting | ~76 EUR | [allesrahmen.de](https://www.allesrahmen.de/bilderrahmen-ystad-aus-massivholz-mit-distanzleiste-28x35-cmweiss-gemasert27-1001000.html) |
| **Passepartout (Mat Board)** | 280x350mm outer, 200x268mm opening | ~17 EUR | [wandstyle.com](https://www.wandstyle.com/passepartout-bianco-naturale-30-x-40-cm/psta-254-030-040p-p1) |

<br/>

---

<br/>

## QUICK START

### 1. Installation

> **Recommended OS:** Raspberry Pi OS Lite **Bookworm (Debian 12, 32-bit)** -- this is the tested and supported OS version. Debian 13 (trixie) with Python 3.13 causes Pillow SIGILL crashes on Pi Zero 1 WH due to incompatible SIMD instructions in the piwheels armv6l build.

**Raspberry Pi / Linux**
```bash
# Install system dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y libffi-dev build-essential python3-pip python3-pil python3-dev python3-numpy python3-gpiozero libopenjp2-7 pkg-config libjpeg-dev zlib1g-dev libfreetype-dev libwebp-dev

# Clone and install
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
python3 -m venv .venv
source .venv/bin/activate
pip install spidev gpiozero lgpio
pip install -r requirements.txt
```

**PC / Windows**
```powershell
# Clone and install
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Setup (All Platforms)

1. **Create Configuration**
   ```bash
   cp config/config.json.example config/config.json
   # Windows: copy config\config.json.example config\config.json
   ```

   > **IMPORTANT:** Open `config/config.json` now and review:
   > - `language`, `web_orientation`, `eink_orientation`, `mempool_host`, etc.
   ```bash
   nano config/config.json
   ```

2. **Create the first admin user**

   ```bash
   python scripts/setup_user.py
   ```

   You will be prompted for a username and password. The password is hashed with Argon2id and stored in the config -- the plain text is never saved.

3. **Start the application**

   ```bash
   python serve.py
   ```

   > **Memes:** Upload your own meme images via the web interface (Meme Management section in Settings). Supported formats: PNG, JPG, JPEG, GIF, WebP.

   Access the dashboard at [http://mempaper-ip:5000](http://mempaper-ip:5000)

   **After setup is complete**, press `Ctrl+C` to stop the server.

4. **Enable Background Service (Linux Systems)**

   For production use, run mempaper as a systemd service (auto-starts on boot).

   **Generate the service file** (automatically configures paths and user):

   ```bash
   python scripts/generate_service_file.py
   cat mempaper.service
   sudo cp mempaper.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mempaper.service
   sudo systemctl start mempaper.service
   sudo systemctl status mempaper.service
   ```

   The dashboard will be accessible at [http://mempaper-ip:5000](http://mempaper-ip:5000).

   **Service Management:**
   ```bash
   sudo journalctl -u mempaper.service -f       # View live logs
   sudo systemctl restart mempaper.service       # Restart after config changes
   sudo systemctl stop mempaper.service          # Stop service
   sudo systemctl disable mempaper.service       # Disable auto-start
   ```

5. **Enable Integrated Wi-Fi Onboarding Hotspot (for shipped devices)**

  This installs the required permissions for NetworkManager operations used by `mempaper.service`.

  ```bash
  sudo bash scripts/install_wifi_permissions.sh
  ```

  > If you updated scripts in this repository later, run the command again to refresh installed rules.

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

<br/>

---

<br/>

## DISPLAY SETUP (RASPBERRY PI)

Mempaper supports Waveshare e-Paper displays. The **Waveshare 7.3inch F (7-color)** is the primary target.

### 1. Enable SPI Interface
```bash
sudo raspi-config
# Navigate to: 3 Interface Options -> I4 SPI -> Yes
```

### 2. Configure Display

Run the configuration tool to select your display. It automatically downloads and installs the required driver files:

```bash
python scripts/configure_display.py
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

<br/>

---

<br/>

## PROJECT STRUCTURE

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
|-- scripts/                     Administration & Setup
|   |-- configure_display.py     Display configuration wizard
|   |-- setup_user.py            Create / update / delete admin users
|   |-- delivery_state.py        Prepare device for delivery
|   |-- diagnose_mempool_api.py  Mempool API diagnostics
|   |-- generate_service_file.py Generate systemd service config
|   |-- backup_manager.py        Backup & maintenance utility
|   +-- reset_cache_rpi.sh       Cache reset for Raspberry Pi
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
- **scripts/** are standalone tools for setup and maintenance

<br/>

---

<br/>

## USER MANAGEMENT

Multiple admin users are supported. Users are stored as Argon2id hashes in `config/config.json` under the `admin_users` key.

```bash
python scripts/setup_user.py                # Create or update a user
python scripts/setup_user.py --list         # List all configured users
python scripts/setup_user.py --delete alice # Delete a user
```

> The script refuses to delete the last remaining user to prevent lockout.
>
> The script can be run while the service is running -- the application picks up the config change automatically. For password resets it is safer to stop the service first: `sudo systemctl stop mempaper`.

**Existing installations** are migrated automatically on first startup: the single `admin_username` / `admin_password_hash` fields in the config are moved into the `admin_users` dict -- no manual action required.

<br/>

---

<br/>

## DELIVERY MODE (SHIPMENT)

Prepare a reset device for shipment:

```bash
python scripts/delivery_state.py
```

What this does:
- renders a clean delivery image on e-ink
- leaves startup behavior in integrated mode (`mempaper.service` only)
- clears setup-mode state so the next boot starts clean

At next boot, `mempaper.service` automatically enables setup hotspot if Wi-Fi cannot connect.

<br/>

---

<br/>

## ONBOARDING / FIRST-TIME SETUP

When a customer powers on a freshly prepared device for the first time, the following onboarding flow guides them through WiFi configuration and admin account creation -- no SSH or technical knowledge required.

### Step 1 -- Delivery State (E-Ink)

The device ships with the delivery-state image on the e-ink display.

<p align="center"><img src="images/readme/onboarding_1_delivery_state.png" alt="Delivery state e-ink screen" width="600"/></p>

### Step 2 -- Setup Hotspot (E-Ink)

On first boot, the device detects that no WiFi is configured and automatically starts a WPA2 setup hotspot. **This takes between 90 seconds and 2 minutes 21 seconds** -- the Pi needs to boot, initialize the WiFi radio, and switch to AP mode. Once ready, the e-ink display refreshes and shows the hotspot SSID, password, and a QR code to connect.

- **SSID:** `mempaper-XXXX` (4-digit suffix derived from the device MAC)
- **Security:** WPA2 (password = 8 hex chars derived from device MAC)
- Scan the QR code with your phone to connect automatically

> **Tip:** Wait until the e-ink display updates from the delivery-state image to the hotspot screen before trying to connect. If the display does not refresh after 2 minutes, the hotspot may have failed to start -- simply power-cycle the device and try again.

<p align="center"><img src="images/readme/onboarding_2_hotspot.png" alt="Hotspot onboarding e-ink screen" width="600"/></p>

### Step 3 -- WiFi Setup Web Page

After connecting to the hotspot, open `http://10.42.0.1:5000/setup` in your browser (this URL is also available as a QR code on the right side of the e-ink screen). The setup page allows the user to:

1. **Select a language** (English, German, Spanish, French, Italian)
2. **Choose your home WiFi** from a scanned list (or enter a hidden SSID)
3. **Enter the WiFi password**
4. **Create an admin account** (username + password for the dashboard)

<p align="center"><img src="images/readme/onboarding_3_wifi_setup.png" alt="WiFi setup web page" width="400"/></p>

### Step 4 -- Connection Success (E-Ink)

Once the device connects to the home WiFi, the e-ink display shows a success screen with instructions on how to access the dashboard from the home network.

<p align="center"><img src="images/readme/onboarding_4_connected.png" alt="WiFi connected e-ink screen" width="600"/></p>

After 60 seconds, the display switches to normal operation mode and shows the first dashboard image.

### Device Reset

If the user forgets their admin password or needs to start fresh, there are two reset options:

#### Option A -- Reset Button (Setup Page)

If the device is in hotspot/setup mode (e.g. stored WiFi unavailable), the setup web page shows a **"Reset Device"** button at the bottom. This clears:

- All admin accounts
- Wallet addresses and monitoring data
- Bitaxe miner configuration
- Donation history and webhook URLs
- Mempool authentication
- Mobile app tokens

The device remains in setup mode so the user can reconfigure WiFi and create a new admin account.

#### Option B -- Power-Cycle Factory Reset

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

<br/>

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
| **Bitaxe** | `show_bitaxe_block` | Aggregate hashrate and found blocks |
| **Wallet Balances** | `show_wallet_balances_block` | On-chain balances for addresses / XPUBs / ZPUBs |
| **Lightning Donation** | `show_donation_block` | Latest Lightning donation via LNbits webhook |

> All blocks are **on** by default except Bitaxe, Wallet Balances, and Donation, which require additional setup.

See [Configuration Reference](docs/CONFIG_REFERENCE.md) for detailed explanation of all settings.

<br/>

---

<br/>

## DOCUMENTATION

- [Configuration Reference](docs/CONFIG_REFERENCE.md) -- Complete guide to all settings
- [Security Guide](docs/SECURITY_GUIDE.md) -- Encryption and password protection
- [Cache System Documentation](docs/UNIFIED_CACHE_DOCUMENTATION.md) -- Technical cache implementation details

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
