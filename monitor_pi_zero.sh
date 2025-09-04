#!/bin/bash
# Raspberry Pi Zero WH Monitoring Script
# Monitor system resources and service health

echo "🍓 Raspberry Pi Zero WH - Mempaper System Monitor"
echo "=================================================="

# Hardware info
if [ -f /proc/device-tree/model ]; then
    echo "📋 Hardware: $(cat /proc/device-tree/model)"
fi

echo "🌡️  CPU Temperature: $(vcgencmd measure_temp | cut -d= -f2)"
echo "⚡ CPU Frequency: $(vcgencmd measure_clock arm | cut -d= -f2 | awk '{print $1/1000000 " MHz"}')"

# Memory usage
echo ""
echo "💾 Memory Usage:"
free -h

# Swap usage
echo ""
echo "💿 Swap Usage:"
swapon --show

# Service status
echo ""
echo "🚀 Mempaper Service Status:"
sudo systemctl status mempaper.service --no-pager -l | head -10

# Process info
echo ""
echo "📊 Mempaper Processes:"
ps aux | grep -E "(gunicorn|mempaper)" | grep -v grep

# Disk usage (SD card)
echo ""
echo "💾 SD Card Usage:"
df -h / | tail -1

# Network connections
echo ""
echo "🌐 Network Connections:"
netstat -tlnp | grep :5000

# Recent logs (last 5 lines)
echo ""
echo "📋 Recent Logs (last 5 lines):"
sudo journalctl -u mempaper.service -n 5 --no-pager

# Check for common issues
echo ""
echo "🔍 Health Checks:"

# Check memory pressure
MEM_AVAILABLE=$(free | awk '/^Mem:/{print $7}')
MEM_TOTAL=$(free | awk '/^Mem:/{print $2}')
MEM_PERCENT=$((100 - (MEM_AVAILABLE * 100 / MEM_TOTAL)))

if [ $MEM_PERCENT -gt 90 ]; then
    echo "❌ High memory usage: ${MEM_PERCENT}%"
elif [ $MEM_PERCENT -gt 75 ]; then
    echo "⚠️  Moderate memory usage: ${MEM_PERCENT}%"
else
    echo "✅ Memory usage OK: ${MEM_PERCENT}%"
fi

# Check CPU temperature
TEMP=$(vcgencmd measure_temp | cut -d= -f2 | cut -d\' -f1)
if (( $(echo "$TEMP > 70" | bc -l) )); then
    echo "❌ High CPU temperature: ${TEMP}°C"
elif (( $(echo "$TEMP > 60" | bc -l) )); then
    echo "⚠️  Warm CPU temperature: ${TEMP}°C"  
else
    echo "✅ CPU temperature OK: ${TEMP}°C"
fi

# Check service health
if systemctl is-active --quiet mempaper.service; then
    echo "✅ Mempaper service is running"
else
    echo "❌ Mempaper service is not running"
fi

# Check port 5000
if netstat -tlnp | grep -q :5000; then
    echo "✅ Port 5000 is listening"
else
    echo "❌ Port 5000 is not listening"
fi

echo ""
echo "💡 Tip: Run this script periodically to monitor Pi Zero health"
echo "💡 For continuous monitoring: watch -n 10 './monitor_pi_zero.sh'"
