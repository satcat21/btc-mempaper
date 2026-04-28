"""
Secure Password Manager for BTC Mempaper Application

This module provides secure password hashing and verification using Argon2id,
the current gold standard for password hashing. It handles first-time setup
and ongoing authentication securely.

Key Features:
- Argon2id hashing algorithm (winner of Password Hashing Competition)
- Resistance to GPU/ASIC attacks
- Configurable time and memory costs
- Secure random salt generation
- First-time setup detection and password creation
"""

import getpass
import logging
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, HashingError

logger = logging.getLogger(__name__)

class SecurePasswordManager:
    """
    Manages secure password hashing and verification using Argon2id.
    
    Uses recommended security parameters:
    - time_cost=3 (iterations)
    - memory_cost=65536 (64 MB memory usage)
    - parallelism=1 (single thread)
    - hash_len=32 (32 byte output)
    - salt_len=16 (16 byte salt)
    """
    
    def __init__(self, config_manager):
        """
        Initialize the password manager.
        
        Args:
            config_manager: Configuration manager instance for storing hashed passwords
        """
        self.config_manager = config_manager
        
        # Argon2id parameters tuned for Raspberry Pi Zero WH (512 MB RAM, single core).
        # memory_cost=19456 KB (19 MB) meets OWASP minimum recommendation while leaving
        # enough headroom for the rest of the application. time_cost=2 compensates for
        # the lower memory cost to keep the overall work factor reasonable.
        self.ph = PasswordHasher(
            time_cost=2,       # Iterations (increased slightly to offset lower memory cost)
            memory_cost=19456, # Memory in KB (19 MB — OWASP minimum, Pi Zero safe)
            parallelism=1,     # Single thread for single-core CPU
            hash_len=32,       # 32-byte output (standard)
            salt_len=16        # 16-byte salt (recommended)
        )
    
    def is_password_set(self):
        """
        Check if at least one user is configured.

        Returns:
            bool: True if admin_users has entries or legacy admin_password_hash exists
        """
        if self._get_users():
            return True
        # Legacy single-user fallback
        password_hash = self.config_manager.get('admin_password_hash')
        return password_hash is not None and password_hash.strip() != ""

    def _get_users(self) -> dict:
        """Return a copy of the admin_users dict (thread-safe)."""
        with self.config_manager.config_lock:
            users = self.config_manager.config.get('admin_users')
            return dict(users) if users else {}

    def list_users(self) -> list:
        """Return the list of configured usernames."""
        return list(self._get_users().keys())

    def create_user(self, username: str, password: str) -> bool:
        """
        Create or update an admin user.

        Args:
            username (str): Username (must be non-empty)
            password (str): Plain text password (minimum 8 characters)

        Returns:
            bool: True if the user was saved successfully
        """
        username = (username or "").strip()
        if not username:
            logger.error("Username cannot be empty")
            return False
        if len(password) < 8:
            logger.error("Password must be at least 8 characters")
            return False
        password_hash = self.hash_password(password)
        if not password_hash:
            return False
        with self.config_manager.config_lock:
            users = dict(self.config_manager.config.get('admin_users') or {})
            users[username] = password_hash
            self.config_manager.config['admin_users'] = users
        self.config_manager.save_config()
        logger.info(f"User '{username}' created/updated successfully")
        return True

    def _migrate_to_multi_user(self) -> bool:
        """
        Migrate legacy single-user config (admin_username + admin_password_hash)
        into the admin_users dict format.  No-op if already migrated.
        """
        if self._get_users():
            return True  # Already in multi-user format

        with self.config_manager.config_lock:
            stored_hash = self.config_manager.config.get('admin_password_hash')
            stored_username = self.config_manager.config.get('admin_username')

        if not stored_hash or not stored_username:
            return True  # Nothing to migrate

        logger.info(f"Migrating user '{stored_username}' to multi-user format")
        with self.config_manager.config_lock:
            self.config_manager.config['admin_users'] = {stored_username: stored_hash}
        self.config_manager.save_config()
        logger.info("Migration to multi-user format complete")
        return True

    def hash_password(self, password):
        """
        Hash a password using Argon2id.
        
        Args:
            password (str): Plain text password to hash
            
        Returns:
            str: Argon2 hash string (includes algorithm, parameters, salt, and hash)
            None: If hashing fails
        """
        try:
            # Argon2 automatically generates a random salt and includes it in the hash
            hash_string = self.ph.hash(password)
            logger.info("Password successfully hashed using Argon2id")
            return hash_string
        except HashingError as e:
            logger.error(f"Password hashing failed: {e}")
            return None
    
    def verify_password(self, password, stored_hash):
        """
        Verify a password against a stored Argon2 hash.
        
        Args:
            password (str): Plain text password to verify
            stored_hash (str): Stored Argon2 hash string
            
        Returns:
            bool: True if password matches, False otherwise
        """
        try:
            # Argon2 automatically extracts salt and parameters from hash string
            self.ph.verify(stored_hash, password)
            logger.info("Password verification successful")
            return True
        except VerifyMismatchError:
            logger.warning("Password verification failed - incorrect password")
            return False
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def prompt_for_new_password(self):
        """
        Prompt user to create a new password with confirmation.
        Includes basic password strength validation.
        
        Returns:
            str: The new password if successfully created and confirmed
            None: If password creation was cancelled or failed
        """
        print("\n" + "="*60)
        print("🔐 FIRST TIME SETUP - CREATE ADMIN PASSWORD")
        print("="*60)
        print("No admin password is configured. Please create a secure password.")
        print("Requirements:")
        print("- Minimum 8 characters")
        print("- Recommended: Mix of letters, numbers, and symbols")
        print("- This password will be hashed and stored securely")
        print("-"*60)
        
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Get password without echo
                password = getpass.getpass("Enter new admin password: ")
                
                # Basic validation
                if len(password) < 8:
                    print("❌ Password must be at least 8 characters long.")
                    continue
                
                if password.strip() == "":
                    print("❌ Password cannot be empty.")
                    continue
                
                # Confirm password
                confirm_password = getpass.getpass("Confirm admin password: ")
                
                if password != confirm_password:
                    print("❌ Passwords do not match. Please try again.")
                    continue
                
                print("✅ Password accepted and will be securely hashed.")
                return password
                
            except KeyboardInterrupt:
                print("\n❌ Password setup cancelled by user.")
                return None
            except Exception as e:
                print(f"❌ Error during password input: {e}")
                continue
        
        print(f"❌ Failed to create password after {max_attempts} attempts.")
        return None
    
    def setup_first_time_password(self):
        """
        Handle first-time password setup workflow.
        Ensures password prompt is visible by stopping config file watching.
        Returns:
            bool: True if password was successfully set up, False otherwise
        """
        if self.is_password_set():
            logger.info("Admin password already configured")
            return True

        logger.info("No admin user found - starting first-time setup")

        # Stop config file watching to avoid console prompt issues
        if hasattr(self.config_manager, 'stop_file_watching'):
            self.config_manager.stop_file_watching()

        try:
            # Prompt for username
            try:
                new_username = input("Enter admin username [admin]: ").strip() or "admin"
            except (EOFError, KeyboardInterrupt):
                print("\n❌ Setup cancelled.")
                return False

            # Prompt for password
            new_password = self.prompt_for_new_password()
            if not new_password:
                logger.error("Password setup cancelled or failed")
                return False

            if not self.create_user(new_username, new_password):
                print("❌ Failed to save user.")
                return False

            # Remove legacy cleartext password if present
            if self.config_manager.get('admin_password'):
                self.config_manager.remove('admin_password')

            print(f"✅ User '{new_username}' created and stored securely!")
            print("🔒 Password protected with Argon2id.")
            logger.info("First-time user setup completed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed during first-time setup: {e}")
            print(f"❌ Setup failed: {e}")
            return False
        finally:
            if hasattr(self.config_manager, 'start_file_watching'):
                self.config_manager.start_file_watching()
    
    def authenticate_user(self, username, password):
        """
        Authenticate a user with username and password.
        
        Args:
            username (str): Username to authenticate
            password (str): Plain text password
            
        Returns:
            bool: True if authentication successful, False otherwise
        """
        users = self._get_users()
        if users:
            # Multi-user format
            stored_hash = users.get(username)
            if not stored_hash:
                logger.warning(f"Authentication failed - unknown user: {username}")
                return False
            if not self.verify_password(password, stored_hash):
                return False
            # Rehash if stored hash used different parameters
            try:
                if self.ph.check_needs_rehash(stored_hash):
                    new_hash = self.hash_password(password)
                    if new_hash:
                        with self.config_manager.config_lock:
                            u = dict(self.config_manager.config.get('admin_users') or {})
                            u[username] = new_hash
                            self.config_manager.config['admin_users'] = u
                        self.config_manager.save_config()
                        logger.info(f"Password rehashed for user '{username}'")
            except Exception as e:
                logger.warning(f"Password rehash skipped: {e}")
            return True

        # Legacy single-user fallback
        stored_username = self.config_manager.get('admin_username')
        if not stored_username or username != stored_username:
            logger.warning(f"Authentication failed - invalid username: {username}")
            return False
        stored_hash = self.config_manager.get('admin_password_hash')
        if not stored_hash:
            logger.error("No password configured - authentication impossible")
            return False
        if not self.verify_password(password, stored_hash):
            return False
        try:
            if self.ph.check_needs_rehash(stored_hash):
                new_hash = self.hash_password(password)
                if new_hash:
                    self.config_manager.set('admin_password_hash', new_hash)
                    self.config_manager.save_config()
                    logger.info("Password rehashed with updated parameters")
        except Exception as e:
            logger.warning(f"Password rehash skipped: {e}")
        return True
    
    def migrate_cleartext_password(self):
        """
        Migrate an existing cleartext password to hashed format.
        This is called automatically during startup for existing installations.
        
        Returns:
            bool: True if migration successful or not needed, False if failed
        """
        # Check if we already have a hashed password
        if self.is_password_set():
            return True
        
        # Check if we have a cleartext password to migrate
        # Use direct config access to avoid default fallback
        with self.config_manager.config_lock:
            current_config = self.config_manager.config
            cleartext_password = current_config.get('admin_password')
            
        if not cleartext_password or cleartext_password.strip() == "":
            # No password to migrate - will trigger first-time setup
            return True
            
        # Don't migrate if it's the default password value
        default_password = "mempaper2025"
        if cleartext_password == default_password:
            logger.info("Skipping migration of default password - treating as no password set")
            return True
        
        logger.info("Migrating existing cleartext password to secure hash")
        print("\n⚙️ Migrating existing password to secure encryption...")
        
        # Hash the existing password
        password_hash = self.hash_password(cleartext_password)
        if not password_hash:
            logger.error("Failed to hash existing password during migration")
            return False
        
        try:
            # Store hash and remove cleartext
            self.config_manager.set('admin_password_hash', password_hash)
            self.config_manager.remove('admin_password')
            self.config_manager.save_config()
            
            print("✅ Password successfully migrated to secure encryption!")
            logger.info("Password migration completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save migrated password: {e}")
            print(f"❌ Password migration failed: {e}")
            return False
    
    def update_username(self, new_username):
        """
        Update the admin username without requiring password change.
        Preserves the existing password hash.
        
        Args:
            new_username (str): New username to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not new_username or new_username.strip() == "":
            logger.error("Cannot set empty username")
            return False
        
        try:
            # Just update the username, password hash is preserved automatically
            self.config_manager.set('admin_username', new_username.strip())
            self.config_manager.save_config()
            
            logger.info(f"Username updated to: {new_username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update username: {e}")
            return False
    
    def change_password(self, new_password):
        """
        Change the admin password without requiring username change.
        
        Args:
            new_password (str): New password to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not new_password or len(new_password) < 8:
            logger.error("Password must be at least 8 characters")
            return False
        
        # Hash the new password
        password_hash = self.hash_password(new_password)
        if not password_hash:
            logger.error("Failed to hash new password")
            return False
        
        try:
            # Update password hash
            self.config_manager.set('admin_password_hash', password_hash)
            
            # Remove old cleartext password if it exists
            if self.config_manager.get('admin_password'):
                self.config_manager.remove('admin_password')
            
            self.config_manager.save_config()
            
            logger.info("Password changed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to change password: {e}")
            return False


def get_password_strength_info(password):
    """
    Analyze password strength and provide feedback.
    
    Args:
        password (str): Password to analyze
        
    Returns:
        dict: Analysis results with score and recommendations
    """
    analysis = {
        'score': 0,
        'strength': 'Very Weak',
        'recommendations': []
    }
    
    if len(password) >= 8:
        analysis['score'] += 20
    else:
        analysis['recommendations'].append("Use at least 8 characters")
    
    if len(password) >= 12:
        analysis['score'] += 20
    else:
        analysis['recommendations'].append("Consider 12+ characters for better security")
    
    if any(c.islower() for c in password):
        analysis['score'] += 15
    else:
        analysis['recommendations'].append("Add lowercase letters")
    
    if any(c.isupper() for c in password):
        analysis['score'] += 15
    else:
        analysis['recommendations'].append("Add uppercase letters")
    
    if any(c.isdigit() for c in password):
        analysis['score'] += 15
    else:
        analysis['recommendations'].append("Add numbers")
    
    if any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        analysis['score'] += 15
    else:
        analysis['recommendations'].append("Add special characters (!@#$%^&*)")
    
    # Determine strength level
    if analysis['score'] >= 80:
        analysis['strength'] = 'Very Strong'
    elif analysis['score'] >= 60:
        analysis['strength'] = 'Strong'
    elif analysis['score'] >= 40:
        analysis['strength'] = 'Medium'
    elif analysis['score'] >= 20:
        analysis['strength'] = 'Weak'
    else:
        analysis['strength'] = 'Very Weak'
    
    return analysis
