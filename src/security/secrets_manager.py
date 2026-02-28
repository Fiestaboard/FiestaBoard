"""Secure secrets management with encryption for OAuth tokens and sensitive credentials.

This module provides encrypted storage for sensitive data like OAuth tokens,
API keys, and other credentials. Data is encrypted using Fernet (symmetric encryption)
with a master key derived from an environment variable.

Usage:
    from src.security.secrets_manager import get_secrets_manager
    
    secrets = get_secrets_manager()
    secrets.set_secret("spotify", "access_token", "secret_value")
    token = secrets.get_secret("spotify", "access_token")
"""

import base64
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Default secrets storage location
DEFAULT_SECRETS_FILE = Path("/app/data/secrets.enc")

# Auto-generated master key storage location
DEFAULT_MASTER_KEY_FILE = Path("/app/data/master.key")

# Environment variable for master encryption key
MASTER_KEY_ENV = "FIESTABOARD_MASTER_KEY"

# Singleton instance
_secrets_manager: Optional["SecretsManager"] = None
_manager_lock = threading.Lock()


class SecretsManager:
    """Manages encrypted storage of sensitive credentials.
    
    Uses Fernet symmetric encryption to protect OAuth tokens, API keys,
    and other sensitive data at rest.
    """
    
    def __init__(self, secrets_file: Optional[Path] = None, master_key: Optional[str] = None):
        """Initialize secrets manager.
        
        Args:
            secrets_file: Path to encrypted secrets file (default: /app/data/secrets.enc)
            master_key: Master encryption key (default: from FIESTABOARD_MASTER_KEY env var)
        """
        self.secrets_file = secrets_file or DEFAULT_SECRETS_FILE
        self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Master key resolution order:
        # 1. Explicit parameter (for testing)
        # 2. Environment variable (user override)
        # 3. Persistent file (auto-generated, survives restarts)
        # 4. Generate new and save to file
        
        if master_key is None:
            # Check environment variable first
            master_key = os.getenv(MASTER_KEY_ENV)
            
            if master_key:
                logger.info(f"Using master key from {MASTER_KEY_ENV} environment variable")
            else:
                # Try to load from persistent file
                master_key = self._load_or_generate_master_key()
        
        # Derive encryption key from master key using PBKDF2
        self._fernet = self._create_fernet(master_key)
        
        # In-memory secrets cache (encrypted data)
        self._secrets: Dict[str, Dict[str, str]] = {}
        self._lock = threading.Lock()
        
        # Load existing secrets from disk
        self._load_secrets()
    
    def _load_or_generate_master_key(self) -> str:
        """Load master key from file or generate a new one.
        
        This allows the master key to persist across container restarts
        without requiring the user to set an environment variable.
        
        Returns:
            Master encryption key
        """
        master_key_file = DEFAULT_MASTER_KEY_FILE
        
        # Try to load existing key
        if master_key_file.exists():
            try:
                master_key = master_key_file.read_text().strip()
                if master_key:
                    logger.info(
                        f"Loaded master key from {master_key_file} "
                        f"(OAuth tokens will persist across restarts)"
                    )
                    return master_key
                else:
                    logger.warning(f"Master key file {master_key_file} is empty, generating new key")
            except Exception as e:
                logger.warning(f"Failed to read master key from {master_key_file}: {e}")
        
        # Generate new key and save to file
        master_key = Fernet.generate_key().decode('utf-8')
        
        try:
            # Write atomically using a temp file
            temp_file = master_key_file.with_suffix('.tmp')
            temp_file.write_text(master_key)
            temp_file.chmod(0o600)  # Restrict permissions to owner only
            temp_file.replace(master_key_file)
            
            logger.info(
                f"Generated and saved new master key to {master_key_file} "
                f"(OAuth tokens will now persist across restarts)"
            )
        except Exception as e:
            logger.warning(
                f"Failed to save master key to {master_key_file}: {e}. "
                f"Using in-memory key only - OAuth tokens will NOT persist across restarts!"
            )
        
        return master_key
    
    def _create_fernet(self, master_key: str) -> Fernet:
        """Create a Fernet instance from master key.
        
        Args:
            master_key: Master encryption key (can be any string)
            
        Returns:
            Fernet encryption instance
        """
        # Use PBKDF2HMAC to derive a 32-byte key from the master key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"fiestaboard_salt_v1",  # Static salt for consistency
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_key.encode('utf-8')))
        return Fernet(key)
    
    def _load_secrets(self):
        """Load encrypted secrets from disk."""
        if not self.secrets_file.exists():
            logger.debug(f"Secrets file does not exist: {self.secrets_file}")
            return
        
        try:
            with self._lock:
                # Read encrypted data
                encrypted_data = self.secrets_file.read_bytes()
                
                if not encrypted_data:
                    logger.debug("Secrets file is empty")
                    return
                
                # Decrypt data
                decrypted_data = self._fernet.decrypt(encrypted_data)
                self._secrets = json.loads(decrypted_data.decode('utf-8'))
                
                logger.info(f"Loaded {len(self._secrets)} secret namespaces from disk")
        
        except InvalidToken:
            logger.error(
                "Failed to decrypt secrets file. Master key may have changed. "
                "Secrets cannot be recovered without the original key."
            )
            self._secrets = {}
        
        except Exception as e:
            logger.error(f"Error loading secrets from disk: {e}")
            self._secrets = {}
    
    def _save_secrets(self):
        """Save encrypted secrets to disk."""
        try:
            with self._lock:
                # Serialize secrets to JSON
                data = json.dumps(self._secrets, indent=2).encode('utf-8')
                
                # Encrypt data
                encrypted_data = self._fernet.encrypt(data)
                
                # Write to disk atomically
                temp_file = self.secrets_file.with_suffix('.tmp')
                temp_file.write_bytes(encrypted_data)
                temp_file.replace(self.secrets_file)
                
                logger.debug(f"Saved {len(self._secrets)} secret namespaces to disk")
        
        except Exception as e:
            logger.error(f"Error saving secrets to disk: {e}")
            raise
    
    def set_secret(self, namespace: str, key: str, value: str):
        """Store a secret value.
        
        Args:
            namespace: Namespace (e.g., "spotify", "google_calendar")
            key: Secret key (e.g., "access_token", "refresh_token")
            value: Secret value to encrypt and store
        """
        with self._lock:
            if namespace not in self._secrets:
                self._secrets[namespace] = {}
            
            self._secrets[namespace][key] = value
        
        # Persist to disk
        self._save_secrets()
        
        logger.debug(f"Stored secret: {namespace}.{key}")
    
    def get_secret(self, namespace: str, key: str) -> Optional[str]:
        """Retrieve a secret value.
        
        Args:
            namespace: Namespace (e.g., "spotify", "google_calendar")
            key: Secret key (e.g., "access_token", "refresh_token")
            
        Returns:
            Decrypted secret value, or None if not found
        """
        with self._lock:
            namespace_secrets = self._secrets.get(namespace, {})
            return namespace_secrets.get(key)
    
    def delete_secret(self, namespace: str, key: Optional[str] = None):
        """Delete a secret or entire namespace.
        
        Args:
            namespace: Namespace to delete from
            key: Specific key to delete (if None, deletes entire namespace)
        """
        with self._lock:
            if key is None:
                # Delete entire namespace
                if namespace in self._secrets:
                    del self._secrets[namespace]
                    logger.debug(f"Deleted secret namespace: {namespace}")
            else:
                # Delete specific key
                if namespace in self._secrets and key in self._secrets[namespace]:
                    del self._secrets[namespace][key]
                    logger.debug(f"Deleted secret: {namespace}.{key}")
        
        self._save_secrets()
    
    def get_namespace(self, namespace: str) -> Dict[str, str]:
        """Get all secrets in a namespace.
        
        Args:
            namespace: Namespace to retrieve
            
        Returns:
            Dictionary of all secrets in the namespace
        """
        with self._lock:
            return dict(self._secrets.get(namespace, {}))
    
    def list_namespaces(self) -> list[str]:
        """List all secret namespaces.
        
        Returns:
            List of namespace names
        """
        with self._lock:
            return list(self._secrets.keys())


def get_secrets_manager(
    secrets_file: Optional[Path] = None,
    master_key: Optional[str] = None
) -> SecretsManager:
    """Get the global secrets manager instance.
    
    Args:
        secrets_file: Path to secrets file (default: /app/data/secrets.enc)
        master_key: Master encryption key (default: from env var)
        
    Returns:
        SecretsManager singleton instance
    """
    global _secrets_manager
    
    if _secrets_manager is None:
        with _manager_lock:
            if _secrets_manager is None:
                _secrets_manager = SecretsManager(secrets_file, master_key)
    
    return _secrets_manager


def reset_secrets_manager():
    """Reset the global secrets manager (primarily for testing)."""
    global _secrets_manager
    with _manager_lock:
        _secrets_manager = None
