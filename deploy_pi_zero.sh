#!/bin/bash
# Raspberry Pi Zero WH Deployment Script
# Optimized for single-core ARM CPU with 512MB RAM

echo "🍓 Deploying Mempaper on Raspberry Pi Zero WH..."

# Check if we're actually on a Pi Zero
if [ -f /proc/device-tree/model ]; then
    MODEL=$(cat /proc/device-tree/model)
    echo "📋 Detected hardware: $MODEL"
    if [[ $MODEL != *"Zero"* ]]; then
        echo "⚠️  Warning: This script is optimized for Pi Zero WH"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# Stop the service
echo "🛑 Stopping mempaper service..."
sudo systemctl stop mempaper.service

# Show current memory usage
echo "📊 Current memory usage:"
free -h

# Update dependencies for Pi Zero
echo "📦 Installing Pi Zero optimized dependencies..."
cd /home/pi/btc-mempaper
source .venv/bin/activate

# Remove eventlet and install optimized gevent
pip uninstall -y eventlet
pip install gevent==24.11.1 gevent-websocket==0.10.1

# Install all dependencies
pip install -r requirements.txt

# Configure swap if needed (Pi Zero needs more swap)
SWAP_SIZE=$(swapon --show=SIZE --noheadings | head -1 | tr -d 'M')
if [ -z "$SWAP_SIZE" ] || [ "$SWAP_SIZE" -lt 512 ]; then
    echo "💾 Configuring swap for Pi Zero (512MB+ recommended)..."
    sudo dphys-swapfile swapoff
    sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=512/' /etc/dphys-swapfile
    sudo dphys-swapfile setup
    sudo dphys-swapfile swapon
    echo "✅ Swap configured to 512MB"
fi

# Optimize systemd service for Pi Zero
echo "⚙️ Optimizing systemd service for Pi Zero..."
sudo tee /etc/systemd/system/mempaper.service > /dev/null << 'EOF'
[Unit]
Description=Mempaper Bitcoin Dashboard (Pi Zero Optimized)
Documentation=https://github.com/satcat21/btc-mempaper
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/bin/sh -c ". /home/pi/btc-mempaper/.venv/bin/activate && gunicorn --config /home/pi/btc-mempaper/gunicorn.conf.py wsgi:application"
WorkingDirectory=/home/pi/btc-mempaper
Restart=always
RestartSec=10
User=pi
Group=pi
Environment="PATH=/home/pi/btc-mempaper/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/home/pi/btc-mempaper"
Environment="PYTHONUNBUFFERED=1"
Environment="FLASK_ENV=production"
Environment="API_RATE_LIMIT_DELAY=5"
Environment="MAX_REQUESTS_PER_MINUTE=5"
Environment="CACHE_DURATION=600"
Environment="REQUEST_TIMEOUT=60"

# Pi Zero specific optimizations
MemoryHigh=200M
MemoryMax=250M
CPUQuota=80%
Nice=5

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Systemd service optimized for Pi Zero"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Start the service
echo "🚀 Starting mempaper service..."
sudo systemctl start mempaper.service

# Enable autostart
sudo systemctl enable mempaper.service

# Wait a moment for startup
sleep 5

# Check status
echo "📊 Service status:"
sudo systemctl status mempaper.service --no-pager -l

# Show memory usage after startup
echo "📊 Memory usage after startup:"
free -h

# Show recent logs
echo "📋 Recent logs:"
sudo journalctl -u mempaper.service --since "1 minute ago" --no-pager

echo "✅ Pi Zero deployment complete!"
echo "🌐 Mempaper should now be running optimized for Pi Zero WH"
echo "💡 Monitor memory usage with: watch -n 2 'free -h'"