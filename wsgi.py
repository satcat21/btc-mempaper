#!/usr/bin/env python3
"""
WSGI Entry Point for mempaper Bitcoin Dashboard

This module provides the WSGI application interface for production
deployment with Gunicorn using gevent workers for better compatibility.
"""

# Must be before any other imports when using gevent workers
from gevent import monkey
# Exclude ssl from patching: gevent's ssl C extension uses ARMv7+ instructions
# that cause SIGILL on Pi Zero 1WH (ARMv6). The underlying socket is still
# patched for cooperative I/O; SSL wrapping uses the system OpenSSL instead.
monkey.patch_all(ssl=False)

import os
import sys

# Tell Flask-SocketIO to use gevent mode (matches monkey.patch_all() above)
os.environ.setdefault('FLASK_ENV', 'production')

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mempaper_app import create_app, get_socketio

# Create the Flask application instance
application = create_app()

# Export the SocketIO instance for Gunicorn gevent worker
socketio = get_socketio()

if __name__ == "__main__":
    # This allows running the WSGI app directly for testing
    print("🚀 Starting mempaper via WSGI interface")
    if socketio:
        socketio.run(application, host="0.0.0.0", port=5000, debug=False)
    else:
        application.run(host="0.0.0.0", port=5000, debug=False)
