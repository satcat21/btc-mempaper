"""Meme and OPSec image upload, listing, thumbnails, rename and delete.
"""

from flask import send_file
from flask import jsonify
from flask import request
from managers.auth_manager import require_auth
from werkzeug.utils import secure_filename
import os

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the media routes."""
    from mempaper_app import _reserve_upload_path, _safe_error

    @self.app.route('/api/upload-meme', methods=['POST'])
    @require_auth(self.auth_manager)
    def upload_meme():
        """Handle meme image uploads."""
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400

            # Validate file type
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

            if file_ext not in allowed_extensions:
                return jsonify({
                    'success': False, 
                    'message': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                }), 400

            # Secure filename and save (never overwrites an existing meme)
            filename, upload_path = _reserve_upload_path(
                os.path.join('static', 'memes'), file.filename, file_ext)
            if not upload_path:
                return jsonify({'success': False,
                                'message': 'Invalid filename'}), 400

            # Save file
            file.save(upload_path)

            # Validate that PIL (or its ImageMagick fallback) can actually open the file.
            # This catches missing codec support (e.g. WebP on Pi without libwebp-dev)
            # before the broken file makes it into the meme pool.
            try:
                self.image_renderer._open_image_robust(upload_path)
            except Exception as img_err:
                os.remove(upload_path)
                hint = ''
                if file_ext == 'webp':
                    hint = (' WebP requires libwebp support in Pillow. '
                            'Run: sudo apt install libwebp-dev && '
                            'pip install --no-binary :all: pillow')
                # The hint is static, actionable text and is kept; the decoder
                # exception itself goes to the log, not to the browser.
                _safe_error(img_err, 'Uploaded image could not be opened')
                return jsonify({
                    'success': False,
                    'message': f'Image cannot be opened by the server.{hint}'
                }), 400

            self.image_renderer.invalidate_meme_cache()

            return jsonify({
                'success': True,
                'message': f'Meme uploaded successfully: {filename}',
                'filename': filename
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/memes', methods=['GET'])
    @require_auth(self.auth_manager)
    def list_memes():
        """List all uploaded memes with pagination and lazy loading support."""
        try:
            # Get pagination parameters
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 50, type=int)  # Limit to 50 memes per request
            search = request.args.get('search', '', type=str).strip().lower()
            untagged = request.args.get('untagged', '').lower() in ('1', 'true', 'yes')

            memes_dir = os.path.join('static', 'memes')
            if not os.path.exists(memes_dir):
                return jsonify({'memes': [], 'total': 0, 'page': page, 'per_page': per_page})

            # Use cached file list + metadata from image_renderer
            all_files = list(self.image_renderer.get_cached_meme_files())

            # If search term provided, filter by cached metadata and filename
            if search:
                meta_map = self.image_renderer.get_cached_meme_meta()
                filtered = []
                for filename in all_files:
                    stem = os.path.splitext(filename)[0]
                    searchable = meta_map.get(stem, [])
                    if (any(search in s for s in searchable)
                            or search in filename.lower()):
                        filtered.append(filename)
                all_files = filtered

            # Memes with nothing to match on. Filtered here rather than in the
            # browser because the grid is paginated: hiding tagged memes from the
            # loaded page would report "4 untagged" while thousands more sat on
            # pages nobody had scrolled to.
            if untagged:
                _tags = self.image_renderer.get_cached_meme_tags()
                _api_tags = self.image_renderer.get_cached_meme_api_tags()
                all_files = [
                    f for f in all_files
                    if not _tags.get(os.path.splitext(f)[0])
                    and not _api_tags.get(os.path.splitext(f)[0])
                ]

            # Already sorted by the cache

            # Calculate pagination
            total_files = len(all_files)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_files = all_files[start_idx:end_idx]

            tags_map = self.image_renderer.get_cached_meme_tags()
            api_tags_map = self.image_renderer.get_cached_meme_api_tags()
            memes = []
            for filename in page_files:
                file_path = os.path.join(memes_dir, filename)
                try:
                    file_size = os.path.getsize(file_path)
                    file_stat = os.stat(file_path)
                    stem = os.path.splitext(filename)[0]

                    meme_data = {
                        'filename': filename,
                        'size': file_size,
                        'url': f'/static/memes/{filename}',
                        'thumb_url': f'/api/thumb/{filename}?v={int(file_stat.st_mtime)}',
                        'last_modified': file_stat.st_mtime,
                        'tags': tags_map.get(stem, []),
                        'api_tags': api_tags_map.get(stem, [])
                    }

                    memes.append(meme_data)
                except OSError:
                    # Skip files that can't be read
                    continue

            return jsonify({
                'memes': memes,
                'total': total_files,
                'page': page,
                'per_page': per_page,
                'has_next': end_idx < total_files,
                'has_prev': page > 1
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/thumb/<filename>', methods=['GET'])
    def serve_meme_thumb(filename):
        """Serve a cached 200×200 WebP thumbnail, generating it on first request."""
        # Auth check without session refresh — avoids Set-Cookie which blocks browser caching
        if not self.auth_manager.is_authenticated():
            return jsonify({'error': 'Authentication required'}), 401

        from PIL import Image

        filename = secure_filename(filename)
        orig_path = os.path.join('static', 'memes', filename)
        if not os.path.exists(orig_path):
            return "Not found", 404

        thumb_dir = os.path.join('static', 'memes', 'thumbs')
        os.makedirs(thumb_dir, exist_ok=True)

        stem = os.path.splitext(filename)[0]
        thumb_path = os.path.join(thumb_dir, f'{stem}.webp')

        orig_mtime = os.stat(orig_path).st_mtime
        thumb_ok = (
            os.path.exists(thumb_path)
            and os.stat(thumb_path).st_mtime >= orig_mtime
        )

        if not thumb_ok:
            try:
                with Image.open(orig_path) as img:
                    # Preserve animation frames for GIFs by only taking frame 0
                    img.seek(0) if hasattr(img, 'seek') else None
                    img = img.convert('RGBA')
                    img.thumbnail((200, 200), Image.LANCZOS)
                    img.save(thumb_path, 'WEBP', quality=70)
            except Exception:
                # Thumbnail generation failed — fall back to the original
                response = send_file(orig_path)
                response.headers['Cache-Control'] = 'private, max-age=3600'
                return response

        # Build an ETag from the thumb file's mtime
        thumb_mtime = int(os.stat(thumb_path).st_mtime)
        etag = f'"{thumb_mtime}"'

        # Return 304 if the browser already has this version
        if request.headers.get('If-None-Match') == etag:
            from flask import Response as _Response
            return _Response(status=304, headers={
                'ETag': etag,
                'Cache-Control': 'private, max-age=31536000, immutable',
            })

        response = send_file(thumb_path, mimetype='image/webp')
        response.headers['ETag'] = etag
        # immutable + long max-age: browser skips the request entirely until ?v=mtime changes
        response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
        return response

    @self.app.route('/api/download-meme/<filename>', methods=['GET'])
    @require_auth(self.auth_manager)
    def download_meme(filename):
        """Download a specific meme file."""
        try:
            # Secure the filename
            filename = secure_filename(filename)
            file_path = os.path.join('static', 'memes', filename)

            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': 'File not found'}), 404

            return send_file(file_path, as_attachment=True, download_name=filename)

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/delete-meme/<filename>', methods=['DELETE'])
    @require_auth(self.auth_manager)
    def delete_meme(filename):
        """Delete a specific meme file."""
        try:
            # Secure the filename
            filename = secure_filename(filename)
            file_path = os.path.join('static', 'memes', filename)

            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': 'File not found'}), 404

            # Delete the file and its thumbnail
            os.remove(file_path)
            stem = os.path.splitext(filename)[0]
            thumb_path = os.path.join('static', 'memes', 'thumbs', f'{stem}.webp')
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

            # The record goes with the image. Left behind it describes a file
            # that is not there: harmless to the renderer, which draws only what
            # it finds on disk, but it is one more record per deletion for ever,
            # and a tag the operator removed here would come back if the image
            # were ever downloaded again.
            forgotten = self.image_renderer.forget_meme(stem)

            self.image_renderer.invalidate_meme_cache()

            return jsonify({
                'success': True,
                'message': f'Meme deleted successfully: {filename}',
                'metadata_removed': forgotten
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/rename-meme', methods=['POST'])
    @require_auth(self.auth_manager)
    def rename_meme():
        """Rename a meme file."""
        try:
            data = request.json
            if not data or 'old_filename' not in data or 'new_filename' not in data:
                return jsonify({'success': False, 'message': 'Missing filename parameters'}), 400

            old_filename = secure_filename(data['old_filename'])
            new_filename = secure_filename(data['new_filename'])

            if old_filename == new_filename:
                return jsonify({'success': False, 'message': 'New filename is the same as old filename'}), 400

            old_path = os.path.join('static', 'memes', old_filename)
            new_path = os.path.join('static', 'memes', new_filename)

            if not os.path.exists(old_path):
                return jsonify({'success': False, 'message': f'File not found: {old_filename}'}), 404

            if os.path.exists(new_path):
                return jsonify({'success': False, 'message': f'A file with the name {new_filename} already exists'}), 400

            # Rename the file
            os.rename(old_path, new_path)

            old_stem = os.path.splitext(old_filename)[0]
            new_stem = os.path.splitext(new_filename)[0]

            # Track rename so metadata stays linked to UUID
            self.image_renderer.record_rename(old_stem, new_stem)

            # Update user tags key if it exists
            import json as _json
            user_tags_path = os.path.join('static', 'memes', '_user_tags.json')
            if os.path.exists(user_tags_path):
                try:
                    with open(user_tags_path, encoding='utf-8') as fh:
                        user_tags = _json.load(fh)
                    if old_stem in user_tags:
                        user_tags[new_stem] = user_tags.pop(old_stem)
                        with open(user_tags_path, 'w', encoding='utf-8') as fh:
                            _json.dump(user_tags, fh, ensure_ascii=False, indent=2)
                except (OSError, _json.JSONDecodeError):
                    pass

            self.image_renderer.invalidate_meme_cache()

            return jsonify({
                'success': True,
                'message': f'Meme renamed from {old_filename} to {new_filename}',
                'old_filename': old_filename,
                'new_filename': new_filename
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/meme-tags', methods=['POST'])
    @require_auth(self.auth_manager)
    def update_meme_tags():
        """Update tags for a meme."""
        try:
            data = request.json
            if not data or 'filename' not in data or 'tags' not in data:
                return jsonify({'success': False, 'message': 'Missing filename or tags'}), 400
            filename = data['filename']
            tags = data['tags']
            if not isinstance(tags, list):
                return jsonify({'success': False, 'message': 'Tags must be a list'}), 400
            stem = os.path.splitext(filename)[0]
            self.image_renderer.set_meme_tags(stem, tags)
            return jsonify({'success': True, 'tags': tags})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/meme-hashes', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_meme_hashes():
        """Get SHA-256 hashes of all existing memes for duplicate detection."""
        try:
            import hashlib

            memes_dir = os.path.join('static', 'memes')
            if not os.path.exists(memes_dir):
                return jsonify({'hashes': {}})

            hashes = {}
            for filename in os.listdir(memes_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    file_path = os.path.join(memes_dir, filename)
                    try:
                        # Calculate SHA-256 hash of file content
                        sha256_hash = hashlib.sha256()
                        with open(file_path, "rb") as f:
                            # Read file in chunks for efficiency
                            for byte_block in iter(lambda: f.read(4096), b""):
                                sha256_hash.update(byte_block)

                        file_hash = sha256_hash.hexdigest()
                        hashes[file_hash] = filename
                    except Exception as e:
                        print(f"Error hashing {filename}: {e}")
                        continue

            return jsonify({'hashes': hashes})

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/opsec-thumb/<filename>', methods=['GET'])
    def serve_opsec_thumb(filename):
        """Serve a cached 200×200 WebP thumbnail for an OPSec image, generating on first request."""
        if not self.auth_manager.is_authenticated():
            return jsonify({'error': 'Authentication required'}), 401

        from PIL import Image

        filename = secure_filename(filename)
        orig_path = os.path.join('static', 'opsec', filename)
        if not os.path.exists(orig_path):
            return "Not found", 404

        thumb_dir = os.path.join('static', 'opsec', 'thumbs')
        os.makedirs(thumb_dir, exist_ok=True)

        stem = os.path.splitext(filename)[0]
        thumb_path = os.path.join(thumb_dir, f'{stem}.webp')

        orig_mtime = os.stat(orig_path).st_mtime
        thumb_ok = (
            os.path.exists(thumb_path)
            and os.stat(thumb_path).st_mtime >= orig_mtime
        )

        if not thumb_ok:
            try:
                with Image.open(orig_path) as img:
                    img.seek(0) if hasattr(img, 'seek') else None
                    img = img.convert('RGBA')
                    img.thumbnail((200, 200), Image.LANCZOS)
                    img.save(thumb_path, 'WEBP', quality=70)
            except Exception:
                response = send_file(orig_path)
                response.headers['Cache-Control'] = 'private, max-age=3600'
                return response

        thumb_mtime = int(os.stat(thumb_path).st_mtime)
        etag = f'"{thumb_mtime}"'

        if request.headers.get('If-None-Match') == etag:
            from flask import Response as _Response
            return _Response(status=304, headers={
                'ETag': etag,
                'Cache-Control': 'private, max-age=31536000, immutable',
            })

        response = send_file(thumb_path, mimetype='image/webp')
        response.headers['ETag'] = etag
        response.headers['Cache-Control'] = 'private, max-age=31536000, immutable'
        return response

    @self.app.route('/api/upload-opsec', methods=['POST'])
    @require_auth(self.auth_manager)
    def upload_opsec():
        """Handle OPSec image uploads."""
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400

            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
            file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

            if file_ext not in allowed_extensions:
                return jsonify({
                    'success': False,
                    'message': f'Invalid file type. Allowed: {", ".join(allowed_extensions)}'
                }), 400

            filename, upload_path = _reserve_upload_path(
                os.path.join('static', 'opsec'), file.filename, file_ext)
            if not upload_path:
                return jsonify({'success': False,
                                'message': 'Invalid filename'}), 400
            file.save(upload_path)

            return jsonify({
                'success': True,
                'message': f'OPSec image uploaded successfully: {filename}',
                'filename': filename
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/opsec-images', methods=['GET'])
    @require_auth(self.auth_manager)
    def list_opsec_images():
        """List all uploaded OPSec images with pagination support."""
        try:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 50, type=int)

            opsec_dir = os.path.join('static', 'opsec')
            if not os.path.exists(opsec_dir):
                return jsonify({'images': [], 'total': 0, 'page': page, 'per_page': per_page, 'has_next': False, 'has_prev': False})

            all_filenames = sorted([
                f for f in os.listdir(opsec_dir)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
            ])

            total_files = len(all_filenames)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            page_filenames = all_filenames[start_idx:end_idx]

            images = []
            for filename in page_filenames:
                file_path = os.path.join(opsec_dir, filename)
                try:
                    file_stat = os.stat(file_path)
                    file_size = file_stat.st_size
                    file_mtime = int(file_stat.st_mtime)
                except Exception:
                    file_size = 0
                    file_mtime = 0
                images.append({'filename': filename, 'size': file_size, 'url': f'/static/opsec/{filename}', 'thumb_url': f'/api/opsec-thumb/{filename}?v={file_mtime}'})

            return jsonify({
                'images': images,
                'total': total_files,
                'page': page,
                'per_page': per_page,
                'has_next': end_idx < total_files,
                'has_prev': page > 1,
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/delete-opsec/<filename>', methods=['DELETE'])
    @require_auth(self.auth_manager)
    def delete_opsec(filename):
        """Delete a specific OPSec image."""
        try:
            filename = secure_filename(filename)
            file_path = os.path.join('static', 'opsec', filename)

            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': 'File not found'}), 404

            os.remove(file_path)
            stem = os.path.splitext(filename)[0]
            thumb_path = os.path.join('static', 'opsec', 'thumbs', f'{stem}.webp')
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
            return jsonify({'success': True, 'message': f'OPSec image deleted: {filename}'})

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/opsec-hashes', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_opsec_hashes():
        """Get SHA-256 hashes of all existing OPSec images for duplicate detection."""
        try:
            import hashlib

            opsec_dir = os.path.join('static', 'opsec')
            if not os.path.exists(opsec_dir):
                return jsonify({'hashes': {}})

            hashes = {}
            for filename in os.listdir(opsec_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                    file_path = os.path.join(opsec_dir, filename)
                    try:
                        sha256_hash = hashlib.sha256()
                        with open(file_path, "rb") as f:
                            for byte_block in iter(lambda: f.read(4096), b""):
                                sha256_hash.update(byte_block)
                        hashes[sha256_hash.hexdigest()] = filename
                    except Exception as e:
                        print(f"Error hashing OPSec image {filename}: {e}")
                        continue

            return jsonify({'hashes': hashes})

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/download-opsec/<filename>', methods=['GET'])
    @require_auth(self.auth_manager)
    def download_opsec(filename):
        """Download a specific OPSec image file."""
        try:
            from flask import send_file
            filename = secure_filename(filename)
            file_path = os.path.join('static', 'opsec', filename)

            if not os.path.exists(file_path):
                return jsonify({'success': False, 'message': 'File not found'}), 404

            return send_file(os.path.abspath(file_path), as_attachment=True, download_name=filename)

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/rename-opsec', methods=['POST'])
    @require_auth(self.auth_manager)
    def rename_opsec():
        """Rename an OPSec image file."""
        try:
            data = request.get_json()
            if not data:
                return jsonify({'success': False, 'message': 'No data provided'}), 400

            old_filename = secure_filename(data.get('old_filename', ''))
            new_filename = secure_filename(data.get('new_filename', ''))

            if not old_filename or not new_filename:
                return jsonify({'success': False, 'message': 'Invalid filenames'}), 400

            old_path = os.path.join('static', 'opsec', old_filename)
            new_path = os.path.join('static', 'opsec', new_filename)

            if not os.path.exists(old_path):
                return jsonify({'success': False, 'message': 'File not found'}), 404

            if os.path.exists(new_path):
                return jsonify({'success': False, 'message': 'A file with that name already exists'}), 409

            if old_filename == new_filename:
                return jsonify({'success': False, 'message': 'New name is the same as old name'}), 400

            os.rename(old_path, new_path)
            return jsonify({
                'success': True,
                'message': f'OPSec image renamed: {old_filename} → {new_filename}',
                'old_filename': old_filename,
                'new_filename': new_filename
            })

        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500
