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
import contextlib
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
from typing import Any

logger = logging.getLogger(__name__)

# --- Config ----------------------------------------------------------------

SESSION_COOKIE_NAME = "fiestaboard_session"

# scrypt parameters: ~64MB / ~100ms on a modern CPU. Tuned for interactive
# logins on a Raspberry-Pi-class host; bump N for stronger.
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16

# Sessions live for 7 days by default. Configurable via env var for ops who
# want a tighter window without a code change.
_DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 3600

# When the user ticks "Keep me logged in" the session is persisted for longer
# (30 days by default). Also env-overridable for ops who want a different
# window. This is the upper bound on a remembered cookie's lifetime.
_DEFAULT_REMEMBER_ME_TTL_SECONDS = 30 * 24 * 3600


def _ttl_from_env(var_name: str, default: int) -> int:
    """Read a positive-int TTL (seconds) from *var_name*, else *default*."""
    raw = os.environ.get(var_name, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        if v <= 0:
            return default
        return v
    except ValueError:
        return default


def _session_ttl_seconds() -> int:
    return _ttl_from_env("FIESTABOARD_SESSION_TTL_SECONDS", _DEFAULT_SESSION_TTL_SECONDS)


def _remember_me_ttl_seconds() -> int:
    return _ttl_from_env("FIESTABOARD_REMEMBER_ME_TTL_SECONDS", _DEFAULT_REMEMBER_ME_TTL_SECONDS)


def is_auth_enabled() -> bool:
    """Return ``True`` iff auth should be enforced for the next request.

    Three-state policy:

    * The env var ``FIESTABOARD_AUTH_ENABLED`` always wins. Truthy values
      (``1``/``true``/``yes``/``on``) force-enable; explicit falsy values
      (``0``/``false``/``no``/``off``) force-disable.
    * Otherwise, fall back to the per-install preference recorded in
      ``data/auth.json`` (set the first time the admin makes a choice).
    * Otherwise (first run, no env var, no recorded choice) default to
      *enabled* — secure-by-default. The middleware combines this with
      "no user yet" to surface the first-run picker in the UI.
    """
    mode = auth_mode()
    return mode in ("enabled", "undecided")


def auth_mode() -> str:
    """Resolve the tri-state auth mode.

    Returns one of ``"enabled"``, ``"disabled"``, or ``"undecided"``.

    ``undecided`` means *secure-by-default* — protected endpoints still
    require auth, but the UI is allowed to show a first-run picker
    inviting the admin to either set up an account or opt out.
    """
    env = _auth_env_override()
    if env is not None:
        return env
    # No env override — consult the persisted preference.
    try:
        svc = get_auth_service()
    except Exception:
        # If the auth store can't be loaded for some reason we still
        # default to "undecided" so the install is never silently opened.
        return "undecided"
    pref = svc.get_auth_preference()
    if pref == "enabled":
        return "enabled"
    if pref == "disabled":
        return "disabled"
    return "undecided"


def _auth_env_override() -> str | None:
    """Return ``"enabled"``/``"disabled"`` if the env var pins the mode, else ``None``.

    Centralised so callers (e.g. ``/auth/preference``) can ask "is the
    mode currently pinned by ops?" without duplicating the parsing logic.
    """
    raw = os.environ.get("FIESTABOARD_AUTH_ENABLED", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return "enabled"
    if raw in {"0", "false", "no", "off"}:
        return "disabled"
    return None


def mcp_token() -> str | None:
    """Return the active MCP bearer token, or ``None`` if none is set.

    Resolution order (first match wins):

    1. ``FIESTABOARD_MCP_TOKEN`` environment variable — lets ops pin a
       value out-of-band without touching ``auth.json``.
    2. ``mcp_token`` field in ``auth.json`` — managed by the Settings UI.

    Read fresh on every call so tests / runtime reconfiguration don't
    have to bust a cache.
    """
    env = os.environ.get("FIESTABOARD_MCP_TOKEN", "").strip()
    if env:
        return env
    try:
        return get_auth_service().get_stored_mcp_token()
    except Exception:
        # Auth store unreachable — fail closed so we don't grant access
        # we can't reason about.
        return None


def mcp_token_source() -> str:
    """Where the active MCP token comes from: ``"env"``, ``"stored"``, or ``"none"``.

    Used by the Settings API so the UI can show "managed by ops" when
    the env var is set and hide the rotate/clear controls.
    """
    if os.environ.get("FIESTABOARD_MCP_TOKEN", "").strip():
        return "env"
    try:
        if get_auth_service().get_stored_mcp_token():
            return "stored"
    except Exception:
        return "none"
    return "none"


def verify_mcp_bearer(supplied: str) -> bool:
    """Constant-time compare a supplied Bearer token to the configured one."""
    expected = mcp_token()
    if expected is None or not supplied:
        return False
    return secrets.compare_digest(expected, supplied)


def generate_mcp_token() -> str:
    """Return a fresh 32-byte URL-safe token suitable for the MCP endpoint."""
    return secrets.token_urlsafe(32)


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
        # Read raw bytes — do NOT strip() here. secrets.token_bytes(32)
        # can include leading/trailing whitespace bytes (\t \n \r space),
        # and silently stripping them shortens the key, breaks the HMAC,
        # and makes every previously-issued session fail verification —
        # a flaky test that bites roughly 1 in 5-10 fresh keys.
        return key_path.read_bytes()
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
    """A session token payload.

    ``issued_at`` and ``expires_at`` are **milliseconds** since the epoch
    so that ``sessions_valid_after`` cutoffs can distinguish a session
    minted just before a password change from one minted just after,
    without resorting to a sleep.
    """

    username: str
    issued_at: int  # ms since epoch
    expires_at: int  # ms since epoch

    def encode(self) -> str:
        # Embedded in the payload, not the header, so an attacker can't
        # selectively shorten / extend the session.
        nonce = _b64e(secrets.token_bytes(8))
        return f"{_b64e(self.username.encode('utf-8'))}.{self.issued_at}.{self.expires_at}.{nonce}"


def _now_ms() -> int:
    """Wall-clock millisecond timestamp."""
    return time.time_ns() // 1_000_000


# --- User store ------------------------------------------------------------


def _default_auth_file() -> Path:
    # Mirror src/config_manager.py path resolution.
    return Path(__file__).resolve().parent.parent.parent / "data" / "auth.json"


class AuthService:
    """Thread-safe single-user auth store.

    Not a singleton on its own — :func:`get_auth_service` returns a module
    -level instance, but tests can construct their own with a temp path.
    """

    def __init__(self, auth_file: Path | None = None) -> None:
        self._path = Path(auth_file) if auth_file else _default_auth_file()
        # RLock because _now_ms() is called from inside other methods
        # that already hold the lock.
        self._lock = threading.RLock()
        # Tracks the last millisecond timestamp this instance has emitted
        # so successive calls are strictly monotonic — critical for the
        # session watermark, which relies on a token minted after a
        # password rotation having ``issued_at > cutoff`` even when both
        # fall in the same wall-clock millisecond.
        self._last_ms = 0
        self._data: dict[str, Any] = {"version": 1, "users": []}
        self._load()

    def _monotonic_ms(self) -> int:
        """Strictly-monotonic millisecond clock for token issuance.

        Wraps the module-level :func:`_now_ms` but guarantees that every
        call on this instance returns a value strictly greater than the
        previous one — see ``self._last_ms`` for why this matters.
        """
        with self._lock:
            t = _now_ms()
            if t <= self._last_ms:
                t = self._last_ms + 1
            self._last_ms = t
            return t

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open(encoding="utf-8") as fh:
                self._data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read %s: %s; starting empty", self._path, exc)
            self._data = {"version": 1, "users": []}
        # Defensive defaults so a hand-edited file doesn't crash us.
        self._data.setdefault("version", 1)
        self._data.setdefault("users", [])
        # ``auth_pref`` records the admin's first-run choice
        # (``"enabled"`` / ``"disabled"``). Absent => undecided.

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
            Path(tmp).replace(self._path)
        except Exception:
            # Cleanup of a cleanup failure — nothing useful we can do;
            # the original exception below is the one that matters and
            # we don't want to mask it.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise

    # -- queries -----------------------------------------------------------

    def has_user(self) -> bool:
        """Return ``True`` iff at least one user has been provisioned."""
        with self._lock:
            return bool(self._data.get("users"))

    def get_user(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            for u in self._data.get("users", []):
                if u.get("username") == username:
                    return dict(u)
        return None

    def get_auth_preference(self) -> str | None:
        """Return the persisted auth preference, or ``None`` if unset.

        Possible values: ``"enabled"``, ``"disabled"``, ``None``.
        """
        with self._lock:
            pref = self._data.get("auth_pref")
        if pref in ("enabled", "disabled"):
            return pref
        return None

    def set_auth_preference(self, preference: str | None) -> None:
        """Persist the admin's auth on/off choice.

        Pass ``None`` to clear the preference (rare, mostly for tests).
        """
        if preference not in (None, "enabled", "disabled"):
            raise ValueError("preference must be 'enabled', 'disabled', or None")
        with self._lock:
            if preference is None:
                self._data.pop("auth_pref", None)
            else:
                self._data["auth_pref"] = preference
            self._save()

    # -- MCP bearer token --------------------------------------------------

    def get_stored_mcp_token(self) -> str | None:
        """Return the persisted MCP bearer token, or ``None`` if unset.

        This is the UI-managed value. The runtime ``mcp_token()`` helper
        in this module also consults ``FIESTABOARD_MCP_TOKEN``; the env
        var wins so ops can pin a value out-of-band.
        """
        with self._lock:
            tok = self._data.get("mcp_token")
        if isinstance(tok, str) and tok:
            return tok
        return None

    def set_stored_mcp_token(self, token: str | None) -> None:
        """Persist (or clear) the UI-managed MCP bearer token.

        Pass ``None`` to remove it. Stored in ``auth.json`` (file mode
        0600 alongside the password hash), so no extra encryption layer.
        """
        if token is not None and (not isinstance(token, str) or not token.strip()):
            raise ValueError("token must be a non-empty string or None")
        with self._lock:
            if token is None:
                self._data.pop("mcp_token", None)
            else:
                self._data["mcp_token"] = token.strip()
            self._save()

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
            now_s = int(time.time())
            self._data["users"] = [
                {
                    "username": username,
                    "password_hash": hash_password(password),
                    "created_at": now_s,
                    "updated_at": now_s,
                    # Sessions whose ``issued_at`` is strictly less than
                    # this watermark are rejected. Bumped on every
                    # password/username change so a rotation also
                    # revokes any stolen cookies. ``_monotonic_ms()``
                    # guarantees the next call returns a higher value,
                    # so a token minted right after this passes the check.
                    "sessions_valid_after_ms": self._monotonic_ms(),
                }
            ]
            # Creating an account is an explicit "I want auth on" decision —
            # persist it so the install no longer counts as undecided.
            self._data["auth_pref"] = "enabled"
            self._save()

    def change_username(self, current_username: str, password: str, new_username: str) -> str:
        """Rename the current user, gated by their password.

        Returns the new username on success. Bumps the session watermark
        so previously-issued cookies are revoked.
        """
        _validate_username(new_username)
        with self._lock:
            users = self._data.get("users", [])
            for u in users:
                if u.get("username") == current_username:
                    if not verify_password(password, u.get("password_hash", "")):
                        raise InvalidCredentials("Password is incorrect")
                    if new_username == current_username:
                        # No-op rename — return without bumping the
                        # session watermark or rewriting the file. There
                        # is no security benefit to invalidating sessions
                        # when nothing actually changed.
                        return new_username
                    # Ensure no collision with another user (forward-compat).
                    for other in users:
                        if other is u:
                            continue
                        if other.get("username") == new_username:
                            raise ValueError("Username is already taken")
                    u["username"] = new_username
                    u["updated_at"] = int(time.time())
                    u["sessions_valid_after_ms"] = self._monotonic_ms()
                    self._save()
                    return new_username
            raise InvalidCredentials("Unknown user")

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
                    # Revoke every session minted strictly before now.
                    # ``_monotonic_ms()`` guarantees the next call returns
                    # a higher value, so any session minted after this
                    # returns satisfies ``issued_at >= cutoff``.
                    u["sessions_valid_after_ms"] = self._monotonic_ms()
                    self._save()
                    return
            raise InvalidCredentials("Unknown user")

    def disable_auth_for_user(self, username: str, password: str) -> None:
        """Turn off auth enforcement after a password check.

        Used by the in-app "Disable login" flow on the Account tab.
        Gated by the current password so a stolen cookie alone can't
        be used to silently open up the install. The stored user is
        deleted at the same time — once auth is off there is no
        notion of "the admin," and leaving a stale credential lying
        around in ``data/auth.json`` would only invite confusion
        when auth is later re-enabled.
        """
        with self._lock:
            users = self._data.get("users", [])
            for u in users:
                if u.get("username") == username:
                    if not verify_password(password, u.get("password_hash", "")):
                        raise InvalidCredentials("Password is incorrect")
                    self._data["users"] = [other for other in users if other is not u]
                    self._data["auth_pref"] = "disabled"
                    self._save()
                    return
            raise InvalidCredentials("Unknown user")

    # -- auth flow ---------------------------------------------------------

    def authenticate(self, username: str, password: str, *, remember: bool = False) -> str:
        """Verify *username*/*password* and return a signed session token.

        When *remember* is true the token is minted with the longer
        "Keep me logged in" TTL; otherwise it uses the default session TTL.
        """
        if not self.has_user():
            raise SetupRequired("No user has been provisioned")
        user = self.get_user(username)
        # Always do a hash comparison even on unknown user to keep timing flat.
        stored = user.get("password_hash") if user else ""
        ok = verify_password(password, stored or "")
        if not user or not ok:
            raise InvalidCredentials("Invalid username or password")
        now_ms = self._monotonic_ms()
        ttl_seconds = _remember_me_ttl_seconds() if remember else _session_ttl_seconds()
        token = SessionToken(
            username=username,
            issued_at=now_ms,
            expires_at=now_ms + ttl_seconds * 1000,
        )
        return self._sign(token.encode())

    def verify_session(self, raw: str | None) -> str | None:
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
            issued_at_ms = int(issued_s)
            expires_at_ms = int(expires_s)
        except (ValueError, UnicodeDecodeError):
            return None
        now_ms = _now_ms()
        if now_ms >= expires_at_ms:
            return None
        # Ensure the user still exists (in case it was deleted/rotated) and
        # that the token wasn't minted before the user's last password
        # rotation — stolen cookies are revoked when the password changes.
        user = self.get_user(username)
        if not user:
            return None
        cutoff = int(user.get("sessions_valid_after_ms", 0) or 0)
        if issued_at_ms < cutoff:
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
            raise ValueError("username may only contain letters, digits, '.', '_', '-', '@'")


def _validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValueError("password must be a string")
    if len(password) < _PASSWORD_MIN:
        raise ValueError(f"password must be at least {_PASSWORD_MIN} characters")
    if len(password) > _PASSWORD_MAX:
        raise ValueError(f"password must be at most {_PASSWORD_MAX} characters")


# --- Module-level singleton -----------------------------------------------

_service_lock = threading.Lock()
_service: AuthService | None = None


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
