#!/usr/bin/env python3
"""
Direct Password Fix for Raspberry Pi

This script directly sets the admin password hash in config.json
to bypass all the complex secure configuration issues.
"""

import json
import sys
import os
from argon2 import PasswordHasher

def fix_password_direct():
    print("🔧 Direct password fix for Raspberry Pi...")
    
    # Create password hash
    ph = PasswordHasher()
    password = "mempaper2025"
    password_hash = ph.hash(password)
    
    print(f"✅ Password hashed: {password_hash[:30]}...")
    
    # Add to config.json directly
    config_path = "config/config.json"
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['admin_password_hash'] = password_hash
        
        # Remove cleartext password if it exists
        if 'admin_password' in config:
            del config['admin_password']
            print("🗑️ Removed cleartext password")
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print("✅ Password hash saved to config.json")
        print("🔒 Admin login: admin / mempaper2025")
        
        # Verify the hash was saved
        with open(config_path, 'r') as f:
            verify_config = json.load(f)
        
        if 'admin_password_hash' in verify_config:
            print("✅ Verification: Hash is in config file")
            
            # Test the hash works
            try:
                ph.verify(verify_config['admin_password_hash'], password)
                print("✅ Verification: Hash works correctly")
                return True
            except Exception as e:
                print(f"❌ Hash verification failed: {e}")
                return False
        else:
            print("❌ Hash not found in config file")
            return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = fix_password_direct()
    sys.exit(0 if success else 1)
