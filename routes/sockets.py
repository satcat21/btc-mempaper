"""SocketIO event handlers, registered only when SocketIO is enabled.
"""

from flask import request
from flask_socketio import join_room
import threading


def register(self):
    """Register the sockets routes."""
    # WebSocket event handlers (only if SocketIO is enabled)
    if self.socketio:
        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection. Join 'authenticated' room if logged in."""
            if self.auth_manager.is_authenticated():
                join_room('authenticated')

        @self.socketio.on('disconnect')
        def handle_disconnect(*args):
            """Handle client disconnection."""
            # Remove client from block notification subscribers
            client_id = request.sid
            self.block_notification_subscribers.discard(client_id)
            # Disconnect logged silently - normal client behavior

            # Clean up console log streaming for disconnected client
            try:
                if self.log_stream_manager:
                    client_id = request.sid
                    self.log_stream_manager.handle_client_disconnect(client_id)
            except Exception as e:
                # Silent cleanup - don't log errors for normal disconnections
                pass

        @self.socketio.on('request_latest_image')
        def handle_request_latest_image():
            """Handle client request for latest image - avoid unnecessary regeneration."""
            try:
                # Try serving from RAM cache first (instant)
                image_data = self._get_web_image_base64()
                if image_data and self._has_valid_cached_image():
                    self.socketio.emit('new_image', {'image': image_data})
                    return

                # No current image — generate in background
                threading.Thread(
                    target=self._background_image_generation,
                    daemon=True
                ).start()

                # Send stale image while generating fresh one
                if image_data:
                    self.socketio.emit('new_image', {'image': image_data})

            except Exception as e:
                print(f"❌ Error handling latest image request: {e}")

        @self.socketio.on('subscribe_block_notifications')
        def handle_subscribe_block_notifications(data):
            """Handle client request to subscribe to live block notifications."""
            try:
                # Block heights are public info — allow any connected client to subscribe
                client_id = request.sid
                self.block_notification_subscribers.add(client_id)
                print(f"📡 Client subscribed to block notifications ({len(self.block_notification_subscribers)} total)")
                self.socketio.emit('block_notification_status', {'status': 'subscribed', 'message': 'Subscribed to live block notifications'})

            except Exception as e:
                print(f"❌ Error subscribing to block notifications: {e}")
                self.socketio.emit('block_notification_error', {'error': 'Failed to subscribe to block notifications'})

        @self.socketio.on('unsubscribe_block_notifications')
        def handle_unsubscribe_block_notifications():
            """Handle client request to unsubscribe from live block notifications."""
            print("📶 Client requested to unsubscribe from block notifications")
            try:
                # Remove client from subscribers
                client_id = request.sid
                self.block_notification_subscribers.discard(client_id)
                print(f"✅ Client {client_id} unsubscribed from block notifications")
                self.socketio.emit('block_notification_status', {'status': 'unsubscribed'})

            except Exception as e:
                print(f"❌ Error unsubscribing from block notifications: {e}")
                self.socketio.emit('block_notification_error', {'error': 'Failed to unsubscribe from block notifications'})

        @self.socketio.on_error_default
        def default_error_handler(e):
            """Handle SocketIO errors."""
            print(f"⚠️ SocketIO error: {e}")

        @self.socketio.on('connect_error')
        def handle_connect_error(data):
            """Handle connection errors."""
            print(f"🚫 SocketIO connection error: {data}")

    else:
        print("⚙️ SocketIO event handlers skipped (SocketIO disabled)")
