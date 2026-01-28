#!/usr/bin/env python3
"""
PC-optimized startup script for mempaper app
Enables full functionality while keeping config file watching disabled to prevent hanging
"""

import os
import sys

def main():
    """Start the mempaper app with PC optimizations."""
    print("🚀 Starting Mempaper App with PC Optimizations...")
    print("   - E-ink display: DISABLED (PC testing mode)")
    print("   - Initial image generation: ENABLED") 
    print("   - WebSocket: ENABLED")
    print("   - Block monitoring: ENABLED")
    print("   - SocketIO: ENABLED")
    print("   - Config file watching: DISABLED (prevents hanging)")
    print()
    
    try:
        # Import and start the app
        from mempaper_app import MempaperApp
        
        print("📱 Initializing Mempaper application...")
        app_instance = MempaperApp()
        
        print("🌐 Starting Flask web server with full functionality...")
        print("   Access at: http://localhost:5000")
        print("   Admin panel: http://localhost:5000/admin")
        print()
        print("🔗 Quick links:")
        print("   - Dashboard: http://localhost:5000")
        print("   - Current image: http://localhost:5000/image")
        print("   - Config: http://localhost:5000/config")
        print("   - Admin: http://localhost:5000/admin")
        print()
        print("🎯 Ready for testing your three new info blocks:")
        print("   💾 BTC Price & Moscow Time")
        print("   ⚙️ Bitaxe Hashrate & Valid Blocks")
        print("   💼 Wallet Balances & Fiat Values")
        print()
        print("✨ All features enabled - Press Ctrl+C to stop")
        print()
        
        # Start the Flask app (use the app's run method which handles SocketIO being disabled)
        app_instance.run(
            host='0.0.0.0',
            port=5000,
            debug=False
        )
        
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
