#!/usr/bin/env python3

from wallet_balance_api import WalletBalanceAPI
import json

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

# Create API instance
api = WalletBalanceAPI(config)

# Show wallet config
print("Checking wallet configuration...")
if hasattr(api, 'wallets'):
    print(f"Found wallets: {api.wallets}")
else:
    print("No wallets attribute found")

# Check all attributes to find wallets
print("\nWalletBalanceAPI attributes:")
for attr in dir(api):
    if not attr.startswith('_'):
        value = getattr(api, attr)
        if 'xpub' in str(value).lower() or 'zpub' in str(value).lower():
            print(f"{attr}: {value}")
