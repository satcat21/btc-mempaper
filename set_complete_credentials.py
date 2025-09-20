#!/usr/bin/env python3
"""
Complete script to set admin credentials and verify authentication.
This script properly integrates with the secure configuration system.
"""

import json
import os
import sys
import argon2
from argon2 import PasswordHasher

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def set_admin_credentials():
    """Set admin username and password hash using the secure configuration system"""
    
    # Configuration
    username = "admin"
    password = "mempaper2025"
    
    print(f"🔧 Setting up admin credentials using secure configuration system...")
    print(f"   Username: {username}")
    print(f"   Password: {password}")
    
    try:
        # Import the secure configuration system
        from secure_config_manager import SecureConfigManager
        from config_manager import ConfigManager
        
        # Initialize the secure config manager
        config_manager = SecureConfigManager()
        regular_config_manager = ConfigManager()
        
        print("✓ Secure configuration system initialized")
        
        # Create password hash
        ph = PasswordHasher()
        password_hash = ph.hash(password)
        print(f"✓ Generated password hash: {password_hash[:30]}...")
        
        # Verify the hash works immediately
        try:
            ph.verify(password_hash, password)
            print("✓ Password hash verification successful")
        except:
            print("❌ Password hash verification failed")
            return False
        
        # Load current secure config
        current_config = config_manager.load_secure_config() or {}
        print(f"✓ Loaded secure config with {len(current_config)} fields")
        
        # Set credentials in secure config
        current_config['admin_username'] = username
        current_config['admin_password_hash'] = password_hash
        
        # Save to secure config
        success = config_manager.save_secure_config(current_config)
        if success:
            print("✓ Saved credentials to secure configuration")
        else:
            print("❌ Failed to save to secure configuration")
            return False
        
        # Also ensure plain config has the username but NOT the hash
        plain_config_path = os.path.join(os.path.dirname(__file__), 'config', 'config.json')
        if os.path.exists(plain_config_path):
            with open(plain_config_path, 'r') as f:
                plain_config = json.load(f)
            
            # Set username in plain config
            plain_config['admin_username'] = username
            
            # Remove password hash from plain config if it exists
            if 'admin_password_hash' in plain_config:
                del plain_config['admin_password_hash']
                print("✓ Removed password hash from plain config (moved to secure config)")
            
            # Save plain config
            with open(plain_config_path, 'w') as f:
                json.dump(plain_config, f, indent=2)
            print("✓ Updated plain config with username only")
        
        # Test authentication
        print("\n🔐 Testing authentication...")
        from secure_password_manager import SecurePasswordManager
        
        password_manager = SecurePasswordManager(regular_config_manager)
        auth_result = password_manager.authenticate_user(username, password)
        
        if auth_result:
            print("✅ Authentication test PASSED!")
        else:
            print("❌ Authentication test FAILED!")
            return False
        
        print("\n" + "="*60)
        print("CREDENTIALS SET SUCCESSFULLY")
        print("="*60)
        print(f"Username: {username}")
        print(f"Password: {password}")
        print("✓ Credentials stored in secure encrypted configuration")
        print("✓ Authentication verified working")
        print("✓ Ready for production use")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"❌ Error setting up credentials: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = set_admin_credentials()
    if success:
        print("\n🎉 Setup completed successfully!")
        print("You can now login with the credentials above.")
    else:
        print("\n💥 Setup failed!")
        print("Please check the error messages above.")
    
    sys.exit(0 if success else 1)
