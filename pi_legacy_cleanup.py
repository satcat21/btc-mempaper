#!/usr/bin/env python3
"""
Remote Legacy Data Cleanup Script for Raspberry Pi

This script cleans up legacy block monitoring data that persists in cache files
even after addresses are removed from the configuration web interface.
"""

import json
import os
import sys

def cleanup_pi_legacy_data():
    """Clean up legacy block monitoring data on Raspberry Pi."""
    print("🧹 Starting Raspberry Pi legacy data cleanup...")
    
    try:
        # Files to check and clean
        cache_files_to_check = [
            "valid_blocks_count.json",
            "cache/block_reward_cache.json", 
            "cache/cache.json",
            "cache/cache.secure.json"  # This might be encrypted
        ]
        
        # Also check for any files that might contain block reward data
        additional_patterns = [
            "cache/async_wallet_address_cache.json",
            "cache/async_wallet_address_cache.secure.json",
            "cache/optimized_balance_cache.json"
        ]
        
        all_files = cache_files_to_check + additional_patterns
        
        cleaned_files = []
        found_legacy_addresses = []
        
        for cache_file in all_files:
            if os.path.exists(cache_file):
                print(f"\n🔍 Checking {cache_file}...")
                
                try:
                    # Skip encrypted files for now - they need special handling
                    if cache_file.endswith('.secure.json'):
                        print(f"🔐 Skipping encrypted file {cache_file} (requires secure cache handler)")
                        continue
                    
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                    
                    file_modified = False
                    
                    # Check different data structures
                    if "blocks_by_address" in data:
                        # Legacy format with blocks_by_address
                        legacy_addresses = list(data["blocks_by_address"].keys())
                        if legacy_addresses:
                            print(f"📍 Found {len(legacy_addresses)} addresses in blocks_by_address:")
                            for addr in legacy_addresses:
                                cropped = addr[:6] + '...' + addr[-6:] if len(addr) > 12 else addr
                                count = data["blocks_by_address"][addr]
                                print(f"   🗑️ {cropped}: {count} blocks")
                                found_legacy_addresses.append(addr)
                            
                            # Clear the blocks_by_address
                            data["blocks_by_address"] = {}
                            
                            # Reset valid_blocks count
                            if "valid_blocks" in data:
                                data["valid_blocks"] = 0
                            
                            file_modified = True
                    
                    elif "addresses" in data and isinstance(data["addresses"], dict):
                        # New cache format with addresses object
                        cached_addresses = list(data["addresses"].keys())
                        if cached_addresses:
                            print(f"📍 Found {len(cached_addresses)} addresses in cache:")
                            for addr in cached_addresses:
                                cropped = addr[:6] + '...' + addr[-6:] if len(addr) > 12 else addr
                                addr_data = data["addresses"][addr]
                                count = addr_data.get("total_coinbase_count", 0) if isinstance(addr_data, dict) else 0
                                print(f"   📊 {cropped}: {count} coinbase transactions")
                                found_legacy_addresses.append(addr)
                            
                            # Ask user if they want to clear this data
                            print(f"\n❓ Clear all address data from {cache_file}? (y/N): ", end='')
                            response = input().strip().lower()
                            if response == 'y':
                                data["addresses"] = {}
                                file_modified = True
                                print(f"✅ Cleared address data from {cache_file}")
                            else:
                                print(f"⏭️ Skipped clearing {cache_file}")
                    
                    # Save modified file
                    if file_modified:
                        # Create backup first
                        backup_file = f"{cache_file}.cleanup_backup"
                        import shutil
                        shutil.copy2(cache_file, backup_file)
                        print(f"💾 Created backup: {backup_file}")
                        
                        # Save cleaned data
                        with open(cache_file, 'w') as f:
                            json.dump(data, f, indent=2)
                        
                        cleaned_files.append(cache_file)
                        print(f"✅ Cleaned {cache_file}")
                    else:
                        print(f"✅ {cache_file} is clean or was skipped")
                        
                except json.JSONDecodeError:
                    print(f"⚠️ {cache_file} is not valid JSON - skipping")
                except Exception as e:
                    print(f"❌ Error processing {cache_file}: {e}")
            else:
                print(f"📄 {cache_file} doesn't exist")
        
        # Summary
        print(f"\n📊 Cleanup Summary:")
        print(f"   🗑️ Found legacy addresses: {len(set(found_legacy_addresses))}")
        print(f"   🧹 Cleaned files: {len(cleaned_files)}")
        
        if cleaned_files:
            print(f"\n✅ Files cleaned: {', '.join(cleaned_files)}")
            print(f"\n🔄 Restart the Mempaper service to apply changes:")
            print(f"   sudo systemctl restart mempaper")
        else:
            print(f"\n✅ No cleanup needed - all cache files are clean!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during cleanup: {e}")
        return False

def handle_encrypted_cache_cleanup():
    """Handle cleanup of encrypted cache files."""
    print(f"\n🔐 For encrypted cache files (.secure.json), you may need to:")
    print(f"   1. Stop the mempaper service: sudo systemctl stop mempaper")
    print(f"   2. Remove encrypted cache files: rm cache/*.secure.json")
    print(f"   3. Start the service: sudo systemctl start mempaper")
    print(f"   4. This will recreate clean cache files")

if __name__ == "__main__":
    success = cleanup_pi_legacy_data()
    
    if not success:
        sys.exit(1)
    
    # Additional advice for encrypted files
    handle_encrypted_cache_cleanup()
    
    print(f"\n🎉 Cleanup completed!")
