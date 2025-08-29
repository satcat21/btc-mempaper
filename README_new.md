# 🚀 BTC Mempaper - Bitcoin Dashboard

**A comprehensive, secure Bitcoin dashboard with web interface, real-time updates, and e-Paper display support.**

Mempaper is a modern Bitcoin dashboard that combines live blockchain data, customizable information blocks, social media integration, and beautiful visual presentation in a self-hosted web application. Perfect for Bitcoin enthusiasts who want a comprehensive monitoring solution with optional e-Paper hardware display.

---

## ✨ Features

### 🖥️ **Web Dashboard**
- **Real-time Bitcoin data** with WebSocket updates on new blocks
- **Responsive web interface** accessible from any device
- **Admin panel** with comprehensive configuration management
- **Secure authentication** with Argon2id password hashing
- **Rate limiting protection** against unauthorized access

### 📊 **Bitcoin Integration**
- **Live blockchain data** from local mempool instance
- **Current block height and hash** display
- **Real-time block notifications** via WebSocket connection
- **Comprehensive API integration** for accurate Bitcoin data
- **Fee estimation** with color-coded block height display

### 💰 **Information Blocks**
- **BTC Price Block**: Current Bitcoin price and "Moscow time" (sats per dollar)
- **Bitaxe Monitoring**: Hashrate aggregation and valid blocks tracking
- **Wallet Balances**: Multi-address balance tracking with fiat conversion
- **Configurable display**: Show/hide blocks based on space and preference
- **Multi-currency support**: USD, EUR, GBP, CAD, CHF, AUD, JPY

### 🐦 **Social Media Integration**
- **Twitter/X integration** with visual tweet screenshots
- **Image tweet fetching** from configured hashtags and users
- **Beautiful tweet rendering** with profile pictures and media
- **Smart fallback** to memes when no tweets available

### 🎨 **Visual Content & Design**
- **Meme gallery** with web-based upload interface
- **Multi-language support**: English, German, Spanish, French
- **Bitcoin holidays** and special event displays
- **High-quality image rendering** with proper typography
- **Customizable colors** for all interface elements
- **Dual display optimization** (web vs e-ink)

### 🖼️ **E-Paper Display Support**
- **60+ e-Paper displays** supported via omni-epd library
- **Automatic image sizing** for different display dimensions
- **Hardware integration** for Raspberry Pi and similar devices
- **Display-less mode** for web-only operation
- **Color optimization** for e-ink displays

### ⚙️ **Configuration**
- **Web-based settings** with intuitive categorized interface
- **Live configuration updates** without restart
- **Secure file uploads** for meme management
- **Comprehensive device support** with easy setup

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

The application uses a comprehensive configuration system organized into logical sections:

### 📋 **Configuration Sections**

#### **General Settings**
- **Language**: Multi-language interface (EN, DE, ES, FR)
- **Authentication**: Secure admin credentials with Argon2id encryption
- **Security**: Session timeout, rate limiting, backup settings
- **Display behavior**: Holiday display options, info block forcing

#### **Colors & Design**
- **Fonts**: Custom font selection for display rendering
- **Date colors**: Normal and holiday date color schemes
- **Holiday colors**: Title and description color customization
- **Info block colors**: Customizable colors for all information blocks
- **Layout**: Block height area configuration

#### **E-Ink Display**
- **Hardware connection**: Enable/disable physical display
- **Display type**: 60+ supported e-Paper models
- **Orientation**: Portrait or landscape mode
- **Dimensions**: Custom width and height settings

#### **Mempool Connection**
- **Server settings**: IP address and ports for mempool instance
- **API endpoints**: REST and WebSocket configuration
- **Fee parameters**: Block height color calculation settings

#### **Bitaxe Statistics**
- **Miner monitoring**: Multiple Bitaxe miner IP addresses
- **Hashrate tracking**: Aggregate hashrate display
- **Block rewards**: Address monitoring for mining payouts

#### **Price Statistics**
- **Currency selection**: Multiple fiat currency support
- **Price display**: Current BTC price and Moscow time
- **Update frequency**: Real-time price updates

#### **Wallet Monitoring**
- **Address tracking**: Bitcoin addresses and XPUB monitoring
- **Balance display**: BTC or satoshi units
- **Fiat conversion**: Optional fiat value display
- **Deduplication**: Smart handling of XPUB vs individual addresses

#### **Social Media (Twitter/X)**
- **API integration**: Twitter Bearer token configuration
- **Content filtering**: Hashtags and users to monitor
- **Tweet display**: Image tweet rendering with fallback to memes

### 🌐 **Web Configuration Interface**

Access the configuration interface at `/admin` after logging in:

1. **Organized sections** with clear navigation
2. **Real-time validation** of settings
3. **Color pickers** with preview functionality
4. **Help text** for each configuration option
5. **Backup and restore** functionality

---

## 🔒 Security Features

### 🛡️ **Password Security**
- **Argon2id encryption**: Military-grade password hashing
- **Memory Cost**: 64 MB protection against GPU attacks
- **Salt protection**: Unique 16-byte salt per password prevents rainbow table attacks
- **GPU resistance**: High memory usage makes specialized attacks expensive
- **Automatic migration**: Seamless upgrade from cleartext passwords

### 🚪 **Access Control**
- **Session management**: Configurable timeout and persistent sessions
- **Rate limiting**: Protection against brute force attacks
- **Secure authentication**: Modern authentication patterns
- **Admin-only access**: Configuration restricted to authenticated admins

### 🔧 **Operational Security**
- **Configuration backups**: Automatic backup before changes
- **File validation**: Secure file upload with type checking
- **Error handling**: Graceful degradation without exposing internals
- **Logging**: Comprehensive activity logging

---

## 🎨 Color System

### 🌈 **Dual Display Optimization**
The color system automatically optimizes colors for different display types:

- **Web displays**: Rich, nuanced colors with smooth gradients
- **E-ink displays**: High contrast colors optimized for e-paper rendering

### 🎨 **Available Colors**

#### **Greens**
- `forest_green`, `lime_green`, `dark_green`

#### **Reds** 
- `fire_brick`, `crimson`, `dark_red`

#### **Oranges/Browns**
- `peru`, `chocolate`, `saddle_brown`

#### **Blues**
- `steel_blue`, `royal_blue`, `navy_blue`

#### **Yellows/Golds**
- `goldenrod`, `gold`, `dark_goldenrod`

#### **Neutrals**
- `black`, `white`, `gray`

### 🔧 **Custom Colors**
You can also specify custom RGB colors: `[255, 128, 0]`

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
- **Local mempool server**: Recommended for best performance
- **Public APIs**: Fallback to mempool.space
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
├── mempaper_app.py           # Main Flask application
├── config_manager.py         # Configuration management
├── image_renderer.py         # Display rendering engine
├── auth_manager.py           # Authentication system
├── secure_password_manager.py # Password security
├── *_api.py                  # API integration modules
├── static/                   # Web interface assets
├── templates/                # HTML templates
├── fonts/                    # Typography files
└── README.md                # This documentation
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

This project is licensed under the MIT License. See the LICENSE file for details.

---

## 🙏 Acknowledgments

- **Mempool.space**: For excellent Bitcoin API services
- **Waveshare/Pimoroni**: For e-paper display hardware and libraries
- **Bitcoin community**: For inspiration and feedback
- **Contributors**: Everyone who has contributed to this project

---

## 🔮 Future Enhancements

- **Mobile app**: Companion mobile application
- **More exchanges**: Additional price data sources
- **Advanced charting**: Historical price and hashrate charts  
- **Plugin system**: Extensible architecture for custom blocks
- **Multi-node**: Support for multiple Bitcoin nodes
- **Lightning**: Lightning Network integration

---

*Made with ❤️ for the Bitcoin community*
