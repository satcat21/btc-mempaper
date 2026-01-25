#!/bin/bash
"""
Gunicorn Startup Script for Mempaper Bitcoin Dashboard

This script provides an easy way to start the Mempaper application
with Gunicorn for production deployment.
"""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Mempaper Bitcoin Dashboard with Gunicorn${NC}"
echo "============================================================"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found. Please run setup first.${NC}"
    exit 1
fi

# Activate virtual environment
echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
source .venv/bin/activate

# Check if gunicorn is installed
if ! command -v gunicorn &> /dev/null; then
    echo -e "${RED}❌ Gunicorn not found. Installing...${NC}"
    pip install gunicorn gevent gevent-websocket
fi

# Ensure required directories exist
echo -e "${YELLOW}📁 Ensuring directories exist...${NC}"
mkdir -p config cache static/tmp

# Start Gunicorn with configuration
echo -e "${GREEN}🔥 Starting Gunicorn server...${NC}"
echo -e "${BLUE}   Config: gunicorn.conf.py${NC}"
echo -e "${BLUE}   WSGI: wsgi:application${NC}"
echo -e "${BLUE}   Host: 0.0.0.0:5000${NC}"
echo ""

exec gunicorn --config gunicorn.conf.py wsgi:application
