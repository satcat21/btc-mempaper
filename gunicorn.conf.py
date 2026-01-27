#!/usr/bin/env python3
"""
Gunicorn configuration for Mempaper Bitcoin Dashboard

This configuration provides production-ready settings for running
the Mempaper application with Gunicorn WSGI server.
"""

import multiprocessing
import os

# Import privacy utilities for masking Bitcoin addresses in logs
try:
    from utils.privacy_utils import BitcoinPrivacyMasker, mask_bitcoin_data
    PRIVACY_UTILS_AVAILABLE = True
except ImportError:
    PRIVACY_UTILS_AVAILABLE = False
    print("⚠️ Privacy utils not available - Bitcoin addresses will not be masked in logs")

# Custom function to filter out static meme requests from access logs
def should_log_request(req):
    """
    Custom function to determine if a request should be logged.
    Returns False for requests that should be filtered out.
    """
    # Filter out static meme image requests
    if req.path.startswith('/static/memes/'):
        return False
    
    # You can add more filters here if needed:
    # if req.path.startswith('/static/css/'):
    #     return False
    # if req.path.startswith('/static/js/'):
    #     return False
    
    return True

# Apply the filter to access logging
def access_log_filter(record):
    """Filter function for access log records."""
    try:
        # Check if the log message contains static meme requests
        if '/static/memes/' in record.getMessage():
            return False
    except (TypeError, AttributeError):
        # If we can't get the message safely, let it through
        pass
    
    # For Gunicorn access logs, we cannot safely modify the args
    # because they use dictionary-style formatting, not tuple-style
    # The privacy masking will be handled at the application level
    
    return True

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes - optimized for Raspberry Pi Zero WH (single core, 512MB RAM)
workers = 1  # Single worker for single-core CPU
worker_class = "gevent"  # Use standard gevent worker (Flask-SocketIO handles WebSocket natively)
worker_connections = 100  # Reduced for limited RAM
timeout = 600  # Increased timeout for wallet balance gap limit detection (10 minutes)
keepalive = 2

# Restart workers after this many requests, to help control memory usage on Pi Zero
max_requests = 200  # Reduced for Pi Zero to prevent memory leaks
max_requests_jitter = 10  # Reduced jitter

# Logging
loglevel = "error" #"debug"
errorlog = "-"   # Log to stderr

# Disable access logs to prevent formatting errors
# The privacy masking happens at the application level
accesslog = None  # Disable problematic access logs

# Alternative: Simple access logs without complex formatting
# accesslog = "-"
# access_log_format = "%(h)s %(m)s %(U)s %(s)s"  # Simple: IP Method URL Status

# Process naming
proc_name = "mempaper"

# Raspberry Pi Zero WH optimizations
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files (faster than SD card)
tmp_upload_dir = "/dev/shm"  # Use RAM for uploads to avoid SD card wear

# Memory management for Pi Zero (512MB total)
# Keep worker memory usage low
preload_app = False  # Disabled to reduce memory usage
graceful_timeout = 60  # Allow time for graceful shutdown

# Enable auto-restart on code changes (development only)
reload = False

# Security - reduced limits for Pi Zero
limit_request_line = 2048  # Reduced from 4096
limit_request_fields = 50   # Reduced from 100
limit_request_field_size = 4096  # Reduced from 8190

# Custom hooks to implement request filtering and privacy masking
def pre_request(worker, req):
    """Called before each request is processed."""
    # Store whether this request should be logged
    req.should_log = should_log_request(req)
    
    # Mask Bitcoin addresses in the request URL for debugging
    if PRIVACY_UTILS_AVAILABLE and hasattr(req, 'uri') and req.uri:
        req.masked_uri = BitcoinPrivacyMasker.mask_url(req.uri)
    else:
        req.masked_uri = getattr(req, 'uri', 'unknown')

def post_request(worker, req, environ, resp):
    """Called after each request is processed."""
    # Only log if the request should be logged
    if hasattr(req, 'should_log') and not req.should_log:
        # Suppress access log for this request
        return
    
    # Custom privacy-aware logging for important requests
    if PRIVACY_UTILS_AVAILABLE and hasattr(req, 'masked_uri'):
        status = getattr(resp, 'status_code', 'unknown')
        method = environ.get('REQUEST_METHOD', 'unknown')
        remote_addr = environ.get('REMOTE_ADDR', 'unknown')
        
        # Only log if not a static meme request
        if '/static/memes/' not in req.masked_uri:
            pass  # Let the standard access log handle it with our filter

# Alternative approach: Configure logging with custom filter
def on_starting(server):
    """Called when the server starts.""" 
    server.log.info("🔧 Access logs disabled to prevent formatting conflicts")
    server.log.info("� Request logging handled at application level with privacy masking")
    
    if PRIVACY_UTILS_AVAILABLE:
        server.log.info("🔒 Bitcoin address privacy masking enabled in application logs")
        server.log.info("🔒 Privacy format: address[:6]...address[-6:] (e.g., bc1qeu...l9lg7c)")
    else:
        server.log.warning("⚠️ Privacy masking disabled - Bitcoin addresses may appear in application logs")

# SSL/TLS (uncomment and configure for HTTPS)
# keyfile = "/path/to/private.key"
# certfile = "/path/to/certificate.crt"
# ssl_version = 2  # SSLv2
# cert_reqs = 0    # CERT_NONE
# ca_certs = None
# suppress_ragged_eofs = True

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("🚀 Mempaper Gunicorn server is ready!")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("⚠️ Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info(f"🔄 Worker {worker.pid} is being forked")

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"✅ Worker {worker.pid} has been forked")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal."""
    worker.log.info(f"❌ Worker {worker.pid} received SIGABRT signal")
