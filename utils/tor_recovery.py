"""Recovery ladder for mempool traffic routed over Tor.

Widening the client-side deadlines (see TOR_CONNECT_TIMEOUT in
technical_config) fixes the case where tor is working and we hang up on it
too early. It does nothing for the other case: tor is genuinely stuck on a
path that will never complete, and retrying the same way forever is exactly
what keeps it stuck.

Three rungs, cheapest first, each triggered by how long it has been since
*anything* reached the mempool host:

  1. Rotate the SOCKS identity. Tor's IsolateSOCKSAuth is on by default, so a
     different SOCKS username gets a different circuit. Costs nothing, needs
     no privileges, no control port, no configuration.
  2. SIGNAL NEWNYM over the control port. Stronger than rotation: it also
     drops the cached hidden-service descriptors, which is what a stale or
     failed descriptor for the onion needs. Only available if the operator
     enabled a control endpoint.
  3. Restart the tor service. The blunt one, and the only rung that clears
     the descriptor cache without a control port. Rate-limited regardless, and
     it cannot fire until nothing has worked for over half an hour, so a device
     whose circuits are healthy never reaches it.

Rungs that are unavailable are skipped with one explanatory line rather than
retried, so a device without a control port does not fill its journal.

Everything here is a no-op when Tor routing is off — a LAN or clearnet
instance has no circuits to fix.
"""

import os
import socket
import subprocess
import threading
import time


# Seconds without a single successful mempool response before each rung fires.
# The first is deliberately past the point where an ordinary blip would have
# resolved itself: blocks arrive every ten minutes or so, and rotating the
# circuit under a merely slow connection would throw away a path that was
# about to work.
ROTATE_AFTER = 8 * 60
NEWNYM_AFTER = 20 * 60
RESTART_AFTER = 35 * 60

# When a pass through all three rungs has not helped, wait this long before
# starting another. Must exceed RESTART_AFTER, or the last rung would never
# come due.
REARM_AFTER = 45 * 60

# A restart costs a full bootstrap, so it must not repeat on the timer during
# a long upstream outage where nothing local can help.
RESTART_MIN_INTERVAL = 60 * 60

# Where Debian's tor package puts its control endpoint once enabled. A unix
# socket is preferred over the TCP port: it is protected by file permissions
# rather than by being on loopback.
_CONTROL_SOCKETS = ("/run/tor/control", "/var/run/tor/control")
_CONTROL_TCP = ("127.0.0.1", 9051)
_CONTROL_COOKIES = ("/run/tor/control.authcookie", "/var/run/tor/control.authcookie")

_ROTATE, _NEWNYM, _RESTART = "rotate", "newnym", "restart"

_lock = threading.RLock()
_generation = 0
_auto_restart = False


def current_identity():
    """SOCKS credentials naming the current circuit generation.

    Deliberately stable while things work. Isolating every request onto its
    own circuit would buy no privacy — it is all one destination either way —
    and would make a Pi Zero pay for a circuit build per call. The username
    changes only when this module decides the current path is bad.
    """
    with _lock:
        return (f"mempaper{_generation}", "x")


def rotate_identity(reason=""):
    """Move every subsequent mempool request onto a fresh circuit."""
    global _generation
    with _lock:
        _generation += 1
        generation = _generation
    print(f"🧅 Asking Tor for a new circuit ({reason}) — SOCKS identity mempaper{generation}")
    return generation


def _read_control_cookie():
    """Cookie bytes for control-port authentication, or None."""
    for path in _CONTROL_COOKIES:
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except (FileNotFoundError, PermissionError):
            continue
        except OSError:
            continue
    return None


def _open_control_connection(timeout):
    """Connect to tor's control endpoint, socket first, then the TCP port."""
    for path in _CONTROL_SOCKETS:
        if not os.path.exists(path):
            continue
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect(path)
            return sock, path
        except (OSError, AttributeError):
            # AF_UNIX is absent on Windows; the dev machine takes the TCP path.
            continue
    try:
        sock = socket.create_connection(_CONTROL_TCP, timeout=timeout)
        sock.settimeout(timeout)
        return sock, f"{_CONTROL_TCP[0]}:{_CONTROL_TCP[1]}"
    except OSError:
        return None, None


def signal_newnym(timeout=10):
    """Send SIGNAL NEWNYM over tor's control port.

    Speaks the control protocol directly rather than pulling in stem for three
    lines of text. Returns (ok, detail); detail explains the failure so the
    caller can say what the operator would have to enable.
    """
    sock, endpoint = _open_control_connection(timeout)
    if sock is None:
        return False, "no control endpoint (ControlSocket/ControlPort not enabled)"

    try:
        cookie = _read_control_cookie()
        # An empty AUTHENTICATE is what tor wants when no authentication is
        # configured at all; the cookie form covers the normal case.
        auth = b"AUTHENTICATE " + cookie.hex().encode() + b"\r\n" if cookie else b"AUTHENTICATE\r\n"

        sock.sendall(auth)
        reply = sock.recv(256)
        if not reply.startswith(b"250"):
            if cookie is None:
                return False, "authentication refused and no readable cookie file"
            return False, f"authentication refused: {reply.decode(errors='replace').strip()}"

        sock.sendall(b"SIGNAL NEWNYM\r\n")
        reply = sock.recv(256)
        if not reply.startswith(b"250"):
            return False, f"NEWNYM refused: {reply.decode(errors='replace').strip()}"

        try:
            sock.sendall(b"QUIT\r\n")
        except OSError:
            pass
        return True, endpoint
    except OSError as e:
        return False, f"control connection failed: {e}"
    finally:
        try:
            sock.close()
        except OSError:
            pass


def restart_tor(timeout=90):
    """Restart the tor service. Needs a sudoers rule; says so when it lacks one."""
    last = ""
    for unit in ("tor@default.service", "tor.service"):
        try:
            result = subprocess.run(
                ["sudo", "-n", "systemctl", "restart", unit],
                capture_output=True, text=True, timeout=timeout)
        except (subprocess.SubprocessError, OSError) as e:
            return False, f"could not run systemctl: {e}"
        if result.returncode == 0:
            return True, unit
        last = (result.stderr or result.stdout or "").strip()
    return False, last or "systemctl restart failed"


class TorRecovery:
    """Tracks how long mempool traffic has been failing and escalates."""

    def __init__(self):
        self._lock = threading.RLock()
        self._last_success = None
        self._first_failure = None
        self._done = set()          # rungs already used in this pass
        self._unavailable = set()   # rungs this device cannot use at all
        self._last_restart = None
        self._pass_started = None   # when the current pass through the ladder began

    def set_auto_restart(self, enabled):
        """Allow or forbid the third rung. Off unless the operator opted in.

        A method rather than a module-level function because every consumer
        reaches this module through the `tor_recovery` singleton, the same way
        they call record_success and record_failure. It was module-level once,
        which made the single caller - configuring it at startup - an
        AttributeError that crash-looped the service before it could serve a
        page. The flag itself stays a module global because _escalate reads it
        from there.
        """
        global _auto_restart
        _auto_restart = bool(enabled)

    def record_success(self):
        """Called whenever any mempool request or the block socket succeeds."""
        with self._lock:
            was_failing = self._first_failure is not None
            self._last_success = time.time()
            self._first_failure = None
            self._pass_started = None
            if was_failing and self._done:
                print("✅ Mempool reachable over Tor again")
            self._done.clear()

    def record_failure(self, source, over_tor):
        """Called when a mempool request or the block socket fails.

        source is for the log only. over_tor is what makes this module inert
        on a LAN or clearnet instance, where none of the rungs apply.
        """
        if not over_tor:
            return

        with self._lock:
            now = time.time()
            if self._first_failure is None:
                self._first_failure = now
                self._pass_started = self._last_success or now
            # Time since anything last worked, falling back to the start of
            # this run of failures on a device that has never yet succeeded.
            since = now - (self._last_success or self._first_failure)

            in_pass = now - self._pass_started
            for rung, threshold in ((_ROTATE, ROTATE_AFTER),
                                    (_NEWNYM, NEWNYM_AFTER),
                                    (_RESTART, RESTART_AFTER)):
                if in_pass >= threshold and rung not in self._done and rung not in self._unavailable:
                    self._escalate(rung, since, source, now)

            # An outage can outlast the whole ladder — an hours-long one did.
            # Once a pass has run its course, start another rather than
            # falling silent for the rest of the outage: the cheap rungs are
            # worth repeating, and a wedge that appears at minute ninety
            # deserves the same treatment as one at minute eight. Checked
            # after the rungs, not before, or the reset would keep clearing
            # the clock just as the last rung came due. Restarts stay rare
            # regardless — RESTART_MIN_INTERVAL outlasts a whole pass.
            if in_pass >= REARM_AFTER:
                self._done.clear()
                self._pass_started = now

    def _escalate(self, rung, since, source, now):
        """Run one rung. Caller holds the lock."""
        self._done.add(rung)
        minutes = since / 60

        if rung == _ROTATE:
            rotate_identity(f"nothing reached the mempool host for {minutes:.0f} min, last failure from {source}")
            return

        if rung == _NEWNYM:
            ok, detail = signal_newnym()
            if ok:
                # NEWNYM also clears the hidden-service descriptor cache, so
                # the next attempt re-fetches the onion's introduction points
                # instead of retrying ones that may be gone.
                rotate_identity("following NEWNYM")
                print(f"🧅 Tor sent NEWNYM after {minutes:.0f} min without a response ({detail})")
            else:
                self._unavailable.add(_NEWNYM)
                print(f"ℹ️ Cannot ask Tor for a new identity: {detail}")
                print("   To enable this rung, add to /etc/tor/torrc:")
                print("     ControlSocket /run/tor/control")
                print("     ControlSocketsGroupWritable 1")
                print("     CookieAuthentication 1")
                print("     CookieAuthFileGroupReadable 1")
                print("   then: sudo adduser mempaper debian-tor && sudo systemctl restart tor@default")
            return

        if rung == _RESTART:
            if not _auto_restart:
                self._unavailable.add(_RESTART)
                print("ℹ️ Tor has been unreachable for a while; set tor_auto_restart to let "
                      "mempaper restart the tor service as a last resort")
                return
            if self._last_restart and now - self._last_restart < RESTART_MIN_INTERVAL:
                return
            ok, detail = restart_tor()
            self._last_restart = now
            if ok:
                rotate_identity("following tor restart")
                print(f"⚙️ Restarted {detail} after {minutes:.0f} min without a response")
            else:
                self._unavailable.add(_RESTART)
                print(f"⚠️ Could not restart tor: {detail}")
                print("   To enable this rung, add to /etc/sudoers.d/mempaper-tor:")
                print("     mempaper ALL=(root) NOPASSWD: /usr/bin/systemctl restart tor@default.service")

    def status(self):
        """Current state, for diagnostics."""
        with self._lock:
            return {
                "last_success": self._last_success,
                "failing_since": self._first_failure,
                "rungs_used": sorted(self._done),
                "rungs_unavailable": sorted(self._unavailable),
            }


# One ladder per process: the WebSocket and every REST client report into it,
# because "has anything reached the mempool host lately" is the only question
# that decides whether the transport needs help.
tor_recovery = TorRecovery()
