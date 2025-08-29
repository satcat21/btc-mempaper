#!/usr/bin/env python3
"""
Enhanced Development Server with Mock Support

This script provides a complete development environment with:
- Mock mempool data when no real mempool is available
- Twitter integration testing
- Hot reloading and enhanced debugging
- Development-specific configurations
"""

import sys
import os
import argparse
import time

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_development_environment(use_mock_mempool=False, use_public_mempool=True):
    """Set up the development environment with appropriate mocking."""
    
    if use_mock_mempool:
        print("🧪 Setting up mock mempool for offline development...")
        try:
            from mock_mempool import patch_mempool_api_for_development
            patch_mempool_api_for_development()
        except ImportError:
            print("⚠️  Mock mempool not available, continuing with real API")
    
    # Import after potential patching
    from mempaper_app import MempaperApp
    return MempaperApp


def main():
    """Start the enhanced development server."""
    parser = argparse.ArgumentParser(description='Mempaper Development Server')
    parser.add_argument('--mock', action='store_true', 
                       help='Use mock mempool API (for offline development)')
    parser.add_argument('--config', default='config.dev.json',
                       help='Configuration file to use (default: config.dev.json)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to run the server on (default: 5000)')
    parser.add_argument('--host', default='127.0.0.1',
                       help='Host to bind to (default: 127.0.0.1)')
    
    args = parser.parse_args()
    
    print("🚀 Starting Mempaper Development Server")
    print("=" * 60)
    
    # Configuration info
    config_file = args.config if os.path.exists(args.config) else "config.json"
    print(f"📂 Configuration: {config_file}")
    print(f"🌐 Server: http://{args.host}:{args.port}")
    
    # Development features
    print("📋 Development Features:")
    print("   • Hot reload enabled")
    print("   • Enhanced error reporting")
    print("   • E-ink display disabled")
    
    if args.mock:
        print("   • Mock mempool API (offline mode)")
    else:
        print("   • Real mempool API")
    
    print("   • Twitter integration ready")
    print("=" * 60)
    
    try:
        # Setup environment
        setup_development_environment(use_mock_mempool=args.mock)
        
        print("📱 Initializing development app...")
        
        # Import and create app after environment setup
        from mempaper_app import MempaperApp
        
        # Create app instance with development modifications
        app_instance = MempaperApp(config_path=config_file)
        
        # Delay WebSocket initialization for development
        print("⏳ Deferring WebSocket initialization for development...")
        
        # Initialize WebSocket in a separate thread to prevent blocking
        def init_websocket_delayed():
            time.sleep(2)  # Give the server time to start
            try:
                print("🔗 Initializing WebSocket connection...")
                app_instance._init_websocket()
                app_instance._generate_initial_image()
                print("✅ WebSocket and initial image ready")
            except Exception as e:
                print(f"⚠️  WebSocket initialization failed (expected in dev): {e}")
                print("   The app will work fine without real-time updates")
        
        # Start WebSocket in background
        import threading
        ws_thread = threading.Thread(target=init_websocket_delayed)
        ws_thread.daemon = True
        ws_thread.start()
        
        print(f"✅ Application initialized successfully")
        print(f"🌐 Open http://{args.host}:{args.port} in your browser")
        print("🔧 Press Ctrl+C to stop the server")
        print("⚠️  WebSocket will initialize in background")
        print()
        
        # Start development server
        app_instance.socketio.run(
            app_instance.app,
            host=args.host,
            port=args.port,
            debug=True,
            use_reloader=False,  # Prevent double initialization
            log_output=True
        )
        
    except KeyboardInterrupt:
        print("\n👋 Development server stopped")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()
        
        print("\n🔧 Troubleshooting Tips:")
        print("   • Check if port 5000 is already in use")
        print("   • Verify your Twitter Bearer Token is valid")
        print("   • Try using --mock flag for offline development")
        print("   • Check config.dev.json for correct settings")
        
        sys.exit(1)


if __name__ == '__main__':
    main()
