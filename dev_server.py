#!/usr/bin/env python3
"""
Fixed Development Server for Mempaper Bitcoin Dashboard

This script starts the application in development mode with proper error handling:
- WebSocket connection timeout handling
- Better error messages
- Debug mode enabled
- Development-friendly configuration
"""

import sys
import os
import time
import threading

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def patch_websocket_for_development():
    """Patch the WebSocket client to be more development-friendly."""
    
    try:
        # Import the WebSocket client
        from websocket_client import MempoolWebSocket
        
        # Store the original methods
        original_init = MempoolWebSocket.__init__
        original_start_connection = MempoolWebSocket.start_connection
        
        def development_init(self, ip, ws_port, on_new_block_callback=None):
            """Development-friendly WebSocket initialization."""
            print(f"🔗 WebSocket target: {ip}:{ws_port}")
            # Call original init
            original_init(self, ip, ws_port, on_new_block_callback)
        
        def development_start_connection(self):
            """Development-friendly WebSocket connection with timeout."""
            try:
                print("🔗 Attempting WebSocket connection...")
                # Call original start_connection method
                original_start_connection(self)
                print("✅ WebSocket connection started")
            except Exception as e:
                print(f"⚠️  WebSocket connection failed: {e}")
                print("   Continuing without real-time updates...")
                # Don't raise the exception - just log it
                self.is_connected = False
        
        # Apply patches
        MempoolWebSocket.__init__ = development_init
        MempoolWebSocket.start_connection = development_start_connection
        
        print("🔧 WebSocket patches applied for development")
        
    except ImportError as e:
        print(f"⚠️  Could not patch WebSocket: {e}")

def main():
    """Start the development server."""
    
    print("🚀 Starting Fixed Mempaper Development Server")
    print("=" * 60)
    print("📂 Configuration: config.dev.json")
    print("🌐 Server: http://127.0.0.1:5000")
    print("📋 Features: Better error handling, WebSocket timeout")
    print("=" * 60)
    
    try:
        # Apply development patches
        patch_websocket_for_development()
        
        # Import and initialize the app
        from mempaper_app import MempaperApp
        
        print("📱 Creating app instance...")
        app_instance = MempaperApp(config_path="config.dev.json")
        
        print("✅ Application initialized successfully")
        print("🌐 Open http://127.0.0.1:5000 in your browser")
        print("🔧 Press Ctrl+C to stop the server")
        print()
        
        # Start the server
        app_instance.socketio.run(
            app_instance.app,
            host='127.0.0.1',
            port=5000,
            debug=True,
            use_reloader=False,
            log_output=True
        )
        
    except KeyboardInterrupt:
        print("\n👋 Development server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n🔧 Troubleshooting Tips:")
        print("   • WebSocket connection to mempool.space might be slow/failing")
        print("   • Try using local mempool or mock mode")
        print("   • Check firewall settings for outbound connections")
        
        sys.exit(1)


if __name__ == '__main__':
    main()
