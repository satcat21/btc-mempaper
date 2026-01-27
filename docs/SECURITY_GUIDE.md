# 🔒 Configuration Security Guide for Raspberry Pi

## 🎯 **Overview**

This guide provides lightweight but effective protection for sensitive Bitcoin data (XPUBs, wallet addresses, API keys) on Raspberry Pi Zero W. The solution uses industry-standard encryption while maintaining optimal performance for embedded devices.

## 🔐 **Security Implementation**

### **Encryption Method:**
- **Algorithm**: AES-128 via Fernet (cryptography library)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 100,000 iterations
- **Device Binding**: Hardware fingerprint from CPU serial + MAC address
- **File Separation**: Public config (plain) + sensitive data (encrypted)

### **What Gets Encrypted:**
```json
{
  "wallet_balance_addresses": ["bc1q..."],
  "wallet_balance_addresses_with_comments": [...],
  "block_reward_addresses": ["bc1q..."],
  "admin_password_hash": "...",
  "secret_key": "..."
}
```

### **What Stays Public:**
```json
{
  "language": "en",
  "display_orientation": "vertical",
  "mempool_host": "192.168.1.100",
  "btc_price_currency": "USD"
}
```

## 🚀 **Quick Setup**

### **1. Install Dependencies**

If you installed from `requirements.txt`, these are already installed:
```bash
# Already included in requirements.txt
# cryptography==45.0.6
# psutil==6.1.0
```

If installing manually or updating:
```bash
pip install cryptography psutil
```

### **2. Enable Secure Configuration**
```bash
# Test encryption functionality
python secure_config_cli.py test

# Check current security status
python secure_config_cli.py status

# Migrate existing config.json to encrypted format
python secure_config_cli.py migrate
```

### **3. Verify Security**
```bash
# Check file permissions
python secure_config_cli.py permissions

# Create encrypted backup
python secure_config_cli.py backup
```

## 📁 **File Structure After Setup**

```
├── config.json              # Public configuration (readable)
├── config.secure.json       # Encrypted sensitive data (600 permissions)
├── .config_key              # Salt for key derivation (600 permissions)
├── config.json.backup       # Backup of original config
└── config_backup_*.secure.json  # Encrypted backups
```

## 🔧 **Automatic Integration**

The system automatically integrates with existing code:

```python
# Your existing code continues to work unchanged
from config_manager import ConfigManager

config_manager = ConfigManager()  # Automatically uses encryption if available
config = config_manager.config   # Transparent decryption

# Access sensitive data normally
wallet_addresses = config.get("wallet_balance_addresses", [])
admin_hash = config.get("admin_password_hash", "")
```

## 🛡️ **Security Features**

### **Device Binding**
- **CPU Serial**: Uses Raspberry Pi's unique hardware serial number
- **MAC Address**: Network interface hardware identifier  
- **System Info**: Platform and user ID for additional entropy
- **Result**: Config encrypted to specific device, won't decrypt elsewhere

### **Key Management**
- **No Plain Keys**: Actual encryption key never stored on disk
- **Salt Storage**: Only PBKDF2 salt stored in `.config_key`
- **Key Derivation**: Encryption key regenerated from device fingerprint each time
- **Hardware Security**: Bound to specific Raspberry Pi hardware

### **File Permissions**
```bash
-rw------- 1 pi pi  config.secure.json    # 600: Owner read/write only
-rw------- 1 pi pi  .config_key           # 600: Owner read/write only  
-rw-r--r-- 1 pi pi  config.json          # 644: Public config readable
```

## ⚡ **Performance Optimized for Pi Zero W**

### **Lightweight Encryption:**
- **Fast Algorithm**: AES-128 (faster than AES-256 on ARM)
- **Minimal Memory**: ~1MB additional RAM usage
- **Quick Operations**: Encrypt/decrypt in <100ms
- **Low CPU**: Optimized iteration count for ARM processor

### **Smart Caching:**
- **Device Fingerprint**: Cached to avoid repeated hardware queries
- **Encryption Key**: Derived once and reused during session
- **Minimal I/O**: Only reads encrypted file when config changes

## 🔍 **Security Status Monitoring**

### **Check Security Status:**
```bash
python secure_config_cli.py status
```

**Example Output:**
```
📊 Security Status Check

🔐 Encryption Status:
   Encryption enabled: ✅
   Key file exists: ✅  
   Public config exists: ✅
   Device fingerprint: a1b2c3d4e5f6...

📁 File Permissions:
   🔒 config.secure.json: 600 (Encrypted configuration)
   🔒 .config_key: 600 (Encryption key salt)
   📄 config.json: 644 (Public configuration)

✅ No security recommendations - configuration is secure!
```

## 🔄 **Migration Process**

### **Step-by-Step Migration:**

1. **Backup Current Config:**
   ```bash
   cp config.json config.json.original
   ```

2. **Test Migration:**
   ```bash
   python secure_config_cli.py test
   python secure_config_cli.py migrate
   ```

3. **Verify Application:**
   ```bash
   python mempaper_app.py  # Test that app still works
   ```

4. **Security Check:**
   ```bash
   python secure_config_cli.py status
   ```

5. **Clean Up (optional):**
   ```bash
   rm config.json.backup  # Remove backup if everything works
   ```

## 🆘 **Recovery & Troubleshooting**

### **If Decryption Fails:**

1. **Check Dependencies:**
   ```bash
   pip install cryptography psutil
   ```

2. **Verify Hardware:**
   ```bash
   # Check if CPU serial is readable
   cat /proc/cpuinfo | grep Serial
   ```

3. **Recovery from Backup:**
   ```bash
   # Restore from original
   cp config.json.original config.json
   
   # Or restore from encrypted backup
   python secure_config_cli.py decrypt
   ```

### **Emergency Access:**

If encryption fails, the system gracefully falls back to plain config:

```python
# ConfigManager automatically falls back
config_manager = ConfigManager(enable_secure_config=False)
```

## 🛡️ **Security Best Practices**

### **Recommended Setup:**
1. **Enable Encryption**: `python secure_config_cli.py migrate`
2. **Set Permissions**: `python secure_config_cli.py permissions`
3. **Regular Backups**: `python secure_config_cli.py backup`
4. **Monitor Status**: `python secure_config_cli.py status`

### **File System Security:**
```bash
# Set restrictive permissions on entire config directory
chmod 700 /home/pi/btc-mempaper/
chown -R pi:pi /home/pi/btc-mempaper/

# Secure SSH access (if using SSH)
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow 5000  # For web interface on local network only
```

### **Network Security:**
```bash
# Web interface only on local network
python mempaper_app.py --host 192.168.1.100  # Bind to local IP only

# Or use with firewall
sudo ufw allow from 192.168.1.0/24 to any port 5000
```

## 🔍 **Advanced Security Options**

### **Hardware Security Module (Future):**
For production deployments, consider:
- **TPM Integration**: Use Raspberry Pi's TPM chip if available
- **Hardware RNG**: Use `/dev/hwrng` for better entropy
- **Secure Boot**: Enable secure boot in Raspberry Pi firmware

### **Network Isolation:**
- **Air-Gapped Setup**: Use Pi without internet connection
- **VPN Only**: Access only through VPN tunnel
- **Local Network**: Restrict to local subnet only

## 📊 **Security Audit Checklist**

### **✅ Configuration Security:**
- [ ] Encryption enabled for sensitive data
- [ ] File permissions set to 600 for encrypted files
- [ ] Device fingerprinting working correctly
- [ ] Backup strategy implemented

### **✅ System Security:**
- [ ] SSH keys configured (disable password auth)
- [ ] Firewall enabled and configured
- [ ] System updates applied
- [ ] User accounts secured

### **✅ Application Security:**
- [ ] Admin password strong and unique
- [ ] Session timeout configured
- [ ] HTTPS enabled for remote access
- [ ] Rate limiting configured

This security implementation provides enterprise-grade protection for your Bitcoin data while maintaining the simplicity and performance needed for Raspberry Pi Zero W deployment.
