"""
Security Configuration Module
Contains hardcoded security settings following best practices.
These values should not be user-configurable for security reasons.
"""

import os
import secrets
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SecurityConfig:
    """
    Hardcoded security configuration following industry best practices.
    These values are not user-configurable to prevent security misconfiguration.
    """
    
    # Rate limiting settings (balanced for usability vs security)
    RATE_LIMIT_REQUESTS = 10  # Max failed login attempts per window
    RATE_LIMIT_WINDOW = 300   # 5 minutes window (300 seconds)

    # Failed logins since the last boot after which the door closes until the
    # device is power-cycled. The sliding window above only ever costs an
    # attacker time; this ends the attempt. Generous enough that a person
    # mistyping a password never reaches it - twenty wrong passwords in one
    # boot is not someone who knows the password.
    #
    # The trade is availability: anyone who can reach /api/login can force the
    # lockout, and clearing it needs physical access. That is the right way
    # round for a device whose panel is in the room, and it is why the count
    # is high rather than tight.
    LOGIN_LOCKOUT_ATTEMPTS = 20

    # ...and how long it stands without one. A power cycle clears it at once,
    # which is the quick way back in for whoever is standing next to the
    # device; anyone else waits this out. Twenty guesses a day against Argon2id
    # is not an attack, so the wait costs an attacker everything and the owner
    # at most a day - and unlike a lockout that only a reboot clears, nobody
    # can use it to keep a remote operator out for good.
    LOGIN_LOCKOUT_SECONDS = 24 * 3600

    # Failed-login state, kept across the gunicorn worker recycling that would
    # otherwise wipe an in-memory counter every thousand requests. Holds the
    # boot id it was written under, so a real reboot clears the lockout and a
    # service restart does not.
    LOGIN_STATE_PATH = os.path.join('cache', '.login_state.json')
    
    # Session timeout (balanced for usability vs security)
    SESSION_TIMEOUT = 1800  # 30 minutes (1800 seconds)
    
    # Secret key length (industry standard)
    SECRET_KEY_LENGTH = 64  # 64 bytes = 512 bits
    
    # Cache for persistent secret key
    _cached_secret_key = None
    
    @staticmethod
    def generate_secret_key():
        """
        Generate a cryptographically secure secret key.
        
        Returns:
            str: A secure random secret key
        """
        return secrets.token_hex(SecurityConfig.SECRET_KEY_LENGTH)
    
    @staticmethod
    def _get_secret_key_file_path():
        """Get the path to the secret key file."""
        # Get project root (parent of utils/) and use config/ directory
        project_root = Path(__file__).parent.parent
        return project_root / 'config' / '.secret_key'
    
    @staticmethod
    def _load_secret_key_from_file():
        """Load secret key from file if it exists."""
        try:
            secret_file = SecurityConfig._get_secret_key_file_path()
            if secret_file.exists():
                key = secret_file.read_text().strip()
                if len(key) >= 32:  # Minimum 32 characters
                    logger.info("Loaded persistent secret key from file")
                    return key
        except Exception as e:
            logger.warning(f"Could not load secret key from file: {e}")
        return None
    
    @staticmethod
    def _save_secret_key_to_file(key):
        """Save secret key to file for persistence."""
        try:
            secret_file = SecurityConfig._get_secret_key_file_path()
            # Create with 0600 already applied rather than write-then-chmod:
            # the latter leaves the key readable by any local user for the
            # window between the two calls.
            fd = os.open(str(secret_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.write(fd, key.encode('utf-8'))
            finally:
                os.close(fd)
            secret_file.chmod(0o600)  # Enforce on pre-existing files too
            logger.info("Saved secret key to file for persistence")
        except Exception as e:
            logger.warning(f"Could not save secret key to file: {e}")
    
    @staticmethod
    def get_secret_key_from_env_or_generate():
        """
        Get secret key from environment variable, file, or generate a persistent one.
        This ensures sessions persist across app restarts.
        
        Returns:
            str: Secret key that persists across restarts
        """
        # Use cached key if available
        if SecurityConfig._cached_secret_key:
            return SecurityConfig._cached_secret_key
        
        # Check environment variable first (highest priority)
        env_key = os.environ.get('MEMPAPER_SECRET_KEY')
        if env_key and len(env_key) >= 32:  # Minimum 32 characters
            logger.info("Using secret key from environment variable")
            SecurityConfig._cached_secret_key = env_key
            return env_key
        
        # Try to load from persistent file
        file_key = SecurityConfig._load_secret_key_from_file()
        if file_key:
            SecurityConfig._cached_secret_key = file_key
            return file_key
        
        # Generate a new secure key and save it for persistence
        secret_key = SecurityConfig.generate_secret_key()
        SecurityConfig._save_secret_key_to_file(secret_key)
        SecurityConfig._cached_secret_key = secret_key
        logger.info("Generated new persistent secret key")
        return secret_key
    
    @staticmethod
    def get_security_settings():
        """
        Get all security settings as a dictionary.
        
        Returns:
            dict: Dictionary containing all security settings
        """
        return {
            'rate_limit_requests': SecurityConfig.RATE_LIMIT_REQUESTS,
            'rate_limit_window': SecurityConfig.RATE_LIMIT_WINDOW,
            'session_timeout': SecurityConfig.SESSION_TIMEOUT,
            'secret_key': SecurityConfig.get_secret_key_from_env_or_generate()
        }
    
    @staticmethod
    def log_security_settings():
        """
        Log current security settings (without revealing secret key).
        """
        logger.info("Security configuration initialized:")
        logger.info(f"  Rate limit: {SecurityConfig.RATE_LIMIT_REQUESTS} requests per {SecurityConfig.RATE_LIMIT_WINDOW} seconds")
        logger.info(f"  Session timeout: {SecurityConfig.SESSION_TIMEOUT} seconds ({SecurityConfig.SESSION_TIMEOUT // 3600} hours)")
        logger.info("  Secret key: Generated/configured (not logged for security)")
