#!/bin/bash
# Mempaper Diagnostic Script
# Quick diagnostic to check for common issues

echo "🔍 Mempaper Service Diagnostic"
echo "============================="

# Check if we're on Pi Zero
if [ -f /proc/device-tree/model ]; then
    echo "📋 Hardware: $(cat /proc/device-tree/model)"
fi

# Check Python environment
echo ""
echo "🐍 Python Environment:"
cd /home/pi/btc-mempaper
source .venv/bin/activate
echo "Python: $(which python)"
echo "Python version: $(python --version)"

# Check critical imports
echo ""
echo "📦 Critical Package Check:"
for pkg in flask gunicorn gevent; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print($pkg.__version__)" 2>/dev/null)
        echo "✅ $pkg: $version"
    else
        echo "❌ $pkg: NOT FOUND"
    fi
done

# Check if gevent-websocket is available
if python -c "import gevent_websocket" 2>/dev/null; then
    echo "✅ gevent-websocket: available"
else
    echo "❌ gevent-websocket: NOT FOUND"
fi

# Test mempaper_app import
echo ""
echo "🧪 App Import Test:"
if python -c "from mempaper_app import MempaperApp" 2>/dev/null; then
    echo "✅ mempaper_app imports successfully"
else
    echo "❌ mempaper_app import failed:"
    python -c "from mempaper_app import MempaperApp" 2>&1 | head -5
fi

# Check service status
echo ""
echo "🚀 Service Status:"
systemctl is-active mempaper.service
systemctl is-enabled mempaper.service

# Check port
echo ""
echo "🌐 Port Check:"
if netstat -tlnp 2>/dev/null | grep -q :5000; then
    echo "✅ Port 5000 is listening"
    netstat -tlnp | grep :5000
else
    echo "❌ Port 5000 is not listening"
fi

# Memory usage
echo ""
echo "💾 Memory Usage:"
free -h

# Recent logs
echo ""
echo "📋 Recent Service Logs (last 5 lines):"
sudo journalctl -u mempaper.service -n 5 --no-pager

echo ""
echo "🎯 Diagnostic complete!"
