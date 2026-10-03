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

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

#: Authorization-code flow with PKCE, returning through the static relay page.
FLOW_RELAY = "relay"
#: Device authorization grant (RFC 8628): the user types a short code.
FLOW_DEVICE = "device"
FLOWS = (FLOW_RELAY, FLOW_DEVICE)

DEFAULT_CLIENT_ID_SETTING = "client_id"

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
    }
)

#: Parameters the platform sets itself; a manifest may not override them.
RESERVED_AUTHORIZATION_PARAMS = frozenset(
    {"response_type", "client_id", "redirect_uri", "state", "scope", "code_challenge", "code_challenge_method"}
)

_SETTING_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


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


def _authorization_params_errors(params: Any) -> list[str]:
    if not isinstance(params, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in params.items()
    ):
        return ["oauth.authorization_params must be an object of string values"]
    if not RESERVED_AUTHORIZATION_PARAMS.isdisjoint(params):
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


def validate_provider_block(raw: Any) -> list[str]:
    """Return every problem with a manifest's ``oauth`` block (empty when valid)."""
    if not isinstance(raw, dict):
        return ["oauth must be an object"]

    errors = _credential_errors(raw)

    flow_errors = _flows_errors(raw.get("flows"))
    errors.extend(flow_errors)
    flows = [] if flow_errors else raw["flows"]

    required_endpoints = ["token_url"]
    if FLOW_RELAY in flows:
        required_endpoints.append("authorization_url")
    if FLOW_DEVICE in flows:
        required_endpoints.append("device_authorization_url")
    for key in ("token_url", "authorization_url", "device_authorization_url"):
        if key in required_endpoints or key in raw:
            problem = _endpoint_error(key, raw.get(key))
            if problem:
                errors.append(problem)

    if "provider_name" in raw and not (isinstance(raw["provider_name"], str) and raw["provider_name"].strip()):
        errors.append("oauth.provider_name must be a non-empty string")
    if "scopes" in raw:
        errors.extend(_scopes_errors(raw["scopes"]))
    if "authorization_params" in raw:
        errors.extend(_authorization_params_errors(raw["authorization_params"]))
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
    if raw is None or validate_provider_block(raw):
        return None
    declared = _declared_settings(settings_schema)
    client_id_setting = raw.get("client_id_setting", DEFAULT_CLIENT_ID_SETTING)
    client_secret_setting = raw.get("client_secret_setting", "")
    return OAuthProvider(
        name=str(raw.get("provider_name") or fallback_name).strip(),
        flows=tuple(raw["flows"]),
        token_url=raw["token_url"],
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
    )
