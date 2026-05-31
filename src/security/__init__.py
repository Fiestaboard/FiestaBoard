"""Security helpers for FiestaBoard.

Submodules:
    - ``secrets``: symmetric (Fernet) encryption for sensitive values stored
      on disk (API keys, board keys, plugin credentials, etc.).
"""

from .secrets import (
    ENCRYPTED_PREFIX,
    decrypt_secret,
    encrypt_secret,
    get_secret_cipher,
    is_encrypted,
    rotate_key,
)

__all__ = [
    "encrypt_secret",
    "decrypt_secret",
    "is_encrypted",
    "rotate_key",
    "get_secret_cipher",
    "ENCRYPTED_PREFIX",
]
