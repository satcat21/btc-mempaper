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
    
    # Session timeout (balanced for usability vs security)
    SESSION_TIMEOUT = 7200  # 2 hours (7200 seconds) - original timeout
    
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
        return Path(__file__).parent / 'config' / '.secret_key'
    
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
            secret_file.write_text(key)
            secret_file.chmod(0o600)  # Restrict file permissions
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
