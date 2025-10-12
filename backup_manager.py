#!/usr/bin/python3
"""
Backup Management Utility for Mempaper

This script helps manage mempool connections during scheduled backup windows.
Use this to prepare for known maintenance periods.
"""

import json
import time
from datetime import datetime, timedelta
from websocket_client import MempoolWebSocket

def load_config():
    """Load the application configuration."""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return None

def create_backup_aware_websocket(config):
    """Create a WebSocket client optimized for backup scenarios."""
    if not config:
        return None
    
    def on_block_callback(height, hash_id):
        print(f"📦 New block during backup recovery: {height} - {hash_id}")
    
    # Create WebSocket with extended settings for backup scenarios
    ws_client = MempoolWebSocket(
        ip=config.get("mempool_host"),
        ws_port=config.get("mempool_ws_port"),
        on_new_block_callback=on_block_callback
    )
    
    # Override settings for backup-aware operation
    ws_client.max_reconnect_attempts = 100  # Very patient during backups
    ws_client.backup_mode_threshold = 5     # Enter backup mode quickly
    
    return ws_client

def monitor_backup_window():
    """Monitor connection during backup window with detailed logging."""
    print("🔧 Backup Window Monitor Started")
    print("=" * 50)
    
    config = load_config()
    if not config:
        print("❌ Cannot load configuration")
        return
    
    ws_client = create_backup_aware_websocket(config)
    if not ws_client:
        print("❌ Cannot create WebSocket client")
        return
    
    print(f"📡 Connecting to mempool at {config['mempool_host']}:{config['mempool_ws_port']}")
    
    # Start connection in thread
    thread = ws_client.start_listener_thread()
    
    try:
        while True:
            status = ws_client.get_connection_status()
            
            # Print status update
            timestamp = datetime.now().strftime("%H:%M:%S")
            if status["connected"]:
                print(f"[{timestamp}] ✅ Connected")
            else:
                backup_indicator = " (BACKUP MODE)" if status["backup_mode"] else ""
                downtime = status.get("downtime_formatted", "unknown")
                print(f"[{timestamp}] ❌ Disconnected - Attempt {status['reconnect_attempts']}/{status['max_attempts']}{backup_indicator} - Downtime: {downtime}")
            
            time.sleep(30)  # Status update every 30 seconds
            
    except KeyboardInterrupt:
        print("\n🛑 Backup monitor stopped by user")
    finally:
        ws_client.close_connection()
        print("🔌 WebSocket connection closed")

def schedule_backup_preparation(backup_start_time):
    """Prepare for a scheduled backup at a specific time."""
    print(f"⏰ Scheduling backup preparation for {backup_start_time}")
    
    # Calculate wait time
    now = datetime.now()
    backup_time = datetime.strptime(backup_start_time, "%H:%M")
    backup_datetime = now.replace(hour=backup_time.hour, minute=backup_time.minute, second=0, microsecond=0)
    
    # If backup time is in the past today, schedule for tomorrow
    if backup_datetime <= now:
        backup_datetime += timedelta(days=1)
    
    wait_seconds = (backup_datetime - now).total_seconds()
    
    print(f"🕐 Backup scheduled for: {backup_datetime}")
    print(f"⏳ Waiting {wait_seconds/3600:.1f} hours...")
    
    # In a real implementation, you might want to:
    # 1. Set the WebSocket to backup mode before the backup starts
    # 2. Log that a backup is expected
    # 3. Adjust reconnection behavior
    
    print("💡 To implement:")
    print("  - Add to systemd timer for automatic backup preparation")
    print("  - Integrate with Proxmox backup notifications")
    print("  - Add backup schedule to config.json")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Backup Management Utility")
        print("Usage:")
        print("  python backup_manager.py monitor          # Monitor during backup")
        print("  python backup_manager.py schedule HH:MM   # Schedule backup prep")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "monitor":
        monitor_backup_window()
    elif command == "schedule" and len(sys.argv) == 3:
        schedule_backup_preparation(sys.argv[2])
    else:
        print("❌ Invalid command")
        sys.exit(1)
