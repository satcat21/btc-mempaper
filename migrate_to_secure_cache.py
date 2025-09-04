#!/usr/bin/env python3
"""
Secure Cache Migration Script

This script helps migrate from individual cache files to the unified secure cache system.
It can also clean up old cache files after successful migration.

Usage:
    python migrate_to_secure_cache.py [--cleanup] [--force]
    
Options:
    --cleanup: Remove old cache files after successful migration
    --force: Force migration even if secure cache already exists
"""

import os
import sys
import argparse
import json
import shutil
from typing import Dict, List


def check_unified_cache_available() -> bool:
    """Check if unified secure cache is available and working."""
    try:
        from secure_cache_manager import get_unified_cache
        cache = get_unified_cache()
        return cache.is_available()
    except Exception as e:
        print(f"❌ Unified secure cache not available: {e}")
        return False


def backup_cache_files(cache_dir: str = "cache") -> List[str]:
    """Create backups of existing cache files."""
    cache_files = [
        "block_reward_cache.json",
        "optimized_balance_cache.json", 
        "wallet_balance_cache.json",
        "cache_metadata.json"
    ]
    
    backed_up = []
    
    for cache_file in cache_files:
        file_path = os.path.join(cache_dir, cache_file)
        if os.path.exists(file_path):
            backup_path = f"{file_path}.pre_secure_backup"
            try:
                shutil.copy2(file_path, backup_path)
                backed_up.append(backup_path)
                print(f"💾 Backed up {file_path} to {backup_path}")
            except Exception as e:
                print(f"⚠️ Failed to backup {file_path}: {e}")
    
    return backed_up


def migrate_to_secure_cache(force: bool = False) -> bool:
    """Migrate cache files to unified secure cache."""
    try:
        from secure_cache_manager import get_unified_cache
        
        # Check if secure cache already exists
        cache_dir = "cache"
        secure_cache_file = os.path.join(cache_dir, "cache.secure.json")
        
        if os.path.exists(secure_cache_file) and not force:
            print(f"ℹ️ Secure cache already exists at {secure_cache_file}")
            print("Use --force to recreate it")
            return True
        
        # Create unified cache (this will trigger migration)
        cache = get_unified_cache()
        
        # Verify migration was successful
        cache_info = cache.get_cache_info()
        migrated_types = [t for t in cache_info["cache_types"] if cache_info["cache_types"][t]["keys"] > 0]
        
        print(f"✅ Successfully migrated cache data for: {', '.join(migrated_types)}")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


def cleanup_old_files(cache_dir: str = "cache") -> None:
    """Remove old individual cache files."""
    old_files = [
        "block_reward_cache.json",
        "optimized_balance_cache.json",
        "wallet_balance_cache.json"
    ]
    
    for old_file in old_files:
        file_path = os.path.join(cache_dir, old_file)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"🗑️ Removed old cache file: {file_path}")
            except Exception as e:
                print(f"⚠️ Failed to remove {file_path}: {e}")


def verify_secure_cache() -> bool:
    """Verify that the secure cache is working correctly."""
    try:
        from secure_cache_manager import get_unified_cache
        from block_reward_cache import BlockRewardCache
        from wallet_balance_api import WalletBalanceAPI
        
        # Test unified cache
        cache = get_unified_cache()
        if not cache.is_available():
            print("❌ Unified cache not available")
            return False
        
        # Test block reward cache
        block_cache = BlockRewardCache()
        if not block_cache.use_secure_cache:
            print("⚠️ Block reward cache not using secure storage")
        
        # Test wallet balance API
        wallet_api = WalletBalanceAPI()
        if not wallet_api.use_unified_cache:
            print("⚠️ Wallet balance API not using unified cache")
        
        print("✅ All components successfully using secure cache")
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate to unified secure cache")
    parser.add_argument("--cleanup", action="store_true", 
                       help="Remove old cache files after successful migration")
    parser.add_argument("--force", action="store_true",
                       help="Force migration even if secure cache exists") 
    
    args = parser.parse_args()
    
    print("🔐 Secure Cache Migration Script")
    print("=" * 40)
    
    # Check prerequisites
    if not check_unified_cache_available():
        print("❌ Cannot proceed without unified secure cache")
        sys.exit(1)
    
    # Create backups
    print("\n📦 Creating backups...")
    backed_up = backup_cache_files()
    
    # Perform migration
    print("\n🔄 Migrating to secure cache...")
    if not migrate_to_secure_cache(force=args.force):
        print("❌ Migration failed")
        sys.exit(1)
    
    # Verify migration
    print("\n🔍 Verifying secure cache...")
    if not verify_secure_cache():
        print("⚠️ Verification failed, but migration appears successful")
    
    # Cleanup if requested
    if args.cleanup:
        print("\n🗑️ Cleaning up old files...")
        cleanup_old_files()
    
    print("\n✅ Migration completed successfully!")
    print(f"📁 Secure cache location: cache/cache.secure.json")
    
    if backed_up:
        print("\n💾 Backup files created:")
        for backup in backed_up:
            print(f"   - {backup}")
    
    if not args.cleanup:
        print("\n💡 Run with --cleanup to remove old cache files")


if __name__ == "__main__":
    main()
