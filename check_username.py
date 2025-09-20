#!/usr/bin/env python3
"""
Quick script to check what username is stored in the config.
"""

import json
import os

def check_username():
    """Check the stored admin username"""
    
    # Check config.json
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.json')
    
    if os.path.exists(config_path):
        print(f"Reading config from: {config_path}")
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            admin_username = config.get('admin_username')
            admin_password_hash = config.get('admin_password_hash')
            
            print(f"Admin username: {admin_username}")
            print(f"Password hash exists: {bool(admin_password_hash)}")
            if admin_password_hash:
                print(f"Password hash starts with: {admin_password_hash[:20]}...")
            
            # Also check for any other relevant settings
            for key in config.keys():
                if 'admin' in key.lower() or 'password' in key.lower() or 'auth' in key.lower():
                    if 'password' in key.lower() and 'hash' not in key.lower():
                        print(f"{key}: [REDACTED]")
                    else:
                        print(f"{key}: {config[key]}")
                        
        except Exception as e:
            print(f"Error reading config: {e}")
    else:
        print(f"Config file not found at: {config_path}")

if __name__ == "__main__":
    check_username()
