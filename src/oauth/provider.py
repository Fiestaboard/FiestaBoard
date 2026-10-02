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

    def resolve_client_id(self, config: dict[str, Any]) -> str:
        """The client ID to use: the user's setting, else the manifest default."""
        configured = config.get(self.client_id_setting)
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return self.client_id

    def resolve_client_secret(self, config: dict[str, Any]) -> str:
        """The client secret from the plugin's settings, or ``""`` for a public client."""
        if not self.client_secret_setting:
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
    errors = [f"oauth.flows contains unknown flow {flow!r}" for flow in flows if flow not in FLOWS]
    if len(set(map(str, flows))) != len(flows):
        errors.append("oauth.flows must not repeat a flow")
    return errors


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
    reserved = sorted(RESERVED_AUTHORIZATION_PARAMS.intersection(params))
    if reserved:
        return [f"oauth.authorization_params may not set {', '.join(reserved)}; the platform sets those"]
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


def validate_oauth_block(raw: Any) -> list[str]:
    """Return every problem with a manifest's ``oauth`` block (empty when valid)."""
    if not isinstance(raw, dict):
        return ["oauth must be an object"]

    errors = _credential_errors(raw)
    unknown = sorted(set(raw) - _KNOWN_KEYS - {"client_secret"})
    errors.extend(f"oauth.{key} is not a recognised field" for key in unknown)

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
    return errors


def parse_oauth_block(raw: Any, fallback_name: str) -> OAuthProvider | None:
    """Parse a manifest's ``oauth`` block, or ``None`` when absent or invalid.

    Invalid blocks never get this far in production — ``validate_manifest``
    refuses to load the plugin — so ``None`` here means "this plugin has no
    OAuth connection".
    """
    if raw is None or validate_oauth_block(raw):
        return None
    return OAuthProvider(
        name=str(raw.get("provider_name") or fallback_name).strip(),
        flows=tuple(raw["flows"]),
        token_url=raw["token_url"],
        authorization_url=raw.get("authorization_url", ""),
        device_authorization_url=raw.get("device_authorization_url", ""),
        scopes=tuple(raw.get("scopes", ())),
        client_id=raw.get("client_id", "").strip(),
        client_id_setting=raw.get("client_id_setting", DEFAULT_CLIENT_ID_SETTING),
        client_secret_setting=raw.get("client_secret_setting", ""),
        authorization_params=dict(raw.get("authorization_params", {})),
    )
