"""Push delivery bounds and endpoint safety, with network I/O replaced only at the edge."""
# ruff: noqa: F811

import base64
import json
import socket
import sqlite3

import http_ece
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.auth.service import SESSION_COOKIE_NAME
from tests.test_auth_phone_tvs import auth, browser  # noqa: F401
from tests.test_web_push import encoded, register, subscription  # noqa: F401


@pytest.fixture
def prepared(browser, auth, subscription):
    from src.push.store import get_push_store

    assert register(browser, subscription).status_code == 200
    assert browser.put("/push/preferences", json={"enabled": True}).status_code == 200
    session = auth.resolve_browser_session(browser.cookies.get(SESSION_COOKIE_NAME))
    return get_push_store(), session


class Provider:
    """External provider stub: stores only the requests actually delivered."""

    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.deliveries = []
        self.after = None

    def post(self, url, data, headers, timeout):
        from requests import Response

        self.deliveries.append((url, data, headers, timeout))
        result = next(self.statuses)
        if self.after:
            self.after()
        if isinstance(result, Exception):
            raise result
        response = Response()
        response.status_code = result
        response._content = b""
        response.headers["Retry-After"] = "2"
        return response


def notifier(prepared, auth, provider, sleeps):
    from src.push.notifier import PushNotifier

    store, _ = prepared
    return PushNotifier(store, auth, transport=provider, sleep=sleeps.append, subject="mailto:push@example.com")


def test_provider_gets_encrypted_payload_and_persisted_vapid(prepared, auth, browser, subscription):
    private = ec.generate_private_key(ec.SECP256R1())
    subscription["keys"]["p256dh"] = encoded(
        private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    assert register(browser, subscription).status_code == 200
    provider = Provider([201])
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Board ready", "body": "Hello"})
    assert result.sent == 1
    _, data, headers, timeout = provider.deliveries[0]
    assert b"Board ready" not in data
    decoded = http_ece.decrypt(
        data,
        private_key=private,
        auth_secret=base64.urlsafe_b64decode(subscription["keys"]["auth"] + "=="),
        version="aes128gcm",
    )
    assert json.loads(decoded)["title"] == "Board ready"
    assert headers["content-encoding"] == "aes128gcm"
    assert "k=" + prepared[0].public_key in headers["Authorization"]
    assert 0 < timeout <= 10


@pytest.mark.parametrize("status", [404, 410])
def test_expired_provider_subscription_removed(prepared, auth, browser, status):
    provider = Provider([status])
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert result.expired == 1
    assert browser.get("/push/status").json()["subscribed"] is False


def test_old_410_does_not_delete_renewed_subscription(prepared, auth, browser, subscription):
    provider = Provider([410])
    replacement = {**subscription, "endpoint": "https://fcm.googleapis.com/fcm/send/new-capability"}
    provider.after = lambda: register(browser, replacement)
    notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert browser.get("/push/status").json()["subscribed"] is True


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_transient_failures_retry_and_stop_after_three_attempts(prepared, auth, status):
    sleeps = []
    provider = Provider([status] * 3)
    result = notifier(prepared, auth, provider, sleeps).notify("admin", {"title": "Test"})
    assert result.failed == 1
    assert len(provider.deliveries) == 3
    assert len(sleeps) == 2
    assert all(0 < delay <= 5 for delay in sleeps)


def test_network_failure_then_success(prepared, auth):
    from requests import ConnectionError

    provider = Provider([ConnectionError("secret endpoint in exception"), 201])
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert result.sent == 1
    assert len(provider.deliveries) == 2


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403])
def test_permanent_failure_not_retried(prepared, auth, status):
    provider = Provider([status])
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert result.failed == 1
    assert len(provider.deliveries) == 1


@pytest.mark.parametrize("revoke", ["user", "device", "session", "generation"])
def test_consent_and_session_rechecked_before_retry(prepared, auth, browser, subscription, revoke):
    def disable():
        if revoke == "user":
            browser.put("/push/preferences", json={"enabled": False})
        elif revoke == "device":
            register(browser, subscription, enabled=False)
        elif revoke == "session":
            auth.sessions.revoke_session("admin", prepared[1].id)
        else:
            auth.invalidate_all_sessions("admin")

    provider = Provider([503])
    provider.after = disable
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert result.skipped == 1
    assert len(provider.deliveries) == 1


def test_no_push_to_other_user_or_without_user_opt_in(prepared, auth, browser):
    browser.put("/push/preferences", json={"enabled": False})
    provider = Provider([])
    sender = notifier(prepared, auth, provider, [])
    assert sender.notify("admin", {"title": "Test"}).sent == 0
    assert sender.notify("other-user", {"title": "Test"}).sent == 0
    assert provider.deliveries == []


def test_expired_subscription_removed_before_transport(prepared, auth, browser, subscription):
    from src.push.notifier import PushNotifier

    now = 2_000_000_000_000
    subscription["expirationTime"] = now + 1000
    assert register(browser, subscription).status_code == 200
    provider = Provider([])
    sender = PushNotifier(
        prepared[0], auth, transport=provider, clock_ms=lambda: now + 2000, subject="mailto:push@example.com"
    )
    assert sender.notify("admin", {"title": "Test"}).expired == 1
    assert not browser.get("/push/status").json()["subscribed"]


@pytest.mark.parametrize(
    "payload,ttl",
    [
        ({"title": "x" * 1000}, 300),
        ({"title": "x", "url": "https://evil.example"}, 300),
        ({"title": "x"}, 0),
        ({"title": "x"}, 86401),
    ],
)
def test_invalid_payload_or_ttl_never_reaches_transport(prepared, auth, payload, ttl):
    provider = Provider([])
    with pytest.raises(ValueError):
        notifier(prepared, auth, provider, []).notify("admin", payload, ttl_seconds=ttl)
    assert provider.deliveries == []


def test_corrupted_private_key_fails_closed_without_rotation(prepared):
    from src.push.store import PushStore

    store, _ = prepared
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE metadata SET value='corrupted' WHERE key='vapid_private'")
    with pytest.raises(ValueError, match="Push storage unavailable"):
        PushStore(store.path)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT value FROM metadata WHERE key='vapid_private'").fetchone()[0] == "corrupted"


def test_transport_rejects_mixed_public_and_private_dns(monkeypatch):
    from src.push.transport import PinnedTransport, UnsafeEndpoint

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(UnsafeEndpoint):
        PinnedTransport().post("https://fcm.googleapis.com/fcm/send/test", b"ciphertext", {}, 5)


def test_transport_pins_socket_and_tls_hostname_without_redirect_or_body_read(monkeypatch):
    from src.push import transport

    connections = []

    class FakeSocket:
        def settimeout(self, value):
            assert 0 < value <= 10

        def connect(self, address):
            connections.append(address)

        def close(self):
            pass

    class FakeContext:
        check_hostname = True
        verify_mode = transport.ssl.CERT_REQUIRED

        def wrap_socket(self, sock, server_hostname):
            assert server_hostname == "fcm.googleapis.com"
            return sock

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    )
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: FakeSocket())
    monkeypatch.setattr(transport.ssl, "create_default_context", lambda: FakeContext())
    connection = transport.PinnedHTTPSConnection("fcm.googleapis.com", timeout=5, context=FakeContext())
    connection.connect()
    assert connections == [("8.8.8.8", 443)]


def test_error_logs_do_not_contain_provider_secrets(prepared, auth, subscription, caplog):
    from requests import ConnectionError

    secret = subscription["endpoint"] + subscription["keys"]["auth"]
    provider = Provider([ConnectionError(secret)] * 3)
    notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert secret not in caplog.text


def test_redirect_is_not_followed_and_response_body_not_read(monkeypatch):
    from src.push import transport

    requests = []

    class Upstream:
        status = 302

        def getheader(self, name):
            return "https://127.0.0.1/secret" if name == "Location" else None

        def read(self):
            raise AssertionError("Provider bodies must not be read")

    class Connection:
        def __init__(self, host, timeout, context, guard=None):
            assert host == "fcm.googleapis.com"
            assert context.check_hostname
            assert context.verify_mode == transport.ssl.CERT_REQUIRED

        def connect(self):
            pass

        def request(self, method, target, body, headers):
            requests.append((method, target, body, headers))

        def getresponse(self):
            return Upstream()

        def close(self):
            pass

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setattr(transport, "PinnedHTTPSConnection", Connection)
    result = transport.PinnedTransport().post("https://fcm.googleapis.com/fcm/send/capability", b"ciphertext", {}, 5)
    assert result.status_code == 302
    assert len(requests) == 1
    assert requests[0][:3] == ("POST", "/fcm/send/capability", b"ciphertext")
    assert result.text == ""


def test_opt_out_then_in_cancels_queued_attempt(prepared, auth, browser):
    provider = Provider([503])

    def toggle():
        browser.put("/push/preferences", json={"enabled": False})
        browser.put("/push/preferences", json={"enabled": True})

    provider.after = toggle
    result = notifier(prepared, auth, provider, []).notify("admin", {"title": "Test"})
    assert result.skipped == 1
    assert len(provider.deliveries) == 1


def test_deleted_store_fails_closed(prepared):
    store, _ = prepared
    store.path.unlink()
    with pytest.raises(sqlite3.OperationalError):
        _ = store.public_key
    assert not store.path.exists()


def test_test_notification_is_fixed_current_device_only_and_rate_limited(prepared, auth, browser, monkeypatch):
    from src.push import notifier as notifier_module
    from tests.test_web_push import second_browser

    other = second_browser()
    monkeypatch.setenv("FIESTABOARD_WEB_PUSH_SUBJECT", "mailto:push@example.com")
    provider = Provider([201])
    monkeypatch.setattr(notifier_module, "PinnedTransport", lambda **kw: provider)
    result = browser.post("/push/test", json={})
    assert result.status_code == 200
    assert result.json() == {"sent": 1, "failed": 0, "skipped": 0, "expired": 0}
    assert browser.post("/push/test", json={}).status_code == 429
    assert other.post("/push/test", json={}).status_code == 409
    assert len(provider.deliveries) == 1


def test_retry_after_beyond_budget_does_not_retry_early(prepared, auth):
    class BusyProvider(Provider):
        def post(self, *args, **kwargs):
            response = super().post(*args, **kwargs)
            response.headers["Retry-After"] = "3600"
            return response

    provider = BusyProvider([429] * 3)
    sleeps = []
    result = notifier(prepared, auth, provider, sleeps).notify("admin", {"title": "Test"})
    assert result.skipped == 1
    assert len(provider.deliveries) == 1
    assert sleeps == []


def test_unsubscribe_reregister_and_restart_cannot_reset_test_cooldown(
    prepared, auth, browser, subscription, monkeypatch
):
    from src.push import notifier as notifier_module
    from src.push import store as store_module

    monkeypatch.setenv("FIESTABOARD_WEB_PUSH_SUBJECT", "mailto:push@example.com")
    provider = Provider([201, 201])
    monkeypatch.setattr(notifier_module, "PinnedTransport", lambda **kw: provider)
    assert browser.post("/push/test", json={}).status_code == 200
    assert browser.delete("/push/subscription").status_code == 200
    assert register(browser, subscription).status_code == 200
    monkeypatch.setattr(store_module, "_store", None)
    assert browser.post("/push/test", json={}).status_code == 429
    assert len(provider.deliveries) == 1


def test_serialized_utf8_payload_must_fit_web_push_record(prepared, auth):
    provider = Provider([201])
    with pytest.raises(ValueError, match="payload"):
        notifier(prepared, auth, provider, []).notify("admin", {"title": "Test", "url": "/" + "😀" * 1023})
    assert provider.deliveries == []


@pytest.mark.parametrize(
    "phase,action", [("dns", "expire"), ("dns", "revoke"), ("tls", "expire"), ("tls", "revoke"), ("tls", "delay")]
)
def test_slow_transport_rechecks_consent_and_refreshes_ttl(prepared, auth, monkeypatch, phase, action):
    import time

    from src.push import transport
    from src.push.notifier import PushNotifier

    clock = [time.time_ns() // 1_000_000]
    delivered = []

    def elapsed(boundary):
        if boundary != phase:
            return
        if action == "expire":
            clock[0] += 31_000
        elif action == "revoke":
            auth.sessions.revoke_session("admin", prepared[1].id)
        else:
            clock[0] += 1000

    def resolve(*args, **kwargs):
        elapsed("dns")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    class Wire:
        def settimeout(self, timeout):
            pass

        def connect(self, address):
            pass

        def close(self):
            pass

    def tls(context, sock, server_hostname):
        elapsed("tls")
        return sock

    def request(connection, method, target, body, headers):
        if connection.sock is None:
            connection.connect()
        delivered.append(headers)

    class Accepted:
        status = 201

        def getheader(self, key):
            return None

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: Wire())
    monkeypatch.setattr(transport.ssl.SSLContext, "wrap_socket", tls)
    monkeypatch.setattr(transport.PinnedHTTPSConnection, "request", request)
    monkeypatch.setattr(transport.PinnedHTTPSConnection, "getresponse", lambda self: Accepted())
    sender = PushNotifier(
        prepared[0],
        auth,
        clock_ms=lambda: clock[0],
        monotonic=lambda: clock[0] / 1000,
        subject="mailto:push@example.com",
    )
    result = sender.notify("admin", {"title": "Test"})
    if action == "delay":
        assert result.sent == 1
        assert int(delivered[0]["ttl"]) == 299
    else:
        assert result.skipped == 1
        assert delivered == []
