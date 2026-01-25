# Gunicorn Configuration for Mempaper Bitcoin Dashboard
# This configuration is optimized for production deployment on Raspberry Pi

import gevent
import gevent.monkey
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:5000"
backlog = 2048

# Worker processes
# Using 2 workers for Raspberry Pi (4 cores * 0.5 + 1)
workers = 2
worker_class = "geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
worker_connections = 500

# Worker process management
max_requests = 1000
max_requests_jitter = 50
preload_app = True
timeout = 120
keepalive = 2

# Restart workers after this many requests, to help prevent memory leaks
max_requests = 1000

# Number of pending connections
backlog = 2048

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance tuning for Raspberry Pi
worker_tmp_dir = '/dev/shm'  # Use RAM for worker temp files

# Logging
errorlog = '-'
loglevel = 'info'
accesslog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'mempaper-btc-dashboard'

# Server mechanics
daemon = False
pidfile = '/tmp/mempaper.pid'
user = None
group = None
tmp_upload_dir = None

# SSL (disabled for local deployment)
# keyfile = None
# certfile = None

def when_ready(server):
    """Called just after the server is started."""
    print("🚀 Mempaper Bitcoin Dashboard server is ready")
    print(f"   Workers: {workers}")
    print(f"   Worker Class: {worker_class}")
    print(f"   Listening on: {bind}")

def worker_int(worker):
    """Called just after a worker has been interrupted by SIGINT."""
    print(f"⚠️ Worker {worker.pid} interrupted")

def pre_request(worker, req):
    """Called just before a worker processes a request."""
    # Verify eventlet is properly monkey patched
    if not hasattr(eventlet, '_is_patched'):
        # Force monkey patching if not already done
        try:
            eventlet.monkey_patch(
                socket=True, 
                dns=True, 
                time=True, 
                select=True,
                thread=False, 
                os=True, 
                ssl=True, 
                httplib=False,
                subprocess=False, 
                sys=False, 
                aggressive=True
            )
            print(f"⚡ Applied eventlet monkey patching in worker {worker.pid}")
        except Exception as e:
            print(f"⚠️ Failed to apply eventlet monkey patching: {e}")

def on_exit(server):
    """Called just before the master process is initialized."""
    print("👋 Mempaper server shutting down")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    print("🔄 Reloading Mempaper server")

# Environment variables
raw_env = [
    'MEMPAPER_ENV=production',
    'PYTHONPATH=/home/pi/btc-mempaper'
]
