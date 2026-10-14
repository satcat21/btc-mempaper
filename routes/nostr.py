"""Nostr posts: the prepared pool, card previews, avatars, profile lookup and
the manual fetch.
"""

from flask import Response
from flask import jsonify
from flask import request
from flask import send_file
from managers.auth_manager import require_auth
import os
import re
import threading

from lib import nostr_images


def register(self):
    """Register the Nostr routes."""
    from mempaper_app import _safe_error

    @self.app.route('/api/nostr-pool', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_nostr_pool():
        """Posts ready to show, in the order they would be picked."""
        try:
            return jsonify(nostr_images.get_store().overview())
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/nostr-card/<key>', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_nostr_card(key):
        """A post rendered as it would appear on the panel.

        theme comes from the request, not the config, so the page can preview
        the switch before it is saved.
        """
        if not re.fullmatch(r'[0-9a-f]{16}', key):
            return 'Not found', 404
        theme = request.args.get('theme', '')
        if theme not in ('light', 'dark'):
            theme = nostr_images.card_theme(self.config)
        width = request.args.get('w', type=int)
        width = max(100, min(width, 1000)) if width else None
        try:
            data = nostr_images.get_store().preview_jpeg(key, theme, width)
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500
        if data is None:
            return 'Not found', 404
        # Kept by the browser for a while: the page reloads the list every
        # minute, and each card fetched again would be rendered again.
        return Response(data, mimetype='image/jpeg',
                        headers={'Cache-Control': 'private, max-age=300'})

    @self.app.route('/api/nostr-dismiss/<key>', methods=['POST'])
    @require_auth(self.auth_manager)
    def dismiss_nostr_post(key):
        """Take one post out of the pool; it is not fetched again."""
        if not re.fullmatch(r'[0-9a-f]{16}', key):
            return jsonify({'success': False, 'message': 'Not found'}), 404
        if not nostr_images.get_store().dismiss(key):
            return jsonify({'success': False, 'message': 'Not found'}), 404
        return jsonify({'success': True})

    @self.app.route('/api/nostr-avatar/<pubkey>', methods=['GET'])
    def serve_nostr_avatar(pubkey):
        """The stored copy of an account's profile picture."""
        # No session refresh: a Set-Cookie would stop the browser caching it.
        if not self.auth_manager.is_authenticated():
            return jsonify({'error': 'Authentication required'}), 401
        # avatar_file() checks the key and keeps the path inside the
        # avatar folder.
        path = nostr_images.avatar_file(pubkey)
        if not path or not os.path.isfile(path):
            return 'Not found', 404
        etag = f'"{int(os.stat(path).st_mtime)}"'
        headers = {'ETag': etag, 'Cache-Control': 'private, max-age=3600'}
        if request.headers.get('If-None-Match') == etag:
            return Response(status=304, headers=headers)
        response = send_file(os.path.abspath(path), mimetype='image/jpeg')
        response.headers.update(headers)
        return response

    @self.app.route('/api/nostr-profile', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_nostr_profile():
        """Name, avatar and posts in the pool for one npub, as it is typed in."""
        pubkey = nostr_images.parse_pubkey(request.args.get('key', ''))
        if not pubkey:
            return jsonify({'success': False, 'message': 'Not a valid npub'}), 400
        try:
            store = nostr_images.get_store()
            profile = store.resolve_profile(pubkey, self.config)
            profile.update(success=True, pubkey=pubkey,
                           count=store.overview()['counts'].get(pubkey, 0))
            return jsonify(profile)
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/nostr-follows', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_nostr_follows():
        """The accounts an npub follows, from its contact list, with names."""
        pubkey = nostr_images.parse_pubkey(request.args.get('key', ''))
        if not pubkey:
            return jsonify({'success': False, 'message': 'Not a valid npub'}), 400
        try:
            follows, error = nostr_images.get_store().follows_of(pubkey, self.config)
            if error:
                return jsonify({'success': False, 'message': error}), 404
            return jsonify({'success': True, 'follows': follows})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/nostr-status', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_nostr_status():
        """Last fetch result and the size of the pool."""
        store = nostr_images.get_store()
        status = dict(store.status)
        status['errors'] = status.get('errors', [])[:50]
        return jsonify({'status': status, 'total': len(store.overview()['posts'])})

    @self.app.route('/api/nostr-fetch', methods=['POST'])
    @require_auth(self.auth_manager)
    def trigger_nostr_fetch():
        """Fetch now, from the saved settings."""
        store = nostr_images.get_store()
        if store.status.get('running'):
            return jsonify({'success': True, 'running': True})
        threading.Thread(target=store.fetch, args=(self.config,),
                         name='nostr-fetch-manual', daemon=True).start()
        return jsonify({'success': True, 'running': True})
