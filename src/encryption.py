"""Encryption utilities for securing sensitive data like OAuth tokens.

Uses Fernet (symmetric encryption) from the cryptography library to encrypt/decrypt
sensitive configuration values before storing them.
"""

import os
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)

# Global encryption instance
_fernet: Optional[Fernet] = None
_encryption_enabled = False


def _derive_key_from_secret(secret: str, salt: bytes) -> bytes:
    """Derive a Fernet key from a secret string using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


def initialize_encryption() -> bool:
    """Initialize the encryption system.
    
    Reads FIESTA_ENCRYPTION_KEY from environment. If not set, tries to generate
    one from FIESTA_SECRET_KEY. If neither exists, encryption is disabled.
    
    Returns:
        True if encryption was initialized, False otherwise
    """
    global _fernet, _encryption_enabled
    
    # Check for explicit encryption key
    encryption_key = os.getenv("FIESTA_ENCRYPTION_KEY")
    
    if not encryption_key:
        # Try to derive from secret key
        secret_key = os.getenv("FIESTA_SECRET_KEY")
        if secret_key:
            # Use a fixed salt for key derivation (stored with the app, not secret)
            # In production, you'd want to store this salt securely
            salt = b"fiestaboard_oauth_token_encryption_v1"
            encryption_key_bytes = _derive_key_from_secret(secret_key, salt)
            encryption_key = encryption_key_bytes.decode()
            logger.info("Derived encryption key from FIESTA_SECRET_KEY")
        else:
            logger.warning(
                "Neither FIESTA_ENCRYPTION_KEY nor FIESTA_SECRET_KEY found in environment. "
                "OAuth tokens will be stored unencrypted. Set FIESTA_ENCRYPTION_KEY or "
                "FIESTA_SECRET_KEY environment variable to enable encryption."
            )
            _encryption_enabled = False
            return False
    
    try:
        _fernet = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        _encryption_enabled = True
        logger.info("Encryption initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize encryption: {e}")
        _encryption_enabled = False
        return False


def is_encryption_enabled() -> bool:
    """Check if encryption is enabled."""
    return _encryption_enabled


def encrypt_value(value: str) -> str:
    """Encrypt a string value.
    
    Args:
        value: Plain text value to encrypt
        
    Returns:
        Encrypted value as a string (or original value if encryption disabled)
    """
    if not _encryption_enabled or not _fernet:
        return value
    
    try:
        encrypted = _fernet.encrypt(value.encode())
        # Return as base64 string with prefix to identify encrypted values
        return f"enc_v1:{base64.urlsafe_b64encode(encrypted).decode()}"
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        # Return original value if encryption fails (logged for debugging)
        return value


def decrypt_value(value: str) -> str:
    """Decrypt an encrypted string value.
    
    Args:
        value: Encrypted value (or plain text if not encrypted)
        
    Returns:
        Decrypted value (or original if not encrypted/encryption disabled)
    """
    if not value:
        return value
    
    # Check if value is encrypted (has our prefix)
    if not value.startswith("enc_v1:"):
        # Not encrypted, return as-is
        return value
    
    if not _encryption_enabled or not _fernet:
        logger.warning("Attempted to decrypt value but encryption is not enabled")
        return value
    
    try:
        # Remove prefix and decode
        encrypted_data = base64.urlsafe_b64decode(value[7:])  # Skip "enc_v1:" prefix
        decrypted = _fernet.decrypt(encrypted_data)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        # Return original value if decryption fails
        return value


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.
    
    Returns:
        Base64-encoded encryption key suitable for FIESTA_ENCRYPTION_KEY env var
    """
    return Fernet.generate_key().decode()


# Initialize on module import
initialize_encryption()
