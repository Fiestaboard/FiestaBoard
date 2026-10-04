"""ProviderClient: provider quirks in token answers and client authentication.

The transport is scripted, so nothing leaves the process. Every credential is
a ``test_`` placeholder.
"""

import base64

import pytest

from src.oauth.client import ProviderClient
from src.oauth.errors import ProviderError, TokenEndpointError

TOKEN_URL = "https://accounts.example.com/token"


class Transport:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, form, headers=None):
        self.calls.append((url, dict(form), headers))
        return self.replies.pop(0)


def _poll(transport):
    return ProviderClient(transport).poll_device_token(TOKEN_URL, device_code="test_dc", client_id="test_client")


# ── Twitch reports device-poll states as {"status", "message"} ─────────────


@pytest.mark.parametrize(
    ("message", "error"),
    [
        ("authorization_pending", "authorization_pending"),
        ("slow_down", "slow_down"),
        ("invalid device code", "expired_token"),
        ("access_denied", "access_denied"),
        ("Invalid refresh token", "invalid_grant"),
    ],
)
def test_twitch_message_errors_map_to_rfc_states(message, error):
    transport = Transport((400, {"status": 400, "message": message}))
    with pytest.raises(TokenEndpointError) as caught:
        _poll(transport)
    assert caught.value.error == error


def test_twitch_message_wins_over_a_generic_error_field():
    transport = Transport((400, {"error": "Bad Request", "status": 400, "message": "authorization_pending"}))
    with pytest.raises(TokenEndpointError) as caught:
        _poll(transport)
    assert caught.value.error == "authorization_pending"


def test_an_unknown_message_is_still_a_failure():
    transport = Transport((400, {"status": 400, "message": "something else"}))
    with pytest.raises(ProviderError):
        _poll(transport)


def test_a_scope_array_is_accepted():
    transport = Transport((200, {"access_token": "test_at", "scope": ["user:read:follows", "user:read:email"]}))
    assert _poll(transport).scopes == ("user:read:follows", "user:read:email")


# ── Meta wraps the code-exchange answer in {"data": [...]} ──────────────────


def test_a_token_wrapped_in_a_data_array_is_accepted():
    transport = Transport((200, {"data": [{"access_token": "test_at", "user_id": 1, "permissions": "a,b"}]}))
    response = ProviderClient(transport).exchange_code(
        TOKEN_URL, code="c", redirect_uri="https://r", client_id="test_client", code_verifier="v"
    )
    assert response.access_token == "test_at"


@pytest.mark.parametrize("body", [{"data": []}, {"data": ["x"]}, {"data": "x"}])
def test_an_empty_or_odd_data_wrapper_is_still_missing_a_token(body):
    with pytest.raises(ProviderError):
        _poll(Transport((200, body)))


# ── token_auth_method ───────────────────────────────────────────────────────


def test_post_is_the_default_and_sends_the_secret_in_the_body():
    transport = Transport((200, {"access_token": "test_at"}))
    ProviderClient(transport).refresh(
        TOKEN_URL, refresh_token="test_rt", client_id="test_client", client_secret="test_secret"
    )
    _, form, headers = transport.calls[0]
    assert form["client_secret"] == "test_secret"
    assert form["client_id"] == "test_client"
    assert headers is None


def test_basic_sends_the_credentials_in_an_authorization_header():
    transport = Transport((200, {"access_token": "test_at"}))
    ProviderClient(transport).refresh(
        TOKEN_URL,
        refresh_token="test_rt",
        client_id="test client",
        client_secret="test:secret",
        auth_method="basic",
    )
    _, form, headers = transport.calls[0]
    assert "client_secret" not in form
    assert "client_id" not in form
    scheme, _, encoded = headers["Authorization"].partition(" ")
    assert scheme == "Basic"
    # RFC 6749 §2.3.1: each part form-encoded before joining.
    assert base64.b64decode(encoded).decode() == "test+client:test%3Asecret"


def test_basic_without_a_secret_is_a_public_client_in_the_body():
    transport = Transport((200, {"access_token": "test_at"}))
    ProviderClient(transport).exchange_code(
        TOKEN_URL, code="c", redirect_uri="https://r", client_id="test_client", code_verifier="v", auth_method="basic"
    )
    _, form, headers = transport.calls[0]
    assert form["client_id"] == "test_client"
    assert headers is None


def test_basic_applies_to_the_device_poll_with_a_custom_client_id_param():
    transport = Transport((200, {"access_token": "test_at"}))
    ProviderClient(transport).poll_device_token(
        TOKEN_URL,
        device_code="test_dc",
        client_id="test_client",
        client_secret="test_secret",
        client_id_param="client_key",
        auth_method="basic",
    )
    _, form, headers = transport.calls[0]
    assert "client_key" not in form
    assert base64.b64decode(headers["Authorization"].split()[1]).decode() == "test_client:test_secret"


def test_refresh_sends_extra_params():
    transport = Transport((200, {"access_token": "test_at"}))
    ProviderClient(transport).refresh(
        TOKEN_URL, refresh_token="test_rt", client_id="test_client", extra_form={"scope": "offline"}
    )
    assert transport.calls[0][1]["scope"] == "offline"
