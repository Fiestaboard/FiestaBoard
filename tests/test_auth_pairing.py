"""H11: pairing a phone by QR, and a phone approving a TV's code.

A browser that is signed in creates a short-lived, single-use pairing offer and
shows it as a QR. The phone app claims it and receives the same ``fb_mob_``
``control`` credential that a password sign-in gives (H10's scope model,
``src/auth/scopes.py``). The pairing secret travels in the QR's fragment and
the claim's JSON body, never in a request URL.

A phone signed in with ``control`` may approve or deny a TV's device code, as
the browser ``/activate`` page does; it may never approve a code that would
mint ``control``.
"""

import threading
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.auth.device_models import AuthFlowError, DeviceMetadata
from src.auth.device_service import DeviceService
from src.auth.session_store import digest_secret

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}
ANDROID = {"client_id": "fiestaboard-android", "device_name": "Pixel", "app_version": "1.0"}
TV = {"client_id": "fiestaboard-tvos", "device_name": "Living room", "app_version": "1.0"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("FIESTABOARD_DATA_DIR", str(tmp_path / "data"))
    routes_module._FAILED_ATTEMPTS.clear()
    return svc


def _browser():
    client = TestClient(app, headers={"User-Agent": "Mozilla/5.0 Test browser"})
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context")
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context.json()["csrf_token"]})
    return client


@pytest.fixture
def browser(auth):
    return _browser()


def bearer_client(token):
    return TestClient(app, headers={"Authorization": "Bearer " + token}, raise_server_exceptions=False)


def sign_in(metadata):
    response = TestClient(app).post("/auth/device/login", json={**metadata, "username": "admin", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def offer(browser):
    response = browser.post("/auth/pairing", json={})
    assert response.status_code == 200, response.text
    return response.json()


def fragment(payload):
    parts = urlsplit(payload["qr_payload"])
    return parts, {key: values[0] for key, values in parse_qs(parts.fragment, keep_blank_values=True).items()}


def code_of(payload):
    return fragment(payload)[1]["code"]


def claim(code, metadata=IOS, client=None):
    return (client or TestClient(app)).post("/auth/pairing/claim", json={**metadata, "pairing_code": code})


# --- The offer and its QR ---------------------------------------------------


def test_offer_is_a_fragment_only_qr_payload(auth, browser):
    payload = offer(browser)
    parts, fields = fragment(payload)
    assert parts.scheme == "fiestaboard" and parts.netloc == "pair"
    # The secret is in the fragment, which no HTTP request carries. Never a query.
    assert parts.query == "" and "code=" not in payload["qr_payload"].split("#")[0]
    assert fields["v"] == "1"
    assert fields["hub"] == "http://testserver"
    assert fields["code"].startswith("fb_pair_") and len(fields["code"]) >= 48
    assert fields["id"] and "name" in fields
    assert payload["expires_in"] == 300 and payload["scope"] == "control"
    assert payload["pairing_id"] and payload["pairing_id"] not in fields["code"]
    # The hub address is also a plain field, so the web page can show it without parsing.
    assert payload["hub"] == "http://testserver"


def test_fragment_uses_percent_encoding_not_plus(auth, browser, monkeypatch):
    # iOS URLComponents does not turn "+" back into a space; encode spaces as %20.
    monkeypatch.setattr("src.auth.pairing_routes.hub_identity", lambda: ("install-1", "Maya's FiestaPi"))
    payload = offer(browser)
    raw = payload["qr_payload"].split("#", 1)[1]
    assert "+" not in raw
    fields = dict(part.split("=", 1) for part in raw.split("&"))
    assert unquote(fields["name"]) == "Maya's FiestaPi"
    assert unquote(fields["hub"]) == "http://testserver"


def test_offer_response_is_not_cached(auth, browser):
    response = browser.post("/auth/pairing", json={})
    assert response.headers["cache-control"] == "no-store"


def test_only_the_digest_is_stored(auth, browser):
    code = code_of(offer(browser))
    with auth.sessions.transaction() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM pairings").fetchall()]
    assert rows and all(code not in str(value) for row in rows for value in row.values())
    assert rows[0]["digest"] == digest_secret(code)


def test_offer_hub_follows_the_validated_origin(auth, browser, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_CORS_ORIGINS", "https://board.example.net")
    browser.headers["Origin"] = "https://board.example.net"
    assert fragment(offer(browser))[1]["hub"] == "https://board.example.net"


@pytest.mark.parametrize(
    "change",
    [
        {"Origin": "http://evil.example"},
        {"X-CSRF-Token": "wrong"},
    ],
)
def test_offer_needs_the_portal_origin_and_csrf(auth, browser, change):
    browser.headers.update(change)
    assert browser.post("/auth/pairing", json={}).status_code == 403


def test_offer_needs_a_browser_session(auth):
    assert TestClient(app).post("/auth/pairing", json={}).status_code == 401


@pytest.mark.parametrize("metadata", [IOS, TV])
def test_native_sign_ins_cannot_create_offers(auth, metadata):
    client = bearer_client(sign_in(metadata)["access_token"])
    assert client.post("/auth/pairing", json={}).status_code == 403
    assert not scopes.permits(scopes.CONTROL, "POST", "/auth/pairing")


def test_offer_needs_device_sign_in_enabled(auth, browser):
    auth.sessions.set_enrollment(False)
    response = browser.post("/auth/pairing", json={})
    assert response.status_code == 403 and response.json()["error"] == "feature_disabled"


def test_offers_are_rate_limited_per_account(auth, browser):
    for _ in range(5):
        offer(browser)
    response = browser.post("/auth/pairing", json={})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


# --- Claiming ---------------------------------------------------------------


@pytest.mark.parametrize("metadata", [IOS, ANDROID])
def test_claim_issues_a_control_credential(auth, browser, metadata):
    response = claim(code_of(offer(browser)), metadata)
    assert response.status_code == 200, response.text
    token = response.json()
    assert token["access_token"].startswith("fb_mob_") and token["scope"] == "control"
    assert token["expires_in"] == 31536000
    phone = bearer_client(token["access_token"])
    assert phone.get("/v1/status").status_code == 200
    assert phone.get("/auth/sessions").status_code == 403
    row = next(r for r in browser.get("/auth/sessions").json()["sessions"] if r["id"] == token["session_id"])
    assert row["kind"] == "mobile" and row["method"] == "pairing" and row["device_name"] == metadata["device_name"]


def test_claim_is_single_use(auth, browser):
    code = code_of(offer(browser))
    assert claim(code).status_code == 200
    replay = claim(code, ANDROID)
    assert replay.status_code == 400 and replay.json()["error"] == "invalid_grant"


def test_claim_expires_after_five_minutes(auth, browser):
    code = code_of(offer(browser))
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 301_000
    response = claim(code)
    assert response.status_code == 400 and response.json()["error"] == "expired_token"


def test_unknown_code_is_invalid(auth):
    response = claim("fb_pair_" + "A" * 43)
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_tv_cannot_pair(auth, browser):
    code = code_of(offer(browser))
    response = claim(code, TV)
    assert response.status_code == 400 and response.json()["error"] == "unsupported_client"
    # The refusal does not burn the offer: the phone can still claim it.
    assert claim(code).status_code == 200


def test_a_new_offer_replaces_the_old_one(auth, browser):
    first = code_of(offer(browser))
    second = code_of(offer(browser))
    assert claim(first).status_code == 400
    assert claim(second).status_code == 200


def test_closing_the_dialog_cancels_the_offer(auth, browser):
    code = code_of(offer(browser))
    assert browser.delete("/auth/pairing").status_code == 200
    assert claim(code).status_code == 400


def test_turning_off_device_sign_in_cancels_offers(auth, browser):
    code = code_of(offer(browser))
    auth.sessions.set_enrollment(False)
    auth.sessions.set_enrollment(True)
    assert claim(code).status_code == 400


def test_claim_refused_while_device_sign_in_is_off(auth, browser):
    code = code_of(offer(browser))
    auth.sessions.set_enrollment(False)
    assert claim(code).status_code == 403


def test_revoking_the_creating_browser_cancels_its_offer(auth, browser):
    code = code_of(offer(browser))
    assert browser.post("/auth/logout").status_code == 200
    assert claim(code).status_code == 400


def test_sign_out_other_devices_cancels_another_browsers_offer(auth, browser):
    code = code_of(offer(browser))
    other = _browser()
    assert other.post("/auth/sessions/revoke", json={"include_current": False}).status_code == 200
    assert claim(code).status_code == 400


def test_sign_out_other_devices_keeps_this_browsers_offer(auth, browser):
    # The browser showing the QR survives "Sign out other devices", so its QR does too:
    # only offers whose creator was signed out are cancelled.
    code = code_of(offer(browser))
    _browser()
    assert browser.post("/auth/sessions/revoke", json={"include_current": False}).status_code == 200
    assert claim(code).status_code == 200


def test_sign_out_everywhere_cancels_offers(auth, browser):
    code = code_of(offer(browser))
    assert browser.post("/auth/sessions/revoke", json={"include_current": True}).status_code == 200
    assert claim(code).status_code == 400


def test_account_rotation_cancels_offers(auth, browser):
    code = code_of(offer(browser))
    auth.invalidate_all_sessions("admin")
    assert claim(code).status_code == 400


def test_failed_claims_share_the_login_lockout(auth, browser):
    code = code_of(offer(browser))
    client = TestClient(app)
    for _ in range(10):
        assert claim("fb_pair_" + "B" * 43, client=client).status_code == 400
    locked = claim(code, client=client)
    assert locked.status_code == 429 and locked.headers["retry-after"] == "60"
    # The bucket is the one /auth/login uses: that IP is locked out there too.
    login = client.post("/auth/login", json={"username": "admin", "password": PASSWORD})
    assert login.status_code == 429


def test_claims_are_rate_limited_per_address(auth, browser, monkeypatch):
    # Even without failures, one address gets 10 claim attempts a minute.
    monkeypatch.setattr(routes_module, "_record_failure", lambda ip: None)
    client = TestClient(app)
    for _ in range(10):
        claim("fb_pair_" + "C" * 43, client=client)
    response = claim(code_of(offer(browser)), client=client)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"


@pytest.mark.parametrize("code", ["", "x" * 200])
def test_claim_validates_the_code_shape(auth, code):
    assert claim(code).status_code == 422


def test_claim_rejects_a_bearer(auth, browser):
    # A signed-in phone has nothing to claim; its token is refused by scope.
    phone = bearer_client(sign_in(IOS)["access_token"])
    assert claim(code_of(offer(browser)), client=phone).status_code == 403


# --- The status the web page polls -------------------------------------------


def test_status_reports_the_claim(auth, browser):
    payload = offer(browser)
    status = browser.get("/auth/pairing/" + payload["pairing_id"])
    assert status.status_code == 200
    assert status.json() == {"state": "pending", "device_name": None, "session_id": None}
    token = claim(code_of(payload)).json()
    status = browser.get("/auth/pairing/" + payload["pairing_id"]).json()
    assert status == {"state": "claimed", "device_name": IOS["device_name"], "session_id": token["session_id"]}


def test_status_reports_expiry_and_cancel(auth, browser):
    payload = offer(browser)
    browser.delete("/auth/pairing")
    assert browser.get("/auth/pairing/" + payload["pairing_id"]).json()["state"] == "cancelled"
    payload = offer(browser)
    now = auth.sessions.clock_ms()
    auth.sessions.clock_ms = lambda: now + 301_000
    assert browser.get("/auth/pairing/" + payload["pairing_id"]).json()["state"] == "expired"


def test_status_is_browser_only_and_unknown_is_404(auth, browser):
    payload = offer(browser)
    assert TestClient(app).get("/auth/pairing/" + payload["pairing_id"]).status_code == 401
    phone = bearer_client(sign_in(IOS)["access_token"])
    assert phone.get("/auth/pairing/" + payload["pairing_id"]).status_code == 403
    assert browser.get("/auth/pairing/nope").status_code == 404


# --- A phone approves a TV ----------------------------------------------------


@pytest.fixture
def phone(auth):
    token = sign_in(IOS)
    return bearer_client(token["access_token"]), token


def tv_code():
    response = TestClient(app).post("/auth/device/authorize", json=TV)
    assert response.status_code == 200
    return response.json()


def test_control_allows_the_three_decision_routes():
    for path in ("/auth/device/inspect", "/auth/device/approve", "/auth/device/deny"):
        assert scopes.permits(scopes.CONTROL, "POST", path)
        assert not scopes.permits(scopes.TV_PANELS, "POST", path)


def test_phone_inspects_and_approves_a_tv(auth, phone):
    client, token = phone
    grant = tv_code()
    pending = client.post("/auth/device/inspect", json={"user_code": grant["user_code"]})
    assert pending.status_code == 200, pending.text
    assert pending.json()["scope"] == "tv_panels" and pending.json()["device_name"] == TV["device_name"]
    assert client.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 200
    auth.sessions.clock_ms = (lambda now: lambda: now + 6_000)(auth.sessions.clock_ms())
    issued = TestClient(app).post(
        "/auth/device/token", json={"device_code": grant["device_code"], "client_id": TV["client_id"]}
    )
    assert issued.status_code == 200, issued.text
    assert issued.json()["access_token"].startswith("fb_tv_") and issued.json()["scope"] == "tv_panels"
    with auth.sessions.transaction() as db:
        row = db.execute("SELECT approving_session_id FROM challenges").fetchone()
    assert row["approving_session_id"] == token["session_id"]


def test_phone_denies_a_tv(auth, phone):
    client, _ = phone
    grant = tv_code()
    assert client.post("/auth/device/deny", json={"user_code": grant["user_code"]}).status_code == 200
    auth.sessions.clock_ms = (lambda now: lambda: now + 6_000)(auth.sessions.clock_ms())
    response = TestClient(app).post(
        "/auth/device/token", json={"device_code": grant["device_code"], "client_id": TV["client_id"]}
    )
    assert response.json()["error"] == "access_denied"


def test_revoking_the_approving_phone_cancels_the_grant(auth, phone):
    client, token = phone
    grant = tv_code()
    assert client.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 200
    auth.sessions.revoke_session("admin", token["session_id"])
    auth.sessions.clock_ms = (lambda now: lambda: now + 6_000)(auth.sessions.clock_ms())
    response = TestClient(app).post(
        "/auth/device/token", json={"device_code": grant["device_code"], "client_id": TV["client_id"]}
    )
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_a_tv_cannot_approve(auth):
    tv = bearer_client(sign_in(TV)["access_token"])
    grant = tv_code()
    assert tv.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 403


def test_an_unknown_bearer_cannot_approve(auth):
    grant = tv_code()
    client = bearer_client("fb_mob_" + "x" * 43)
    assert client.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 401


def test_a_cookie_does_not_rescue_a_bad_phone_bearer(auth, browser):
    grant = tv_code()
    browser.headers["Authorization"] = "Bearer fb_mob_" + "x" * 43
    assert browser.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 401


def test_phone_decisions_are_rate_limited(auth, phone):
    client, _ = phone
    for _ in range(10):
        client.post("/auth/device/inspect", json={"user_code": "BCDF-GHJK"})
    response = client.post("/auth/device/inspect", json={"user_code": "BCDF-GHJK"})
    assert response.status_code == 429


def test_browser_approval_is_unchanged(auth, browser):
    grant = tv_code()
    assert browser.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 200


def test_a_phone_never_approves_a_control_challenge(auth, phone):
    # Phones cannot start a device-code flow today; forge one to pin the rule anyway.
    _, token = phone
    service = DeviceService(auth)
    grant = service.authorize(DeviceMetadata(**TV), "127.0.0.1")
    with auth.sessions.transaction() as db:
        db.execute("UPDATE challenges SET client_id='fiestaboard-ios'")
    approver = auth.sessions.find_active(digest_secret(token["access_token"]))
    with pytest.raises(AuthFlowError) as raised:
        service.decide(grant.user_code, approver, True)
    assert raised.value.error == "invalid_grant"


# --- Each defence layer, on its own ------------------------------------------


def test_logout_marks_the_offer_cancelled(auth, browser):
    payload = offer(browser)
    other = _browser()
    assert browser.post("/auth/logout").status_code == 200
    assert other.get("/auth/pairing/" + payload["pairing_id"]).json()["state"] == "cancelled"


def test_claim_rechecks_the_creating_browser(auth, browser):
    # Even if an offer were left pending, a creator that is no longer signed in
    # cannot vouch for a new phone.
    code = code_of(offer(browser))
    with auth.sessions.transaction() as db:
        db.execute("UPDATE sessions SET revoked_ms=1 WHERE kind='browser'")
    response = claim(code)
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_the_phone_decision_path_refuses_a_tv_token(auth):
    # The middleware already stops a TV token here; the handler does not rely on it.
    from starlette.requests import Request

    from src.auth.device_routes import _decision_context

    token = sign_in(TV)["access_token"]
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/device/approve",
            "headers": [(b"authorization", ("Bearer " + token).encode())],
            "client": ("127.0.0.1", 1),
        }
    )
    with pytest.raises(AuthFlowError) as raised:
        _decision_context(request)
    assert raised.value.status == 401


# --- Races and odd credentials ------------------------------------------------


def test_concurrent_claims_issue_exactly_one_credential(auth, browser):
    code = code_of(offer(browser))
    start = threading.Barrier(12)
    statuses = []

    def race():
        client = TestClient(app)
        start.wait()
        statuses.append(claim(code, client=client).status_code)

    threads = [threading.Thread(target=race) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert statuses.count(200) == 1
    assert set(statuses) <= {200, 400, 429}
    with auth.sessions.transaction() as db:
        claimed = db.execute("SELECT COUNT(*) FROM pairings WHERE state='claimed'").fetchone()[0]
        phones = db.execute("SELECT COUNT(*) FROM sessions WHERE method='pairing'").fetchone()[0]
    assert claimed == 1 and phones == 1


def test_a_phone_and_a_browser_racing_to_approve_one_tv_code(auth, browser):
    phone = bearer_client(sign_in(IOS)["access_token"])
    grant = tv_code()
    start = threading.Barrier(2)
    statuses = []

    def approve(client):
        start.wait()
        statuses.append(client.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code)

    threads = [threading.Thread(target=approve, args=(client,)) for client in (phone, browser)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(statuses) == [200, 400]
    with auth.sessions.transaction() as db:
        rows = db.execute("SELECT state, approving_session_id FROM challenges").fetchall()
    assert [row["state"] for row in rows] == ["approved"] and rows[0]["approving_session_id"]


def test_claim_refused_when_the_creating_browser_expired(auth, browser):
    code = code_of(offer(browser))
    now = auth.sessions.clock_ms()
    with auth.sessions.transaction() as db:
        db.execute("UPDATE sessions SET expires_ms=? WHERE kind='browser'", (now - 1,))
    response = claim(code)
    assert response.status_code == 400 and response.json()["error"] == "invalid_grant"


def test_a_cookie_with_basic_auth_cannot_approve(auth, browser):
    # Any Authorization header takes the phone path; a cookie never rescues it.
    grant = tv_code()
    browser.headers["Authorization"] = "Basic YWRtaW46Y29ycmVjdC1wYXNzd29yZA=="
    assert browser.post("/auth/device/approve", json={"user_code": grant["user_code"]}).status_code == 401
