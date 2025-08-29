#!/usr/bin/env python3
"""
Secure Config CLI Tool

Command-line interface for managing encrypted configuration files.
Optimized for Raspberry Pi Zero W with minimal resource usage.

Usage:
    python secure_config_cli.py migrate    # Migrate plain config.json to encrypted
    python secure_config_cli.py status     # Show security status
    python secure_config_cli.py decrypt    # Decrypt and show sensitive data
    python secure_config_cli.py test       # Test encryption/decryption
    python secure_config_cli.py backup     # Create encrypted backup

"""

import sys
import os
import argparse
import json
from secure_config_manager import SecureConfigManager

# Import cache security functions
try:
    from secure_cache_manager import (
        SecureCacheManager, 
        migrate_all_caches, 
        get_all_cache_status,
        patch_wallet_balance_api,
        patch_async_cache_manager
    )
    CACHE_SECURITY_AVAILABLE = True
except ImportError:
    CACHE_SECURITY_AVAILABLE = False


def migrate_config(args):
    """Migrate plain config.json to encrypted format."""
    print("🔄 Migrating configuration to secure format...")
    
    secure_manager = SecureConfigManager()
    
    config_success = secure_manager.migrate_from_plain_config()
    
    # Also migrate cache files if available
    cache_success = True
    if CACHE_SECURITY_AVAILABLE:
        print("\n🗂️ Migrating cache files...")
        migrated_count = migrate_all_caches()
        cache_success = migrated_count >= 0
    
    if config_success and cache_success:
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Verify your application still works with encrypted config")
        print("2. Remove the backup file if everything works: rm config.json.backup")
        print("3. Ensure restrictive file permissions are set")
        print("4. Test cache functionality to ensure encrypted caches work")
        return True
    else:
        print("\n❌ Migration failed!")
        return False


def show_status(args):
    """Show current security status."""
    print("📊 Security Status Check")
    
    secure_manager = SecureConfigManager()
    status = secure_manager.get_security_status()
    
    print(f"\n🔐 Configuration Encryption Status:")
    print(f"   Encryption enabled: {'✅' if status['encryption_enabled'] else '❌'}")
    print(f"   Key file exists: {'✅' if status['key_file_exists'] else '❌'}")
    print(f"   Public config exists: {'✅' if status['public_config_exists'] else '❌'}")
    print(f"   Device fingerprint: {status['device_fingerprint']}")
    
    # Check cache security
    if CACHE_SECURITY_AVAILABLE:
        print(f"\n🗂️ Cache Security Status:")
        cache_status = get_all_cache_status()
        
        for cache_file, info in cache_status.items():
            if info['plain_cache_exists'] or info['encrypted_cache_exists']:
                print(f"   📁 {cache_file}:")
                print(f"      Plain cache: {'⚠️' if info['plain_cache_exists'] else '✅'}")
                print(f"      Encrypted cache: {'✅' if info['encrypted_cache_exists'] else '❌'}")
                
                if info['recommendation']:
                    print(f"      💡 {info['recommendation']}")
    
    # Combine all recommendations
    all_recommendations = status['recommendations'].copy()
    if CACHE_SECURITY_AVAILABLE:
        cache_status = get_all_cache_status()
        for cache_file, info in cache_status.items():
            if info['recommendation']:
                all_recommendations.append(f"Cache: {info['recommendation']}")
    
    if all_recommendations:
        print(f"\n💡 Security Recommendations:")
        for rec in all_recommendations:
            print(f"   • {rec}")
    else:
        print(f"\n✅ No security recommendations - all data is secure!")
    
    # Show file permissions
    print(f"\n📁 File Permissions:")
    files_to_check = [
        ('config.json', 'Public configuration'),
        ('config.secure.json', 'Encrypted configuration'),
        ('.config_key', 'Encryption key salt'),
        ('wallet_address_cache.secure.json', 'Encrypted address cache'),
        ('async_wallet_address_cache.secure.json', 'Encrypted async cache')
    ]
    
    for filename, description in files_to_check:
        if os.path.exists(filename):
            stat = os.stat(filename)
            permissions = oct(stat.st_mode)[-3:]
            secure = "🔒" if permissions in ["600", "400"] else "⚠️"
            print(f"   {secure} {filename}: {permissions} ({description})")
        else:
            print(f"   ❌ {filename}: Not found ({description})")


def decrypt_config(args):
    """Decrypt and display sensitive configuration data."""
    print("🔓 Decrypting sensitive configuration...")
    
    secure_manager = SecureConfigManager()
    config = secure_manager.load_secure_config()
    
    if config is None:
        print("❌ Failed to decrypt configuration")
        return False
    
    # Show only sensitive fields
    sensitive_data = {}
    for field in secure_manager.sensitive_fields:
        if field in config:
            sensitive_data[field] = config[field]
    
    if sensitive_data:
        print(f"\n🔐 Sensitive Configuration Data:")
        print(json.dumps(sensitive_data, indent=2))
    else:
        print(f"\n💡 No sensitive data found in configuration")
    
    return True


def test_encryption(args):
    """Test encryption and decryption functionality."""
    print("🧪 Testing encryption functionality...")
    
    secure_manager = SecureConfigManager()
    
    # Test data
    test_data = {
        "wallet_balance_addresses": ["bc1qtest1", "bc1qtest2"],
        "admin_password_hash": "test_hash_12345",
        "secret_key": "test_secret_key"
    }
    
    try:
        # Test encryption
        print("   🔒 Testing encryption...")
        encrypted = secure_manager._encrypt_data(test_data)
        print(f"      ✅ Encrypted data length: {len(encrypted)} bytes")
        
        # Test decryption
        print("   🔓 Testing decryption...")
        decrypted = secure_manager._decrypt_data(encrypted)
        print(f"      ✅ Decrypted data matches: {decrypted == test_data}")
        
        if decrypted == test_data:
            print("\n✅ Encryption test passed!")
            return True
        else:
            print("\n❌ Encryption test failed - data mismatch!")
            return False
            
    except Exception as e:
        print(f"\n❌ Encryption test failed: {e}")
        return False


def create_backup(args):
    """Create encrypted backup of current configuration."""
    print("💾 Creating encrypted backup...")
    
    secure_manager = SecureConfigManager()
    config = secure_manager.load_secure_config()
    
    if config is None:
        print("❌ Failed to load configuration for backup")
        return False
    
    # Create backup filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"config_backup_{timestamp}.secure.json"
    
    # Create backup with different filename
    backup_manager = SecureConfigManager(backup_file)
    success = backup_manager.save_secure_config(config)
    
    if success:
        print(f"✅ Backup created: {backup_file}")
        return True
    else:
        print(f"❌ Backup creation failed")
        return False


def migrate_cache_command(args):
    """Migrate plain cache files to encrypted format."""
    if not CACHE_SECURITY_AVAILABLE:
        print("❌ Cache security features not available")
        print("Ensure secure_cache_manager.py is present in the project")
        return False
    
    print("🗂️ Migrating cache files to secure format...")
    
    migrated_count = migrate_all_caches()
    
    if migrated_count > 0:
        print(f"✅ Successfully migrated {migrated_count} cache files!")
        print("\nCache files are now encrypted and secure.")
        return True
    elif migrated_count == 0:
        print("ℹ️ No cache files found to migrate")
        return True
    else:
        print("❌ Cache migration failed!")
        return False


def cache_status_command(args):
    """Check and display cache security status."""
    if not CACHE_SECURITY_AVAILABLE:
        print("❌ Cache security features not available")
        print("Ensure secure_cache_manager.py is present in the project")
        return False
    
    print("🗂️ Cache Security Status")
    print("=" * 40)
    
    cache_files = find_cache_files()
    
    if not cache_files:
        print("ℹ️ No cache files found")
        return True
    
    encrypted_count = 0
    plain_count = 0
    
    for cache_file in cache_files:
        if cache_file.endswith('.enc'):
            print(f"🔐 {cache_file} - ENCRYPTED")
            encrypted_count += 1
        else:
            print(f"⚠️  {cache_file} - PLAIN TEXT (VULNERABLE)")
            plain_count += 1
    
    print("\n" + "=" * 40)
    print(f"📊 Summary: {encrypted_count} encrypted, {plain_count} plain text")
    
    if plain_count > 0:
        print("\n⚠️ Security Warning:")
        print(f"Found {plain_count} unencrypted cache files containing sensitive data")
        print("Run 'python secure_config_cli.py migrate-cache' to secure them")
        return False
    else:
        print("\n✅ All cache files are properly encrypted")
        return True


def setup_permissions(args):
    """Set up proper file permissions for security."""
    print("🔐 Setting up secure file permissions...")
    
    files_to_secure = [
        ('.config_key', 0o600, 'Encryption key salt'),
        ('config.secure.json', 0o600, 'Encrypted configuration'),
        ('config.json', 0o644, 'Public configuration')
    ]
    
    for filename, mode, description in files_to_secure:
        if os.path.exists(filename):
            try:
                os.chmod(filename, mode)
                print(f"   ✅ {filename}: {oct(mode)[-3:]} ({description})")
            except Exception as e:
                print(f"   ❌ {filename}: Failed to set permissions - {e}")
        else:
            print(f"   ⚠️ {filename}: File not found ({description})")
    
    print(f"\n✅ File permissions configured for security")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Secure Configuration Manager for BTC Mempaper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python secure_config_cli.py migrate     # Migrate plain config to encrypted
  python secure_config_cli.py status      # Check security status
  python secure_config_cli.py test        # Test encryption functionality
  python secure_config_cli.py backup      # Create encrypted backup
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate plain config.json to encrypted format')
    migrate_parser.set_defaults(func=migrate_config)
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show security status and recommendations')
    status_parser.set_defaults(func=show_status)
    
    # Decrypt command
    decrypt_parser = subparsers.add_parser('decrypt', help='Decrypt and show sensitive configuration')
    decrypt_parser.set_defaults(func=decrypt_config)
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test encryption/decryption functionality')
    test_parser.set_defaults(func=test_encryption)
    
    # Backup command
    backup_parser = subparsers.add_parser('backup', help='Create encrypted backup of configuration')
    backup_parser.set_defaults(func=create_backup)
    
    # Permissions command
    permissions_parser = subparsers.add_parser('permissions', help='Set up secure file permissions')
    permissions_parser.set_defaults(func=setup_permissions)
    
    # Cache migration command
    migrate_cache_parser = subparsers.add_parser(
        'migrate-cache',
        help='Migrate plain cache files to encrypted format'
    )
    migrate_cache_parser.set_defaults(func=migrate_cache_command)
    
    # Cache status command
    cache_status_parser = subparsers.add_parser(
        'cache-status', 
        help='Check cache security status'
    )
    cache_status_parser.set_defaults(func=cache_status_command)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Check for required dependencies
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("❌ Missing required dependency: cryptography")
        print("Install with: pip install cryptography psutil")
        return 1
    
    # Execute command
    try:
        success = args.func(args)
        return 0 if success else 1
    except KeyboardInterrupt:
        print(f"\n⚠️ Operation cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
