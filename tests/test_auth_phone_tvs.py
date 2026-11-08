"""H10b: a phone lists and revokes the account's signed-in TVs.

Per Jev D14, phones manage TVs through a narrow surface: TV sessions only.
``/auth/sessions`` stays browser-only, and a phone can never see or revoke a
browser or a phone. A phone signs itself out with ``DELETE /auth/device/session``.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
ANDROID = {"client_id": "fiestaboard-android", "device_name": "Pixel", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}
GTV = {"client_id": "fiestaboard-androidtv", "device_name": "Bedroom", "app_version": "2.0"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    routes_module._FAILED_ATTEMPTS.clear()
    return svc


@pytest.fixture
def browser(auth):
    client = TestClient(app, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


def bearer_client(token):
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


def sign_in(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def phone(auth):
    token = sign_in(IOS)
    return bearer_client(token["access_token"]), token


def approved_tv(auth, approver, metadata=TV):
    """A TV signed in with a code that *approver* (a phone or browser client) approved."""
    grant = TestClient(app).post("/auth/device/authorize", json=metadata).json()
    assert approver.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 200
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 6_000
    token = TestClient(app).post(
        "/auth/device/token", json={"device_code": grant["device_code"], "client_id": metadata["client_id"]}
    )
    assert token.status_code == 200, token.text
    return token.json()


def tvs(client):
    response = client.get("/auth/device/tvs")
    assert response.status_code == 200, response.text
    return response.json()["tvs"]


# --- Listing -------------------------------------------------------------------


def test_a_phone_lists_tvs_only(auth, browser, phone):
    client, _ = phone
    sign_in(ANDROID)
    tv = sign_in(TV)
    rows = tvs(client)
    assert [row["id"] for row in rows] == [tv["session_id"]]
    row = rows[0]
    assert row["device_name"] == TV["device_name"] and row["client_id"] == TV["client_id"]
    assert row["app_version"] == TV["app_version"] and row["method"] == "password"
    assert {"created_at", "last_active_at", "expires_at", "last_shown_at", "shown_panels"} <= set(row)
    for secret in ("digest", "username", "access_token", "account_generation", "approver_session_id", "kind"):
        assert secret not in row


def test_newest_tv_first(auth, phone):
    client, _ = phone
    first = sign_in(TV)
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 1_000
    second = sign_in(GTV)
    assert [row["id"] for row in tvs(client)] == [second["session_id"], first["session_id"]]


def test_approved_by_you_marks_the_approving_phone(auth, browser, phone):
    client, _ = phone
    mine = approved_tv(auth, client)
    theirs = approved_tv(auth, browser, GTV)
    rows = {row["id"]: row for row in tvs(client)}
    assert rows[mine["session_id"]]["approved_by_you"] is True
    assert rows[theirs["session_id"]]["approved_by_you"] is False
    other = bearer_client(sign_in(ANDROID)["access_token"])
    assert all(row["approved_by_you"] is False for row in tvs(other))


def test_a_password_tv_is_not_approved_by_anyone(auth, phone):
    client, _ = phone
    sign_in(TV)
    assert tvs(client)[0]["approved_by_you"] is False


def test_other_generations_are_hidden(auth, phone):
    sign_in(TV)
    auth.invalidate_all_sessions("admin")
    client = bearer_client(sign_in(IOS)["access_token"])
    assert tvs(client) == []


# --- Revoking ------------------------------------------------------------------


def test_a_phone_signs_out_a_tv(auth, phone):
    client, _ = phone
    tv = sign_in(TV)
    tv_client = bearer_client(tv["access_token"])
    assert tv_client.get("/panels").status_code == 200
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    assert tv_client.get("/panels").status_code == 401
    assert tvs(client) == []


def test_a_phone_may_sign_out_a_tv_it_did_not_approve(auth, browser, phone):
    client, _ = phone
    tv = approved_tv(auth, browser)
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200


def _not_found(response):
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "not_found"


def test_a_phone_cannot_sign_out_a_browser(auth, browser, phone):
    client, _ = phone
    browser_id = browser.get("/auth/sessions").json()["current_session_id"]
    _not_found(client.delete("/auth/device/tvs/" + browser_id))
    assert browser.get("/auth/sessions").status_code == 200


def test_a_phone_cannot_sign_out_another_phone(auth, phone):
    client, _ = phone
    other = sign_in(ANDROID)
    _not_found(client.delete("/auth/device/tvs/" + other["session_id"]))
    assert bearer_client(other["access_token"]).get("/v1/status").status_code == 200


def test_a_phone_cannot_sign_itself_out_here(auth, phone):
    client, token = phone
    _not_found(client.delete("/auth/device/tvs/" + token["session_id"]))
    assert client.get("/v1/status").status_code == 200


@pytest.mark.parametrize("session_id", ["nope", "A" * 22])
def test_unknown_ids_are_not_found(auth, phone, session_id):
    client, _ = phone
    _not_found(client.delete("/auth/device/tvs/" + session_id))


def test_a_signed_out_tv_is_not_found(auth, phone):
    client, _ = phone
    tv = sign_in(TV)
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    _not_found(client.delete("/auth/device/tvs/" + tv["session_id"]))


def test_an_old_generation_tv_is_not_found(auth):
    tv = sign_in(TV)
    with auth.sessions.transaction() as db:
        db.execute("UPDATE sessions SET account_generation=account_generation-1 WHERE id=?", (tv["session_id"],))
    client = bearer_client(sign_in(IOS)["access_token"])
    _not_found(client.delete("/auth/device/tvs/" + tv["session_id"]))


def test_revokes_are_rate_limited_per_phone(auth, phone):
    client, _ = phone
    for _ in range(20):
        client.delete("/auth/device/tvs/nope")
    response = client.delete("/auth/device/tvs/nope")
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    # The limit is the phone's, not the address's: another phone is unaffected.
    other = bearer_client(sign_in(ANDROID)["access_token"])
    _not_found(other.delete("/auth/device/tvs/nope"))


AUDIT = "src.auth.audit"


def _audit_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == AUDIT]


def test_a_phone_revoke_is_audited_without_the_token(auth, phone, caplog):
    client, token = phone
    tv = sign_in(TV)
    with caplog.at_level(logging.INFO, logger=AUDIT):
        assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    lines = _audit_lines(caplog)
    assert lines == [
        f"Sign-out: mobile {token['session_id']} ({IOS['device_name']}) signed out "
        f"tv {tv['session_id']} ({TV['device_name']})"
    ]
    assert all(tv["access_token"] not in line and token["access_token"] not in line for line in lines)


def test_a_browser_revoke_is_audited_the_same_way(auth, browser, caplog):
    tv = sign_in(TV)
    browser_id = browser.get("/auth/sessions").json()["current_session_id"]
    with caplog.at_level(logging.INFO, logger=AUDIT):
        assert browser.delete("/auth/sessions/" + tv["session_id"]).status_code == 200
    lines = _audit_lines(caplog)
    assert len(lines) == 1
    assert lines[0].startswith(f"Sign-out: browser {browser_id} (")
    assert lines[0].endswith(f"signed out tv {tv['session_id']} ({TV['device_name']})")


def test_a_browser_revoke_of_an_unknown_id_is_not_audited(auth, browser, caplog):
    with caplog.at_level(logging.INFO, logger=AUDIT):
        assert browser.delete("/auth/sessions/nope").status_code == 200
    assert _audit_lines(caplog) == []


# --- Every miss looks the same (security F5) ------------------------------------


def _forge(auth, kind, username="admin", **changes):
    from src.auth.session_models import SessionRecord

    now = auth.sessions.clock_ms()
    user = auth.get_user("admin")
    record = SessionRecord(
        id="forged-" + kind + "-" + username,
        digest="d-" + kind + "-" + username,
        username=username,
        account_generation=user.get("sessions_valid_after_ms", 0),
        kind=kind,
        device_name="Forged",
        client_id="fiestaboard-tvos",
        app_version="1",
        method="password",
        created_ms=now,
        expires_ms=now + 3_600_000,
        last_active_ms=now,
    )
    auth.sessions.create_session(record.__class__(**{**record.__dict__, **changes}))
    return record.id


def _miss_ids(auth, browser, phone_token):
    revoked, expired, old = sign_in(TV), sign_in(GTV), sign_in({**TV, "device_name": "Old"})
    auth.sessions.revoke_session("admin", revoked["session_id"])
    with auth.sessions.transaction() as db:
        db.execute("UPDATE sessions SET expires_ms=1 WHERE id=?", (expired["session_id"],))
        db.execute("UPDATE sessions SET account_generation=account_generation-1 WHERE id=?", (old["session_id"],))
    return {
        "browser": browser.get("/auth/sessions").json()["current_session_id"],
        "other phone": sign_in(ANDROID)["session_id"],
        "self": phone_token["session_id"],
        "unknown": "A" * 22,
        "revoked": revoked["session_id"],
        "expired": expired["session_id"],
        "old generation": old["session_id"],
        "legacy": _forge(auth, "legacy"),
        "another user's tv": _forge(auth, "tv", username="someone-else"),
    }


def test_every_miss_is_the_same_404(auth, browser, phone):
    client, token = phone
    shapes = {}
    for label, session_id in _miss_ids(auth, browser, token).items():
        with auth.sessions.transaction() as db:
            db.execute("DELETE FROM limits")
        response = client.delete("/auth/device/tvs/" + session_id)
        headers = {k: v for k, v in response.headers.items() if k.lower() != "date"}
        shapes[label] = (response.status_code, response.text, tuple(sorted(headers.items())))
    assert len(set(shapes.values())) == 1, shapes
    status, body, _ = next(iter(shapes.values()))
    assert status == 404 and json.loads(body) == {"error": "not_found", "detail": "No signed-in TV with that id."}
    # None of the targets was touched.
    assert client.get("/v1/status").status_code == 200
    assert browser.get("/auth/sessions").status_code == 200


def test_an_operator_api_token_cannot_manage_tvs(auth, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "operator-token-for-tests-0123456789")
    client = bearer_client("operator-token-for-tests-0123456789")
    tv = sign_in(TV)
    assert client.get("/auth/device/tvs").status_code == 401
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 401
    assert bearer_client(tv["access_token"]).get("/panels").status_code == 200


def test_a_cookie_never_widens_the_phone_bearer(auth, browser, phone):
    _, token = phone
    browser_id = browser.get("/auth/sessions").json()["current_session_id"]
    browser.headers["Authorization"] = "Bearer " + token["access_token"]
    response = browser.delete("/auth/device/tvs/" + browser_id)
    assert response.status_code == 404
    del browser.headers["Authorization"]
    assert browser.get("/auth/sessions").status_code == 200


def test_a_cookie_does_not_rescue_a_bad_phone_bearer(auth, browser):
    browser.headers["Authorization"] = "Bearer fb_mob_" + "x" * 43
    assert browser.get("/auth/device/tvs").status_code == 401


# --- Shared revoke side effects (Fable note 3, security F3) ---------------------


def test_a_phone_revoke_drops_the_tvs_panel_views(auth, phone):
    client, _ = phone
    tv = sign_in(TV)
    assert auth.sessions.record_panel_view(tv["session_id"], "living-room")
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    with auth.sessions.transaction() as db:
        rows = db.execute("SELECT COUNT(*) FROM panel_views WHERE session_id=?", (tv["session_id"],)).fetchone()
    assert rows[0] == 0


def _approvals(auth, session_id):
    with auth.sessions.transaction() as db:
        return db.execute("SELECT COUNT(*) FROM session_approvals WHERE session_id=?", (session_id,)).fetchone()[0]


def test_an_approval_goes_with_its_expired_tv(auth, phone):
    client, _ = phone
    tv = approved_tv(auth, client)
    assert _approvals(auth, tv["session_id"]) == 1
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 366 * 24 * 3600 * 1000
    auth.sessions.list_sessions("admin")  # any registry read runs cleanup
    assert _approvals(auth, tv["session_id"]) == 0


def test_an_approval_goes_with_its_revoked_tv(auth, phone):
    client, _ = phone
    tv = approved_tv(auth, client)
    assert client.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 200
    auth.sessions.list_sessions("admin")
    assert _approvals(auth, tv["session_id"]) == 0


# --- Shape of the row (Fable note 1) ---------------------------------------------


def test_the_tv_row_model_refuses_unknown_fields():
    from src.auth.device_models import PhoneTV

    assert PhoneTV.model_config.get("extra") == "forbid"


def test_the_route_module_does_not_reach_into_other_routers():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/auth/device_routes.py").read_text())
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "session_routes" not in imported and "src.panels.service" not in imported


# --- Who may call ----------------------------------------------------------------


def test_control_has_exactly_the_two_new_rules():
    assert scopes.permits(scopes.CONTROL, "GET", "/auth/device/tvs")
    assert scopes.permits(scopes.CONTROL, "DELETE", "/auth/device/tvs/x")
    assert not scopes.permits(scopes.CONTROL, "POST", "/auth/device/tvs")
    assert not scopes.permits(scopes.CONTROL, "DELETE", "/auth/device/tvs")
    assert not scopes.permits(scopes.TV_PANELS, "GET", "/auth/device/tvs")
    assert not scopes.permits(scopes.TV_PANELS, "DELETE", "/auth/device/tvs/x")
    # The browser's session management stays out of the phone's reach.
    assert not scopes.permits(scopes.CONTROL, "GET", "/auth/sessions")
    assert not scopes.permits(scopes.CONTROL, "DELETE", "/auth/sessions/x")


def test_a_tv_cannot_list_or_revoke(auth):
    tv = bearer_client(sign_in(TV)["access_token"])
    other = sign_in(GTV)
    assert tv.get("/auth/device/tvs").status_code == 403
    assert tv.delete("/auth/device/tvs/" + other["session_id"]).status_code == 403


def test_a_browser_uses_its_own_route(auth, browser):
    tv = sign_in(TV)
    assert browser.get("/auth/device/tvs").status_code == 401
    assert browser.delete("/auth/device/tvs/" + tv["session_id"]).status_code == 401


def test_no_credential_is_401(auth):
    assert TestClient(app).get("/auth/device/tvs").status_code == 401


def test_a_revoked_phone_cannot_list(auth, browser, phone):
    client, token = phone
    assert browser.delete("/auth/sessions/" + token["session_id"]).status_code == 200
    assert client.get("/auth/device/tvs").status_code == 401


def test_the_handler_itself_refuses_a_tv_token(auth):
    # The middleware already stops a TV token here; the route does not rely on it.
    from starlette.requests import Request

    from src.auth.device_models import AuthFlowError
    from src.auth.device_routes import _phone

    token = sign_in(TV)["access_token"]
    request = Request(
        {"type": "http", "method": "GET", "path": "/auth/device/tvs",
         "headers": [(b"authorization", ("Bearer " + token).encode())], "client": ("127.0.0.1", 1)}
    )  # fmt: skip
    with pytest.raises(AuthFlowError) as raised:
        _phone(request)
    assert raised.value.status == 401


# --- Control bytes never reach the audit log (security F6) ----------------------

_HOSTILE_AGENT = "Mozilla/5.0 \x1b[31mRED\x1b[0m \x9b31mCSI\x9b0m end"


def _printable(text):
    return all(ch.isprintable() for ch in text)


def test_a_browser_name_is_stored_without_control_bytes(auth):
    client = TestClient(app, headers={"User-Agent": _HOSTILE_AGENT.encode("latin-1")})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    names = [row.device_name for row in auth.sessions.list_sessions("admin") if row.kind == "browser"]
    assert names and all(_printable(name) for name in names)
    assert "RED" in names[0] and "CSI" in names[0]


def test_the_audit_line_is_printable_even_for_an_old_raw_name(auth, browser, caplog):
    # A row stored before the fix can still carry the raw User-Agent.
    victim = _forge(auth, "browser", device_name=_HOSTILE_AGENT)
    with caplog.at_level(logging.INFO, logger=AUDIT):
        assert browser.delete("/auth/sessions/" + victim).status_code == 200
    lines = _audit_lines(caplog)
    assert len(lines) == 1 and _printable(lines[0])
    assert "\x1b" not in lines[0] and "\x9b" not in lines[0]
