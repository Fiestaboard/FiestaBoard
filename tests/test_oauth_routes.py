"""The ``/oauth`` endpoints, and how the OAuth module meets the plugin system.

Drives the real FastAPI app. Only the outermost collaborators are substituted:
the plugin registry (a stub with one OAuth plugin) and the provider transport.
"""

from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest
from fastapi.testclient import TestClient

from src.oauth.client import ProviderClient
from src.oauth.service import OAuthService, RegistryConnectionSource
from src.oauth.state import StateSigner
from src.oauth.tokens import TokenSet, TokenStore
from src.plugins.registry import PluginRegistry

RELAY_BLOCK = {
    "provider_name": "Example Music",
    "flows": ["relay"],
    "authorization_url": "https://accounts.example.com/authorize",
    "token_url": "https://accounts.example.com/api/token",
    "scopes": ["read-playing"],
}
DEVICE_BLOCK = {
    "flows": ["device"],
    "device_authorization_url": "https://id.example.com/device/code",
    "token_url": "https://id.example.com/token",
}
TOKENS = {"access_token": "access-1", "expires_in": 3600, "refresh_token": "refresh-1"}
BOARD = {"board_url": "http://192.168.1.50:4420"}


class StubRegistry:
    """The four things RegistryConnectionSource asks a plugin registry for."""

    parse_instance_key = staticmethod(PluginRegistry.parse_instance_key)

    def __init__(self):
        self.plugins = {}
        self._manifests = {}
        self._configs = {}

    def add(self, key, name, oauth=None, config=None):
        raw = {"id": key.split(":")[0], "name": name, "version": "1.0.0"}
        if oauth is not None:
            raw["oauth"] = oauth
        self.plugins[key] = object()
        self._manifests[key] = SimpleNamespace(name=name, raw=raw)
        self._configs[key] = config or {}
        return self.plugins[key]

    def get_manifest(self, key):
        return self._manifests.get(key)

    def get_plugin_config(self, key):
        return self._configs.get(key)


class Provider:
    def __init__(self):
        self.calls = []
        self.replies = []

    def __call__(self, url, form):
        self.calls.append((url, dict(form)))
        return self.replies.pop(0)


@pytest.fixture
def registry(monkeypatch):
    stub = StubRegistry()
    stub.add("music", "Music", RELAY_BLOCK, {"client_id": "client-abc"})
    stub.add("git", "Git", DEVICE_BLOCK, {"client_id": "client-git"})
    stub.add("weather", "Weather")
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: stub)
    return stub


@pytest.fixture
def provider():
    return Provider()


@pytest.fixture
def service(registry, provider, tmp_path, monkeypatch):
    built = OAuthService(
        source=RegistryConnectionSource(),
        store=TokenStore(tmp_path / "oauth_tokens.json"),
        signer=StateSigner(b"k" * 32),
        client=ProviderClient(provider),
        poll_in_background=False,
    )
    monkeypatch.setattr("src.oauth.routes.get_oauth_service", lambda: built)
    monkeypatch.setattr("src.oauth.service.get_oauth_service", lambda: built)
    monkeypatch.delenv("FIESTABOARD_OAUTH_REDIRECT_URI", raising=False)
    return built


@pytest.fixture
def client(service):
    from src.api_server import app

    return TestClient(app, follow_redirects=False)


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")


def _state_from(start_response):
    return parse_qs(urlsplit(start_response.json()["authorization_url"]).query)["state"][0]


def _location_query(response):
    return {key: values[0] for key, values in parse_qs(urlsplit(response.headers["location"]).query).items()}


# ── Reading connections ─────────────────────────────────────────────────────


def test_list_names_only_plugins_that_declare_oauth(client):
    body = client.get("/oauth/connections").json()
    assert [connection["id"] for connection in body["connections"]] == ["git", "music"]


def test_list_tells_the_ui_which_redirect_uri_to_register(client):
    body = client.get("/oauth/connections").json()
    assert body["redirect_uri"] == "https://fiestaboard.app/auth/oauth/redirect.html"


def test_a_connection_reports_its_shape(client):
    assert client.get("/oauth/connections/music").json() == {
        "id": "music",
        "plugin_id": "music",
        "instance_label": None,
        "plugin_name": "Music",
        "provider_name": "Example Music",
        "flows": ["relay"],
        "configured": True,
        "status": "disconnected",
        "scopes": ["read-playing"],
        "expires_at": None,
        "connected_at": None,
        "device": None,
    }


def test_a_plugin_without_oauth_has_no_connection(client):
    response = client.get("/oauth/connections/weather")
    assert response.status_code == 404
    assert response.json() == {"detail": "No OAuth connection for plugin: weather"}


def test_an_unknown_plugin_has_no_connection(client):
    assert client.get("/oauth/connections/nope").status_code == 404


def test_no_response_ever_carries_a_token(client, service):
    service._store.put("music", TokenSet(access_token="access-1", refresh_token="refresh-1", expires_at=9e9))
    for path in ("/oauth/connections", "/oauth/connections/music"):
        text = client.get(path).text
        assert "access-1" not in text
        assert "refresh-1" not in text
    assert client.get("/oauth/connections/music").json()["status"] == "connected"


# ── Starting a flow ─────────────────────────────────────────────────────────


def test_authorize_answers_with_the_provider_url_for_a_relay_plugin(client):
    response = client.post("/oauth/connections/music/authorize", json=BOARD)
    assert response.status_code == 200
    body = response.json()
    assert body["flow"] == "relay"
    assert body["device"] is None
    query = parse_qs(urlsplit(body["authorization_url"]).query)
    assert query["redirect_uri"] == ["https://fiestaboard.app/auth/oauth/redirect.html"]
    assert query["client_id"] == ["client-abc"]


def test_authorize_answers_with_a_user_code_for_a_device_plugin(client, provider):
    provider.replies.append(
        (
            200,
            {
                "device_code": "dc",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://id.example.com/go",
                "expires_in": 600,
            },
        )
    )
    body = client.post("/oauth/connections/git/authorize", json={}).json()
    assert body["flow"] == "device"
    assert body["authorization_url"] == ""
    assert body["device"]["user_code"] == "ABCD-EFGH"
    assert "dc" not in body["device"].values()
    assert client.get("/oauth/connections/git").json()["device"]["status"] == "pending"


def test_authorize_puts_the_board_address_in_the_state_for_the_relay(client):
    import base64
    import json

    payload = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD)).split(".")[0]
    assert json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["b"] == "http://192.168.1.50:4420"


@pytest.mark.parametrize("body", [{}, {"board_url": ""}, {"board_url": "http://user:pw@192.168.1.50"}])
def test_authorize_a_relay_plugin_without_a_usable_board_address_is_a_400(client, body):
    response = client.post("/oauth/connections/music/authorize", json=body)
    assert response.status_code == 400
    assert "board's own address" in response.json()["detail"]


def test_authorize_without_a_client_id_is_a_400_that_says_what_to_do(client, registry):
    registry._configs["music"] = {}
    response = client.post("/oauth/connections/music/authorize", json=BOARD)
    assert response.status_code == 400
    assert "needs a client ID" in response.json()["detail"]


def test_authorize_with_a_flow_the_plugin_lacks_is_a_400(client):
    response = client.post("/oauth/connections/music/authorize", json={"flow": "device", **BOARD})
    assert response.status_code == 400


def test_authorize_with_a_flow_that_does_not_exist_is_a_422(client):
    assert client.post("/oauth/connections/music/authorize", json={"flow": "implicit"}).status_code == 422


def test_authorize_for_a_plugin_without_oauth_is_a_404(client):
    assert client.post("/oauth/connections/weather/authorize", json={}).status_code == 404


def test_a_provider_that_fails_to_start_a_device_flow_is_a_502(client, provider):
    provider.replies.append((500, {"message": "boom"}))
    response = client.post("/oauth/connections/git/authorize", json={})
    assert response.status_code == 502
    assert response.json() == {"detail": "The sign-in provider answered HTTP 500."}


# ── The callback ────────────────────────────────────────────────────────────


def test_a_valid_callback_connects_and_returns_to_the_integrations_page(client, provider, service):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    provider.replies.append((200, TOKENS))

    response = client.get("/oauth/callback", params={"code": "code-1", "state": state})

    assert response.status_code == 302
    assert response.headers["location"] == "../../integrations?tab=installed&oauth=connected&plugin=music"
    assert service.get_access_token("music") == "access-1"


def test_the_callback_response_is_not_cached_and_sends_no_referrer(client, provider):
    """The request URL carried an authorization code."""
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    provider.replies.append((200, TOKENS))
    response = client.get("/oauth/callback", params={"code": "code-1", "state": state})
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"


@pytest.mark.parametrize(
    ("browser_url", "lands_on"),
    [
        ("http://192.168.1.50:4420/api/oauth/callback", "http://192.168.1.50:4420/integrations"),
        (
            "http://homeassistant.local:8123/api/hassio_ingress/tok123/api/oauth/callback",
            "http://homeassistant.local:8123/api/hassio_ingress/tok123/integrations",
        ),
    ],
)
def test_the_return_redirect_resolves_to_the_app_root_behind_any_path_prefix(client, provider, browser_url, lands_on):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    provider.replies.append((200, TOKENS))
    location = client.get("/oauth/callback", params={"code": "c", "state": state}).headers["location"]
    assert urlsplit(urljoin(browser_url, location))._replace(query="").geturl() == lands_on


def test_a_tampered_state_redirects_with_a_reason_and_connects_nothing(client, provider, service):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    tampered = state[:-1] + ("A" if state[-1] != "A" else "B")

    response = client.get("/oauth/callback", params={"code": "code-1", "state": tampered})

    assert response.status_code == 302
    assert _location_query(response) == {"tab": "installed", "oauth": "error", "reason": "invalid_state"}
    assert provider.calls == []
    assert service.get_access_token("music") is None


def test_a_replayed_callback_is_refused(client, provider):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    provider.replies.append((200, TOKENS))
    client.get("/oauth/callback", params={"code": "code-1", "state": state})

    replay = client.get("/oauth/callback", params={"code": "code-1", "state": state})

    assert _location_query(replay) == {
        "tab": "installed",
        "oauth": "error",
        "plugin": "music",
        "reason": "invalid_state",
    }
    assert len(provider.calls) == 1


def test_a_callback_with_no_parameters_redirects_instead_of_erroring(client):
    response = client.get("/oauth/callback")
    assert response.status_code == 302
    assert _location_query(response)["reason"] == "invalid_state"


def test_a_declined_consent_names_the_plugin_and_the_reason(client):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    response = client.get("/oauth/callback", params={"error": "access_denied", "state": state})
    assert _location_query(response) == {
        "tab": "installed",
        "oauth": "error",
        "plugin": "music",
        "reason": "access_denied",
    }


def test_a_failed_code_exchange_names_the_plugin_and_the_reason(client, provider):
    state = _state_from(client.post("/oauth/connections/music/authorize", json=BOARD))
    provider.replies.append((400, {"error": "invalid_grant"}))
    response = client.get("/oauth/callback", params={"code": "c", "state": state})
    assert _location_query(response)["reason"] == "exchange_failed"


# ── Disconnecting ───────────────────────────────────────────────────────────


def test_disconnect_deletes_the_tokens_and_reports_the_new_status(client, service):
    service._store.put("music", TokenSet(access_token="access-1"))
    response = client.delete("/oauth/connections/music")
    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"
    assert service.get_access_token("music") is None


def test_disconnect_of_a_plugin_without_oauth_is_a_404(client):
    response = client.delete("/oauth/connections/weather")
    assert response.status_code == 404


# ── The auth boundary ───────────────────────────────────────────────────────


def test_the_callback_is_reachable_without_a_session(client, auth_enabled):
    """It arrives by cross-site navigation from the relay; its state is what authenticates it."""
    response = client.get("/oauth/callback", params={"code": "c", "state": "forged"})
    assert response.status_code == 302
    assert _location_query(response)["reason"] == "invalid_state"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/oauth/connections"),
        ("GET", "/oauth/connections/music"),
        ("POST", "/oauth/connections/music/authorize"),
        ("DELETE", "/oauth/connections/music"),
    ],
)
def test_everything_but_the_callback_requires_a_session(client, auth_enabled, method, path):
    response = client.request(method, path, json={} if method == "POST" else None)
    assert response.status_code in (401, 409)


def test_only_the_exact_callback_path_is_public():
    from src.auth.middleware import _is_public_path

    assert _is_public_path("/oauth/callback") is True
    assert _is_public_path("/api/oauth/callback") is True
    assert _is_public_path("/oauth/connections") is False
    assert _is_public_path("/oauth/callback/extra") is False
    assert _is_public_path("/oauth") is False


# ── Meeting the plugin system ───────────────────────────────────────────────


def test_a_named_instance_has_its_own_connection(client, registry):
    registry.add("music:kitchen", "Music", RELAY_BLOCK, {"client_id": "client-kitchen"})
    body = client.get("/oauth/connections/music:kitchen").json()
    assert (body["id"], body["plugin_id"], body["instance_label"]) == ("music:kitchen", "music", "kitchen")
    assert body["plugin_name"] == "Music (kitchen)"
    url = client.post("/oauth/connections/music:kitchen/authorize", json=BOARD).json()["authorization_url"]
    assert parse_qs(urlsplit(url).query)["client_id"] == ["client-kitchen"]


def test_get_oauth_token_on_a_plugin_returns_that_instances_token(service, registry):
    from src.plugins.base import PluginBase, PluginResult

    class Music(PluginBase):
        @property
        def plugin_id(self):
            return "music"

        def fetch_data(self):
            return PluginResult(available=True)

    base, kitchen = Music({"id": "music"}), Music({"id": "music"})
    registry.plugins["music"] = base
    registry.add("music:kitchen", "Music", RELAY_BLOCK)
    registry.plugins["music:kitchen"] = kitchen
    service._store.put("music", TokenSet(access_token="base-token"))

    assert base.get_oauth_token() == "base-token"
    assert kitchen.get_oauth_token() is None


def test_deleting_a_plugin_instance_deletes_its_tokens(service, monkeypatch):
    from unittest.mock import MagicMock

    from src.plugins.service import PluginService

    service._store.put("music:kitchen", TokenSet(access_token="kitchen-token"))
    service._store.put("music", TokenSet(access_token="base-token"))
    plugin_registry = MagicMock()
    plugin_registry.parse_instance_key = PluginRegistry.parse_instance_key
    plugin_registry.make_instance_key = PluginRegistry.make_instance_key
    plugin_registry.delete_instance.return_value = []
    plugins = PluginService(
        registry=plugin_registry, config_manager=MagicMock(), reset_display=lambda: None, reset_template=lambda: None
    )

    plugins.delete_instance("music", "kitchen")

    assert service._store.get("music:kitchen") is None
    assert service._store.get("music").access_token == "base-token"


def test_uninstalling_a_plugin_deletes_its_tokens_and_its_instances_tokens(service):
    from unittest.mock import MagicMock

    from src.plugins.service import PluginService

    for key in ("music", "music:kitchen", "git"):
        service._store.put(key, TokenSet(access_token=f"{key}-token"))
    plugin_registry = MagicMock()
    plugin_registry.list_plugins.return_value = [
        {"id": "music", "base_plugin_id": "music", "instance_label": None},
        {"id": "music:kitchen", "base_plugin_id": "music", "instance_label": "kitchen"},
    ]
    plugin_registry.uninstall_external_plugin.return_value = []
    plugins = PluginService(
        registry=plugin_registry, config_manager=MagicMock(), reset_display=lambda: None, reset_template=lambda: None
    )

    plugins.uninstall("music")

    assert service._store.ids() == ["git"]


def test_a_failed_uninstall_keeps_the_tokens(service):
    from unittest.mock import MagicMock

    from src.plugins.errors import PluginOperationRejected
    from src.plugins.service import PluginService

    service._store.put("music", TokenSet(access_token="base-token"))
    plugin_registry = MagicMock()
    plugin_registry.list_plugins.return_value = []
    plugin_registry.uninstall_external_plugin.return_value = ["Cannot uninstall a built-in plugin"]
    plugins = PluginService(registry=plugin_registry, config_manager=MagicMock())

    with pytest.raises(PluginOperationRejected):
        plugins.uninstall("music")

    assert service._store.get("music").access_token == "base-token"
