#!/usr/bin/env python3
"""
Gunicorn configuration for Mempaper Bitcoin Dashboard - Fallback Mode

This configuration uses threading mode which works without gevent.
Use this as a backup if gevent installation fails.
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 1024

# Worker processes - Pi Zero optimized, threading mode
workers = 1  # Single worker for single-core CPU
worker_class = "sync"  # Uses threading, no gevent required
timeout = 120  # Increased timeout for slower CPU
keepalive = 2

# Restart workers after this many requests, to help control memory usage on Pi Zero
max_requests = 200  # Reduced for Pi Zero to prevent memory leaks
max_requests_jitter = 10  # Reduced jitter

# Logging
loglevel = "info"
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "mempaper-fallback"

# Raspberry Pi Zero WH optimizations
worker_tmp_dir = "/dev/shm"  # Use RAM for temp files (faster than SD card)
tmp_upload_dir = "/dev/shm"  # Use RAM for uploads to avoid SD card wear

# Memory management for Pi Zero (512MB total)
# Keep worker memory usage low
preload_app = False  # Disabled to reduce memory usage
graceful_timeout = 60  # Allow time for graceful shutdown

# Security - reduced limits for Pi Zero
limit_request_line = 2048  # Reduced from 4096
limit_request_fields = 50   # Reduced from 100
limit_request_field_size = 4096  # Reduced from 8190

# Enable auto-restart on code changes (development only)
reload = False

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("🚀 Mempaper Gunicorn server is ready! (Fallback/Threading Mode)")

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
