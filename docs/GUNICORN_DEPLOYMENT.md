# Gunicorn Production Deployment

This document explains how to deploy Mempaper with Gunicorn for production use.

## Quick Start

### 1. Install Dependencies
```bash
# Activate virtual environment
source .venv/bin/activate

# Install Gunicorn and eventlet (if not already installed)
pip install -r requirements.txt
```

### 2. Manual Start (Testing)
```bash
# Make startup script executable
chmod +x start-gunicorn.sh

# Start with the convenience script
./start-gunicorn.sh

# Or start directly with gunicorn
gunicorn --config gunicorn.conf.py wsgi:application
```

### 3. Systemd Service (Production)
```bash
# Copy the service file
sudo cp mempaper.service /etc/systemd/system/

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable mempaper.service

# Start the service
sudo systemctl start mempaper.service

# Check status
sudo systemctl status mempaper.service

# View logs
sudo journalctl -u mempaper.service -f
```

## Configuration

### Gunicorn Settings (`gunicorn.conf.py`)
- **Workers**: Auto-calculated based on CPU cores
- **Worker Class**: `eventlet` for SocketIO support
- **Bind**: `0.0.0.0:5000` (all interfaces)
- **Timeout**: 30 seconds
- **Logging**: Info level to stdout/stderr

### Key Features
- **Auto-restart**: Workers restart after 1000 requests
- **Process naming**: Shows as "mempaper" in process list
- **Preload app**: Better performance and memory usage
- **Security**: Request limits and validation

## Monitoring

### Check Service Status
```bash
sudo systemctl status mempaper.service
```

### View Real-time Logs
```bash
sudo journalctl -u mempaper.service -f
```

### Monitor Resource Usage
```bash
# CPU and memory usage
htop -p $(pgrep -f mempaper)

# Network connections
sudo netstat -tlnp | grep :5000
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   sudo lsof -i :5000
   sudo kill -9 <PID>
   ```

2. **Permission Errors**
   ```bash
   # Check file permissions
   ls -la /home/pi/btc-mempaper/
   
   # Fix ownership if needed
   sudo chown -R pi:pi /home/pi/btc-mempaper/
   ```

3. **Virtual Environment Issues**
   ```bash
   # Recreate virtual environment
   rm -rf .venv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

### Performance Tuning

1. **Adjust Worker Count**
   Edit `gunicorn.conf.py`:
   ```python
   workers = 4  # Fixed number instead of auto-calculated
   ```

2. **Memory Limits**
   ```python
   max_requests = 500  # Restart workers more frequently
   max_requests_jitter = 25
   ```

3. **Connection Limits**
   ```python
   worker_connections = 500  # Reduce for limited memory
   ```

## SSL/HTTPS Setup

To enable HTTPS, edit `gunicorn.conf.py`:

```python
# Uncomment and configure these lines
keyfile = "/path/to/your/private.key"
certfile = "/path/to/your/certificate.crt"
```

Or use a reverse proxy like Nginx for SSL termination.

## Advanced Configuration

### Environment Variables
Set in the systemd service file or export before starting:

```bash
export FLASK_ENV=production
export PYTHONUNBUFFERED=1
export API_RATE_LIMIT_DELAY=3
```

### Logging Configuration
Gunicorn logs are sent to systemd journal. To save to files:

```python
# In gunicorn.conf.py
accesslog = "/var/log/mempaper/access.log"
errorlog = "/var/log/mempaper/error.log"
```

### Load Balancing
For multiple instances, use a load balancer like Nginx:

```nginx
upstream mempaper {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://mempaper;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
