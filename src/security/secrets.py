"""Symmetric encryption for secrets stored on disk.

Provides a small wrapper around :class:`cryptography.fernet.Fernet` that:

* Loads (or generates) a key from one of:
    1. ``FIESTABOARD_SECRET_KEY`` environment variable (urlsafe base64, 32 bytes).
    2. A key file at ``data/.secret_key`` with mode ``0600``. Generated on
       first use if missing.
* Marks encrypted values with the prefix ``"enc::v1::"`` so callers can
  distinguish ciphertext from legacy plaintext and migrate transparently.
* Is safe to call from multiple threads (the cipher is lazily built once
  and is itself thread-safe per :class:`cryptography.fernet.Fernet`).

This module deliberately handles only "secrets at rest" — passwords and
session tokens are handled by :mod:`src.auth.service` with separate, more
specialised primitives.
"""

from __future__ import annotations

import logging
import os
import stat
import threading
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Versioned marker on every ciphertext. Lets us spot encrypted values in
# config files and roll the scheme forward in the future without guessing.
ENCRYPTED_PREFIX = "enc::v1::"

# Path resolution mirrors src/config_manager.py — the canonical data
# directory is ``<repo>/data``.
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_KEY_PATH = _DATA_DIR / ".secret_key"

_ENV_VAR = "FIESTABOARD_SECRET_KEY"

_cipher_lock = threading.Lock()
_cipher: Optional[Fernet] = None
_loaded_from: Optional[str] = None  # for logs/tests


def _load_or_generate_key() -> bytes:
    """Return the raw Fernet key, generating one on disk if needed."""
    global _loaded_from

    env_value = os.environ.get(_ENV_VAR, "").strip()
    if env_value:
        # Validate eagerly so misconfiguration surfaces at startup rather
        # than on the first decrypt call.
        try:
            Fernet(env_value.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"{_ENV_VAR} is set but is not a valid Fernet key "
                "(expected 32 url-safe base64 bytes)."
            ) from exc
        _loaded_from = "env"
        return env_value.encode("utf-8")

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes().strip()
        try:
            Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Secret key file at {_KEY_PATH} is corrupt. "
                "Delete it to regenerate (encrypted values will need to "
                f"be re-entered) or set {_ENV_VAR}."
            ) from exc
        _loaded_from = "file"
        return key

    # First run: generate, persist with restrictive perms.
    key = Fernet.generate_key()
    # Write atomically with a 0600 mode so other users on the host cannot
    # read the key. ``os.open`` lets us set the mode at create time.
    fd = os.open(
        str(_KEY_PATH),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(key)
    except Exception:
        # Best-effort cleanup so we don't leave an empty key file behind.
        try:
            _KEY_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.warning(
        "Generated new secret encryption key at %s. Back this file up "
        "(or set %s) — losing it makes existing encrypted secrets "
        "unrecoverable.",
        _KEY_PATH,
        _ENV_VAR,
    )
    _loaded_from = "generated"
    return key


def get_secret_cipher() -> Fernet:
    """Return the process-wide :class:`Fernet` instance, building it lazily."""
    global _cipher
    if _cipher is not None:
        return _cipher
    with _cipher_lock:
        if _cipher is None:
            _cipher = Fernet(_load_or_generate_key())
    return _cipher


def is_encrypted(value: object) -> bool:
    """Return ``True`` iff *value* looks like one of our ciphertexts."""
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt *plaintext* and return a prefixed, urlsafe-base64 token.

    Re-encrypting an already-encrypted value is a no-op so callers can use
    this idempotently when migrating config files.
    """
    if not isinstance(plaintext, str):
        raise TypeError("encrypt_secret requires a str")
    if is_encrypted(plaintext):
        return plaintext
    if plaintext == "":
        # Empty secrets are common in default configs; leave them as-is so
        # consumers don't have to special-case the empty marker.
        return ""
    token = get_secret_cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_secret(value: str) -> str:
    """Decrypt *value*. If it isn't an encrypted token, return it unchanged.

    This lets callers transparently handle legacy plaintext secrets while
    a migration is in progress.

    Raises:
        ValueError: when the value looks encrypted but cannot be decrypted
            (wrong key, tampered ciphertext, etc.).
    """
    if not isinstance(value, str):
        raise TypeError("decrypt_secret requires a str")
    if not is_encrypted(value):
        return value
    token = value[len(ENCRYPTED_PREFIX):].encode("ascii")
    try:
        return get_secret_cipher().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Failed to decrypt secret: token is invalid or was encrypted "
            "with a different key."
        ) from exc


def rotate_key(new_key: bytes, *, values: Optional[list] = None) -> list:
    """Re-encrypt *values* under *new_key* and switch the process to it.

    Intended for an admin "rotate encryption key" flow. Returns the list of
    re-encrypted values in the same order as the input. Plaintext / non-
    encrypted entries are passed through unchanged.

    The caller is responsible for persisting *new_key* (e.g. updating the
    env var or rewriting ``data/.secret_key``) — this helper only does the
    in-memory swap so the new key is used for subsequent operations.
    """
    global _cipher
    try:
        new_cipher = Fernet(new_key)
    except (ValueError, TypeError) as exc:
        raise ValueError("new_key is not a valid Fernet key") from exc

    out: list = []
    for v in values or []:
        if isinstance(v, str) and is_encrypted(v):
            plain = decrypt_secret(v)
            token = new_cipher.encrypt(plain.encode("utf-8")).decode("ascii")
            out.append(f"{ENCRYPTED_PREFIX}{token}")
        else:
            out.append(v)

    with _cipher_lock:
        _cipher = new_cipher
    return out


def _reset_for_tests() -> None:
    """Drop the cached cipher. **Tests only.**"""
    global _cipher, _loaded_from
    with _cipher_lock:
        _cipher = None
        _loaded_from = None
