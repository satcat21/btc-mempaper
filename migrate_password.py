#!/usr/bin/env python3
"""
Migrate cleartext admin password to hashed format.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from secure_password_manager import SecurePasswordManager

def migrate_password():
    """Migrate cleartext password to hashed format."""
    print("🔄 Migrating cleartext password to secure format...")
    
    config_manager = ConfigManager()
    password_manager = SecurePasswordManager(config_manager)
    
    # Attempt migration
    success = password_manager.migrate_cleartext_password()
    
    if success:
        print("✅ Password migration successful!")
        
        # Verify the migration worked
        if password_manager.is_password_set():
            print("✅ Password hash is now properly set!")
            return True
        else:
            print("❌ Migration completed but password hash not found!")
            return False
    else:
        print("❌ Password migration failed!")
        return False

if __name__ == "__main__":
    success = migrate_password()
    sys.exit(0 if success else 1)
