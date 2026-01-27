"""
Unified Secure Cache Manager

Provides encryption for all sensitive cache data including:
- Block reward monitoring cache (Bitcoin addresses and coinbase counts)
- Optimized balance cache (XPUB data and derived addresses)  
- Wallet balance cache (address balances and comments)

All cache data is encrypted into a single cache.secure.json file using the same
encryption system as config.secure.json.

Security Features:
- Single encrypted file for all cache data
- Uses same encryption key as secure config
- Thread-safe operations
- Transparent migration from individual cache files
- Performance optimized for frequent cache operations

Cache Structure:
{
    "block_reward_cache": { ... },
    "optimized_balance_cache": { ... },
    "wallet_balance_cache": { ... },
    "cache_version": "2.0",
    "last_updated": timestamp
}
"""

import os
import json
import threading
import time
from typing import Dict, Any, Optional, Literal
from managers.secure_config_manager import SecureConfigManager


class UnifiedSecureCache:
    """Manages all sensitive cache data in a single encrypted file."""
    
    CacheType = Literal["block_reward_cache", "optimized_balance_cache", "wallet_balance_cache"]
    
    def __init__(self, cache_dir: str = "cache"):
        """
        Initialize unified secure cache manager.
        
        Args:
            cache_dir: Directory where cache files are stored
        """
        self.cache_dir = cache_dir
        self.secure_cache_file = os.path.join(cache_dir, "cache.secure.json")
        self.cache_lock = threading.RLock()
        
        # Ensure cache directory exists
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        # Use shared encryption system from secure config
        self.secure_manager = SecureConfigManager("config/config.json")
        
        # Initialize cache structure
        self.cache_data = {
            "block_reward_cache": {},
            "optimized_balance_cache": {},
            "wallet_balance_cache": {},
            "cache_version": "2.0",
            "last_updated": time.time()
        }
        
        # Load existing cache or migrate from individual files
        self._load_or_migrate_cache()
        
        print(f"🔐 Unified secure cache initialized at {self.secure_cache_file}")
    
    def _load_or_migrate_cache(self) -> None:
        """Load existing secure cache or migrate from individual cache files."""
        with self.cache_lock:
            # Try to load existing secure cache first
            if os.path.exists(self.secure_cache_file):
                try:
                    with open(self.secure_cache_file, 'r') as f:
                        encrypted_data = json.load(f)
                    
                    # Decrypt the data
                    if 'encrypted_data' in encrypted_data:
                        decrypted_data = self.secure_manager._decrypt_data(encrypted_data['encrypted_data'])
                        if decrypted_data and isinstance(decrypted_data, dict):
                            # Validate cache structure
                            if self._validate_cache_structure(decrypted_data):
                                self.cache_data = decrypted_data
                                # print(f"✅ Loaded unified secure cache from {self.secure_cache_file}")
                                return
                            else:
                                print(f"⚠️ Invalid secure cache structure, will migrate individual files")
                except Exception as e:
                    print(f"⚠️ Failed to load secure cache: {e}, will migrate individual files")
            
            # If no secure cache exists, migrate from individual files
            self._migrate_individual_cache_files()
    
    def _migrate_individual_cache_files(self) -> None:
        """Migrate data from individual cache files to unified secure cache."""
        print("🔄 Migrating individual cache files to unified secure cache...")
        
        # Individual cache file paths
        individual_files = {
            "block_reward_cache": os.path.join(self.cache_dir, "block_reward_cache.json"),
            "optimized_balance_cache": os.path.join(self.cache_dir, "optimized_balance_cache.json"),
            "wallet_balance_cache": os.path.join(self.cache_dir, "wallet_balance_cache.json")
        }
        
        migrated_count = 0
        
        for cache_type, file_path in individual_files.items():
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        cache_data = json.load(f)
                        self.cache_data[cache_type] = cache_data
                        migrated_count += 1
                        print(f"✅ Migrated {cache_type} from {file_path}")
                        
                        # Create backup of original file (copy instead of move to avoid lock issues)
                        backup_path = file_path + ".migrated_backup"
                        try:
                            import shutil
                            shutil.copy2(file_path, backup_path)
                            print(f"💾 Backed up original file to {backup_path}")
                        except Exception as backup_error:
                            print(f"⚠️ Failed to backup {file_path}: {backup_error}")
                            # Continue migration even if backup fails
                        
                except Exception as e:
                    print(f"⚠️ Failed to migrate {cache_type} from {file_path}: {e}")
        
        if migrated_count > 0:
            self.cache_data["last_updated"] = time.time()
            self._save_cache()
            print(f"✅ Migration complete! Migrated {migrated_count} cache files to secure storage")
        else:
            print("ℹ️ No individual cache files found to migrate")
    
    def _validate_cache_structure(self, cache_data: Dict[str, Any]) -> bool:
        """Validate the unified cache structure."""
        required_keys = {"block_reward_cache", "optimized_balance_cache", "wallet_balance_cache", "cache_version"}
        return all(key in cache_data for key in required_keys)
    
    def _save_cache(self) -> None:
        """Save cache data to encrypted file."""
        try:
            self.cache_data["last_updated"] = time.time()
            
            # Encrypt the cache data
            encrypted_data = self.secure_manager._encrypt_data(self.cache_data)
            
            # Save to file
            secure_data = {
                "encrypted_data": encrypted_data,
                "version": "2.0",
                "created": time.time()
            }
            
            with open(self.secure_cache_file, 'w') as f:
                json.dump(secure_data, f, indent=2)
                
        except Exception as e:
            print(f"❌ Failed to save unified cache: {e}")
            raise
    
    def get_cache(self, cache_type: CacheType) -> Dict[str, Any]:
        """
        Get cache data for a specific cache type.
        
        Args:
            cache_type: Type of cache to retrieve
            
        Returns:
            Cache data dictionary
        """
        with self.cache_lock:
            return self.cache_data.get(cache_type, {}).copy()
    
    def set_cache(self, cache_type: CacheType, cache_data: Dict[str, Any]) -> None:
        """
        Set cache data for a specific cache type.
        
        Args:
            cache_type: Type of cache to update
            cache_data: New cache data
        """
        with self.cache_lock:
            self.cache_data[cache_type] = cache_data
            self._save_cache()
    
    def update_cache(self, cache_type: CacheType, updates: Dict[str, Any]) -> None:
        """
        Update specific fields in a cache type.
        
        Args:
            cache_type: Type of cache to update
            updates: Dictionary of fields to update
        """
        with self.cache_lock:
            if cache_type not in self.cache_data:
                self.cache_data[cache_type] = {}
            
            self.cache_data[cache_type].update(updates)
            self._save_cache()
    
    def clear_cache(self, cache_type: CacheType) -> None:
        """
        Clear all data for a specific cache type.
        
        Args:
            cache_type: Type of cache to clear
        """
        with self.cache_lock:
            self.cache_data[cache_type] = {}
            self._save_cache()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the unified cache."""
        with self.cache_lock:
            info = {
                "cache_file": self.secure_cache_file,
                "cache_version": self.cache_data.get("cache_version", "unknown"),
                "last_updated": self.cache_data.get("last_updated", 0),
                "cache_types": {
                    cache_type: {
                        "size": len(str(cache_data).encode('utf-8')),
                        "keys": len(cache_data) if isinstance(cache_data, dict) else 0
                    }
                    for cache_type, cache_data in self.cache_data.items()
                    if cache_type not in ("cache_version", "last_updated")
                }
            }
            
            if os.path.exists(self.secure_cache_file):
                info["file_size"] = os.path.getsize(self.secure_cache_file)
            
            return info
    
    def is_available(self) -> bool:
        """Check if secure cache is available and working."""
        try:
            # Test that we can encrypt/decrypt
            test_data = {"test": "data"}
            encrypted = self.secure_manager._encrypt_data(test_data)
            decrypted = self.secure_manager._decrypt_data(encrypted)
            return decrypted == test_data
        except Exception:
            return False


# Singleton instance for global access
_unified_cache_instance: Optional[UnifiedSecureCache] = None
_instance_lock = threading.Lock()


def get_unified_cache() -> UnifiedSecureCache:
    """Get or create the global unified cache instance."""
    global _unified_cache_instance
    
    with _instance_lock:
        if _unified_cache_instance is None:
            _unified_cache_instance = UnifiedSecureCache()
        return _unified_cache_instance
