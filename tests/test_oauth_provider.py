"""The ``oauth`` block of a plugin manifest: what is accepted, what is refused."""

import pytest

from src.oauth.provider import parse_provider_block, provider_block_warnings, validate_provider_block
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
    assert validate_provider_block(RELAY) == []


def test_a_device_block_is_valid():
    assert validate_provider_block(DEVICE) == []


def test_a_block_may_offer_both_flows():
    block = _with(RELAY, flows=["device", "relay"], device_authorization_url="https://id.example.com/device/code")
    assert validate_provider_block(block) == []
    assert parse_provider_block(block, "x").flows == ("device", "relay")


@pytest.mark.parametrize("block", [None, "relay", ["relay"], 7])
def test_a_block_that_is_not_an_object_is_refused(block):
    assert validate_provider_block(block) == ["oauth must be an object"]


@pytest.mark.parametrize("flows", [None, [], "relay", ["implicit"], ["relay", "relay"]])
def test_flows_must_be_a_non_empty_list_of_known_flows_without_repeats(flows):
    assert any("oauth.flows" in error for error in validate_provider_block(_with(RELAY, flows=flows)))


def test_relay_requires_an_authorization_url():
    assert "oauth.authorization_url must be a non-empty string" in validate_provider_block(
        _without(RELAY, "authorization_url")
    )


def test_device_requires_a_device_authorization_url():
    assert "oauth.device_authorization_url must be a non-empty string" in validate_provider_block(
        _without(DEVICE, "device_authorization_url")
    )


def test_every_flow_requires_a_token_url():
    assert "oauth.token_url must be a non-empty string" in validate_provider_block(_without(RELAY, "token_url"))


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
    assert validate_provider_block(_with(RELAY, token_url=url)) == ["oauth.token_url must be an https:// URL"]


@pytest.mark.parametrize("url", ["http://localhost:9000/token", "http://127.0.0.1:9000/token"])
def test_plain_http_is_allowed_only_to_loopback(url):
    assert validate_provider_block(_with(RELAY, token_url=url)) == []


def test_a_client_secret_in_the_manifest_is_refused():
    """Plugin repositories are public; a secret committed to one is burned."""
    errors = validate_provider_block(_with(RELAY, client_secret="example-secret-value"))
    assert len(errors) == 1
    assert "must never be in a manifest" in errors[0]


def test_a_client_id_in_the_manifest_is_allowed():
    """A client ID identifies a public client; it is not a credential."""
    block = _with(RELAY, client_id="example-public-client-id")
    assert validate_provider_block(block) == []
    assert parse_provider_block(block, "x").client_id == "example-public-client-id"


def test_an_unknown_field_is_a_warning_not_an_error():
    """A newer FiestaBoard may add a field; a plugin using it must still load on this one."""
    block = _with(RELAY, some_future_field="x")
    assert validate_provider_block(block) == []
    warnings = provider_block_warnings(block)
    assert len(warnings) == 1
    assert warnings[0].startswith("oauth has a field this FiestaBoard does not recognise, which is ignored.")
    assert "app_setup_url" in warnings[0]  # the known fields are listed, so a typo can be spotted
    assert "some_future_field" not in warnings[0]
    assert parse_provider_block(block, "x").flows == ("relay",)


def test_a_block_with_only_known_fields_has_no_warnings():
    assert provider_block_warnings(RELAY) == []
    assert provider_block_warnings(_with(RELAY, client_secret="example-secret-value")) == []
    assert provider_block_warnings(None) == []


def test_a_plugin_with_a_field_from_a_newer_core_still_loads_and_is_reported(tmp_path):
    import json

    from src.plugins.loader import PluginLoader

    plugin_dir = tmp_path / "futureauth"
    plugin_dir.mkdir()
    manifest = {
        "id": "futureauth",
        "name": "Future Auth",
        "version": "1.0.0",
        "oauth": _with(RELAY, some_future_field=1),
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text(
        "from src.plugins.base import PluginBase, PluginResult\n\n\n"
        "class FutureAuthPlugin(PluginBase):\n"
        "    @property\n"
        "    def plugin_id(self) -> str:\n"
        '        return "futureauth"\n\n'
        "    def fetch_data(self) -> PluginResult:\n"
        "        return PluginResult(available=True, data={})\n"
    )
    loader = PluginLoader(plugins_dir=tmp_path, external_dirs=[])

    assert loader.load_plugin("futureauth") is not None, "the plugin must still load"
    assert any("does not recognise" in e for e in loader.load_errors.get("futureauth", [])), loader.load_errors


def test_app_setup_url_must_be_https():
    assert validate_provider_block(_with(RELAY, app_setup_url="https://example.com/developers")) == []
    assert validate_provider_block(_with(RELAY, app_setup_url="javascript:alert(1)")) == [
        "oauth.app_setup_url must be an https:// URL"
    ]
    assert validate_provider_block(_with(RELAY, app_setup_url="")) == ["oauth.app_setup_url must be a non-empty string"]
    assert parse_provider_block(_with(RELAY, app_setup_url="https://example.com/developers"), "x").app_setup_url == (
        "https://example.com/developers"
    )


@pytest.mark.parametrize("scopes", ["a b", [""], ["has space"], [3]])
def test_scopes_must_be_a_list_of_tokens(scopes):
    assert any("oauth.scopes" in error for error in validate_provider_block(_with(RELAY, scopes=scopes)))


@pytest.mark.parametrize(
    "reserved",
    ["response_type", "client_id", "redirect_uri", "state", "scope", "code_challenge", "code_challenge_method"],
)
def test_authorization_params_may_not_override_what_the_platform_sets(reserved):
    errors = validate_provider_block(_with(RELAY, authorization_params={reserved: "x"}))
    assert len(errors) == 1
    assert errors[0].startswith("oauth.authorization_params may not set any of: ")
    assert reserved in errors[0]


def test_authorization_params_must_be_strings():
    assert validate_provider_block(_with(RELAY, authorization_params={"prompt": 1})) == [
        "oauth.authorization_params must be an object of string values"
    ]


@pytest.mark.parametrize("key", ["client_id_setting", "client_secret_setting"])
@pytest.mark.parametrize("value", ["", "has space", "1leading", 5])
def test_setting_names_must_be_settings_keys(key, value):
    assert validate_provider_block(_with(RELAY, **{key: value})) == [f"oauth.{key} must name a key in settings_schema"]


def test_validation_messages_never_repeat_a_value_from_the_manifest():
    """They are logged at install time; nothing a manifest contains may ride along."""
    marker = "zq9-marker"
    block = {
        "flows": [marker],
        "token_url": f"http://{marker}.example/token",
        "authorization_url": marker,
        "device_authorization_url": marker,
        "scopes": [f"{marker} with space"],
        "client_secret": marker,
        "client_id": 7,
        "client_id_setting": f"{marker} bad",
        "client_secret_setting": f"{marker} bad",
        "provider_name": "",
        "authorization_params": {"state": marker, marker: 1},
        marker: marker,
    }
    errors = validate_provider_block(block)
    assert len(errors) >= 8
    assert not [error for error in errors if marker in error]


# ── Parsing ─────────────────────────────────────────────────────────────────


def test_parse_returns_none_when_a_plugin_declares_no_oauth():
    assert parse_provider_block(None, "Plugin") is None


def test_parse_returns_none_for_an_invalid_block():
    assert parse_provider_block({"flows": ["relay"]}, "Plugin") is None


def test_provider_name_falls_back_to_the_plugin_name():
    assert parse_provider_block(DEVICE, "My Plugin").name == "My Plugin"
    assert parse_provider_block(RELAY, "My Plugin").name == "Example Music"


def test_the_users_client_id_setting_wins_over_the_manifest_default():
    provider = parse_provider_block(_with(RELAY, client_id="manifest-default"), "x")
    assert provider.resolve_client_id({}) == "manifest-default"
    assert provider.resolve_client_id({"client_id": "   "}) == "manifest-default"
    assert provider.resolve_client_id({"client_id": " users-own "}) == "users-own"


def test_client_id_is_read_from_the_setting_the_manifest_names():
    provider = parse_provider_block(_with(RELAY, client_id_setting="app_id"), "x")
    assert provider.resolve_client_id({"client_id": "wrong", "app_id": "right"}) == "right"


def test_there_is_no_client_secret_unless_the_manifest_names_a_setting_for_it():
    public = parse_provider_block(RELAY, "x")
    assert public.resolve_client_secret({"client_secret": "ignored"}) == ""
    confidential = parse_provider_block(_with(RELAY, client_secret_setting="client_secret"), "x")
    assert confidential.resolve_client_secret({"client_secret": " s3 "}) == "s3"
    assert confidential.resolve_client_secret({}) == ""


def test_a_user_client_id_counts_only_if_the_plugin_offers_a_field_for_it():
    block = _with(RELAY, client_id="shipped")
    offered = parse_provider_block(block, "x", {"properties": {"client_id": {"type": "string"}}})
    hidden = parse_provider_block(block, "x", {"properties": {"refresh_seconds": {"type": "integer"}}})
    assert offered.user_client_id is True
    assert offered.resolve_client_id({"client_id": "users-own"}) == "users-own"
    assert hidden.user_client_id is False
    assert hidden.resolve_client_id({"client_id": "users-own"}) == "shipped"


def test_a_plugin_with_no_settings_at_all_offers_no_client_id_field():
    provider = parse_provider_block(_with(RELAY, client_id="shipped"), "x", {})
    assert provider.user_client_id is False
    assert provider.resolve_client_id({"client_id": "users-own"}) == "shipped"


def test_a_user_secret_counts_only_if_the_plugin_offers_a_field_for_it():
    block = _with(RELAY, client_secret_setting="client_secret")
    offered = parse_provider_block(block, "x", {"properties": {"client_secret": {"type": "string"}}})
    hidden = parse_provider_block(block, "x", {"properties": {}})
    assert offered.resolve_client_secret({"client_secret": "s3"}) == "s3"
    assert hidden.resolve_client_secret({"client_secret": "s3"}) == ""


def test_without_a_schema_the_user_may_supply_both():
    provider = parse_provider_block(_with(RELAY, client_secret_setting="client_secret"), "x")
    assert (provider.user_client_id, provider.user_client_secret) == (True, True)


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


# ── 9.9.0 fields ────────────────────────────────────────────────────────────

from src.oauth.errors import ConnectionNotConfigured  # noqa: E402
from src.oauth.provider import Endpoints, _base_url_error  # noqa: E402

HA = {
    "provider_name": "Home Assistant",
    "flows": ["relay"],
    "endpoint_base_setting": "base_url",
    "authorization_url": "/auth/authorize",
    "token_url": "/auth/token",
    "client_id": "https://fiestaboard.app/",
}
HA_SCHEMA = {"type": "object", "properties": {"base_url": {"type": "string"}}}


@pytest.mark.parametrize(
    "field,value",
    [
        ("client_id_param", "client_key"),
        ("scope_separator", ","),
        ("scope_separator", " "),
        ("device_scope_param", "scopes"),
        ("device_poll_scope", True),
        ("plex_product", "FiestaBoard"),
        ("token_auth_method", "post"),
        ("token_auth_method", "basic"),
        ("refresh_params", {"scope": "offline"}),
    ],
)
def test_new_fields_are_known_and_valid(field, value):
    block = _with(RELAY, **{field: value})
    assert validate_provider_block(block) == []
    assert provider_block_warnings(block) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("client_id_param", "client-key"),
        ("client_id_param", ""),
        ("client_id_param", 3),
        ("scope_separator", ";"),
        ("scope_separator", ""),
        ("device_scope_param", "a b"),
        ("device_poll_scope", "yes"),
        ("plex_product", ""),
        ("endpoint_base_setting", "base-url"),
        ("token_auth_method", "jwt"),
        ("token_auth_method", True),
        ("refresh_params", {"scope": 1}),
        ("refresh_params", ["scope"]),
        ("refresh_params", {"grant_type": "x"}),
        ("refresh_params", {"refresh_token": "x"}),
        ("refresh_params", {"client_secret": "x"}),
    ],
)
def test_new_fields_refuse_bad_values(field, value):
    errors = validate_provider_block(_with(RELAY, **{field: value}))
    assert errors and all(field in error for error in errors)


def test_defaults_match_9_8_behaviour():
    provider = parse_provider_block(RELAY, "Music")
    assert provider.client_id_param == "client_id"
    assert provider.scope_separator == " "
    assert provider.device_scope_param == "scope"
    assert provider.device_poll_scope is False
    assert provider.endpoint_base_setting == ""
    assert provider.joined_scopes() == "user-read-currently-playing"
    assert provider.token_auth_method == "post"
    assert provider.refresh_params == {}


def test_refresh_params_may_not_override_a_custom_client_id_param():
    errors = validate_provider_block(_with(RELAY, client_id_param="client_key", refresh_params={"client_key": "x"}))
    assert errors and all("refresh_params" in error for error in errors)


def test_auth_method_and_refresh_params_are_parsed():
    provider = parse_provider_block(_with(RELAY, token_auth_method="basic", refresh_params={"scope": "offline"}), "X")
    assert provider.token_auth_method == "basic"
    assert provider.refresh_params == {"scope": "offline"}


def test_new_fields_are_parsed():
    block = _with(
        DEVICE,
        scopes=["a", "b"],
        client_id_param="client_key",
        scope_separator=",",
        device_scope_param="scopes",
        device_poll_scope=True,
    )
    provider = parse_provider_block(block, "Twitch")
    assert provider.client_id_param == "client_key"
    assert provider.joined_scopes() == "a,b"
    assert provider.device_scope_param == "scopes"
    assert provider.device_poll_scope is True


def test_authorization_params_may_not_set_the_custom_client_id_param():
    errors = validate_provider_block(
        _with(RELAY, client_id_param="client_key", authorization_params={"client_key": "x"})
    )
    assert errors


def test_key_exchange_needs_authorization_and_token_urls_but_no_client_id():
    block = {
        "flows": ["key_exchange"],
        "authorization_url": "https://or.example.com/auth",
        "token_url": "https://or.example.com/api/v1/auth/keys",
    }
    assert validate_provider_block(block) == []
    assert validate_provider_block(_without(block, "authorization_url"))


def test_plex_pin_needs_no_endpoints():
    block = {"flows": ["plex_pin"], "provider_name": "Plex", "plex_product": "FiestaBoard"}
    assert validate_provider_block(block) == []
    provider = parse_provider_block(block, "Plex")
    assert provider.flows == ("plex_pin",)
    assert provider.plex_product == "FiestaBoard"
    assert provider.needs_client_id is False


def test_plex_product_defaults_to_fiestaboard():
    provider = parse_provider_block({"flows": ["plex_pin"]}, "Plex")
    assert provider.plex_product == "FiestaBoard"


def test_relay_and_device_still_need_a_token_url_and_a_client_id():
    assert parse_provider_block(RELAY, "x").needs_client_id is True
    assert validate_provider_block(_without(DEVICE, "token_url"))


# ── Endpoints from plugin settings ──────────────────────────────────────────


def test_endpoint_base_setting_takes_absolute_paths():
    assert validate_provider_block(HA, HA_SCHEMA) == []


@pytest.mark.parametrize("path", ["auth/token", "//evil.example/token", "https://ha.example/auth/token", ""])
def test_endpoint_base_setting_refuses_anything_but_a_path(path):
    assert validate_provider_block(_with(HA, token_url=path), HA_SCHEMA)


def test_endpoint_base_setting_must_name_a_declared_setting():
    errors = validate_provider_block(HA, {"type": "object", "properties": {"other": {}}})
    assert any("endpoint_base_setting" in error for error in errors)


def test_a_manifest_validates_endpoint_base_setting_against_its_schema():
    manifest = {
        "id": "home_assistant_x",
        "name": "HA",
        "version": "1.0.0",
        "settings_schema": {"type": "object", "properties": {"other": {"type": "string"}}},
        "oauth": HA,
    }
    valid, errors = validate_manifest(manifest)
    assert valid is False
    assert any("endpoint_base_setting" in error for error in errors)


def test_endpoints_resolve_from_the_setting():
    provider = parse_provider_block(HA, "HA", HA_SCHEMA)
    endpoints = provider.resolve_endpoints({"base_url": "http://homeassistant.local:8123/"})
    assert endpoints == Endpoints(
        authorization_url="http://homeassistant.local:8123/auth/authorize",
        token_url="http://homeassistant.local:8123/auth/token",
        device_authorization_url="",
    )


def test_fixed_endpoints_resolve_unchanged():
    provider = parse_provider_block(RELAY, "Music")
    endpoints = provider.resolve_endpoints({})
    assert endpoints.authorization_url == RELAY["authorization_url"]
    assert endpoints.token_url == RELAY["token_url"]


@pytest.mark.parametrize("base", [None, "", "   ", "http://203.0.113.9:8123", "ftp://ha.local"])
def test_unusable_base_is_not_configured(base):
    provider = parse_provider_block(HA, "HA", HA_SCHEMA)
    with pytest.raises(ConnectionNotConfigured):
        provider.resolve_endpoints({"base_url": base})


@pytest.mark.parametrize(
    "url",
    [
        "https://ha.example.com",
        "https://203.0.113.9",
        "http://localhost:8123",
        "http://127.0.0.1:8123",
        "http://10.0.0.5:8123",
        "http://172.16.4.2",
        "http://172.31.255.1",
        "http://192.168.1.20:8123",
        "http://169.254.1.1",
        "http://100.64.0.1",
        "http://100.127.255.254",
        "http://[::1]:8123",
        "http://[fd00::5]:8123",
        "http://[fe80::1]",
        "http://homeassistant:8123",
        "http://homeassistant.local:8123",
        "http://ha.lan",
        "http://ha.home.arpa",
        "http://ha.internal",
        "http://192.168.1.20:8123/prefix",
    ],
)
def test_base_url_accepts_https_anywhere_and_http_on_a_home_network(url):
    assert _base_url_error(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://203.0.113.9",
        "http://8.8.8.8",
        "http://172.32.0.1",
        "http://100.128.0.1",
        "http://ha.example.com",
        "http://[2001:db8::1]",
        "https://user:pass@ha.example.com",
        "http://user@192.168.1.2",
        "https://ha.example.com?x=1",
        "https://ha.example.com#frag",
        "ha.local:8123",
        "https://",
        "javascript:alert(1)",
        "",
        None,
    ],
)
def test_base_url_refuses_public_http_userinfo_query_and_junk(url):
    assert _base_url_error(url)
