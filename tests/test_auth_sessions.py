"""Revocation is a server-side property, including across restarts."""

import hashlib
import sqlite3

import pytest

from src.auth.service import AuthService


@pytest.fixture
def service(tmp_path):
    svc = AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", "correct-password")
    return svc


def test_revoked_cookie_fails_even_with_valid_signature(service):
    token = service.authenticate("admin", "correct-password")
    assert service.verify_session(token) == "admin"
    session = service.resolve_browser_session(token)
    service.sessions.revoke_session("admin", session.id)
    assert service.verify_session(token) is None
    restarted = AuthService(service._path)
    assert restarted.verify_session(token) is None


def test_missing_registry_row_fails_closed(service):
    token = service.authenticate("admin", "correct-password")
    with sqlite3.connect(service._path.parent / "auth_sessions.sqlite3") as db:
        db.execute("DELETE FROM sessions")
    assert service.verify_session(token) is None


def test_revoke_others_preserves_current(service):
    current = service.authenticate("admin", "correct-password")
    other = service.authenticate("admin", "correct-password")
    session = service.resolve_browser_session(current)
    service.sessions.revoke_sessions("admin", except_id=session.id)
    assert service.verify_session(current) == "admin"
    assert service.verify_session(other) is None


def test_storage_never_contains_raw_cookie(service):
    token = service.authenticate("admin", "correct-password")
    with sqlite3.connect(service._path.parent / "auth_sessions.sqlite3") as db:
        values = repr(db.execute("SELECT * FROM sessions").fetchall())
    assert token not in values
    assert hashlib.sha256(token.encode()).hexdigest() in values


def test_session_survives_normal_restart(service):
    token = service.authenticate("admin", "correct-password")
    restarted = AuthService(service._path)
    assert restarted.verify_session(token) == "admin"


def test_sign_out_everywhere_invalidates_all(service):
    token = service.authenticate("admin", "correct-password")
    before = service.get_user("admin")["sessions_valid_after_ms"]
    service.invalidate_all_sessions("admin")
    assert service.get_user("admin")["sessions_valid_after_ms"] > before
    assert service.verify_session(token) is None
    assert service.verify_session(service.authenticate("admin", "correct-password")) == "admin"


def test_last_active_throttles_writes(service, monkeypatch):
    from src.auth.session_store import digest_secret

    token = service.authenticate("admin", "correct-password")
    row = service.resolve_browser_session(token)
    monkeypatch.setattr(service.sessions, "clock_ms", lambda: row.created_ms + 299_999)
    service.sessions.find_active(digest_secret(token))
    assert service.sessions.list_sessions("admin")[0].last_active_ms == row.created_ms
    monkeypatch.setattr(service.sessions, "clock_ms", lambda: row.created_ms + 300_000)
    service.sessions.find_active(digest_secret(token))
    assert service.sessions.list_sessions("admin")[0].last_active_ms == row.created_ms + 300_000


def test_logout_invalidates_copied_cookie(service, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.auth import service as module

    monkeypatch.setattr(module, "_service", service)
    client = TestClient(app)
    token = service.authenticate("admin", "correct-password")
    client.cookies.set("fiestaboard_session", token)
    assert client.post("/auth/logout").status_code == 200
    assert service.verify_session(token) is None
