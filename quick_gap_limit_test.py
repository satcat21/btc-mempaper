#!/usr/bin/env python3
"""Quick test of gap limit configuration"""

import json
import os

# Test config settings
with open('config.json', 'r') as f:
    config = json.load(f)

print('🔧 Gap limit configuration:')
print(f'   xpub_enable_gap_limit: {config.get("xpub_enable_gap_limit", "NOT SET")}')
print(f'   xpub_gap_limit_last_n: {config.get("xpub_gap_limit_last_n", "NOT SET")}')
print(f'   xpub_gap_limit_increment: {config.get("xpub_gap_limit_increment", "NOT SET")}')
print(f'   xpub_enable_bootstrap_search: {config.get("xpub_enable_bootstrap_search", "NOT SET")}')
print(f'   xpub_bootstrap_max_addresses: {config.get("xpub_bootstrap_max_addresses", "NOT SET")}')

# Test WalletBalanceAPI
try:
    from wallet_balance_api import WalletBalanceAPI
    api = WalletBalanceAPI(config)

    print()
    print('🔧 WalletBalanceAPI settings:')
    print(f'   enable_gap_limit: {api.enable_gap_limit}')
    print(f'   gap_limit_last_n: {api.gap_limit_last_n}')
    print(f'   gap_limit_increment: {api.gap_limit_increment}')
    print(f'   enable_bootstrap_search: {api.enable_bootstrap_search}')
    print(f'   bootstrap_max_addresses: {api.bootstrap_max_addresses}')

    if api.enable_gap_limit:
        print('✅ Gap limit detection is properly enabled!')
    else:
        print('❌ Gap limit detection is disabled!')
        
except Exception as e:
    print(f'❌ Error testing WalletBalanceAPI: {e}')

# Check cache state
cache_exists = os.path.exists('async_wallet_address_cache.secure.json')
print()
print(f'📁 Async cache exists: {cache_exists}')
if not cache_exists:
    print('✅ Async cache cleared - gap limit detection will run on next startup')
else:
    print('⚠️ Async cache exists - consider clearing it to force gap limit detection')
