"""Static file serving: cache headers and the minified-dist fallback.
"""

import os
from flask import request
from flask import send_file
from werkzeug.utils import safe_join
import traceback


def register(self):
    """Register the static assets routes."""
    # Add CORS headers to all responses (MUST BE FIRST)
    @self.app.after_request
    def add_cors_headers(response):
        """Add CORS headers to allow cross-origin requests."""
        try:
            # Get the origin from the request, or use wildcard if not present
            origin = request.headers.get('Origin')
            if origin:
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
            else:
                response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        except Exception as e:
            print(f"❌ Error adding CORS headers: {type(e).__name__}: {str(e)}")
            traceback.print_exc()

        # Cache static assets (icons, CSS, JS, fonts) for 24 hours
        try:
            path = request.path
            if path.startswith('/static/') and not path.startswith('/static/memes/'):
                if path.endswith(('.svg', '.css', '.js', '.png', '.woff', '.woff2', '.ttf')):
                    response.headers.setdefault('Cache-Control', 'public, max-age=86400, must-revalidate')
        except Exception:
            pass

        # Security headers
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-XSS-Protection', '1; mode=block')

        return response

    # Cache static icons (SVG, etc.) for 7 days — they never change at runtime
    @self.app.route('/static/icons/<filename>')
    def serve_icon_with_cache(filename):
        import os
        file_path = safe_join('static', 'icons', filename)
        if not file_path or not os.path.exists(file_path):
            return "File not found", 404
        file_stat = os.stat(file_path)
        etag = f'"{file_stat.st_mtime}-{file_stat.st_size}"'
        if request.headers.get('If-None-Match') == etag:
            from flask import Response
            return Response(status=304)
        response = send_file(file_path)
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        response.headers['ETag'] = etag
        return response

    # Serve JS from static/js/dist/ if minified copy exists, else fall back to static/js/
    @self.app.route('/static/js/<path:filename>')
    def serve_js_with_dist_fallback(filename):
        # safe_join, not os.path.join: the <path:> converter accepts slashes,
        # so an unchecked filename could walk out of static/js and hand
        # send_file() anything readable — config/config.json included.
        dist_path = safe_join('static', 'js', 'dist', filename)
        src_path = safe_join('static', 'js', filename)
        if not dist_path or not src_path:
            return 'Not found', 404
        serve_path = dist_path if os.path.exists(dist_path) else src_path
        if not os.path.exists(serve_path):
            return 'Not found', 404
        return send_file(serve_path, mimetype='application/javascript')

    # Serve CSS from static/css/dist/ if minified copy exists, else fall back to static/css/
    @self.app.route('/static/css/<path:filename>')
    def serve_css_with_dist_fallback(filename):
        # safe_join, not os.path.join — see serve_js_with_dist_fallback above.
        dist_path = safe_join('static', 'css', 'dist', filename)
        src_path = safe_join('static', 'css', filename)
        if not dist_path or not src_path:
            return 'Not found', 404
        serve_path = dist_path if os.path.exists(dist_path) else src_path
        if not os.path.exists(serve_path):
            return 'Not found', 404
        return send_file(serve_path, mimetype='text/css')

    # Add optimized static file serving with cache headers for memes
    @self.app.route('/static/memes/<filename>')
    def serve_meme_with_cache(filename):
        """Serve meme files with proper cache headers to reduce browser overhead."""
        from flask import Response
        import os
        from datetime import datetime

        file_path = safe_join('static', 'memes', filename)

        if not file_path or not os.path.exists(file_path):
            return "File not found", 404

        # Get file stats for ETag and Last-Modified
        file_stat = os.stat(file_path)
        file_mtime = datetime.fromtimestamp(file_stat.st_mtime)
        etag = f'"{file_stat.st_mtime}-{file_stat.st_size}"'

        # Check if client has cached version (If-None-Match header)
        if request.headers.get('If-None-Match') == etag:
            return Response(status=304)  # Not Modified

        # Check if client has cached version (If-Modified-Since header)
        if_modified_since = request.headers.get('If-Modified-Since')
        if if_modified_since:
            try:
                client_cache_time = datetime.strptime(if_modified_since, '%a, %d %b %Y %H:%M:%S GMT')
                if file_mtime <= client_cache_time:
                    return Response(status=304)  # Not Modified
            except ValueError:
                pass  # Invalid date format, serve the file

        # Serve file with cache headers
        response = send_file(file_path)

        # Set cache headers for 1 hour (3600 seconds)
        response.headers['Cache-Control'] = 'public, max-age=3600, must-revalidate'
        response.headers['ETag'] = etag
        response.headers['Last-Modified'] = file_mtime.strftime('%a, %d %b %Y %H:%M:%S GMT')

        # Add immutable cache for files that don't change (optional)
        # Uncomment the next line for longer caching if memes rarely change
        # response.headers['Cache-Control'] = 'public, max-age=86400, immutable'  # 24 hours

        return response
