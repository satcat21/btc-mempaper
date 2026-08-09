#!/bin/bash
# Cache Reset Script for Raspberry Pi
# This script will reset all wallet address caches and force a fresh scan

echo "🔄 Resetting wallet address cache on Raspberry Pi..."
echo "=================================================="

# Change to the application directory
cd /home/pi/btc-mempaper || {
    echo "❌ Error: Could not change to /home/pi/btc-mempaper directory"
    echo "   Please run this script from the correct location or update the path"
    exit 1
}

echo "📁 Current directory: $(pwd)"
echo ""

# Function to safely remove files
remove_file() {
    local file="$1"
    if [ -f "$file" ]; then
        rm -f "$file"
        echo "✅ Deleted: $file"
    else
        echo "⚠️  Not found: $file"
    fi
}

# Function to safely remove directories
remove_directory() {
    local dir="$1"
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "✅ Deleted directory: $dir"
    else
        echo "⚠️  Not found: $dir"
    fi
}

echo "🗑️  Removing cache files..."

# Remove wallet address cache files
remove_file "cache/async_wallet_address_cache.sensitive.json"
remove_file "cache.json"
remove_file "wallet_address_cache.sensitive.json"
remove_file "wallet_address_cache.json"

# Remove optimized balance cache files
remove_file "optimized_balance_cache.json"
remove_file "optimized_balance_cache.sensitive.json"

# Remove image cache files
remove_file "current.png"
remove_file "current_eink.png"
remove_file "current_processed.png"

# Remove any backup cache files
remove_file "cache/async_wallet_address_cache.sensitive.json.backup"
remove_file "cache.json.backup"

# Remove Python cache directories
remove_directory "__pycache__"
remove_directory ".pytest_cache"

# Check for any other cache-related files
echo ""
echo "🔍 Checking for any remaining cache files..."
cache_files=$(find . -maxdepth 1 -name "*cache*" -type f 2>/dev/null)
if [ -n "$cache_files" ]; then
    echo "📋 Found additional cache files:"
    echo "$cache_files"
    echo ""
    read -p "❓ Remove these files too? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "$cache_files" | xargs rm -f
        echo "✅ Additional cache files removed"
    fi
else
    echo "✅ No additional cache files found"
fi

echo ""
echo "🎯 Cache reset complete! Next steps:"
echo "1. Restart the mempaper service:"
echo "   sudo systemctl restart mempaper.service"
echo ""
echo "2. Monitor the logs to see the fresh scan:"
echo "   journalctl -u mempaper.service -f --since \"now\""
echo ""
echo "3. Expected behavior:"
echo "   • Bootstrap search will check up to 200 addresses"
echo "   • Gap limit will continue until 20 consecutive unused addresses"
echo "   • All positive balances should be found"
echo ""
echo "📊 Gap limit configuration status:"
echo "   • xpub_enable_gap_limit: $(grep -o '\"xpub_enable_gap_limit\":[[:space:]]*[^,]*' config.json | cut -d':' -f2 | tr -d ' ,')"
echo "   • gap_limit: $(grep -o '\"gap_limit\":[[:space:]]*[^,]*' config.json | cut -d':' -f2 | tr -d ' ,')"
echo "   • enable_bootstrap_search: $(grep -o '\"enable_bootstrap_search\":[[:space:]]*[^,]*' config.json | cut -d':' -f2 | tr -d ' ,')"
echo "   • bootstrap_max_addresses: $(grep -o '\"bootstrap_max_addresses\":[[:space:]]*[^,]*' config.json | cut -d':' -f2 | tr -d ' ,')"
echo ""
echo "🚀 Ready for fresh wallet scan!"
