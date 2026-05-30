"""Security helpers for FiestaBoard.

Submodules:
    - ``secrets``: symmetric (Fernet) encryption for sensitive values stored
      on disk (API keys, board keys, plugin credentials, etc.).
"""

from .secrets import (
    encrypt_secret,
    decrypt_secret,
    is_encrypted,
    rotate_key,
    get_secret_cipher,
    ENCRYPTED_PREFIX,
)

__all__ = [
    "encrypt_secret",
    "decrypt_secret",
    "is_encrypted",
    "rotate_key",
    "get_secret_cipher",
    "ENCRYPTED_PREFIX",
]
