## BTC Mempaper

BTC Mempaper is a Python-based dashboard and e-Paper display app for visualizing Bitcoin mempool data and memes. It supports Raspberry Pi and PC, integrates with a local mempool instance, and features secure password setup, meme downloads, and a web dashboard.

---

### Installation

1. **Clone the repository:**
   ```pwsh
   git clone https://github.com/satcat21/btc-mempaper.git
   cd btc-mempaper
   ```
2. **Create a virtual environment (recommended):**
   ```pwsh
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. **Install dependencies:**
   ```pwsh
   pip install -r requirements.txt
   ```

---

### First Run: Meme Download

To download memes for the display, run:
```pwsh
python initialize_memes.py
```
This will fetch memes from [bitcoinmemes.info](https://bitcoinmemes.info/) and save them to `static/memes/`. If the download fails, follow the manual instructions printed by the script.

---

### Manual App Start

To start the dashboard and e-Paper display app:
```pwsh
python mempaper_app.py
```
The web dashboard will be available at [http://localhost:5000](http://localhost:5000).

---

### User/Password Setup

To set a secure password for the dashboard, run:
```pwsh
python setup_secure_password.py
```
Follow the prompts to set your username and password.

---

### Raspberry Pi Service Setup

For Raspberry Pi, you can run the app as a systemd service:
1. Copy `mempaper.service` to `/etc/systemd/system/`.
2. Edit the service file to set the correct paths.
3. Enable and start the service:
   ```pwsh
   sudo systemctl enable mempaper
   sudo systemctl start mempaper
   ```
See [docs-archive/INSTALL_GUIDE_RASPBERRY_PI.md](docs-archive/INSTALL_GUIDE_RASPBERRY_PI.md) for hardware and SPI setup details. All advanced and legacy documentation is now in docs-archive.

---

### Mempool Connection

BTC Mempaper connects to your local mempool instance via REST and WebSocket. Ensure your mempool is running and accessible. For troubleshooting and advanced configuration, see [docs-archive/mempool.md](docs-archive/mempool.md).

---

### Further Topics & Advanced Guides

For advanced setup, troubleshooting, development, and legacy documentation, see the [docs-archive/](docs-archive/) directory:
- [INSTALL_GUIDE_RASPBERRY_PI.md](docs-archive/INSTALL_GUIDE_RASPBERRY_PI.md)
- [INSTALL_GUIDE_PC.md](docs-archive/INSTALL_GUIDE_PC.md)
- [mempool.md](docs-archive/mempool.md)
- [troubleshooting.md](docs-archive/troubleshooting.md)
- [development.md](docs-archive/development.md)
- [future_enhancements.md](docs-archive/future_enhancements.md)

---

### License

MIT License
# 🚀 BTC Mempaper - Bitcoin Dashboard

**A comprehensive, secure Bitcoin dashboard with web interface, real-time updates, and e-Paper display support.**

Mempaper is a modern Bitcoin dashboard that combines live blockchain data, customizable information blocks, and beautiful visual presentation in a self-hosted web application. Social media integration is currently paused and may be implemented in the future using Nostr instead of X/Twitter.

---

## ✨ Features

- Real-time Bitcoin data from your local mempool
- Responsive web dashboard and e-Paper display support
- Secure authentication and admin panel
- Multi-currency price blocks and wallet monitoring
- Meme gallery and multi-language support
- Raspberry Pi and desktop/server deployment

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Local mempool instance (optional, can use public APIs)
- E-Paper display (optional)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd btc-mempaper
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initial setup**
   ```bash
   python setup_secure_password.py  # Set up secure admin password
   python configure_display.py      # Configure your display (optional)
   ```

5. **Start the application**
   ```bash
   python serve.py  # Production server
   # OR
   python start_fast.py  # Development mode
   ```

6. **Access the dashboard**
   - Open `http://localhost:5000` in your browser
   - Login with your configured admin credentials

---

## 🔧 Configuration


BTC Mempaper uses a single JSON configuration file (`config.json`) to control all app settings. You can use the provided `config.json.example` as a template for your own configuration.

#### Setup Default Configuration
To create a default configuration, copy the example file:
```pwsh
cp config.json.example config.json
```
Edit `config.json` to match your environment and preferences.

#### Supported Settings
Below are all allowed and supported settings in `config.json`:

- `language`: Interface language (`en`, `de`, `es`, `fr`)
- `display_orientation`: `vertical` or `horizontal`
- `prioritize_large_scaled_meme`: Show large memes first (true/false)
- `mempool_ip`: IP address of your mempool instance
- `mempool_rest_port`: REST API port
- `mempool_ws_port`: WebSocket port
- `fee_parameter`: Fee estimation mode (e.g. `fastestFee`)
- `display_width`, `display_height`: Display resolution in pixels
- `e-ink-display-connected`: Enable e-Paper display (true/false)
- `omni_device_name`: Device name for e-Paper (e.g. `waveshare_epd.epd7in3f`)
- `admin_username`: Dashboard admin username
- `rate_limit_requests`: Max requests per window
- `rate_limit_window`: Rate limit window (seconds)
- `show_btc_price_block`: Show BTC price block (true/false)
- `btc_price_currency`: Fiat currency for price display (`USD`, `EUR`, etc.)
- `show_bitaxe_block`: Show Bitaxe miner block (true/false)
- `bitaxe_miner_ips`: IPs of Bitaxe miners (comma-separated)
- `show_wallet_balances_block`: Show wallet balances block (true/false)
- `wallet_balance_unit`: Display unit (`btc` or `sats`)
- `wallet_balance_show_fiat`: Show fiat value for wallet balances (true/false)
- `xpub_derivation_count`: XPUB address derivation count
- `xpub_enable_gap_limit`: Enable XPUB gap limit (true/false)
- `xpub_gap_limit_last_n`: XPUB gap limit last N addresses
- `xpub_gap_limit_increment`: XPUB gap limit increment
- `xpub_enable_bootstrap_search`: Enable XPUB bootstrap search (true/false)
- `xpub_bootstrap_max_addresses`: Max addresses for XPUB bootstrap
- `xpub_bootstrap_increment`: XPUB bootstrap increment
- `color_mode_dark`: Enable dark mode (true/false)
- `font_regular`, `font_bold`: Paths to font files
- `session_timeout`: Session timeout (seconds)
- `backup_duration_minutes`: Backup interval (minutes)
- `block_height_area`: Block height display area (pixels)
- `moscow_time_unit`: Moscow time unit (`hour`, etc.)

For more details and advanced options, see `config.json.example` and the `/admin` web configuration interface.

---


## 🔒 Security Features

### 🛡️ Password Security
- Passwords are hashed using Argon2id (memory-hard, GPU-resistant)
- 64 MB memory cost and unique 16-byte salt per password
- Automatic migration from cleartext passwords

### 🚪 Access Control
- Configurable session timeout and persistent sessions
- Rate limiting to prevent brute force attacks
- Secure authentication and admin-only configuration access

### 🔧 Operational Security
- Automatic configuration backups before changes
- Secure file uploads with type and integrity checks
- Graceful error handling without exposing internals
- Comprehensive activity logging for audit and troubleshooting

---

## 🖼️ Display Support

### 📱 **Supported E-Paper Displays**

#### **Waveshare Displays**
- **7.3" 7-color (EPD7in3F)** ⭐ *Recommended*
- **5.83" V2**, **4.2"**, **2.7"** series
- **Small displays**: 1.02", 1.54", 1.64G
- **Medium displays**: 2.13", 2.36G, 2.66"
- **Large displays**: 7.5" series, HD variants

#### **Inky Displays (Pimoroni)**
- **Inky Impression 7-color**
- **Inky pHAT** (Red/Yellow/Black variants)
- **Inky wHAT** series
- **Auto-detection** support

#### **Testing**
- **Mock display**: Virtual display for development

### ⚙️ **Display Configuration**
1. Run `python configure_display.py`
2. Select your display from the list
3. Automatic dimension and color profile setup
4. Test with mock display first

---

## 🔧 API Integration

### ⛏️ **Mempool Integration**
- **Local mempool server**: Fetching Block and wallet balance data privately
- **WebSocket updates**: Real-time block notifications
- **Fee estimation**: Accurate fee recommendations

### 💰 **Price APIs**
- **Multiple sources**: Redundant price data sources
- **Currency support**: Major fiat currencies
- **Caching**: Intelligent caching for performance
- **Fallback**: Graceful handling of API failures

### ⚡ **Bitaxe Integration**
- **Multiple miners**: Support for multiple Bitaxe devices
- **Health monitoring**: Online/offline status tracking
- **Hashrate aggregation**: Total mining power calculation
- **Block rewards**: Automatic reward detection

---

## 🖥️ Deployment

### 🍓 **Raspberry Pi Setup**

1. **Install Raspberry Pi OS**
2. **Enable SPI** for e-paper displays:
   ```bash
   sudo raspi-config
   # Interface Options → SPI → Enable
   ```
3. **Install dependencies**:
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv git
   ```
4. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd btc-mempaper
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
5. **Configure systemd service**:
   ```bash
   sudo cp mempaper.service /etc/systemd/system/
   sudo systemctl enable mempaper
   sudo systemctl start mempaper
   ```

### 🖥️ **Desktop/Server Deployment**
1. **Setup as above**
2. **Run with production server**: `python serve.py`
3. **Configure reverse proxy** (nginx/apache) if needed
4. **Setup SSL certificate** for secure access

---

## 🛟 Troubleshooting

### 🔍 **Common Issues**

#### **Display Issues**
- **No display output**: Check SPI configuration and device selection
- **Color problems**: Verify e-ink display model in configuration
- **Size mismatch**: Ensure correct width/height settings

#### **API Issues**
- **No Bitcoin data**: Verify mempool server connectivity
- **Twitter/X not working**: Check bearer token and API limits
- **Price data missing**: Verify internet connectivity and API access

#### **Authentication Issues**
- **Login fails**: Reset password with `python setup_secure_password.py`
- **Session expires**: Adjust session timeout in configuration
- **Rate limited**: Wait for rate limit reset or adjust limits

### 📋 **Debug Tools**
```bash
python configure_display.py show    # Display current configuration
python -c "import requests; print(requests.get('http://localhost:4081/api/blocks/tip/height').text)"  # Test mempool
```

---

## 🛠️ Development

### 📁 **Project Structure**
```
btc-mempaper/
├── mempaper_app.py               # Main Flask application
├── config_manager.py             # Configuration management
├── image_renderer.py             # Display rendering engine
├── auth_manager.py               # Authentication system
├── secure_password_manager.py    # Password security
├── wallet_balance_api.py         # Wallet balance API
├── btc_price_api.py              # Bitcoin price API
├── bitaxe_api.py                 # Bitaxe miner API
├── mempool_api.py                # Mempool integration
├── twitter_api.py                # (Paused) Twitter/X API
├── display/                      # Display utilities and scripts
├── static/                       # Web assets (css, js, memes, icons, tweets)
├── templates/                    # HTML templates (dashboard, login, config)
├── fonts/                        # Typography files (Roboto, IBMPlexMono)
├── setup_secure_password.py      # Secure password setup script
├── initialize_memes.py           # Meme download script
├── serve.py                      # Production server entrypoint
├── start_fast.py                 # Development server entrypoint
├── LICENSE                       # License (GPLv3)
├── requirements.txt              # Python dependencies
└── README.md                     # This documentation
```

### 🔧 **Development Mode**
```bash
python start_fast.py  # Fast startup for development
```

### 📝 **Contributing**
1. Follow existing code patterns
2. Add tests for new features
3. Update documentation
4. Use secure coding practices

---

## 📄 License

This project is licensed under the GNU General Public License v3.0 (GPLv3). See the LICENSE file for details.

---

## 🙏 Acknowledgments

- **Mempool.space**: For excellent Bitcoin API services
- **Waveshare/Pimoroni**: For e-paper display hardware and libraries
- **Bitcoin community**: For inspiration and feedback


*Made with ❤️ for the Bitcoin community*
