#!/usr/bin/env python3
"""
Alternative Gunicorn configuration with simplified static file filtering

This version uses a simpler approach to filter out static meme requests.
"""

import multiprocessing
import os
import logging

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes - optimized for Raspberry Pi Zero WH
workers = 1
worker_class = "gevent"
worker_connections = 100
timeout = 600
keepalive = 2

# Memory management
max_requests = 200
max_requests_jitter = 10

# Logging configuration
loglevel = "debug"
errorlog = "-"

# Custom access logger that filters static meme requests
class FilteredAccessLogger:
    def __init__(self, logger):
        self.logger = logger
    
    def info(self, message, *args, **kwargs):
        # Filter out static meme requests
        if '/static/memes/' not in str(message):
            self.logger.info(message, *args, **kwargs)
    
    def debug(self, message, *args, **kwargs):
        if '/static/memes/' not in str(message):
            self.logger.debug(message, *args, **kwargs)
    
    def warning(self, message, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)

# Configure access logging
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "mempaper_filtered"

# Raspberry Pi Zero optimizations
worker_tmp_dir = "/dev/shm"
tmp_upload_dir = "/dev/shm"
preload_app = False
graceful_timeout = 60
reload = False

def on_starting(server):
    """Initialize custom logging when server starts."""
    # Get the gunicorn access logger
    access_logger = logging.getLogger("gunicorn.access")
    
    # Create a custom filter
    class StaticMemeFilter(logging.Filter):
        def filter(self, record):
            # Return False to filter out (not log) the record
            return '/static/memes/' not in record.getMessage()
    
    # Add the filter to the access logger
    access_logger.addFilter(StaticMemeFilter())
    
    server.log.info("🔧 Static meme request filter enabled")

print("🔧 Filtered Gunicorn configuration loaded")
