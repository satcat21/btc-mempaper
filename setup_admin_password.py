#!/usr/bin/env python3
"""
Admin Password Setup Tool - Permanent Fix

This script will properly set up the admin password and ensure it persists.
"""

import sys
import os
import json

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secure_config_manager import SecureConfigManager
from secure_password_manager import SecurePasswordManager

def setup_permanent_password():
    """Set up a permanent admin password that persists across restarts."""
    print("🔧 Setting up permanent admin password...")
    
    # Initialize managers
    config_manager = SecureConfigManager()
    password_manager = SecurePasswordManager(config_manager)
    
    # Use the default password if none provided
    password = "mempaper2025"
    print(f"🔑 Using password: {password}")
    
    try:
        # Hash the password
        password_hash = password_manager.hash_password(password)
        if not password_hash:
            print("❌ Failed to hash password")
            return False
        
        print(f"✅ Password hashed successfully")
        
        # Get current config
        current_config = config_manager.load_secure_config()
        if not current_config:
            print("⚠️ No secure config found, creating new one...")
            current_config = {}
        
        # Add the password hash
        current_config['admin_password_hash'] = password_hash
        
        # Remove any cleartext password
        if 'admin_password' in current_config:
            del current_config['admin_password']
            print("🗑️ Removed cleartext password")
        
        # Save the secure config
        success = config_manager.save_secure_config(current_config)
        
        if success:
            print("✅ Password saved to secure configuration!")
            
            # Verify it's actually there
            reloaded_config = config_manager.load_secure_config()
            if reloaded_config and 'admin_password_hash' in reloaded_config:
                print("✅ Verification: Password hash is properly stored!")
                print("🔒 Your admin password is now persistent across restarts")
                return True
            else:
                print("❌ Verification failed: Password hash not found after save")
                return False
        else:
            print("❌ Failed to save secure configuration")
            return False
            
    except Exception as e:
        print(f"❌ Error setting up password: {e}")
        return False

def main():
    print("🔧 PERMANENT ADMIN PASSWORD FIX")
    print("=" * 50)
    
    success = setup_permanent_password()
    
    if success:
        print("\n🎉 SUCCESS!")
        print("✅ Admin password is now properly configured")
        print("🚀 You can now start the server without password prompts")
        print("\n📝 Login credentials:")
        print("   Username: admin")
        print("   Password: mempaper2025")
    else:
        print("\n❌ FAILED!")
        print("❌ Password setup was not successful")
        print("💡 You may need to manually add the password during server startup")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
