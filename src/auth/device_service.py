"""Scoped native credentials and transactional, one-use TV approvals."""

from __future__ import annotations

import secrets
import sqlite3

from .device_models import AuthFlowError, DeviceChallenge, DeviceMetadata, DeviceTokenResult, PendingDevice
from .service import AuthService, auth_mode
from .session_models import SessionRecord
from .session_store import digest_secret

ALPHABET = "BCDFGHJKLMNPQRSTVWXYZ23456789"
TV_TOKEN_SECONDS = 365 * 24 * 3600


def normalize_code(code: str) -> str:
    value = code.upper().replace("-", "").replace(" ", "")
    if len(value) != 8 or any(c not in ALPHABET for c in value):
        raise AuthFlowError("invalid_grant", "That code is invalid or no longer available.")
    return value


class DeviceService:
    def __init__(self, auth: AuthService):
        self.auth, self.store = auth, auth.sessions

    def require_enrollment(self) -> None:
        if auth_mode() != "enabled" or not self.auth.has_user():
            raise AuthFlowError("setup_required", "Finish account setup and enable sign-in in the web portal.", 409)
        if not self.store.enrollment_enabled:
            raise AuthFlowError("feature_disabled", "TV sign-in is disabled. Enable it in Settings → Account.", 403)

    def limit(self, key: str, maximum: int) -> None:
        now = self.store.clock_ms()
        with self.store.transaction() as db:
            self.store.cleanup(db)
            key = digest_secret(key)
            row = db.execute("SELECT * FROM limits WHERE key=?", (key,)).fetchone()
            if row and row["started_ms"] > now - 60_000:
                if row["count"] >= maximum:
                    raise AuthFlowError("rate_limited", "Too many attempts. Try again in a minute.", 429, 60)
                db.execute("UPDATE limits SET count=count+1 WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO limits VALUES (?, ?, 1)", (key, now))

    def authorize(self, metadata: DeviceMetadata, source: str) -> DeviceChallenge:
        self.require_enrollment()
        self.limit("start:" + source, 5)
        now = self.store.clock_ms()
        with self.store.transaction() as db:
            self._enrollment_in_transaction(db)
            self.store.cleanup(db)
            count = db.execute(
                "SELECT COUNT(*) FROM challenges WHERE state IN ('pending','approved') AND expires_ms>?", (now,)
            ).fetchone()[0]
            if count >= 100:
                raise AuthFlowError("rate_limited", "Too many pending sign-ins. Try again shortly.", 429, 60)
            for _ in range(10):
                user_code = "".join(secrets.choice(ALPHABET) for _ in range(8))
                device_code = secrets.token_urlsafe(32)
                try:
                    db.execute(
                        """INSERT INTO challenges
                        (device_digest,user_digest,client_id,device_name,app_version,state,created_ms,expires_ms,
                         next_poll_ms,interval_seconds) VALUES (?,?,?,?,?,'pending',?,?,?,5)""",
                        (
                            digest_secret(device_code),
                            digest_secret(user_code),
                            metadata.client_id,
                            metadata.device_name,
                            metadata.app_version,
                            now,
                            now + 600_000,
                            now,
                        ),
                    )
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                raise AuthFlowError("temporarily_unavailable", "Could not create a code. Try again.", 503)
        display = user_code[:4] + "-" + user_code[4:]
        return DeviceChallenge(
            device_code=device_code, user_code=display, verification_path_complete="/activate?user_code=" + display
        )

    @staticmethod
    def _enrollment_in_transaction(db: sqlite3.Connection) -> None:
        row = db.execute("SELECT value FROM settings WHERE key='tv_enabled'").fetchone()
        if not row or row["value"] != "true":
            raise AuthFlowError("feature_disabled", "TV sign-in is disabled.", 403)

    def _challenge_for_user(self, db: sqlite3.Connection, code: str) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM challenges WHERE user_digest=?", (digest_secret(normalize_code(code)),)
        ).fetchone()
        if row is None or row["state"] != "pending":
            raise AuthFlowError("invalid_grant", "That code is invalid or no longer available.")
        if row["expires_ms"] <= self.store.clock_ms():
            raise AuthFlowError("expired_token", "That code expired. Request a new code on the TV.")
        return row

    def inspect(self, code: str) -> PendingDevice:
        self.require_enrollment()
        with self.store.transaction() as db:
            row = self._challenge_for_user(db, code)
            normalized = normalize_code(code)
            return PendingDevice(
                user_code=normalized[:4] + "-" + normalized[4:],
                client_id=row["client_id"],
                device_name=row["device_name"],
                app_version=row["app_version"],
                expires_in=max(0, (row["expires_ms"] - self.store.clock_ms()) // 1000),
            )

    def decide(self, code: str, browser: SessionRecord, approve: bool) -> None:
        self.require_enrollment()
        with self.auth._lock, self.store.transaction() as db:
            self._enrollment_in_transaction(db)
            self._require_active_browser(db, browser.id, browser.username, browser.account_generation)
            row = self._challenge_for_user(db, code)
            db.execute(
                """UPDATE challenges SET state=?, username=?, account_generation=?, approving_session_id=?
                          WHERE device_digest=?""",
                (
                    "approved" if approve else "denied",
                    browser.username,
                    browser.account_generation,
                    browser.id,
                    row["device_digest"],
                ),
            )

    def _require_active_browser(self, db, session_id: str, username: str, generation: int) -> None:
        user = self.auth.get_user(username)
        row = db.execute(
            "SELECT * FROM sessions WHERE id=? AND revoked_ms IS NULL AND expires_ms>?",
            (session_id, self.store.clock_ms()),
        ).fetchone()
        if (
            not row
            or row["kind"] not in ("browser", "legacy")
            or not user
            or user.get("sessions_valid_after_ms", 0) != generation
            or row["account_generation"] != generation
        ):
            raise AuthFlowError("invalid_grant", "The approving sign-in is no longer valid. Request a new code.")

    def _issue(self, db, username: str, generation: int, metadata: DeviceMetadata, method: str) -> DeviceTokenResult:
        now = self.store.clock_ms()
        token, session_id = "fb_tv_" + secrets.token_urlsafe(32), secrets.token_urlsafe(16)
        self.store.create_session(
            SessionRecord(
                id=session_id,
                digest=digest_secret(token),
                username=username,
                account_generation=generation,
                kind="tv",
                device_name=metadata.device_name,
                client_id=metadata.client_id,
                app_version=metadata.app_version,
                method=method,
                created_ms=now,
                expires_ms=now + TV_TOKEN_SECONDS * 1000,
                last_active_ms=now,
            ),
            connection=db,
        )
        return DeviceTokenResult(access_token=token, session_id=session_id)

    def exchange(self, code: str, client_id: str) -> DeviceTokenResult:
        self.require_enrollment()
        error = None
        result = None
        with self.auth._lock, self.store.transaction() as db:
            self._enrollment_in_transaction(db)
            row = db.execute("SELECT * FROM challenges WHERE device_digest=?", (digest_secret(code),)).fetchone()
            if not row or row["client_id"] != client_id or row["state"] in ("consumed", "cancelled"):
                raise AuthFlowError("invalid_grant", "That sign-in is no longer available. Request a new code.")
            now = self.store.clock_ms()
            if now >= row["expires_ms"]:
                raise AuthFlowError("expired_token", "That code expired. Request a new code.")
            if row["state"] == "denied":
                raise AuthFlowError("access_denied", "Sign-in was declined in the web portal.")
            if now < row["next_poll_ms"]:
                interval = row["interval_seconds"] + 5
                db.execute(
                    "UPDATE challenges SET interval_seconds=?, next_poll_ms=? WHERE device_digest=?",
                    (interval, now + interval * 1000, row["device_digest"]),
                )
                error = AuthFlowError("slow_down", "Wait longer before checking this code again.")
            else:
                db.execute(
                    "UPDATE challenges SET next_poll_ms=? WHERE device_digest=?",
                    (now + row["interval_seconds"] * 1000, row["device_digest"]),
                )
                if row["state"] == "pending":
                    error = AuthFlowError("authorization_pending", "Waiting for approval in the web portal.")
                else:
                    self._require_active_browser(
                        db, row["approving_session_id"], row["username"], row["account_generation"]
                    )
                    metadata = DeviceMetadata(
                        client_id=row["client_id"], device_name=row["device_name"], app_version=row["app_version"]
                    )
                    result = self._issue(db, row["username"], row["account_generation"], metadata, "device_code")
                    db.execute("UPDATE challenges SET state='consumed' WHERE device_digest=?", (row["device_digest"],))
        # Poll timing is persisted even when the protocol response is an error.
        if error:
            raise error
        return result

    def login(self, username: str, password: str, metadata: DeviceMetadata) -> DeviceTokenResult:
        self.require_enrollment()
        with self.auth._lock:
            user = self.auth.verify_credentials(username, password)
            with self.store.transaction() as db:
                self._enrollment_in_transaction(db)
                return self._issue(db, username, user.get("sessions_valid_after_ms", 0), metadata, "password")

    def cancel(self, code: str) -> None:
        with self.store.transaction() as db:
            db.execute(
                "UPDATE challenges SET state='cancelled' WHERE device_digest=? AND state IN ('pending','approved')",
                (digest_secret(code),),
            )

    def authenticate_tv(self, token: str) -> SessionRecord | None:
        if not token.startswith("fb_tv_") or len(token) > 128:
            return None
        with self.auth._lock:
            row = self.store.find_active(digest_secret(token))
            if not row or row.kind != "tv":
                return None
            user = self.auth.get_user(row.username)
            if not user or user.get("sessions_valid_after_ms", 0) != row.account_generation:
                return None
            return row
