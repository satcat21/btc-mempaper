#!/bin/bash
# Emergency Fix for Mempaper Service - Install gevent
# Run this on your Raspberry Pi to fix the gevent import error

echo "🚨 Emergency fix: Installing gevent dependencies..."

# Stop the failing service first
sudo systemctl stop mempaper.service

# Navigate to project directory
cd /home/pi/btc-mempaper

# Activate virtual environment
source .venv/bin/activate

# Install gevent and dependencies
echo "📦 Installing gevent..."
pip install gevent==24.2.1 gevent-websocket==0.10.1

# Verify installation
echo "✅ Verifying gevent installation..."
python -c "import gevent; print(f'gevent version: {gevent.__version__}')"

# Update gunicorn config to use gevent now that it's installed
echo "⚙️ Updating gunicorn config to use gevent..."
sed -i 's/worker_class = "sync"/worker_class = "gevent"/' gunicorn.conf.py

echo "🔄 Restarting mempaper service..."
sudo systemctl daemon-reload
sudo systemctl start mempaper.service

# Check status
echo "📊 Service status:"
sudo systemctl status mempaper.service --no-pager -l

echo "📋 Recent logs:"
sudo journalctl -u mempaper.service --since "30 seconds ago" --no-pager

echo "✅ Emergency fix complete!"
echo "🌐 Mempaper should now be running with gevent"
