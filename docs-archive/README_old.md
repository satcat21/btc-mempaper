# 🚀 Mempaper - Bitcoin Dashboard

**A modern, full-featured Bitcoin dashboard with web interface, real-time updates, and e-Paper display support.**

Mempaper combines live Bitcoin blockchain data, social media integration, and beautiful visual presentation in a self-hosted web application. Perfect for Bitcoin enthusiasts who want a comprehensive dashboard with optional e-Paper hardware display.

---

## ✨ Features

### �️ **Web Dashboard**
- **Real-time updates** via WebSockets when new blocks are mined
- **Responsive web interface** accessible from any device
- **Admin panel** with comprehensive configuration management
- **Secure authentication** with rate limiting protection

### 📊 **Bitcoin Integration**
- **Live block data** from local mempool instance
- **Current block height and hash** display
- **Real-time block notifications** via WebSocket connection
- **Mempool API integration** for accurate blockchain data

### 🐦 **Social Media**
- **Twitter/X integration** with visual tweet screenshots
- **Image tweet fetching** from configured hashtags and users
- **Beautiful tweet rendering** with profile pictures and media
- **Smart fallback** to memes when no tweets available

### 🎨 **Visual Content**
- **Meme gallery** with web-based upload interface
- **Multi-language support**: English, German, Spanish, French
- **Bitcoin holidays** and special event displays
- **High-quality image rendering** with proper typography

### �️ **E-Paper Display Support**
- **60+ e-Paper displays** supported via omni-epd library
- **Automatic image sizing** for different display dimensions
- **Hardware integration** for Raspberry Pi and similar devices
- **Display-less mode** for web-only operation

### ⚙️ **Configuration**
- **Web-based settings** with intuitive interface
- **Live configuration updates** without restart
- **Secure file uploads** for meme management
- **Comprehensive device support** with easy setup

---

## � Quick Start

### 1. **Clone Repository**
```bash
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
```

### 2. **Install Dependencies**
```bash
# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 3. **Configure Application**
```bash
# Copy example configuration
cp config.json.example config.json

# Edit configuration (or use web interface after first start)
nano config.json
```

### 4. **Start Application**
```bash
python mempaper_app.py
```

### 5. **Access Dashboard**
Open your browser and navigate to:
- **Dashboard**: `http://localhost:5000`
- **Settings**: `http://localhost:5000/config` (requires authentication)

---

## ⚙️ Configuration

### Web Interface
The easiest way to configure Mempaper is through the web interface:

1. Start the application: `python mempaper_app.py`
2. Navigate to `http://localhost:5000/config`
3. Log in with your admin credentials
4. Configure all settings through the intuitive interface

### Configuration File
Alternatively, edit `config.json` directly:

```json
{
  "language": "en",
  "orientation": "vertical",
  "width": 800,
  "height": 480,
  "e-ink-display-connected": true,
  "omni_device_name": "waveshare_epd7in5_V2",
  
  "mempool_ip": "127.0.0.1",
  "mempool_rest_port": "8999",
  "mempool_ws_port": "8999",
  
  "admin_username": "admin",
  "admin_password": "secure_password_here",
  "session_timeout": 3600,
  "rate_limit_requests": 5,
  "rate_limit_window": 300
}
```

### Key Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `e-ink-display-connected` | Enable/disable e-Paper display | `true` |
| `omni_device_name` | E-Paper display model | `"mock"` |
| `mempool_ip` | Mempool server IP address | `"127.0.0.1"` |
| `admin_username` | Admin panel username | `"admin"` |
| `language` | Interface language (en/de/es/fr) | `"en"` |

---

## �️ Hardware Setup

### Raspberry Pi + E-Paper Display

1. **Install system dependencies**:
```bash
sudo apt update
sudo apt install python3-pip python3-venv git
```

2. **Enable SPI interface**:
```bash
sudo raspi-config
# Interface Options → SPI → Enable
```

3. **Install application**:
```bash
git clone https://github.com/satcat21/btc-mempaper.git
cd btc-mempaper
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

4. **Configure display**:
   - Use web interface to select your exact display model
   - Test display with: `python configure_display.py`

### Supported Displays
Mempaper supports 60+ e-Paper displays via the omni-epd library:

- **Waveshare**: 2.13", 2.9", 4.2", 5.83", 7.5", 10.3", 13.3"
- **Pimoroni Inky**: Impression, pHAT, wHAT series  
- **Adafruit**: Various e-ink displays
- **And many more...**

### Display-less Mode
Run without hardware for web-only dashboard:
```json
{
  "e-ink-display-connected": false
}
```

---

## �️ Security Features

### Authentication
- **Session-based authentication** for admin panel
- **Password hashing** with secure algorithms
- **Configurable session timeout**

### Rate Limiting
- **IP-based rate limiting** prevents brute force attacks
- **Configurable limits** for failed login attempts
- **Automatic IP blocking** for suspicious activity

### File Upload Security
- **Secure filename handling** prevents directory traversal
- **File type validation** for image uploads
- **Size limits** and format restrictions

---

## 🔧 Development

### Project Structure
```
btc-mempaper/
├── mempaper_app.py          # Main application
├── config_manager.py        # Configuration handling
├── auth_manager.py          # Authentication system  
├── image_renderer.py        # Image generation
├── mempool_api.py          # Bitcoin blockchain API
├── websocket_client.py     # Real-time updates
├── translations.py         # Multi-language support
├── btc_holidays.py         # Bitcoin holidays
├── config.json             # Configuration file
├── requirements.txt        # Python dependencies
├── static/                 # Web assets
│   ├── favicon.png
│   ├── socket.io.min.js
│   └── memes/             # Uploaded memes
├── fonts/                 # Typography
│   ├── Roboto-Regular.ttf
│   └── Roboto-Bold.ttf
└── display/               # E-paper utilities
    ├── prepare_image.py
    ├── show_image.py
    └── update_piframe.sh
```

### Running Tests
```bash
# Test display configuration
python configure_display.py

# Test individual components
python -c "from image_renderer import ImageRenderer; print('✓ Image renderer working')"
```

### Service Installation
For production deployment, install as a system service:

```bash
# Copy service file
sudo cp mempaper.service /etc/systemd/system/

# Edit service file with your paths
sudo nano /etc/systemd/system/mempaper.service

# Enable and start service
sudo systemctl enable mempaper
sudo systemctl start mempaper
```

---

## 🌐 API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/` | GET | Main dashboard |
| `/image` | GET | Generate current dashboard image |
| `/config` | GET | Configuration page |
| `/api/config` | GET/POST | Configuration API |
| `/api/login` | POST | Authentication |
| `/api/upload-meme` | POST | Upload meme images |
| `/api/memes` | GET | List uploaded memes |

### WebSocket Events

| Event | Description |
|-------|-------------|
| `connect` | Client connected |
| `disconnect` | Client disconnected |
| `new_image` | New dashboard image available |

---

## �️ Troubleshooting

### Common Issues

**Q: "Module not found" errors**
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**Q: E-Paper display not working**
```bash
# Check SPI is enabled (Raspberry Pi)
lsmod | grep spi

# Test display manually
python configure_display.py
```

**Q: Twitter integration not working**
- Verify Bearer Token is correct
- Check rate limits haven't been exceeded
- Ensure topics/users are configured

**Q: WebSocket connection fails**
- Check mempool server is running
- Verify mempool IP and ports in config
- Test connection: `curl https://your-mempool-ip:4081/api/v1/blocks/tip/height`

### Debug Mode
Run with debug output:
```bash
python mempaper_app.py --debug
```

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and test thoroughly
4. **Commit changes**: `git commit -m "Add amazing feature"`
5. **Push to branch**: `git push origin feature/amazing-feature`
6. **Open a Pull Request**

### Development Guidelines
- Follow PEP 8 style guidelines
- Add comments for complex logic
- Test new features thoroughly
- Update documentation as needed

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🎯 Roadmap

### Planned Features
- [ ] **Multi-device support** - Run multiple displays from one instance
- [ ] **Custom themes** - User-configurable color schemes and layouts
- [ ] **Plugin system** - Add custom data sources and widgets
- [ ] **Mobile app** - Companion app for remote control
- [ ] **Data export** - Historical data logging and CSV export
- [ ] **Alerting system** - Notifications for significant events

### Community Requests
- [ ] **Lightning Network** integration
- [ ] **Nostr** social protocol support  
- [ ] **Price data** from exchanges
- [ ] **Mining pool** statistics
- [ ] **Hardware wallet** integration

---

## � Acknowledgments

- **Bitcoin Core** developers for the blockchain
- **Mempool.space** for excellent API design
- **omni-epd** project for e-Paper display support
- **Twitter API** for social media integration
- **Flask** and **SocketIO** for web framework
- **PIL/Pillow** for image processing

---

**Made with ❤️ for the Bitcoin community**

*"Fix the money, fix the world."*
