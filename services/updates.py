"""Scheduled software updates and the deferred Pillow rebuild.
"""
from utils.paths import PROJECT_ROOT

import os
import subprocess
import threading
import time


# Module-level helpers in mempaper_app; imported inside the method that uses
# them to avoid a circular import at load time.


class UpdateSchedulerMixin:
    """Scheduled software updates and the deferred Pillow rebuild."""

    def _start_pillow_rebuild_if_needed(self):
        """Rebuild Pillow from source in the background if a previous update changed its version."""
        project_dir = PROJECT_ROOT
        flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
        if not os.path.exists(flag_path):
            return

        venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
        if not os.path.exists(venv_pip):
            return

        from utils.wheel_platform import SOURCE_BUILD_TIMEOUT

        def _rebuild():
            try:
                print("📦 Rebuilding Pillow from source for native WebP support (this may take ~15 min on Pi Zero)...")
                subprocess.check_call(
                    [venv_pip, 'install', '--force-reinstall', '--no-cache-dir', '--no-binary', ':all:', 'Pillow'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=SOURCE_BUILD_TIMEOUT
                )
                os.remove(flag_path)
                print("✅ Pillow rebuilt from source. Restarting service to activate...")
                subprocess.run(
                    ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                    timeout=30
                )
            except subprocess.TimeoutExpired:
                print("⚠️ Pillow source build timed out. Will retry on next restart.")
            except Exception as e:
                print(f"⚠️ Pillow source rebuild failed: {e}. ImageMagick fallback remains active.")
                try:
                    os.remove(flag_path)
                except OSError:
                    pass

        threading.Thread(target=_rebuild, daemon=True).start()

    def _queue_build_unit(self, wanted, flag_path):
        """Hand the queue to mempaper-build.service. True if it took it.

        The queue file is the whole instruction: the sudoers grant covers
        starting one fixed unit and nothing else, so what gets built is decided
        by a file the service user already owns rather than by an argument.
        """
        import json

        unit_file = '/etc/systemd/system/mempaper-build.service'
        if not os.path.exists(unit_file):
            return False

        queue_path = os.path.join(PROJECT_ROOT, 'cache', 'build-queue.json')
        try:
            os.makedirs(os.path.dirname(queue_path), exist_ok=True)
            with open(queue_path, 'w') as fh:
                json.dump({'jobs': [{'kind': 'rebuild', 'spec': f'{n}=={v}',
                                     'attempts': a} for n, v, a in wanted],
                           'restart_when_done': True}, fh)
        except OSError as exc:
            print(f"Could not write the build queue: {exc}")
            return False

        try:
            result = subprocess.run(
                ['sudo', '-n', 'systemctl', 'start', 'mempaper-build.service'],
                capture_output=True, text=True, timeout=30)
        except Exception as exc:
            print(f"Could not start the build unit: {exc}")
            return False

        if result.returncode != 0:
            # No grant yet, most likely. Leave the flag alone so the in-process
            # path still runs, and say why rather than failing silently.
            print(f"Build unit refused to start: "
                  f"{(result.stderr or '').strip() or result.returncode}")
            return False

        # The worker owns the queue now; two readers of the same work would
        # rebuild the same package twice against one virtualenv.
        try:
            os.remove(flag_path)
        except OSError:
            pass
        print(f"{len(wanted)} package(s) handed to mempaper-build.service")
        return True

    def _start_wheel_rebuild_if_needed(self, start=False):
        """Report what needs rebuilding, and with start=True begin doing it.

        Boot only reports. A rebuild costs hours on this hardware and is not a
        decision the device gets to make for its owner: the alternative to
        rebuilding is usually pinning a version whose published wheel already
        suits the CPU, which costs nothing and is the better answer whenever it
        exists. So the finding is surfaced and left there until someone asks for
        it - from the config page, or by calling this with start=True.

        Runs in the background: a source build takes tens of minutes per package
        on this hardware and the dashboard has to stay up meanwhile. A package
        that fails keeps its place in the flag with its attempt count raised, so
        a transient failure is retried on the next start while one that cannot
        build here stops after MAX_ATTEMPTS instead of rebuilding every boot.
        """
        from utils.wheel_platform import (REBUILD_FLAG, SOURCE_BUILD_TIMEOUT,
                                          WHEEL_FETCH_TIMEOUT, format_flag,
                                          incompatible_dists, parse_flag,
                                          platform_tag, queue_order, rebuild)

        project_dir = PROJECT_ROOT
        flag_path = os.path.join(project_dir, REBUILD_FLAG)
        if not os.path.exists(flag_path):
            return

        venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
        if not os.path.exists(venv_pip):
            return

        try:
            with open(flag_path) as fh:
                wanted = parse_flag(fh.read())
        except OSError:
            return

        if not start and wanted:
            # Held, not hidden: the config page reads this and offers the build.
            self._wheel_rebuild_state = {
                'running': False, 'pending': [f'{n}=={v}' for n, v, _ in wanted],
                'target': platform_tag(), 'total': len(wanted), 'index': 0,
                'completed': 0, 'current': None, 'rebuilt': [], 'failed': [],
                'log': [], 'events': [],
            }
            print(f"{len(wanted)} package(s) were built for a newer CPU than "
                  f"this one; rebuild them from the config page when convenient")
            try:
                if getattr(self, 'socketio', None):
                    self.socketio.emit('wheel_rebuild_pending',
                                       {'packages': [n for n, _, _ in wanted],
                                        'target': platform_tag()},
                                       room='authenticated')
            except Exception:
                pass
            return

        if not wanted:
            try:
                os.remove(flag_path)
            except OSError:
                pass
            return

        # Hand it to the build unit if this device has one. That unit is a
        # control group of its own, so the restart that ends an update cannot
        # kill a build running inside it - which is what took down every attempt
        # before it existed. A device whose permissions predate the unit falls
        # through to the in-process path below: the same work, with none of the
        # survival.
        if self._queue_build_unit(wanted, flag_path):
            return

        # Mirrored into app state as well as emitted, because a rebuild outlives
        # any one page view: the browser reconnects after the restart that
        # started it, and the reader may reload or come back hours later.
        self._wheel_rebuild_state = {
            'running': True, 'target': None, 'total': 0, 'index': 0,
            'current': None, 'rebuilt': [], 'failed': [], 'log': [],
            'events': [],
        }

        def _log(line):
            state = self._wheel_rebuild_state
            state['log'].append(line)
            # Bounded: a 14-package run is chatty enough, and this is held for
            # hours in a process with 512 MB to work with.
            if len(state['log']) > 200:
                del state['log'][:-200]
            print(line)

        def _emit(event, data):
            """Tell any connected dashboard what the rebuild is doing.

            The update itself finished minutes ago and reported success, so
            without this the device looks idle while it is compiling for hours.
            """
            # Recorded as well as sent. A page that loads mid-rebuild replays
            # these to build the log the live listeners already have, so every
            # line is worded by the browser in the reader's language instead of
            # arriving as English text from here.
            state = self._wheel_rebuild_state
            state['events'].append(dict(data, kind=event))
            if len(state['events']) > 200:
                del state['events'][:-200]
            try:
                if getattr(self, 'socketio', None):
                    self.socketio.emit(event, data, room='authenticated')
            except Exception:
                pass

        def _write_queue(entries):
            """Persist what is left, so an interruption resumes rather than restarts."""
            try:
                if entries:
                    with open(flag_path, 'w') as fh:
                        fh.write(format_flag(entries))
                else:
                    os.remove(flag_path)
            except OSError:
                pass

        def _rebuild_all():
            target = platform_tag()
            ordered = queue_order(wanted)
            total = len(ordered)
            queue = list(ordered)
            rebuilt, failed = [], []

            self._wheel_rebuild_state.update({'target': target, 'total': total})
            _log(f"Rebuilding {total} package(s) for {target}. This can take "
                 f"hours; leave the device powered on. An interruption resumes "
                 f"on the next start, but the package building at the time has "
                 f"to be redone.")
            _emit('wheel_rebuild_started', {'total': total, 'target': target,
                                            'packages': [n for n, _, _ in ordered]})

            for index, (name, version, attempts) in enumerate(ordered, start=1):
                # Rebuilding one package rebuilds its dependencies too, so a
                # package queued earlier may already be correct by the time its
                # turn comes. Skipping it saves tens of minutes per hit.
                if not any(n == name for n, _, _ in incompatible_dists()):
                    _log(f"{name}=={version} already built for {target} - skipping")
                    queue = [e for e in queue if e[0] != name]
                    _write_queue(queue)
                    rebuilt.append(name)
                    _emit('wheel_rebuild_progress', {
                        'name': name, 'index': index, 'total': total,
                        'ok': True, 'skipped': True})
                    continue

                self._wheel_rebuild_state.update({'index': index, 'current': name})
                _log(f"Reinstalling {name}=={version} for {target}...")
                _emit('wheel_rebuild_progress', {
                    'name': name, 'index': index, 'total': total, 'building': True})

                # The attempt is recorded before it is made. A build heavy enough
                # to take the whole process down never reaches the failure path,
                # so counting afterwards leaves the package at its old count and
                # first in the queue - retried from the top on every restart, for
                # ever, with everything behind it never reached.
                queue = [(n, v, a + 1) if n == name else (n, v, a)
                         for n, v, a in queue]
                _write_queue(queue)

                # pip and the compilers under it emit thousands of lines per
                # build. One every few seconds is enough to show the build is
                # moving, and keeps a log bounded at 200 lines useful.
                last_line_at = [0.0]

                def _build_line(line, _name=name, _index=index):
                    now = time.monotonic()
                    if now - last_line_at[0] < 5:
                        return
                    last_line_at[0] = now
                    _log(line)
                    _emit('wheel_rebuild_output', {
                        'name': _name, 'index': _index, 'total': total,
                        'line': line})

                # A published wheel for this platform is tried first. Fetching
                # one takes seconds where building the same package takes an
                # hour, and the index the device already uses carries armv6l
                # builds for most of them. Source is the fallback, not the first
                # move. pip reports success for a wheel that is still built for
                # somewhere else, so the result is checked rather than trusted.
                ok, output = rebuild(venv_pip, name, version, source=False,
                                     timeout=WHEEL_FETCH_TIMEOUT,
                                     on_line=_build_line)
                if ok and any(n == name for n, _, _ in incompatible_dists()):
                    ok = False
                    _log(f"The published wheel for {name} still holds code "
                         f"this CPU cannot run")
                from_wheel = ok
                if not ok:
                    _log(f"Building {name}=={version} from source for {target} "
                         f"(this can take hours)...")
                    ok, output = rebuild(venv_pip, name, version, source=True,
                                         timeout=SOURCE_BUILD_TIMEOUT,
                                         on_line=_build_line)
                if ok:
                    _log(f"{name}=={version} now built for {target} "
                         f"({'published wheel' if from_wheel else 'built here'})")
                    rebuilt.append(name)
                    queue = [e for e in queue if e[0] != name]
                else:
                    _log(f"Could not rebuild {name}=={version}: "
                         f"{output.strip()[-300:] or 'no output captured'}")
                    failed.append(name)
                    # To the back of the queue: a restart should spend its time
                    # on the packages that can build here rather than another
                    # half hour on the one that just failed.
                    entry = next((e for e in queue if e[0] == name), None)
                    if entry:
                        queue = [e for e in queue if e[0] != name] + [entry]

                # After every package, not at the end: a restart mid-run would
                # otherwise discard the hours already spent and start over.
                _write_queue(queue)
                _emit('wheel_rebuild_progress', {
                    'name': name, 'index': index, 'total': total, 'ok': ok})

            _log(f"Wheel rebuild finished for {target}: "
                 f"{len(rebuilt)} rebuilt, {len(failed)} failed")
            self._wheel_rebuild_state.update({
                'running': False, 'current': None,
                'rebuilt': rebuilt, 'failed': failed})
            _emit('wheel_rebuild_done', {
                'rebuilt': rebuilt, 'failed': failed, 'target': target,
                'restarting': bool(rebuilt)})

            # The running process already imported the old binaries, so the
            # rebuilt ones are only in use after a restart. Nothing else in the
            # update flow reaches this point - the update finished hours ago.
            if rebuilt:
                time.sleep(3)
                try:
                    subprocess.run(['sudo', 'systemctl', 'restart', 'mempaper.service'],
                                   timeout=30)
                except Exception as restart_err:
                    _log(f"Service restart failed: {restart_err}")

        threading.Thread(target=_rebuild_all, daemon=True).start()

    def _start_auto_update_scheduler(self):
        """One-shot timer scheduler for automatic updates.

        Uses threading.Timer so the process sleeps exactly until the next scheduled
        run — no polling loop, zero CPU between fires.  When the auto-update config
        changes, _reschedule_auto_update() cancels the current timer and creates a
        new one for the updated schedule, taking effect immediately.
        """
        from mempaper_app import _read_reboot_time, _in_reboot_window
        import datetime

        _DAY_MAP = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        self._auto_update_timer     = None
        self._auto_update_last_run  = None   # date of last completed run

        def _next_run_dt():
            """Return the next datetime at which the update should fire, or None if
            disabled / no days configured.  Searches up to 14 days ahead so gaps
            between allowed days are handled correctly, and skips any candidate that
            falls within 2 hours before the unattended-upgrades auto-reboot time."""
            if not self.config.get('auto_update_enabled', False):
                return None
            raw = self.config.get('auto_update_time', self.config.get('auto_update_hour', '03:00'))
            if isinstance(raw, int):
                h, m = raw, 0
            else:
                parts = str(raw).split(':')
                h, m = int(parts[0]), (int(parts[1]) if len(parts) > 1 else 0)
            allowed = {_DAY_MAP.get(d, -1) for d in self.config.get('auto_update_days', ['mon', 'wed', 'fri'])} - {-1}
            if not allowed:
                return None
            reboot_hm = _read_reboot_time()
            now = datetime.datetime.now()
            for days_ahead in range(14):
                candidate = (now + datetime.timedelta(days=days_ahead)).replace(
                    hour=h, minute=m, second=0, microsecond=0)
                if candidate.weekday() not in allowed or (candidate - now).total_seconds() <= 5:
                    continue
                if _in_reboot_window(h, m, reboot_hm):
                    rh, rm = reboot_hm
                    ws = (rh * 60 + rm - 120) % (24 * 60)
                    we = (rh * 60 + rm + 15)  % (24 * 60)
                    print(f"⚠️ Auto-update: {h:02d}:{m:02d} falls in OS reboot window "
                          f"{ws//60:02d}:{ws%60:02d}–{we//60:02d}:{we%60:02d} — skipping this occurrence")
                    continue
                return candidate
            return None

        def _schedule():
            """Cancel any pending timer and arm a new one for the next run."""
            if self._auto_update_timer is not None:
                self._auto_update_timer.cancel()
                self._auto_update_timer = None
            target = _next_run_dt()
            if target is None:
                print("🕐 Auto-update: disabled or no days configured — timer not set")
                return
            delay = (target - datetime.datetime.now()).total_seconds()
            self._auto_update_timer = threading.Timer(delay, _run_update)
            self._auto_update_timer.daemon = True
            self._auto_update_timer.start()
            # Every config save reschedules, so the same target was printed each
            # time. Only report when it actually moves.
            if getattr(self, '_last_logged_update_target', None) != target:
                self._last_logged_update_target = target
                days = delay / 86400
                print(f"🕐 Auto-update scheduled for {target.strftime('%Y-%m-%d %H:%M')} "
                      f"(in {f'{days:.1f} days' if days >= 1 else f'{delay/3600:.1f}h'})")

        # Expose so _on_config_change can reschedule without importing anything.
        self._reschedule_auto_update = _schedule

        def _run_update():
            self._auto_update_timer = None
            today = datetime.date.today()

            if self._auto_update_last_run == today:
                # Already ran today (e.g. timer fired twice due to a race) — just reschedule
                _schedule()
                return
            if getattr(self, '_update_running', False) or getattr(self, '_apt_running', False):
                _schedule()
                return

            self._auto_update_last_run = today
            now = datetime.datetime.now()
            print(f"🔄 Auto-update triggered at {now.strftime('%Y-%m-%d %H:%M')}")

            try:
                # Notify connected browsers
                if hasattr(self, 'socketio') and self.socketio:
                    self.socketio.emit('auto_update_started')

                project_dir = PROJECT_ROOT
                needs_restart = False

                # System packages update - safe because python3/python3-dev/python3-venv
                # are held via apt-mark hold, so the Python minor cannot change.
                #
                # full-upgrade is deliberately not here. It is the one apt
                # operation allowed to remove packages, and the web route only
                # runs it after simulating and refusing when the removal list
                # touches a declared dependency or the Python the venv is built
                # on. There is nobody at 05:00 to read that refusal.
                from routes.updates import (PILLOW_NATIVE_DEPS, _installed_versions)

                pillow_before = _installed_versions(PILLOW_NATIVE_DEPS)
                try:
                    subprocess.run(
                        ['sudo', 'apt-get', 'update', '-qq'],
                        timeout=300, capture_output=True, check=True
                    )
                    # Half an hour, not five minutes. An upgrade carrying a
                    # kernel regenerates the initramfs, which on a Pi Zero runs
                    # well past the old budget - and a timeout there leaves dpkg
                    # mid-transaction, unattended, with the failure swallowed as
                    # "non-fatal". A partial upgrade is worse than none.
                    result = subprocess.run(
                        ['sudo', 'apt-get', 'upgrade', '-y'],
                        timeout=30 * 60, capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        print("✅ Auto-update: system packages upgraded")
                    else:
                        tail = (result.stderr or result.stdout or '').strip().splitlines()
                        print(f"⚠️ Auto-update: apt upgrade exited {result.returncode} - "
                              f"{' / '.join(tail[-3:]) or 'no output'}")
                        print("   The upgrade may be half-applied. Repair with: "
                              "sudo dpkg --configure -a && sudo apt-get -f install")
                except subprocess.TimeoutExpired:
                    print("⚠️ Auto-update: apt upgrade timed out after 30 minutes and "
                          "was killed. dpkg is likely mid-transaction - repair with: "
                          "sudo dpkg --configure -a && sudo apt-get -f install")
                except Exception as e:
                    print(f"⚠️ Auto-update: system packages update failed (non-fatal): {e}")

                # What the web route does after any apt work, and this path did
                # not: an upgrade that moves a library Pillow was compiled
                # against leaves it linked to something no longer installed, and
                # an upgrade can drift a pinned package off the version
                # apt-requirements.txt declares. Neither announces itself.
                try:
                    from routes.updates import _flag_pillow_rebuild
                    moved = _flag_pillow_rebuild(
                        project_dir, pillow_before,
                        lambda msg, header=False: print(f"   {msg}"))
                    if moved:
                        needs_restart = True
                except Exception as e:
                    print(f"⚠️ Auto-update: Pillow dependency check skipped: {e}")

                try:
                    wrapper = '/usr/local/bin/mempaper-apt-install'
                    if os.path.exists(wrapper):
                        reconcile = subprocess.run(
                            ['sudo', wrapper], timeout=30 * 60,
                            capture_output=True, text=True
                        )
                        if reconcile.returncode != 0:
                            print("⚠️ Auto-update: declared packages could not be "
                                  "reconciled after the upgrade")
                        for line in (reconcile.stdout or '').splitlines():
                            if line.startswith(('📌', '🔓', '⚠️', '❌')):
                                print(f"   {line}")
                except Exception as e:
                    print(f"⚠️ Auto-update: package reconcile skipped: {e}")

                # mempaper software update — only if a newer release exists
                try:
                    subprocess.run(
                        ['git', 'fetch', '--tags', '--force'],
                        cwd=project_dir, capture_output=True, timeout=60, check=True
                    )

                    tags_output = subprocess.check_output(
                        ['git', 'tag', '-l', '--sort=-version:refname'],
                        cwd=project_dir, text=True
                    ).strip()

                    if not tags_output:
                        print("⚠️ Auto-update: no tags found, skipping software update")
                    else:
                        latest_tag = tags_output.splitlines()[0].strip()

                        try:
                            current_tag = subprocess.check_output(
                                ['git', 'describe', '--tags', '--exact-match', 'HEAD'],
                                cwd=project_dir, stderr=subprocess.DEVNULL, text=True
                            ).strip()
                        except subprocess.CalledProcessError:
                            current_tag = None

                        if current_tag == latest_tag:
                            print(f"✅ Auto-update: already on latest release ({latest_tag}), skipping")
                        else:
                            print(f"🔄 Auto-update: upgrading from {current_tag} to {latest_tag}...")

                            deps_changed = False
                            apt_deps_changed = False
                            pillow_changed = False
                            try:
                                diff_result = subprocess.run(
                                    ['git', 'diff', '--name-only', 'HEAD', f'refs/tags/{latest_tag}', '--',
                                     'requirements.txt', 'apt-requirements.txt'],
                                    cwd=project_dir, capture_output=True, text=True
                                )
                                changed_files = diff_result.stdout.strip()
                                deps_changed = 'requirements.txt' in changed_files
                                apt_deps_changed = 'apt-requirements.txt' in changed_files
                                if deps_changed:
                                    import re
                                    diff_content = subprocess.run(
                                        ['git', 'diff', 'HEAD', f'refs/tags/{latest_tag}', '--', 'requirements.txt'],
                                        cwd=project_dir, capture_output=True, text=True
                                    )
                                    pillow_changed = bool(re.search(r'^\+.*pillow==', diff_content.stdout, re.IGNORECASE | re.MULTILINE))
                            except Exception:
                                deps_changed = True
                                apt_deps_changed = True

                            subprocess.run(['git', 'reset', '--hard'], cwd=project_dir, capture_output=True, check=True)
                            subprocess.run(['git', 'checkout', f'refs/tags/{latest_tag}'], cwd=project_dir, capture_output=True, check=True)
                            needs_restart = True  # code changed → always restart

                            if apt_deps_changed:
                                apt_req_file = os.path.join(project_dir, 'apt-requirements.txt')
                                if os.path.exists(apt_req_file):
                                    subprocess.run(['sudo', '/usr/local/bin/mempaper-apt-install'],
                                                    capture_output=True, timeout=300)

                            venv_pip = os.path.join(project_dir, '.venv', 'bin', 'pip')
                            requirements_file = os.path.join(project_dir, 'requirements.txt')
                            if deps_changed and os.path.exists(venv_pip) and os.path.exists(requirements_file):
                                result = subprocess.run(
                                    [venv_pip, 'install', '-r', requirements_file],
                                    cwd=project_dir, capture_output=True, timeout=600
                                )
                                if result.returncode != 0:
                                    print("⚠️ Auto-update: pip install failed, rolling back...")
                                    subprocess.run(
                                        ['git', 'checkout', current_tag or 'HEAD~1'],
                                        cwd=project_dir, capture_output=True, check=True
                                    )
                                    needs_restart = False  # rolled back to old code

                            if pillow_changed:
                                flag_path = os.path.join(project_dir, '.pillow-rebuild-needed')
                                with open(flag_path, 'w') as f:
                                    f.write('1')

                            if needs_restart:
                                print(f"✅ Auto-update: upgraded to {latest_tag}. Restarting service...")
                                print("⏳ Auto-update: waiting for e-ink display to finish...")
                                acquired = self._display_worker_lock.acquire(timeout=150)
                                if acquired:
                                    self._display_worker_lock.release()
                                    print("✅ Auto-update: display idle — safe to restart")
                                else:
                                    print("⚠️ Auto-update: display lock timeout after 150s — restarting anyway")

                                if hasattr(self, 'socketio') and self.socketio:
                                    self.socketio.emit('service_restarting', {
                                        'reason': 'auto_update',
                                        'tag': latest_tag,
                                        'estimated_seconds': 25
                                    })
                                    time.sleep(1)
                                subprocess.run(
                                    ['sudo', 'systemctl', 'restart', 'mempaper.service'],
                                    timeout=30
                                )
                except Exception as e:
                    print(f"⚠️ Auto-update: software update failed: {e}")

            except Exception as e:
                print(f"⚠️ Auto-update error: {e}")

            # Always reschedule for the next occurrence.
            # If systemctl restart above succeeded, this process is already dead and
            # _schedule() is never reached — the new process reschedules on startup.
            _schedule()

        # Arm the initial timer on startup.
        _schedule()
