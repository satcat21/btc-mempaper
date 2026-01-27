"""
Secure Configuration Manager

Provides lightweight encryption for sensitive configuration data on Raspberry Pi.
Uses Fernet (AES 128) for fast, secure encryption suitable for embedded devices.

Security Features:
- File-level encryption for sensitive config sections
- Key derivation from device-specific hardware info
- Automatic detection of sensitive fields
- Graceful fallback for unencrypted configs
- Raspberry Pi Zero W optimized

"""

import os
import json
import hashlib
import base64
import time
from typing import Dict, Any, List, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import platform
import uuid


class SecureConfigManager:
    """Lightweight encryption for sensitive configuration data."""
    
    def __init__(self, config_file: str = "config/config.json"):
        """
        Initialize secure config manager.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.encrypted_config_file = "config/config.secure.json"
        self.key_file = "config/.config_key"
        
        # Define sensitive fields that should be encrypted
        self.sensitive_fields = {
            'wallet_balance_addresses_with_comments', 
            'block_reward_addresses_table',
            'admin_password_hash',
            'secret_key',
        }
        
        # Initialize encryption key
        self._encryption_key = None
        self._ensure_encryption_key()
    
    def _get_device_fingerprint(self) -> str:
        """
        Generate device-specific fingerprint for Raspberry Pi.
        Uses hardware-specific information available on RPi.
        """
        fingerprint_data = []
        
        try:
            # CPU serial number (Raspberry Pi specific)
            with open('/proc/cpuinfo', 'r') as f:
                for line in f:
                    if line.startswith('Serial'):
                        fingerprint_data.append(line.strip())
                        break
        except (FileNotFoundError, PermissionError, OSError):
            # Fallback for non-RPi systems or permission issues
            fingerprint_data.append(platform.node())
        
        try:
            # MAC address of first network interface
            import psutil
            interfaces = psutil.net_if_addrs()
            for interface_name, addresses in interfaces.items():
                for address in addresses:
                    if address.family == psutil.AF_LINK:  # MAC address
                        fingerprint_data.append(address.address)
                        break
                if fingerprint_data and len([d for d in fingerprint_data if d]) > 1:
                    break
        except (ImportError, AttributeError, OSError):
            # Fallback without psutil or on error
            try:
                import uuid
                mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                               for elements in range(0, 2*6, 2)][::-1])
                fingerprint_data.append(mac)
            except Exception:
                fingerprint_data.append(platform.machine())
        
        # Add system info as additional entropy with error handling
        try:
            fingerprint_data.extend([
                platform.system(),
                platform.machine(),
                str(os.getuid() if hasattr(os, 'getuid') else 'windows')
            ])
        except (AttributeError, OSError):
            # Fallback if platform calls fail
            fingerprint_data.extend([
                'unknown_system',
                'unknown_machine', 
                'unknown_user'
            ])
        
        # Ensure we have at least some fingerprint data
        if not fingerprint_data or not any(fingerprint_data):
            fingerprint_data = [
                'fallback_device',
                str(hash(platform.platform())),
                str(int(time.time()) // 86400)  # Day-based fallback
            ]
        
        # Create hash of all fingerprint data
        fingerprint_str = '|'.join(str(d) for d in fingerprint_data if d)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()
    
    def _derive_key_from_device(self, salt: bytes) -> bytes:
        """
        Derive encryption key from device fingerprint.
        Uses PBKDF2 for key stretching.
        """
        device_fingerprint = self._get_device_fingerprint()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256-bit key
            salt=salt,
            iterations=100000,  # Moderate for RPi Zero W
        )
        
        return kdf.derive(device_fingerprint.encode())
    
    def _ensure_encryption_key(self) -> None:
        """Ensure encryption key exists or create new one."""
        if os.path.exists(self.key_file):
            # Load existing key
            try:
                with open(self.key_file, 'rb') as f:
                    salt = f.read(32)  # First 32 bytes are salt
                    
                key = self._derive_key_from_device(salt)
                self._encryption_key = base64.urlsafe_b64encode(key)
                
                # Test key validity
                Fernet(self._encryption_key)
                
            except Exception as e:
                print(f"⚠️ Error loading encryption key: {e}")
                self._create_new_key()
        else:
            # Create new key
            self._create_new_key()
    
    def _create_new_key(self) -> None:
        """Create new encryption key and save salt."""
        # Generate random salt
        salt = os.urandom(32)
        
        # Derive key from device fingerprint
        key = self._derive_key_from_device(salt)
        self._encryption_key = base64.urlsafe_b64encode(key)
        
        # Save salt to key file (not the actual key!)
        with open(self.key_file, 'wb') as f:
            f.write(salt)
        
        # Set restrictive permissions on key file
        os.chmod(self.key_file, 0o600)
        
        print(f"🔐 Created new encryption key (salt saved to {self.key_file})")
    
    def _encrypt_data(self, data: Any) -> str:
        """Encrypt sensitive data."""
        if self._encryption_key is None:
            raise ValueError("Encryption key not initialized")
        
        fernet = Fernet(self._encryption_key)
        json_str = json.dumps(data, separators=(',', ':'))
        encrypted_bytes = fernet.encrypt(json_str.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def _decrypt_data(self, encrypted_str: str) -> Any:
        """Decrypt sensitive data."""
        if self._encryption_key is None:
            raise ValueError("Encryption key not initialized")
        
        try:
            fernet = Fernet(self._encryption_key)
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_str.encode())
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode())
        except Exception as e:
            print(f"⚠️ Decryption failed: {e}")
            return None
    
    def save_secure_config(self, config: Dict[str, Any]) -> bool:
        """
        Save configuration with sensitive fields encrypted.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if saved successfully
        """
        try:
            # Separate sensitive and non-sensitive data
            secure_config = {}
            public_config = {}
            
            for key, value in config.items():
                if key in self.sensitive_fields:
                    secure_config[key] = value
                else:
                    public_config[key] = value
            
            # Save public config as regular JSON
            with open(self.config_file, 'w') as f:
                json.dump(public_config, f, indent=2)
            
            # Save encrypted sensitive config
            if secure_config:
                encrypted_config = {
                    '_encrypted': True,
                    '_version': '1.0',
                    'data': self._encrypt_data(secure_config)
                }
                
                with open(self.encrypted_config_file, 'w') as f:
                    json.dump(encrypted_config, f, indent=2)
                
                # Set restrictive permissions
                os.chmod(self.encrypted_config_file, 0o600)
            
            print(f"🔒 Saved secure configuration:")
            print(f"   📄 Public data: {self.config_file}")
            print(f"   🔐 Encrypted data: {self.encrypted_config_file}")
            return True
            
        except Exception as e:
            print(f"❌ Error saving secure config: {e}")
            return False
    
    def load_secure_config(self) -> Optional[Dict[str, Any]]:
        """
        Load and decrypt configuration.
        This method loads BOTH plain and encrypted configs, but should only be used
        for migration purposes. For normal operation, use the config_manager.
        
        Returns:
            Complete configuration dictionary or None if failed
        """
        try:
            # Load public config (non-sensitive fields)
            public_config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    public_config = json.load(f)
            
            # Load encrypted config (sensitive fields only)
            secure_config = {}
            if os.path.exists(self.encrypted_config_file):
                with open(self.encrypted_config_file, 'r') as f:
                    encrypted_data = json.load(f)
                
                if encrypted_data.get('_encrypted'):
                    decrypted_data = self._decrypt_data(encrypted_data['data'])
                    if decrypted_data:
                        secure_config = decrypted_data
                    else:
                        print("⚠️ Failed to decrypt secure configuration")
                        return None
            
            # Merge configurations - sensitive fields from encrypted, non-sensitive from plain
            complete_config = {**public_config, **secure_config}
            
            # print(f"🔓 Loaded secure configuration:")
            # print(f"   📄 Public fields: {len(public_config)}")
            # print(f"   🔐 Encrypted fields: {len(secure_config)}")
            
            return complete_config
            
        except Exception as e:
            print(f"❌ Error loading secure config: {e}")
            return None
    
    def migrate_from_plain_config(self) -> bool:
        """
        Migrate existing plain config.json to secure format.
        
        Returns:
            True if migration successful
        """
        if not os.path.exists(self.config_file):
            print(f"❌ Config file {self.config_file} not found")
            return False
        
        try:
            # Backup original config
            backup_file = self.config_file + '.backup'
            import shutil
            shutil.copy2(self.config_file, backup_file)
            
            # Load existing config
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Save in secure format
            success = self.save_secure_config(config)
            
            if success:
                print(f"✅ Migration completed successfully!")
                print(f"   📄 Backup saved: {backup_file}")
                print(f"   🔒 Secure config created: {self.encrypted_config_file}")
                return True
            else:
                print(f"❌ Migration failed")
                return False
                
        except Exception as e:
            print(f"❌ Migration error: {e}")
            return False
    
    def clean_secure_config(self) -> bool:
        """
        Clean the secure config to ensure it only contains sensitive fields.
        Remove any non-sensitive data that shouldn't be encrypted.
        
        Returns:
            True if cleaning successful
        """
        try:
            # Load current complete configuration
            current_config = self.load_secure_config()
            if not current_config:
                print("❌ Could not load current configuration for cleaning")
                return False
            
            # Check what's currently in the encrypted file
            encrypted_data = {}
            if os.path.exists(self.encrypted_config_file):
                with open(self.encrypted_config_file, 'r') as f:
                    encrypted_file_data = json.load(f)
                
                if encrypted_file_data.get('_encrypted'):
                    decrypted_data = self._decrypt_data(encrypted_file_data['data'])
                    if decrypted_data:
                        encrypted_data = decrypted_data
                        print(f"🔍 Current encrypted config contains {len(encrypted_data)} fields:")
                        for key in encrypted_data.keys():
                            is_sensitive = key in self.sensitive_fields
                            print(f"   {'🔐' if is_sensitive else '📄'} {key}: {'SENSITIVE' if is_sensitive else 'NOT SENSITIVE'}")
            
            # Identify non-sensitive fields that shouldn't be encrypted
            non_sensitive_in_encrypted = {k: v for k, v in encrypted_data.items() if k not in self.sensitive_fields}
            
            if non_sensitive_in_encrypted:
                print(f"🧹 Found {len(non_sensitive_in_encrypted)} non-sensitive fields in encrypted config:")
                for key in non_sensitive_in_encrypted.keys():
                    print(f"   📄 {key} (will be moved to public config)")
                
                # Re-save configuration to properly separate sensitive/non-sensitive data
                success = self.save_secure_config(current_config)
                
                if success:
                    print("✅ Secure config cleaned successfully!")
                    print("   🔐 Only sensitive fields are now encrypted")
                    print("   📄 Non-sensitive fields moved to public config")
                    return True
                else:
                    print("❌ Failed to clean secure config")
                    return False
            else:
                print("✅ Secure config is already clean - contains only sensitive fields")
                return True
                
        except Exception as e:
            print(f"❌ Error cleaning secure config: {e}")
            return False
        """Get current security status and recommendations."""
        status = {
            'encryption_enabled': os.path.exists(self.encrypted_config_file),
            'key_file_exists': os.path.exists(self.key_file),
            'public_config_exists': os.path.exists(self.config_file),
            'device_fingerprint': self._get_device_fingerprint()[:16] + "...",
            'recommendations': []
        }
        
        if not status['encryption_enabled']:
            status['recommendations'].append("Enable encryption for sensitive data")
        
        if status['public_config_exists']:
            # Check if public config contains sensitive data
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                sensitive_in_public = [key for key in config.keys() if key in self.sensitive_fields]
                if sensitive_in_public:
                    status['recommendations'].append(f"Migrate sensitive fields to encrypted storage: {', '.join(sensitive_in_public)}")
            except:
                pass
        
        # Check file permissions
        for file_path in [self.key_file, self.encrypted_config_file]:
            if os.path.exists(file_path):
                file_stat = os.stat(file_path)
                if file_stat.st_mode & 0o077:  # Check if readable by group/others
                    status['recommendations'].append(f"Restrict permissions on {os.path.basename(file_path)}")
        
        return status


def main():
    """Test and demonstration of secure config manager."""
    print("🔐 Secure Configuration Manager Test")
    
    secure_manager = SecureConfigManager()
    
    # Show security status
    status = secure_manager.get_security_status()
    print(f"\n📊 Security Status:")
    for key, value in status.items():
        if key != 'recommendations':
            print(f"   {key}: {value}")
    
    if status['recommendations']:
        print(f"\n💡 Recommendations:")
        for rec in status['recommendations']:
            print(f"   • {rec}")
    
    # Test migration if plain config exists
    if os.path.exists('config/config.json') and not status['encryption_enabled']:
        print(f"\n🔄 Testing migration from plain config...")
        success = secure_manager.migrate_from_plain_config()
        if success:
            print("✅ Migration test successful")
        else:
            print("❌ Migration test failed")


if __name__ == "__main__":
    main()
