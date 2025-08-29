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
from secure_config_manager import SecureConfigManager


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
        
        # Use shared encryption system from secure config
        config_dir = os.path.dirname(cache_file) or '.'
        config_path = os.path.join(config_dir, 'config.json')
        
        try:
            self.secure_manager = SecureConfigManager(config_path)
            self.encryption_available = True
            print(f"🔐 Secure cache manager initialized for {cache_file}")
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
            # Try encrypted cache first
            if self.encryption_available and os.path.exists(self.encrypted_cache_file):
                try:
                    with open(self.encrypted_cache_file, 'r') as f:
                        encrypted_data = json.load(f)
                    
                    if encrypted_data.get('_encrypted_cache'):
                        decrypted_data = self.secure_manager._decrypt_data(encrypted_data['data'])
                        if decrypted_data is not None:
                            print(f"🔓 Loaded encrypted cache: {self.cache_file}")
                            return decrypted_data
                        else:
                            print(f"⚠️ Failed to decrypt cache: {self.cache_file}")
                except Exception as e:
                    print(f"⚠️ Error loading encrypted cache: {e}")
            
            # Fallback to plain cache
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r') as f:
                        data = json.load(f)
                    print(f"📄 Loaded plain cache: {self.cache_file}")
                    return data
                except Exception as e:
                    print(f"⚠️ Error loading plain cache: {e}")
            
            # Return empty cache if nothing found
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
                # Save encrypted cache if encryption available
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
                    
                    # Remove plain cache file if it exists (migration)
                    if os.path.exists(self.cache_file):
                        try:
                            os.remove(self.cache_file)
                            print(f"🗑️ Removed plain cache file: {self.cache_file}")
                        except:
                            pass
                    
                    print(f"🔒 Saved encrypted cache: {self.encrypted_cache_file}")
                    return True
                
                # Fallback to plain cache
                with open(self.cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                print(f"📄 Saved plain cache: {self.cache_file}")
                return True
                
            except Exception as e:
                print(f"❌ Error saving cache: {e}")
                return False
    
    def migrate_plain_cache(self) -> bool:
        """
        Migrate existing plain cache to encrypted format.
        
        Returns:
            True if migration successful
        """
        if not os.path.exists(self.cache_file):
            print(f"✅ No plain cache to migrate: {self.cache_file}")
            return True
        
        if not self.encryption_available:
            print(f"⚠️ Cannot migrate cache - encryption not available")
            return False
        
        try:
            # Load existing cache
            cache_data = {}
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            if not cache_data:
                print(f"✅ Empty cache, nothing to migrate")
                return True
            
            # Save as encrypted
            success = self.save_cache(cache_data)
            
            if success:
                print(f"✅ Cache migration successful: {self.cache_file} → {self.encrypted_cache_file}")
                return True
            else:
                print(f"❌ Cache migration failed: {self.cache_file}")
                return False
                
        except Exception as e:
            print(f"❌ Cache migration error: {e}")
            return False
    
    def clear_cache(self) -> bool:
        """Clear both encrypted and plain cache files."""
        success = True
        
        for cache_path in [self.cache_file, self.encrypted_cache_file]:
            if os.path.exists(cache_path):
                try:
                    os.remove(cache_path)
                    print(f"🗑️ Cleared cache: {cache_path}")
                except Exception as e:
                    print(f"⚠️ Failed to clear {cache_path}: {e}")
                    success = False
        
        return success
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about cache files."""
        info = {
            'plain_cache_exists': os.path.exists(self.cache_file),
            'encrypted_cache_exists': os.path.exists(self.encrypted_cache_file),
            'encryption_available': self.encryption_available,
            'plain_cache_size': 0,
            'encrypted_cache_size': 0,
            'recommendation': None
        }
        
        if info['plain_cache_exists']:
            info['plain_cache_size'] = os.path.getsize(self.cache_file)
        
        if info['encrypted_cache_exists']:
            info['encrypted_cache_size'] = os.path.getsize(self.encrypted_cache_file)
        
        # Security recommendations
        if info['plain_cache_exists'] and info['encryption_available']:
            info['recommendation'] = "Migrate plain cache to encrypted format"
        elif not info['encryption_available'] and (info['plain_cache_exists'] or info['encrypted_cache_exists']):
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
    """Migrate all existing cache files to encrypted format."""
    cache_files = [
        'wallet_address_cache.json',
        'async_wallet_address_cache.json'
    ]
    
    migrated = 0
    for cache_file in cache_files:
        if os.path.exists(cache_file):
            secure_cache = SecureCacheManager(cache_file)
            if secure_cache.migrate_plain_cache():
                migrated += 1
    
    print(f"✅ Migrated {migrated} cache files to encrypted format")
    return migrated


def get_all_cache_status():
    """Get security status of all cache files."""
    cache_files = [
        'wallet_address_cache.json',
        'async_wallet_address_cache.json'
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
    print("\n📊 Cache Security Status:")
    cache_status = get_all_cache_status()
    
    for cache_file, info in cache_status.items():
        print(f"\n📁 {cache_file}:")
        print(f"   Plain cache exists: {'✅' if info['plain_cache_exists'] else '❌'}")
        print(f"   Encrypted cache exists: {'✅' if info['encrypted_cache_exists'] else '❌'}")
        print(f"   Encryption available: {'✅' if info['encryption_available'] else '❌'}")
        
        if info['recommendation']:
            print(f"   💡 Recommendation: {info['recommendation']}")
    
    # Test migration
    print(f"\n🔄 Testing cache migration...")
    migrate_all_caches()
    
    # Patch existing systems
    print(f"\n🔧 Patching cache systems...")
    patch_wallet_balance_api()
    patch_async_cache_manager()


if __name__ == "__main__":
    main()
