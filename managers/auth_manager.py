"""
Authentication and Rate Limiting Module

Handles admin authentication and rate limiting for the Mempaper application.
Provides protection against unauthorized access and request flooding.
Now includes secure Argon2 password hashing for enhanced security.

Version: 2.0 - Enhanced with Argon2 security
"""

import time
import logging
from functools import wraps
from collections import defaultdict, deque
from typing import Dict, Tuple
from flask import request, jsonify, session
from managers.secure_password_manager import SecurePasswordManager
from utils.security_config import SecurityConfig

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
            
            # If no password is set up, trigger first-time setup
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
            session['authenticated'] = True
            session['username'] = username
            session['login_time'] = time.time()
            # Make session permanent to leverage Flask's session management
            session.permanent = True
            return True
        return False
    
    def logout(self):
        """Logout user and clear session."""
        session.clear()
    
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
            
            # If authenticated, skip rate limiting for web pages
            # (Rate limiting still applies to login attempts)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


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
                
            # Check rate limiting
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            allowed, reset_time = auth_manager.check_rate_limit(client_ip)
            if not allowed:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Too many requests. Try again in {reset_time} seconds.',
                    'retry_after': reset_time
                }), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_mobile_auth(mobile_token_manager):
    """
    Decorator to require mobile API token authentication for routes.
    
    Args:
        mobile_token_manager: Mobile token manager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # First check for mobile session authentication
            if session.get('mobile_authenticated') and session.get('mobile_token'):
                token = session.get('mobile_token')
                if mobile_token_manager.validate_token(token):
                    return f(*args, **kwargs)
            
            # Check for token in Authorization header
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                if mobile_token_manager.validate_token(token):
                    return f(*args, **kwargs)
            
            # Check for token in request body
            data = request.json or {}
            token = data.get('token', '')
            if token and mobile_token_manager.validate_token(token):
                return f(*args, **kwargs)
            
            return jsonify({
                'error': 'Mobile authentication required',
                'message': 'Valid API token required for mobile access'
            }), 401
        return decorated_function
    return decorator
