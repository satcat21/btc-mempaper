"""
Real-time Log Streaming for Browser Console

This module captures application logs and streams them to authenticated
web clients via WebSocket for real-time debugging and monitoring.

Version: 1.0 - Initial implementation for browser console logging
"""

import logging
import queue
import threading
import time
from datetime import datetime
from typing import Dict, Set, List
from flask_socketio import emit
import json


class BrowserConsoleLogHandler(logging.Handler):
    """
    Custom logging handler that captures logs and streams them to browser console
    via WebSocket for authenticated users only.
    """
    
    def __init__(self, socketio_instance, auth_manager):
        """
        Initialize the browser console log handler.
        
        Args:
            socketio_instance: Flask-SocketIO instance for WebSocket communication
            auth_manager: Authentication manager to verify user sessions
        """
        super().__init__()
        self.socketio = socketio_instance
        self.auth_manager = auth_manager
        
        # Store connected clients who want logs
        self.log_clients: Set[str] = set()
        
        # Log buffer for batching
        self.log_buffer: List[Dict] = []
        self.buffer_lock = threading.Lock()
        self.max_buffer_size = 50
        self.flush_interval = 1.0  # seconds
        
        # Start background thread for log flushing
        self.flush_thread = threading.Thread(target=self._log_flush_worker, daemon=True)
        self.flush_thread.start()
        
        # Set format for console logs
        self.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s'
        ))
    
    def emit(self, record):
        """
        Emit a log record to connected browser clients.
        
        Args:
            record: LogRecord instance
        """
        try:
            # Format the log message
            formatted_message = self.format(record)
            
            # Create log entry for browser console
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'formatted': formatted_message,
                'module': getattr(record, 'module', ''),
                'funcName': getattr(record, 'funcName', ''),
                'lineno': getattr(record, 'lineno', 0)
            }
            
            # Add to buffer for batching
            with self.buffer_lock:
                self.log_buffer.append(log_entry)
                
                # Flush immediately if buffer is full
                if len(self.log_buffer) >= self.max_buffer_size:
                    self._flush_logs()
                    
        except Exception as e:
            # Avoid infinite recursion by not logging this error
            print(f"Error in BrowserConsoleLogHandler: {e}")
    
    def _log_flush_worker(self):
        """Background worker to flush logs periodically."""
        while True:
            time.sleep(self.flush_interval)
            with self.buffer_lock:
                if self.log_buffer:
                    self._flush_logs()
    
    def _flush_logs(self):
        """
        Flush buffered logs to connected clients.
        Note: Should be called while holding buffer_lock.
        """
        if not self.log_buffer or not self.log_clients:
            return
        
        # Copy buffer and clear it
        logs_to_send = self.log_buffer.copy()
        self.log_buffer.clear()
        
        # Send to authenticated clients only
        authenticated_clients = []
        for client_id in self.log_clients.copy():
            # Check if client is still authenticated
            # Note: This is a simplified check - you may need to adapt based on your auth system
            try:
                if self._is_client_authenticated(client_id):
                    authenticated_clients.append(client_id)
                else:
                    self.log_clients.discard(client_id)
            except Exception:
                # Remove problematic clients
                self.log_clients.discard(client_id)
        
        # Send logs to authenticated clients
        if authenticated_clients and logs_to_send:
            try:
                self.socketio.emit('console_logs', {
                    'logs': logs_to_send,
                    'batch_size': len(logs_to_send)
                }, room=None)  # Send to all connected clients, they'll filter on frontend
            except Exception as e:
                print(f"Error sending logs to clients: {e}")
    
    def _is_client_authenticated(self, client_id: str) -> bool:
        """
        Check if a client is authenticated.
        
        Args:
            client_id: Client session ID
            
        Returns:
            bool: True if client is authenticated
        """
        # This is a simplified implementation
        # You may need to adapt this based on your authentication system
        try:
            # For now, we'll check if the auth_manager reports authentication
            # In a real implementation, you'd check the specific client session
            return self.auth_manager.is_authenticated() if self.auth_manager else False
        except Exception:
            return False
    
    def add_client(self, client_id: str):
        """
        Add a client to receive console logs.
        
        Args:
            client_id: Client session ID
        """
        if self._is_client_authenticated(client_id):
            self.log_clients.add(client_id)
            print(f"📺 Added authenticated client to console log stream: {client_id}")
            return True
        else:
            print(f"🚫 Rejected unauthenticated client for console logs: {client_id}")
            return False
    
    def remove_client(self, client_id: str):
        """
        Remove a client from receiving console logs.
        
        Args:
            client_id: Client session ID
        """
        self.log_clients.discard(client_id)
        print(f"📺 Removed client from console log stream: {client_id}")
    
    def get_client_count(self) -> int:
        """Get number of connected log clients."""
        return len(self.log_clients)


class LogStreamManager:
    """
    Manager for browser console log streaming functionality.
    """
    
    def __init__(self, socketio_instance, auth_manager):
        """
        Initialize the log stream manager.
        
        Args:
            socketio_instance: Flask-SocketIO instance
            auth_manager: Authentication manager
        """
        self.socketio = socketio_instance
        self.auth_manager = auth_manager
        self.handler = None
        self.is_enabled = False
    
    def setup_log_streaming(self, enable: bool = True, log_level: int = logging.INFO):
        """
        Set up log streaming to browser console.
        
        Args:
            enable: Whether to enable log streaming
            log_level: Minimum log level to stream
        """
        if enable and not self.is_enabled:
            # Create and configure handler
            self.handler = BrowserConsoleLogHandler(self.socketio, self.auth_manager)
            self.handler.setLevel(log_level)
            
            # Add to root logger to capture all logs
            logging.getLogger().addHandler(self.handler)
            
            self.is_enabled = True
            print("📺 Browser console log streaming enabled")
            
        elif not enable and self.is_enabled:
            # Remove handler
            if self.handler:
                logging.getLogger().removeHandler(self.handler)
                self.handler = None
            
            self.is_enabled = False
            print("📺 Browser console log streaming disabled")
    
    def handle_client_connect(self, client_id: str) -> bool:
        """
        Handle client requesting to receive console logs.
        
        Args:
            client_id: Client session ID
            
        Returns:
            bool: True if client was added successfully
        """
        if self.handler and self.is_enabled:
            return self.handler.add_client(client_id)
        return False
    
    def handle_client_disconnect(self, client_id: str):
        """
        Handle client disconnecting from console logs.
        
        Args:
            client_id: Client session ID
        """
        if self.handler:
            self.handler.remove_client(client_id)
    
    def get_status(self) -> Dict:
        """
        Get current log streaming status.
        
        Returns:
            Dict with status information
        """
        return {
            'enabled': self.is_enabled,
            'connected_clients': self.handler.get_client_count() if self.handler else 0,
            'buffer_size': len(self.handler.log_buffer) if self.handler else 0
        }
