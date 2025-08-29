#!/usr/bin/env python3
"""
Address Derivation Diagnostic Script

Check what addresses are being generated and verify the derivation algorithm.
"""

import sys
import os
import json

# Add the parent directory to sys.path to import our modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from address_derivation import AddressDerivation
from wallet_balance_api import WalletBalanceAPI

def test_address_derivation():
    """Test address derivation with both XPUB and ZPUB."""
    
    print("🔍 Address Derivation Diagnostic")
    print("=" * 50)
    
    derivation = AddressDerivation()
    
    # Test ZPUB (should generate bc1... addresses)
    zpub = "zpub6rrfVgQUrywTwGz4UsqEkxKQa6TZsYWkC8hPatX65BfEuWhY6XiBe6W1mVbRhSaVRVYYkRkQ7AFopBVXNJaLuxMGwVvje5D1F3vWKCeromk"
    
    print(f"\n🧪 Testing ZPUB derivation:")
    print(f"   ZPUB: {zpub[:20]}...{zpub[-20:]}")
    
    try:
        addresses = derivation.derive_addresses(zpub, 5)
        print(f"   Generated {len(addresses)} addresses:")
        for addr, idx in addresses:
            address_type = "Native SegWit (bc1)" if addr.startswith("bc1") else "Legacy (1)" if addr.startswith("1") else "Unknown"
            print(f"      {idx}: {addr[:10]}...{addr[-10:]} ({address_type})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test XPUB (should generate 1... addresses)
    xpub = "xpub6CUGRUonZSQ4TWtTMmzXdrXDtypWKiKrhko4egpiMZbpiaQL2jkwSB1icqYh2cfDfVxdx4df189oLKnC5fSwqPfgyP3hooxujYzAu3fDVmz"
    
    print(f"\n🧪 Testing XPUB derivation:")
    print(f"   XPUB: {xpub[:20]}...{xpub[-20:]}")
    
    try:
        addresses = derivation.derive_addresses(xpub, 5)
        print(f"   Generated {len(addresses)} addresses:")
        for addr, idx in addresses:
            address_type = "Native SegWit (bc1)" if addr.startswith("bc1") else "Legacy (1)" if addr.startswith("1") else "Unknown"
            print(f"      {idx}: {addr[:10]}...{addr[-10:]} ({address_type})")
    except Exception as e:
        print(f"   ❌ Error: {e}")

def check_wallet_api_configuration():
    """Check what the wallet API is actually using."""
    
    print(f"\n🔧 Checking WalletBalanceAPI Configuration")
    print("=" * 50)
    
    # Load config
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Check for wallet addresses in various places
    config_addresses = config.get("wallet_balance_addresses", [])
    config_comments = config.get("wallet_balance_addresses_with_comments", [])
    
    print(f"📄 Config.json wallet_balance_addresses: {len(config_addresses)}")
    for addr in config_addresses:
        key_type = "ZPUB" if addr.startswith("zpub") else "XPUB" if addr.startswith("xpub") else "Address"
        print(f"   {key_type}: {addr[:20]}...{addr[-20:]}")
    
    print(f"📝 Config.json wallet_balance_addresses_with_comments: {len(config_comments)}")
    for entry in config_comments:
        if isinstance(entry, dict):
            addr = entry.get("address", "")
            key_type = "ZPUB" if addr.startswith("zpub") else "XPUB" if addr.startswith("xpub") else "Address"
            print(f"   {key_type}: {addr[:20]}...{addr[-20:]}")
    
    # Test the API
    print(f"\n🤖 Testing WalletBalanceAPI:")
    try:
        api = WalletBalanceAPI(config)
        entries_with_comments, user_addresses, user_xpubs = api._parse_wallet_entries()
        
        print(f"   📋 Parsed entries: {len(entries_with_comments)}")
        print(f"   🏠 User addresses: {len(user_addresses)}")
        print(f"   🔑 User XPUBs: {len(user_xpubs)}")
        
        for xpub in user_xpubs:
            key_type = "ZPUB" if xpub.startswith("zpub") else "XPUB" if xpub.startswith("xpub") else "Unknown"
            print(f"      {key_type}: {xpub[:20]}...{xpub[-20:]}")
            
            # Test derivation with this key
            derivation = AddressDerivation()
            test_addresses = derivation.derive_addresses(xpub, 3)
            print(f"         First 3 addresses:")
            for addr, idx in test_addresses:
                address_type = "bc1" if addr.startswith("bc1") else "1" if addr.startswith("1") else "?"
                print(f"           {idx}: {addr} ({address_type})")
        
    except Exception as e:
        print(f"   ❌ Error: {e}")

def check_secure_config():
    """Check if secure config contains wallet addresses."""
    
    print(f"\n🔒 Checking Secure Configuration")
    print("=" * 50)
    
    # Check secure config template
    if os.path.exists('secure_config_template.json'):
        print("📄 Found secure_config_template.json:")
        with open('secure_config_template.json', 'r') as f:
            secure_template = json.load(f)
        
        template_addresses = secure_template.get("wallet_balance_addresses", [])
        for addr in template_addresses:
            key_type = "ZPUB" if addr.startswith("zpub") else "XPUB" if addr.startswith("xpub") else "Address"
            print(f"   {key_type}: {addr[:20]}...{addr[-20:]}")
    
    # Check for actual secure config file
    if os.path.exists('config.secure.json'):
        print("🔐 Found config.secure.json (encrypted)")
    else:
        print("⚠️ No config.secure.json found")

if __name__ == "__main__":
    test_address_derivation()
    check_wallet_api_configuration()
    check_secure_config()
    
    print(f"\n💡 Analysis:")
    print("   If you see Legacy (1...) addresses in your logs but expect Native SegWit (bc1...):")
    print("   1. Check if you're using an XPUB instead of a ZPUB")
    print("   2. Verify the wallet configuration is being read correctly")
    print("   3. Ensure the ZPUB is in the right configuration location")
