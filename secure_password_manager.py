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
        
        # Initialize Argon2 password hasher with security-recommended parameters
        # These parameters provide good security vs performance balance
        self.ph = PasswordHasher(
            time_cost=3,       # Number of iterations (3 is recommended minimum)
            memory_cost=65536, # Memory usage in KB (64 MB - good security/performance balance)
            parallelism=1,     # Number of parallel threads (1 for consistency)
            hash_len=32,       # Output hash length in bytes (32 is standard)
            salt_len=16        # Salt length in bytes (16 is recommended)
        )
    
    def is_password_set(self):
        """
        Check if a password is already configured.
        
        Returns:
            bool: True if admin_password_hash exists in config, False otherwise
        """
        password_hash = self.config_manager.get('admin_password_hash')
        return password_hash is not None and password_hash.strip() != ""
    
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

        logger.info("No admin password found - starting first-time setup")

        # Stop config file watching to avoid console prompt issues
        if hasattr(self.config_manager, 'stop_file_watching'):
            self.config_manager.stop_file_watching()

        # Prompt for new password
        new_password = self.prompt_for_new_password()
        if not new_password:
            logger.error("Password setup cancelled or failed")
            # Optionally restart file watching after failed setup
            if hasattr(self.config_manager, 'start_file_watching'):
                self.config_manager.start_file_watching()
            return False

        # Hash the password
        password_hash = self.hash_password(new_password)
        if not password_hash:
            logger.error("Failed to hash password")
            print("❌ Failed to hash password. Please try again.")
            if hasattr(self.config_manager, 'start_file_watching'):
                self.config_manager.start_file_watching()
            return False

        # Store the hash and remove old cleartext password
        try:
            self.config_manager.set('admin_password_hash', password_hash)

            # Remove old cleartext password if it exists
            if self.config_manager.get('admin_password'):
                self.config_manager.remove('admin_password')
                logger.info("Removed old cleartext password from config")

            self.config_manager.save_config()

            print("✅ Password successfully hashed and stored securely!")
            print("🔒 Your password is now protected with Argon2id encryption.")
            logger.info("First-time password setup completed successfully")

            # Optionally restart file watching after setup
            if hasattr(self.config_manager, 'start_file_watching'):
                self.config_manager.start_file_watching()
            return True

        except Exception as e:
            logger.error(f"Failed to save password hash to config: {e}")
            print(f"❌ Failed to save password configuration: {e}")
            if hasattr(self.config_manager, 'start_file_watching'):
                self.config_manager.start_file_watching()
            return False
    
    def authenticate_user(self, username, password):
        """
        Authenticate a user with username and password.
        
        Args:
            username (str): Username to authenticate
            password (str): Plain text password
            
        Returns:
            bool: True if authentication successful, False otherwise
        """
        # Check username
        stored_username = self.config_manager.get('admin_username')
        if not stored_username or username != stored_username:
            logger.warning(f"Authentication failed - invalid username: {username}")
            return False
        
        # Check if password is configured
        if not self.is_password_set():
            logger.error("No password configured - authentication impossible")
            return False
        
        # Verify password
        stored_hash = self.config_manager.get('admin_password_hash')
        return self.verify_password(password, stored_hash)
    
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
        cleartext_password = self.config_manager.get('admin_password')
        if not cleartext_password or cleartext_password.strip() == "":
            # No password to migrate - will trigger first-time setup
            return True
        
        logger.info("Migrating existing cleartext password to secure hash")
        print("\n🔄 Migrating existing password to secure encryption...")
        
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
