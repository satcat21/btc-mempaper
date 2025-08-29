#!/usr/bin/env python3
"""
Simple Development Server

A minimal development server that bypasses WebSocket initialization
to prevent hanging during development setup.
"""

import sys
import os
import time

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Start a simple development server."""
    
    print("🚀 Starting Simple Mempaper Development Server")
    print("=" * 60)
    print("📂 Configuration: config.dev.json")
    print("🌐 Server: http://127.0.0.1:5000")
    print("📋 Features: Development mode, no WebSocket blocking")
    print("=" * 60)
    
    try:
        # Import app components
        from mempaper_app import MempaperApp
        
        # Override the initialization to skip WebSocket
        original_init_websocket = MempaperApp._init_websocket
        original_generate_initial = MempaperApp._generate_initial_image
        
        def skip_websocket(self):
            print("⏭️  Skipping WebSocket initialization for development")
            # Create a dummy websocket_client attribute
            self.websocket_client = None
        
        def skip_initial_image(self):
            print("⏭️  Skipping initial image generation for development")
            self.image_is_current = False
        
        # Patch the methods
        MempaperApp._init_websocket = skip_websocket
        MempaperApp._generate_initial_image = skip_initial_image
        
        print("📱 Creating app instance...")
        app_instance = MempaperApp(config_path="config.dev.json")
        
        print("✅ Application initialized successfully")
        print("🌐 Open http://127.0.0.1:5000 in your browser")
        print("🔧 Press Ctrl+C to stop the server")
        print("⚠️  Real-time updates disabled for development")
        print()
        
        # Start development server with simplified configuration
        app_instance.app.run(
            host='127.0.0.1',
            port=5000,
            debug=True,
            use_reloader=False  # Prevent double initialization
        )
        
    except KeyboardInterrupt:
        print("\n👋 Development server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n🔧 Troubleshooting Tips:")
        print("   • Check if port 5000 is already in use")
        print("   • Verify config.dev.json exists and is valid")
        print("   • Try running: python -m flask --app mempaper_app run --debug")
        
        sys.exit(1)


if __name__ == '__main__':
    main()
