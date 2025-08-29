"""
Authentication and Rate Limiting Module

Handles admin authentication and rate limiting for the Mempaper application.
Provides protection against unauthorized access and request flooding.
Now includes secure Argon2 password hashing for enhanced security.

Version: 2.0 - Enhanced with Argon2 security
"""

import hashlib
import time
import logging
from functools import wraps
from collections import defaultdict, deque
from typing import Dict, Tuple
from flask import request, jsonify, session
from secure_password_manager import SecurePasswordManager

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
        if not session.get('authenticated', False):
            return False
        
        # Check session timeout
        login_time = session.get('login_time', 0)
        session_timeout = self.config_manager.get('session_timeout', 172800)  # Default 48 hours
        
        if time.time() - login_time > session_timeout:
            # Session expired, clear it
            session.clear()
            return False
        
        return True
    
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
        max_requests = self.config_manager.get("rate_limit_requests", 100)
        window = self.config_manager.get("rate_limit_window", 900)  # 15 minutes
        
        allowed = self.rate_limiter.is_allowed(ip, max_requests, window)
        reset_time = self.rate_limiter.get_reset_time(ip, window)
        
        return allowed, reset_time


def require_auth(auth_manager: AuthManager):
    """
    Decorator to require authentication for routes.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check rate limiting first
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
            
            # Check authentication
            if not auth_manager.is_authenticated():
                return jsonify({
                    'error': 'Authentication required',
                    'message': 'Please login to access this resource'
                }), 401
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_web_auth(auth_manager: AuthManager):
    """
    Decorator to require authentication for web page routes.
    Redirects to login page instead of returning JSON error.
    
    Args:
        auth_manager (AuthManager): Authentication manager instance
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check rate limiting first
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
            if client_ip:
                client_ip = client_ip.split(',')[0].strip()
            
            allowed, reset_time = auth_manager.check_rate_limit(client_ip)
            if not allowed:
                # For web pages, redirect to login with error message
                from flask import redirect, url_for, flash
                flash(f'Too many requests. Try again in {reset_time} seconds.', 'error')
                return redirect(url_for('login_page'))
            
            # Check authentication
            if not auth_manager.is_authenticated():
                # Redirect to login page for web requests
                from flask import redirect, url_for
                return redirect(url_for('login_page'))
            
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
