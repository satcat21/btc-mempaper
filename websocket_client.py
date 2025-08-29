"""
WebSocket Connection Module

This module handles WebSocket connections to the mempool for real-time updates:
- WebSocket connection management
- Message handling for new blocks
- Connection error handling and reconnection logic
- Automatic reconnection with exponential backoff
"""

import json
import threading
import websocket
import time
from datetime import datetime


class MempoolWebSocket:
    """Handles WebSocket connection to mempool for real-time block updates with auto-reconnection."""
    
    def __init__(self, ip, ws_port, on_new_block_callback=None):
        """
        Initialize WebSocket connection.
        
        Args:
            ip (str): IP address of the mempool instance
            ws_port (str): WebSocket port
            on_new_block_callback (callable): Function to call when new block received
        """
        self.ip = ip
        self.ws_port = ws_port
        self.ws_url = f"ws://{ip}:{ws_port}/api/v1/ws"
        self.on_new_block_callback = on_new_block_callback
        self.ws = None
        self.is_connected = False
        self.should_reconnect = True
        self.reconnect_attempts = 0
        
        # Enhanced reconnection for backup scenarios
        self.max_reconnect_attempts = 50  # Increased for longer outages
        self.reconnect_delays = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]  # Up to 10 minutes per attempt
        self.backup_mode = False  # Special mode for extended outages
        self.backup_start_time = None
        self.max_backup_duration = 30 * 60  # 30 minutes max backup time
    
    def on_message(self, ws, message):
        """
        Handle incoming WebSocket messages.
        
        Args:
            ws: WebSocket instance
            message (str): JSON message from server
        """
        try:
            data = json.loads(message)
            print(f"WebSocket message received: {type(data)}")
            
            # Check for new block data
            block_data = data.get("block")
            if block_data:
                block_height = block_data.get("height")
                block_hash = block_data.get("id")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                print(f"[{timestamp}] New block received: Height {block_height}, Hash {block_hash}")
                
                # Call the callback function if provided
                if self.on_new_block_callback:
                    self.on_new_block_callback(block_height, block_hash)
            else:
                print("Received message does not contain 'block' key.")
                
        except json.JSONDecodeError as e:
            print(f"Error parsing WebSocket message JSON: {e}")
        except Exception as e:
            print(f"Error processing WebSocket message: {e}")
    
    def on_error(self, ws, error):
        """
        Handle WebSocket errors.
        
        Args:
            ws: WebSocket instance
            error: Error object
        """
        print(f"WebSocket error: {error}")
        self.is_connected = False
        # Don't immediately reconnect on error - let on_close handle it
    
    def on_close(self, ws, close_status_code, close_msg):
        """
        Handle WebSocket connection close with backup-aware auto-reconnection.
        
        Args:
            ws: WebSocket instance
            close_status_code: Close status code
            close_msg: Close message
        """
        self.is_connected = False
        current_time = time.time()
        
        # Detect if this might be a backup scenario (multiple consecutive failures)
        if self.reconnect_attempts >= 5 and not self.backup_mode:
            self.backup_mode = True
            self.backup_start_time = current_time
            print(f"🕒 Detected extended outage (attempt {self.reconnect_attempts}). Switching to backup mode...")
        
        print(f"WebSocket closed: {close_msg} (Code: {close_status_code})")
        
        # Check if we should continue reconnecting
        should_continue = self.should_reconnect and self.reconnect_attempts < self.max_reconnect_attempts
        
        # In backup mode, check if we've exceeded max backup duration
        if self.backup_mode and self.backup_start_time:
            backup_duration = current_time - self.backup_start_time
            if backup_duration > self.max_backup_duration:
                print(f"⏰ Backup duration exceeded {self.max_backup_duration/60:.1f} minutes. Stopping reconnection attempts.")
                should_continue = False
        
        if should_continue:
            # Use longer delays in backup mode
            if self.backup_mode:
                delay = min(300, 60 + (self.reconnect_attempts - 5) * 30)  # 1-5 min delays during backup
                print(f"🔄 Backup mode: Attempting reconnection {self.reconnect_attempts + 1}/{self.max_reconnect_attempts} in {delay}s...")
            else:
                delay = self.reconnect_delays[min(self.reconnect_attempts, len(self.reconnect_delays) - 1)]
                print(f"🔄 Normal mode: Attempting reconnection {self.reconnect_attempts + 1}/{self.max_reconnect_attempts} in {delay}s...")
            
            self.reconnect_attempts += 1
            time.sleep(delay)
            
            try:
                print(f"🌐 Reconnecting to {self.ws_url}...")
                self.start_connection()
            except Exception as e:
                print(f"❌ Reconnection attempt {self.reconnect_attempts} failed: {e}")
        else:
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                print(f"⛔ Max reconnection attempts ({self.max_reconnect_attempts}) reached. Giving up.")
            elif self.backup_mode and self.backup_start_time:
                backup_duration = current_time - self.backup_start_time
                print(f"⏰ Extended outage lasted {backup_duration/60:.1f} minutes. Stopping attempts.")
            else:
                print("🚫 Auto-reconnection disabled.")
            
            # Reset backup mode
            self.backup_mode = False
            self.backup_start_time = None
    
    def on_open(self, ws):
        """
        Handle WebSocket connection open.
        
        Args:
            ws: WebSocket instance
        """
        current_time = time.time()
        
        # Calculate outage duration if we were in backup mode
        if self.backup_mode and self.backup_start_time:
            outage_duration = current_time - self.backup_start_time
            print(f"✅ Connected to mempool WebSocket at {self.ws_url}")
            print(f"🎯 Backup/outage lasted {outage_duration/60:.1f} minutes. Connection restored!")
            
            # Reset backup mode
            self.backup_mode = False
            self.backup_start_time = None
        else:
            print(f"✅ Connected to mempool WebSocket at {self.ws_url}")
        
        self.is_connected = True
        self.reconnect_attempts = 0  # Reset counter on successful connection
        
        # Subscribe to new block events
        subscription_message = json.dumps({"action": "want", "data": ["blocks"]})
        ws.send(subscription_message)
        print("📡 Subscribed to block updates")
    
    def start_connection(self):
        """Start the WebSocket connection and run forever."""
        print(f"Starting WebSocket connection to {self.ws_url}")
        
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Run forever (blocking call)
        self.ws.run_forever()
    
    def start_listener_thread(self):
        """Start WebSocket listener in a separate daemon thread."""
        def run_listener():
            try:
                self.start_connection()
            except Exception as e:
                print(f"WebSocket thread error: {e}")
        
        thread = threading.Thread(target=run_listener, daemon=True)
        thread.start()
        print("WebSocket listener thread started")
        return thread
    
    def close_connection(self):
        """Close the WebSocket connection and disable auto-reconnection."""
        self.should_reconnect = False  # Disable auto-reconnection
        if self.ws:
            self.ws.close()
            self.is_connected = False
            print("WebSocket connection closed (auto-reconnection disabled)")
    
    def enable_reconnection(self):
        """Enable automatic reconnection."""
        self.should_reconnect = True
        self.reconnect_attempts = 0
        print("Auto-reconnection enabled")
    
    def disable_reconnection(self):
        """Disable automatic reconnection."""
        self.should_reconnect = False
        print("Auto-reconnection disabled")
    
    def get_connection_status(self):
        """Get current connection status and stats."""
        status = {
            "connected": self.is_connected,
            "should_reconnect": self.should_reconnect,
            "reconnect_attempts": self.reconnect_attempts,
            "max_attempts": self.max_reconnect_attempts,
            "url": self.ws_url,
            "backup_mode": self.backup_mode
        }
        
        # Add backup timing info if in backup mode
        if self.backup_mode and self.backup_start_time:
            current_time = time.time()
            backup_duration = current_time - self.backup_start_time
            status.update({
                "backup_duration_minutes": round(backup_duration / 60, 1),
                "max_backup_duration_minutes": round(self.max_backup_duration / 60, 1)
            })
        
        return status
    
    def reset_backup_mode(self):
        """Manually reset backup mode (useful for testing or manual intervention)."""
        self.backup_mode = False
        self.backup_start_time = None
        self.reconnect_attempts = 0
        print("🔄 Backup mode reset manually")
    
    def set_backup_schedule(self, max_backup_duration_minutes=30):
        """
        Configure backup-aware settings.
        
        Args:
            max_backup_duration_minutes (int): Maximum expected backup duration in minutes
        """
        self.max_backup_duration = max_backup_duration_minutes * 60
        print(f"⏰ Configured for backups up to {max_backup_duration_minutes} minutes")
