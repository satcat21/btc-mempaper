"""
Secure Cache Manager

Provides encryption for address derivation cache files containing sensitive XPUB data.
Integrates with the existing cache system to transparently encrypt/decrypt cache data.

Security Features:
- Encrypts entire cache files containing XPUBs and derived addresses
- Uses same encryption system as secure config
- Transparent integration with existing cache code
- Performance optimized for frequent cache operations

"""

import os
import json
import threading
from typing import Dict, Any, Optional
from managers.secure_config_manager import SecureConfigManager


class SecureCacheManager:
    """Manages encrypted cache files for sensitive address derivation data."""
    
    def __init__(self, cache_file: str):
        """
        Initialize secure cache manager.
        
        Args:
            cache_file: Path to cache file to encrypt
        """
        self.cache_file = cache_file
        self.encrypted_cache_file = cache_file.replace('.json', '.secure.json')
        self.cache_lock = threading.RLock()
        
        # Ensure cache directory exists
        cache_dir = os.path.dirname(cache_file)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        
        # Use shared encryption system from secure config
        # Always look for config in the root directory, not in cache subdirectory
        if cache_dir.startswith('cache'):
            config_path = 'config/config.json'
        else:
            config_dir = os.path.dirname(cache_file) or '.'
            config_path = os.path.join(config_dir, 'config.json')
        
        try:
            self.secure_manager = SecureConfigManager(config_path)
            self.encryption_available = True
            # print(f"🔐 Secure cache manager initialized for {cache_file}")
        except Exception as e:
            print(f"⚠️ Cache encryption unavailable: {e}")
            self.encryption_available = False
            self.secure_manager = None
    
    def load_cache(self) -> Dict[str, Any]:
        """
        Load cache data with automatic decryption.
        
        Returns:
            Cache data dictionary
        """
        with self.cache_lock:
            # Load encrypted cache only
            if self.encryption_available and os.path.exists(self.encrypted_cache_file):
                try:
                    with open(self.encrypted_cache_file, 'r') as f:
                        encrypted_data = json.load(f)
                    
                    if encrypted_data.get('_encrypted_cache'):
                        decrypted_data = self.secure_manager._decrypt_data(encrypted_data['data'])
                        if decrypted_data is not None:
                            # Only log if cache has actual content (not just empty dict)
                            # if decrypted_data and len(decrypted_data) > 0:
                                # Silent loading for faster startup
                                # print(f"💾 Loaded cached data from {self.encrypted_cache_file}")
                            return decrypted_data
                        else:
                            print(f"⚠️ Failed to decrypt cache: {self.encrypted_cache_file}")
                except Exception as e:
                    print(f"⚠️ Error loading encrypted cache: {e}")
            
            # Return empty cache if encrypted cache not found
            return {}
    
    def save_cache(self, cache_data: Dict[str, Any]) -> bool:
        """
        Save cache data with automatic encryption.
        
        Args:
            cache_data: Cache data to save
            
        Returns:
            True if saved successfully
        """
        with self.cache_lock:
            try:
                # Only save encrypted cache
                if self.encryption_available and self.secure_manager:
                    encrypted_cache = {
                        '_encrypted_cache': True,
                        '_version': '1.0',
                        '_cache_type': 'address_derivation',
                        'data': self.secure_manager._encrypt_data(cache_data)
                    }
                    
                    with open(self.encrypted_cache_file, 'w') as f:
                        json.dump(encrypted_cache, f, indent=2)
                    
                    # Set restrictive permissions
                    os.chmod(self.encrypted_cache_file, 0o600)
                    
                    print(f" Saved encrypted cache: {self.encrypted_cache_file}")
                    return True
                else:
                    print(f"❌ Encryption not available - cannot save cache")
                    return False
                
            except Exception as e:
                print(f"❌ Error saving cache: {e}")
                return False
    
    def clear_cache(self) -> bool:
        """Clear encrypted cache file."""
        if os.path.exists(self.encrypted_cache_file):
            try:
                os.remove(self.encrypted_cache_file)
                print(f"🗑️ Cleared cache: {self.encrypted_cache_file}")
                return True
            except Exception as e:
                print(f"⚠️ Failed to clear {self.encrypted_cache_file}: {e}")
                return False
        else:
            print(f"ℹ️ No cache file to clear: {self.encrypted_cache_file}")
            return True
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about cache files."""
        info = {
            'encrypted_cache_exists': os.path.exists(self.encrypted_cache_file),
            'encryption_available': self.encryption_available,
            'encrypted_cache_size': 0,
            'recommendation': None
        }
        
        if info['encrypted_cache_exists']:
            info['encrypted_cache_size'] = os.path.getsize(self.encrypted_cache_file)
        
        # Security recommendations
        if not info['encryption_available']:
            info['recommendation'] = "Install cryptography library to enable cache encryption"
        
        return info


def patch_wallet_balance_api():
    """
    Patch WalletBalanceAPI to use secure cache automatically.
    This function modifies the existing cache system to use encryption.
    """
    try:
        from wallet_balance_api import WalletBalanceAPI
        
        # Store original methods
        original_load_cache = WalletBalanceAPI._load_address_cache
        original_save_cache = WalletBalanceAPI._save_address_cache
        
        def secure_load_cache(self):
            """Load address cache with encryption support."""
            if not hasattr(self, '_secure_cache_manager'):
                self._secure_cache_manager = SecureCacheManager(self.cache_file)
            
            self.address_cache = self._secure_cache_manager.load_cache()
        
        def secure_save_cache(self):
            """Save address cache with encryption support."""
            if not hasattr(self, '_secure_cache_manager'):
                self._secure_cache_manager = SecureCacheManager(self.cache_file)
            
            return self._secure_cache_manager.save_cache(self.address_cache)
        
        # Patch the methods
        WalletBalanceAPI._load_address_cache = secure_load_cache
        WalletBalanceAPI._save_address_cache = secure_save_cache
        
        print("🔐 WalletBalanceAPI patched for secure cache support")
        return True
        
    except Exception as e:
        print(f"⚠️ Failed to patch WalletBalanceAPI: {e}")
        return False


def patch_async_cache_manager():
    """
    Patch AsyncAddressCacheManager to use secure cache.
    """
    try:
        from config_observer import AsyncAddressCacheManager
        
        # Store original methods
        original_load_cache = AsyncAddressCacheManager._load_cache_from_disk
        original_save_cache = AsyncAddressCacheManager._save_cache_to_disk
        
        def secure_load_cache(self):
            """Load async cache with encryption support."""
            if not hasattr(self, '_secure_cache_manager'):
                self._secure_cache_manager = SecureCacheManager(self.cache_file)
            
            cache_data = self._secure_cache_manager.load_cache()
            
            # Convert to expected format
            for key, value in cache_data.items():
                if isinstance(value, dict) and 'addresses' in value:
                    self.cache[key] = {
                        'addresses': value['addresses'],
                        'timestamp': value.get('timestamp', 0),
                        'count': value.get('count', len(value['addresses']))
                    }
        
        def secure_save_cache(self):
            """Save async cache with encryption support."""
            if not hasattr(self, '_secure_cache_manager'):
                self._secure_cache_manager = SecureCacheManager(self.cache_file)
            
            return self._secure_cache_manager.save_cache(dict(self.cache))
        
        # Patch the methods
        AsyncAddressCacheManager._load_cache_from_disk = secure_load_cache
        AsyncAddressCacheManager._save_cache_to_disk = secure_save_cache
        
        print("🔐 AsyncAddressCacheManager patched for secure cache support")
        return True
        
    except Exception as e:
        print(f"⚠️ Failed to patch AsyncAddressCacheManager: {e}")
        return False


def migrate_all_caches():
    """Check all secure cache files (migration no longer needed as plain caches are deprecated)."""
    cache_files = [
        'wallet_address_cache.json',
        'cache/async_wallet_address_cache.json'
    ]
    
    # Check if secure cache files exist
    existing_secure = 0
    for cache_file in cache_files:
        secure_cache = SecureCacheManager(cache_file)
        if secure_cache.get_cache_info()['encrypted_cache_exists']:
            existing_secure += 1
    
    print(f"✅ Found {existing_secure} existing secure cache files")
    return existing_secure


def get_all_cache_status():
    """Get security status of all cache files."""
    cache_files = [
        'wallet_address_cache.json',
        'cache/async_wallet_address_cache.json'
    ]
    
    status = {}
    for cache_file in cache_files:
        secure_cache = SecureCacheManager(cache_file)
        status[cache_file] = secure_cache.get_cache_info()
    
    return status


def main():
    """Test and demonstration of secure cache manager."""
    print("🔐 Secure Cache Manager Test")
    
    # Check status of all caches
    print("\n💾 Cache Security Status:")
    cache_status = get_all_cache_status()
    
    for cache_file, info in cache_status.items():
        print(f"\n📁 {cache_file}:")
        print(f"   Encrypted cache exists: {'✅' if info['encrypted_cache_exists'] else '❌'}")
        print(f"   Encryption available: {'✅' if info['encryption_available'] else '❌'}")
        
        if info['recommendation']:
            print(f"   💡 Recommendation: {info['recommendation']}")
    
    # Test migration
    print(f"\n⚙️ Testing cache migration...")
    migrate_all_caches()
    
    # Patch existing systems
    print(f"\n🔧 Patching cache systems...")
    patch_wallet_balance_api()
    patch_async_cache_manager()


if __name__ == "__main__":
    main()
