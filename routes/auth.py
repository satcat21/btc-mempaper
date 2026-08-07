"""Login, logout, session checks, admin users and the donation webhook.
"""

from flask import jsonify
from flask import redirect
from flask import request
from flask import session
from managers.auth_manager import require_auth
from managers.auth_manager import require_rate_limit
import traceback

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the auth routes."""
    from mempaper_app import _safe_error

    @self.app.route('/api/login', methods=['POST', 'OPTIONS'])
    @require_rate_limit(self.auth_manager)
    def login():
        """Handle login requests."""

        # Handle CORS preflight
        if request.method == 'OPTIONS':
            response = jsonify({'status': 'ok'})
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            return response

        try:
            # Try to parse JSON
            try:
                data = request.json
            except Exception as json_err:
                return jsonify({'success': False, 'message': 'Invalid JSON in request'}), 400

            username = data.get('username', '')
            password = data.get('password', '')

            if len(password) > 128:
                return jsonify({'success': False, 'message': 'Password too long (max 128 characters)'}), 400

            # Try to authenticate
            try:
                auth_result = self.auth_manager.login(username, password)
            except Exception as auth_err:
                return jsonify({
                    'success': False,
                    'message': _safe_error(auth_err, 'Authentication error')
                }), 500

            if auth_result:
                # Determine redirect: if public dashboard is on, login is only for config access
                public_dashboard = self.config.get('public_dashboard', False)
                redirect_url = '/config' if public_dashboard else '/'
                response_data = {'success': True, 'message': 'Login successful', 'redirect': redirect_url}

                # Create response with explicit handling
                try:
                    response = jsonify(response_data)

                    # Explicitly set headers
                    response.headers['Content-Type'] = 'application/json'
                    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'

                    # Force session to be saved
                    session.modified = True

                    return response

                except Exception as resp_err:
                    traceback.print_exc()
                    # Try to return a simple response
                    try:
                        return '{"success": true, "message": "Login successful"}', 200, {'Content-Type': 'application/json'}
                    except:
                        raise resp_err
            else:
                return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        except Exception as e:
            traceback.print_exc()
            try:
                return jsonify({'success': False, 'message': _safe_error(e)}), 500
            except:
                # If even jsonify fails, return raw JSON
                return '{"success": false, "message": "Server error"}', 500, {'Content-Type': 'application/json'}

    @self.app.route('/api/logout', methods=['POST'])
    def logout():
        """Handle logout requests."""
        public_dashboard = self.config.get('public_dashboard', False)
        self.auth_manager.logout()
        return jsonify({
            'success': True,
            'message': 'Logout successful',
            'public_dashboard': public_dashboard
        })

    @self.app.route('/logout', methods=['GET'])
    def logout_redirect():
        """Server-side logout: clears session and redirects atomically.
        Avoids mobile browser race where fetch() Set-Cookie isn't applied
        before the subsequent client-side window.location navigation."""
        public_dashboard = self.config.get('public_dashboard', False)
        self.auth_manager.logout()
        resp = redirect('/' if public_dashboard else '/login')
        resp.headers['Cache-Control'] = 'no-store, private'
        return resp

    @self.app.route('/api/auth-check', methods=['GET'])
    def auth_check():
        """Lightweight session validity check (no redirect) used by bfcache restore."""
        return jsonify({'authenticated': self.auth_manager.is_authenticated()})

    # User management endpoints
    @self.app.route('/api/users', methods=['GET'])
    @require_auth(self.auth_manager)
    def list_users():
        try:
            users = self.auth_manager.password_manager.list_users()
            return jsonify({'success': True, 'users': users})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/users', methods=['POST'])
    @require_auth(self.auth_manager)
    def create_user():
        try:
            data = request.json or {}
            username = (data.get('username') or '').strip()
            password = data.get('password', '')
            if not username:
                return jsonify({'success': False, 'message': 'Username is required'}), 400
            if len(password) < 8:
                return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
            if self.auth_manager.password_manager.create_user(username, password):
                return jsonify({'success': True})
            return jsonify({'success': False, 'message': 'Failed to create user'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 400

    @self.app.route('/api/users/<username>/password', methods=['POST'])
    @require_auth(self.auth_manager)
    def change_user_password(username):
        try:
            data = request.json or {}
            password = data.get('password', '')
            if len(password) < 8:
                return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400
            if len(password) > 128:
                return jsonify({'success': False, 'message': 'Password too long (max 128 characters)'}), 400
            users = self.auth_manager.password_manager.list_users()
            if username not in users:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            if self.auth_manager.password_manager.create_user(username, password):
                return jsonify({'success': True})
            return jsonify({'success': False, 'message': 'Failed to update password'}), 500
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 400

    @self.app.route('/api/users/<username>/rename', methods=['POST'])
    @require_auth(self.auth_manager)
    def rename_user(username):
        try:
            data = request.json or {}
            new_username = (data.get('new_username') or '').strip()
            if not new_username:
                return jsonify({'success': False, 'message': 'New username is required'}), 400
            users_dict = self.auth_manager.password_manager._get_users()
            if username not in users_dict:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            if new_username in users_dict and new_username != username:
                return jsonify({'success': False, 'message': 'Username already taken'}), 409
            with self.config_manager.config_lock:
                u = dict(self.config_manager.config.get('admin_users') or {})
                u[new_username] = u.pop(username)
                self.config_manager.config['admin_users'] = u
            self.config_manager.save_config()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 400

    @self.app.route('/api/users/<username>', methods=['DELETE'])
    @require_auth(self.auth_manager)
    def delete_user(username):
        try:
            users = self.auth_manager.password_manager.list_users()
            if username not in users:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            if len(users) <= 1:
                return jsonify({'success': False, 'message': 'Cannot delete the last user'}), 400
            with self.config_manager.config_lock:
                u = dict(self.config_manager.config.get('admin_users') or {})
                u.pop(username, None)
                self.config_manager.config['admin_users'] = u
            self.config_manager.save_config()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 400

    # Lightning Donation Webhook
    @self.app.route('/api/donation-webhook/<webhook_token>', methods=['POST'])
    def donation_webhook(webhook_token):
        """Receive LNbits payment webhook and broadcast donation to connected clients.
        The URL must include the per-installation secret token (shown in Settings > Lightning Donations).
        """
        expected = self.config_manager.get('donation_webhook_token', '')
        if not expected or webhook_token != expected:
            return jsonify({'success': False}), 403
        # force=True parses JSON regardless of Content-Type header, which LNbits sometimes omits.
        data = request.get_json(force=True, silent=True) or {}
        self._process_donation_payload(data)
        return jsonify({'success': True}), 200

    @self.app.route('/api/donation-webhook', methods=['POST'])
    def donation_webhook_legacy():
        """Reject calls to the old tokenless webhook URL with a helpful message."""
        return jsonify({
            'success': False,
            'message': 'Webhook URL must include the security token. '
                       'Update your LNbits webhook URL — open Settings > Lightning Donations to copy the correct URL.'
        }), 410
