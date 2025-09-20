#!/usr/bin/env python3
"""
Script to clean the secure configuration and ensure only sensitive data is encrypted.
"""

import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secure_config_manager import SecureConfigManager

def main():
    print("🧹 Cleaning secure configuration...")
    print("=" * 50)
    
    # Initialize secure config manager
    secure_manager = SecureConfigManager("config/config.json")
    
    # Check current status
    print("\n📋 Current secure config status:")
    
    # Clean the secure config
    print("\n🔧 Starting cleanup process...")
    success = secure_manager.clean_secure_config()
    
    if success:
        print("\n🎉 Cleanup completed successfully!")
        print("\n📝 Summary:")
        print("   ✅ Only sensitive fields are now in the encrypted config")
        print("   ✅ All non-sensitive fields are in the plain config.json")
        print("   ✅ No data duplication between files")
    else:
        print("\n❌ Cleanup failed!")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)