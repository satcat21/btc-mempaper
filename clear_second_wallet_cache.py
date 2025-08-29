#!/usr/bin/env python3
"""
Clear optimized balance cache for second wallet to trigger fresh gap limit detection
"""

import json
import os
from pathlib import Path

def clear_second_wallet_cache():
    """Clear the optimized balance cache for zpub6rEoKKBKD7dEcBo6 wallet"""
    
    # Define cache file paths
    cache_files = [
        "optimized_balance_cache.json",
        "optimized_balance_cache.secure.json"
    ]
    
    second_wallet_prefix = "zpub6rEoKKBKD7dEcBo6"
    
    print(f"🔍 Looking for optimized balance cache entries for {second_wallet_prefix}...")
    
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            try:
                print(f"📂 Checking {cache_file}...")
                
                # Load cache
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                # Find and remove entries for second wallet
                keys_to_remove = []
                for key in cache_data.keys():
                    if second_wallet_prefix in key:
                        keys_to_remove.append(key)
                
                if keys_to_remove:
                    for key in keys_to_remove:
                        del cache_data[key]
                        print(f"🗑️  Removed cache entry: {key[:50]}...")
                    
                    # Save updated cache
                    with open(cache_file, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                    
                    print(f"✅ Updated {cache_file} - removed {len(keys_to_remove)} entries")
                else:
                    print(f"ℹ️  No entries found for {second_wallet_prefix} in {cache_file}")
                    
            except Exception as e:
                print(f"⚠️  Error processing {cache_file}: {e}")
        else:
            print(f"⚠️  Cache file not found: {cache_file}")
    
    print(f"""
🚀 Cache cleared for {second_wallet_prefix}

Next steps:
1. Deploy the updated code to Raspberry Pi:
   - wallet_balance_api.py (fixed gap limit detection)
   - config.json (added gap limit settings)

2. Restart the service:
   sudo systemctl restart mempaper.service

3. Monitor the logs for gap limit detection:
   journalctl -u mempaper.service -f --since "now"

Expected behavior:
- Bootstrap search will scan up to 200 addresses in batches of 20
- Gap limit will continue until 20 consecutive unused addresses found
- If funded addresses exist beyond address 20, they will be detected
- Cache will be valid for 50 days after successful scan
""")

if __name__ == "__main__":
    clear_second_wallet_cache()
