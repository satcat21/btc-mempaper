#!/bin/bash
"""
Quick Pi Legacy Data Fix

This script quickly removes legacy block monitoring data on Raspberry Pi
and restarts the service to apply changes.
"""

echo "🧹 Quick fix for legacy block monitoring data on Raspberry Pi"
echo "==============================================================="

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run with sudo for service management"
    echo "Usage: sudo bash pi_quick_fix.sh"
    exit 1
fi

# Navigate to mempaper directory
cd /home/pi/btc-mempaper || {
    echo "❌ Cannot find /home/pi/btc-mempaper directory"
    echo "Please adjust the path to your mempaper installation"
    exit 1
}

echo "📍 Current directory: $(pwd)"

# Stop the service
echo "🛑 Stopping mempaper service..."
systemctl stop mempaper

# Create backup directory
echo "💾 Creating backup of cache files..."
mkdir -p cache_backup_$(date +%Y%m%d_%H%M%S)
cp cache/*.json cache_backup_$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || true
cp *.json cache_backup_$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || true

# Remove legacy cache files that might contain old addresses
echo "🗑️ Removing legacy cache files..."
rm -f valid_blocks_count.json
rm -f cache/block_reward_cache.json
rm -f cache/cache.json
rm -f cache/cache.secure.json
rm -f cache/async_wallet_address_cache.json
rm -f cache/async_wallet_address_cache.secure.json

# Keep display cache but remove others
echo "✅ Kept display cache files, removed block monitoring cache"

# Start the service
echo "🚀 Starting mempaper service..."
systemctl start mempaper

# Wait a moment and check status
sleep 3
echo "📊 Service status:"
systemctl is-active mempaper

echo ""
echo "✅ Quick fix completed!"
echo "🔍 Monitor the logs to verify the legacy address is gone:"
echo "   sudo journalctl -f -u mempaper"
echo ""
echo "📋 The service will now:"
echo "   • Create fresh cache files"
echo "   • Only monitor addresses currently in the config"
echo "   • No longer show the legacy 1BM1sA...sFC2Qc address"
