#!/bin/bash
# Update Production Environment Script
# This script updates the production environment to use gevent instead of eventlet

echo "🔄 Updating Mempaper production environment..."

# Stop the service
echo "🛑 Stopping mempaper service..."
sudo systemctl stop mempaper.service

# Update dependencies
echo "📦 Installing gevent dependencies..."
cd /home/pi/btc-mempaper
source .venv/bin/activate

# Remove eventlet and install gevent
pip uninstall -y eventlet
pip install gevent==24.2.1 gevent-websocket==0.10.1

# Update all dependencies
pip install -r requirements.txt

echo "✅ Dependencies updated"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

# Start the service
echo "🚀 Starting mempaper service..."
sudo systemctl start mempaper.service

# Check status
echo "📊 Service status:"
sudo systemctl status mempaper.service --no-pager -l

# Show recent logs
echo "📋 Recent logs:"
sudo journalctl -u mempaper.service --since "1 minute ago" --no-pager

echo "✅ Production environment update complete!"
echo "🌐 Mempaper should now be running with gevent instead of eventlet"
