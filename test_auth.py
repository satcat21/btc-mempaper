#!/usr/bin/env python3
"""
Test authentication with the set credentials.
"""

import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(__file__))

from secure_password_manager import SecurePasswordManager
from config_manager import ConfigManager

def test_authentication():
    """Test authentication with the credentials we just set"""
    
    username = "admin"
    password = "mempaper2025"
    
    print(f"Testing authentication for: {username}")
    
    try:
        # Initialize the password manager
        config_manager = ConfigManager()
        password_manager = SecurePasswordManager(config_manager)
        
        # Test authentication
        result = password_manager.authenticate_user(username, password)
        
        if result:
            print("✓ AUTHENTICATION SUCCESSFUL!")
            print(f"Username '{username}' and password '{password}' work correctly.")
        else:
            print("✗ Authentication failed")
            
            # Debug information
            stored_username = config_manager.get('admin_username')
            is_password_set = password_manager.is_password_set()
            
            print(f"Stored username: {stored_username}")
            print(f"Username match: {username == stored_username}")
            print(f"Password set: {is_password_set}")
            
    except Exception as e:
        print(f"Error during authentication test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_authentication()
