#!/usr/bin/env python3
"""
Migration script to set up secure password authentication.

This script will initialize the secure password system for the BTC Mempaper
application, allowing you to set a secure password that will be hashed
with Argon2id encryption.
"""

import os
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from secure_password_manager import SecurePasswordManager

def main():
    """Run the secure password setup."""
    print("🔐 BTC Mempaper Secure Password Setup")
    print("=" * 50)
    
    config_path = "config.json"
    
    try:
        # Initialize configuration manager
        print("📄 Loading configuration...")
        config_manager = ConfigManager(config_path)
        
        # Initialize secure password manager
        password_manager = SecurePasswordManager(config_manager)
        
        # Check current password status
        if password_manager.is_password_set():
            print("✅ Secure password is already configured.")
            print("🔒 Your password is protected with Argon2id encryption.")
            
            # Test authentication with current settings
            print("\nTo verify your setup works, you can test authentication when you start the app.")
            return 0
        
        print("🆕 No secure password found. Starting first-time setup...")
        
        # Run first-time password setup
        setup_success = password_manager.setup_first_time_password()
        
        if setup_success:
            print("\n" + "=" * 60)
            print("🎉 Secure password setup completed successfully!")
            print("✅ Your password is now protected with Argon2id encryption.")
            print("🔒 The password hash has been saved to your config file.")
            print("🚫 Your cleartext password has been removed for security.")
            print("\nNext time you start the application, you will be")
            print("prompted to enter this password for authentication.")
            print("=" * 60)
            return 0
        else:
            print("\n❌ Password setup failed or was cancelled.")
            print("🔄 You can run this script again to try setting up a password.")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error during password setup: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
