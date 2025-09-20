#!/usr/bin/env python3
"""
Debug the secure configuration authentication issue.
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secure_config_manager import SecureConfigManager
from config_manager import ConfigManager
from secure_password_manager import SecurePasswordManager
from argon2 import PasswordHasher

def debug_secure_config_auth():
    """Debug what's happening with secure config authentication."""
    
    print("🔍 Debugging secure configuration authentication...")
    
    # Test password
    test_password = "mempaper2025"
    test_username = "admin"
    
    # Initialize managers
    secure_config_manager = SecureConfigManager()
    config_manager = ConfigManager()
    password_manager = SecurePasswordManager(config_manager)
    
    print("\n1. Loading configurations...")
    
    # Check secure config
    secure_config = secure_config_manager.load_secure_config()
    print(f"   Secure config loaded: {secure_config is not None}")
    if secure_config:
        print(f"   Secure config fields: {len(secure_config)}")
        print(f"   Has admin_username: {'admin_username' in secure_config}")
        print(f"   Has admin_password_hash: {'admin_password_hash' in secure_config}")
        if 'admin_password_hash' in secure_config:
            print(f"   Hash starts with: {secure_config['admin_password_hash'][:30]}...")
    
    # Check regular config manager
    current_config = config_manager.get_current_config()
    print(f"   Regular config loaded: {current_config is not None}")
    if current_config:
        print(f"   Regular config fields: {len(current_config)}")
        print(f"   Has admin_username: {'admin_username' in current_config}")
        print(f"   Has admin_password_hash: {'admin_password_hash' in current_config}")
        if 'admin_password_hash' in current_config:
            print(f"   Hash starts with: {current_config['admin_password_hash'][:30]}...")
    
    print("\n2. Testing password manager state...")
    
    # Check if password is set
    is_set = password_manager.is_password_set()
    print(f"   Password manager says password is set: {is_set}")
    
    # Get the hash the password manager is using
    stored_hash = password_manager.config_manager.get('admin_password_hash')
    print(f"   Password manager hash: {stored_hash[:30] if stored_hash else 'None'}...")
    
    print("\n3. Testing hash verification manually...")
    
    if stored_hash:
        ph = PasswordHasher()
        try:
            ph.verify(stored_hash, test_password)
            print(f"   ✅ Manual hash verification: SUCCESS")
        except Exception as e:
            print(f"   ❌ Manual hash verification: FAILED - {e}")
    else:
        print(f"   ❌ No hash to verify")
    
    print("\n4. Testing authentication...")
    
    # Test through password manager
    auth_result = password_manager.authenticate_user(test_username, test_password)
    print(f"   Password manager authentication: {'✅ SUCCESS' if auth_result else '❌ FAILED'}")
    
    print("\n5. Checking username...")
    stored_username = password_manager.config_manager.get('admin_username')
    print(f"   Stored username: '{stored_username}'")
    print(f"   Username match: {test_username == stored_username}")

if __name__ == "__main__":
    debug_secure_config_auth()
