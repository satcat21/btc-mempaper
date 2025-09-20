#!/usr/bin/env python3
"""
Cleanup Legacy Block Data

This script removes legacy block monitoring data for addresses that are no longer
in the configuration. Run this to clean up old data immediately.
"""

import json
import os
import sys
from config_manager import ConfigManager

def cleanup_legacy_block_data():
    """Clean up legacy block monitoring data."""
    try:
        # Initialize config manager
        config_manager = ConfigManager()
        config = config_manager.get_current_config()
        
        # Get current monitored addresses from config
        current_addresses = []
        block_reward_table = config.get("block_reward_addresses_table", [])
        for entry in block_reward_table:
            if isinstance(entry, dict) and entry.get("address"):
                current_addresses.append(entry["address"])
        
        current_addresses = set(current_addresses)
        print(f"📍 Current configuration monitors {len(current_addresses)} addresses")
        
        # Check legacy files
        legacy_files = [
            "valid_blocks_count.json",
            "cache/block_reward_cache.json"
        ]
        
        cleaned_any = False
        
        for legacy_file in legacy_files:
            if os.path.exists(legacy_file):
                print(f"\n🔍 Checking {legacy_file}...")
                
                try:
                    with open(legacy_file, 'r') as f:
                        data = json.load(f)
                    
                    # Check for blocks_by_address in legacy format
                    if "blocks_by_address" in data:
                        legacy_addresses = set(data["blocks_by_address"].keys())
                        to_remove = legacy_addresses - current_addresses
                        
                        if to_remove:
                            print(f"🧹 Found {len(to_remove)} legacy addresses to remove:")
                            
                            for addr in to_remove:
                                cropped_addr = addr[:6] + '...' + addr[-6:] if len(addr) > 12 else addr
                                count = data["blocks_by_address"].get(addr, 0)
                                print(f"   🗑️ Removing {cropped_addr} (blocks: {count})")
                                del data["blocks_by_address"][addr]
                                
                                # Update valid_blocks count if it exists
                                if "valid_blocks" in data:
                                    data["valid_blocks"] = max(0, data.get("valid_blocks", 0) - count)
                            
                            # Save cleaned data
                            with open(legacy_file, 'w') as f:
                                json.dump(data, f, indent=2)
                            
                            print(f"✅ Cleaned {legacy_file}")
                            cleaned_any = True
                        else:
                            print(f"✅ {legacy_file} is already clean")
                    
                    # Check for addresses in new cache format
                    elif "addresses" in data:
                        cache_addresses = set(data["addresses"].keys())
                        to_remove = cache_addresses - current_addresses
                        
                        if to_remove:
                            print(f"🧹 Found {len(to_remove)} cached addresses to remove:")
                            
                            for addr in to_remove:
                                cropped_addr = addr[:6] + '...' + addr[-6:] if len(addr) > 12 else addr
                                print(f"   🗑️ Removing {cropped_addr}")
                                del data["addresses"][addr]
                            
                            # Save cleaned data
                            with open(legacy_file, 'w') as f:
                                json.dump(data, f, indent=2)
                            
                            print(f"✅ Cleaned {legacy_file}")
                            cleaned_any = True
                        else:
                            print(f"✅ {legacy_file} is already clean")
                    else:
                        print(f"✅ {legacy_file} doesn't contain address data")
                        
                except Exception as e:
                    print(f"❌ Error processing {legacy_file}: {e}")
            else:
                print(f"📄 {legacy_file} doesn't exist")
        
        if cleaned_any:
            print("\n🎉 Legacy data cleanup completed! Restart the application to see the changes.")
        else:
            print("\n✅ No legacy data cleanup needed - all files are clean!")
            
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🧹 Starting legacy block data cleanup...")
    success = cleanup_legacy_block_data()
    sys.exit(0 if success else 1)
