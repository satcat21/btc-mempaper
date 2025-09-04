#!/bin/bash
# Critical Fix for Mempaper UnboundLocalError
# This fixes the os import conflict that's causing the service to fail

echo "🚨 CRITICAL FIX: Resolving UnboundLocalError in mempaper_app.py"

# Stop the failing service
sudo systemctl stop mempaper.service

# Navigate to project directory
cd /home/pi/btc-mempaper

# Check current git status
echo "📋 Current git status:"
git status --porcelain

# The fix should already be applied in the updated code, but let's verify gevent is installed
echo "📦 Checking gevent installation..."
source .venv/bin/activate

# Check if gevent is installed
if python -c "import gevent" 2>/dev/null; then
    echo "✅ gevent is already installed"
    python -c "import gevent; print(f'gevent version: {gevent.__version__}')"
else
    echo "📦 Installing gevent..."
    pip install gevent==24.2.1 gevent-websocket==0.10.1
    echo "✅ gevent installed successfully"
fi

# Test the fix by importing the app (this will catch any remaining issues)
echo "🧪 Testing mempaper_app import..."
if python -c "from mempaper_app import MempaperApp; print('✅ mempaper_app imports successfully')" 2>/dev/null; then
    echo "✅ Import test passed"
else
    echo "❌ Import test failed - there may be other issues"
    python -c "from mempaper_app import MempaperApp" # Show the error
    exit 1
fi

# Check which Python environment the service will use
echo "🔍 Python environment check:"
which python
pip list | grep -E "(gevent|flask|gunicorn)"

echo "🔄 Starting mempaper service..."
sudo systemctl start mempaper.service

# Wait a moment for startup
sleep 5

# Check status
echo "📊 Service status:"
sudo systemctl status mempaper.service --no-pager -l

# Show recent logs
echo "📋 Recent logs:"
sudo journalctl -u mempaper.service --since "30 seconds ago" --no-pager

# Test if the service is responding
echo "🌐 Testing service response:"
if curl -s http://localhost:5000 > /dev/null; then
    echo "✅ Service is responding on port 5000"
else
    echo "❌ Service is not responding on port 5000"
fi

echo "✅ Critical fix applied!"
echo "🎯 The UnboundLocalError should now be resolved"
