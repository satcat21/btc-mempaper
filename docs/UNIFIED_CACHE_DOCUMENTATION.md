# Unified Secure Cache System Documentation

## Overview

The Mempa#### 1. **UnifiedSecureCache** (`unified_secure_cache.py`)
- **Purpose:** Central manager for all secure cache operations
- **Key Methods:**
  - `get_cache(cache_type)` - Retrieve cache data for specific type
  - `set_cache(cache_type, data)` - Update cache data for specific type  
  - `get_cache_info()` - Get cache statistics and status
- **Thread Safety:** Uses RLock for concurrent access protection

#### 2. **BlockRewardCache** (`block_reward_cache.py`)
- **Updated:** Now uses `UnifiedSecureCache` when available
- **Fallback:** Individual file cache if secure cache unavailable
- **Migration:** Automatic detection and use of secure storageion now uses a unified secure cache system that encrypts all sensitive cache data into a single `cache.secure.json` file. This replaces the previous system of individual JSON cache files that contained sensitive Bitcoin addresses and transaction data in plain text.

## Security Features

### 🔐 **Encryption**
- Uses the same encryption system as `config.secure.json`
- AES-256 encryption via Fernet (cryptography library)
- Device-specific key derivation for Raspberry Pi hardware
- All sensitive cache data is encrypted at rest

### 🗂️ **Unified Storage**
- Single encrypted file: `cache/cache.secure.json`
- Contains all cache types: block reward, wallet balance, and optimized balance
- Atomic operations to prevent corruption
- Thread-safe access with proper locking

### 🔄 **Automatic Migration**
- Seamless migration from individual cache files
- Preserves all existing cache data during transition
- Creates backups of original files
- Graceful fallback if encryption fails

## Cache Types

The unified cache stores three types of sensitive data:

### 1. **Block Reward Cache** (`block_reward_cache`)
- Bitcoin addresses being monitored for mining rewards
- Coinbase transaction counts per address
- Block sync heights and scan progress
- **Previously:** `block_reward_cache.json`

### 2. **Wallet Balance Cache** (`wallet_balance_cache`)  
- Wallet addresses with current balances
- XPUB balance summaries
- Address comments and metadata
- **Previously:** `wallet_balance_cache.json`

### 3. **Optimized Balance Cache** (`optimized_balance_cache`)
- XPUB-derived address caches
- Performance optimization data for balance monitoring
- Gap limit detection results
- **Previously:** `optimized_balance_cache.json`

## File Structure

### New Structure (Secure)
```
cache/
├── cache.secure.json          # 🔐 All sensitive cache data (encrypted)
├── cache_metadata.json        # Non-sensitive metadata
└── *.migrated_backup          # Backup of original files
```

### Old Structure (Deprecated)
```
cache/
├── block_reward_cache.json    # ❌ Plain text (migrated)
├── optimized_balance_cache.json # ❌ Plain text (migrated)
├── wallet_balance_cache.json  # ❌ Plain text (migrated)
└── cache_metadata.json        # ✅ Still used (non-sensitive)
```

## Implementation Details

### Components Updated

#### 1. **SecureCacheManager** (`secure_cache_manager.py`)
- **Purpose:** Central manager for all secure cache operations
- **Key Methods:**
  - `get_cache(cache_type)` - Retrieve cache data for specific type
  - `set_cache(cache_type, data)` - Update cache data for specific type  
  - `get_cache_info()` - Get cache statistics and status
- **Thread Safety:** Uses RLock for concurrent access protection

#### 2. **BlockRewardCache** (`block_reward_cache.py`)
- **Updated:** Now uses `SecureCacheManager` when available
- **Fallback:** Individual file cache if secure cache unavailable
- **Migration:** Automatic detection and use of secure storage

#### 3. **WalletBalanceAPI** (`wallet_balance_api.py`)
- **Updated:** Integrates with unified cache for wallet data
- **Compatibility:** Works with async cache for address derivation
- **Dual Mode:** Uses both unified cache (wallet data) and async cache (addresses)

### Security Configuration

The unified cache uses the same encryption key as the secure configuration system:

```python
# Encryption key derived from:
- Raspberry Pi CPU serial number
- Network interface MAC address  
- System hostname and platform info
- Additional entropy sources
```

### API Usage Examples

#### Basic Cache Operations
```python
from secure_cache_manager import get_unified_cache

# Get cache instance
cache = get_unified_cache()

# Read cache data
block_data = cache.get_cache("block_reward_cache")
wallet_data = cache.get_cache("wallet_balance_cache")

# Update cache data
cache.set_cache("block_reward_cache", updated_data)

# Get cache information
info = cache.get_cache_info()
print(f"Cache version: {info['cache_version']}")
```

#### Component Integration
```python
from block_reward_cache import BlockRewardCache
from wallet_balance_api import WalletBalanceAPI

# These automatically use secure cache when available
block_cache = BlockRewardCache()  # Uses unified secure cache
wallet_api = WalletBalanceAPI()   # Uses unified secure cache + async cache
```

## Migration Guide

### Automatic Migration
The system automatically migrates from individual cache files on first use:

1. **Detection:** Checks for existing `cache.secure.json`
2. **Migration:** Reads individual cache files if secure cache doesn't exist
3. **Backup:** Creates `.migrated_backup` copies of original files
4. **Encryption:** Encrypts combined data into secure cache
5. **Verification:** Validates migration success

### Manual Migration
Use the provided migration script for controlled migration:

```bash
# Migrate with backup creation
python migrate_to_secure_cache.py

# Migrate and cleanup old files
python migrate_to_secure_cache.py --cleanup

# Force re-migration 
python migrate_to_secure_cache.py --force
```

### Rollback Procedure
If needed, restore from backup files:

```bash
# Restore individual cache files
cp cache/block_reward_cache.json.migrated_backup cache/block_reward_cache.json
cp cache/optimized_balance_cache.json.migrated_backup cache/optimized_balance_cache.json  
cp cache/wallet_balance_cache.json.migrated_backup cache/wallet_balance_cache.json

# Remove secure cache to disable unified system
rm cache/cache.secure.json
```

## Benefits

### 🔒 **Enhanced Security**
- **Before:** Sensitive addresses visible in plain text cache files
- **After:** All sensitive data encrypted with device-specific keys
- **Protection:** Cache files safe even if copied to other systems

### 🗂️ **Better Organization**
- **Before:** Multiple cache files scattered in project
- **After:** Single unified cache file for all sensitive data
- **Maintenance:** Easier backup, monitoring, and management

### ⚡ **Performance**
- **Atomic Operations:** Single file reduces I/O operations
- **Caching:** In-memory cache with periodic encryption saves
- **Thread Safety:** Proper locking prevents corruption

### 🔄 **Reliability** 
- **Backup System:** Automatic backup creation during migration
- **Fallback Mode:** Graceful degradation if encryption fails
- **Validation:** Cache structure validation prevents corruption

## Monitoring and Troubleshooting

### Cache Status
```python
from secure_cache_manager import get_unified_cache

cache = get_unified_cache()
print("Cache available:", cache.is_available())

info = cache.get_cache_info()
print(f"File size: {info.get('file_size', 0)} bytes")
print(f"Last updated: {info.get('last_updated', 0)}")
```

### Component Status
```python
from block_reward_cache import BlockRewardCache
from wallet_balance_api import WalletBalanceAPI

# Check if components are using secure cache
block_cache = BlockRewardCache()
print("Block cache secure:", block_cache.use_secure_cache)

wallet_api = WalletBalanceAPI()  
print("Wallet API unified:", wallet_api.use_unified_cache)
```

### Log Messages
- `🔐 Using unified secure cache` - Component successfully using secure storage
- `⚠️ Failed to initialize unified cache` - Fallback to individual files
- `✅ Migration complete! Migrated X cache files` - Successful migration
- `❌ Failed to save unified cache` - Encryption or file write error

## File Exclusions

The following files are excluded from version control (`.gitignore`):

```gitignore
# Secure cache files
cache/cache.secure.json
cache/async_wallet_address_cache.secure.json
*.secure.json

# Individual cache files (deprecated but excluded for safety)
cache/block_reward_cache.json
cache/optimized_balance_cache.json
cache/wallet_balance_cache.json

# Backup files
*.migrated_backup
*.pre_secure_backup
```

## Compatibility

### Requirements
- Python 3.7+
- `cryptography` library (already required for secure config)
- Existing secure configuration system

### Backwards Compatibility
- **Full compatibility** with existing individual cache files
- **Automatic migration** preserves all data
- **Graceful fallback** if encryption unavailable
- **No breaking changes** to existing APIs

### Platform Support
- **Raspberry Pi:** Full encryption with hardware-specific keys
- **Development Systems:** Compatible encryption with fallback entropy
- **Docker/Containers:** Works with available system information

---

*This unified secure cache system provides enterprise-grade security for sensitive Bitcoin address and transaction data while maintaining full compatibility with existing Mempaper functionality.*
