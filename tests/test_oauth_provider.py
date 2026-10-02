"""The ``oauth`` block of a plugin manifest: what is accepted, what is refused."""

import pytest

from src.oauth.provider import parse_oauth_block, validate_oauth_block
from src.plugins.manifest import validate_manifest

RELAY = {
    "provider_name": "Example Music",
    "flows": ["relay"],
    "authorization_url": "https://accounts.example.com/authorize",
    "token_url": "https://accounts.example.com/api/token",
    "scopes": ["user-read-currently-playing"],
}
DEVICE = {
    "flows": ["device"],
    "device_authorization_url": "https://id.example.com/device/code",
    "token_url": "https://id.example.com/token",
}


def _with(base, **changes):
    return {**base, **changes}


def _without(base, key):
    return {k: v for k, v in base.items() if k != key}


def test_a_relay_block_is_valid():
    assert validate_oauth_block(RELAY) == []


def test_a_device_block_is_valid():
    assert validate_oauth_block(DEVICE) == []


def test_a_block_may_offer_both_flows():
    block = _with(RELAY, flows=["device", "relay"], device_authorization_url="https://id.example.com/device/code")
    assert validate_oauth_block(block) == []
    assert parse_oauth_block(block, "x").flows == ("device", "relay")


@pytest.mark.parametrize("block", [None, "relay", ["relay"], 7])
def test_a_block_that_is_not_an_object_is_refused(block):
    assert validate_oauth_block(block) == ["oauth must be an object"]


@pytest.mark.parametrize("flows", [None, [], "relay", ["implicit"], ["relay", "relay"]])
def test_flows_must_be_a_non_empty_list_of_known_flows_without_repeats(flows):
    assert any("oauth.flows" in error for error in validate_oauth_block(_with(RELAY, flows=flows)))


def test_relay_requires_an_authorization_url():
    assert "oauth.authorization_url must be a non-empty string" in validate_oauth_block(
        _without(RELAY, "authorization_url")
    )


def test_device_requires_a_device_authorization_url():
    assert "oauth.device_authorization_url must be a non-empty string" in validate_oauth_block(
        _without(DEVICE, "device_authorization_url")
    )


def test_every_flow_requires_a_token_url():
    assert "oauth.token_url must be a non-empty string" in validate_oauth_block(_without(RELAY, "token_url"))


@pytest.mark.parametrize(
    "url",
    [
        "http://accounts.example.com/token",
        "http://192.168.1.10/token",
        "ftp://accounts.example.com/token",
        "//accounts.example.com/token",
        "accounts.example.com/token",
        "https://",
    ],
)
def test_endpoints_must_be_https(url):
    """They carry authorization codes, refresh tokens and client secrets."""
    assert validate_oauth_block(_with(RELAY, token_url=url)) == ["oauth.token_url must be an https:// URL"]


@pytest.mark.parametrize("url", ["http://localhost:9000/token", "http://127.0.0.1:9000/token"])
def test_plain_http_is_allowed_only_to_loopback(url):
    assert validate_oauth_block(_with(RELAY, token_url=url)) == []


def test_a_client_secret_in_the_manifest_is_refused():
    """Plugin repositories are public; a secret committed to one is burned."""
    errors = validate_oauth_block(_with(RELAY, client_secret="example-secret-value"))
    assert len(errors) == 1
    assert "must never be in a manifest" in errors[0]


def test_a_client_id_in_the_manifest_is_allowed():
    """A client ID identifies a public client; it is not a credential."""
    block = _with(RELAY, client_id="example-public-client-id")
    assert validate_oauth_block(block) == []
    assert parse_oauth_block(block, "x").client_id == "example-public-client-id"


def test_an_unknown_field_is_refused_so_typos_do_not_pass_silently():
    assert validate_oauth_block(_with(RELAY, scope=["x"])) == ["oauth.scope is not a recognised field"]


@pytest.mark.parametrize("scopes", ["a b", [""], ["has space"], [3]])
def test_scopes_must_be_a_list_of_tokens(scopes):
    assert any("oauth.scopes" in error for error in validate_oauth_block(_with(RELAY, scopes=scopes)))


@pytest.mark.parametrize(
    "reserved",
    ["response_type", "client_id", "redirect_uri", "state", "scope", "code_challenge", "code_challenge_method"],
)
def test_authorization_params_may_not_override_what_the_platform_sets(reserved):
    errors = validate_oauth_block(_with(RELAY, authorization_params={reserved: "x"}))
    assert errors == [f"oauth.authorization_params may not set {reserved}; the platform sets those"]


def test_authorization_params_must_be_strings():
    assert validate_oauth_block(_with(RELAY, authorization_params={"prompt": 1})) == [
        "oauth.authorization_params must be an object of string values"
    ]


@pytest.mark.parametrize("key", ["client_id_setting", "client_secret_setting"])
@pytest.mark.parametrize("value", ["", "has space", "1leading", 5])
def test_setting_names_must_be_settings_keys(key, value):
    assert validate_oauth_block(_with(RELAY, **{key: value})) == [f"oauth.{key} must name a key in settings_schema"]


# ── Parsing ─────────────────────────────────────────────────────────────────


def test_parse_returns_none_when_a_plugin_declares_no_oauth():
    assert parse_oauth_block(None, "Plugin") is None


def test_parse_returns_none_for_an_invalid_block():
    assert parse_oauth_block({"flows": ["relay"]}, "Plugin") is None


def test_provider_name_falls_back_to_the_plugin_name():
    assert parse_oauth_block(DEVICE, "My Plugin").name == "My Plugin"
    assert parse_oauth_block(RELAY, "My Plugin").name == "Example Music"


def test_the_users_client_id_setting_wins_over_the_manifest_default():
    provider = parse_oauth_block(_with(RELAY, client_id="manifest-default"), "x")
    assert provider.resolve_client_id({}) == "manifest-default"
    assert provider.resolve_client_id({"client_id": "   "}) == "manifest-default"
    assert provider.resolve_client_id({"client_id": " users-own "}) == "users-own"


def test_client_id_is_read_from_the_setting_the_manifest_names():
    provider = parse_oauth_block(_with(RELAY, client_id_setting="app_id"), "x")
    assert provider.resolve_client_id({"client_id": "wrong", "app_id": "right"}) == "right"


def test_there_is_no_client_secret_unless_the_manifest_names_a_setting_for_it():
    public = parse_oauth_block(RELAY, "x")
    assert public.resolve_client_secret({"client_secret": "ignored"}) == ""
    confidential = parse_oauth_block(_with(RELAY, client_secret_setting="client_secret"), "x")
    assert confidential.resolve_client_secret({"client_secret": " s3 "}) == "s3"
    assert confidential.resolve_client_secret({}) == ""


# ── Through the manifest validator ──────────────────────────────────────────

MANIFEST = {"id": "music", "name": "Music", "version": "1.0.0"}


def test_a_manifest_with_a_valid_oauth_block_loads():
    assert validate_manifest({**MANIFEST, "oauth": RELAY}) == (True, [])


def test_a_manifest_with_an_invalid_oauth_block_does_not_load():
    valid, errors = validate_manifest({**MANIFEST, "oauth": _with(RELAY, client_secret="example-secret-value")})
    assert valid is False
    assert any("must never be in a manifest" in error for error in errors)


def test_a_manifest_without_oauth_is_unaffected():
    assert validate_manifest(MANIFEST) == (True, [])


def test_a_transition_plugin_may_not_declare_oauth():
    valid, errors = validate_manifest({**MANIFEST, "plugin_type": "transition", "oauth": RELAY})
    assert valid is False
    assert errors == ["oauth is not supported for transition plugins — they fetch no data"]
