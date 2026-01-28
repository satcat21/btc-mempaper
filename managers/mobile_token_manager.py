"""
Mobile API Token Manager for Flutter App Authentication

Provides long-lived API tokens for mobile apps to avoid frequent re-authentication.
Tokens are stored securely and can be revoked as needed.
"""

import secrets
import time
import logging
from typing import Dict, Optional, List
from managers.secure_cache_manager import SecureCacheManager

# Setup logging
logger = logging.getLogger(__name__)


class MobileTokenManager:
    """Manages API tokens for mobile app authentication."""
    
    def __init__(self, cache_manager: SecureCacheManager):
        """
        Initialize mobile token manager.
        
        Args:
            cache_manager: Secure cache manager for token storage
        """
        self.cache_manager = cache_manager
        self.token_cache_key = "mobile_api_tokens"
        self.tokens = self._load_tokens()
        
    def _load_tokens(self) -> Dict:
        """Load tokens from secure cache."""
        try:
            cache_data = self.cache_manager.load_cache()
            tokens_data = cache_data.get(self.token_cache_key, {})
            if tokens_data and isinstance(tokens_data, dict):
                return tokens_data
            return {}
        except Exception as e:
            logger.error(f"Failed to load mobile tokens: {e}")
            return {}
    
    def _save_tokens(self) -> bool:
        """Save tokens to secure cache."""
        try:
            # Load existing cache data
            cache_data = self.cache_manager.load_cache()
            # Update the tokens section
            cache_data[self.token_cache_key] = self.tokens
            # Save the entire cache back
            return self.cache_manager.save_cache(cache_data)
        except Exception as e:
            logger.error(f"Failed to save mobile tokens: {e}")
            return False
    
    def generate_token(self, device_name: str, validity_days: int = 90) -> Optional[str]:
        """
        Generate a new API token for a mobile device.
        
        Args:
            device_name: Human-readable device name
            validity_days: Token validity in days (default 90 days)
            
        Returns:
            str: Generated token or None if failed
        """
        try:
            # Generate secure random token
            token = secrets.token_urlsafe(32)
            
            # Calculate expiration
            expiration = time.time() + (validity_days * 24 * 60 * 60)
            
            # Store token info
            self.tokens[token] = {
                'device_name': device_name,
                'created_at': time.time(),
                'expires_at': expiration,
                'last_used': None,
                'active': True
            }
            
            if self._save_tokens():
                logger.info(f"Generated mobile API token for device: {device_name}")
                return token
            else:
                logger.error("Failed to save token after generation")
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate mobile token: {e}")
            return None
    
    def validate_token(self, token: str) -> bool:
        """
        Validate if a token is active and not expired.
        
        Args:
            token: Token to validate
            
        Returns:
            bool: True if token is valid
        """
        try:
            if token not in self.tokens:
                return False
            
            token_data = self.tokens[token]
            
            # Check if token is active
            if not token_data.get('active', False):
                return False
            
            # Check if token is expired
            if token_data.get('expires_at', 0) < time.time():
                logger.info(f"Mobile token expired for device: {token_data.get('device_name', 'unknown')}")
                return False
            
            # Update last used timestamp
            token_data['last_used'] = time.time()
            self._save_tokens()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate mobile token: {e}")
            return False
    
    def revoke_token(self, token: str) -> bool:
        """
        Revoke a specific token.
        
        Args:
            token: Token to revoke
            
        Returns:
            bool: True if token was revoked
        """
        try:
            if token in self.tokens:
                self.tokens[token]['active'] = False
                self._save_tokens()
                logger.info(f"Revoked mobile token for device: {self.tokens[token].get('device_name', 'unknown')}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to revoke mobile token: {e}")
            return False
    
    def list_tokens(self) -> List[Dict]:
        """
        List all active tokens with metadata.
        
        Returns:
            List of token information (without actual token values)
        """
        try:
            token_list = []
            for token, data in self.tokens.items():
                if data.get('active', False):
                    token_info = {
                        'device_name': data.get('device_name', 'Unknown'),
                        'created_at': data.get('created_at'),
                        'expires_at': data.get('expires_at'),
                        'last_used': data.get('last_used'),
                        'token_preview': token[:8] + '...' + token[-4:],  # Show partial token
                        'days_until_expiry': int((data.get('expires_at', 0) - time.time()) / (24 * 60 * 60))
                    }
                    token_list.append(token_info)
            
            return sorted(token_list, key=lambda x: x['created_at'], reverse=True)
        except Exception as e:
            logger.error(f"Failed to list mobile tokens: {e}")
            return []
    
    def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tokens from storage.
        
        Returns:
            int: Number of tokens cleaned up
        """
        try:
            current_time = time.time()
            expired_tokens = []
            
            for token, data in self.tokens.items():
                if data.get('expires_at', 0) < current_time:
                    expired_tokens.append(token)
            
            for token in expired_tokens:
                del self.tokens[token]
            
            if expired_tokens:
                self._save_tokens()
                logger.info(f"Cleaned up {len(expired_tokens)} expired mobile tokens")
            
            return len(expired_tokens)
        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0
