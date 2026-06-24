#!/usr/bin/env python3
"""
Gunicorn configuration for mempaper Bitcoin Dashboard

Production-ready settings for running the mempaper application
with Gunicorn WSGI server on Raspberry Pi Zero WH.
"""

import os

# Import privacy utilities for masking Bitcoin addresses in logs
try:
    from utils.privacy_utils import BitcoinPrivacyMasker
    PRIVACY_UTILS_AVAILABLE = True
except ImportError:
    PRIVACY_UTILS_AVAILABLE = False
    print("⚠️ Privacy utils not available - Bitcoin addresses will not be masked in logs")

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes - optimized for Raspberry Pi Zero WH (single core, 512MB RAM)
workers = 1  # Single worker for single-core CPU
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"  # Required for WebSocket upgrade support
worker_connections = 100  # Reduced for limited RAM
timeout = 600  # Increased timeout for wallet balance gap limit detection (10 minutes)
keepalive = 2

# Restart workers after this many requests, to help control memory usage on Pi Zero
max_requests = 1000  # Increased - Pi Zero memory usage is stable at ~67MB
max_requests_jitter = 50  # Increased jitter

# Logging
loglevel = "error" #"debug"
errorlog = "-"   # Log to stderr

# Disable access logs to prevent formatting errors
# The privacy masking happens at the application level
accesslog = None

# Process naming
proc_name = "mempaper"

# Raspberry Pi Zero WH optimizations
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files (faster than SD card)
tmp_upload_dir = "/dev/shm"  # Use RAM for uploads to avoid SD card wear

# Memory management for Pi Zero (512MB total)
# Keep worker memory usage low
preload_app = False  # Disabled to reduce memory usage
graceful_timeout = 5  # Quick shutdown — WebSocket clients reconnect automatically

# Enable auto-restart on code changes (development only)
reload = False

# Security - reduced limits for Pi Zero
limit_request_line = 2048  # Reduced from 4096
limit_request_fields = 50   # Reduced from 100
limit_request_field_size = 4096  # Reduced from 8190

# Privacy masking hook
def pre_request(worker, req):
    """Mask Bitcoin addresses in request URLs for logging."""
    if PRIVACY_UTILS_AVAILABLE and hasattr(req, 'uri') and req.uri:
        req.masked_uri = BitcoinPrivacyMasker.mask_url(req.uri)
    else:
        req.masked_uri = getattr(req, 'uri', 'unknown')

def on_starting(server):
    """Called when the server starts."""
    if PRIVACY_UTILS_AVAILABLE:
        server.log.info("Bitcoin address privacy masking enabled")
