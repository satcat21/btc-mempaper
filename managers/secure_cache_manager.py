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
import threading
from typing import Dict, Any
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
        self.encrypted_cache_file = cache_file.replace('.json', '.sensitive.json')
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
                    encrypted_data = self.secure_manager._read_possibly_sealed(
                        self.encrypted_cache_file) or {}

                    if encrypted_data.get('_encrypted_cache'):
                        # Written by a version that still encrypted at rest.
                        # Decrypt once; the next save rewrites it in the clear.
                        decrypted_data = self.secure_manager._decrypt_data(encrypted_data['data'])
                        if decrypted_data is not None:
                            self.save_cache(decrypted_data)
                            return decrypted_data
                        else:
                            print(f"⚠️ Failed to decrypt cache: {self.encrypted_cache_file}")
                    elif isinstance(encrypted_data.get('data'), dict):
                        return encrypted_data['data']
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
                    # Plain, like the other sensitive files. The device key it
                    # used to be wrapped in was recomputable by anyone holding
                    # the Pi; Tang seals this file when it is switched on.
                    encrypted_cache = {
                        '_encrypted_cache': False,
                        '_version': '2.0',
                        '_cache_type': 'address_derivation',
                        'data': cache_data
                    }

                    self.secure_manager._write_possibly_sealed(
                        self.encrypted_cache_file, encrypted_cache)
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
