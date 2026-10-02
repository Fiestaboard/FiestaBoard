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
from src.oauth.provider import parse_oauth_block
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

    def add(self, connection_id, block, config=None, name="Music"):
        plugin_id, _, label = connection_id.partition(":")
        self.targets[connection_id] = ConnectionTarget(
            connection_id=connection_id,
            plugin_id=plugin_id,
            instance_label=label or None,
            plugin_name=name,
            provider=parse_oauth_block(block, name),
            config=config if config is not None else {"client_id": "client-abc"},
        )
        self.plugins[connection_id] = object()
        return self.plugins[connection_id]

    def get(self, connection_id):
        return self.targets.get(connection_id)

    def all(self):
        return list(self.targets.values())

    def id_for(self, plugin):
        return next((cid for cid, candidate in self.plugins.items() if candidate is plugin), None)


class FakeProvider:
    """A scripted token/device endpoint that records every form it is sent."""

    def __init__(self):
        self.calls = []
        self.replies = []

    def reply(self, body, status=200):
        self.replies.append((status, body))
        return self

    def fail(self, exc):
        self.replies.append(exc)
        return self

    def __call__(self, url, form):
        self.calls.append((url, dict(form)))
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
    assert default.redirect_uri == DEFAULT_REDIRECT_URI == "https://fiestaboard.app/auth/oauth/redirect.html"


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
