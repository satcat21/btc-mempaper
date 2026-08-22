"""The persistent e-ink worker subprocess: starting it, streaming its stdout
and stderr, dispatching refreshes and surfacing its errors.
"""
from utils.paths import PROJECT_ROOT

import subprocess
import json
import os
import queue
import threading
import time


class DisplayWorkerMixin:
    """The persistent e-ink worker subprocess: starting it, streaming its stdout"""

    def _display_on_epaper_async(self, image_path, block_height=None, block_hash=None):
        """Display image on e-Paper via persistent worker process."""

        # Skip immediately if this block is already superseded
        if block_height:
            current_block = getattr(self, 'current_block_height', 0) or 0
            if int(block_height) < int(current_block):
                print(f"⏭️ Skipping e-paper display for old block {block_height} (current: {current_block})")
                return

        def display_in_worker():
            # Non-blocking: if a display is already running, don't queue a second
            # worker call right behind it. Two full hardware refreshes back-to-back
            # (e.g. a settings change firing moments after a block-triggered refresh)
            # can leave the panel's BUSY line stuck, hanging the driver indefinitely —
            # that's what caused a 120s timeout that required a service restart to
            # clear on 2026-07-16. Just remember to refresh once more when free.
            if not self._display_worker_lock.acquire(blocking=False):
                self._pending_eink_refresh = True
                print(f"📌 Display busy — queued refresh for block {block_height}")
                return

            try:
                display_start = time.time()
                print(f"⚙️ Starting e-paper display for block {block_height} at {time.strftime('%H:%M:%S')}")

                try:
                    worker = self._get_or_start_display_worker()
                except Exception as e:
                    print(f"❌ Could not start display worker: {e}")
                    self._emit_display_error(str(e))
                    return

                try:
                    _cmd = {"image_path": image_path}
                    # Set by the recovery ladder after an abnormal refresh, and
                    # consumed once: the blanking pass is expensive and is a
                    # recovery step, not a mode.
                    if getattr(self, '_force_display_clear', False):
                        _cmd["full_clear"] = True
                        self._force_display_clear = False
                    worker.stdin.write(json.dumps(_cmd) + "\n")
                    worker.stdin.flush()
                except Exception as e:
                    print(f"❌ Failed to send command to display worker: {e}")
                    self._kill_display_worker(worker)  # force restart next time
                    self._emit_display_error(str(e))
                    return

                try:
                    result = self._display_worker_results.get(timeout=120)
                except queue.Empty:
                    device_name = self.config.get("omni_device_name", "unknown")
                    print(f"❌ E-paper display timed out after 120s")
                    print(f"   The selected display driver '{device_name}' may be incorrect.")
                    print(f"   Run: python tools/configure_display.py")
                    # Kill the stuck worker rather than abandoning it — an orphaned
                    # process still holds the GPIO lines (e.g. RST), so the next
                    # worker's driver import fails with "GPIO busy"/"pin already in
                    # use" and silently falls back to no-hardware mode from then on.
                    self._kill_display_worker(worker)
                    self._emit_display_error(
                        f'Display timed out after 120s. The driver "{device_name}" may be incorrect. '
                        f'Check Settings → Display.'
                    )
                    return

                display_duration = time.time() - display_start

                if result.get("worker_died"):
                    print(f"❌ Display worker died unexpectedly")
                    self._kill_display_worker(worker)
                    self._emit_display_error("Worker process died")
                    return

                if result.get("success") and display_duration > self.DISPLAY_SLOW_REFRESH_SECS:
                    # The driver returned success, but took far longer than this
                    # panel ever needs. SPI carries no acknowledgement and e-ink
                    # cannot be read back, so a refresh the panel ignored still
                    # reports success in a normal-looking time - which means the
                    # abnormal one is the only moment the fault is visible at
                    # all. Spend it.
                    self._recover_display(worker, display_duration)
                elif result.get("success"):
                    print(f"✅ E-paper display completed in {display_duration:.2f}s")
                    self._last_display_error = None  # clear any previous error
                    self._consecutive_display_failures = 0
                    # The panel is behaving, so the recovery history stops
                    # counting against the next genuine fault.
                    self._clear_reboot_state()
                    # The display works again, so drop the retry marker; otherwise
                    # a later user disable would look like an auto-disable and be
                    # undone by the next reboot.
                    if self.config.get('eink_auto_disabled'):
                        try:
                            self.config_manager.set('eink_auto_disabled', False)
                            self.config_manager.save_config()
                            self.config['eink_auto_disabled'] = False
                        except Exception as _e:
                            print(f"⚠️ Could not clear the display retry marker: {_e}")

                    # Update block tracking if this result is still current
                    if block_height and block_hash:
                        current_height = getattr(self, 'last_eink_block_height', 0) or 0
                        latest_block = getattr(self, 'current_block_height', 0) or 0
                        if int(block_height) >= int(current_height):
                            self.last_eink_block_height = block_height
                            self.last_eink_block_hash = block_hash
                            # Only log if this is actually the latest block (avoid confusion)
                            if int(block_height) >= int(latest_block):
                                print(f"💾 E-ink display tracking updated: Block {block_height}")

                    if hasattr(self, 'socketio'):
                        self.socketio.emit('display_update', {
                            'status': 'success',
                            'message': f'Display updated in {display_duration:.1f}s',
                            'block_height': block_height,
                            'timestamp': time.time()
                        })
                else:
                    error = result.get("error", "unknown error")
                    print(f"⚠️ E-paper display failed after {display_duration:.2f}s: {error}")
                    if result.get("traceback"):
                        for line in result["traceback"].splitlines():
                            print(f"   {line}")
                    self._emit_display_error(error)
            finally:
                self._display_worker_lock.release()
                # Run any refresh that came in while we were busy, now that we're free.
                if getattr(self, '_pending_eink_refresh', False):
                    self._pending_eink_refresh = False
                    print(f"📌 Executing pending e-ink refresh...")
                    threading.Thread(
                        target=self._display_on_epaper_async,
                        args=(self._eink_worker_path(), self.current_block_height, self.current_block_hash),
                        daemon=True
                    ).start()

        threading.Thread(target=display_in_worker, daemon=True).start()

    def _kill_display_worker(self, proc):
        """Terminate a stuck/failed display worker and clear the reference.

        Must be used instead of just setting self._display_worker = None: the
        worker's atexit/SIGTERM handler releases its GPIO claims (RST, DC, CS,
        PWR) on the way out. Abandoning the Popen object without killing the
        process leaves it running as an orphan that still holds those pins, so
        the next worker's driver import fails with "GPIO busy" and the display
        silently falls back to no-hardware mode for the rest of the process's life.
        """
        self._display_worker = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        except Exception:
            pass

    def _get_or_start_display_worker(self):
        """Return the running display worker, starting it if necessary."""
        import subprocess
        import sys

        if self._display_worker and self._display_worker.poll() is None:
            return self._display_worker

        # Start fresh worker
        script_path = os.path.join(PROJECT_ROOT, "lib", "display_worker.py")
        # Drain any stale results from a previous worker
        while not self._display_worker_results.empty():
            try:
                self._display_worker_results.get_nowait()
            except queue.Empty:
                break

        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT
        )
        self._display_worker = proc

        # Start background thread that reads worker stdout into the results queue
        threading.Thread(
            target=self._read_display_worker_stdout,
            args=(proc,),
            daemon=True
        ).start()
        
        # Start background thread to forward worker stderr to our logs
        threading.Thread(
            target=self._read_display_worker_stderr,
            args=(proc,),
            daemon=True
        ).start()

        # Wait for the worker to finish loading drivers (ready signal)
        try:
            ready = self._display_worker_results.get(timeout=60)
            if ready.get("status") != "ready":
                raise RuntimeError(f"Unexpected worker signal: {ready}")
        except queue.Empty:
            proc.kill()
            raise RuntimeError("Display worker failed to become ready within 60s")

        print(f"⚙️ Display worker started (PID {proc.pid})")
        return proc

    def _read_display_worker_stdout(self, proc):
        """Background thread: pipe worker stdout lines into the results queue."""
        # Patterns to suppress (verbose hardware status messages)
        suppress_patterns = [
            "Write PON", "Write DRF", "Write POF",
            "e-Paper busy", "e-Paper busy H", "e-Paper busy H release",
            "EPD init...", "bcm2835 init success", "Display Done!!"
        ]
        
        try:
            for line in proc.stdout:
                line = line.strip()
                if line:
                    try:
                        self._display_worker_results.put(json.loads(line))
                    except json.JSONDecodeError:
                        # Filter out verbose hardware status messages
                        if not any(pattern in line for pattern in suppress_patterns):
                            # Log non-JSON output from worker (debugging info)
                            print(f"   [worker] {line}")
        finally:
            # Check if there's stderr output to provide better error context
            stderr_output = ""
            try:
                # Try to read any remaining stderr (non-blocking)
                if proc.stderr:
                    remaining = proc.stderr.read()
                    if remaining:
                        stderr_output = remaining.strip()
            except Exception:
                pass
            
            # Notify any waiting caller that the worker died
            error_msg = "Worker process died"
            if stderr_output:
                error_msg = f"Worker process died: {stderr_output[:200]}"  # Limit length
            self._display_worker_results.put({
                "worker_died": True, 
                "success": False,
                "error": error_msg
            })

    def _read_display_worker_stderr(self, proc):
        """Background thread: forward worker stderr to our logs with prefix."""
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    # Forward stderr from worker to our logs
                    print(f"   [worker stderr] {line}")
        except Exception:
            pass

    # Consecutive display failures (timeout, worker died, etc.) before auto-disabling.
    # A single failure is often a one-off hiccup (transient hardware busy-line stall,
    # a killed subprocess) rather than a real misconfiguration — give it a few natural
    # retries (one per new block) before giving up and requiring manual reconfiguration.
    DISPLAY_FAILURE_DISABLE_THRESHOLD = 3

    # A refresh beyond this has not behaved: a 13.3" panel takes around 35s and
    # a 7.3" less, so this is twice the slowest healthy run. Reaching it costs a
    # fresh worker process and a blanking pass on the next push.
    DISPLAY_SLOW_REFRESH_SECS = 80

    # And beyond this, nothing legitimate is happening. The run that wedged a
    # panel in the field took 857s. Separate from the threshold above because
    # this one is allowed to reboot the device, and a merely slow refresh must
    # never do that.
    DISPLAY_WEDGE_REFRESH_SECS = 300

    # A reboot that does not fix it must not become a loop.
    DISPLAY_REBOOT_MIN_INTERVAL = 6 * 3600

    # And after this many recovery reboots without a healthy refresh in between,
    # rebooting is not the answer and repeating it only takes the dashboard down
    # too. The count clears the moment a refresh comes back inside its normal
    # duration, so a device that recovers starts again from zero.
    DISPLAY_REBOOT_MAX_ATTEMPTS = 2

    # Held on disk, not in memory: this is the one piece of state that has to
    # outlive the very reboot it governs. Keeping it in an attribute meant every
    # boot started with a clean slate, so a panel a reboot could not fix would
    # be rebooted again on the next boot, and the next - forever, and without
    # even tripping the power-cycle panic threshold, because these reboots
    # deliberately write the graceful marker that excludes them from it.
    DISPLAY_REBOOT_STATE_PATH = os.path.join('cache', '.eink-recovery-reboot')

    def _read_reboot_state(self):
        """(timestamp, count) of recovery reboots so far, or (None, 0)."""
        import json as _json
        try:
            with open(self.DISPLAY_REBOOT_STATE_PATH, encoding='utf-8') as fh:
                d = _json.load(fh)
            return d.get('at'), int(d.get('count', 0))
        except (OSError, ValueError, _json.JSONDecodeError):
            return None, 0

    def _clear_reboot_state(self):
        """Forget the recovery history — called when a refresh behaves again."""
        try:
            os.remove(self.DISPLAY_REBOOT_STATE_PATH)
        except OSError:
            pass

    def _recover_display(self, worker, display_duration):
        """Escalate after a refresh that ran far outside its normal duration.

        Three rungs, cheapest first, mirroring utils/tor_recovery:

          1. Kill the worker, so the next push runs in a fresh process against a
             freshly initialised driver.
          2. Ask that push for a blanking pass, in case the controller needs
             re-initialising rather than just redrawing.
          3. Reboot. Blunt, opt-in and rate-limited - and the only step observed
             to bring a wedged panel back, because neither a new process nor a
             standalone Init/Clear reaches the kernel-level GPIO and SPI state
             that a restart leaves untouched.
        """
        device_name = self.config.get("omni_device_name", "unknown")
        print(f"⚠️ E-paper refresh took {display_duration:.0f}s — far beyond what "
              f"'{device_name}' needs. Treating it as a failure.")

        self._kill_display_worker(worker)
        self._force_display_clear = True
        print("🔧 Display worker killed; the next refresh gets a full clear pass")

        if hasattr(self, 'socketio') and self.socketio:
            self.socketio.emit('display_update', {
                'status': 'warning',
                'message': f'The e-ink refresh took {display_duration:.0f}s and may not have '
                           f'reached the panel. Recovering.',
                'timestamp': time.time()
            })

        if display_duration < self.DISPLAY_WEDGE_REFRESH_SECS:
            return

        if not self.config.get('eink_auto_reboot', True):
            print("ℹ️ The panel looks wedged. Set eink_auto_reboot to let mempaper "
                  "reboot the device, which is the only step known to clear this.")
            return

        last, attempts = self._read_reboot_state()
        if attempts >= self.DISPLAY_REBOOT_MAX_ATTEMPTS:
            print(f"⚠️ The panel is still not responding after "
                  f"{attempts} recovery reboot(s). Rebooting again will not fix "
                  f"it — the display needs looking at. Leaving the device up.")
            return
        if last and time.time() - last < self.DISPLAY_REBOOT_MIN_INTERVAL:
            print("ℹ️ The panel looks wedged again, but a recovery reboot was "
                  "already tried recently — leaving it alone.")
            return

        import json as _json
        try:
            os.makedirs(os.path.dirname(self.DISPLAY_REBOOT_STATE_PATH) or '.',
                        exist_ok=True)
            with open(self.DISPLAY_REBOOT_STATE_PATH, 'w', encoding='utf-8') as fh:
                _json.dump({'at': time.time(), 'count': attempts + 1}, fh)
        except OSError as e:
            # Unable to record the attempt means unable to bound the next one.
            print(f"⚠️ Could not record the recovery reboot ({e}) — not rebooting, "
                  f"because without that record this would repeat every boot.")
            return
        print("⚙️ Rebooting to recover the display — a restart does not clear this.")
        try:
            # The same marker the web UI writes, so the next boot counts this as
            # an intentional reboot rather than toward the panic-reset threshold.
            marker = getattr(self, 'GRACEFUL_REBOOT_MARKER_PATH', None)
            if marker:
                os.makedirs(os.path.dirname(marker) or '.', exist_ok=True)
                with open(marker, 'w', encoding='utf-8') as fh:
                    fh.write('')
        except OSError as e:
            print(f"⚠️ Could not write the graceful-reboot marker: {e}")
        try:
            subprocess.run(['sudo', '-n', 'systemctl', 'reboot'],
                           timeout=30, capture_output=True)
        except Exception as e:
            print(f"⚠️ Could not reboot: {e}")

    def _retry_auto_disabled_display(self):
        """Give an auto-disabled display one more chance on this start.

        The auto-disable is persisted, so without this a transient fault — a
        wrong driver path, an SPI glitch, a cable reseated since — leaves the
        panel dark permanently, and the only cure is the dashboard. A device
        handed to someone who never logs in would stay broken forever.

        Only an auto-disable is retried. A display the operator switched off
        carries no marker and stays off, so a reboot never overrides them.
        Retrying costs at most three failed refreshes per start before the
        threshold trips again, so a genuinely dead panel does not spin.
        """
        if self.config.get('e-ink-display-connected', True):
            return
        if not self.config.get('eink_auto_disabled', False):
            return
        try:
            self.config_manager.set('e-ink-display-connected', True)
            self.config_manager.set('eink_auto_disabled', False)
            self.config_manager.save_config()
            self.config['e-ink-display-connected'] = True
            self.config['eink_auto_disabled'] = False
            self._consecutive_display_failures = 0
            print("🔁 e-Paper display was auto-disabled after earlier failures — "
                  "re-enabling to retry on this start.")
        except Exception as _e:
            print(f"⚠️ Could not re-enable the auto-disabled display: {_e}")

    def _emit_display_error(self, message):
        self._last_display_error = {'message': message, 'timestamp': time.time()}
        self._consecutive_display_failures = getattr(self, '_consecutive_display_failures', 0) + 1

        if self._consecutive_display_failures < self.DISPLAY_FAILURE_DISABLE_THRESHOLD:
            print(f"⚠️ Display error ({self._consecutive_display_failures}/{self.DISPLAY_FAILURE_DISABLE_THRESHOLD} "
                  f"before auto-disable): {message}")
        else:
            # Auto-disable the display to stop repeated failures (wrong driver, SPI error, etc.)
            try:
                if self.config_manager.get('e-ink-display-connected'):
                    self.config_manager.set('e-ink-display-connected', False)
                    # Record that *we* switched it off, not the operator. Startup
                    # retries an auto-disable so a device with no dashboard access
                    # can recover on a reboot; a deliberate user disable has no
                    # marker and is therefore left alone.
                    self.config_manager.set('eink_auto_disabled', True)
                    self.config_manager.save_config()
                    # save_config() suppresses this process's own file-watcher for a couple
                    # of seconds (to avoid the self-reload it would otherwise trigger), so the
                    # usual external-change callback that refreshes self.e_ink_enabled never
                    # fires here. Without this, self.e_ink_enabled stays True in memory even
                    # though the config now says the display is disabled, and every future
                    # block keeps retrying (and re-failing) a display that's supposedly off.
                    self.e_ink_enabled = False
                    self.config['e-ink-display-connected'] = False
                    print(f"⚠️ Display auto-disabled after {self._consecutive_display_failures} consecutive "
                          f"failures — will retry once on the next restart or reboot.")
            except Exception as _e:
                print(f"⚠️ Could not auto-disable display: {_e}")
        if hasattr(self, 'socketio'):
            self.socketio.emit('display_update', {
                'status': 'error',
                'message': message,
                'display_disabled': not self.e_ink_enabled,
                'timestamp': time.time()
            })
