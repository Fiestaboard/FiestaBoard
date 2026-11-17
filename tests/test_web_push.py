"""H15 browser contract: identity, consent and secret-free projections."""
# ruff: noqa: F811

import base64
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from src.api_server import app
from src.backup.service import BackupService
from tests.test_auth_phone_tvs import PASSWORD, auth, browser, phone  # noqa: F401


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


@pytest.fixture
def subscription():
    public = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-capability-secret",
        "expirationTime": None,
        "keys": {"p256dh": encoded(public), "auth": encoded(b"test-secret-1234")},
    }


def register(client, subscription, enabled=True):
    return client.put("/push/subscription", json={"enabled": enabled, "subscription": subscription})


def second_browser():
    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context").json()
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context["csrf_token"]})
    return client


def test_status_starts_with_both_opt_ins_off(browser):
    response = browser.get("/push/status")
    assert response.status_code == 200, response.text
    status = response.json()
    assert status == {
        "public_key": status["public_key"],
        "user_enabled": False,
        "device_enabled": False,
        "subscribed": False,
        "expiration_time": None,
        "event_sources": [],
        "test_available": False,
    }
    public = base64.urlsafe_b64decode(status["public_key"] + "==")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)


def test_device_and_user_opt_ins_are_independent(browser, subscription):
    assert register(browser, subscription).status_code == 200
    state = browser.get("/push/status").json()
    assert state["device_enabled"] is True
    assert state["user_enabled"] is False
    assert browser.put("/push/preferences", json={"enabled": True}).status_code == 200
    other = second_browser()
    state = other.get("/push/status").json()
    assert state["user_enabled"] is True
    assert state["device_enabled"] is False
    assert state["subscribed"] is False
    assert other.delete("/push/subscription").status_code == 200
    assert browser.get("/push/status").json()["subscribed"] is True
    assert register(browser, subscription, enabled=False).status_code == 200
    state = browser.get("/push/status").json()
    assert state["device_enabled"] is False
    assert state["user_enabled"] is True


def test_response_and_backup_never_expose_subscription_secrets(browser, subscription, tmp_path, caplog):
    response = register(browser, subscription)
    assert response.status_code == 200
    backup = BackupService(tmp_path / "data").export_to_json()
    for secret in [subscription["endpoint"], *subscription["keys"].values(), "PRIVATE KEY"]:
        assert secret not in response.text + browser.get("/push/status").text + backup + caplog.text


def test_no_unauthenticated_identity_even_when_auth_disabled(auth, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    client = TestClient(app)
    assert client.get("/push/status").status_code == 401
    assert client.put("/push/preferences", json={"enabled": True}).status_code == 401


def test_native_and_api_tokens_cannot_manage_push(browser, phone, monkeypatch):
    client, _ = phone
    assert client.get("/push/status").status_code == 403
    assert client.put("/push/preferences", json={"enabled": True}).status_code == 403
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "test-api-token")
    browser.headers["Authorization"] = "Bearer test-api-token"
    assert browser.get("/push/status").status_code == 401


@pytest.mark.parametrize("header", ["Origin", "X-CSRF-Token"])
def test_mutations_require_origin_and_csrf(browser, subscription, header):
    del browser.headers[header]
    assert register(browser, subscription).status_code == 403
    assert browser.put("/push/preferences", json={"enabled": True}).status_code == 403
    assert browser.delete("/push/subscription").status_code == 403


def test_endpoint_cannot_be_claimed_by_another_session(browser, subscription):
    assert register(browser, subscription).status_code == 200
    assert register(second_browser(), subscription).status_code == 409
    assert browser.delete("/push/subscription").status_code == 200
    assert browser.get("/push/status").json()["subscribed"] is False


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/x",
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://fcm.googleapis.com.evil.example/x",
        "https://fcm.googleapis.com:444/x",
        "https://secret@fcm.googleapis.com/x",
        "https://fcm.googleapis.com/x#fragment",
        "https://fcm.googleapis.com./x",
        "https://push.apple.com\\@localhost/x",
    ],
)
def test_unsafe_endpoint_rejected_without_echoing_it(browser, subscription, endpoint):
    subscription["endpoint"] = endpoint
    response = register(browser, subscription)
    assert response.status_code == 422
    assert endpoint not in response.text


@pytest.mark.parametrize("key,value", [("auth", "bad"), ("p256dh", "AA"), ("auth", "!" * 22)])
def test_invalid_browser_keys_rejected_without_echo(browser, subscription, key, value):
    subscription["keys"][key] = value
    response = register(browser, subscription)
    assert response.status_code == 422
    assert subscription["endpoint"] not in response.text


def test_expired_subscription_and_spoofed_identity_rejected(browser, subscription):
    subscription["expirationTime"] = 1
    assert register(browser, subscription).status_code == 400
    assert browser.put("/push/preferences", json={"enabled": True, "username": "someone"}).status_code == 422
    assert browser.put("/push/preferences", json={"enabled": "true"}).status_code == 422


def test_store_persists_public_key_and_private_permissions(browser, tmp_path):
    from src.push.store import PushStore

    public = browser.get("/push/status").json()["public_key"]
    path = tmp_path / "data" / "web-push.sqlite3"
    assert path.exists()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert PushStore(path).public_key == public
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: PushStore(path).public_key, range(16)))
    assert set(keys) == {public}
    fresh = tmp_path / "parallel.sqlite3"
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len(set(pool.map(lambda _: PushStore(fresh).public_key, range(16)))) == 1


def test_new_account_generation_starts_without_consent(browser, auth):
    assert browser.put("/push/preferences", json={"enabled": True}).status_code == 200
    auth.invalidate_all_sessions("admin")
    client = second_browser()
    assert client.get("/push/status").json()["user_enabled"] is False


def test_internal_schema_declares_session_only_and_no_secret_response_fields(browser):
    schema = browser.get("/internal/openapi.json").json()
    for path in ("/push/status", "/push/preferences", "/push/subscription"):
        assert path in schema["paths"]
        for operation in schema["paths"][path].values():
            assert operation["security"] == [{"session": []}]
    fields = schema["components"]["schemas"]["PushStatus"]["properties"]
    assert set(fields) == {
        "public_key",
        "user_enabled",
        "device_enabled",
        "subscribed",
        "expiration_time",
        "event_sources",
        "test_available",
    }


def test_test_delivery_requires_consent_and_refuses_caller_payload(browser, subscription):
    assert browser.post("/push/test", json={}).status_code == 409
    assert register(browser, subscription).status_code == 200
    assert browser.post("/push/test", json={}).status_code == 409
    assert browser.post("/push/test", json={"title": "arbitrary"}).status_code == 422


def test_test_delivery_refuses_private_provider_dns(browser, subscription, monkeypatch):
    import socket

    monkeypatch.setenv("FIESTABOARD_WEB_PUSH_SUBJECT", "mailto:push@example.com")
    assert register(browser, subscription).status_code == 200
    assert browser.put("/push/preferences", json={"enabled": True}).status_code == 200
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    )
    client = TestClient(app, cookies=browser.cookies, headers=browser.headers, raise_server_exceptions=False)
    response = client.post("/push/test", json={})
    assert response.status_code == 503, response.text
    assert client.post("/push/test", json={}).status_code == 429


def test_revoked_sessions_do_not_exhaust_subscription_capacity(browser, auth, subscription):
    from dataclasses import replace

    from src.auth.service import SESSION_COOKIE_NAME
    from src.push.models import PushSubscription
    from src.push.store import get_push_store

    current = auth.resolve_browser_session(browser.cookies.get(SESSION_COOKIE_NAME))
    store = get_push_store()
    for index in range(20):
        stale = replace(current, id=f"old-session-{index}")
        payload = PushSubscription(
            enabled=True, subscription={**subscription, "endpoint": f"https://fcm.googleapis.com/fcm/send/old-{index}"}
        )
        store.subscribe(stale, payload)
    assert register(browser, subscription).status_code == 200


def test_renamed_account_can_reclaim_its_old_browser_endpoint(browser, auth, subscription):
    assert register(browser, subscription).status_code == 200
    auth.change_username("admin", PASSWORD, "renamed")
    client = TestClient(app)
    assert client.post("/auth/login", json={"username": "renamed", "password": PASSWORD}).status_code == 200
    context = client.get("/auth/sessions/context").json()
    client.headers.update({"Origin": "http://testserver", "X-CSRF-Token": context["csrf_token"]})
    assert register(client, subscription).status_code == 200


def test_redacted_validation_matches_declared_error_schema(browser, subscription):
    invalid = browser.put("/push/preferences", json={"enabled": "yes"})
    assert invalid.status_code == 422
    assert isinstance(invalid.json()["detail"], str)
    schema = browser.get("/internal/openapi.json").json()
    response = schema["paths"]["/push/preferences"]["put"]["responses"]["422"]
    assert response["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
    subscription["expirationTime"] = 1
    assert register(browser, subscription).status_code == 400


def test_prune_cannot_delete_browser_enrolled_after_auth_snapshot(browser, auth, subscription, monkeypatch):
    assert register(browser, subscription).status_code == 200
    list_sessions = auth.sessions.list_sessions
    other = []
    interleaved = False

    def enroll_after_snapshot(username):
        nonlocal interleaved
        snapshot = list_sessions(username)
        if not interleaved:
            interleaved = True
            device = second_browser()
            replacement = {**subscription, "endpoint": "https://fcm.googleapis.com/fcm/send/concurrent-browser"}
            assert register(device, replacement).status_code == 200
            other.append(device)
        return snapshot

    monkeypatch.setattr(auth.sessions, "list_sessions", enroll_after_snapshot)
    assert register(browser, subscription).status_code == 200
    assert other[0].get("/push/status").json()["subscribed"] is True
