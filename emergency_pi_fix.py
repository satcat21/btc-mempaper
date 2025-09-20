#!/usr/bin/env python3
"""
Emergency credential fix for Raspberry Pi.
This bypasses all complex systems and sets credentials directly.
"""

import json
import os
from argon2 import PasswordHasher

def emergency_fix():
    """Emergency fix to set credentials directly in both config files."""
    
    username = "admin"
    password = "mempaper2025"
    
    print("🚨 Emergency credential fix...")
    
    # Create hash
    ph = PasswordHasher()
    password_hash = ph.hash(password)
    
    # Verify hash works
    try:
        ph.verify(password_hash, password)
        print("✅ Hash verified")
    except:
        print("❌ Hash verification failed")
        return False
    
    # Update plain config
    config_path = "config/config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['admin_username'] = username
        config['admin_password_hash'] = password_hash
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Updated {config_path}")
    
    # Also create/update secure config if it exists
    secure_config_path = "config/config.secure.json"
    if os.path.exists(secure_config_path):
        print(f"⚠️ Secure config exists - you may need to delete it: {secure_config_path}")
        print("   Run: rm config/config.secure.json")
    
    print(f"\n✅ Emergency fix complete!")
    print(f"Username: {username}")
    print(f"Password: {password}")
    print(f"Hash: {password_hash[:30]}...")
    
    return True

if __name__ == "__main__":
    emergency_fix()
