# Unified Cache System

## Overview

mempaper keeps all sensitive cache data — monitored Bitcoin addresses, balances,
XPUB-derived address sets — in a single file, `cache/cache.sensitive.json`,
managed by [`managers/unified_secure_cache.py`](../managers/unified_secure_cache.py).

> **This file is written in clear text by default.** It is `0600`, so other
> users on the device cannot read it, but anyone holding the hardware can.
> Encryption at rest happens only when **Tang is enabled**, and the section
> below explains why that is a deliberate choice rather than a gap.

The `.sensitive.json` suffix marks *what the file contains*, not that it is
encrypted. It is what keeps the file out of Git and out of backups by default.

---

## What protects this file

### By default: filesystem permissions only

Earlier versions encrypted this file under a key derived from the device —
CPU serial, MAC address, hostname. That was removed, because the key was
reconstructible by anyone who had the device the file was on. It cost an
Argon2id derivation at every process start and defended against nothing that
actually happens: an attacker with a copied SD image has the serial numbers too.

Encrypting under a key stored next to the ciphertext is not encryption. Writing
in the clear is the honest description of the same security.

### With Tang enabled: sealed to a key that is not on the device

When `tang_enabled` is set, both this file and `config.sensitive.json` are
sealed via `SecureConfigManager._write_possibly_sealed()` against a
[Tang](https://github.com/latchset/tang) server on your LAN. The key never
touches the SD card, so a device carried off your network cannot decrypt either
file at all.

Two behaviours worth knowing:

- **A sealed file is never silently downgraded.** If Tang is enabled but the
  sealed store cannot be reached, the write raises rather than falling back to
  clear text. Overwriting sealed content with plaintext would be silent,
  permanent, and would remove the protection with nothing to say so.
- **Reads raise `TangLocked`** while the Tang host is unreachable. The app still
  starts; the wallet and donation blocks stay disabled until it returns, then
  restore themselves.

Setup and limits: [Self-Hosting Guide → Tang](SELF_HOSTING_GUIDE.md#part-8--tang-network-bound-encryption-for-wallet-data-optional).

---

## On-disk format

```json
{
  "data":    { "block_reward_cache": {...}, "wallet_balance_cache": {...}, ... },
  "version": "3.0",
  "created": 1765432100.0
}
```

| Envelope `version` | Meaning |
|---|---|
| `3.0` | Current. Payload under `data`, in the clear — or the whole envelope sealed to Tang |
| `2.x` | Legacy. Payload under `encrypted_data`, wrapped with the old device key |

A version-2 file is decrypted once on read using the legacy device key, then
rewritten in the clear (`🔄 Rewriting the cache without device encryption`).
The derivation is lazy — it only ever runs if such a file is actually found —
so a device that has already migrated never pays for it again.

Note that the envelope `version` and the `cache_version` field *inside* `data`
are different things and do not track each other; `cache_version` describes the
shape of the cache payload and is currently `2.0`.

---

## Cache types

| Key | Holds |
|---|---|
| `block_reward_cache` | Addresses monitored for mining rewards, coinbase counts per address, block sync heights and scan progress |
| `wallet_balance_cache` | Wallet addresses with current balances, XPUB balance summaries, address comments and metadata |
| `optimized_balance_cache` | XPUB-derived address caches, gap-limit detection results, balance-monitoring performance data |

---

## Files

```
cache/
  cache.sensitive.json                       All three caches (clear text, or Tang-sealed)
  async_wallet_address_cache.sensitive.json  Derived-address cache
  cache_metadata.json                        Non-sensitive: block height, image paths
```

All are excluded from version control by `.gitignore` (`*.sensitive.json`,
`*.secure.json`, plus the deprecated per-type filenames and `*.migrated_backup`).

---

## Write cadence

Disk writes are debounced by `SAVE_DEBOUNCE_SECONDS` (30 minutes). RAM is always
authoritative, so a crash before a pending write flushes costs one cheap
transaction-history catch-up scan on restart, not data loss. Callers that must
not lose state — `clear_cache`, shutdown — pass `force=True` to write
immediately.

---

## API

```python
from managers.unified_secure_cache import get_unified_cache

cache = get_unified_cache()          # process-wide singleton

block_data  = cache.get_cache("block_reward_cache")
wallet_data = cache.get_cache("wallet_balance_cache")

cache.set_cache("block_reward_cache", updated_data)

info = cache.get_cache_info()
print(cache.is_available(), info.get("file_size"), info.get("last_updated"))
```

Access is guarded by an `RLock`, and writes go through `atomic_write_json` (or
the Tang store), so a crash mid-write cannot leave a truncated file.

### Consumers

| Component | Behaviour |
|---|---|
| [`lib/block_reward_cache.py`](../lib/block_reward_cache.py) | Uses the unified cache when importable, else per-file fallback. Check `block_cache.use_secure_cache` |
| [`lib/wallet_balance_api.py`](../lib/wallet_balance_api.py) | Unified cache for wallet data, async cache for derived addresses. Check `wallet_api.use_unified_cache` |

---

## Log messages

| Message | Meaning |
|---|---|
| `🔄 Rewriting the cache without device encryption` | A legacy version-2 file was found and migrated. Happens once |
| `❌ Failed to save unified cache` | Write failed — disk full, read-only root, or Tang enabled and unreachable |
| `Tang is enabled but the sealed store is unavailable` | Refused to write clear text over a sealed file. Fix the Tang host; nothing was overwritten |

---

## Requirements

- Python 3.7+
- `cryptography` — still required for the Tang seal path and for reading legacy
  version-2 files
- `clevis` — only when `tang_enabled`; see [`apt-requirements.txt`](../apt-requirements.txt)
