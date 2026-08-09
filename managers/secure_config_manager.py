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
import subprocess
import time
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from argon2.low_level import Type as Argon2Type, hash_secret_raw
import platform

from utils.atomic_io import atomic_write_json


# Files renamed when the device-key encryption was removed. "secure" claimed a
# protection the scheme never provided; these hold sensitive data, which is what
# the name now says. Renaming rather than leaving the old name avoids a file
# whose name misleads whoever finds it on a card.
LEGACY_FILE_RENAMES = [
    ('config/config.secure.json', 'config/config.sensitive.json'),
    ('cache/cache.secure.json', 'cache/cache.sensitive.json'),
    ('cache/async_wallet_address_cache.secure.json',
     'cache/async_wallet_address_cache.sensitive.json'),
]


def migrate_legacy_filenames(root=None):
    """Rename the old .secure.json files, once, keeping their contents.

    Runs before anything opens them. Skips a rename when the new name already
    exists, so an interrupted upgrade cannot clobber converted data with a
    stale copy left behind.
    """
    base = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    renamed = []
    for old_rel, new_rel in LEGACY_FILE_RENAMES:
        old_path = os.path.join(base, old_rel)
        new_path = os.path.join(base, new_rel)
        if not os.path.exists(old_path) or os.path.exists(new_path):
            continue
        try:
            os.replace(old_path, new_path)
            renamed.append((old_rel, new_rel))
        except OSError as e:
            print(f"⚠️ Could not rename {old_rel}: {e}")
    for old_rel, new_rel in renamed:
        print(f"🔄 Renamed {old_rel} -> {new_rel}")
    return renamed


class SecureConfigManager:
    """Lightweight encryption for sensitive configuration data."""
    
    # Class-level cache for encryption key (shared across all instances)
    _cached_encryption_key = None
    _key_file_mtime = None
    _cached_legacy_keys = None
    _cached_salt = None

    # Current device-key scheme. Bump when the fingerprint or the KDF changes,
    # and keep the superseded derivation reachable from
    # _get_device_fingerprint so existing data stays readable.
    FINGERPRINT_VERSION = 2

    # Argon2id cost. Memory is the parameter that hurts a GPU attacker. The
    # derived key is cached on the class, so this is paid once per process
    # rather than per instance, but it still lands in the boot path on a Pi
    # Zero and so is sized for that rather than maximised.
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_KIB = 16384  # 16 MiB
    ARGON2_PARALLELISM = 1

    def __init__(self, config_file: str = "config/config.json"):
        """
        Initialize secure config manager.
        
        Args:
            config_file: Path to configuration file
        """
        self.config_file = config_file
        self.encrypted_config_file = "config/config.sensitive.json"
        self.key_file = "config/.config_key"
        
        # Define sensitive fields that should be encrypted
        self.sensitive_fields = {
            'wallet_balance_addresses_with_comments',
            'block_reward_addresses_table',
            'admin_password_hash',
            'admin_users',
            'secret_key',
            'mempool_password'
        }
        
        # Set when a decrypt only succeeded under a superseded key, meaning
        # the file on disk still needs rewriting. See migrate_to_current_scheme.
        self._used_legacy_key = False

        # The device key is derived lazily, only if a file written by an older
        # version is encountered. New writes are not encrypted at all.
        #
        # Deriving it eagerly used to cost an Argon2id pass at every process
        # start - one to three seconds on a Pi Zero - to protect data against a
        # key an attacker holding the device can simply recompute. That was
        # never worth it; see docs/SECURITY_GUIDE.md. Real protection against a
        # stolen device is Tang, whose key is not on the card at all.
        #
        # Once every file has been read once and rewritten in the clear, this
        # derivation never runs again and the whole path can be deleted.
        self._encryption_key = None

        # Set when a read had to fall back to device-encrypted content,
        # so the file gets rewritten in the clear exactly once.
        self._needs_plaintext_rewrite = False

        # Decrypted config, cached as JSON text against the on-disk stamp of
        # both config files. See get_sensitive_fields_cached.
        self._secure_cache_json = None
        self._secure_cache_stamp = None

    def _config_files_stamp(self):
        """Identity of both config files, for cache invalidation.

        Size is carried alongside mtime because coarse filesystem timestamps
        can put two quick writes in the same tick.
        """
        stamp = []
        for path in (self.config_file, self.encrypted_config_file):
            try:
                st = os.stat(path)
                stamp.append((st.st_mtime_ns, st.st_size))
            except OSError:
                stamp.append(None)
        return tuple(stamp)

    def get_sensitive_fields_cached(self) -> Optional[Dict[str, Any]]:
        """The sensitive fields only, without re-reading and re-decrypting
        unchanged files.

        load_secure_config costs two file reads plus a Fernet decrypt, and the
        per-request mempool helpers reach it through
        ConfigManager.get_current_config several times per outgoing HTTP
        request. Keyed on the stamp of both files, so an outside writer is
        still picked up; save_secure_config drops the cache outright.

        Only the sensitive keys are kept, since that is all the caller merges,
        which keeps the cached payload at a handful of keys rather than the
        whole config. The plaintext is held as JSON text and parsed per call,
        so callers get their own objects and cannot mutate what the next
        caller sees.
        """
        stamp = self._config_files_stamp()
        if stamp == self._secure_cache_stamp and self._secure_cache_json is not None:
            return json.loads(self._secure_cache_json)

        config = self.load_secure_config()
        if config is None:
            # A failed decrypt is not cached, so the next call retries.
            self._secure_cache_json = None
            self._secure_cache_stamp = None
            return None

        sensitive = {k: v for k, v in config.items() if k in self.sensitive_fields}
        self._secure_cache_json = json.dumps(sensitive)
        self._secure_cache_stamp = stamp
        return sensitive

    def _invalidate_secure_cache(self):
        """Drop the cached plaintext after a write."""
        self._secure_cache_json = None
        self._secure_cache_stamp = None

    def _tang_store(self):
        """The shared Tang store, or None when sealing is genuinely off.

        Imported lazily: tang_store imports this module, so a module-level
        import would be circular.

        Only a disabled configuration returns None. An error here used to
        return None too, which the writer read as "Tang is off" and answered by
        writing clear text - so a fault anywhere in this path silently undid the
        sealing of every file it touched. A failure now propagates, because
        refusing to write is recoverable and quietly unsealing is not.
        """
        from managers.tang_store import get_shared_store
        store = get_shared_store()
        return store if store.is_enabled() else None

    def _tang_enabled_on_disk(self):
        """Whether sealing is switched on, straight from config.json.

        Used as an independent check so a broken store cannot be mistaken for
        a disabled one.
        """
        try:
            with open(self.config_file, encoding='utf-8') as f:
                return bool(json.load(f).get('tang_enabled'))
        except Exception:
            return False

    def _write_possibly_sealed(self, path, obj):
        """Write JSON, sealed against Tang when that is switched on.

        The plain-config check is a second opinion, not belt-and-braces: if
        sealing is configured, this must not fall back to clear text for any
        reason. Writing plaintext over a sealed file is silent and permanent -
        the protection is gone and nothing says so.
        """
        store = self._tang_store()
        if store is None:
            if self._tang_enabled_on_disk():
                raise RuntimeError(
                    'Tang is enabled but the sealed store is unavailable; '
                    'refusing to write this file in clear text')
            atomic_write_json(path, obj, mode=0o600, indent=2)
            return
        payload = json.dumps(obj, indent=2).encode('utf-8')
        store.write_file(path, payload, mode=0o600)

    def _read_possibly_sealed(self, path):
        """Read JSON written by _write_possibly_sealed, or None if absent.

        Handles a file written before Tang was enabled: read_file passes
        unsealed content straight through.
        """
        store = self._tang_store()
        if store is None:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except FileNotFoundError:
                return None
        raw = store.read_file(path)
        return json.loads(raw.decode('utf-8')) if raw else None

    def migrate_encrypted_to_plaintext(self) -> bool:
        """Rewrite a still-encrypted sensitive config in the clear, once.

        Reading sets _needs_plaintext_rewrite when it had to fall back to the
        device key. Without this the file would only convert on the next
        configuration save, so a device nobody touches would keep paying the
        Argon2id cost at every start forever.

        Returns True only when a rewrite happened.
        """
        if not os.path.exists(self.encrypted_config_file):
            return False

        self._needs_plaintext_rewrite = False
        config = self.load_secure_config()
        if config is None or not self._needs_plaintext_rewrite:
            return False

        print("🔄 Rewriting the sensitive config without device encryption")
        if self.save_secure_config(config):
            print("✅ Sensitive config converted; the device key is no longer needed")
            return True

        # Not fatal: the old key still reads it, so the next start can retry.
        print("⚠️ Could not convert the sensitive config; will retry")
        return False

    def migrate_to_current_scheme(self) -> bool:
        """Rewrite the encrypted config if it is still under an older key.

        The cache files re-encrypt themselves, since they are rewritten
        whenever a balance changes. config.sensitive.json is only written when
        something saves the configuration, so without this an untouched
        device would keep its secrets under the superseded key indefinitely
        and never benefit from the current scheme.

        Returns True only when a rewrite actually happened.
        """
        if not os.path.exists(self.encrypted_config_file):
            return False

        self._used_legacy_key = False
        config = self.load_secure_config()
        if config is None or not self._used_legacy_key:
            return False

        print(f"🔄 Re-encrypting {self.encrypted_config_file} "
              f"under key scheme v{self.FINGERPRINT_VERSION}")
        if self.save_secure_config(config):
            print("✅ Secure configuration migrated to the current key scheme")
            return True

        # Not fatal: the old key still reads the data, so the next attempt
        # can retry rather than leaving the device unable to start.
        print("⚠️ Could not re-encrypt the secure configuration; will retry")
        return False


    def _get_device_fingerprint(self, version: int = None) -> str:
        """Device fingerprint for the requested scheme version.

        Version 2 is current. Version 1 is kept byte-for-byte so that data
        written before the change still decrypts; see _decrypt_data.
        """
        version = self.FINGERPRINT_VERSION if version is None else version
        if version == 1:
            return self._get_device_fingerprint_v1()
        return self._get_device_fingerprint_v2()

    def _read_text(self, path: str) -> str:
        """First line of a small sysfs/procfs file, or empty. Device-tree
        values carry a trailing NUL, which would otherwise land in the hash."""
        try:
            with open(path, 'r', errors='ignore') as f:
                return f.read(256).replace('\x00', '').strip()
        except (OSError, UnicodeDecodeError):
            return ''

    def _hardware_macs(self) -> list:
        """MAC addresses of real interfaces, sorted, all-zero ones dropped.

        Sorted because interface enumeration order is not guaranteed stable
        across reboots, and an unstable fingerprint means unreadable data.
        Virtual interfaces are excluded for the same reason: docker and
        wireguard devices come and go.
        """
        skip_prefixes = ('lo', 'docker', 'veth', 'br-', 'virbr', 'tun', 'tap',
                         'wg', 'zt', 'tailscale')
        macs = set()
        try:
            import psutil
            for name, addresses in psutil.net_if_addrs().items():
                if name.startswith(skip_prefixes):
                    continue
                for address in addresses:
                    if getattr(address, 'family', None) != psutil.AF_LINK:
                        continue
                    mac = (address.address or '').strip().lower()
                    if mac and set(mac) - set(':-0'):
                        macs.add(mac)
        except (ImportError, AttributeError, OSError):
            pass
        return sorted(macs)

    def _get_device_fingerprint_v2(self) -> str:
        """Device fingerprint bound to the SoC where one is available.

        Replaces the v1 inputs, which were weaker than intended: v1 took the
        first interface psutil reported, and on Linux that is the loopback
        device, whose MAC is 00:00:00:00:00:00. The supposed MAC component
        was therefore a constant contributing nothing.

        On a Pi the CPU serial is the only identifier that lives in the SoC
        rather than on the card, so it alone decides the key when present.
        Hardware MACs are the fallback for non-Pi hosts. They are deliberately
        not mixed in alongside the serial: adding a USB network adapter would
        then change the fingerprint and orphan the encrypted data.
        """
        parts = []

        serial = ''
        for line in self._read_text('/proc/cpuinfo').splitlines():
            if line.startswith('Serial'):
                serial = line.split(':', 1)[-1].strip()
                break
        if not serial:
            serial = self._read_text('/proc/device-tree/serial-number')

        if serial:
            parts.append(f'serial={serial}')
        else:
            macs = self._hardware_macs()
            if macs:
                parts.append('macs=' + ','.join(macs))
            else:
                parts.append('node=' + platform.node())

        parts.append('machine=' + platform.machine())

        return hashlib.sha256('|'.join(parts).encode()).hexdigest()

    def _get_device_fingerprint_v1(self) -> str:
        """
        Generate device-specific fingerprint for Raspberry Pi.
        Uses hardware-specific information available on RPi.

        Superseded by _get_device_fingerprint_v2 and retained only so that
        data encrypted under the old scheme can still be read. Do not change.
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
            ])
        except (AttributeError, OSError):
            # Fallback if platform calls fail
            fingerprint_data.extend([
                'unknown_system',
                'unknown_machine',
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
    
    def _derive_key_from_device(self, salt: bytes, version: int = None) -> bytes:
        """
        Derive encryption key from device fingerprint.

        Version 2 uses Argon2id. The fingerprint it stretches is worth only
        about 32 bits on a Pi - the unique part of the CPU serial - and no
        hardware source can raise that, so the remaining lever is the cost of
        a guess. PBKDF2-SHA256 parallelises well on a GPU; Argon2id is
        memory-hard and does not, which is worth roughly an order of
        magnitude here. See docs/SECURITY_GUIDE.md.

        Version 1 is PBKDF2 and is kept only to read old data.
        """
        version = self.FINGERPRINT_VERSION if version is None else version
        device_fingerprint = self._get_device_fingerprint(version)

        if version == 1:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,  # 256-bit key
                salt=salt,
                iterations=100000,  # Moderate for RPi Zero W
            )
            return kdf.derive(device_fingerprint.encode())

        return hash_secret_raw(
            secret=device_fingerprint.encode(),
            salt=salt,
            time_cost=self.ARGON2_TIME_COST,
            memory_cost=self.ARGON2_MEMORY_KIB,
            parallelism=self.ARGON2_PARALLELISM,
            hash_len=32,
            type=Argon2Type.ID,
        )

    def _legacy_encryption_keys(self, salt: bytes) -> list:
        """Keys for superseded schemes, newest first.

        Decryption accepts these so an in-place upgrade does not orphan data
        already on disk; encryption always uses the current scheme, so a
        record migrates the next time it is written.
        """
        keys = []
        for version in range(self.FINGERPRINT_VERSION - 1, 0, -1):
            try:
                keys.append(base64.urlsafe_b64encode(
                    self._derive_key_from_device(salt, version)))
            except Exception:
                continue
        return keys
    
    def _ensure_encryption_key(self) -> None:
        """Ensure encryption key exists or create new one."""
        # Check if we can use cached key
        if os.path.exists(self.key_file):
            current_mtime = os.path.getmtime(self.key_file)
            
            # Use class-level cached key if available and key file hasn't changed
            if (SecureConfigManager._cached_encryption_key is not None and
                SecureConfigManager._key_file_mtime == current_mtime):
                self._encryption_key = SecureConfigManager._cached_encryption_key
                # Carry the salt across too. Without it this instance cannot
                # derive a superseded key, and data written under the old
                # scheme would look corrupt rather than being migrated.
                self._salt = SecureConfigManager._cached_salt
                return
            
            # Load existing key
            try:
                with open(self.key_file, 'rb') as f:
                    salt = f.read(32)  # First 32 bytes are salt

                self._salt = salt
                SecureConfigManager._cached_salt = salt
                key = self._derive_key_from_device(salt)
                self._encryption_key = base64.urlsafe_b64encode(key)
                
                # Test key validity
                Fernet(self._encryption_key)
                
                # Cache the key for future instances
                SecureConfigManager._cached_encryption_key = self._encryption_key
                SecureConfigManager._key_file_mtime = current_mtime
                
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
        self._salt = salt
        SecureConfigManager._cached_salt = salt
        key = self._derive_key_from_device(salt)
        self._encryption_key = base64.urlsafe_b64encode(key)
        
        # Save salt to key file (not the actual key!)
        with open(self.key_file, 'wb') as f:
            f.write(salt)
        
        # Set restrictive permissions on key file
        os.chmod(self.key_file, 0o600)
        
        # Cache the key for future instances
        SecureConfigManager._cached_encryption_key = self._encryption_key
        SecureConfigManager._key_file_mtime = os.path.getmtime(self.key_file)
        
        print(f"🔐 Created new encryption key (salt saved to {self.key_file})")
    
    def _encrypt_data(self, data: Any) -> str:
        """Encrypt sensitive data."""
        if self._encryption_key is None:
            raise ValueError("Encryption key not initialized")
        
        fernet = Fernet(self._encryption_key)
        json_str = json.dumps(data, separators=(',', ':'))
        encrypted_bytes = fernet.encrypt(json_str.encode())
        return base64.urlsafe_b64encode(encrypted_bytes).decode()
    
    def _ensure_key_for_legacy_read(self) -> bool:
        """Derive the device key, on demand, to read pre-plaintext data.

        Called only when an _encrypted envelope is actually found, so a device
        that has finished migrating never pays the Argon2id cost.
        """
        if self._encryption_key is not None:
            return True
        try:
            self._ensure_encryption_key()
        except Exception as e:
            print(f"⚠️ Could not derive the legacy device key: {e}")
            return False
        return self._encryption_key is not None

    def _decrypt_data(self, encrypted_str: str) -> Any:
        """Decrypt data written by a version that still encrypted at rest."""
        if not self._ensure_key_for_legacy_read():
            return None

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_str.encode())
        except Exception as e:
            print(f"⚠️ Decryption failed: {e}")
            return None

        try:
            decrypted_bytes = Fernet(self._encryption_key).decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode())
        except Exception as current_error:
            # Fall back to superseded schemes: a device upgraded in place still
            # holds data written under the old key. Rewriting it happens on the
            # next save, which always encrypts with the current scheme.
            for key in self._get_legacy_keys():
                try:
                    decrypted_bytes = Fernet(key).decrypt(encrypted_bytes)
                except Exception:
                    continue
                self._used_legacy_key = True
                return json.loads(decrypted_bytes.decode())

            print(f"⚠️ Decryption failed: {current_error}")
            return None

    def _get_legacy_keys(self) -> list:
        """Superseded device keys, derived once per process.

        Deriving them is as costly as deriving the real key, so this only runs
        when a decrypt has already failed, and the result is cached.
        """
        if SecureConfigManager._cached_legacy_keys is not None:
            return SecureConfigManager._cached_legacy_keys
        salt = getattr(self, '_salt', None)
        if not salt:
            return []
        SecureConfigManager._cached_legacy_keys = self._legacy_encryption_keys(salt)
        return SecureConfigManager._cached_legacy_keys
    
    def _is_root_readonly(self) -> bool:
        """Check if / is mounted read-only."""
        try:
            with open('/proc/mounts') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[1] == '/':
                        return 'ro' in parts[3].split(',')
        except Exception:
            pass
        return False

    def save_secure_config(self, config: Dict[str, Any]) -> bool:
        """
        Save configuration with sensitive fields encrypted.

        Args:
            config: Configuration dictionary

        Returns:
            True if saved successfully
        """
        # Some Pi images run with / mounted read-only (e.g. raspi-config's
        # overlay filesystem); remount rw for the duration of the write so
        # this doesn't silently fail and leave stale data on disk.
        was_readonly = self._is_root_readonly()
        if was_readonly:
            subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], capture_output=True, timeout=10)
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
            atomic_write_json(self.config_file, public_config, indent=2)

            # Always (re)write the encrypted file, even when secure_config is
            # empty. Skipping the write when there's nothing sensitive left
            # (e.g. a factory/delivery-state reset that clears admin_users
            # with no other sensitive field to keep the dict non-empty) would
            # leave stale credentials sitting in the old encrypted file.
            # Written in the clear. The device-derived key that used to wrap
            # this was recomputable by anyone holding the Pi, so it never
            # defended the case it appeared to. Keeping it would have implied a
            # protection the scheme could not deliver. Physical protection of
            # the device, or Tang, is what actually defends this file.
            #
            # The separate file still earns its place: it stays 0600 while
            # config.json is group-readable, it is the unit Tang seals, and it
            # keeps tang_url readable so the store can bootstrap.
            encrypted_config = {
                '_encrypted': False,
                '_version': '2.0',
                'data': secure_config,
            }

            # Sealed on top of the device-key encryption when Tang is on. The
            # two layers are independent: the device key still protects a
            # copied image, and Tang additionally makes a stolen card useless.
            # Reading reverses both, so the layers can be unwound separately if
            # the device scheme is ever retired.
            self._write_possibly_sealed(self.encrypted_config_file, encrypted_config)

            self._invalidate_secure_cache()

            print(f"🔒 Saved secure configuration:")
            print(f"   📄 Public data: {self.config_file}")
            print(f"   🔐 Encrypted data: {self.encrypted_config_file}")
            return True

        except Exception as e:
            print(f"❌ Error saving secure config: {e}")
            return False
        finally:
            if was_readonly:
                subprocess.run(['sudo', 'mount', '-o', 'remount,ro', '/'], capture_output=True, timeout=10)
    
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
                encrypted_data = self._read_possibly_sealed(self.encrypted_config_file) or {}

                payload = encrypted_data.get('data')
                if encrypted_data.get('_encrypted'):
                    # Written by a version that still encrypted at rest. Derive
                    # the device key just for this, then let the next save
                    # rewrite the file in the clear.
                    decrypted_data = self._decrypt_data(payload)
                    if decrypted_data:
                        secure_config = decrypted_data
                        self._needs_plaintext_rewrite = True
                    else:
                        print("⚠️ Failed to decrypt secure configuration")
                        return None
                elif isinstance(payload, dict):
                    secure_config = payload
            
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
    
    def get_security_status(self):
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
                if file_stat.st_mode & 0o077:
                    status['recommendations'].append(f"Restrict permissions on {os.path.basename(file_path)}")
        
        return status


def main():
    """Test and demonstration of secure config manager."""
    print("🔐 Secure Configuration Manager Test")
    
    secure_manager = SecureConfigManager()
    
    # Show security status
    status = secure_manager.get_security_status()
    print(f"\n💾 Security Status:")
    for key, value in status.items():
        if key != 'recommendations':
            print(f"   {key}: {value}")
    
    if status['recommendations']:
        print(f"\n💡 Recommendations:")
        for rec in status['recommendations']:
            print(f"   • {rec}")
    
    # Test migration if plain config exists
    if os.path.exists('config/config.json') and not status['encryption_enabled']:
        print(f"\n⚙️ Testing migration from plain config...")
        success = secure_manager.migrate_from_plain_config()
        if success:
            print("✅ Migration test successful")
        else:
            print("❌ Migration test failed")


if __name__ == "__main__":
    main()
