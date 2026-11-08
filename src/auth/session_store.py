"""Transactional, hash-only session registry and device authorization state.

One connection per transaction avoids thread-affinity and stale-connection
issues. BEGIN IMMEDIATE serializes grant consumption, revocation and limits.
The database is private before SQLite first opens it; rollback journals
inherit its permissions. No persistent connection or background thread.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .session_models import SessionRecord

# TVs poll a panel frame every 2 s. "Last shown" is persisted at most once per
# viewer and panel in this window; between writes the poll touches no storage.
PANEL_VIEW_PERSIST_MS = 60_000
_PANEL_VIEW_MEMORY = 4096


class SessionLimit(ValueError):
    pass


def digest_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class SessionStore:
    def __init__(self, path: Path, clock_ms: Callable[[], int] | None = None):
        self.path = path
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        # (session_id, panel_id) -> when this process last persisted that view.
        self._view_writes: dict[tuple[str, str], int] = {}
        self._view_lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(descriptor)
        path.chmod(0o600)
        with self.transaction() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported authentication registry version")
            db.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL, account_generation INTEGER NOT NULL,
                kind TEXT NOT NULL, device_name TEXT NOT NULL, client_id TEXT NOT NULL,
                app_version TEXT NOT NULL, method TEXT NOT NULL, created_ms INTEGER NOT NULL,
                expires_ms INTEGER NOT NULL, last_active_ms INTEGER NOT NULL, revoked_ms INTEGER
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS session_user ON sessions(username)")
            db.execute("""CREATE TABLE IF NOT EXISTS challenges (
                device_digest TEXT PRIMARY KEY, user_digest TEXT UNIQUE NOT NULL,
                client_id TEXT NOT NULL, device_name TEXT NOT NULL, app_version TEXT NOT NULL,
                state TEXT NOT NULL, created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL,
                next_poll_ms INTEGER NOT NULL, interval_seconds INTEGER NOT NULL,
                username TEXT, account_generation INTEGER, approving_session_id TEXT
            )""")
            db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS csrf (
                digest TEXT PRIMARY KEY, session_id TEXT NOT NULL, expires_ms INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS limits (
                key TEXT PRIMARY KEY, started_ms INTEGER NOT NULL, count INTEGER NOT NULL)""")
            # Additive: older builds ignore the table, so user_version stays 1.
            db.execute("""CREATE TABLE IF NOT EXISTS panel_views (
                session_id TEXT NOT NULL, panel_id TEXT NOT NULL, last_shown_ms INTEGER NOT NULL,
                PRIMARY KEY (session_id, panel_id))""")
            # H11 QR pairing offers: digest only, single use, owned by the browser
            # session that created them. Additive, like panel_views.
            db.execute("""CREATE TABLE IF NOT EXISTS pairings (
                id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, username TEXT NOT NULL,
                account_generation INTEGER NOT NULL, creator_session_id TEXT NOT NULL,
                state TEXT NOT NULL, created_ms INTEGER NOT NULL, expires_ms INTEGER NOT NULL,
                claimed_session_id TEXT, device_name TEXT)""")
            # H10b: which session approved a code-signed-in TV, for the phone's
            # "approved by you". A table, not a column: older builds build
            # SessionRecord(**row), so sessions must keep its columns on rollback.
            db.execute("""CREATE TABLE IF NOT EXISTS session_approvals (
                session_id TEXT PRIMARY KEY, approver_session_id TEXT NOT NULL)""")
            db.execute("PRAGMA user_version = 1")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        # mode=rw: deleting the database must not silently create an empty one.
        db = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=rw", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def cleanup(self, db: sqlite3.Connection) -> None:
        now = self.clock_ms()
        db.execute("DELETE FROM sessions WHERE expires_ms <= ?", (now,))
        db.execute("DELETE FROM csrf WHERE expires_ms <= ?", (now,))
        # Keep terminal grant outcomes briefly so an expired code is distinguishable.
        db.execute("DELETE FROM challenges WHERE expires_ms < ?", (now - 600_000,))
        db.execute("DELETE FROM limits WHERE started_ms < ?", (now - 600_000,))
        # Keep finished offers briefly so the web page can still read the outcome.
        db.execute("DELETE FROM pairings WHERE expires_ms < ?", (now - 600_000,))
        db.execute("DELETE FROM session_approvals WHERE session_id NOT IN (SELECT id FROM sessions)")
        db.execute("DELETE FROM panel_views WHERE session_id NOT IN (SELECT id FROM sessions WHERE revoked_ms IS NULL)")

    def create_session(self, record: SessionRecord, *, connection: sqlite3.Connection | None = None) -> None:
        if connection is None:
            with self.transaction() as db:
                self.create_session(record, connection=db)
            return
        self.cleanup(connection)
        count = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE username=? AND revoked_ms IS NULL AND expires_ms>?",
            (record.username, self.clock_ms()),
        ).fetchone()[0]
        if count >= 200:
            raise SessionLimit("Too many signed-in devices. Revoke a device in Settings → Account first.")
        values = asdict(record)
        connection.execute(
            f"INSERT INTO sessions ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",
            tuple(values.values()),
        )

    def find_active(self, digest: str, account_generation: int | None = None) -> SessionRecord | None:
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE digest=? AND revoked_ms IS NULL AND expires_ms>?",
                (digest, self.clock_ms()),
            ).fetchone()
            if row is None or (account_generation is not None and row["account_generation"] != account_generation):
                return None
            now = self.clock_ms()
            if row["last_active_ms"] <= now - 300_000:
                db.execute("UPDATE sessions SET last_active_ms=? WHERE id=?", (now, row["id"]))
            return SessionRecord(**dict(row))

    def revoke_session(self, username: str, session_id: str) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET revoked_ms=? WHERE username=? AND id=? AND revoked_ms IS NULL",
                (self.clock_ms(), username, session_id),
            )
            db.execute(
                "DELETE FROM panel_views WHERE session_id IN (SELECT id FROM sessions WHERE username=? AND id=?)",
                (username, session_id),
            )
            db.execute(
                "UPDATE challenges SET state='cancelled' WHERE approving_session_id=? AND state='approved'",
                (session_id,),
            )
            db.execute(
                "UPDATE pairings SET state='cancelled' WHERE creator_session_id=? AND state='pending'",
                (session_id,),
            )

    def revoke_sessions(self, username: str, except_id: str | None = None) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET revoked_ms=? WHERE username=? AND id!=? AND revoked_ms IS NULL",
                (self.clock_ms(), username, except_id or ""),
            )
            self._drop_revoked_views(db)
            # Challenges begun anonymously belong to this single-account install.
            db.execute("UPDATE challenges SET state='cancelled' WHERE state IN ('pending','approved')")
            # Only offers whose creating browser was just signed out; "Sign out other
            # devices" keeps the QR the current browser is showing.
            db.execute(
                "UPDATE pairings SET state='cancelled' WHERE username=? AND state='pending' AND creator_session_id!=?",
                (username, except_id or ""),
            )

    def list_sessions(self, username: str) -> list[SessionRecord]:
        with self.transaction() as db:
            self.cleanup(db)
            rows = db.execute(
                "SELECT * FROM sessions WHERE username=? AND revoked_ms IS NULL AND expires_ms>? ORDER BY created_ms DESC",
                (username, self.clock_ms()),
            ).fetchall()
            return [SessionRecord(**dict(row)) for row in rows]

    @staticmethod
    def _drop_revoked_views(db: sqlite3.Connection) -> None:
        db.execute("DELETE FROM panel_views WHERE session_id IN (SELECT id FROM sessions WHERE revoked_ms IS NOT NULL)")

    def panel_view_due(self, session_id: str, panel_id: str) -> bool:
        """Whether a view would be persisted now. Memory only; no storage."""
        with self._view_lock:
            last = self._view_writes.get((session_id, panel_id))
        return last is None or self.clock_ms() - last >= PANEL_VIEW_PERSIST_MS

    def record_panel_view(self, session_id: str, panel_id: str) -> bool:
        """Note that a signed-in viewer fetched *panel_id*'s frame just now.

        Throttled in memory to one write per viewer and panel every
        ``PANEL_VIEW_PERSIST_MS``; a throttled call opens no transaction.
        Returns whether this call persisted. A failed write releases its slot
        so the next poll retries.
        """
        key, now = (session_id, panel_id), self.clock_ms()
        with self._view_lock:
            last = self._view_writes.get(key)
            if last is not None and now - last < PANEL_VIEW_PERSIST_MS:
                return False
            if len(self._view_writes) >= _PANEL_VIEW_MEMORY:
                self._view_writes.clear()
            self._view_writes[key] = now
        try:
            self._write_panel_view(session_id, panel_id, now)
        except BaseException:
            with self._view_lock:
                if self._view_writes.get(key) == now:
                    del self._view_writes[key]
            raise
        return True

    def _write_panel_view(self, session_id: str, panel_id: str, now: int) -> None:
        with self.transaction() as db:
            # Only a live session may own a row, so a view racing its own
            # revocation cannot resurrect the viewer.
            db.execute(
                """INSERT INTO panel_views (session_id, panel_id, last_shown_ms)
                SELECT id, ?, ? FROM sessions WHERE id=? AND revoked_ms IS NULL AND expires_ms>?
                ON CONFLICT(session_id, panel_id) DO UPDATE SET last_shown_ms=excluded.last_shown_ms""",
                (panel_id, now, session_id, now),
            )

    def approved_by(self, approver_session_id: str) -> set[str]:
        """Ids of the sessions whose sign-in code *approver_session_id* approved."""
        with self.transaction() as db:
            rows = db.execute(
                "SELECT session_id FROM session_approvals WHERE approver_session_id=?", (approver_session_id,)
            ).fetchall()
        return {row["session_id"] for row in rows}

    def panel_views(self, username: str) -> dict[str, list[tuple[str, int]]]:
        """Live sessions' last-shown panels, newest first, keyed by session id."""
        with self.transaction() as db:
            rows = db.execute(
                """SELECT v.session_id, v.panel_id, v.last_shown_ms FROM panel_views v
                JOIN sessions s ON s.id = v.session_id
                WHERE s.username=? AND s.revoked_ms IS NULL AND s.expires_ms>?
                ORDER BY v.last_shown_ms DESC, v.panel_id""",
                (username, self.clock_ms()),
            ).fetchall()
        views: dict[str, list[tuple[str, int]]] = {}
        for row in rows:
            views.setdefault(row["session_id"], []).append((row["panel_id"], row["last_shown_ms"]))
        return views

    def update_metadata(self, token: str, *, device_name: str, kind: str) -> None:
        with self.transaction() as db:
            db.execute(
                "UPDATE sessions SET device_name=?, kind=? WHERE digest=?",
                (device_name[:100], kind, digest_secret(token)),
            )

    @property
    def enrollment_enabled(self) -> bool:
        with self.transaction() as db:
            row = db.execute("SELECT value FROM settings WHERE key='tv_enabled'").fetchone()
            # The beta release channel gates rollout; device sign-in needs no opt-in.
            # One switch, labelled "Device sign-in", gates TVs and phones; the key stays
            # tv_enabled so existing installs keep an administrator's choice.
            # Preserve an administrator's explicit disable across upgrades.
            return row is None or row["value"] == "true"

    def set_enrollment(self, enabled: bool) -> None:
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('tv_enabled', ?)", ("true" if enabled else "false",))
            if not enabled:
                db.execute("UPDATE challenges SET state='cancelled' WHERE state IN ('pending','approved')")
                db.execute("UPDATE pairings SET state='cancelled' WHERE state='pending'")

    def issue_csrf(self, session_id: str) -> str:
        value = secrets.token_urlsafe(32)
        with self.transaction() as db:
            self.cleanup(db)
            db.execute(
                """DELETE FROM csrf WHERE session_id=? AND digest NOT IN
                (SELECT digest FROM csrf WHERE session_id=? ORDER BY expires_ms DESC LIMIT 9)""",
                (session_id, session_id),
            )
            db.execute(
                "INSERT INTO csrf VALUES (?, ?, ?)", (digest_secret(value), session_id, self.clock_ms() + 600_000)
            )
        return value

    def verify_csrf(self, session_id: str, nonce: str) -> bool:
        if not nonce or len(nonce) > 128:
            return False
        with self.transaction() as db:
            row = db.execute(
                "SELECT digest FROM csrf WHERE digest=? AND session_id=? AND expires_ms>?",
                (digest_secret(nonce), session_id, self.clock_ms()),
            ).fetchone()
        return row is not None
