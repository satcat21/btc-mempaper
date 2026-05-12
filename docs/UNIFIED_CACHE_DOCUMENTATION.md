# UNIFIED SECURE CACHE SYSTEM

## OVERVIEW

The mempaper application uses a unified secure cache system that encrypts all sensitive cache data into a single `cache.secure.json` file. This replaces the previous system of individual JSON cache files that contained sensitive Bitcoin addresses and transaction data in plain text.

---

## SECURITY FEATURES

### Encryption

- Uses the same encryption system as `config.secure.json`
- AES-256 encryption via Fernet (cryptography library)
- Device-specific key derivation for Raspberry Pi hardware
- All sensitive cache data is encrypted at rest

### Unified Storage

- Single encrypted file: `cache/cache.secure.json`
- Contains all cache types: block reward, wallet balance, and optimized balance
- Atomic operations to prevent corruption
- Thread-safe access with proper locking

### Automatic Migration

- Seamless migration from individual cache files
- Preserves all existing cache data during transition
- Creates backups of original files
- Graceful fallback if encryption fails

---

## CACHE TYPES

The unified cache stores three types of sensitive data:

### 1. Block Reward Cache (`block_reward_cache`)

- Bitcoin addresses being monitored for mining rewards
- Coinbase transaction counts per address
- Block sync heights and scan progress
- **Previously:** `block_reward_cache.json`

### 2. Wallet Balance Cache (`wallet_balance_cache`)

- Wallet addresses with current balances
- XPUB balance summaries
- Address comments and metadata
- **Previously:** `wallet_balance_cache.json`

### 3. Optimized Balance Cache (`optimized_balance_cache`)

- XPUB-derived address caches
- Performance optimization data for balance monitoring
- Gap limit detection results
- **Previously:** `optimized_balance_cache.json`

---

## FILE STRUCTURE

### New Structure (Secure)

```
cache/
  cache.secure.json          All sensitive cache data (encrypted)
  cache_metadata.json        Non-sensitive metadata
  *.migrated_backup          Backup of original files
```

### Old Structure (Deprecated)

```
cache/
  block_reward_cache.json        Plain text (migrated)
  optimized_balance_cache.json   Plain text (migrated)
  wallet_balance_cache.json      Plain text (migrated)
  cache_metadata.json            Still used (non-sensitive)
```

---

## IMPLEMENTATION DETAILS

### Components

#### 1. SecureCacheManager (`secure_cache_manager.py`)

- **Purpose** -- Central manager for all secure cache operations
- **Key Methods:**
  - `get_cache(cache_type)` -- Retrieve cache data for specific type
  - `set_cache(cache_type, data)` -- Update cache data for specific type
  - `get_cache_info()` -- Get cache statistics and status
- **Thread Safety** -- Uses RLock for concurrent access protection

#### 2. BlockRewardCache (`block_reward_cache.py`)

- **Updated** -- Now uses `SecureCacheManager` when available
- **Fallback** -- Individual file cache if secure cache unavailable
- **Migration** -- Automatic detection and use of secure storage

#### 3. WalletBalanceAPI (`wallet_balance_api.py`)

- **Updated** -- Integrates with unified cache for wallet data
- **Compatibility** -- Works with async cache for address derivation
- **Dual Mode** -- Uses both unified cache (wallet data) and async cache (addresses)

### Security Configuration

The unified cache uses the same encryption key as the secure configuration system:

```python
# Encryption key derived from:
# - Raspberry Pi CPU serial number
# - Network interface MAC address
# - System hostname and platform info
# - Additional entropy sources
```

---

## API USAGE

### Basic Cache Operations

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

### Component Integration

```python
from block_reward_cache import BlockRewardCache
from wallet_balance_api import WalletBalanceAPI

# These automatically use secure cache when available
block_cache = BlockRewardCache()  # Uses unified secure cache
wallet_api = WalletBalanceAPI()   # Uses unified secure cache + async cache
```

---


### Performance

- **Atomic Operations** -- Single file reduces I/O operations
- **Caching** -- In-memory cache with periodic encryption saves
- **Thread Safety** -- Proper locking prevents corruption

### Reliability

- **Backup System** -- Automatic backup creation during migration
- **Fallback Mode** -- Graceful degradation if encryption fails
- **Validation** -- Cache structure validation prevents corruption

---

## MONITORING AND TROUBLESHOOTING

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

- `Using unified secure cache` -- Component successfully using secure storage
- `Failed to initialize unified cache` -- Fallback to individual files
- `Migration complete! Migrated X cache files` -- Successful migration
- `Failed to save unified cache` -- Encryption or file write error

---

## FILE EXCLUSIONS

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

---

## COMPATIBILITY

### Requirements

- Python 3.7+
- `cryptography` library (already required for secure config)
- Existing secure configuration system

### Platform Support

- **Raspberry Pi** -- Full encryption with hardware-specific keys
- **Development Systems** -- Compatible encryption with fallback entropy
- **Docker/Containers** -- Works with available system information
