#!/usr/bin/env python3
"""
Debug Development Server

This script helps identify what's causing the app to hang during initialization.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config_loading():
    """Test configuration loading."""
    print("1️⃣ Testing configuration loading...")
    try:
        from config_manager import ConfigManager
        config_manager = ConfigManager("config.dev.json")
        config = config_manager.get_current_config()
        print(f"   ✅ Config loaded: {len(config)} settings")
        return config_manager, config
    except Exception as e:
        print(f"   ❌ Config loading failed: {e}")
        return None, None

def test_api_clients(config):
    """Test API client initialization."""
    print("2️⃣ Testing API clients...")
    
    # Test Twitter API
    try:
        twitter_enabled = config.get("twitter_enabled", True)
        print(f"   Twitter enabled: {twitter_enabled}")
        if twitter_enabled:
            from twitter_api import TwitterAPI
            twitter_token = config.get("twitter_bearer_token", "")
            if twitter_token:
                twitter_api = TwitterAPI(twitter_token, config)
                print("   ✅ Twitter API initialized")
            else:
                print("   ⚠️  No Twitter token configured")
        else:
            print("   ⏭️  Twitter API disabled")
    except Exception as e:
        print(f"   ❌ Twitter API failed: {e}")
    
    # Test Mempool API
    try:
        from mempool_api import MempoolAPI
        mempool_ip = config.get("mempool_ip", "127.0.0.1")
        mempool_rest_port = config.get("mempool_rest_port", "4081")
        print(f"   Mempool target: {mempool_ip}:{mempool_rest_port}")
        mempool_api = MempoolAPI(mempool_ip, mempool_rest_port)
        print("   ✅ Mempool API initialized")
    except Exception as e:
        print(f"   ❌ Mempool API failed: {e}")

def test_flask_app():
    """Test Flask app creation."""
    print("3️⃣ Testing Flask app...")
    try:
        from flask import Flask
        app = Flask(__name__, static_folder="static")
        print("   ✅ Flask app created")
        return app
    except Exception as e:
        print(f"   ❌ Flask app failed: {e}")
        return None

def test_image_renderer(config):
    """Test image renderer."""
    print("4️⃣ Testing image renderer...")
    try:
        from translations import translations
        from image_renderer import ImageRenderer
        
        lang = config.get("language", "en")
        trans = translations.get(lang, translations["en"])
        renderer = ImageRenderer(config, trans)
        print("   ✅ Image renderer initialized")
    except Exception as e:
        print(f"   ❌ Image renderer failed: {e}")

def main():
    """Run diagnostic tests."""
    print("🔍 Mempaper Development Diagnostics")
    print("=" * 50)
    
    # Test each component individually
    config_manager, config = test_config_loading()
    if not config:
        return
    
    test_api_clients(config)
    app = test_flask_app()
    test_image_renderer(config)
    
    print("=" * 50)
    print("✅ All basic components tested")
    print("🌐 If all tests passed, the issue is likely in the full app initialization")

if __name__ == '__main__':
    main()
