#!/usr/bin/env python3
"""
Optimized Production Server for mempaper Bitcoin Dashboard

This script starts the application in production mode with optimizations:
- No debug mode (prevents double initialization)
- Optimized startup sequence
- Better error handling
- Uses singleton pattern to prevent duplicate initialization
"""

import sys
import os

# Fix Unicode encoding for Windows terminals
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mempaper_app import get_app_instance

def main():
    """Start the mempaper application in production mode."""
    print("🚀 Starting mempaper Bitcoin Dashboard (Production Mode)")
    print("=" * 60)
    
    try:
        # Get the singleton app instance (prevents double initialization)
        app = get_app_instance()
        
        # Start the server (no debug mode for faster startup)
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False  # Important: no debug mode in production
        )
        
    except KeyboardInterrupt:
        print("\n👋 mempaper application stopped by user")
    except Exception as e:
        print(f"❌ Failed to start mempaper application: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
