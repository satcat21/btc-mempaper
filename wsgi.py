#!/usr/bin/env python3
"""
WSGI Entry Point for Mempaper Bitcoin Dashboard

This module provides the WSGI application interface for production
deployment with Gunicorn using gevent workers for better compatibility.
"""

import os
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mempaper_app import create_app, get_socketio

# Create the Flask application instance
application = create_app()

# Export the SocketIO instance for Gunicorn gevent worker
socketio = get_socketio()

if __name__ == "__main__":
    # This allows running the WSGI app directly for testing
    print("🚀 Starting Mempaper via WSGI interface")
    if socketio:
        socketio.run(application, host="0.0.0.0", port=5000, debug=False)
    else:
        application.run(host="0.0.0.0", port=5000, debug=False)
