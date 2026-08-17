"""Version reporting, releases, software update and display drivers.
"""
from utils.paths import PROJECT_ROOT

from flask import jsonify
from flask import request
from managers.auth_manager import require_auth
from utils.apt_requirements import package_names, parse_apt_requirements, pinned_versions
import os
import re
import requests
import subprocess
import sys
import threading
import time
import traceback

# Packages a source-built Pillow links against. Pillow is compiled on this
# device rather than installed as a wheel - that is what the .pillow-rebuild-
# needed mechanism exists for - so when one of these moves underneath it the
# result is a Pillow that either lost a codec or refuses to import. A full
# upgrade is precisely the operation that moves them.
PILLOW_NATIVE_DEPS = (
    'libjpeg62-turbo', 'libwebp7', 'libwebpdemux2', 'libwebpmux3',
    'libfreetype6', 'libopenjp2-7', 'zlib1g', 'libtiff6', 'liblcms2-2',
)

# Held to pin the Python minor the venv is built against. Never a candidate for
# removal, and named here so the guard below can say so by name.
PYTHON_PINS = ('python3', 'python3-dev', 'python3-venv')


def _permissions_hint(translations, key, default, project_dir):
    """The 'run this over SSH' line, translated and filled in.

    Two substitutions matter and neither is guessable by whoever reads it:

      {path}  install.sh *moves* the repo into the service user's home, so it
              is not under the admin's ~ and a relative path resolves elsewhere.
      {user}  the account the grants are for — which is not the account running
              the command. The service user is a system account with no
              password and no sudo-group membership, and the scoped sudoers set
              grants named commands rather than bash, so it cannot run this at
              all. It has to be done from an account that can sudo.

    A translation missing a placeholder is fine; one with a stray brace is not,
    so formatting failures fall back to the unformatted string rather than
    taking the update down over a message.
    """
    text = (translations or {}).get(key) or default
    try:
        return text.format(path=project_dir, user=os.environ.get('USER', 'mempaper'))
    except (KeyError, IndexError, ValueError):
        return text


def _write_version_reports(project_dir, emit_line):
    """Refresh cache/currently_installed_*.txt after a successful operation.

    Deliberately swallows its own failures: this is a report written at the tail
    of work that has already succeeded, and being unable to write it is not a
    reason to tell the user their upgrade failed.
    """
    try:
        from utils.installed_report import write_installed_reports
        write_installed_reports(project_dir, log=emit_line)
    except Exception as exc:
        try:
            emit_line(f'Could not write version report: {exc}')
        except Exception:
            pass


def _simulate_dist_upgrade():
    """What a full upgrade would do, without doing any of it.

    `apt-get -s` prints one machine-readable verb per action - Inst, Conf,
    Remv - which is far steadier to parse than the human summary and is the
    reason this can be trusted as a gate. An Inst line carrying a bracketed
    old version is an upgrade; one without is a new package.

    Runs unprivileged on purpose: simulation needs no root, so the preview a
    user is shown before approving costs no grant at all.

    Returns (upgrade, install, remove, error). Any failure yields empty lists
    and an error string, and the caller must treat that as "do not proceed" -
    an unreadable simulation is not permission to run the real thing.

    Every error string returned here reaches a browser - the preview endpoint
    puts it in a JSON response, and the full-upgrade run emits it over the
    socket. So a failure to run the command at all is logged server-side and
    reported generically: the exception text carries interpreter internals and
    filesystem paths, which say more about the host than the person clicking
    "upgrade" needs. apt's own stderr below is kept, being the diagnostic the
    operator actually came for and not a view into the process.
    """
    from mempaper_app import _safe_error
    try:
        proc = subprocess.run(
            ['apt-get', '-s', 'dist-upgrade'],
            capture_output=True, text=True, timeout=180
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return [], [], [], _safe_error(exc, 'apt-get -s dist-upgrade could not be run')
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or '').strip().splitlines()
        return [], [], [], '; '.join(tail[-3:]) or f'apt-get -s exited {proc.returncode}'

    upgrade, install, remove = [], [], []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        verb, name = parts[0], parts[1]
        if verb == 'Inst':
            # 'Inst name [old-version] (new-version …)' is an upgrade;
            # 'Inst name (new-version …)' is a package that was not there before.
            if len(parts) >= 3 and parts[2].startswith('['):
                upgrade.append(name)
            else:
                install.append(name)
        elif verb == 'Remv':
            remove.append(name)
    return upgrade, install, remove, None


def _installed_versions(names):
    """{name: version} for those of `names` dpkg currently has installed."""
    if not names:
        return {}
    try:
        proc = subprocess.run(
            ['dpkg-query', '-W', '-f=${Package} ${Status} ${Version}\\n'] + list(names),
            capture_output=True, text=True, timeout=30
        )
    except (subprocess.SubprocessError, OSError):
        return {}
    out = {}
    for line in (proc.stdout or '').splitlines():
        parts = line.split()
        # 'name want error state version' — only an installed state has a
        # version worth recording, and a purged package prints none at all.
        if len(parts) >= 5 and parts[3] == 'installed':
            out[parts[0]] = parts[4]
    return out

# The update log is a browser element, not a terminal. Helper scripts color
# their output for the SSH case - postinstall.sh sets a blue step marker and a
# green tick - and those escapes arrived in the log as literal [0;34m noise
# wrapped around every line.
_ANSI_RE = re.compile(r'\x1B\[[0-9;]*[A-Za-z]')


def _clean_line(line):
    """One line of subprocess output, ready to show in the browser."""
    return _ANSI_RE.sub('', line).rstrip('\n').rstrip()


def _line_emitter(emit, event, phase):
    """Adapt a route's socket emit into the emit(line, header=False) callback
    the helpers below take, so they stay free of event names and phase labels.

    'header' is added only when true, keeping the payload byte-identical to the
    ones built inline everywhere else - the page keys off its presence.
    """
    def _say(line, header=False):
        payload = {'line': line, 'phase': phase}
        if header:
            payload['header'] = True
        emit(event, payload)
    return _say


def _apt_env():
    """The environment apt subprocesses should run with.

    There is no terminal behind a web request, so debconf tried Dialog, then
    Readline, then Teletype, and announced each failure before falling back to
    Noninteractive - eight lines of apology in the log on every single run.
    Naming the frontend up front skips the whole cascade.

    Passed as the child's environment rather than on the command line, because
    the sudoers set grants these invocations by exact command match
    ('apt-get update', no wildcard): 'sudo DEBIAN_FRONTEND=noninteractive
    apt-get update' is a *different* command and sudo refuses it outright. It
    reaches root through the env_keep grant install_permissions.sh writes
    instead. A device whose sudoers predates that grant simply drops the
    variable and behaves exactly as it does today.

    This settles the frontend, not dpkg's conffile question - that would need
    -o Dpkg::Options::=--force-confold, which is again a command line the
    grants would no longer match. dpkg with no tty on stdin keeps the installed
    conffile and says so, which is the answer we would have given anyway.
    """
    env = dict(os.environ)
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    return env


def _flag_pillow_rebuild(project_dir, before, emit):
    """Set the rebuild flag if any library Pillow links against has moved.

    `before` is a {name: version} snapshot taken before the apt work started.
    Pillow is compiled on this device, so when one of these moves underneath it
    the build in the venv is linked against a version that is no longer
    installed - it loses a codec, or refuses to import at all. Reuses the
    existing .pillow-rebuild-needed mechanism rather than inventing a second.

    A package missing from `before` was newly installed, which is not a move. A
    package missing *now* was removed, which the protected-package gate exists
    to prevent and which rebuilding could not repair in any case.

    Returns the names whose version changed, or [] - including when the flag
    could not be written, since a caller that cannot record the need has
    nothing useful to report about it.
    """
    after = _installed_versions(PILLOW_NATIVE_DEPS)
    moved = sorted(n for n, v in after.items() if before.get(n) not in (None, v))
    if not moved:
        return []
    try:
        with open(os.path.join(project_dir, '.pillow-rebuild-needed'), 'w') as f:
            f.write('native libraries changed: ' + ', '.join(moved))
    except OSError:
        return []
    emit('Pillow will be rebuilt from source after restart ('
         + ', '.join(moved) + ' changed)', header=True)
    return moved


def _run_postinstall(wrapper, translations, emit):
    """Run the postinstall wrapper, showing its output only if it did something.

    The script reports what it did on a POSTINSTALL_RESULT= line. That line is
    protocol between it and this function, not something to put in front of a
    user, so it is consumed here and never emitted - it leaked into the browser
    log verbatim for as long as one of the two call sites streamed the script
    directly instead of going through this.

    Buffered for the same reason: the script is idempotent and every check
    announces itself even when it changed nothing, so streaming it wrote four
    lines of 'already correct' into the log on every update forever. Its own
    output over SSH is untouched; only the browser view is condensed.

    Returns the exit code, or None if the wrapper could not be run at all.
    """
    t = translations or {}
    try:
        proc = subprocess.Popen(
            ['sudo', wrapper], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
    except (subprocess.SubprocessError, OSError) as exc:
        emit(f'Warning: {exc}', header=True)
        return None

    buffered = []
    # Assume it did something: an older postinstall.sh emits no marker at all,
    # and showing its output is the safe way to be wrong.
    changed = True
    for line in proc.stdout:
        text = _clean_line(line)
        if text.startswith('POSTINSTALL_RESULT='):
            changed = text.split('=', 1)[1].strip() != 'unchanged'
            continue
        buffered.append(text)
    proc.wait()

    if changed or proc.returncode != 0:
        emit(t.get('applying_postinstall',
                   'Applying post-install system configuration...'), header=True)
        for text in buffered:
            emit(text)
    else:
        emit(t.get('postinstall_unchanged',
                   'System configuration already applied — nothing to do'), header=True)
    if proc.returncode != 0:
        emit(f'Warning: post-install configuration exited {proc.returncode}', header=True)
    return proc.returncode

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

    # ── Meme sync ─────────────────────────────────────────────────────────
    # The weekly cron entry runs exactly this command; these routes give it a
    # button so a new device does not have to wait until the scheduled day to
    # get its memes, and so a failed scheduled run can be retried without SSH.
    # State lives in the output directory rather than in this process — the
    # downloader keeps its own status/stop files so a run survives a service
    # restart, and the status route reads what it wrote.

    @self.app.route('/api/memes/sync-status', methods=['GET'])
    @require_auth(self.auth_manager)
    def meme_sync_status():
        """idle / running / paused / done, straight from the downloader."""
        try:
            out = subprocess.run(
                _meme_download_cmd(PROJECT_ROOT, ['--status']),
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
            )
            status = (out.stdout or '').strip().splitlines()
            return jsonify({'success': True, 'status': status[-1] if status else 'idle'})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/memes/sync-stop', methods=['POST'])
    @require_auth(self.auth_manager)
    def meme_sync_stop():
        """Ask a running download to stop at the next clean point.

        The downloader is resumable, so this pauses rather than cancels: the
        discovered-UUID cache survives and the next run picks up where this one
        left off instead of re-walking several thousand tags.
        """
        try:
            subprocess.run(
                _meme_download_cmd(PROJECT_ROOT, ['--stop']),
                cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=30
            )
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error(e)}), 500

    @self.app.route('/api/memes/sync', methods=['POST'])
    @require_auth(self.auth_manager)
    def meme_sync_start():
        """Fetch memes that are not already on disk, streaming progress."""
        if getattr(self, '_meme_sync_running', False):
            return jsonify({'success': False, 'message': 'A meme sync is already running'}), 409

        # --update is the cheap path: it asks which UUIDs are new relative to
        # what is on disk instead of re-discovering the whole catalogue. A full
        # rescan is available from the CLI and deliberately not from a button —
        # it walks thousands of tags and takes hours on a Pi Zero.
        cmd = _meme_download_cmd(PROJECT_ROOT, ['--update'])

        def _emit(event, data):
            if self.socketio:
                self.socketio.emit(event, data, room='authenticated')

        def _run():
            self._meme_sync_running = True
            try:
                _emit('meme_sync_output', {'line': self.translations.get('syncing_memes', 'Checking einundzwanzig-memes.space for new memes...'), 'header': True})
                proc = subprocess.Popen(
                    cmd, cwd=PROJECT_ROOT, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1
                )
                for line in proc.stdout:
                    _emit('meme_sync_output', {'line': _clean_line(line)})
                proc.wait()
                _emit('meme_sync_done', {
                    'success': proc.returncode == 0,
                    'error': None if proc.returncode == 0 else f'Meme sync exited {proc.returncode}',
                })
            except Exception as e:
                print(f"Meme sync error: {e}")
                _emit('meme_sync_done', {'success': False, 'error': _safe_error(e)})
            finally:
                self._meme_sync_running = False

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'success': True, 'message': 'Meme sync started'})

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

                    def _file_differs(path):
                        """True when the file's raw bytes differ between the two refs.

                        Used for the helper-script refresh, where _deps_differ's
                        parsed comparison makes no sense: every line of a shell
                        script matters, including its comments, because the file
                        *is* the thing being deployed.

                        Absent from *both* refs is not a change — it is a file
                        this release has nothing to say about. Returning True
                        there, as this once did, meant that a path which had been
                        renamed away reported a difference on every update
                        forever, re-running the permissions refresh each time.
                        Absent from exactly one ref *is* a change: the file was
                        added or removed, and both are worth acting on.
                        """
                        before = subprocess.run(['git', 'show', f'HEAD:{path}'],
                                                cwd=project_dir, capture_output=True)
                        after = subprocess.run(['git', 'show', f'refs/tags/{tag}:{path}'],
                                               cwd=project_dir, capture_output=True)
                        if before.returncode != 0 and after.returncode != 0:
                            return False
                        if before.returncode != 0 or after.returncode != 0:
                            return True
                        return before.stdout != after.stdout

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

                # ── Refresh the sudo wrappers and sudoers set ───────────────
                # tools/install_permissions.sh generates every helper this
                # updater calls — mempaper-apt-install above all — plus the
                # sudoers grants that make them reachable. When a release
                # changes it, the device keeps running the previous generation
                # until someone SSHes in as a sudo-capable user, which meant a
                # release could ship a new grant to every device and the grant
                # to none of them. Re-run it from here instead, and do it before
                # the apt step below so the same update uses the new wrapper
                # rather than the next one.
                #
                # Both names are checked. The script was called
                # install_wifi_permissions.sh until it outgrew the name, and the
                # release that renames it changes neither file's *content* —
                # only its path — so watching the new name alone would miss
                # exactly the update that matters most, the one that repoints
                # the refresh wrapper.
                #
                # Only when something actually changed: regenerating sudoers on
                # every update is a write to /etc for no reason, and this runs
                # on devices where / is remounted read-only between updates.
                perms_wrapper = '/usr/local/bin/mempaper-refresh-permissions'
                perms_changed = False
                try:
                    perms_changed = (_file_differs('tools/install_permissions.sh')
                                     or _file_differs('tools/install_wifi_permissions.sh'))
                except Exception:
                    perms_changed = True
                if perms_changed and os.path.exists(perms_wrapper):
                    _emit('update_output', {'line': self.translations.get('refreshing_permissions', 'Refreshing helper scripts and sudo permissions...'), 'phase': 'apt', 'header': True})
                    try:
                        subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], timeout=10, capture_output=True)
                        proc = subprocess.Popen(
                            ['sudo', perms_wrapper],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1
                        )
                        for line in proc.stdout:
                            _emit('update_output', {'line': _clean_line(line), 'phase': 'apt'})
                        proc.wait()
                        if proc.returncode != 0:
                            _emit('update_output', {'line': f'Warning: permissions refresh exited {proc.returncode} — some helpers may be stale', 'phase': 'apt', 'header': True})
                    except Exception as perm_err:
                        _emit('update_output', {'line': f'Warning: {perm_err}', 'phase': 'apt'})
                elif perms_changed:
                    # The device predates the refresh wrapper. It cannot install
                    # the wrapper from here — that needs root — so this is the
                    # one remaining case that still wants an SSH session, and it
                    # happens exactly once per device.
                    # Absolute path and a cd, because neither is guessable from
                    # an admin shell: install.sh *moves* the repo into the
                    # service user's home, so it is not under the admin's ~, and
                    # the service user cannot run this at all — it is a system
                    # account with no password and no sudo-group membership, and
                    # the scoped sudoers set grants specific commands, not bash.
                    _user = os.environ.get('USER', 'mempaper')
                    _emit('update_output', {
                        'line': f'Helper scripts changed in this release but {perms_wrapper} is not installed yet. '
                                f'Over SSH, as a user that can sudo, run once: '
                                f'cd {project_dir} && sudo bash tools/install_permissions.sh {_user} '
                                f'— future releases will apply themselves.',
                        'phase': 'apt', 'header': True})

                # Install apt dependencies when the declared set changed, or when
                # anything it declares is not actually on the device.
                #
                # Parsed through utils.apt_requirements rather than by stripping
                # comments here. A declaration may be 'name' or 'name=version',
                # and the name is what dpkg-query takes: the hand-rolled read
                # this replaces passed the whole 'tor=0.4.9.11-0+deb13u1' spec
                # through, so dpkg reported an unknown package and *every*
                # pinned package was announced as "declared but not installed"
                # — immediately before the wrapper correctly reported the same
                # packages as already present. Pinning the file turned the
                # entire declared set into a phantom missing list.
                apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                apt_entries = parse_apt_requirements(apt_req_file)
                apt_pkgs = package_names(apt_entries)

                # The diff above only sees what changed between these two tags. A
                # package that was declared but never landed — a batch install that
                # one unavailable package aborted, a device with a stale index, an
                # install predating the wrapper — stayed missing forever, because
                # every later update found the file unchanged and skipped apt
                # entirely. Reconcile against dpkg rather than against the diff.
                missing_apt = self._missing_apt_packages(apt_pkgs) if apt_pkgs else []
                if missing_apt:
                    _emit('update_output', {'line': 'Declared but not installed: ' + ', '.join(missing_apt), 'phase': 'apt', 'header': True})

                # A pinned package sitting at some other version is installed, so
                # the check above calls the device converged while a declaration
                # goes unsatisfied. The startup dependency check has always looked
                # for this; the updater did not, which meant the one operation that
                # changes the declared pins was the one that never noticed drift.
                drifted_apt = self._drifted_pins(pinned_versions(apt_entries)) if apt_entries else []
                if drifted_apt:
                    _emit('update_output', {'line': 'Pinned to another version: ' + ', '.join(drifted_apt), 'phase': 'apt', 'header': True})

                if not apt_pkgs:
                    pass
                elif not apt_deps_changed and not missing_apt and not drifted_apt:
                    _emit('update_output', {'line': self.translations.get('system_deps_unchanged', 'System dependencies unchanged — skipping apt install'), 'phase': 'apt', 'header': True})
                else:
                    _emit('update_output', {'line': self.translations.get('installing_system_deps', 'Installing system dependencies...'), 'phase': 'apt', 'header': True})
                    try:
                        # Ensure root filesystem is writable (may be read-only after unclean shutdown)
                        subprocess.run(['sudo', 'mount', '-o', 'remount,rw', '/'], timeout=10, capture_output=True)
                        wrapper = '/usr/local/bin/mempaper-apt-install'
                        if not os.path.exists(wrapper):
                            # Name the account, and give the absolute path. The
                            # script derives the account from the systemd unit
                            # when the argument is omitted, but a command someone
                            # is about to paste into a root shell should not rely
                            # on a default to be right — and the repo is not
                            # under the admin's home, so a relative path is not
                            # merely unhelpful, it resolves somewhere else.
                            _u = os.environ.get('USER', 'mempaper')
                            _emit('update_output', {'line': f'{wrapper} not found — over SSH, run: cd {project_dir} && sudo bash tools/install_permissions.sh {_u}', 'phase': 'apt', 'header': True})
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
                            still_drifted = self._drifted_pins(pinned_versions(apt_entries))
                            if still_missing:
                                _emit('update_output', {'line': 'Warning: still missing after install: ' + ', '.join(still_missing), 'phase': 'apt', 'header': True})
                            if still_drifted:
                                _emit('update_output', {'line': 'Warning: still pinned to another version after install: ' + ', '.join(still_drifted), 'phase': 'apt', 'header': True})
                            if not still_missing and not still_drifted:
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
                postinstall_wrapper = '/usr/local/bin/mempaper-postinstall'
                if os.path.exists(postinstall_wrapper):
                    _run_postinstall(postinstall_wrapper, self.translations,
                                     _line_emitter(_emit, 'update_output', 'apt'))
                else:
                    # Device installed before this wrapper existed. It cannot be
                    # created from here — that needs root — so name the one command
                    # that fixes it rather than failing quietly.
                    #
                    # Translated and formatted here rather than shipped as a
                    # fixed English sentence for the page to look up by exact
                    # match: the command carries the project path now, so no
                    # literal key could match it, and a line the page could not
                    # match fell through to English regardless of the configured
                    # language.
                    _emit('update_output', {
                        'line': _permissions_hint(self.translations, 'skipping_postinstall',
                                                  'Skipping post-install configuration — over SSH, run once: '
                                                  'cd {path} && sudo bash tools/install_permissions.sh {user}',
                                                  project_dir),
                        'phase': 'apt', 'header': True})

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

                # Record what this release actually resolved to. Written after
                # everything else has succeeded, so the report describes a
                # combination that installed cleanly rather than one that was
                # half-applied.
                _write_version_reports(project_dir,
                                       lambda m: _emit('update_output', {'line': m, 'phase': 'pip'}))

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
                _emit('update_done', {'success': False, 'error': _safe_error(e, 'Update error')})
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

                # Before any apt work: an ordinary upgrade moves the libraries a
                # source-built Pillow is linked against just as readily as a full
                # upgrade does — libfreetype6 and zlib1g get security updates
                # through exactly this path — and this route never looked.
                project_dir = PROJECT_ROOT
                pillow_before = _installed_versions(PILLOW_NATIVE_DEPS)
                pillow_checked = False

                def _check_pillow():
                    """As in the full-upgrade route: once, however this ends.

                    'apt upgrade failed' returns below with the transaction
                    part-applied, which is precisely a state where a native
                    library has moved and Pillow needs rebuilding.
                    """
                    nonlocal pillow_checked
                    if pillow_checked:
                        return
                    pillow_checked = True
                    _flag_pillow_rebuild(project_dir, pillow_before,
                                         _line_emitter(_emit, 'apt_output', 'deps'))

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
                        bufsize=1,
                        env=_apt_env()
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
                apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                if package_names(parse_apt_requirements(apt_req_file)):
                    _emit('apt_output', {'line': self.translations.get('installing_mempaper_deps', 'Installing mempaper dependencies...'), 'phase': 'deps', 'header': True})
                    proc = subprocess.Popen(
                        ['sudo', '/usr/local/bin/mempaper-apt-install'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        env=_apt_env()
                    )
                    for line in proc.stdout:
                        _emit('apt_output', {'line': _clean_line(line), 'phase': 'deps'})
                    proc.wait()
                    if proc.returncode != 0:
                        _emit('apt_output', {'line': self.translations.get('mempaper_deps_warning', 'Warning: some mempaper dependencies failed to install'), 'phase': 'deps', 'header': True})

                # Everything apt was going to touch has now been touched.
                _check_pillow()

                _write_version_reports(project_dir,
                                       lambda m: _emit('apt_output', {'line': m, 'phase': 'deps'}))

                _emit('apt_done', {'success': True})
            except Exception as e:
                _emit('apt_done', {'success': False, 'error': _safe_error(e, 'System update error')})
            finally:
                # Written even when the upgrade bailed out — see the note on the
                # same call in the full-upgrade route.
                try:
                    _check_pillow()
                except Exception:
                    pass
                # Restore read-only for whichever mounts were read-only before
                if readonly_targets:
                    _emit('apt_output', {'line': self.translations.get('restoring_readonly', 'Restoring read-only filesystem...'), 'phase': 'cleanup', 'header': True})
                    for target in reversed(readonly_targets):
                        subprocess.call(['sudo', 'mount', '-o', 'remount,ro', target])
                self._apt_running = False

        threading.Thread(target=_run_apt, daemon=True).start()
        return jsonify({'success': True, 'message': 'System update started'})

    # ── Full Upgrade ──────────────────────────────────────────────────────

    def _protected_packages():
        """Packages a full upgrade must never be allowed to remove.

        Everything apt-requirements.txt declares, plus the Python metapackages
        the venv is pinned against. These are the packages whose absence turns
        the device into a brick that can only be fixed with a keyboard and a
        monitor, which is the failure this whole gate exists to prevent.
        """
        entries = parse_apt_requirements(os.path.join(PROJECT_ROOT, 'apt-requirements.txt'))
        return set(package_names(entries)) | set(PYTHON_PINS)

    @self.app.route('/api/system/upgrade-preview', methods=['GET'])
    @require_auth(self.auth_manager)
    def get_upgrade_preview():
        """What a full upgrade would change, for the confirmation dialog.

        The removal list is the reason this exists. `apt upgrade` cannot remove
        anything, so the existing System Update button needs no preview; a full
        upgrade resolves dependency changes by removing packages, and the user
        approving it deserves to see which ones before rather than after.
        """
        upgrade, install, remove, error = _simulate_dist_upgrade()
        if error:
            return jsonify({'success': False, 'message': error}), 500
        protected = _protected_packages()
        blocked = sorted(set(remove) & protected)
        return jsonify({
            'success': True,
            'upgrade': sorted(upgrade),
            'install': sorted(install),
            'remove': sorted(remove),
            # Non-empty means the run will refuse. Surfaced here so the dialog
            # can say so up front instead of offering a button that aborts.
            'blocked': blocked,
            'pinned': pinned_versions(parse_apt_requirements(
                os.path.join(PROJECT_ROOT, 'apt-requirements.txt'))),
        })

    @self.app.route('/api/system/full-upgrade', methods=['POST'])
    @require_auth(self.auth_manager)
    def full_upgrade_system():
        """apt update → upgrade → full-upgrade → autoremove, then reconcile.

        The sequence the maintainer would run by hand, with three things a hand
        run does not get: a refusal if the resolver wants to remove something
        mempaper depends on, a re-pin pass so declared versions survive the
        upgrade, and a verification at the end that there is genuinely nothing
        left to upgrade.
        """
        if getattr(self, '_apt_running', False) or getattr(self, '_update_running', False):
            return jsonify({'success': False, 'message': 'An update is already in progress'}), 409

        def _is_mount_readonly(mount_point):
            try:
                with open('/proc/mounts') as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 4 and parts[1] == mount_point:
                            return 'ro' in parts[3].split(',')
            except Exception:
                pass
            return False

        def _emit(event, data):
            if self.socketio:
                self.socketio.emit(event, data, room='authenticated')

        def _run():
            self._apt_running = True
            readonly_targets = []
            project_dir = PROJECT_ROOT
            try:
                # Both mounts, for the same reason the plain update needs them:
                # a kernel or initramfs-tools upgrade writes to /boot/firmware,
                # and a read-only mount there fails dpkg mid-transaction.
                for target in ['/', '/boot/firmware']:
                    if _is_mount_readonly(target):
                        if subprocess.call(['sudo', 'mount', '-o', 'remount,rw', target]) != 0:
                            _emit('apt_done', {'success': False, 'error': f'Could not remount {target} read-write'})
                            return
                        readonly_targets.append(target)

                def _stream(cmd, phase, label):
                    _emit('apt_output', {'line': label, 'phase': phase, 'header': True})
                    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1,
                                            env=_apt_env())
                    for line in proc.stdout:
                        _emit('apt_output', {'line': _clean_line(line), 'phase': phase})
                    proc.wait()
                    return proc.returncode

                # Snapshot the libraries Pillow links against *before* the first
                # apt command, not before dist-upgrade. Taken later, the ordinary
                # upgrade below had already moved them, so its changes were
                # invisible to the comparison — and the snapshot sat inside the
                # 'else' of the gate, so a run where the simulation found nothing
                # further skipped the check entirely no matter how much the
                # ordinary upgrade had just changed.
                pillow_before = _installed_versions(PILLOW_NATIVE_DEPS)
                pillow_checked = False

                def _check_pillow():
                    """Compare against the snapshot once, however this run ends.

                    Every early return below — a refused full upgrade, a failed
                    dist-upgrade, a simulation that could not be read — happens
                    *after* the ordinary upgrade has been applied, so any of them
                    can leave a moved native library behind. The finally block
                    covers those; the ordinary path calls this in place, so the
                    line reaches the log before apt_done closes the subscription.
                    """
                    nonlocal pillow_checked
                    if pillow_checked:
                        return
                    pillow_checked = True
                    _flag_pillow_rebuild(project_dir, pillow_before,
                                         _line_emitter(_emit, 'apt_output', 'deps'))

                if _stream(['sudo', 'apt-get', 'update'], 'update',
                           self.translations.get('fetching_package_list', 'Fetching package list (apt update)...')) != 0:
                    _emit('apt_done', {'success': False, 'error': 'apt update failed'})
                    return

                # Ordinary upgrade first. It cannot remove anything, so whatever
                # it can do is the safe part of the job — doing it before the
                # resolver runs means a later refusal still leaves the device
                # with its security updates applied rather than with nothing.
                if _stream(['sudo', 'apt-get', 'upgrade', '-y'], 'upgrade',
                           self.translations.get('installing_upgrades', 'Installing upgrades (apt upgrade)...')) != 0:
                    _emit('apt_done', {'success': False, 'error': 'apt upgrade failed'})
                    return

                # ── The gate ────────────────────────────────────────────────
                _emit('apt_output', {'line': self.translations.get('checking_full_upgrade', 'Checking what a full upgrade would change...'), 'phase': 'fullupgrade', 'header': True})
                up, inst, rem, err = _simulate_dist_upgrade()
                if err:
                    _emit('apt_done', {'success': False, 'error': f'Could not simulate full upgrade: {err}'})
                    return
                if not (up or inst or rem):
                    _emit('apt_output', {'line': self.translations.get('nothing_further', 'Nothing further to upgrade.'), 'phase': 'fullupgrade', 'header': True})
                else:
                    blocked = sorted(set(rem) & _protected_packages())
                    if blocked:
                        # Refuse rather than proceed. This is the whole point of
                        # the gate: apt is willing to remove these to satisfy a
                        # dependency, and mempaper does not survive it.
                        _emit('apt_output', {'line': 'Refusing: a full upgrade would remove packages mempaper depends on: ' + ', '.join(blocked), 'phase': 'fullupgrade', 'header': True})
                        _emit('apt_done', {
                            'success': False,
                            'error': 'Full upgrade refused — it would remove: ' + ', '.join(blocked)
                                     + '. The ordinary upgrade was applied. Resolve this over SSH.'
                        })
                        return
                    if rem:
                        _emit('apt_output', {'line': 'Will remove: ' + ', '.join(sorted(rem)), 'phase': 'fullupgrade', 'header': True})

                    if _stream(['sudo', 'apt-get', 'dist-upgrade', '-y'], 'fullupgrade',
                               self.translations.get('running_full_upgrade', 'Running full upgrade (apt full-upgrade)...')) != 0:
                        _emit('apt_done', {'success': False, 'error': 'apt full-upgrade failed'})
                        return

                if _stream(['sudo', 'apt-get', 'autoremove', '-y'], 'autoremove',
                           self.translations.get('removing_orphans', 'Removing packages nothing needs any more (apt autoremove)...')) != 0:
                    # Not fatal — nothing the device needs depends on an orphan
                    # being gone — but silence here meant a failure that leaves
                    # the disk full looked exactly like a clean sweep.
                    _emit('apt_output', {'line': 'Warning: apt autoremove did not complete cleanly', 'phase': 'autoremove', 'header': True})

                # Reconcile the declared set last: autoremove above can take out
                # something apt-requirements.txt names but nothing else depends
                # on, and a full upgrade can move a pinned package off its pin.
                # This puts both back, and re-applies every hold.
                wrapper = '/usr/local/bin/mempaper-apt-install'
                if os.path.exists(wrapper):
                    if _stream(['sudo', wrapper], 'deps',
                               self.translations.get('installing_mempaper_deps', 'Installing mempaper dependencies...')) != 0:
                        _emit('apt_output', {'line': self.translations.get('mempaper_deps_warning', 'Warning: some mempaper dependencies failed to install'), 'phase': 'deps', 'header': True})
                    # What the wrapper could not put back. The plain update route
                    # has always re-queried dpkg rather than trusting an exit
                    # code; this one reported success either way.
                    apt_entries = parse_apt_requirements(
                        os.path.join(project_dir, 'apt-requirements.txt'))
                    still_missing = self._missing_apt_packages(package_names(apt_entries))
                    still_drifted = self._drifted_pins(pinned_versions(apt_entries))
                    if still_missing:
                        _emit('apt_output', {'line': 'Warning: declared but not installed: ' + ', '.join(still_missing), 'phase': 'deps', 'header': True})
                    if still_drifted:
                        _emit('apt_output', {'line': 'Warning: pinned to another version: ' + ', '.join(still_drifted), 'phase': 'deps', 'header': True})

                postinstall = '/usr/local/bin/mempaper-postinstall'
                if os.path.exists(postinstall):
                    _run_postinstall(postinstall, self.translations,
                                     _line_emitter(_emit, 'apt_output', 'deps'))

                # Every apt command has now run, including the reconcile that can
                # itself pull a native library back to a pinned version.
                _check_pillow()

                # ── Verification ────────────────────────────────────────────
                # The question the user actually asked: is anything still
                # outstanding? Answered by asking apt again rather than by
                # assuming the commands above did what they said.
                up2, inst2, rem2, err2 = _simulate_dist_upgrade()
                if err2:
                    _emit('apt_output', {'line': f'Could not verify final state: {err2}', 'phase': 'verify', 'header': True})
                elif up2 or inst2 or rem2:
                    _emit('apt_output', {
                        'line': f'Still outstanding: {len(up2)} to upgrade, {len(inst2)} to install, '
                                f'{len(rem2)} to remove. Held packages account for this when the '
                                f'held version blocks a dependency.',
                        'phase': 'verify', 'header': True})
                    if up2:
                        _emit('apt_output', {'line': 'Held back: ' + ', '.join(sorted(up2)), 'phase': 'verify'})
                else:
                    _emit('apt_output', {'line': self.translations.get('system_fully_upgraded', 'System fully upgraded — nothing further to install, upgrade or remove.'), 'phase': 'verify', 'header': True})

                # The whole point of a full upgrade is that the resolved set
                # moved. Capture where it landed, so a combination proven on
                # this device can be promoted into the declared files.
                _write_version_reports(project_dir,
                                       lambda m: _emit('apt_output', {'line': m, 'phase': 'verify'}))

                _emit('apt_done', {'success': True})
            except Exception as e:
                print(f"Full upgrade error: {e}")
                traceback.print_exc()
                _emit('apt_done', {'success': False, 'error': _safe_error(e)})
            finally:
                # The flag file is what actually schedules the rebuild, so it
                # gets written even on the paths that bailed out early. Only the
                # accompanying log line is lost there, the page having already
                # stopped listening once apt_done went out.
                try:
                    _check_pillow()
                except Exception:
                    pass
                if readonly_targets:
                    _emit('apt_output', {'line': self.translations.get('restoring_readonly', 'Restoring read-only filesystem...'), 'phase': 'cleanup', 'header': True})
                    for target in reversed(readonly_targets):
                        subprocess.call(['sudo', 'mount', '-o', 'remount,ro', target])
                self._apt_running = False

        threading.Thread(target=_run, daemon=True).start()
        return jsonify({'success': True, 'message': 'Full upgrade started'})
