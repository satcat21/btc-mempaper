#!/bin/bash
# Log filtering script for Gunicorn
# This script runs Gunicorn and filters out static meme requests in real-time

echo "🚀 Starting Mempaper with filtered logging..."

# Run Gunicorn and filter out static meme requests
gunicorn -c gunicorn.conf.py mempaper_app:app 2>&1 | grep -v "/static/memes/"

# Alternative: Save filtered logs to file
# gunicorn -c gunicorn.conf.py mempaper_app:app 2>&1 | grep -v "/static/memes/" | tee filtered_gunicorn.log
