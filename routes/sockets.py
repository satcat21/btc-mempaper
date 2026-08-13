"""SocketIO event handlers, registered only when SocketIO is enabled.
"""

from flask import request
from flask_socketio import join_room
import threading


def register(self):
    """Register the sockets routes."""
    # WebSocket event handlers (only if SocketIO is enabled)
    if self.socketio:
        def _may_view_dashboard():
            """Whether this socket may see rendered dashboard content.

            Mirrors the rule the HTTP dashboard applies: a login is required
            unless public_dashboard is on. The socket used to answer differently
            from the page it belongs to, so anything able to reach /socket.io/
            could pull the rendered image even with public_dashboard off — and
            that image carries whatever the panel draws, wallet balances
            included when that block is enabled.
            """
            return (self.config.get('public_dashboard', False)
                    or self.auth_manager.is_authenticated())

        @self.socketio.on('connect')
        def handle_connect():
            """Handle client connection. Join 'authenticated' room if logged in."""
            if self.auth_manager.is_authenticated():
                join_room('authenticated')
            elif not self.config.get('public_dashboard', False):
                # Returning False refuses the connection. Block heights and the
                # other public events are not worth an open socket on a device
                # whose dashboard requires a login.
                return False

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
            # Checked here as well as on connect: a refused socket should never
            # reach this, but the image is the one piece of genuinely private
            # content this handler serves, so it does not rely on that alone.
            if not _may_view_dashboard():
                return
            try:
                # Try serving from RAM cache first (instant)
                image_data = self._get_web_image_base64()
                if image_data and self._has_valid_cached_image():
                    self.socketio.emit('new_image', {'image': image_data}, room=request.sid)
                    return

                # No current image — generate in background
                threading.Thread(
                    target=self._background_image_generation,
                    daemon=True
                ).start()

                # Send stale image while generating fresh one.
                # Addressed to the caller: broadcasting meant one client's
                # request pushed a full base64 PNG to every open socket.
                if image_data:
                    self.socketio.emit('new_image', {'image': image_data}, room=request.sid)

            except Exception as e:
                print(f"❌ Error handling latest image request: {e}")

        @self.socketio.on('subscribe_block_notifications')
        def handle_subscribe_block_notifications(data):
            """Handle client request to subscribe to live block notifications."""
            try:
                # Block heights are public info — allow any connected client to subscribe
                client_id = request.sid
                # Clients re-subscribe on every reconnect and the set is
                # idempotent, so logging unconditionally repeated an unchanged
                # count several times a minute. Only a genuinely new subscriber
                # is worth a line.
                if client_id not in self.block_notification_subscribers:
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
