"""Private transactional push storage, deliberately outside every export allowlist."""

import base64
import fcntl
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.paths import get_data_dir

from .models import PushSubscription


class PushConflict(ValueError):
    pass


class PushLimit(ValueError):
    pass


class PushStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        # Serialize first creation across processes as well as threads. An empty
        # existing file is corruption, never permission to rotate the VAPID key.
        fd = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            created = not path.exists()
            if created:
                private_fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                os.close(private_fd)
            elif path.is_symlink() or path.stat().st_size == 0:
                raise ValueError("Push storage unavailable")
            path.chmod(0o600)
            with self.transaction() as db:
                if created:
                    db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    db.execute("""CREATE TABLE preferences (
                        username TEXT NOT NULL, generation INTEGER NOT NULL, enabled INTEGER NOT NULL,
                        revision TEXT NOT NULL, PRIMARY KEY(username, generation))""")
                    db.execute("""CREATE TABLE subscriptions (
                        session_id TEXT PRIMARY KEY, username TEXT NOT NULL, generation INTEGER NOT NULL,
                        endpoint TEXT UNIQUE NOT NULL, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
                        enabled INTEGER NOT NULL, expires_ms INTEGER, revision TEXT NOT NULL,
                        test_after_ms INTEGER NOT NULL DEFAULT 0)""")
                    key = ec.generate_private_key(ec.SECP256R1())
                    der = key.private_bytes(
                        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
                    )
                    db.execute("INSERT INTO metadata VALUES ('vapid_private', ?)", (base64.b64encode(der).decode(),))
                    db.execute("PRAGMA user_version=1")
                if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("Push storage unavailable")
                self._read_key(db)
                db.execute("""CREATE TABLE IF NOT EXISTS test_limits (
                    session_id TEXT PRIMARY KEY, after_ms INTEGER NOT NULL)""")
                # Additive migration from the enrollment-row cooldown: preserve
                # existing reservations, including across restart/rollback.
                db.execute("""INSERT OR IGNORE INTO test_limits
                    SELECT session_id,test_after_ms FROM subscriptions WHERE test_after_ms>0""")
        finally:
            os.close(fd)

    @contextmanager
    def transaction(self):
        # Missing storage after startup fails closed, rather than creating keys.
        db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=rw", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _read_key(db):
        try:
            value = db.execute("SELECT value FROM metadata WHERE key='vapid_private'").fetchone()[0]
            key = serialization.load_der_private_key(base64.b64decode(value, validate=True), password=None)
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
                raise ValueError
            return key
        except (ValueError, TypeError, IndexError):
            raise ValueError("Push storage unavailable") from None

    @property
    def private_key(self):
        with self.transaction() as db:
            return self._read_key(db)

    @property
    def public_key(self):
        raw = self.private_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    def status(self, session):
        with self.transaction() as db:
            pref = db.execute(
                "SELECT enabled FROM preferences WHERE username=? AND generation=?",
                (session.username, session.account_generation),
            ).fetchone()
            row = db.execute(
                "SELECT enabled,expires_ms FROM subscriptions WHERE session_id=? AND username=? AND generation=?",
                (session.id, session.username, session.account_generation),
            ).fetchone()
        return {
            "user_enabled": bool(pref and pref[0]),
            "device_enabled": bool(row and row[0]),
            "subscribed": bool(row),
            "expiration_time": row[1] if row else None,
        }

    def set_user_enabled(self, session, enabled: bool):
        with self.transaction() as db:
            db.execute(
                """INSERT INTO preferences VALUES (?,?,?,?) ON CONFLICT(username,generation)
                DO UPDATE SET enabled=excluded.enabled,revision=excluded.revision
                WHERE preferences.enabled != excluded.enabled""",
                (session.username, session.account_generation, enabled, secrets.token_hex(16)),
            )

    def subscribe(self, session, payload: PushSubscription):
        sub = payload.subscription
        if sub.expirationTime is not None and sub.expirationTime <= time.time_ns() // 1_000_000:
            raise ValueError("Subscription has expired")
        with self.transaction() as db:
            owner = db.execute("SELECT session_id FROM subscriptions WHERE endpoint=?", (sub.endpoint,)).fetchone()
            if owner and owner[0] != session.id:
                raise PushConflict("Subscription is already registered")
            existing = db.execute("SELECT 1 FROM subscriptions WHERE session_id=?", (session.id,)).fetchone()
            if not existing and db.execute("SELECT count(*) FROM subscriptions").fetchone()[0] >= 100:
                raise PushLimit("Push subscription limit reached")
            if (
                not existing
                and db.execute("SELECT count(*) FROM subscriptions WHERE username=?", (session.username,)).fetchone()[0]
                >= 20
            ):
                raise PushLimit("Push subscription limit reached")
            db.execute(
                """INSERT INTO subscriptions
                (session_id,username,generation,endpoint,p256dh,auth,enabled,expires_ms,revision)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
                endpoint=excluded.endpoint,p256dh=excluded.p256dh,auth=excluded.auth,
                enabled=excluded.enabled,expires_ms=excluded.expires_ms,revision=excluded.revision""",
                (
                    session.id,
                    session.username,
                    session.account_generation,
                    sub.endpoint,
                    sub.keys.p256dh,
                    sub.keys.auth,
                    payload.enabled,
                    sub.expirationTime,
                    secrets.token_hex(16),
                ),
            )

    def unsubscribe(self, session):
        with self.transaction() as db:
            db.execute(
                "DELETE FROM subscriptions WHERE session_id=? AND username=? AND generation=?",
                (session.id, session.username, session.account_generation),
            )

    def prune(self, username, active_sessions):
        """Reclaim expired and signed-out devices before applying capacity limits."""
        live = {(s.id, s.account_generation) for s in active_sessions if s.kind == "browser"}
        with self.transaction() as db:
            db.execute("DELETE FROM subscriptions WHERE expires_ms<=?", (time.time_ns() // 1_000_000,))
            for row in db.execute("SELECT session_id,generation FROM subscriptions WHERE username=?", (username,)):
                if (row[0], row[1]) not in live:
                    db.execute("DELETE FROM subscriptions WHERE session_id=?", (row[0],))

    def owners(self):
        with self.transaction() as db:
            return [row[0] for row in db.execute("SELECT DISTINCT username FROM subscriptions")]

    def candidates(self, username):
        with self.transaction() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT s.*,p.revision AS user_revision
                FROM subscriptions s JOIN preferences p ON s.username=p.username AND s.generation=p.generation
                WHERE s.username=? AND s.enabled=1 AND p.enabled=1 LIMIT 20""",
                    (username,),
                )
            ]

    def eligible(self, row):
        return any(
            r["session_id"] == row["session_id"]
            and r["revision"] == row["revision"]
            and r["user_revision"] == row["user_revision"]
            for r in self.candidates(row["username"])
        )

    def delete_if_current(self, row):
        with self.transaction() as db:
            return bool(
                db.execute(
                    "DELETE FROM subscriptions WHERE session_id=? AND revision=?", (row["session_id"], row["revision"])
                ).rowcount
            )

    def reserve_test(self, session, now_ms):
        with self.transaction() as db:
            db.execute("DELETE FROM test_limits WHERE after_ms<=?", (now_ms,))
            return bool(
                db.execute(
                    """INSERT INTO test_limits VALUES (?,?) ON CONFLICT(session_id)
                    DO UPDATE SET after_ms=excluded.after_ms WHERE test_limits.after_ms<=?""",
                    (session.id, now_ms + 60_000, now_ms),
                ).rowcount
            )


_store = None
_guard = threading.Lock()


def get_push_store():
    global _store
    path = get_data_dir() / "web-push.sqlite3"
    with _guard:
        if _store is None or _store.path != path:
            _store = PushStore(path)
        return _store
