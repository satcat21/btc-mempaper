#!/usr/bin/env python3
"""
Secure Configuration Migration Script

Migrates sensitive wallet data from config.json to encrypted secure configuration.
"""

import sys
import os
import json

# Add the parent directory to sys.path to import our modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from secure_config_manager import SecureConfigManager

def migrate_to_secure_config():
    """Migrate wallet addresses from config.json to secure configuration."""
    
    print("🔐 Secure Configuration Migration")
    print("=" * 50)
    
    # Initialize secure config manager
    secure_manager = SecureConfigManager()
    
    # Check if config.json exists
    if not os.path.exists('config.json'):
        print("❌ config.json not found")
        return False
    
    # Load current config
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Check if there are any sensitive fields that need migration
    sensitive_data = {}
    migration_needed = False
    
    # Check for wallet addresses in plain config
    if 'wallet_balance_addresses' in config:
        sensitive_data['wallet_balance_addresses'] = config['wallet_balance_addresses']
        migration_needed = True
        print(f"📋 Found {len(config['wallet_balance_addresses'])} wallet addresses to migrate")
    
    if 'wallet_balance_addresses_with_comments' in config:
        sensitive_data['wallet_balance_addresses_with_comments'] = config['wallet_balance_addresses_with_comments']
        migration_needed = True
        print(f"📝 Found {len(config['wallet_balance_addresses_with_comments'])} commented addresses to migrate")
    
    # Check other sensitive fields
    sensitive_fields = [
        'admin_password_hash',
        'secret_key', 
        'twitter_bearer_token',
        'block_reward_addresses'
    ]
    
    for field in sensitive_fields:
        if field in config:
            sensitive_data[field] = config[field]
            migration_needed = True
            print(f"🔑 Found sensitive field: {field}")
    
    if not migration_needed:
        print("✅ No sensitive data found in config.json - migration not needed")
        return True
    
    print(f"\n🚀 Migrating {len(sensitive_data)} sensitive fields to secure configuration...")
    
    # Save sensitive data to secure config
    success = secure_manager.save_secure_config(sensitive_data)
    
    if not success:
        print("❌ Failed to save secure configuration")
        return False
    
    print("✅ Sensitive data successfully encrypted and saved")
    
    # Create backup of original config
    backup_file = 'config.json.backup'
    import shutil
    shutil.copy2('config.json', backup_file)
    print(f"📄 Backup created: {backup_file}")
    
    # Remove sensitive fields from plain config
    clean_config = config.copy()
    for field in sensitive_data.keys():
        if field in clean_config:
            del clean_config[field]
            print(f"🗑️ Removed {field} from plain config")
    
    # Save cleaned config
    with open('config.json', 'w') as f:
        json.dump(clean_config, f, indent=2)
    
    print("✅ Plain config cleaned of sensitive data")
    
    # Verify the migration worked
    print("\n🔍 Verifying migration...")
    loaded_secure_config = secure_manager.load_secure_config()
    
    if loaded_secure_config:
        verified_fields = []
        for field in sensitive_data.keys():
            if field in loaded_secure_config:
                verified_fields.append(field)
        
        print(f"✅ Verified {len(verified_fields)} fields in secure config:")
        for field in verified_fields:
            if field == 'wallet_balance_addresses' and isinstance(loaded_secure_config[field], list):
                print(f"   📋 {field}: {len(loaded_secure_config[field])} addresses")
            elif field == 'wallet_balance_addresses_with_comments' and isinstance(loaded_secure_config[field], list):
                print(f"   📝 {field}: {len(loaded_secure_config[field])} commented addresses")
            else:
                print(f"   🔑 {field}: [protected]")
    else:
        print("❌ Could not verify secure config")
        return False
    
    print("\n🎉 Migration completed successfully!")
    print("\nNext steps:")
    print("   1. Test your application to ensure it can read from secure config")
    print("   2. If everything works, you can delete config.json.backup")
    print("   3. The sensitive data is now encrypted in config.secure.json")
    
    return True

if __name__ == "__main__":
    if migrate_to_secure_config():
        print("\n✅ Migration successful!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed!")
        sys.exit(1)
