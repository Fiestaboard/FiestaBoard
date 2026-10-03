"""OAuthService: the relay flow, the device flow, and keeping tokens fresh.

The provider is a scripted transport and the clock is a variable, so every
branch is driven deliberately rather than waited for.
"""

import json
import stat
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

from src.oauth import pkce
from src.oauth.client import DEVICE_GRANT_TYPE, ProviderClient
from src.oauth.errors import (
    ConnectionNotConfigured,
    ConnectionNotFound,
    FlowNotSupported,
    InvalidBoardUrl,
    ProviderError,
)
from src.oauth.provider import parse_provider_block
from src.oauth.service import (
    DEFAULT_REDIRECT_URI,
    MAX_PENDING_AUTHORIZATIONS,
    REFRESH_MARGIN_SECONDS,
    ConnectionTarget,
    OAuthService,
    normalize_board_url,
)
from src.oauth.state import STATE_TTL_SECONDS, StatePayload, StateSigner
from src.oauth.tokens import TokenSet, TokenStore

NOW = 1_800_000_000.0
AUTHORIZE_URL = "https://accounts.example.com/authorize"
TOKEN_URL = "https://accounts.example.com/api/token"
DEVICE_URL = "https://accounts.example.com/device/code"
BOARD = "http://192.168.1.50:4420"

RELAY_BLOCK = {
    "provider_name": "Example Music",
    "flows": ["relay"],
    "authorization_url": AUTHORIZE_URL,
    "token_url": TOKEN_URL,
    "scopes": ["read-playing", "read-state"],
    "authorization_params": {"show_dialog": "true"},
}
DEVICE_BLOCK = {
    "flows": ["device"],
    "device_authorization_url": DEVICE_URL,
    "token_url": TOKEN_URL,
    "scopes": ["read"],
    "client_secret_setting": "client_secret",
}


class FakeSource:
    def __init__(self):
        self.targets = {}
        self.plugins = {}
        self.invalidated = []

    def add(self, connection_id, block, config=None, name="Music", plugin=None):
        plugin_id, _, label = connection_id.partition(":")
        plugin = plugin if plugin is not None else object()
        self.targets[connection_id] = ConnectionTarget(
            connection_id=connection_id,
            plugin_id=plugin_id,
            instance_label=label or None,
            plugin_name=name,
            provider=parse_provider_block(block, name),
            config=config if config is not None else {"client_id": "client-abc"},
            plugin=plugin,
        )
        self.plugins[connection_id] = plugin
        return plugin

    def get(self, connection_id):
        return self.targets.get(connection_id)

    def all(self):
        return list(self.targets.values())

    def id_for(self, plugin):
        return next((cid for cid, candidate in self.plugins.items() if candidate is plugin), None)

    def invalidate(self, connection_id):
        self.invalidated.append(connection_id)


class FakeProvider:
    """A scripted token/device endpoint that records every form it is sent."""

    def __init__(self):
        self.calls = []
        self.headers = []
        self.replies = []

    def reply(self, body, status=200):
        self.replies.append((status, body))
        return self

    def fail(self, exc):
        self.replies.append(exc)
        return self

    def __call__(self, url, form, headers=None):
        self.calls.append((url, dict(form)))
        self.headers.append(headers)
        assert self.replies, f"unexpected provider call to {url}: {form}"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class Clock:
    def __init__(self, now=NOW):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def source():
    return FakeSource()


@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / "oauth_tokens.json")


@pytest.fixture
def signer():
    return StateSigner(b"k" * 32)


@pytest.fixture
def service(source, store, signer, provider, clock):
    return OAuthService(
        source=source,
        store=store,
        signer=signer,
        client=ProviderClient(provider),
        clock=clock,
        redirect_uri="https://relay.example/oauth/redirect.html",
        poll_in_background=False,
    )


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _begin_relay(service, connection_id="music"):
    return _query(service.start(connection_id, board_url=BOARD).authorization_url)


TOKENS = {"access_token": "access-1", "token_type": "Bearer", "expires_in": 3600, "refresh_token": "refresh-1"}


# ── Starting the relay flow ─────────────────────────────────────────────────


def test_relay_start_sends_the_browser_to_the_provider_with_pkce(service, source):
    source.add("music", RELAY_BLOCK)
    start = service.start("music", board_url=BOARD)
    assert start.flow == "relay"
    assert start.authorization_url.startswith(f"{AUTHORIZE_URL}?")
    query = _query(start.authorization_url)
    assert query["response_type"] == "code"
    assert query["client_id"] == "client-abc"
    assert query["redirect_uri"] == "https://relay.example/oauth/redirect.html"
    assert query["scope"] == "read-playing read-state"
    assert query["code_challenge_method"] == "S256"
    assert query["show_dialog"] == "true"
    assert len(query["code_challenge"]) == 43


def test_the_pkce_verifier_is_never_in_the_url_the_browser_sees(service, source, provider):
    source.add("music", RELAY_BLOCK)
    start = service.start("music", board_url=BOARD)
    query = _query(start.authorization_url)
    provider.reply(TOKENS)
    service.complete_authorization(state=query["state"], code="code-1", error=None)
    verifier = provider.calls[0][1]["code_verifier"]
    assert verifier not in start.authorization_url
    assert pkce.challenge_for(verifier) == query["code_challenge"]


def test_relay_start_keeps_an_existing_query_string_on_the_authorization_url(service, source):
    source.add("music", {**RELAY_BLOCK, "authorization_url": f"{AUTHORIZE_URL}?tenant=common"})
    url = service.start("music", board_url=BOARD).authorization_url
    assert url.startswith(f"{AUTHORIZE_URL}?tenant=common&")
    assert _query(url)["tenant"] == "common"


def test_start_for_a_plugin_without_oauth_is_not_found(service):
    with pytest.raises(ConnectionNotFound):
        service.start("weather")


def test_start_without_a_client_id_is_refused(service, source):
    source.add("music", RELAY_BLOCK, config={})
    with pytest.raises(ConnectionNotConfigured):
        service.start("music", board_url=BOARD)


def test_start_uses_the_manifest_client_id_when_the_user_set_none(service, source):
    source.add("music", {**RELAY_BLOCK, "client_id": "shared-public-id"}, config={})
    assert _begin_relay(service)["client_id"] == "shared-public-id"


def test_start_with_a_flow_the_plugin_does_not_declare_is_refused(service, source):
    source.add("music", RELAY_BLOCK)
    with pytest.raises(FlowNotSupported):
        service.start("music", "device")


def test_redirect_uri_defaults_to_the_public_relay(source, store, signer, monkeypatch):
    monkeypatch.delenv("FIESTABOARD_OAUTH_REDIRECT_URI", raising=False)
    default = OAuthService(source=source, store=store, signer=signer)
    assert default.redirect_uri == DEFAULT_REDIRECT_URI == "https://fiestaboard.app/auth/oauth/redirect"


def test_redirect_uri_can_be_overridden_by_environment(source, store, signer, monkeypatch):
    monkeypatch.setenv("FIESTABOARD_OAUTH_REDIRECT_URI", "https://relay.internal.example/r/redirect.html")
    overridden = OAuthService(source=source, store=store, signer=signer)
    assert overridden.redirect_uri == "https://relay.internal.example/r/redirect.html"


# ── Telling the relay which board to come back to ───────────────────────────


def _board_in_state(state):
    """Read the address the way the relay page does: the payload is not secret, only signed."""
    import base64

    payload = state.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["b"]


def test_the_state_tells_the_relay_which_board_to_return_to(service, source):
    source.add("music", RELAY_BLOCK)
    assert _board_in_state(_begin_relay(service)["state"]) == BOARD


@pytest.mark.parametrize(
    ("sent", "carried"),
    [
        ("http://192.168.1.50:4420/", "http://192.168.1.50:4420"),
        ("  http://fiestaboard.local:4420  ", "http://fiestaboard.local:4420"),
        ("https://fiestaboard.local", "https://fiestaboard.local"),
        (
            "http://homeassistant.local:8123/api/hassio_ingress/tok123/",
            "http://homeassistant.local:8123/api/hassio_ingress/tok123",
        ),
    ],
)
def test_the_board_address_is_carried_without_a_trailing_slash(sent, carried):
    assert normalize_board_url(sent) == carried


@pytest.mark.parametrize(
    "board_url",
    [
        None,
        "",
        "   ",
        "192.168.1.50:4420",
        "ftp://192.168.1.50",
        "javascript:alert(1)",
        "http://user:pass@192.168.1.50",
        "http://192.168.1.50/?next=https://evil.example",
        "http://192.168.1.50/#x",
        "http://192.168.1.50?",
        "http://",
        "http://192.168.1.50:notaport",
        "http://" + "a" * 600 + ".local",
    ],
)
def test_a_relay_flow_will_not_start_without_a_plain_board_address(service, source, board_url):
    source.add("music", RELAY_BLOCK)
    with pytest.raises(InvalidBoardUrl):
        service.start("music", board_url=board_url)
    assert service._pending == {}


def test_the_board_address_cannot_be_swapped_after_signing(service, source, provider):
    """The relay cannot check the signature, but the board does when the code comes back."""
    import base64

    source.add("music", RELAY_BLOCK)
    payload, _, signature = _begin_relay(service)["state"].partition(".")
    body = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    body["b"] = "http://192.168.1.66:4420"
    swapped = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).rstrip(b"=").decode()

    outcome = service.complete_authorization(state=f"{swapped}.{signature}", code="code-1", error=None)

    assert (outcome.connected, outcome.reason) == (False, "invalid_state")
    assert provider.calls == []


# ── Finishing the relay flow ────────────────────────────────────────────────


def test_a_valid_callback_exchanges_the_code_and_stores_the_tokens(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    query = _begin_relay(service)
    provider.reply({**TOKENS, "scope": "read-playing"})

    outcome = service.complete_authorization(state=query["state"], code="code-1", error=None)

    assert (outcome.connected, outcome.connection_id, outcome.reason) == (True, "music", "")
    url, form = provider.calls[0]
    assert url == TOKEN_URL
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "code-1"
    assert form["client_id"] == "client-abc"
    assert form["redirect_uri"] == "https://relay.example/oauth/redirect.html"
    assert "client_secret" not in form
    tokens = store.get("music")
    assert tokens.access_token == "access-1"
    assert tokens.refresh_token == "refresh-1"
    assert tokens.expires_at == NOW + 3600
    assert tokens.scopes == ("read-playing",)
    assert service.get_connection("music").status == "connected"


def test_requested_scopes_are_recorded_when_the_provider_echoes_none(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    query = _begin_relay(service)
    provider.reply(TOKENS)
    service.complete_authorization(state=query["state"], code="code-1", error=None)
    assert store.get("music").scopes == ("read-playing", "read-state")


def test_a_confidential_client_sends_its_secret_to_the_token_endpoint_only(service, source, provider):
    source.add(
        "music",
        {**RELAY_BLOCK, "client_secret_setting": "client_secret"},
        config={"client_id": "client-abc", "client_secret": "example-secret"},
    )
    start = service.start("music", board_url=BOARD)
    assert "example-secret" not in start.authorization_url
    provider.reply(TOKENS)
    service.complete_authorization(state=_query(start.authorization_url)["state"], code="c", error=None)
    assert provider.calls[0][1]["client_secret"] == "example-secret"


def test_a_state_cannot_be_used_twice(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    query = _begin_relay(service)
    provider.reply(TOKENS)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected

    replay = service.complete_authorization(state=query["state"], code="code-2", error=None)

    assert (replay.connected, replay.reason) == (False, "invalid_state")
    assert len(provider.calls) == 1, "a replayed state must never reach the token endpoint"


def test_a_tampered_state_is_rejected_without_calling_the_provider(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    tampered = state[:-1] + ("A" if state[-1] != "A" else "B")

    outcome = service.complete_authorization(state=tampered, code="code-1", error=None)

    assert (outcome.connected, outcome.connection_id, outcome.reason) == (False, None, "invalid_state")
    assert provider.calls == []
    assert store.get("music") is None


def test_a_state_signed_by_another_install_is_rejected(service, source, provider):
    source.add("music", RELAY_BLOCK)
    foreign = StateSigner(b"x" * 32).sign(StatePayload("n", "music", int(NOW) + 600))
    outcome = service.complete_authorization(state=foreign, code="code-1", error=None)
    assert (outcome.connected, outcome.reason) == (False, "invalid_state")
    assert provider.calls == []


def test_a_correctly_signed_state_for_a_flow_that_was_never_started_is_rejected(service, source, signer, provider):
    """Signature alone is not enough: the board must also remember starting the flow."""
    source.add("music", RELAY_BLOCK)
    orphan = signer.sign(StatePayload("never-issued", "music", int(NOW) + 600))
    outcome = service.complete_authorization(state=orphan, code="code-1", error=None)
    assert (outcome.connected, outcome.connection_id, outcome.reason) == (False, "music", "invalid_state")
    assert provider.calls == []


def test_an_expired_state_is_rejected(service, source, provider, clock):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    clock.now += STATE_TTL_SECONDS

    outcome = service.complete_authorization(state=state, code="code-1", error=None)

    assert (outcome.connected, outcome.reason) == (False, "expired")
    assert provider.calls == []


@pytest.mark.parametrize("state", [None, "", "garbage"])
def test_a_missing_or_unsigned_state_is_rejected(service, state, provider):
    outcome = service.complete_authorization(state=state, code="code-1", error=None)
    assert (outcome.connected, outcome.reason) == (False, "invalid_state")
    assert provider.calls == []


def test_a_user_declining_consent_is_reported_and_spends_the_state(service, source, provider):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]

    declined = service.complete_authorization(state=state, code=None, error="access_denied")
    assert (declined.connected, declined.connection_id, declined.reason) == (False, "music", "access_denied")

    retried = service.complete_authorization(state=state, code="code-1", error=None)
    assert retried.reason == "invalid_state"
    assert provider.calls == []


def test_any_other_provider_error_is_reported_generically(service, source):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    outcome = service.complete_authorization(state=state, code=None, error="server_error")
    assert outcome.reason == "provider_error"


def test_a_callback_with_neither_code_nor_error_is_a_provider_error(service, source):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    assert service.complete_authorization(state=state, code=None, error=None).reason == "provider_error"


def test_a_rejected_code_exchange_stores_nothing(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    provider.reply({"error": "invalid_grant", "error_description": "code already used"}, status=400)

    outcome = service.complete_authorization(state=state, code="code-1", error=None)

    assert (outcome.connected, outcome.connection_id, outcome.reason) == (False, "music", "exchange_failed")
    assert store.get("music") is None


def test_an_unreachable_token_endpoint_is_an_exchange_failure(service, source, provider):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    provider.fail(ProviderError("down"))
    assert service.complete_authorization(state=state, code="c", error=None).reason == "exchange_failed"


def test_an_error_object_served_with_http_200_is_still_a_failure(service, source, provider, store):
    """GitHub reports OAuth errors with a 200; the body decides, not the status."""
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    provider.reply({"error": "bad_verification_code"}, status=200)
    assert service.complete_authorization(state=state, code="c", error=None).reason == "exchange_failed"
    assert store.get("music") is None


def test_two_flows_for_different_plugins_do_not_cross(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    source.add("calendar", RELAY_BLOCK, config={"client_id": "client-cal"}, name="Calendar")
    music_state = _begin_relay(service, "music")["state"]
    calendar_state = _begin_relay(service, "calendar")["state"]

    provider.reply({**TOKENS, "access_token": "calendar-token"})
    assert service.complete_authorization(state=calendar_state, code="c", error=None).connection_id == "calendar"

    assert provider.calls[0][1]["client_id"] == "client-cal"
    assert store.get("calendar").access_token == "calendar-token"
    assert store.get("music") is None
    provider.reply({**TOKENS, "access_token": "music-token"})
    assert service.complete_authorization(state=music_state, code="c", error=None).connection_id == "music"
    assert store.get("music").access_token == "music-token"


def test_abandoned_flows_are_capped(service, source):
    source.add("music", RELAY_BLOCK)
    states = [_begin_relay(service)["state"] for _ in range(MAX_PENDING_AUTHORIZATIONS + 5)]
    assert len(service._pending) == MAX_PENDING_AUTHORIZATIONS
    oldest = service.complete_authorization(state=states[0], code="c", error=None)
    assert oldest.reason == "invalid_state"


# ── Device flow ─────────────────────────────────────────────────────────────

DEVICE_ANSWER = {
    "device_code": "device-secret",
    "user_code": "WDJB-MJHT",
    "verification_uri": "https://example.com/device",
    "verification_uri_complete": "https://example.com/device?user_code=WDJB-MJHT",
    "expires_in": 900,
    "interval": 5,
}


@pytest.fixture
def device(source):
    source.add("git", DEVICE_BLOCK, config={"client_id": "client-abc", "client_secret": "example-secret"}, name="Git")
    return "git"


def test_device_start_returns_the_code_for_the_user_to_type(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    start = service.start(device)

    assert start.flow == "device"
    assert start.device.status == "pending"
    assert start.device.user_code == "WDJB-MJHT"
    assert start.device.verification_uri == "https://example.com/device"
    assert start.device.verification_uri_complete == "https://example.com/device?user_code=WDJB-MJHT"
    assert start.device.expires_at == NOW + 900
    assert provider.calls == [(DEVICE_URL, {"client_id": "client-abc", "scope": "read"})]


def test_a_device_flow_needs_no_board_address(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    assert service.start(device, board_url=None).flow == "device"


def test_the_device_code_is_never_part_of_the_reported_status(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    assert "device-secret" not in repr(service.get_connection(device))


def test_googles_verification_url_spelling_is_accepted(service, device, provider):
    answer = {k: v for k, v in DEVICE_ANSWER.items() if k != "verification_uri"}
    provider.reply({**answer, "verification_url": "https://example.com/device"})
    assert service.start(device).device.verification_uri == "https://example.com/device"


def test_an_incomplete_device_answer_is_a_provider_error(service, device, provider):
    provider.reply({"user_code": "WDJB-MJHT"})
    with pytest.raises(ProviderError):
        service.start(device)


def test_polling_while_the_user_has_not_approved_keeps_the_flow_pending(service, device, provider, store):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({"error": "authorization_pending"}, status=400)

    assert service.poll_device(device) is True

    url, form = provider.calls[1]
    assert url == TOKEN_URL
    assert form == {
        "grant_type": DEVICE_GRANT_TYPE,
        "device_code": "device-secret",
        "client_id": "client-abc",
        "client_secret": "example-secret",
    }
    assert service.get_connection(device).device.status == "pending"
    assert store.get(device) is None


def test_approval_stores_the_tokens_and_ends_the_flow(service, device, provider, store):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply(TOKENS)

    assert service.poll_device(device) is False

    assert store.get(device).access_token == "access-1"
    status = service.get_connection(device)
    assert status.status == "connected"
    assert status.device is None


def test_slow_down_lengthens_the_polling_interval_by_five_seconds(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({"error": "slow_down"}, status=400)

    assert service.poll_device(device) is True
    assert service._device[device].interval == 10


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [("expired_token", "expired", ""), ("access_denied", "denied", ""), ("invalid_client", "failed", "invalid_client")],
)
def test_a_terminal_device_error_ends_the_flow_with_a_status(service, device, provider, store, error, status, detail):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({"error": error}, status=400)

    assert service.poll_device(device) is False

    reported = service.get_connection(device).device
    assert (reported.status, reported.detail) == (status, detail)
    assert store.get(device) is None
    assert service.poll_device(device) is False, "a finished flow must not be polled again"
    assert len(provider.calls) == 2


def test_a_device_code_past_its_lifetime_expires_without_asking_the_provider(service, device, provider, clock):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    clock.now += 900

    assert service.poll_device(device) is False
    assert service.get_connection(device).device.status == "expired"
    assert len(provider.calls) == 1


def test_a_network_failure_while_polling_is_retried_not_treated_as_a_verdict(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.fail(ProviderError("connection reset"))

    assert service.poll_device(device) is True
    assert service.get_connection(device).device.status == "pending"


def test_starting_again_replaces_the_earlier_device_flow(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({**DEVICE_ANSWER, "device_code": "device-2", "user_code": "NEW-CODE"})
    service.start(device)
    provider.reply({"error": "authorization_pending"}, status=400)

    service.poll_device(device)

    assert provider.calls[-1][1]["device_code"] == "device-2"
    assert service.get_connection(device).device.user_code == "NEW-CODE"


def test_polling_a_connection_with_no_device_flow_does_nothing(service, device, provider):
    assert service.poll_device(device) is False
    assert provider.calls == []


def test_the_background_poller_waits_the_providers_interval_between_polls(
    source, store, signer, provider, clock, device
):
    """Polling faster than the interval gets a real client rate-limited."""
    slept = []
    done = threading.Event()

    def fake_sleep(seconds):
        slept.append(seconds)

    service = OAuthService(
        source=source,
        store=store,
        signer=signer,
        client=ProviderClient(provider),
        clock=clock,
        sleep=fake_sleep,
        poll_in_background=False,
    )
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({"error": "authorization_pending"}, status=400)
    provider.reply({"error": "slow_down"}, status=400)
    provider.reply(TOKENS)

    poller = threading.Thread(target=lambda: (service._poll_device_until_done(service._device[device]), done.set()))
    poller.start()
    assert done.wait(5)

    assert slept == [5, 5, 10]
    assert store.get(device).access_token == "access-1"


def test_a_superseded_poller_stops_without_touching_the_new_flow(source, store, signer, provider, clock, device):
    service = OAuthService(
        source=source,
        store=store,
        signer=signer,
        client=ProviderClient(provider),
        clock=clock,
        sleep=lambda _seconds: None,
        poll_in_background=False,
    )
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    first = service._device[device]
    provider.reply({**DEVICE_ANSWER, "device_code": "device-2"})
    service.start(device)
    calls_before = len(provider.calls)

    service._poll_device_until_done(first)

    assert len(provider.calls) == calls_before


# ── Handing out tokens ──────────────────────────────────────────────────────


def _connected(store, connection_id="music", **overrides):
    values = {
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_at": NOW + 3600,
        "scopes": ("read-playing",),
        "obtained_at": NOW - 100,
    }
    store.put(connection_id, TokenSet(**{**values, **overrides}))


def test_no_token_for_a_plugin_that_never_connected(service, source):
    source.add("music", RELAY_BLOCK)
    assert service.get_access_token("music") is None


def test_a_fresh_token_is_returned_without_calling_the_provider(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    assert service.get_access_token("music") == "access-1"
    assert provider.calls == []


def test_a_token_without_an_expiry_is_treated_as_long_lived(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=None)
    assert service.get_access_token("music") == "access-1"
    assert provider.calls == []


def test_a_token_inside_the_refresh_margin_is_refreshed_before_use(service, source, store, provider, clock):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW + REFRESH_MARGIN_SECONDS - 1)
    provider.reply({"access_token": "access-2", "expires_in": 3600})

    assert service.get_access_token("music") == "access-2"

    url, form = provider.calls[0]
    assert url == TOKEN_URL
    assert form == {"grant_type": "refresh_token", "refresh_token": "refresh-1", "client_id": "client-abc"}
    stored = store.get("music")
    assert stored.access_token == "access-2"
    assert stored.expires_at == NOW + 3600


def test_a_refresh_that_returns_no_new_refresh_token_keeps_the_old_one(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    service.get_access_token("music")
    assert store.get("music").refresh_token == "refresh-1"


def test_a_rotated_refresh_token_replaces_the_old_one(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"access_token": "access-2", "expires_in": 3600, "refresh_token": "refresh-2"})
    service.get_access_token("music")
    assert store.get("music").refresh_token == "refresh-2"


def test_a_refresh_keeps_the_original_connection_time_and_scopes(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    service.get_access_token("music")
    stored = store.get("music")
    assert stored.obtained_at == NOW - 100
    assert stored.scopes == ("read-playing",)


@pytest.mark.parametrize("error", ["invalid_grant", "invalid_client", "unauthorized_client"])
def test_a_refused_refresh_marks_the_connection_for_reconnecting(service, source, store, provider, error):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"error": error}, status=400)

    assert service.get_access_token("music") is None
    assert service.get_connection("music").status == "reauthorization_required"

    assert service.get_access_token("music") is None
    assert len(provider.calls) == 1, "a revoked grant must not be retried on every fetch"


def test_a_failed_refresh_still_serves_a_token_that_has_not_expired_yet(service, source, store, provider):
    """A provider outage inside the refresh margin must not take the plugin down early."""
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW + 10)
    provider.fail(ProviderError("timeout"))
    assert service.get_access_token("music") == "access-1"
    assert service.get_connection("music").status == "connected"


def test_a_failed_refresh_of_an_expired_token_serves_nothing(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.fail(ProviderError("timeout"))
    assert service.get_access_token("music") is None
    assert service.get_connection("music").status == "connected", "an outage is not a revoked grant"


def test_a_temporary_token_endpoint_error_does_not_demand_reconnecting(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"error": "temporarily_unavailable"}, status=503)
    assert service.get_access_token("music") is None
    assert service.get_connection("music").status == "connected"


def test_an_expired_token_with_no_refresh_token_serves_nothing(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, refresh_token="", expires_at=NOW - 1)
    assert service.get_access_token("music") is None
    assert provider.calls == []


def test_concurrent_fetches_refresh_only_once(source, store, signer, clock):
    """Rotating providers invalidate the old refresh token on first use.

    The provider holds its answer until every caller has had time to arrive,
    so without the per-connection lock all eight would be mid-refresh at once.
    """
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    release = threading.Event()
    calls = []

    def slow_provider(url, form):
        calls.append(form)
        assert release.wait(5)
        return 200, {"access_token": "access-2", "expires_in": 3600, "refresh_token": "refresh-2"}

    service = OAuthService(source=source, store=store, signer=signer, client=ProviderClient(slow_provider), clock=clock)
    results = []
    threads = [threading.Thread(target=lambda: results.append(service.get_access_token("music"))) for _ in range(8)]
    for thread in threads:
        thread.start()
    threading.Event().wait(0.3)
    release.set()
    for thread in threads:
        thread.join(5)

    assert results == ["access-2"] * 8
    assert len(calls) == 1


def test_a_plugin_object_gets_its_own_instances_token(service, source, store):
    base = source.add("music", RELAY_BLOCK)
    kitchen = source.add("music:kitchen", RELAY_BLOCK)
    _connected(store, "music", access_token="base-token")
    _connected(store, "music:kitchen", access_token="kitchen-token")

    assert service.access_token_for(base) == "base-token"
    assert service.access_token_for(kitchen) == "kitchen-token"
    assert service.access_token_for(object()) is None


def test_plugins_on_the_same_provider_do_not_share_a_connection(service, source, store):
    source.add("music", RELAY_BLOCK)
    source.add("playlists", RELAY_BLOCK, name="Playlists")
    _connected(store, "music")
    assert service.get_access_token("music") == "access-1"
    assert service.get_access_token("playlists") is None
    assert service.get_connection("playlists").status == "disconnected"


# ── Status, disconnecting, storage ──────────────────────────────────────────


def test_status_before_connecting_shows_what_will_be_requested(service, source):
    source.add("music:kitchen", RELAY_BLOCK, name="Music (kitchen)")
    status = service.get_connection("music:kitchen")
    assert status.id == "music:kitchen"
    assert (status.plugin_id, status.instance_label) == ("music", "kitchen")
    assert status.provider_name == "Example Music"
    assert status.flows == ("relay",)
    assert status.configured is True
    assert status.status == "disconnected"
    assert status.scopes == ("read-playing", "read-state")
    assert (status.expires_at, status.connected_at, status.device) == (None, None, None)


def test_status_reports_unconfigured_when_there_is_no_client_id(service, source):
    source.add("music", RELAY_BLOCK, config={})
    assert service.get_connection("music").configured is False


def test_status_never_contains_a_token(service, source, store):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    rendered = repr(service.get_connection("music"))
    assert "access-1" not in rendered
    assert "refresh-1" not in rendered


def test_list_includes_only_plugins_that_declare_oauth(service, source):
    source.add("music", RELAY_BLOCK)
    source.add("git", DEVICE_BLOCK, name="Git")
    assert sorted(status.id for status in service.list_connections()) == ["git", "music"]


def test_disconnect_deletes_the_tokens(service, source, store):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    assert service.disconnect("music").status == "disconnected"
    assert store.get("music") is None
    assert service.get_access_token("music") is None


def test_disconnect_drops_the_plugins_cached_results(service, source, store):
    """Otherwise the board keeps showing the account's data until the cache expires."""
    source.add("music", RELAY_BLOCK)
    _connected(store)
    service.disconnect("music")
    assert source.invalidated == ["music"]


def test_a_new_sign_in_drops_the_plugins_cached_results(service, source, provider):
    """A reconnect to a different account must not keep serving the old account's data."""
    source.add("music", RELAY_BLOCK)
    query = _begin_relay(service)
    provider.reply(TOKENS)
    service.complete_authorization(state=query["state"], code="code-1", error=None)
    assert source.invalidated == ["music"]


def test_an_approved_device_code_drops_the_plugins_cached_results(service, device, source, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply(TOKENS)
    service.poll_device(device)
    assert source.invalidated == [device]


def test_a_token_refresh_leaves_the_plugins_cache_alone(service, source, store, provider):
    """It happens inside the plugin's own fetch; the data is still the same account's."""
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW - 1)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    service.get_access_token("music")
    assert source.invalidated == []


def test_a_failed_sign_in_leaves_the_plugins_cache_alone(service, source):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    service.complete_authorization(state=state, code=None, error="access_denied")
    assert source.invalidated == []


def test_disconnect_cancels_flows_in_progress(service, source, device, provider):
    source.add("music", RELAY_BLOCK)
    state = _begin_relay(service)["state"]
    provider.reply(DEVICE_ANSWER)
    service.start(device)

    service.disconnect("music")
    service.disconnect(device)

    assert service.complete_authorization(state=state, code="c", error=None).reason == "invalid_state"
    assert service.get_connection(device).device is None


def test_disconnect_of_an_unknown_plugin_is_not_found(service):
    with pytest.raises(ConnectionNotFound):
        service.disconnect("weather")


def test_forget_removes_tokens_for_a_plugin_that_no_longer_exists(service, store):
    _connected(store, "uninstalled")
    assert service.forget("uninstalled") is True
    assert store.get("uninstalled") is None
    assert service.forget("uninstalled") is False


def test_the_token_file_is_owner_only(store, tmp_path):
    _connected(store)
    mode = stat.S_IMODE((tmp_path / "oauth_tokens.json").stat().st_mode)
    assert mode == 0o600


def test_tokens_survive_a_restart(store, tmp_path):
    _connected(store, needs_reauthorization=True)
    reloaded = TokenStore(tmp_path / "oauth_tokens.json").get("music")
    assert reloaded == store.get("music")
    assert reloaded.scopes == ("read-playing",)
    assert reloaded.needs_reauthorization is True


def test_a_corrupt_token_file_starts_empty_rather_than_crashing(tmp_path):
    path = tmp_path / "oauth_tokens.json"
    path.write_text("{not json", encoding="utf-8")
    assert TokenStore(path).ids() == []


def test_the_token_file_has_a_schema_version(store, tmp_path):
    _connected(store)
    assert json.loads((tmp_path / "oauth_tokens.json").read_text())["schema_version"] == 1


# ── 9.9.0 manifest fields ───────────────────────────────────────────────────

TIKTOK_BLOCK = {**RELAY_BLOCK, "client_id_param": "client_key", "scope_separator": ","}
TWITCH_BLOCK = {
    **DEVICE_BLOCK,
    "scopes": ["user:read:email", "channel:read:subscriptions"],
    "device_scope_param": "scopes",
    "device_poll_scope": True,
}
HA_BLOCK = {
    "provider_name": "Home Assistant",
    "flows": ["relay"],
    "endpoint_base_setting": "base_url",
    "authorization_url": "/auth/authorize",
    "token_url": "/auth/token",
    "client_id": "https://fiestaboard.app/",
}


def test_a_custom_client_id_param_is_used_in_the_authorize_url(service, source):
    source.add("tiktok", TIKTOK_BLOCK)
    query = _begin_relay(service, "tiktok")
    assert query["client_key"] == "client-abc"
    assert "client_id" not in query


def test_scopes_are_joined_with_the_declared_separator(service, source):
    source.add("tiktok", TIKTOK_BLOCK)
    assert _begin_relay(service, "tiktok")["scope"] == "read-playing,read-state"


def test_default_scope_join_is_still_a_space(service, source):
    source.add("music", RELAY_BLOCK)
    assert _begin_relay(service)["scope"] == "read-playing read-state"


def test_a_custom_client_id_param_is_used_in_the_code_exchange(service, source, provider):
    source.add("tiktok", TIKTOK_BLOCK)
    query = _begin_relay(service, "tiktok")
    provider.reply(TOKENS)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected
    form = provider.calls[0][1]
    assert form["client_key"] == "client-abc"
    assert "client_id" not in form


def test_a_custom_client_id_param_is_used_on_refresh(service, source, store, provider):
    source.add("tiktok", TIKTOK_BLOCK)
    _connected(store, "tiktok", expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    assert service.get_access_token("tiktok") == "access-2"
    assert provider.calls[0][1] == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "client_key": "client-abc",
    }


def test_device_flow_uses_the_custom_client_id_and_scope_params(service, source, provider):
    source.add("twitch", {**TWITCH_BLOCK, "client_id_param": "client_key"}, config={"client_id": "client-abc"})
    provider.reply(DEVICE_ANSWER)
    service.start("twitch")
    assert provider.calls[0] == (
        DEVICE_URL,
        {"client_key": "client-abc", "scopes": "user:read:email channel:read:subscriptions"},
    )


def test_twitch_device_poll_sends_the_scopes(service, source, provider):
    source.add("twitch", TWITCH_BLOCK, config={"client_id": "client-abc"})
    provider.reply(DEVICE_ANSWER)
    service.start("twitch")
    provider.reply({"error": "authorization_pending"})
    service.poll_device("twitch")
    assert provider.calls[1][1] == {
        "grant_type": DEVICE_GRANT_TYPE,
        "device_code": "device-secret",
        "client_id": "client-abc",
        "scopes": "user:read:email channel:read:subscriptions",
    }


def test_a_plain_device_poll_sends_no_scope(service, device, provider):
    provider.reply(DEVICE_ANSWER)
    service.start(device)
    provider.reply({"error": "authorization_pending"})
    service.poll_device(device)
    assert "scope" not in provider.calls[1][1]


def test_endpoints_come_from_the_plugins_base_url_setting(service, source, provider):
    source.add("ha", HA_BLOCK, config={"base_url": "http://homeassistant.local:8123/"})
    url = service.start("ha", board_url=BOARD).authorization_url
    assert url.startswith("http://homeassistant.local:8123/auth/authorize?")
    query = _query(url)
    assert query["client_id"] == "https://fiestaboard.app/"
    provider.reply(TOKENS)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected
    assert provider.calls[0][0] == "http://homeassistant.local:8123/auth/token"


def test_refresh_uses_the_settings_based_token_url(service, source, store, provider):
    source.add("ha", HA_BLOCK, config={"base_url": "https://ha.example.com"})
    _connected(store, "ha", expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 1800})
    assert service.get_access_token("ha") == "access-2"
    assert provider.calls[0][0] == "https://ha.example.com/auth/token"


@pytest.mark.parametrize("base", [None, "", "http://203.0.113.9:8123"])
def test_a_missing_or_public_http_base_is_not_configured(service, source, base):
    source.add("ha", HA_BLOCK, config={"base_url": base})
    assert service.get_connection("ha").configured is False
    with pytest.raises(ConnectionNotConfigured, match="home network"):
        service.start("ha", board_url=BOARD)


def test_a_lan_base_is_configured(service, source):
    source.add("ha", HA_BLOCK, config={"base_url": "http://192.168.1.20:8123"})
    assert service.get_connection("ha").configured is True


# ── Paste what the provider showed you ──────────────────────────────────────

from src.oauth.errors import PastedCodeRejected  # noqa: E402


def _relay_state(service, connection_id="music"):
    return _begin_relay(service, connection_id)["state"]


def _reject_reason(service, connection_id, pasted):
    with pytest.raises(PastedCodeRejected) as caught:
        service.complete_pasted(connection_id, pasted)
    return caught.value.reason


def test_pasting_the_full_address_connects(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    provider.reply(TOKENS)

    status = service.complete_pasted("music", f"https://relay.example/oauth/redirect.html?code=code-1&state={state}")

    assert status.status == "connected"
    assert provider.calls[0][1]["code"] == "code-1"
    assert store.get("music").access_token == "access-1"
    assert source.invalidated == ["music"]


def test_pasting_an_address_with_a_fragment_connects(service, source, provider):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    provider.reply(TOKENS)
    assert service.complete_pasted("music", f"https://x.example/cb#code=code-1&state={state}").status == "connected"


def test_a_bare_code_cannot_finish_a_relay_flow(service, source, provider):
    source.add("music", RELAY_BLOCK)
    _relay_state(service)
    assert _reject_reason(service, "music", "code-12345") == "no_pending"
    assert provider.calls == []


def test_a_paste_for_another_connection_is_refused(service, source, provider):
    source.add("music", RELAY_BLOCK)
    source.add("other", RELAY_BLOCK)
    state = _relay_state(service, "music")
    assert _reject_reason(service, "other", f"https://x.example/cb?code=c-1&state={state}") == "invalid_state"
    assert provider.calls == []


def test_a_paste_for_another_connection_does_not_spend_the_state(service, source, provider):
    source.add("music", RELAY_BLOCK)
    source.add("other", RELAY_BLOCK)
    state = _relay_state(service, "music")
    _reject_reason(service, "other", f"https://x.example/cb?code=c-1&state={state}")
    provider.reply(TOKENS)
    assert service.complete_pasted("music", f"https://x.example/cb?code=c-1&state={state}").status == "connected"


def test_a_pasted_state_is_single_use_and_shared_with_the_callback(service, source, provider):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    provider.reply(TOKENS)
    service.complete_pasted("music", f"https://x.example/cb?code=c-1&state={state}")
    assert _reject_reason(service, "music", f"https://x.example/cb?code=c-1&state={state}") == "invalid_state"
    assert service.complete_authorization(state=state, code="c-1", error=None).reason == "invalid_state"


def test_a_tampered_pasted_state_is_refused(service, source):
    source.add("music", RELAY_BLOCK)
    _relay_state(service)
    assert _reject_reason(service, "music", "https://x.example/cb?code=c-1&state=forged.sig") == "invalid_state"


def test_an_expired_pasted_state_is_refused(service, source, clock):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    clock.now += STATE_TTL_SECONDS + 1
    assert _reject_reason(service, "music", f"https://x.example/cb?code=c-1&state={state}") == "expired"


def test_a_pasted_denial_is_reported(service, source, provider):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    assert (
        _reject_reason(service, "music", f"https://x.example/cb?error=access_denied&state={state}") == "access_denied"
    )
    assert provider.calls == []


def test_a_failed_exchange_after_paste_is_reported(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    provider.reply({"error": "invalid_grant"}, status=400)
    assert _reject_reason(service, "music", f"https://x.example/cb?code=c-1&state={state}") == "exchange_failed"
    assert store.get("music") is None


def test_unreadable_paste_is_refused(service, source):
    source.add("music", RELAY_BLOCK)
    assert _reject_reason(service, "music", "not a code") == "unreadable"


def test_pasting_for_an_unknown_connection_is_not_found(service):
    with pytest.raises(ConnectionNotFound):
        service.complete_pasted("nope", "code-12345")


def test_a_relay_from_a_url_address_ignores_a_client_id_in_the_paste(service, source, provider, store):
    source.add("music", RELAY_BLOCK)
    state = _relay_state(service)
    provider.reply(TOKENS)
    service.complete_pasted("music", f"https://x.example/cb?code=c-1&state={state}&client_id=evil")
    assert provider.calls[0][1]["client_id"] == "client-abc"
    assert store.get("music").client_id == ""


# ── Token records ───────────────────────────────────────────────────────────


def test_a_9_8_token_record_loads_with_the_new_fields_defaulted(tmp_path):
    path = tmp_path / "oauth_tokens.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "connections": {
                    "music": {
                        "access_token": "access-1",
                        "token_type": "Bearer",
                        "refresh_token": "refresh-1",
                        "expires_at": NOW,
                        "scopes": ["a"],
                        "obtained_at": NOW,
                        "needs_reauthorization": False,
                    }
                },
            }
        )
    )
    tokens = TokenStore(path).get("music")
    assert (tokens.client_id, tokens.reauth_reason) == ("", "")
    assert tokens.access_token == "access-1"


def test_refresh_prefers_a_client_id_issued_at_sign_in(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, expires_at=NOW, client_id="issued-client-1")
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    assert service.get_access_token("music") == "access-2"
    assert provider.calls[0][1]["client_id"] == "issued-client-1"
    assert store.get("music").client_id == "issued-client-1"


# ── key_exchange (OpenRouter-style) ─────────────────────────────────────────

from src.oauth import plex  # noqa: E402

KEY_BLOCK = {
    "provider_name": "OpenRouter",
    "flows": ["key_exchange"],
    "authorization_url": "https://or.example.com/auth",
    "token_url": "https://or.example.com/api/v1/auth/keys",
}


class FakeHttp:
    """A scripted JSON endpoint: records (method, url, headers, form, json)."""

    def __init__(self):
        self.calls = []
        self.headers = []
        self.replies = []

    def reply(self, body, status=200):
        self.replies.append((status, body))
        return self

    def fail(self, exc):
        self.replies.append(exc)
        return self

    def __call__(self, method, url, *, headers, form=None, json_body=None):
        self.calls.append((method, url, dict(headers), form, json_body))
        assert self.replies, f"unexpected http call to {url}"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def http():
    return FakeHttp()


@pytest.fixture
def xservice(source, store, signer, provider, http, clock):
    return OAuthService(
        source=source,
        store=store,
        signer=signer,
        client=ProviderClient(provider, http=http),
        clock=clock,
        redirect_uri="https://relay.example/oauth/redirect.html",
        poll_in_background=False,
        plex_client_identifier=lambda: "test-install-id",
    )


def test_key_exchange_start_sends_pkce_and_the_relay_as_callback(xservice, source):
    source.add("openrouter", KEY_BLOCK, config={})
    start = xservice.start("openrouter", board_url=BOARD)
    assert start.flow == "key_exchange"
    assert start.paste_expected is False
    assert start.authorization_url.startswith("https://or.example.com/auth?")
    query = _query(start.authorization_url)
    assert query["callback_url"] == "https://relay.example/oauth/redirect.html"
    assert query["code_challenge_method"] == "S256"
    assert query["code_challenge"]
    assert query["state"]
    assert "client_id" not in query


def test_key_exchange_needs_no_client_id(xservice, source):
    source.add("openrouter", KEY_BLOCK, config={})
    assert xservice.get_connection("openrouter").configured is True


def test_key_exchange_callback_posts_json_and_stores_a_non_expiring_key(xservice, source, http, store, provider):
    source.add("openrouter", KEY_BLOCK, config={})
    start = xservice.start("openrouter", board_url=BOARD)
    query = _query(start.authorization_url)
    http.reply({"key": "sk-or-test-key", "user_id": "user_test"})

    outcome = xservice.complete_authorization(state=query["state"], code="code-1", error=None)

    assert outcome.connected
    method, url, _headers, form, body = http.calls[0]
    assert (method, url, form) == ("POST", "https://or.example.com/api/v1/auth/keys", None)
    assert set(body) == {"code", "code_verifier", "code_challenge_method"}
    assert body["code"] == "code-1"
    assert body["code_challenge_method"] == "S256"
    assert pkce.challenge_for(body["code_verifier"]) == query["code_challenge"]
    assert provider.calls == []
    tokens = store.get("openrouter")
    assert (tokens.access_token, tokens.expires_at, tokens.refresh_token) == ("sk-or-test-key", None, "")


def test_a_stored_key_is_handed_out_forever(xservice, source, http, clock):
    source.add("openrouter", KEY_BLOCK, config={})
    query = _query(xservice.start("openrouter", board_url=BOARD).authorization_url)
    http.reply({"key": "sk-or-test-key"})
    xservice.complete_authorization(state=query["state"], code="code-1", error=None)
    clock.now += 10 * 365 * 86400
    assert xservice.get_access_token("openrouter") == "sk-or-test-key"


def test_headless_key_exchange_omits_callback_and_state_and_expects_a_paste(xservice, source):
    source.add("openrouter", KEY_BLOCK, config={})
    start = xservice.start("openrouter", headless=True)
    query = _query(start.authorization_url)
    assert "callback_url" not in query and "state" not in query
    assert start.paste_expected is True
    assert start.paste_hint


def test_a_bare_code_finishes_a_headless_key_exchange_once(xservice, source, http, store):
    source.add("openrouter", KEY_BLOCK, config={})
    query = _query(xservice.start("openrouter", headless=True).authorization_url)
    http.reply({"key": "sk-or-test-key"})

    status = xservice.complete_pasted("openrouter", "  code-abc-123 ")

    assert status.status == "connected"
    body = http.calls[0][4]
    assert body["code"] == "code-abc-123"
    assert pkce.challenge_for(body["code_verifier"]) == query["code_challenge"]
    with pytest.raises(PastedCodeRejected) as caught:
        xservice.complete_pasted("openrouter", "code-abc-123")
    assert caught.value.reason == "no_pending"


def test_a_bare_code_uses_the_newest_headless_start(xservice, source, http):
    source.add("openrouter", KEY_BLOCK, config={})
    xservice.start("openrouter", headless=True)
    newest = _query(xservice.start("openrouter", headless=True).authorization_url)
    http.reply({"key": "sk-or-test-key"})
    xservice.complete_pasted("openrouter", "code-abc-123")
    assert pkce.challenge_for(http.calls[0][4]["code_verifier"]) == newest["code_challenge"]


def test_a_bare_code_cannot_finish_a_key_exchange_started_with_a_callback(xservice, source):
    source.add("openrouter", KEY_BLOCK, config={})
    xservice.start("openrouter", board_url=BOARD)
    with pytest.raises(PastedCodeRejected) as caught:
        xservice.complete_pasted("openrouter", "code-abc-123")
    assert caught.value.reason == "no_pending"


@pytest.mark.parametrize("reply", [(200, {"nokey": 1}), (400, {"error": "invalid_code"}), (500, {})])
def test_a_key_exchange_without_a_key_stores_nothing(xservice, source, http, store, reply):
    source.add("openrouter", KEY_BLOCK, config={})
    xservice.start("openrouter", headless=True)
    http.reply(reply[1], status=reply[0])
    with pytest.raises(PastedCodeRejected) as caught:
        xservice.complete_pasted("openrouter", "code-abc-123")
    assert caught.value.reason == "exchange_failed"
    assert store.get("openrouter") is None


# ── plex_pin ────────────────────────────────────────────────────────────────

PLEX_BLOCK = {"provider_name": "Plex", "flows": ["plex_pin"], "plex_product": "FiestaBoard Test"}
PIN = {"id": 4242, "code": "pin-code-1", "expiresIn": 900, "authToken": None}


@pytest.fixture
def plexconn(source):
    source.add("plex", PLEX_BLOCK, config={}, name="Plex")
    return "plex"


def test_plex_start_creates_a_strong_pin_and_sends_the_browser_to_plex(xservice, plexconn, http):
    http.reply(PIN, status=201)
    start = xservice.start(plexconn, board_url=BOARD)

    method, url, headers, _form, _body = http.calls[0]
    assert (method, url) == ("POST", "https://plex.tv/api/v2/pins?strong=true")
    assert headers["Accept"] == "application/json"
    assert headers["X-Plex-Client-Identifier"] == "test-install-id"
    assert headers["X-Plex-Product"] == "FiestaBoard Test"
    assert start.flow == "plex_pin"
    assert start.authorization_url.startswith("https://app.plex.tv/auth#?")
    fragment = parse_qs(start.authorization_url.split("#?", 1)[1])
    assert fragment["clientID"] == ["test-install-id"]
    assert fragment["code"] == ["pin-code-1"]
    assert fragment["forwardUrl"] == [f"{BOARD}/integrations?plugin=plex"]
    assert fragment["context[device][product]"] == ["FiestaBoard Test"]
    assert start.device.status == "pending"
    assert start.device.user_code == ""
    assert start.device.expires_at == NOW + 900


def test_plex_start_without_a_board_omits_the_forward_url(xservice, plexconn, http):
    http.reply(PIN)
    start = xservice.start(plexconn)
    assert "forwardUrl" not in parse_qs(start.authorization_url.split("#?", 1)[1])


def test_plex_needs_no_client_id(xservice, plexconn):
    assert xservice.get_connection(plexconn).configured is True


def test_plex_poll_waits_then_stores_a_non_expiring_token(xservice, plexconn, http, store):
    http.reply(PIN)
    xservice.start(plexconn)
    http.reply(PIN)
    assert xservice.poll_device(plexconn) is True
    http.reply({**PIN, "authToken": "plex-test-token"})
    assert xservice.poll_device(plexconn) is False

    method, url, headers, _, _ = http.calls[1]
    assert (method, url) == ("GET", "https://plex.tv/api/v2/pins/4242")
    assert headers["X-Plex-Client-Identifier"] == "test-install-id"
    tokens = store.get(plexconn)
    assert (tokens.access_token, tokens.expires_at, tokens.refresh_token) == ("plex-test-token", None, "")
    status = xservice.get_connection(plexconn)
    assert (status.status, status.device) == ("connected", None)


def test_a_vanished_plex_pin_expires_the_flow(xservice, plexconn, http, store):
    http.reply(PIN)
    xservice.start(plexconn)
    http.reply({"errors": [{"code": 1020}]}, status=404)
    assert xservice.poll_device(plexconn) is False
    assert xservice.get_connection(plexconn).device.status == "expired"
    assert store.get(plexconn) is None


def test_a_plex_pin_past_its_lifetime_expires_without_asking(xservice, plexconn, http, clock):
    http.reply(PIN)
    xservice.start(plexconn)
    clock.now += 901
    assert xservice.poll_device(plexconn) is False
    assert len(http.calls) == 1
    assert xservice.get_connection(plexconn).device.status == "expired"


def test_a_network_failure_while_polling_plex_is_retried(xservice, plexconn, http):
    http.reply(PIN)
    xservice.start(plexconn)
    http.fail(ProviderError("unreachable"))
    assert xservice.poll_device(plexconn) is True
    assert xservice.get_connection(plexconn).device.status == "pending"


def test_plex_polls_every_two_seconds(source, store, signer, provider, http, clock, plexconn):
    slept = []
    built = OAuthService(
        source=source,
        store=store,
        signer=signer,
        client=ProviderClient(provider, http=http),
        clock=clock,
        sleep=slept.append,
        poll_in_background=False,
        plex_client_identifier=lambda: "test-install-id",
    )
    http.reply(PIN)
    built.start(plexconn)
    http.reply({**PIN, "authToken": "plex-test-token"})
    built._poll_device_until_done(built._device[plexconn])
    assert slept == [2]


def test_a_plex_pin_answer_without_an_id_is_a_provider_error(xservice, plexconn, http):
    http.reply({"code": "x"})
    with pytest.raises(ProviderError):
        xservice.start(plexconn)


def test_the_install_client_identifier_is_created_once_and_private(tmp_path):
    first = plex.load_client_identifier(tmp_path)
    assert first == plex.load_client_identifier(tmp_path)
    path = tmp_path / ".oauth_client_identifier"
    assert path.read_text() == first
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


# ── A plugin reports the provider rejected its token ────────────────────────

from src.oauth.service import FORCED_REFRESH_COOLDOWN_SECONDS  # noqa: E402


def test_a_rejected_token_is_force_refreshed_and_the_new_one_returned(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store)  # fresh by expiry, but the provider says no
    provider.reply({"access_token": "access-2", "expires_in": 3600})

    assert service.report_rejected("music") == "access-2"

    assert provider.calls[0][1]["grant_type"] == "refresh_token"
    assert store.get("music").access_token == "access-2"
    assert service.get_connection("music").status == "connected"


def test_a_refused_forced_refresh_needs_reconnecting(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    provider.reply({"error": "invalid_grant"}, status=400)

    assert service.report_rejected("music") is None

    status = service.get_connection("music")
    assert (status.status, status.status_reason) == ("reauthorization_required", "refresh_refused")
    assert service.get_access_token("music") is None


def test_a_rejected_token_without_a_refresh_token_needs_reconnecting(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, refresh_token="")

    assert service.report_rejected("music") is None

    assert provider.calls == []
    status = service.get_connection("music")
    assert (status.status, status.status_reason) == ("reauthorization_required", "rejected")
    assert service.get_access_token("music") is None


def test_forced_refreshes_are_at_most_one_a_minute(service, source, store, provider, clock):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    provider.reply({"access_token": "access-2", "expires_in": 3600, "refresh_token": "refresh-2"})
    assert service.report_rejected("music") == "access-2"

    clock.now += FORCED_REFRESH_COOLDOWN_SECONDS - 1
    assert service.report_rejected("music") is None

    assert len(provider.calls) == 1
    status = service.get_connection("music")
    assert (status.status, status.status_reason) == ("reauthorization_required", "rejected")


def test_after_the_cooldown_a_forced_refresh_is_tried_again(service, source, store, provider, clock):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    service.report_rejected("music")
    clock.now += FORCED_REFRESH_COOLDOWN_SECONDS
    provider.reply({"access_token": "access-3", "expires_in": 3600})
    assert service.report_rejected("music") == "access-3"


def test_an_unreachable_provider_on_forced_refresh_keeps_the_connection(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store)
    provider.fail(ProviderError("down"))
    assert service.report_rejected("music") is None
    assert service.get_connection("music").status == "connected"


def test_reporting_for_a_connection_with_no_tokens_does_nothing(service, source, store):
    source.add("music", RELAY_BLOCK)
    assert service.report_rejected("music") is None
    assert store.get("music") is None


def test_reconnecting_clears_the_rejected_reason(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, refresh_token="")
    service.report_rejected("music")
    state = _relay_state(service)
    provider.reply(TOKENS)
    service.complete_authorization(state=state, code="c-1", error=None)
    status = service.get_connection("music")
    assert (status.status, status.status_reason) == ("connected", "")


def test_report_rejected_for_maps_the_plugin_object(service, source, store):
    plugin = source.add("music", RELAY_BLOCK)
    _connected(store, refresh_token="")
    assert service.report_rejected_for(plugin) is None
    assert service.get_connection("music").status_reason == "rejected"
    assert service.report_rejected_for(object()) is None


# ── Rollout gaps: auth method, refresh params, Twitch, TikTok, token hooks ──

BASIC_BLOCK = {**RELAY_BLOCK, "client_secret_setting": "client_secret", "token_auth_method": "basic"}
SECRET_CONFIG = {"client_id": "client-abc", "client_secret": "test_secret"}


def _basic_user(provider, index=0):
    import base64

    header = (provider.headers[index] or {}).get("Authorization", "")
    return base64.b64decode(header.removeprefix("Basic ")).decode() if header else ""


def test_basic_auth_is_used_for_the_code_exchange(service, source, provider):
    source.add("x", BASIC_BLOCK, config=SECRET_CONFIG)
    query = _begin_relay(service, "x")
    provider.reply(TOKENS)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected
    assert _basic_user(provider) == "client-abc:test_secret"
    assert "client_secret" not in provider.calls[0][1]


def test_basic_auth_is_used_on_refresh(service, source, store, provider):
    source.add("x", BASIC_BLOCK, config=SECRET_CONFIG)
    _connected(store, "x", expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    assert service.get_access_token("x") == "access-2"
    assert _basic_user(provider) == "client-abc:test_secret"


def test_basic_auth_is_used_for_the_device_poll(service, source, provider):
    source.add("dev", {**DEVICE_BLOCK, "token_auth_method": "basic"}, config=SECRET_CONFIG)
    provider.reply(DEVICE_ANSWER)
    service.start("dev")
    provider.reply({"error": "authorization_pending"})
    service.poll_device("dev")
    assert provider.headers[0] is None, "the device request carries no secret"
    assert _basic_user(provider, 1) == "client-abc:test_secret"


def test_the_default_still_posts_the_secret(service, source, store, provider):
    source.add("music", {**RELAY_BLOCK, "client_secret_setting": "client_secret"}, config=SECRET_CONFIG)
    _connected(store, expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    service.get_access_token("music")
    assert provider.calls[0][1]["client_secret"] == "test_secret"
    assert provider.headers[0] is None


def test_refresh_params_are_sent_on_refresh_only(service, source, store, provider):
    source.add("whoop", {**RELAY_BLOCK, "refresh_params": {"scope": "offline"}})
    query = _begin_relay(service, "whoop")
    provider.reply(TOKENS)
    service.complete_authorization(state=query["state"], code="code-1", error=None)
    assert "scope" not in provider.calls[0][1]
    store.put("whoop", replace_tokens(store.get("whoop"), expires_at=NOW))
    provider.reply({"access_token": "access-2", "expires_in": 3600, "refresh_token": "refresh-2"})
    assert service.get_access_token("whoop") == "access-2"
    assert provider.calls[1][1]["scope"] == "offline"
    assert store.get("whoop").refresh_token == "refresh-2"


def replace_tokens(tokens, **changes):
    from dataclasses import replace

    return replace(tokens, **changes)


def test_tiktok_refresh_uses_client_key_and_keeps_the_rotated_refresh_token(service, source, store, provider):
    source.add("tiktok", TIKTOK_BLOCK)
    _connected(store, "tiktok", expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 86400, "refresh_token": "refresh-2"})
    assert service.get_access_token("tiktok") == "access-2"
    assert provider.calls[0][1]["client_key"] == "client-abc"
    assert store.get("tiktok").refresh_token == "refresh-2"
    store.put("tiktok", replace_tokens(store.get("tiktok"), expires_at=NOW))
    provider.reply({"access_token": "access-3", "expires_in": 86400, "refresh_token": "refresh-3"})
    service.get_access_token("tiktok")
    assert provider.calls[1][1]["refresh_token"] == "refresh-2"


def test_twitch_device_flow_end_to_end(service, source, store, provider):
    source.add("twitch", TWITCH_BLOCK, config={"client_id": "client-abc"})
    provider.reply(DEVICE_ANSWER)
    service.start("twitch")
    provider.reply({"status": 400, "message": "authorization_pending"}, status=400)
    assert service.poll_device("twitch") is True
    provider.reply({"status": 400, "message": "slow_down"}, status=400)
    assert service.poll_device("twitch") is True
    provider.reply(
        {"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 14000, "scope": ["user:read:email"]}
    )
    assert service.poll_device("twitch") is False
    assert store.get("twitch").scopes == ("user:read:email",)


def test_twitch_invalid_device_code_expires_the_flow(service, source, provider):
    source.add("twitch", TWITCH_BLOCK, config={"client_id": "client-abc"})
    provider.reply(DEVICE_ANSWER)
    service.start("twitch")
    provider.reply({"status": 400, "message": "invalid device code"}, status=400)
    assert service.poll_device("twitch") is False
    assert service.get_connection("twitch").device.status == "expired"


class TokenHooks:
    """A plugin that swaps its sign-in token for a long-lived one and renews it itself."""

    def __init__(self, exchanged=None, refreshed=None, error=None):
        self.exchanged = exchanged
        self.refreshed = refreshed
        self.error = error
        self.seen = []

    def exchange_oauth_token(self, token):
        self.seen.append(("exchange", token))
        if self.error:
            raise self.error
        return self.exchanged

    def refresh_oauth_token(self, token):
        self.seen.append(("refresh", token))
        if self.error:
            raise self.error
        return self.refreshed


SHORT_LIVED = {"access_token": "short-1", "token_type": "bearer", "user_id": 7}


def test_the_exchange_hook_swaps_the_token_after_sign_in(service, source, provider, store, clock):
    hooks = TokenHooks(exchanged={"access_token": "long-1", "expires_in": 5_184_000})
    source.add("instagram", RELAY_BLOCK, plugin=hooks)
    query = _begin_relay(service, "instagram")
    provider.reply(SHORT_LIVED)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected
    kind, given = hooks.seen[0]
    assert kind == "exchange"
    assert given == {"access_token": "short-1", "refresh_token": "", "expires_at": None, "scopes": []}
    stored = store.get("instagram")
    assert stored.access_token == "long-1"
    assert stored.expires_at == NOW + 5_184_000
    assert stored.scopes == ("read-playing", "read-state")


@pytest.mark.parametrize(
    "hooks",
    [TokenHooks(exchanged=None), TokenHooks(error=RuntimeError("boom")), TokenHooks(exchanged={"nope": 1})],
)
def test_a_declining_or_failing_exchange_hook_keeps_the_sign_in_token(service, source, provider, store, hooks):
    source.add("instagram", RELAY_BLOCK, plugin=hooks)
    query = _begin_relay(service, "instagram")
    provider.reply(SHORT_LIVED)
    assert service.complete_authorization(state=query["state"], code="code-1", error=None).connected
    assert store.get("instagram").access_token == "short-1"


def test_the_exchange_hook_runs_after_a_device_sign_in(service, source, provider, store):
    hooks = TokenHooks(exchanged={"access_token": "long-1"})
    source.add("dev", DEVICE_BLOCK, plugin=hooks)
    provider.reply(DEVICE_ANSWER)
    service.start("dev")
    provider.reply(TOKENS)
    service.poll_device("dev")
    stored = store.get("dev")
    assert stored.access_token == "long-1"
    assert stored.refresh_token == "refresh-1", "a hook that names no refresh token keeps the provider's"


def test_the_refresh_hook_renews_a_token_without_a_refresh_token(service, source, store, provider):
    hooks = TokenHooks(refreshed={"access_token": "long-2", "expires_in": 5_184_000})
    source.add("instagram", RELAY_BLOCK, plugin=hooks)
    _connected(store, "instagram", refresh_token="", expires_at=NOW + 30)
    assert service.get_access_token("instagram") == "long-2"
    assert hooks.seen[0] == (
        "refresh",
        {"access_token": "access-1", "refresh_token": "", "expires_at": NOW + 30, "scopes": ["read-playing"]},
    )
    stored = store.get("instagram")
    assert stored.expires_at == NOW + 5_184_000
    assert stored.obtained_at == NOW - 100
    assert provider.calls == []


def test_the_refresh_hook_is_not_asked_while_the_token_is_fresh(service, source, store):
    hooks = TokenHooks(refreshed={"access_token": "long-2"})
    source.add("instagram", RELAY_BLOCK, plugin=hooks)
    _connected(store, "instagram", refresh_token="")
    assert service.get_access_token("instagram") == "access-1"
    assert hooks.seen == []


def test_a_refresh_hook_that_declines_falls_back_to_the_standard_refresh(service, source, store, provider):
    hooks = TokenHooks(refreshed=None)
    source.add("music", RELAY_BLOCK, plugin=hooks)
    _connected(store, expires_at=NOW)
    provider.reply({"access_token": "access-2", "expires_in": 3600})
    assert service.get_access_token("music") == "access-2"
    assert hooks.seen[0][0] == "refresh"


def test_a_failing_refresh_hook_serves_the_token_until_it_expires(service, source, store, provider, clock):
    hooks = TokenHooks(error=RuntimeError("boom"))
    source.add("instagram", RELAY_BLOCK, plugin=hooks)
    _connected(store, "instagram", refresh_token="", expires_at=NOW + 30)
    assert service.get_access_token("instagram") == "access-1"
    clock.now = NOW + 31
    assert service.get_access_token("instagram") is None
    assert provider.calls == []


def test_a_plugin_without_hooks_is_unaffected(service, source, store, provider):
    source.add("music", RELAY_BLOCK)
    _connected(store, refresh_token="", expires_at=NOW + 30)
    assert service.get_access_token("music") == "access-1"
    assert provider.calls == []


def test_url_overrides_point_endpoints_at_a_local_mock(service, source, provider, monkeypatch):
    monkeypatch.setenv(
        "FIESTABOARD_OAUTH_URL_OVERRIDES", json.dumps({"https://accounts.example.com": "http://localhost:9400"})
    )
    source.add("music", RELAY_BLOCK)
    query = _begin_relay(service, "music")
    provider.reply(TOKENS)
    service.complete_authorization(state=query["state"], code="code-1", error=None)
    assert provider.calls[0][0] == "http://localhost:9400/api/token"
