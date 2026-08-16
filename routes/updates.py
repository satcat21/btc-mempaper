"""Version reporting, releases, software update and display drivers.
"""
from utils.paths import PROJECT_ROOT

from flask import jsonify
from flask import request
from managers.auth_manager import require_auth
import os
import re
import requests
import subprocess
import sys
import threading
import time
import traceback

# The update log is a browser element, not a terminal. Helper scripts color
# their output for the SSH case - postinstall.sh sets a blue step marker and a
# green tick - and those escapes arrived in the log as literal [0;34m noise
# wrapped around every line.
_ANSI_RE = re.compile(r'\x1B\[[0-9;]*[A-Za-z]')


def _clean_line(line):
    """One line of subprocess output, ready to show in the browser."""
    return _ANSI_RE.sub('', line).rstrip('\n').rstrip()

# Defined in mempaper_app; imported lazily inside register() to avoid
# a circular import at module load time.


def register(self):
    """Register the updates routes."""
    from mempaper_app import _parse_git_remote, _safe_error

    @self.app.route('/api/update/current', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_current_version():
        """Get the currently checked-out git tag/commit."""
        try:
            project_dir = PROJECT_ROOT

            # Get current tag (if on a tag)
            try:
                current_tag = subprocess.check_output(
                    ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                    cwd=project_dir, stderr=subprocess.DEVNULL
                ).decode().strip()
            except subprocess.CalledProcessError:
                current_tag = None

            # Get current commit hash
            current_commit = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=project_dir, stderr=subprocess.DEVNULL
            ).decode().strip()

            return jsonify({
                'success': True,
                'current_tag': current_tag,
                'current_commit': current_commit
            })
        except Exception as e:
            print(f"Error getting current version: {e}")
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/update/releases', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_available_releases():
        """Fetch available releases from the git remote (GitHub or GitLab)."""
        try:
            project_dir = PROJECT_ROOT

            # Minimum version that supports web GUI updates — older releases
            # lack this feature and installing them would lock out the user.
            min_version = (2, 0, 0)

            def _parse_version(tag):
                """Parse 'v1.7.0' into (1, 7, 0) tuple, or None on failure."""
                try:
                    return tuple(int(x) for x in tag.lstrip('v').split('.'))
                except (ValueError, AttributeError):
                    return None

            # Read remote URL from git config
            remote_url = subprocess.check_output(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=project_dir, text=True
            ).strip()

            # rstrip('.git') was wrong: it strips any trailing '.', 'g', 'i'
            # and 't' characters, so a repo named 'digit' became 'd'.
            if remote_url.endswith('.git'):
                remote_url = remote_url[:-4]
            remote_url = remote_url.rstrip('/')

            remote_host, remote_path = _parse_git_remote(remote_url)
            is_gitlab = remote_host not in ('github.com', 'www.github.com')
            repo_url = remote_url
            platform = 'GitLab' if is_gitlab else 'GitHub'

            # Try fetching releases from the hosting API first
            # Optional: GIT_API_TOKEN in .env for private repo access
            api_token = os.getenv('GIT_API_TOKEN')
            if not api_token:
                try:
                    from dotenv import dotenv_values
                    env_path = os.path.join(project_dir, '.env')
                    env_vars = dotenv_values(env_path)
                    api_token = env_vars.get('GIT_API_TOKEN')
                except Exception:
                    pass

            api_releases = None
            try:
                if not is_gitlab:
                    api_url = f'https://api.github.com/repos/{remote_path}/releases'
                    headers = {'Accept': 'application/vnd.github.v3+json'}
                    if api_token:
                        headers['Authorization'] = f'Bearer {api_token}'
                else:
                    from urllib.parse import urlparse
                    parsed = urlparse(remote_url)
                    project_path = parsed.path.lstrip('/')
                    api_url = f'{parsed.scheme}://{parsed.hostname}/api/v4/projects/{requests.utils.quote(project_path, safe="")}/releases'
                    headers = {}
                    if api_token:
                        headers['PRIVATE-TOKEN'] = api_token

                resp = requests.get(api_url, headers=headers, timeout=15)
                resp.raise_for_status()
                api_releases = resp.json()
            except requests.RequestException:
                pass  # Fall back to local git tags

            if api_releases is not None:
                # Build result from API response (has release notes, dates, etc.)
                result = []
                for rel in api_releases:
                    tag_name = rel.get('tag_name', '')
                    ver = _parse_version(tag_name)
                    if ver is not None and ver < min_version:
                        continue
                    result.append({
                        'tag': tag_name,
                        'name': rel.get('name', '') or tag_name,
                        'published_at': rel.get('released_at', '') if is_gitlab else rel.get('published_at', ''),
                        'body': rel.get('description', '') if is_gitlab else rel.get('body', ''),
                        'prerelease': rel.get('upcoming_release', False) if is_gitlab else rel.get('prerelease', False),
                        'draft': False if is_gitlab else rel.get('draft', False)
                    })
            else:
                # Fallback: use local git tags (works for private repos)
                subprocess.run(
                    ['git', 'fetch', '--tags', '--force'],
                    cwd=project_dir, capture_output=True, timeout=30
                )
                tag_output = subprocess.check_output(
                    ['git', 'tag', '-l', '--sort=-version:refname'],
                    cwd=project_dir, text=True
                ).strip()

                result = []
                for tag_name in tag_output.splitlines():
                    tag_name = tag_name.strip()
                    if not tag_name:
                        continue
                    ver = _parse_version(tag_name)
                    if ver is not None and ver < min_version:
                        continue
                    # Get tag date
                    try:
                        date_str = subprocess.check_output(
                            ['git', 'log', '-1', '--format=%aI', tag_name],
                            cwd=project_dir, text=True
                        ).strip()
                    except subprocess.SubprocessError:
                        date_str = ''
                    result.append({
                        'tag': tag_name,
                        'name': tag_name,
                        'published_at': date_str,
                        'body': '',
                        'prerelease': False,
                        'draft': False
                    })

            return jsonify({'success': True, 'releases': result, 'repo_url': repo_url, 'platform': platform})
        except Exception as e:
            return jsonify({
                'success': False,
                'message': _safe_error(e, 'Failed to fetch releases')
            }), 502

    def _meme_download_cmd(project_dir: str, extra_args: list | None = None) -> list:
        """Build the subprocess command for tools/sync_memes.py.

        Automatically appends --tor when tor_meme_downloads is enabled in config.
        extra_args (e.g. ['--update'] or ['--status']) are appended after the tor flag.
        """
        venv_python = os.path.join(project_dir, '.venv', 'bin', 'python')
        python = venv_python if os.path.exists(venv_python) else 'python3'
        script = os.path.join(project_dir, 'tools', 'sync_memes.py')
        cmd = [python, script]
        if self.config_manager.get('tor_meme_downloads', False):
            cmd.append('--tor')
        if extra_args:
            cmd.extend(extra_args)
        return cmd

    @self.app.route('/api/update/install', methods=['POST'])
    @require_auth(self.auth_manager)
    def install_update():
        """Install a specific release by checking out its git tag."""
        if getattr(self, '_update_running', False):
            return jsonify({'success': False, 'message': 'Update already in progress'}), 409

        data = request.json or {}
        tag = data.get('tag', '').strip()
        if not tag:
            return jsonify({'success': False, 'message': 'No tag specified'}), 400

        project_dir = PROJECT_ROOT

        # Verify the tag exists before starting background work
        try:
            subprocess.check_call(
                ['git', 'fetch', '--tags', '--force'],
                cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
            )
            subprocess.check_call(
                ['git', 'rev-parse', f'refs/tags/{tag}'],
                cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            return jsonify({'success': False, 'message': f'Tag {tag} not found'}), 404

        def _emit(event, data):
            if self.socketio:
                self.socketio.emit(event, data, room='authenticated')

        def _run_update():
            self._update_running = True
            try:
                # Save rollback point
                rollback_commit = subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=project_dir, stderr=subprocess.DEVNULL
                ).decode().strip()

                try:
                    rollback_tag = subprocess.check_output(
                        ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                        cwd=project_dir, stderr=subprocess.DEVNULL
                    ).decode().strip()
                except subprocess.CalledProcessError:
                    rollback_tag = None

                # Check if dependency files changed between current and target
                deps_changed = False
                apt_deps_changed = False
                pillow_changed = False
                try:
                    def _effective_deps(ref, path):
                        """The package list a file declares, ignoring comments."""
                        out = subprocess.run(
                            ['git', 'show', f'{ref}:{path}'],
                            cwd=project_dir, capture_output=True, text=True
                        )
                        if out.returncode != 0:
                            return None      # file absent in that ref
                        return [
                            ln.strip() for ln in out.stdout.splitlines()
                            if ln.strip() and not ln.strip().startswith('#')
                        ]

                    def _deps_differ(path):
                        """True only when the declared packages actually differ.

                        Comparing the parsed list rather than the raw file keeps a
                        comment edit from triggering a full apt or pip run — one
                        word in a comment used to cost several minutes on a Pi
                        Zero. Returns True when either side cannot be read, so an
                        unreadable ref installs rather than silently skipping.
                        """
                        before = _effective_deps('HEAD', path)
                        after = _effective_deps(f'refs/tags/{tag}', path)
                        if before is None or after is None:
                            return True
                        return before != after

                    # Exact per-file checks. The previous substring test
                    # ('requirements.txt' in changed_files) also matched
                    # 'apt-requirements.txt', so an apt-only change always
                    # dragged the pip install along with it.
                    deps_changed = _deps_differ('requirements.txt')
                    apt_deps_changed = _deps_differ('apt-requirements.txt')
                    if deps_changed:
                        diff_content = subprocess.run(
                            ['git', 'diff', 'HEAD', f'refs/tags/{tag}', '--', 'requirements.txt'],
                            cwd=project_dir, capture_output=True, text=True
                        )
                        import re
                        pillow_changed = bool(re.search(r'^\+.*pillow==', diff_content.stdout, re.IGNORECASE | re.MULTILINE))
                except Exception:
                    deps_changed = True
                    apt_deps_changed = True

                # Git checkout
                _emit('update_output', {'line': self.translations.get('checking_out_code', 'Checking out {tag}...').format(tag=tag), 'phase': 'git', 'header': True})
                subprocess.check_call(
                    ['git', 'reset', '--hard'],
                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
                subprocess.check_call(
                    ['git', 'checkout', f'refs/tags/{tag}'],
                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                )
                _emit('update_output', {'line': self.translations.get('checked_out', 'Checked out {tag}').format(tag=tag), 'phase': 'git', 'header': True})

                # Check if the new release requires a different Python minor.
                # The venv is bound to the installed minor — a mismatch means
                # pip install will fail or install incompatible wheels.
                # When a mismatch is detected we run the upgrade script inline
                # (streams output to the UI) before continuing with pip install.
                py_version_file = os.path.join(project_dir, 'tools', 'python_version')
                if os.path.exists(py_version_file):
                    try:
                        _os_codename = ''
                        try:
                            with open('/etc/os-release') as _f:
                                for _l in _f:
                                    if _l.startswith('VERSION_CODENAME='):
                                        _os_codename = _l.split('=', 1)[1].strip().strip('"').lower()
                                        break
                        except OSError:
                            pass
                        required_minor = None
                        with open(py_version_file) as _f:
                            for _l in _f:
                                _l = _l.strip()
                                if '=' in _l and not _l.startswith('#'):
                                    _k, _v = _l.split('=', 1)
                                    if _k.strip().lower() == _os_codename:
                                        required_minor = int(_v.strip())
                                        break
                        current_minor = sys.version_info.minor
                        if required_minor is not None and current_minor < required_minor:
                            _emit('update_output', {
                                'line': f'Python 3.{required_minor} required (currently 3.{current_minor}) — upgrading Python first...',
                                'phase': 'pip', 'header': True
                            })
                            _emit('update_output', {
                                'line': 'This may take 20-30 minutes on Pi Zero 1 WH (compiling from source).',
                                'phase': 'pip'
                            })
                            try:
                                proc = subprocess.Popen(
                                    ['sudo', '/usr/local/bin/mempaper-upgrade-python'],
                                    cwd=project_dir,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1
                                )
                                for line in proc.stdout:
                                    _emit('update_output', {'line': _clean_line(line), 'phase': 'pip'})
                                proc.wait()
                                if proc.returncode != 0:
                                    subprocess.check_call(
                                        ['git', 'checkout', rollback_commit],
                                        cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                                    )
                                    _emit('update_done', {
                                        'success': False,
                                        'error': f'Python upgrade to 3.{required_minor} failed. Check logs or run tools/upgrade_python.sh manually via SSH.'
                                    })
                                    return
                                _emit('update_output', {
                                    'line': f'Python 3.{required_minor} upgrade complete — continuing with mempaper update.',
                                    'phase': 'pip', 'header': True
                                })
                            except Exception as py_err:
                                subprocess.check_call(
                                    ['git', 'checkout', rollback_commit],
                                    cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                                )
                                _emit('update_done', {
                                    'success': False,
                                    'error': f'Python upgrade failed: {py_err}. Run tools/upgrade_python.sh via SSH.'
                                })
                                return
                    except (ValueError, OSError):
                        pass  # malformed file — ignore and proceed

                # Install apt dependencies when the declared set changed, or when
                # anything it declares is not actually on the device.
                apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                apt_pkgs = []
                if os.path.exists(apt_req_file):
                    with open(apt_req_file) as f:
                        apt_pkgs = [
                            line.strip() for line in f
                            if line.strip() and not line.strip().startswith('#')
                        ]

                # The diff above only sees what changed between these two tags. A
                # package that was declared but never landed — a batch install that
                # one unavailable package aborted, a device with a stale index, an
                # install predating the wrapper — stayed missing forever, because
                # every later update found the file unchanged and skipped apt
                # entirely. Reconcile against dpkg rather than against the diff.
                missing_apt = self._missing_apt_packages(apt_pkgs) if apt_pkgs else []
                if missing_apt:
                    _emit('update_output', {'line': 'Declared but not installed: ' + ', '.join(missing_apt), 'phase': 'apt', 'header': True})

                if not apt_pkgs:
                    pass
                elif not apt_deps_changed and not missing_apt:
                    _emit('update_output', {'line': self.translations.get('system_deps_unchanged', 'System dependencies unchanged — skipping apt install'), 'phase': 'apt', 'header': True})
                else:
                    _emit('update_output', {'line': self.translations.get('installing_system_deps', 'Installing system dependencies...'), 'phase': 'apt', 'header': True})
                    try:
                        # Ensure root filesystem is writable (may be read-only after unclean shutdown)
                        subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], timeout=10, capture_output=True)
                        wrapper = '/usr/local/bin/mempaper-apt-install'
                        if not os.path.exists(wrapper):
                            _emit('update_output', {'line': f'{wrapper} not found — run "sudo bash tools/install_wifi_permissions.sh" over SSH to reinstall the helper scripts', 'phase': 'apt', 'header': True})
                        else:
                            proc = subprocess.Popen(
                                ['sudo', wrapper],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1
                            )
                            for line in proc.stdout:
                                _emit('update_output', {'line': _clean_line(line), 'phase': 'apt'})
                            proc.wait()
                            # Report on what dpkg holds now, not on the exit code — the
                            # user needs to know which package is still missing, not
                            # that "some" dependency failed.
                            still_missing = self._missing_apt_packages(apt_pkgs)
                            if still_missing:
                                _emit('update_output', {'line': 'Warning: still missing after install: ' + ', '.join(still_missing), 'phase': 'apt', 'header': True})
                            else:
                                _emit('update_output', {'line': self.translations.get('system_deps_installed', 'System dependencies installed'), 'phase': 'apt', 'header': True})
                    except Exception as apt_err:
                        _emit('update_output', {'line': f'Warning: {apt_err}', 'phase': 'apt'})

                # Re-apply post-install system configuration (periodic TRIM, and
                # whatever a later release adds to tools/postinstall.sh).
                #
                # This used to live inline in install.sh, which means it only ever
                # ran on a fresh install: a release that added a system-level step
                # shipped the release note to every device and the step to none of
                # the updated ones. The script is idempotent, so running it on every
                # update is cheap and converges a drifted device.
                #
                # Buffered rather than streamed, so a run that changed nothing
                # can be collapsed to one line. On a converged device every
                # check still reports itself, which put four lines of "already
                # correct" into this log on every update forever - the same
                # noise the pip step avoids just below. The script's own SSH
                # output is untouched; only the browser view is condensed.
                postinstall_wrapper = '/usr/local/bin/mempaper-postinstall'
                if os.path.exists(postinstall_wrapper):
                    try:
                        proc = subprocess.Popen(
                            ['sudo', postinstall_wrapper],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1
                        )
                        buffered = []
                        # Assume it did something: an older postinstall.sh emits
                        # no marker at all, and showing its output is the safe
                        # way to be wrong.
                        changed = True
                        for line in proc.stdout:
                            text = _clean_line(line)
                            if text.startswith('POSTINSTALL_RESULT='):
                                changed = text.split('=', 1)[1].strip() != 'unchanged'
                                continue
                            buffered.append(text)
                        proc.wait()
                        if changed or proc.returncode != 0:
                            _emit('update_output', {'line': self.translations.get('applying_postinstall', 'Applying post-install system configuration...'), 'phase': 'apt', 'header': True})
                            for text in buffered:
                                _emit('update_output', {'line': text, 'phase': 'apt'})
                        else:
                            _emit('update_output', {'line': self.translations.get('postinstall_unchanged', 'System configuration already applied — nothing to do'), 'phase': 'apt', 'header': True})
                    except Exception as post_err:
                        _emit('update_output', {'line': f'Warning: {post_err}', 'phase': 'apt'})
                else:
                    # Device installed before this wrapper existed. It cannot be
                    # created from here — that needs root — so name the one command
                    # that fixes it rather than failing quietly.
                    _emit('update_output', {'line': 'Skipping post-install configuration — run "sudo bash tools/install_wifi_permissions.sh" over SSH once to enable it', 'phase': 'apt', 'header': True})

                # Install pip dependencies (only when requirements.txt changed)
                venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
                requirements_file = os.path.join(project_dir, 'requirements.txt')

                if not deps_changed:
                    _emit('update_output', {'line': self.translations.get('python_deps_unchanged', 'Python dependencies unchanged — skipping pip install'), 'phase': 'pip', 'header': True})
                elif os.path.exists(venv_pip) and os.path.exists(requirements_file):
                    _emit('update_output', {'line': self.translations.get('installing_python_deps', 'Installing Python dependencies...'), 'phase': 'pip', 'header': True})
                    try:
                        proc = subprocess.Popen(
                            [venv_pip, 'install', '-r', requirements_file],
                            cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1
                        )
                        for line in proc.stdout:
                            _emit('update_output', {'line': _clean_line(line), 'phase': 'pip'})
                        proc.wait()
                        if proc.returncode != 0:
                            # Rollback on pip failure
                            _emit('update_output', {'line': self.translations.get('pip_install_failed_rollback', 'pip install failed, rolling back...'), 'phase': 'pip', 'header': True})
                            subprocess.check_call(
                                ['git', 'checkout', rollback_commit],
                                cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                            )
                            _emit('update_done', {
                                'success': False,
                                'error': self.translations.get('dep_install_failed_rollback', 'Dependency installation failed. Rolled back to previous version.')
                            })
                            return
                        _emit('update_output', {'line': self.translations.get('python_deps_installed', 'Python dependencies installed'), 'phase': 'pip', 'header': True})
                    except subprocess.TimeoutExpired:
                        subprocess.check_call(
                            ['git', 'checkout', rollback_commit],
                            cwd=project_dir, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
                        )
                        _emit('update_done', {
                            'success': False,
                            'error': self.translations.get('pip_timed_out_rollback_msg', 'pip install timed out. Rolled back to previous version.')
                        })
                        return

                # Write flag file if Pillow version changed
                if pillow_changed:
                    try:
                        flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
                        with open(flag_path, 'w') as f:
                            f.write('1')
                        _emit('update_output', {'line': self.translations.get('pillow_rebuild_scheduled', 'Pillow will be rebuilt from source after restart'), 'phase': 'pip', 'header': True})
                    except Exception:
                        pass

                # Re-minify JS+CSS if dist/ exists (user previously opted into minification)
                js_dist_dir  = os.path.join(project_dir, 'static', 'js', 'dist')
                css_dist_dir = os.path.join(project_dir, 'static', 'css', 'dist')
                minify_script = os.path.join(project_dir, 'tools', 'minify.py')
                has_js_dist  = os.path.isdir(js_dist_dir)  and bool(os.listdir(js_dist_dir))
                has_css_dist = os.path.isdir(css_dist_dir) and bool(os.listdir(css_dist_dir))
                dist_dir = js_dist_dir  # keep variable for compat
                if (has_js_dist or has_css_dist) and os.path.exists(minify_script):
                    _emit('update_output', {'line': 'Re-minifying JavaScript and CSS...', 'phase': 'pip', 'header': True})
                    try:
                        import sys as _sys
                        proc = subprocess.Popen(
                            [_sys.executable, minify_script],
                            cwd=project_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1
                        )
                        for line in proc.stdout:
                            _emit('update_output', {'line': _clean_line(line), 'phase': 'pip'})
                        proc.wait()
                        if proc.returncode == 0:
                            _emit('update_output', {'line': 'JavaScript and CSS minified successfully', 'phase': 'pip', 'header': True})
                        else:
                            _emit('update_output', {'line': 'Minification failed — app will use source files', 'phase': 'pip', 'header': True})
                    except Exception as minify_err:
                        _emit('update_output', {'line': f'JS minification skipped: {minify_err}', 'phase': 'pip'})

                # Emit restart message before update_done (frontend unsubscribes from update_output on done)
                _emit('update_output', {'line': self.translations.get('restarting_service', 'Restarting mempaper service...'), 'phase': 'restart', 'header': True})

                _emit('update_done', {
                    'success': True,
                    'tag': tag,
                    'rollback_tag': rollback_tag,
                    'rollback_commit': rollback_commit
                })

                # Wait for any ongoing e-ink display refresh to finish before restarting
                acquired = self._display_worker_lock.acquire(timeout=150)
                if acquired:
                    self._display_worker_lock.release()
                    print("✅ Display idle — safe to restart")
                else:
                    print("⚠️ Display lock timeout after 150s — restarting anyway")

                time.sleep(2)
                try:
                    subprocess.run(
                        ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                        timeout=30
                    )
                except Exception as restart_err:
                    print(f"Service restart failed: {restart_err}")

            except Exception as e:
                print(f"Update error: {e}")
                traceback.print_exc()
                _emit('update_done', {'success': False, 'error': str(e)})
            finally:
                self._update_running = False

        threading.Thread(target=_run_update, daemon=True).start()
        return jsonify({'success': True, 'message': 'Update started'})

    # ── Display Driver Install Endpoint ──────────────────────

    @self.app.route('/api/display/install-drivers', methods=['POST'])
    @require_auth(self.auth_manager)
    def install_display_drivers():
        """Install display drivers for the configured device."""
        try:
            data = request.json or {}
            device_id = data.get('device_id', '').strip()
            if not device_id:
                return jsonify({'success': False, 'message': 'No device_id specified'}), 400

            from tools.configure_display import (
                DEVICE_CONFIGS, DRIVER_DOWNLOADS, _drivers_missing, install_drivers
            )

            if device_id not in DEVICE_CONFIGS:
                return jsonify({'success': False, 'message': f'Unknown device: {device_id}'}), 400

            # Check if this device needs downloadable drivers
            if device_id not in DRIVER_DOWNLOADS:
                return jsonify({
                    'success': True,
                    'message': 'No driver download required for this device',
                    'installed': False,
                    'restart_required': False
                })

            missing = _drivers_missing(device_id)
            if not missing:
                # Drivers already on disk — nothing to do. The display worker
                # (subprocess) manages its own module state; importing
                # waveshare_display here would trigger SPI init in the Flask
                # process and contend with the worker, so we don't do that.
                return jsonify({
                    'success': True,
                    'message': 'Drivers already installed',
                    'installed': False,
                    'restart_required': False
                })

            print(f"📦 Installing display drivers for {device_id}...")
            ok = install_drivers(device_id)

            if ok:
                print(f"✅ Display drivers installed for {device_id}")

                # SPI must be enabled for the hardware to work
                spi_missing = not os.path.exists('/dev/spidev0.0')
                if spi_missing:
                    print(f"⚠️ SPI interface not enabled — /dev/spidev0.0 missing.")
                    print(f"   Enable it: sudo raspi-config nonint do_spi 0 && sudo reboot")
                    return jsonify({
                        'success': True,
                        'message': (
                            f'Drivers installed for {DEVICE_CONFIGS[device_id]["name"]}, '
                            f'but SPI is not enabled. '
                            f'Run: sudo raspi-config nonint do_spi 0 && sudo reboot'
                        ),
                        'installed': True,
                        'restart_required': False,
                        'spi_required': True,
                    })

                # Schedule service restart so new drivers are loaded
                def _delayed_restart():
                    time.sleep(2)
                    try:
                        subprocess.run(
                            ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                            timeout=30
                        )
                    except Exception as e:
                        print(f"Service restart failed: {e}")

                threading.Thread(target=_delayed_restart, daemon=True).start()

                return jsonify({
                    'success': True,
                    'message': f'Drivers installed for {DEVICE_CONFIGS[device_id]["name"]}. Service restarting...',
                    'installed': True,
                    'restart_required': True,
                    'spi_required': False,
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Driver download failed. Check internet connection.'
                }), 500

        except Exception as e:
            print(f"Driver install error: {e}")
            traceback.print_exc()
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    # ── Display Status Endpoint ────────────────────────────────

    @self.app.route('/api/display/status', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_display_status():
        """Return current display error state (if any)."""
        err = self._last_display_error
        if err:
            return jsonify({
                'success': True,
                'error': err['message'],
                'timestamp': err['timestamp'],
                'display_disabled': True,
            })
        return jsonify({'success': True, 'error': None, 'display_disabled': False})

    @self.app.route('/api/system/dependency-status', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_dependency_status():
        """Return any apt-dependency compatibility issues found at startup
        (e.g. nft/dnsmasq syntax breaking after a system package update)."""
        issues = self._dependency_health_issues
        return jsonify({'success': True, 'issues': issues or []})

    # ── System Package Update Endpoint ────────────────────────

    @self.app.route('/api/system/update-packages', methods=['POST'])
    @require_auth(self.auth_manager)
    def update_system_packages():
        """Run apt update && apt upgrade -y in background, streaming output via SocketIO."""
        if getattr(self, '_apt_running', False):
            return jsonify({'success': False, 'message': 'System update already in progress'}), 409

        def _is_mount_readonly(mount_point):
            """Check if the given mount point is mounted read-only."""
            try:
                with open('/proc/mounts') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 4 and parts[1] == mount_point:
                            return 'ro' in parts[3].split(',')
            except Exception:
                pass
            return False

        # /boot/firmware is a separate mount point from / on Raspberry Pi
        # OS and is not covered by remounting / read-write. If it stays
        # read-only, initramfs-tools' post-install hook fails to write the
        # new initramfs there, which makes dpkg (and apt upgrade) fail.
        _remount_targets = ['/', '/boot/firmware']

        def _emit(event, data):
            if self.socketio:
                self.socketio.emit(event, data, room='authenticated')

        def _run_apt():
            self._apt_running = True
            readonly_targets = []
            try:
                # Check each filesystem that may be read-only and remount rw if needed
                targets_to_remount = [t for t in _remount_targets if _is_mount_readonly(t)]
                if targets_to_remount:
                    _emit('apt_output', {'line': self.translations.get('remounting_filesystem', 'Remounting filesystem...'), 'phase': 'prepare', 'header': True})
                    for target in targets_to_remount:
                        rc = subprocess.call(['sudo', 'mount', '-o', 'remount,rw', target])
                        if rc != 0:
                            _emit('apt_done', {
                                'success': False,
                                'error': self.translations.get('remount_failed', 'Failed to remount filesystem read-write')
                            })
                            return
                        readonly_targets.append(target)

                phase_labels = {
                    'update': self.translations.get('fetching_package_list', 'Fetching package list (apt update)...'),
                    'upgrade': self.translations.get('installing_upgrades', 'Installing upgrades (apt upgrade)...'),
                }
                for phase, cmd in [
                    ('update', ['sudo', 'apt-get', 'update']),
                    ('upgrade', ['sudo', 'apt-get', 'upgrade', '-y']),
                ]:
                    _emit('apt_output', {'line': phase_labels.get(phase, f'apt {phase}'), 'phase': phase, 'header': True})

                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    for line in proc.stdout:
                        _emit('apt_output', {'line': _clean_line(line), 'phase': phase})

                    proc.wait()
                    if proc.returncode != 0:
                        _emit('apt_done', {
                            'success': False,
                            'error': f'apt {phase} failed (exit code {proc.returncode})'
                        })
                        return

                # Ensure all packages from apt-requirements.txt are installed.
                # Must go through the scoped mempaper-apt-install wrapper — the
                # sudoers file only grants NOPASSWD for that exact wrapper path
                # (accepts no arguments, reads apt-requirements.txt itself), not
                # for 'apt-get install' invoked directly with a package list.
                project_dir = PROJECT_ROOT
                apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                if os.path.exists(apt_req_file):
                    with open(apt_req_file) as f:
                        apt_pkgs = [
                            line.strip() for line in f
                            if line.strip() and not line.strip().startswith('#')
                        ]
                    if apt_pkgs:
                        _emit('apt_output', {'line': self.translations.get('installing_mempaper_deps', 'Installing mempaper dependencies...'), 'phase': 'deps', 'header': True})
                        proc = subprocess.Popen(
                            ['sudo', '/usr/local/bin/mempaper-apt-install'],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        for line in proc.stdout:
                            _emit('apt_output', {'line': _clean_line(line), 'phase': 'deps'})
                        proc.wait()
                        if proc.returncode != 0:
                            _emit('apt_output', {'line': self.translations.get('mempaper_deps_warning', 'Warning: some mempaper dependencies failed to install'), 'phase': 'deps', 'header': True})

                _emit('apt_done', {'success': True})
            except Exception as e:
                print(f"System update error: {e}")
                _emit('apt_done', {'success': False, 'error': str(e)})
            finally:
                # Restore read-only for whichever mounts were read-only before
                if readonly_targets:
                    _emit('apt_output', {'line': self.translations.get('restoring_readonly', 'Restoring read-only filesystem...'), 'phase': 'cleanup', 'header': True})
                    for target in reversed(readonly_targets):
                        subprocess.call(['sudo', 'mount', '-o', 'remount,ro', target])
                self._apt_running = False

        threading.Thread(target=_run_apt, daemon=True).start()
        return jsonify({'success': True, 'message': 'System update started'})
