"""The ``oauth`` block of a plugin manifest.

A plugin that needs a user to sign in to a third-party service declares the
provider here; the platform runs the flow and stores the tokens. Nothing in
``src/`` knows the name of any provider.

.. code-block:: json

    "oauth": {
      "provider_name": "Example Music",
      "flows": ["relay"],
      "authorization_url": "https://accounts.example.com/authorize",
      "token_url": "https://accounts.example.com/api/token",
      "scopes": ["user-read-currently-playing"],
      "client_id_setting": "client_id"
    }

This module is pure (no I/O, no imports from the rest of ``src``) so
``src/plugins/manifest.py`` can validate the block at load time.

Validation messages are fixed text. They name the rule that was broken and
never repeat a value from the block, so nothing a manifest contains can reach
a log line through them.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .errors import ConnectionNotConfigured

#: Authorization-code flow with PKCE, returning through the static relay page.
FLOW_RELAY = "relay"
#: Device authorization grant (RFC 8628): the user types a short code.
FLOW_DEVICE = "device"
#: OpenRouter-style PKCE exchange that yields an API key (no client ID).
FLOW_KEY_EXCHANGE = "key_exchange"
#: Plex PIN sign-in: the board creates a PIN and polls plex.tv for its token.
FLOW_PLEX_PIN = "plex_pin"
FLOWS = (FLOW_RELAY, FLOW_DEVICE, FLOW_KEY_EXCHANGE, FLOW_PLEX_PIN)
#: Flows that identify the app to the provider with a client ID.
CLIENT_ID_FLOWS = frozenset({FLOW_RELAY, FLOW_DEVICE})

DEFAULT_CLIENT_ID_SETTING = "client_id"
DEFAULT_CLIENT_ID_PARAM = "client_id"
DEFAULT_SCOPE_SEPARATOR = " "
SCOPE_SEPARATORS = (" ", ",")
DEFAULT_DEVICE_SCOPE_PARAM = "scope"
DEFAULT_PLEX_PRODUCT = "FiestaBoard"
#: How the client authenticates at the token endpoint: the secret in the POST
#: body (``client_secret_post``) or an HTTP Basic header (``client_secret_basic``).
TOKEN_AUTH_METHODS = ("post", "basic")
DEFAULT_TOKEN_AUTH_METHOD = "post"
#: Refresh-form fields the platform sets itself; ``refresh_params`` may not set them.
RESERVED_REFRESH_PARAMS = frozenset({"grant_type", "refresh_token", "client_id", "client_secret"})

_KNOWN_KEYS = frozenset(
    {
        "provider_name",
        "flows",
        "authorization_url",
        "token_url",
        "device_authorization_url",
        "scopes",
        "client_id",
        "client_id_setting",
        "client_secret_setting",
        "authorization_params",
        "app_setup_url",
        # 9.11.0
        "client_id_param",
        "scope_separator",
        "device_scope_param",
        "device_poll_scope",
        "endpoint_base_setting",
        "plex_product",
        "token_auth_method",
        "refresh_params",
    }
)

#: Parameters the platform sets itself; a manifest may not override them.
RESERVED_AUTHORIZATION_PARAMS = frozenset(
    {"response_type", "client_id", "redirect_uri", "state", "scope", "code_challenge", "code_challenge_method"}
)

_SETTING_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_ENDPOINT_KEYS = ("token_url", "authorization_url", "device_authorization_url")

#: Address ranges a board's own network uses: plain http is allowed to these
#: for a provider that lives on the LAN (Home Assistant). RFC 1918, loopback,
#: link-local, CGNAT (Tailscale and friends) and IPv6 ULA.
_HOME_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
        "100.64.0.0/10",
        "::1/128",
        "fe80::/10",
        "fc00::/7",
    )
)
# Link-local (169.254/16) and ``.internal`` are left out on purpose: they are
# where cloud metadata services live. Docker's name for its host stays in.
_HOME_SUFFIXES = (".local", ".lan", ".home.arpa", ".docker.internal")
_METADATA_HOSTS = frozenset({"metadata", ipaddress.ip_address("fd00:ec2::254")})


@dataclass(frozen=True)
class Endpoints:
    """A provider's endpoints as they apply to one plugin's settings."""

    authorization_url: str
    token_url: str
    device_authorization_url: str


@dataclass(frozen=True)
class OAuthProvider:
    """A parsed, validated ``oauth`` manifest block."""

    name: str
    flows: tuple[str, ...]
    token_url: str
    authorization_url: str = ""
    device_authorization_url: str = ""
    scopes: tuple[str, ...] = ()
    client_id: str = ""
    client_id_setting: str = DEFAULT_CLIENT_ID_SETTING
    client_secret_setting: str = ""
    authorization_params: dict[str, str] = field(default_factory=dict)
    #: Whether the plugin's settings offer a field for the client ID (and,
    #: separately, for the secret). A value saved under a key the plugin does
    #: not offer is ignored: a plugin that ships its own app and no field means
    #: users cannot swap that app out, through the UI or around it.
    user_client_id: bool = True
    user_client_secret: bool = True
    #: Where a user creates their own app with the provider (its developer
    #: dashboard). The settings link to it from the guided setup.
    app_setup_url: str = ""
    #: The name the provider gives the client-ID parameter (TikTok: ``client_key``).
    client_id_param: str = DEFAULT_CLIENT_ID_PARAM
    #: How scopes are joined (Strava, TikTok, Todoist: ``,``).
    scope_separator: str = DEFAULT_SCOPE_SEPARATOR
    #: The scope parameter on the device authorization request (Twitch: ``scopes``).
    device_scope_param: str = DEFAULT_DEVICE_SCOPE_PARAM
    #: Whether the device token poll also sends the scopes (Twitch).
    device_poll_scope: bool = False
    #: A settings key holding the base URL the endpoint paths hang off, for a
    #: provider that runs on the user's own network (Home Assistant).
    endpoint_base_setting: str = ""
    #: ``X-Plex-Product`` for the plex_pin flow.
    plex_product: str = DEFAULT_PLEX_PRODUCT
    #: ``post`` (secret in the form) or ``basic`` (HTTP Basic) at the token endpoint.
    token_auth_method: str = DEFAULT_TOKEN_AUTH_METHOD
    #: Extra fields sent with every refresh (WHOOP: ``{"scope": "offline"}``).
    refresh_params: dict[str, str] = field(default_factory=dict)
    # The fields below are never read from a manifest: only built-in presets
    # (FiestaBot AI sign-in, ``src/ai/sign_in.py``) set them.
    #: A fixed redirect URI used instead of the relay (OpenAI's loopback
    #: address). The browser cannot come back, so the user pastes the address.
    redirect_uri_override: str = ""
    #: Extra fields for the authorization-code exchange (a ``resource``).
    token_params: dict[str, str] = field(default_factory=dict)
    #: The provider issues a client during sign-in, in the redirect address;
    #: it is kept with the tokens and used for refresh and the next sign-in.
    accept_issued_client_id: bool = False
    #: Authorization parameters sent only before a client has been issued.
    first_sign_in_params: dict[str, str] = field(default_factory=dict)

    @property
    def needs_client_id(self) -> bool:
        """Whether any declared flow identifies the app with a client ID."""
        return any(flow in CLIENT_ID_FLOWS for flow in self.flows)

    def joined_scopes(self) -> str:
        return self.scope_separator.join(self.scopes)

    def resolve_endpoints(self, config: dict[str, Any]) -> Endpoints:
        """The endpoints to call, joined to the plugin's base-URL setting when it has one.

        Raises :class:`ConnectionNotConfigured` when that setting is missing or
        is not an address the board may send credentials to.
        """
        if not self.endpoint_base_setting:
            return Endpoints(self.authorization_url, self.token_url, self.device_authorization_url)
        raw = config.get(self.endpoint_base_setting)
        base = raw.strip() if isinstance(raw, str) else ""
        if not base or _base_url_error(base):
            raise ConnectionNotConfigured(
                f"{self.name}'s address must be https, or http on your home network. "
                "Check it in the plugin's settings and save."
            )
        base = base.rstrip("/")

        def join(path: str) -> str:
            return f"{base}{path}" if path else ""

        return Endpoints(join(self.authorization_url), join(self.token_url), join(self.device_authorization_url))

    def resolve_client_id(self, config: dict[str, Any]) -> str:
        """The client ID to use: the user's setting if the plugin offers one, else the manifest's."""
        configured = config.get(self.client_id_setting) if self.user_client_id else None
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return self.client_id

    def resolve_client_secret(self, config: dict[str, Any]) -> str:
        """The client secret from the plugin's settings, or ``""`` for a public client."""
        if not self.client_secret_setting or not self.user_client_secret:
            return ""
        configured = config.get(self.client_secret_setting)
        return configured.strip() if isinstance(configured, str) else ""


def _endpoint_error(key: str, value: Any) -> str | None:
    """Why *value* is not an acceptable provider endpoint, or ``None``.

    Endpoints carry authorization codes, refresh tokens and client secrets, so
    they must be ``https``. Plain ``http`` is allowed only to a loopback host,
    which is what a local mock provider in a test looks like.
    """
    if not isinstance(value, str) or not value:
        return f"oauth.{key} must be a non-empty string"
    parts = urlsplit(value)
    if parts.scheme == "https" and parts.hostname:
        return None
    if parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS:
        return None
    return f"oauth.{key} must be an https:// URL"


def _is_home_host(hostname: str) -> bool:
    """Whether *hostname* names something on the board's own network. No DNS."""
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        name = hostname.rstrip(".").lower()
        if name in _METADATA_HOSTS:
            return False
        return name == "localhost" or "." not in name or name.endswith(_HOME_SUFFIXES)
    if address in _METADATA_HOSTS:
        return False
    return any(address in network for network in _HOME_NETWORKS if network.version == address.version)


def _base_url_error(value: Any) -> str | None:
    """Why *value* is not a usable base URL for settings-based endpoints, or ``None``.

    ``https`` to any host; plain ``http`` only to a host on the user's own
    network, judged from the hostname alone. Never userinfo, query or fragment.
    """
    if not isinstance(value, str) or not value.strip():
        return "the address is empty"
    try:
        parts = urlsplit(value.strip())
        hostname = parts.hostname
        _ = parts.port
    except ValueError:
        return "the address is not a valid web address"
    if not hostname or parts.username is not None or parts.password is not None:
        return "the address must be a plain web address"
    if parts.query or parts.fragment or "?" in value or "#" in value:
        return "the address must not have a query or fragment"
    if parts.scheme == "https":
        return None
    if parts.scheme == "http" and _is_home_host(hostname):
        return None
    return "the address must be https, or http on your home network"


def _endpoint_path_error(key: str, value: Any) -> str | None:
    if isinstance(value, str) and value.startswith("/") and not value.startswith("//") and "://" not in value:
        return None
    return f"oauth.{key} must be a path starting with / when oauth.endpoint_base_setting is set"


def _flows_errors(flows: Any) -> list[str]:
    if not isinstance(flows, list) or not flows:
        return [f"oauth.flows must be a non-empty array of: {', '.join(FLOWS)}"]
    if any(flow not in FLOWS for flow in flows):
        return [f"oauth.flows contains an unknown flow; the flows are: {', '.join(FLOWS)}"]
    if len(set(flows)) != len(flows):
        return ["oauth.flows must not repeat a flow"]
    return []


def _scopes_errors(scopes: Any) -> list[str]:
    if not isinstance(scopes, list):
        return ["oauth.scopes must be an array of strings"]
    if any(not isinstance(scope, str) or not scope or any(ch.isspace() for ch in scope) for scope in scopes):
        return ["oauth.scopes entries must be non-empty strings without whitespace"]
    return []


def _authorization_params_errors(params: Any, client_id_param: str = DEFAULT_CLIENT_ID_PARAM) -> list[str]:
    if not isinstance(params, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()
    ):
        return ["oauth.authorization_params must be an object of string values"]
    if not (RESERVED_AUTHORIZATION_PARAMS | {client_id_param}).isdisjoint(params):
        reserved = ", ".join(sorted(RESERVED_AUTHORIZATION_PARAMS))
        return [f"oauth.authorization_params may not set any of: {reserved}; the platform sets those"]
    return []


def _credential_errors(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "client_secret" in raw:
        # The single most damaging mistake available in this block: plugin
        # repositories are public.
        errors.append(
            "oauth.client_secret must never be in a manifest; declare oauth.client_secret_setting "
            "and let each user enter their own secret in the plugin's settings"
        )
    if "client_id" in raw and not isinstance(raw["client_id"], str):
        errors.append("oauth.client_id must be a string")
    for key in ("client_id_setting", "client_secret_setting"):
        if key in raw and not (isinstance(raw[key], str) and _SETTING_KEY_RE.match(raw[key])):
            errors.append(f"oauth.{key} must name a key in settings_schema")
    return errors


def _refresh_params_errors(params: Any, client_id_param: Any) -> list[str]:
    if not isinstance(params, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()
    ):
        return ["oauth.refresh_params must be an object of string values"]
    reserved = RESERVED_REFRESH_PARAMS | ({client_id_param} if isinstance(client_id_param, str) else set())
    if not reserved.isdisjoint(params):
        return [
            f"oauth.refresh_params may not set any of: {', '.join(sorted(RESERVED_REFRESH_PARAMS))} "
            "or the client ID parameter; the platform sets those"
        ]
    return []


def _new_field_errors(raw: dict[str, Any], settings_schema: Any) -> list[str]:
    errors: list[str] = []
    for key in ("client_id_param", "device_scope_param", "endpoint_base_setting"):
        if key in raw and not (isinstance(raw[key], str) and _SETTING_KEY_RE.match(raw[key])):
            errors.append(f"oauth.{key} must be a parameter name (letters, digits, underscore)")
    if "scope_separator" in raw and raw["scope_separator"] not in SCOPE_SEPARATORS:
        errors.append('oauth.scope_separator must be " " or ","')
    if "device_poll_scope" in raw and not isinstance(raw["device_poll_scope"], bool):
        errors.append("oauth.device_poll_scope must be true or false")
    if "plex_product" in raw and not (isinstance(raw["plex_product"], str) and raw["plex_product"].strip()):
        errors.append("oauth.plex_product must be a non-empty string")
    if "token_auth_method" in raw and raw["token_auth_method"] not in TOKEN_AUTH_METHODS:
        errors.append('oauth.token_auth_method must be "post" or "basic"')
    if "refresh_params" in raw:
        errors.extend(_refresh_params_errors(raw["refresh_params"], raw.get("client_id_param")))
    base_setting = raw.get("endpoint_base_setting")
    declared = _declared_settings(settings_schema)
    if isinstance(base_setting, str) and declared is not None and base_setting not in declared:
        errors.append("oauth.endpoint_base_setting must name a key in settings_schema")
    return errors


def validate_provider_block(raw: Any, settings_schema: Any = None) -> list[str]:
    """Return every problem with a manifest's ``oauth`` block (empty when valid).

    *settings_schema*, when given, is checked against settings the block names
    (``endpoint_base_setting``).
    """
    if not isinstance(raw, dict):
        return ["oauth must be an object"]

    errors = _credential_errors(raw)

    flow_errors = _flows_errors(raw.get("flows"))
    errors.extend(flow_errors)
    flows = [] if flow_errors else raw["flows"]

    errors.extend(_new_field_errors(raw, settings_schema))

    # A plex_pin-only block has no endpoints at all: they are plex.tv's.
    required_endpoints = [] if flows and set(flows) <= {FLOW_PLEX_PIN} else ["token_url"]
    if FLOW_RELAY in flows or FLOW_KEY_EXCHANGE in flows:
        required_endpoints.append("authorization_url")
    if FLOW_DEVICE in flows:
        required_endpoints.append("device_authorization_url")
    endpoint_check = _endpoint_path_error if "endpoint_base_setting" in raw else _endpoint_error
    for key in _ENDPOINT_KEYS:
        if key in required_endpoints or key in raw:
            problem = endpoint_check(key, raw.get(key))
            if problem:
                errors.append(problem)

    if "provider_name" in raw and not (isinstance(raw["provider_name"], str) and raw["provider_name"].strip()):
        errors.append("oauth.provider_name must be a non-empty string")
    if "scopes" in raw:
        errors.extend(_scopes_errors(raw["scopes"]))
    if "authorization_params" in raw:
        client_id_param = raw.get("client_id_param", DEFAULT_CLIENT_ID_PARAM)
        errors.extend(
            _authorization_params_errors(
                raw["authorization_params"],
                client_id_param if isinstance(client_id_param, str) else DEFAULT_CLIENT_ID_PARAM,
            )
        )
    if "app_setup_url" in raw:
        problem = _endpoint_error("app_setup_url", raw["app_setup_url"])
        if problem:
            errors.append(problem)
    return errors


def provider_block_warnings(raw: Any) -> list[str]:
    """The *non-fatal* findings in an ``oauth`` block: fields this core does not know.

    Not an error, for the reason given at ``settings_schema_ui_warnings`` in
    ``src/plugins/manifest.py``: plugins auto-update hourly and cores are
    updated by hand, so a plugin routinely lands on a core older than the one
    it was written against. Refusing a manifest for a field a newer core
    added would uninstall the plugin from every board a release behind. The
    field is ignored and the plugin loads; the warning surfaces through
    ``GET /plugins/errors`` so a typo is still visible.

    The message is fixed text and does not name the field, because nothing a
    manifest contains may reach a log line through this module.
    """
    if not isinstance(raw, dict) or not (set(raw) - _KNOWN_KEYS - {"client_secret"}):
        return []
    return [
        "oauth has a field this FiestaBoard does not recognise, which is ignored. Check the spelling; "
        f"if it is spelled correctly it was added in a newer FiestaBoard. Known fields: {', '.join(sorted(_KNOWN_KEYS))}"
    ]


def _declared_settings(settings_schema: Any) -> set[str] | None:
    if not isinstance(settings_schema, dict):
        return None
    properties = settings_schema.get("properties")
    return set(properties) if isinstance(properties, dict) else set()


def parse_provider_block(raw: Any, fallback_name: str, settings_schema: Any = None) -> OAuthProvider | None:
    """Parse a manifest's ``oauth`` block, or ``None`` when absent or invalid.

    Invalid blocks never get this far in production — ``validate_manifest``
    refuses to load the plugin — so ``None`` here means "this plugin has no
    OAuth connection".

    *settings_schema* is the plugin's ``settings_schema``. Pass it whenever it
    is known: it decides whether a user may supply their own client ID and
    secret (only through fields the plugin offers). Without it, both are
    allowed, which is right only for callers that have no manifest to hand.
    """
    if raw is None or validate_provider_block(raw, settings_schema):
        return None
    declared = _declared_settings(settings_schema)
    client_id_setting = raw.get("client_id_setting", DEFAULT_CLIENT_ID_SETTING)
    client_secret_setting = raw.get("client_secret_setting", "")
    return OAuthProvider(
        name=str(raw.get("provider_name") or fallback_name).strip(),
        flows=tuple(raw["flows"]),
        token_url=raw.get("token_url", ""),
        authorization_url=raw.get("authorization_url", ""),
        device_authorization_url=raw.get("device_authorization_url", ""),
        scopes=tuple(raw.get("scopes", ())),
        client_id=raw.get("client_id", "").strip(),
        client_id_setting=client_id_setting,
        client_secret_setting=client_secret_setting,
        authorization_params=dict(raw.get("authorization_params", {})),
        user_client_id=declared is None or client_id_setting in declared,
        user_client_secret=declared is None or client_secret_setting in declared,
        app_setup_url=raw.get("app_setup_url", ""),
        client_id_param=raw.get("client_id_param", DEFAULT_CLIENT_ID_PARAM),
        scope_separator=raw.get("scope_separator", DEFAULT_SCOPE_SEPARATOR),
        device_scope_param=raw.get("device_scope_param", DEFAULT_DEVICE_SCOPE_PARAM),
        device_poll_scope=bool(raw.get("device_poll_scope", False)),
        endpoint_base_setting=raw.get("endpoint_base_setting", ""),
        plex_product=str(raw.get("plex_product") or DEFAULT_PLEX_PRODUCT).strip(),
        token_auth_method=raw.get("token_auth_method", DEFAULT_TOKEN_AUTH_METHOD),
        refresh_params=dict(raw.get("refresh_params", {})),
    )
