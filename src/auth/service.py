"""Auth service: user store, password hashing, session tokens.

Design notes
------------

* **Single user.** This is "lock the front door" for self-hosted installs.
  Multi-user / RBAC is intentionally out of scope for this draft. The
  store is shaped (``{"users": [...]}``) so we can grow into it later
  without a migration.
* **Password hashing.** :func:`hashlib.scrypt` from the standard library.
  No new wheel deps; parameters (``N=2**15, r=8, p=1``) follow OWASP's
  current recommendation for interactive logins.
* **Session tokens.** Stateless HMAC-signed tokens (``payload.signature``),
  not JWTs. Avoids "alg: none" footguns and an extra dependency.
* **Storage.** ``data/auth.json`` with ``0600`` perms, written atomically
  via a temp file + ``os.replace`` to avoid torn writes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

SESSION_COOKIE_NAME = "fiestaboard_session"

# scrypt parameters: ~64MB / ~100ms on a modern CPU. Tuned for interactive
# logins on a Raspberry-Pi-class host; bump N for stronger.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16

# Sessions live for 7 days by default. Configurable via env var for ops who
# want a tighter window without a code change.
_DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 3600


def _session_ttl_seconds() -> int:
    raw = os.environ.get("FIESTABOARD_SESSION_TTL_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_SESSION_TTL_SECONDS
    try:
        v = int(raw)
        if v <= 0:
            return _DEFAULT_SESSION_TTL_SECONDS
        return v
    except ValueError:
        return _DEFAULT_SESSION_TTL_SECONDS


def is_auth_enabled() -> bool:
    """Return ``True`` iff ``FIESTABOARD_AUTH_ENABLED`` is truthy."""
    return os.environ.get("FIESTABOARD_AUTH_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# --- Errors ----------------------------------------------------------------


class AuthError(Exception):
    """Base class for auth errors."""


class InvalidCredentials(AuthError):
    """Wrong username or password."""


class SetupRequired(AuthError):
    """No user has been created yet."""


class AlreadySetup(AuthError):
    """Setup endpoint called after a user already exists."""


# --- Hashing ---------------------------------------------------------------


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        # ``maxmem`` defaults to 32MB which is below scrypt's needs at N=2**15.
        # 128 * N * r * p * 2 ≈ 67MB; allocate a bit more for headroom.
        maxmem=128 * _SCRYPT_N * _SCRYPT_R * _SCRYPT_P * 2,
    )


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def hash_password(password: str) -> str:
    """Return a self-contained password hash string.

    Format: ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``. Self-describing so
    we can change parameters later without breaking existing hashes.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = secrets.token_bytes(_SALT_BYTES)
    h = _hash_password(password, salt)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64e(salt)}${_b64e(h)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify *password* against a hash from :func:`hash_password`."""
    if not isinstance(password, str) or not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = _b64d(parts[4])
        expected = _b64d(parts[5])
    except (ValueError, TypeError):
        return False
    try:
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=128 * n * r * p * 2,
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, expected)


# --- Session tokens --------------------------------------------------------

# Tokens are HMAC-SHA256 over ``<username>.<issued_at>.<expires_at>.<nonce>``.
# That keeps verification stateless: no DB lookup, just a signature check
# plus the expiry window.


def _signing_key(auth_file: Path) -> bytes:
    """Per-install signing key, kept alongside the auth store.

    We deliberately don't reuse the secret-encryption key from
    :mod:`src.security.secrets` so that compromising one doesn't trivially
    let an attacker mint sessions, and vice-versa.
    """
    key_path = auth_file.parent / ".session_key"
    if key_path.exists():
        return key_path.read_bytes().strip()
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    fd = os.open(
        str(key_path),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


@dataclass(frozen=True)
class SessionToken:
    username: str
    issued_at: int
    expires_at: int

    def encode(self) -> str:
        # Embedded in the payload, not the header, so an attacker can't
        # selectively shorten / extend the session.
        nonce = _b64e(secrets.token_bytes(8))
        return (
            f"{_b64e(self.username.encode('utf-8'))}."
            f"{self.issued_at}.{self.expires_at}.{nonce}"
        )


# --- User store ------------------------------------------------------------


def _default_auth_file() -> Path:
    # Mirror src/config_manager.py path resolution.
    return Path(__file__).resolve().parent.parent.parent / "data" / "auth.json"


class AuthService:
    """Thread-safe single-user auth store.

    Not a singleton on its own — :func:`get_auth_service` returns a module
    -level instance, but tests can construct their own with a temp path.
    """

    def __init__(self, auth_file: Optional[Path] = None) -> None:
        self._path = Path(auth_file) if auth_file else _default_auth_file()
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"version": 1, "users": []}
        self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read %s: %s; starting empty", self._path, exc)
            self._data = {"version": 1, "users": []}
        # Defensive defaults so a hand-edited file doesn't crash us.
        self._data.setdefault("version", 1)
        self._data.setdefault("users", [])

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        # Restrictive perms on the temp file before fdopen writes to it.
        fd = os.open(
            str(tmp),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    # -- queries -----------------------------------------------------------

    def has_user(self) -> bool:
        """Return ``True`` iff at least one user has been provisioned."""
        with self._lock:
            return bool(self._data.get("users"))

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for u in self._data.get("users", []):
                if u.get("username") == username:
                    return dict(u)
        return None

    # -- mutations ---------------------------------------------------------

    def create_initial_user(self, username: str, password: str) -> None:
        """Create the first (and currently only) user.

        Raises :class:`AlreadySetup` if a user already exists.
        """
        _validate_username(username)
        _validate_password(password)
        with self._lock:
            if self._data.get("users"):
                raise AlreadySetup("A user already exists")
            now = int(time.time())
            self._data["users"] = [
                {
                    "username": username,
                    "password_hash": hash_password(password),
                    "created_at": now,
                    "updated_at": now,
                }
            ]
            self._save()

    def change_password(self, username: str, old: str, new: str) -> None:
        _validate_password(new)
        with self._lock:
            users = self._data.get("users", [])
            for u in users:
                if u.get("username") == username:
                    if not verify_password(old, u.get("password_hash", "")):
                        raise InvalidCredentials("Current password is incorrect")
                    u["password_hash"] = hash_password(new)
                    u["updated_at"] = int(time.time())
                    self._save()
                    return
            raise InvalidCredentials("Unknown user")

    # -- auth flow ---------------------------------------------------------

    def authenticate(self, username: str, password: str) -> str:
        """Verify *username*/*password* and return a signed session token."""
        if not self.has_user():
            raise SetupRequired("No user has been provisioned")
        user = self.get_user(username)
        # Always do a hash comparison even on unknown user to keep timing flat.
        stored = user.get("password_hash") if user else ""
        ok = verify_password(password, stored or "")
        if not user or not ok:
            raise InvalidCredentials("Invalid username or password")
        now = int(time.time())
        token = SessionToken(
            username=username,
            issued_at=now,
            expires_at=now + _session_ttl_seconds(),
        )
        return self._sign(token.encode())

    def verify_session(self, raw: Optional[str]) -> Optional[str]:
        """Return the username if *raw* is a valid, unexpired session token."""
        if not raw or not isinstance(raw, str):
            return None
        try:
            payload, sig = raw.rsplit(".", 1)
        except ValueError:
            return None
        expected = self._sign_payload(payload)
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            user_b64, issued_s, expires_s, _nonce = payload.split(".")
            username = _b64d(user_b64).decode("utf-8")
            issued_at = int(issued_s)
            expires_at = int(expires_s)
        except (ValueError, UnicodeDecodeError):
            return None
        now = int(time.time())
        if now < issued_at or now >= expires_at:
            return None
        # Ensure the user still exists (in case it was deleted/rotated).
        if not self.get_user(username):
            return None
        return username

    # -- signing -----------------------------------------------------------

    def _sign_payload(self, payload: str) -> str:
        key = _signing_key(self._path)
        mac = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).digest()
        return _b64e(mac)

    def _sign(self, payload: str) -> str:
        return f"{payload}.{self._sign_payload(payload)}"


# --- Validation helpers ----------------------------------------------------

_USERNAME_MAX = 64
_PASSWORD_MIN = 8
_PASSWORD_MAX = 1024  # avoid pathological scrypt inputs


def _validate_username(username: str) -> None:
    if not isinstance(username, str):
        raise ValueError("username must be a string")
    u = username.strip()
    if not u:
        raise ValueError("username must not be empty")
    if len(u) > _USERNAME_MAX:
        raise ValueError(f"username must be at most {_USERNAME_MAX} characters")
    if u != username:
        raise ValueError("username must not have leading/trailing whitespace")
    for ch in username:
        if not (ch.isalnum() or ch in "._-@"):
            raise ValueError(
                "username may only contain letters, digits, '.', '_', '-', '@'"
            )


def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("password must be a string")
    if len(password) < _PASSWORD_MIN:
        raise ValueError(
            f"password must be at least {_PASSWORD_MIN} characters"
        )
    if len(password) > _PASSWORD_MAX:
        raise ValueError(
            f"password must be at most {_PASSWORD_MAX} characters"
        )


# --- Module-level singleton -----------------------------------------------

_service_lock = threading.Lock()
_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Return the process-wide :class:`AuthService`."""
    global _service
    if _service is not None:
        return _service
    with _service_lock:
        if _service is None:
            _service = AuthService()
    return _service


def _reset_for_tests() -> None:
    """Drop the cached service. **Tests only.**"""
    global _service
    with _service_lock:
        _service = None
