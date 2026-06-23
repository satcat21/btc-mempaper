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
import ssl
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


class MempoolWebSocket:
    """Handles WebSocket connection to mempool for real-time block updates with auto-reconnection."""
    
    def __init__(self, host, port, path="/api/v1/ws", use_wss=False, on_new_block_callback=None, verify_ssl=True, username=None, password=None):
        """
        Initialize WebSocket connection.
        
        Args:
            host (str): IP address or domain of the mempool instance
            port (str): WebSocket port
            path (str): WebSocket path
            use_wss (bool): Whether to use WSS (secure) protocol
            on_new_block_callback (callable): Function to call when new block received
            verify_ssl (bool): Whether to verify SSL certificates
            username (str): Optional username for Basic authentication
            password (str): Optional password for Basic authentication
        """
        self.host = host
        self.port = port
        self.path = path
        self.use_wss = use_wss
        self.on_new_block_callback = on_new_block_callback
        self.verify_ssl = verify_ssl
        self.username = username
        self.password = password
        
        # Build WebSocket URL
        protocol = "wss" if use_wss else "ws"
        
        # Normalize port to string for comparison
        port_str = str(port)
        
        # Always omit standard ports to avoid 404s with some reverse proxies/load balancers
        # This applies to both domains and IP addresses
        is_standard_port = (use_wss and port_str == "443") or (not use_wss and port_str == "80")
        
        # Build WebSocket URL (without credentials in URL)
        if is_standard_port:
            self.ws_url = f"{protocol}://{host}{path}"
        else:
            self.ws_url = f"{protocol}://{host}:{port}{path}"

        # Build Basic Auth header if credentials provided
        self._auth_header = None
        if username and password:
            import base64
            credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
            self._auth_header = f"Basic {credentials}"
        
        self.ws = None
        self.is_connected = False
        self.should_reconnect = True
        self.reconnect_attempts = 0
        
        # Enhanced reconnection for backup scenarios
        self.max_reconnect_attempts = 50  # Increased for longer outages
        self.reconnect_delays = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]  # Up to 10 minutes per attempt
        self.outage_mode = False  # Special mode for extended outages
        self.outage_start_time = None
        self.max_outage_duration = 30 * 60  # 30 minutes max outage tolerance
        self.dns_error_count = 0  # Track DNS resolution failures
        self.last_error_type = None  # Track error type for smarter logging

    def _safe_ws_url_for_log(self):
        """Return WebSocket URL with any credentials redacted for logs."""
        try:
            parts = urlsplit(self.ws_url)
            hostname = parts.hostname or ""
            if parts.port is not None:
                netloc = f"{hostname}:{parts.port}"
            else:
                netloc = hostname
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        except Exception:
            # Conservative fallback: avoid leaking credentials in unexpected parsing errors.
            return "[redacted websocket url]"
    
    def on_message(self, ws, message):
        """
        Handle incoming WebSocket messages.
        
        Args:
            ws: WebSocket instance
            message (str): JSON message from server
        """
        try:
            data = json.loads(message)
            
            # Check for new block data
            block_data = data.get("block")
            if block_data:
                block_height = block_data.get("height")
                block_hash = block_data.get("id")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Call the callback function if provided
                if self.on_new_block_callback:
                    self.on_new_block_callback(block_height, block_hash)
            else:
                pass
                
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
        error_str = str(error)
        
        # Detect DNS/network resolution errors
        is_dns_error = any(x in error_str.lower() for x in [
            'name or service not known',
            'nodename nor servname provided',
            'temporary failure in name resolution',
            'errno -2', 'errno -3'
        ])
        
        if is_dns_error:
            self.dns_error_count += 1
            self.last_error_type = 'dns'
            # Only log the first DNS error with explanation
            if self.dns_error_count == 1:
                print(f"⚠️ WebSocket error: {error}")
                print(f"   Network not ready yet — will retry with longer backoff")
            # Silently count other DNS errors
        else:
            # Reset DNS counter for non-DNS errors
            if self.last_error_type == 'dns' and self.dns_error_count > 0:
                print(f"   (Had {self.dns_error_count} consecutive DNS failures)")
            self.dns_error_count = 0
            self.last_error_type = 'other'
            print(f"⚠️ WebSocket error: {error}")
        
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
        if self.reconnect_attempts >= 5 and not self.outage_mode:
            self.outage_mode = True
            self.outage_start_time = current_time
            print(f"🕒 Detected extended outage (attempt {self.reconnect_attempts}). Switching to outage mode...")
        
        # Only log close message if not in DNS error mode
        if self.last_error_type != 'dns':
            print(f"📶 WebSocket connection closed")
            if close_msg:
                print(f"   Reason: {close_msg} (Code: {close_status_code})")
        
        # Check if we should continue reconnecting
        should_continue = self.should_reconnect and self.reconnect_attempts < self.max_reconnect_attempts
        
        # In outage mode, check if we've exceeded max outage duration
        if self.outage_mode and self.outage_start_time:
            outage_duration = current_time - self.outage_start_time
            if outage_duration > self.max_outage_duration:
                print(f"⏰ Outage duration exceeded {self.max_outage_duration/60:.1f} minutes. Stopping reconnection attempts.")
                should_continue = False
        
        if should_continue:
            # Use longer delays in outage mode
            if self.outage_mode:
                delay = min(300, 60 + (self.reconnect_attempts - 5) * 30)  # 1-5 min delays during outage
                print(f"⚙️ Outage mode: Attempting reconnection {self.reconnect_attempts + 1}/{self.max_reconnect_attempts} in {delay}s...")
            elif self.last_error_type == 'dns':
                # DNS failure = network not ready yet (e.g. DHCP still settling after WiFi connect).
                # Use a fixed 30s floor so we don't hammer DNS during the settling window.
                base_delay = self.reconnect_delays[min(self.reconnect_attempts, len(self.reconnect_delays) - 1)]
                delay = max(30, base_delay)
                if self.dns_error_count == 1:
                    print(f"⚙️ Will attempt to reconnect in {delay}s (waiting for network/DNS)...")
            else:
                delay = self.reconnect_delays[min(self.reconnect_attempts, len(self.reconnect_delays) - 1)]
                # Only log reconnection attempts if not in DNS error mode
                if self.last_error_type != 'dns':
                    print(f"⚙️ Will attempt to reconnect in {delay}s (attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})...")
            
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
            elif self.outage_mode and self.outage_start_time:
                outage_duration = current_time - self.outage_start_time
                print(f"⏰ Extended outage lasted {outage_duration/60:.1f} minutes. Stopping attempts.")
            else:
                print("🚫 Auto-reconnection disabled.")
            
            # Reset outage mode
            self.outage_mode = False
            self.outage_start_time = None
    
    def on_open(self, ws):
        """
        Handle WebSocket connection open.
        
        Args:
            ws: WebSocket instance
        """
        current_time = time.time()
        
        # Calculate outage duration if we were in outage mode
        if self.outage_mode and self.outage_start_time:
            outage_duration = current_time - self.outage_start_time
            print(f"✅ WebSocket connected and subscribed ({self._safe_ws_url_for_log()})")
            print(f"✅ Outage lasted {outage_duration/60:.1f} minutes. Connection restored!")
            
            # Reset outage mode
            self.outage_mode = False
            self.outage_start_time = None
        else:
            print(f"✅ WebSocket connected and subscribed ({self._safe_ws_url_for_log()})")
        
        self.is_connected = True
        self.reconnect_attempts = 0  # Reset counter on successful connection
        self.dns_error_count = 0  # Reset DNS error counter
        self.last_error_type = None
        
        # Subscribe to new block events
        subscription_message = json.dumps({"action": "want", "data": ["blocks"]})
        ws.send(subscription_message)
        # Subscription confirmation included in connection message above
    
    def start_connection(self):
        """Start the WebSocket connection and run forever."""
        ws_headers = {}
        if self._auth_header:
            ws_headers['Authorization'] = self._auth_header

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=ws_headers or None,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Configure SSL options with explicit SNI support
        sslopt = {}
        if self.use_wss:
            if self.verify_ssl:
                # Explicitly set server_hostname for correct SNI support
                sslopt = {
                    "cert_reqs": ssl.CERT_REQUIRED,
                    "check_hostname": True,
                    "server_hostname": self.host
                }
            else:
                print("⚠️ SSL verification disabled for WebSocket")
                sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
            
        # Run forever with keepalive ping/pong to prevent idle timeouts
        # ping_interval: Send ping every 30s to keep connection alive (prevents 5min timeout)
        # ping_timeout: Wait 10s for pong response before considering connection dead
        self.ws.run_forever(
            sslopt=sslopt,
            ping_interval=30,  # Send ping every 30 seconds
            ping_timeout=10    # Wait 10 seconds for pong response
        )
    
    def start_listener_thread(self):
        """Start WebSocket listener in a separate daemon thread."""
        def run_listener():
            try:
                self.start_connection()
            except Exception as e:
                print(f"WebSocket thread error: {e}")
        
        thread = threading.Thread(target=run_listener, daemon=True)
        thread.start()
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
            "url": self._safe_ws_url_for_log(),
            "outage_mode": self.outage_mode
        }
        
        # Add outage timing info if in outage mode
        if self.outage_mode and self.outage_start_time:
            current_time = time.time()
            outage_duration = current_time - self.outage_start_time
            status.update({
                "outage_duration_minutes": round(outage_duration / 60, 1),
                "max_outage_tolerance_minutes": round(self.max_outage_duration / 60, 1)
            })
        
        return status
    
    def reset_outage_mode(self):
        """Manually reset outage mode (useful for testing or manual intervention)."""
        self.outage_mode = False
        self.outage_start_time = None
        self.reconnect_attempts = 0
        print("⚙️ Outage mode reset manually")
    
    def set_network_tolerance(self, max_outage_minutes=30):
        """
        Configure network outage tolerance settings.
        
        Args:
            max_outage_minutes (int): Maximum expected outage duration in minutes
        """
        self.max_outage_duration = max_outage_minutes * 60
