"""
Authentication and Rate Limiting Module

Handles admin authentication and rate limiting for the mempaper application.
Provides protection against unauthorized access and request flooding,
using secure Argon2 password hashing.
"""

import ipaddress
import json
import os
import secrets
import time
import logging
import threading
from functools import wraps
from collections import defaultdict, deque
from typing import Tuple
from flask import request, jsonify, session, make_response, has_request_context
from flask.sessions import SecureCookieSessionInterface
from managers.secure_password_manager import SecurePasswordManager
from utils.atomic_io import atomic_write_json
from utils.security_config import SecurityConfig


# Sessions are Flask signed cookies: the contents travel with the client and
# the server keeps nothing, so clearing one only ever asked the browser to
# forget it. A cookie that survived that request - captured off the LAN, where
# this runs over plain HTTP, or restored from a backup - stayed valid until it
# aged out, and no logout could touch it.
#
# Each login now mints a random id that is recorded here as well as in the
# cookie, and a cookie whose id is not in this file is refused however well it
# is signed. Logout removes the id, which is what makes it a revocation rather
# than a request.
#
# On disk rather than in memory because gunicorn recycles this worker every
# thousand requests or so to keep memory flat on a Pi Zero. An in-memory set
# would take every live session with it each time, logging the operator out at
# intervals that would look random.
SESSION_STORE_PATH = os.path.join('cache', '.sessions.json')

# Ids are dropped after this long regardless, so a device that is never logged
# out does not accumulate them forever. Well clear of the sliding session
# window: expiry is still decided by the cookie's own login_time, and this only
# stops the file growing without bound.
SESSION_ID_MAX_AGE = 30 * 24 * 3600

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter to prevent request flooding."""
    
    def __init__(self):
        """Initialize rate limiter with IP tracking."""
        self.requests = defaultdict(deque)
        
    def is_allowed(self, ip: str, max_requests: int, window: int) -> bool:
        """
        Check if request from IP is allowed based on rate limits.
        
        Args:
            ip (str): Client IP address
            max_requests (int): Maximum requests allowed
            window (int): Time window in seconds
            
        Returns:
            bool: True if request is allowed, False if rate limited
        """
        now = time.time()
        
        # Clean old requests outside the window
        while self.requests[ip] and self.requests[ip][0] < now - window:
            self.requests[ip].popleft()
        
        # Check if under limit
        if len(self.requests[ip]) < max_requests:
            self.requests[ip].append(now)
            return True
        
        return False
    
    def get_reset_time(self, ip: str, window: int) -> int:
        """
        Get time until rate limit resets for IP.
        
        Args:
            ip (str): Client IP address
            window (int): Time window in seconds
            
        Returns:
            int: Seconds until rate limit resets
        """
        if not self.requests[ip]:
            return 0
        
        oldest_request = self.requests[ip][0]
        return max(0, int(window - (time.time() - oldest_request)))


def _kernel_boot_id():
    """The kernel's boot id, or None off Linux.

    A UUID that changes on every reboot and stays put across service restarts,
    which is exactly the line the login lockout has to draw.
    """
    try:
        with open('/proc/sys/kernel/random/boot_id', 'r') as f:
            return f.read().strip() or None
    except (OSError, ValueError):
        return None


class LoginAttemptStore:
    """Failed logins since boot, on disk.

    In-memory counters do not survive the worker recycling gunicorn does every
    thousand requests, which handed an attacker a clean slate for the price of
    some traffic. The file records the boot id it was written under: a service
    restart reads it back, a reboot discards it, and the lockout is therefore
    exactly as durable as it claims to be.
    """

    def __init__(self, path=None):
        self.path = path or SecurityConfig.LOGIN_STATE_PATH
        self.boot_id = _kernel_boot_id()
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {'failures': 0}
        if not isinstance(data, dict):
            return {'failures': 0}
        # A different boot is a different attempt history. Off Linux there is
        # no boot id to compare, so the count simply persists.
        if self.boot_id and data.get('boot_id') != self.boot_id:
            return {'failures': 0}
        return data

    def _write(self, data: dict) -> None:
        data['boot_id'] = self.boot_id
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except OSError as e:
            logger.warning(f"Could not record login attempt state: {e}")

    def failures(self) -> int:
        with self._lock:
            return int(self._read().get('failures', 0) or 0)

    def record_failure(self) -> int:
        with self._lock:
            data = self._read()
            data['failures'] = int(data.get('failures', 0) or 0) + 1
            # Stamped when the threshold is first crossed, so the wait runs
            # from the attempt that closed the door rather than from each one
            # after it - otherwise anyone still knocking would keep it shut.
            if (data['failures'] >= SecurityConfig.LOGIN_LOCKOUT_ATTEMPTS
                    and not data.get('locked_at')):
                data['locked_at'] = time.time()
            self._write(data)
            return data['failures']

    def reset(self) -> None:
        """Called on a successful login: the run of failures is over."""
        with self._lock:
            try:
                os.remove(self.path)
            except OSError:
                pass

    def is_locked(self) -> bool:
        """Locked, unless the wait has run out - then the slate is wiped."""
        limit = SecurityConfig.LOGIN_LOCKOUT_ATTEMPTS
        if not limit:
            return False
        with self._lock:
            data = self._read()
            if int(data.get('failures', 0) or 0) < limit:
                return False
            locked_at = float(data.get('locked_at') or 0)
            if locked_at and time.time() - locked_at >= SecurityConfig.LOGIN_LOCKOUT_SECONDS:
                try:
                    os.remove(self.path)
                except OSError:
                    pass
                logger.info("Login lockout expired - attempts allowed again")
                return False
            return True

    def seconds_remaining(self) -> int:
        """How long the lockout still has to run, for the message shown."""
        with self._lock:
            locked_at = float(self._read().get('locked_at') or 0)
        if not locked_at:
            return SecurityConfig.LOGIN_LOCKOUT_SECONDS
        left = SecurityConfig.LOGIN_LOCKOUT_SECONDS - (time.time() - locked_at)
        return max(0, int(left))


class AuthManager:
    """Manages admin authentication and sessions with secure Argon2 password hashing."""
    
    def __init__(self, config_manager):
        """
        Initialize authentication manager with secure password manager.
        
        Args:
            config_manager: ConfigManager instance for accessing configuration
        """
        self.config_manager = config_manager
        self.config = config_manager.config  # Keep backward compatibility
        self.login_attempts = LoginAttemptStore()
        self.rate_limiter = RateLimiter()
        
        # Initialize secure password manager
        self.password_manager = SecurePasswordManager(config_manager)
        
        # Handle password migration and setup on initialization
        self._initialize_password_security()
        
    def _initialize_password_security(self):
        """
        Initialize password security system.
        Handles migration from cleartext and first-time setup.
        """
        try:
            # First, try to migrate any existing cleartext password
            migration_success = self.password_manager.migrate_cleartext_password()

            if not migration_success:
                logger.error("Password migration failed")
                return False

            # Migrate legacy single-user format to admin_users dict
            self.password_manager._migrate_to_multi_user()

            # If no user is set up, trigger first-time setup
            if not self.password_manager.is_password_set():
                logger.info("No admin password configured - starting first-time setup")
                setup_success = self.password_manager.setup_first_time_password()
                
                if not setup_success:
                    logger.error("First-time password setup failed")
                    return False
                    
            logger.info("Password security system initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize password security: {e}")
            return False
        
    def hash_password(self, password: str) -> str:
        """
        Hash password using secure Argon2 algorithm.
        
        Args:
            password (str): Plain text password
            
        Returns:
            str: Argon2 hashed password
        """
        return self.password_manager.hash_password(password)
    
    def verify_credentials(self, username: str, password: str) -> bool:
        """
        Verify admin credentials using secure password verification.
        
        Args:
            username (str): Username to verify
            password (str): Password to verify
            
        Returns:
            bool: True if credentials are valid
        """
        try:
            # Use the secure password manager for authentication
            return self.password_manager.authenticate_user(username, password)
        except Exception as e:
            logger.error(f"Credential verification failed: {e}")
            return False
    
    def is_authenticated(self) -> bool:
        """
        Check if current session is authenticated and not expired.
        
        Returns:
            bool: True if session is authenticated and valid
        """
        # Check if authenticated flag exists
        authenticated = session.get('authenticated', False)
        if not authenticated:
            logger.debug("Session check failed: not authenticated")
            return False

        # The cookie is signed, so its contents are genuine - but genuine is
        # not the same as current. A session the server has revoked, or one
        # issued before this store existed, carries an id that is not on file.
        sid = session.get('sid')
        if not sid or sid not in self._load_session_ids():
            logger.info("Session check failed: session id has been revoked")
            session.clear()
            return False
        
        # Check session timeout
        login_time = session.get('login_time', 0)
        session_timeout = SecurityConfig.SESSION_TIMEOUT
        current_time = time.time()
        elapsed_time = current_time - login_time
        
        logger.debug(f"Session check: login_time={login_time}, current_time={current_time}, elapsed={elapsed_time}, timeout={session_timeout}")
        
        if elapsed_time > session_timeout:
            # Session expired, clear it
            logger.info(f"Session expired: {elapsed_time} seconds > {session_timeout} seconds timeout")
            session.clear()
            return False
        
        # Session is valid
        logger.debug(f"Session valid: {session_timeout - elapsed_time} seconds remaining")
        return True
    
    # ── Server-side session ids ────────────────────────────────────────
    # Read on demand rather than cached in the instance: the file is small,
    # reads are cheap next to the request they authorise, and re-reading means
    # a session revoked in one place cannot be honoured somewhere else because
    # a copy went stale.

    def _load_session_ids(self) -> dict:
        """{session_id: issued_at} for every session not yet revoked."""
        try:
            with open(SESSION_STORE_PATH, encoding='utf-8') as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            # No file yet, or one we cannot read. Treated as "nothing is
            # valid", which fails closed: the worst case is a login prompt.
            return {}

    def _save_session_ids(self, ids: dict) -> bool:
        """Persist the live set, dropping anything long past use."""
        cutoff = time.time() - SESSION_ID_MAX_AGE
        pruned = {k: v for k, v in ids.items()
                  if isinstance(v, (int, float)) and v > cutoff}
        try:
            os.makedirs(os.path.dirname(SESSION_STORE_PATH) or '.', exist_ok=True)
            # 0600: this file is the difference between a signed cookie being
            # honoured and refused, so nothing but the service account reads it.
            atomic_write_json(SESSION_STORE_PATH, pruned, mode=0o600, indent=0)
            return True
        except OSError as e:
            logger.error(f"Could not write the session store: {e}")
            return False

    def _issue_session_id(self) -> str:
        """Record a new session and return its id."""
        sid = secrets.token_urlsafe(24)
        ids = self._load_session_ids()
        ids[sid] = time.time()
        self._save_session_ids(ids)
        return sid

    def _revoke_session_id(self, sid: str) -> None:
        """Drop one session, so a cookie carrying it stops being accepted."""
        if not sid:
            return
        ids = self._load_session_ids()
        if ids.pop(sid, None) is not None:
            self._save_session_ids(ids)

    def revoke_all_sessions(self) -> None:
        """Refuse every session currently outstanding, on any device."""
        self._save_session_ids({})

    def refresh_session(self) -> bool:
        """
        Refresh the current session by updating the login time.
        Only works if session is currently authenticated.
        
        Returns:
            bool: True if session was refreshed, False if not authenticated
        """
        if session.get('authenticated', False):
            session['login_time'] = time.time()
            return True
        return False
    
    def get_session_info(self) -> dict:
        """
        Get information about the current session.
        
        Returns:
            dict: Session information including time remaining
        """
        if not session.get('authenticated', False):
            return {
                'authenticated': False,
                'time_remaining': 0,
                'expires_at': 0
            }
        
        login_time = session.get('login_time', 0)
        session_timeout = SecurityConfig.SESSION_TIMEOUT
        current_time = time.time()
        elapsed_time = current_time - login_time
        time_remaining = max(0, session_timeout - elapsed_time)
        expires_at = login_time + session_timeout
        
        return {
            'authenticated': True,
            'time_remaining': int(time_remaining),
            'expires_at': int(expires_at),
            'elapsed_time': int(elapsed_time),
            'session_timeout': session_timeout
        }
    
    def login(self, username: str, password: str) -> bool:
        """
        Authenticate user and create session.
        
        Args:
            username (str): Username
            password (str): Password
            
        Returns:
            bool: True if login successful
        """
        if self.verify_credentials(username, password):
            self.login_attempts.reset()
            session['authenticated'] = True
            session['username'] = username
            session['login_time'] = time.time()
            session['sid'] = self._issue_session_id()
            # Make session permanent to leverage Flask's session management
            session.permanent = True
            return True

        failures = self.login_attempts.record_failure()
        limit = SecurityConfig.LOGIN_LOCKOUT_ATTEMPTS
        if limit and failures >= limit:
            logger.warning(
                f"Login locked after {failures} failed attempts since boot - "
                "power-cycle the device to clear it")
        return False
    
    def logout(self):
        """Log out: revoke the session server-side, then clear the cookie.

        Revoking first, and deliberately not conditioned on the clear
        succeeding. Whether the browser drops its copy is the browser's
        business; once the id is off the file the cookie is refused either way.
        """
        self._revoke_session_id(session.get('sid'))
        session.clear()
    
    def lockout_message(self, hours: int) -> str:
        """The refusal, in the language the device is set to.

        Built here rather than in the route: the login page is the one screen
        an operator may be looking at before anything else has told them what
        is wrong, and 'try again later' with no number is the least useful
        thing it could say.
        """
        # login_locked is carried in every language; English stands in for a
        # table that somehow lacks it. The literal below is only for the case
        # where the translations module itself could not be imported, which
        # would mean the app is in no state to be logged into anyway.
        try:
            from utils.translations import translations
            lang = (self.config_manager.get('language', 'en') or 'en').lower()
            table = translations.get(lang) or translations['en']
            template = table.get('login_locked') or translations['en']['login_locked']
        except Exception:
            template = ('Too many failed login attempts. The device stays locked '
                        'for {hours} h, or unlocks straight away if you '
                        'power-cycle it.')
        try:
            return template.format(hours=hours)
        except (KeyError, IndexError):
            return template

    def check_rate_limit(self, ip: str) -> Tuple[bool, int]:
        """
        Check if request is within rate limits.
        
        Args:
            ip (str): Client IP address
            
        Returns:
            Tuple[bool, int]: (allowed, reset_time)
        """
        max_requests = SecurityConfig.RATE_LIMIT_REQUESTS
        window = SecurityConfig.RATE_LIMIT_WINDOW
        
        allowed = self.rate_limiter.is_allowed(ip, max_requests, window)
        reset_time = self.rate_limiter.get_reset_time(ip, window)
        
        return allowed, reset_time


def require_auth(auth_manager: AuthManager):
    """
    Decorator to require authentication for routes.
    Automatically refreshes session on authenticated activity.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check authentication first
            if not auth_manager.is_authenticated():
                return jsonify({
                    'error': 'Authentication required',
                    'message': 'Please login to access this resource'
                }), 401
            
            # Automatically refresh session on any authenticated activity
            auth_manager.refresh_session()
            
            # If authenticated, skip rate limiting for API requests
            # (Rate limiting still applies to login attempts via separate decorator)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_web_auth(auth_manager: AuthManager):
    """
    Decorator to require authentication for web page routes.
    Redirects to login page instead of returning JSON error.
    Automatically refreshes session on authenticated activity.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check authentication first
            if not auth_manager.is_authenticated():
                # Redirect to login page for web requests
                from flask import redirect, url_for
                return redirect(url_for('login_page'))

            # Automatically refresh session on any authenticated activity
            auth_manager.refresh_session()

            # Prevent browsers from caching authenticated pages.
            # Without no-store, mobile browsers may serve a stale cached copy of
            # the config page after logout, bypassing this auth check entirely.
            response = make_response(f(*args, **kwargs))
            response.headers['Cache-Control'] = 'no-store, private'
            response.headers['Pragma'] = 'no-cache'
            return response
        return decorated_function
    return decorator


def allow_public_or_auth(auth_manager: AuthManager, config_manager):
    """
    Decorator that allows public access when public_dashboard is enabled,
    otherwise requires authentication like require_web_auth.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
        config_manager: ConfigManager instance for checking public_dashboard setting
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # If public dashboard is enabled, allow access without auth
            if config_manager.config.get('public_dashboard', False):
                # Still refresh session if user happens to be authenticated
                if auth_manager.is_authenticated():
                    auth_manager.refresh_session()
                return f(*args, **kwargs)
            
            # Otherwise require authentication
            if not auth_manager.is_authenticated():
                from flask import redirect, url_for
                return redirect(url_for('login_page'))
            
            auth_manager.refresh_session()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Address ranges that can only be a machine on your own side of the internet:
# loopback, RFC1918, IPv6 ULA, link-local, and the shared range Tailscale and
# carrier NAT use. A request whose *peer* is one of these came either from the
# LAN or from a reverse proxy sitting next to the device, which is what makes
# its X-Forwarded-For worth reading.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network('100.64.0.0/10')


def _is_local_hop(addr: str) -> bool:
    """True when this address is on your own network rather than the internet."""
    try:
        ip = ipaddress.ip_address((addr or '').strip())
    except ValueError:
        return False
    if ip.version == 4 and ip in _SHARED_ADDRESS_SPACE:
        return True
    return ip.is_private or ip.is_loopback or ip.is_link_local


def client_ip() -> str:
    """The address to hold responsible for this request.

    X-Forwarded-For is written by whoever sends the request, so reading it
    unconditionally - as this used to - let anyone claim a new address per
    attempt, and so a fresh rate-limit bucket. Ignoring it entirely is no good
    either: behind a reverse proxy every request arrives from the proxy, and
    the whole internet would then share one bucket.

    So the chain is walked from the near end, dropping hops for as long as they
    are on your own network. The first address outside it is the client. If the
    peer itself is public there is no proxy of yours in the path, nothing in
    the header is evidence, and it is not read at all.

    That covers a proxy on the same host, in a container, or elsewhere on the
    LAN without being told which - and a spoofed header from a public client
    changes nothing, because the walk never starts.
    """
    peer = request.remote_addr or 'unknown'
    if not _is_local_hop(peer):
        return peer

    forwarded = request.headers.get('X-Forwarded-For', '')
    for hop in reversed([h.strip() for h in forwarded.split(',') if h.strip()]):
        if not _is_local_hop(hop):
            return hop

    # nginx's default is X-Real-IP on its own, with no chain to walk.
    real_ip = (request.headers.get('X-Real-IP') or '').strip()
    if real_ip and not _is_local_hop(real_ip):
        return real_ip

    # Everything in sight is local: a client on the LAN.
    return peer


def request_is_https() -> bool:
    """Whether the browser's own connection is encrypted.

    True for TLS terminated here, and for TLS terminated by a proxy on your own
    network that says so in X-Forwarded-Proto. The header is believed only from
    a local peer, and only ever to answer yes: the two things it decides - the
    Secure flag on the session cookie, and HSTS - are harmless to switch on by
    mistake and unsafe to leave off by mistake.
    """
    if request.is_secure:
        return True
    if not _is_local_hop(request.remote_addr or ''):
        return False
    proto = (request.headers.get('X-Forwarded-Proto') or '').split(',')[0].strip().lower()
    return proto == 'https'


class SchemeAwareSessionInterface(SecureCookieSessionInterface):
    """Sets the session cookie's Secure flag from the request it answers.

    Flask reads SESSION_COOKIE_SECURE once, but the same mempaper answers both
    http://<ip> on the LAN and https://<domain> through a reverse proxy, and
    the right answer differs per request. Fixed on, and a LAN browser is handed
    a cookie it will never send back - login appears to succeed and then does
    nothing. Fixed off, and the cookie that is the whole session travels in the
    clear the moment the device is published.
    """

    def get_cookie_secure(self, app):
        if not has_request_context():
            return super().get_cookie_secure(app)
        return request_is_https()


def require_rate_limit(auth_manager: AuthManager, exempt_authenticated=False):
    """
    Decorator to apply rate limiting to routes.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
        exempt_authenticated (bool): If True, skip rate limiting for authenticated users
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # If exempt_authenticated is True and user is authenticated, skip rate limiting
            if exempt_authenticated and auth_manager.is_authenticated():
                return f(*args, **kwargs)

            allowed, reset_time = auth_manager.check_rate_limit(client_ip())
            if not allowed:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Too many requests. Try again in {reset_time} seconds.',
                    'retry_after': reset_time
                }), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_not_locked(auth_manager: AuthManager):
    """Refuse logins once the failures since boot have passed the threshold.

    Separate from the rate limit, which only ever asks an attacker to wait.
    This one does not lift on its own: the count lives in a file stamped with
    the kernel boot id, so only a power cycle clears it. 423 rather than 429,
    since there is no retry-after that would be true.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if auth_manager.login_attempts.is_locked():
                logger.warning(f"Login refused - locked (from {client_ip()})")
                hours = max(1, round(auth_manager.login_attempts.seconds_remaining() / 3600))
                return jsonify({
                    'success': False,
                    'locked': True,
                    'hours_remaining': hours,
                    'message': auth_manager.lockout_message(hours),
                }), 423
            return f(*args, **kwargs)
        return decorated_function
    return decorator
