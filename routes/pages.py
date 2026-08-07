"""Rendered pages: dashboard image, dashboard, config and login.
"""

from flask import redirect
from flask import render_template
from flask import request
from flask import send_file
from flask import url_for
from managers.auth_manager import allow_public_or_auth
from managers.auth_manager import require_web_auth
from utils.translations import translations
import io
import os
import threading
import time


def register(self):
    """Register the pages routes."""
    @self.app.route('/image')
    @allow_public_or_auth(self.auth_manager, self.config_manager)
    def image():
        """Return current dashboard image (optimized for fast serving)."""
        # Get client info for debugging repeated requests
        client_ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Unknown')

        # Always serve existing image if available (even if outdated)
        if os.path.exists(self.current_image_path):
            # For outdated images, start background refresh but serve current one
            if not self._has_valid_cached_image():
                print(f"📷 Serving cached image, starting background refresh (client: {client_ip})")
                threading.Thread(
                    target=self._background_image_generation,
                    daemon=True
                ).start()
            else:
                # Only log if there are frequent requests (throttle logging)
                if not hasattr(self, '_last_image_serve_log'):
                    self._last_image_serve_log = {}

                now = time.time()
                last_log_time = self._last_image_serve_log.get(client_ip, 0)

                # Log once per 5 minutes per client to reduce log spam
                if now - last_log_time > 300:
                    print(f"📷 Serving up-to-date cached image (client: {client_ip})")
                    self._last_image_serve_log[client_ip] = now

            # Serve WebP if the client accepts it and a WebP copy exists
            accept = request.headers.get('Accept', '')
            use_webp = 'image/webp' in accept and os.path.exists(self.current_webp_image_path)
            served_path = self.current_webp_image_path if use_webp else self.current_image_path
            served_mime = 'image/webp' if use_webp else 'image/png'

            # ETag + conditional request check before sending body
            if os.path.exists(served_path):
                file_mtime = os.path.getmtime(served_path)
                etag = f'"{int(file_mtime)}-{served_mime}"'
                if request.headers.get('If-None-Match') == etag:
                    return '', 304

            response = send_file(served_path, mimetype=served_mime)
            # no-cache forces an ETag revalidation on every load (cheap — a 304 with
            # no body) instead of trusting a max-age window, so a mid-block regen
            # (config save, donation, wallet update) is never served stale from the
            # browser's own HTTP cache under the same "/image?v=<block_height>" URL.
            response.headers['Cache-Control'] = 'no-cache, must-revalidate'
            if os.path.exists(served_path):
                response.headers['ETag'] = etag

            return response

        # No cached image at all - generate minimal placeholder and start background generation
        print("⚠️ No cached image - generating placeholder and starting background generation")
        try:
            # Start background generation immediately
            threading.Thread(
                target=self._background_image_generation,
                daemon=True
            ).start()

            # Generate and return placeholder quickly
            placeholder_img = self._generate_placeholder_image()
            buf = io.BytesIO()
            placeholder_img.save(buf, format='PNG')
            buf.seek(0)
            return send_file(buf, mimetype='image/png')

        except Exception as e:
            print(f"❌ Failed to generate placeholder image: {e}")
            return "Image generation failed", 503

    @self.app.route('/')
    @allow_public_or_auth(self.auth_manager, self.config_manager)
    def dashboard():
        """Serve the main dashboard web page."""
        if self._is_setup_mode_enabled() and not self.auth_manager.is_authenticated():
            return redirect(url_for('setup_wifi_page'))

        display_status = "enabled" if self.e_ink_enabled else "disabled"
        display_icon = "🖥️" if self.e_ink_enabled else "🚫"

        # Get current language and orientation
        lang = self.config.get("language", "en")
        # Use web_orientation for the dashboard view
        orientation = self.config.get("web_orientation", "vertical")
        current_translations = translations.get(lang, translations["en"])

        # Get current block height for cache-busting
        block_height = self.current_block_height if self.current_block_height else 0

        # Check if user is authenticated (for showing/hiding logout button)
        is_authenticated = self.auth_manager.is_authenticated()

        # Compute actual web-image pixel dimensions for the img width/height hint.
        # display_width/height are the physical display resolution (e.g. 960×680 for
        # 13.3E, 800×480 for 7.3F). In vertical orientation the shorter side becomes
        # the width; in horizontal the longer side is the width.
        _dw = self.config.get("display_width", 800)
        _dh = self.config.get("display_height", 480)
        if orientation == "vertical":
            img_w, img_h = min(_dw, _dh), max(_dw, _dh)
        else:
            img_w, img_h = max(_dw, _dh), min(_dw, _dh)

        return render_template('dashboard.html',
                             translations=current_translations,
                             display_icon=display_icon,
                             e_ink_enabled=self.e_ink_enabled,
                             orientation=orientation,
                             block_height=block_height,
                             is_authenticated=is_authenticated,
                             lang=lang,
                             show_wallet=self.config.get('show_wallet_balances_block', False),
                             show_bitaxe=self.config.get('show_bitaxe_block', False),
                             show_donations=self.config.get('show_donation_block', False),
                             dark_mode=self.config.get('color_mode_dark', True),
                             img_width=img_w,
                             img_height=img_h)

    @self.app.route('/config')
    @require_web_auth(self.auth_manager)
    def config_page():
        """Serve the configuration page."""
        # Get current language
        lang = self.config.get("language", "en")
        current_translations = translations.get(lang, translations["en"])

        return render_template('config.html',
                             translations=current_translations,
                             all_translations=translations,
                             lang=lang,
                             dark_mode=self.config.get('color_mode_dark', True))

    @self.app.route('/login')
    def login_page():
        """Serve the login page."""
        # If already authenticated, redirect to config page
        if self.auth_manager.is_authenticated():
            return redirect(url_for('config_page'))

        # Get current language
        lang = self.config.get("language", "en")
        current_translations = translations.get(lang, translations["en"])

        return render_template('login.html', translations=current_translations,
                             lang=lang,
                             dark_mode=self.config.get('color_mode_dark', True),
                             public_dashboard=self.config.get('public_dashboard', False))
