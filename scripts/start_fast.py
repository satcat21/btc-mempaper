#!/usr/bin/env python3
"""
Fast startup script for testing mempaper app on PC
Optimized for quick startup without e-ink display dependencies
"""

import os
import sys

def main():
    """Start the mempaper app with fast startup optimizations."""
    print("🚀 Starting Mempaper App with PC Optimizations...")
    print("   - E-ink display: DISABLED (PC testing mode)")
    print("   - Initial image generation: ENABLED") 
    print("   - WebSocket: ENABLED")
    print("   - Block monitoring: ENABLED")
    print("   - SocketIO: ENABLED")
    print("   - Config file watching: DISABLED (prevents hanging)")
    print()
    
    import signal
    def handle_sigint(signum, frame):
        print("\n👋 Shutting down gracefully...")
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sigint)

    try:
        # Import and start the app
        from mempaper_app import MempaperApp

        print("📱 Initializing Mempaper application...")
        app_instance = MempaperApp()

        print("🌐 Starting Flask web server...")
        print("   Access at: http://localhost:5000")
        print("   Admin panel: http://localhost:5000/admin")
        print()
        print("🔗 Quick links:")
        print("   - Dashboard: http://localhost:5000")
        print("   - Current image: http://localhost:5000/current-image")
        print("   - Config: http://localhost:5000/admin/config")
        print()
        print("⚙️ App should start much faster now!")
        print("   Press Ctrl+C to stop")
        print()

        # Start the Flask app (use the app's run method which handles SocketIO being disabled)
        app_instance.run(
            host='0.0.0.0',
            port=5000,
            debug=False
        )

    except Exception as e:
        print(f"❌ Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
