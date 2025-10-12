#!/usr/bin/env python3
"""
Script to verify and display the separation of sensitive vs non-sensitive config data.
"""

import sys
import os
import json

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secure_config_manager import SecureConfigManager

def main():
    print("🔍 Configuration Data Separation Verification")
    print("=" * 60)
    
    # Check plain config.json
    plain_config_path = "config/config.json"
    if os.path.exists(plain_config_path):
        with open(plain_config_path, 'r') as f:
            plain_config = json.load(f)
        print(f"\n📄 Plain config.json contains {len(plain_config)} fields:")
        for key in sorted(plain_config.keys()):
            print(f"   • {key}")
    else:
        print("\n❌ Plain config.json not found!")
        plain_config = {}
    
    # Check encrypted config
    secure_manager = SecureConfigManager("config/config.json")
    encrypted_config_path = "config/config.secure.json"
    if os.path.exists(encrypted_config_path):
        with open(encrypted_config_path, 'r') as f:
            encrypted_file = json.load(f)
        
        if encrypted_file.get('_encrypted'):
            decrypted_data = secure_manager._decrypt_data(encrypted_file['data'])
            if decrypted_data:
                print(f"\n🔐 Encrypted config.secure.json contains {len(decrypted_data)} fields:")
                for key in sorted(decrypted_data.keys()):
                    print(f"   • {key}")
            else:
                print("\n❌ Failed to decrypt secure config!")
                return False
        else:
            print("\n❌ Secure config file is not encrypted!")
            return False
    else:
        print("\n📝 No encrypted config found (this is normal if no sensitive data is configured)")
        decrypted_data = {}
    
    # Check for overlaps
    if plain_config and decrypted_data:
        overlap = set(plain_config.keys()) & set(decrypted_data.keys())
        if overlap:
            print(f"\n⚠️ WARNING: Found {len(overlap)} duplicate fields in both configs:")
            for key in sorted(overlap):
                print(f"   ! {key}")
        else:
            print(f"\n✅ Perfect separation! No duplicate fields between configs.")
    
    # Summary
    print(f"\n📊 Summary:")
    print(f"   📄 Plain config fields: {len(plain_config)}")
    print(f"   🔐 Encrypted fields: {len(decrypted_data) if decrypted_data else 0}")
    print(f"   📝 Total fields: {len(plain_config) + (len(decrypted_data) if decrypted_data else 0)}")
    
    # Verify sensitive fields are encrypted
    sensitive_fields = {'wallet_balance_addresses_with_comments', 
                        'block_reward_addresses_table', 'admin_password_hash', 'secret_key'}
    print(f"\n🔒 Sensitive field verification:")
    for field in sensitive_fields:
        in_plain = field in plain_config
        in_encrypted = field in (decrypted_data or {})
        
        if in_plain and not in_encrypted:
            print(f"   ⚠️ {field}: In plain config (should be encrypted!)")
        elif not in_plain and in_encrypted:
            print(f"   ✅ {field}: Properly encrypted")
        elif in_plain and in_encrypted:
            print(f"   ⚠️ {field}: In BOTH configs (duplicate!)")
        else:
            print(f"   📝 {field}: Not configured (OK)")
    
    print(f"\n🎉 Verification complete!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)