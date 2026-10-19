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


def test_unset_tv_sign_in_defaults_on_after_restart(service):
    # Earlier beta registries never wrote a setting for the default-off state.
    # They must gain the new default without a separate opt-in or migration.
    with service.sessions.transaction() as db:
        assert db.execute("SELECT value FROM settings WHERE key='tv_enabled'").fetchone() is None
    assert AuthService(service._path).sessions.enrollment_enabled is True


def test_explicit_tv_sign_in_disable_survives_restart(service):
    service.sessions.set_enrollment(False)
    assert AuthService(service._path).sessions.enrollment_enabled is False


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


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [("/private", "GET"), ("/auth/status", "GET"), ("/auth/logout", "POST")])
async def test_slow_registry_lookup_does_not_block_other_requests(service, monkeypatch, path, method):
    """Another request must run while credential storage waits on disk/locks."""
    import asyncio
    import threading

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.auth import service as module
    from src.auth.middleware import AuthMiddleware
    from src.auth.routes import router

    monkeypatch.setattr(module, "_service", service)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    token = service.authenticate("admin", "correct-password")
    entered, release = threading.Event(), threading.Event()
    lookup = service.sessions.find_active
    unblocked_by_other_request = []

    def slow_lookup(*args, **kwargs):
        entered.set()
        unblocked_by_other_request.append(release.wait(timeout=1))
        return lookup(*args, **kwargs)

    monkeypatch.setattr(service.sessions, "find_active", slow_lookup)
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(router)

    @app.get("/private")
    def private():
        return {"ok": True}

    @app.get("/health")
    async def health():
        release.set()
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

        async def concurrent_health():
            assert await asyncio.to_thread(entered.wait, 2)
            return await client.get("/health")

        result, health_result = await asyncio.gather(
            client.request(method, path, headers={"cookie": f"fiestaboard_session={token}"}), concurrent_health()
        )
    assert result.status_code == health_result.status_code == 200
    assert unblocked_by_other_request and all(unblocked_by_other_request)
