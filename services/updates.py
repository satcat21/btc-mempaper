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

        def _rebuild():
            try:
                print("📦 Rebuilding Pillow from source for native WebP support (this may take ~15 min on Pi Zero)...")
                subprocess.check_call(
                    [venv_pip, 'install', '--force-reinstall', '--no-cache-dir', '--no-binary', ':all:', 'Pillow'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    timeout=3600
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

                # System packages update — safe because python3/python3-dev/python3-venv
                # are held via apt-mark hold, so the Python minor cannot change.
                try:
                    subprocess.run(
                        ['sudo', 'apt-get', 'update', '-qq'],
                        timeout=120, capture_output=True, check=True
                    )
                    subprocess.run(
                        ['sudo', 'apt-get', 'upgrade', '-y'],
                        timeout=300, capture_output=True, check=True
                    )
                    print("✅ Auto-update: system packages upgraded")
                except Exception as e:
                    print(f"⚠️ Auto-update: system packages update failed (non-fatal): {e}")

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
                                    print(f"⚠️ Auto-update: pip install failed, rolling back...")
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
