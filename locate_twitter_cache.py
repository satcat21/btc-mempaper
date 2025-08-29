#!/usr/bin/env python3
"""
Twitter Cache File Location and Creation Test

This script helps locate and create the Twitter user cache file.
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def show_cache_file_location():
    """Show where the Twitter cache file should be located."""
    print("📍 Twitter User Cache File Location")
    print("=" * 50)
    
    # Get current working directory
    current_dir = os.getcwd()
    cache_file_path = os.path.join(current_dir, "twitter_user_cache.json")
    
    print(f"Expected location: {cache_file_path}")
    print(f"Current directory: {current_dir}")
    
    # Check if file exists
    if os.path.exists(cache_file_path):
        print("✅ Cache file EXISTS")
        
        # Show file info
        stat_info = os.stat(cache_file_path)
        file_size = stat_info.st_size
        print(f"   File size: {file_size} bytes")
        
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            print(f"   Cached entries: {len(cache_data)}")
            
            if cache_data:
                print("   Sample entries:")
                for username, data in list(cache_data.items())[:3]:
                    print(f"     @{username} → {data.get('user_id')}")
        except Exception as e:
            print(f"   ⚠️  Error reading cache: {e}")
    else:
        print("❌ Cache file DOES NOT EXIST")
        print("   This is normal if TwitterAPI hasn't been used yet")
    
    return cache_file_path

def create_test_cache():
    """Create a test cache file to demonstrate functionality."""
    print("\n🧪 Creating Test Cache File")
    print("=" * 40)
    
    cache_file_path = "twitter_user_cache.json"
    
    # Create a sample cache with some test data
    test_cache = {
        "test_user": {
            "user_id": "123456789",
            "timestamp": 1691234567.123
        },
        "another_user": {
            "user_id": "987654321",
            "timestamp": 1691234568.456
        }
    }
    
    try:
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(test_cache, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Test cache file created: {cache_file_path}")
        print(f"   Created {len(test_cache)} test entries")
        
        # Verify it can be read back
        with open(cache_file_path, 'r', encoding='utf-8') as f:
            loaded_cache = json.load(f)
        
        print(f"✅ Cache file verified - loaded {len(loaded_cache)} entries")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create test cache: {e}")
        return False

def test_with_real_api():
    """Test cache creation with real TwitterAPI."""
    print("\n🐦 Testing with Real TwitterAPI")
    print("=" * 40)
    
    try:
        from config_manager import ConfigManager
        from twitter_api import TwitterAPI
        
        # Load config
        config_manager = ConfigManager()
        config = config_manager.get_current_config()
        
        twitter_enabled = config.get("twitter_enabled", False)
        twitter_token = config.get("twitter_bearer_token", "")
        
        if not twitter_enabled:
            print("❌ Twitter is disabled in config")
            return False
            
        if not twitter_token or twitter_token == "000000000000000000000000000000000000000":
            print("❌ No valid Twitter bearer token configured")
            return False
        
        print("🔧 Initializing TwitterAPI...")
        twitter_api = TwitterAPI(twitter_token, config)
        
        print(f"📄 Cache file path: {twitter_api.user_id_cache_path}")
        
        # Check if cache was loaded
        cache_stats = twitter_api.get_cache_stats()
        print(f"📊 Initial cache stats:")
        print(f"   Total cached: {cache_stats['total_cached']}")
        print(f"   Configured users: {cache_stats['configured_users']}")
        print(f"   Coverage: {cache_stats['coverage_percent']:.1f}%")
        
        # Test getting one user ID to trigger cache creation
        print("\n🔍 Testing user ID lookup (will create cache)...")
        test_username = "jack"  # Well-known account
        
        print(f"   Looking up @{test_username}...")
        user_id = twitter_api.get_user_id(test_username)
        
        if user_id:
            print(f"   ✅ Success: @{test_username} → {user_id}")
            print(f"   💾 Cache should now be created/updated")
        else:
            print(f"   ❌ Failed to get user ID for @{test_username}")
        
        # Check if cache file was created
        if os.path.exists(twitter_api.user_id_cache_path):
            print(f"✅ Cache file now exists: {twitter_api.user_id_cache_path}")
        else:
            print(f"❌ Cache file still doesn't exist")
        
        return True
        
    except Exception as e:
        print(f"❌ TwitterAPI test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function."""
    print("🔍 Twitter User Cache File Locator")
    print("=" * 60)
    
    # Show expected location
    cache_path = show_cache_file_location()
    
    # Ask user what they want to do
    print("\n📋 Options:")
    print("1. Create test cache file")
    print("2. Test with real TwitterAPI")
    print("3. Just show location info")
    
    try:
        choice = input("\nEnter choice (1/2/3): ").strip()
        
        if choice == "1":
            create_test_cache()
        elif choice == "2":
            test_with_real_api()
        elif choice == "3":
            print("✅ Location info shown above")
        else:
            print("❌ Invalid choice")
            
    except KeyboardInterrupt:
        print("\n👋 Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
