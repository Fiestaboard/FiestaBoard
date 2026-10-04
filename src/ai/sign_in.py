"""Sign in to an AI provider instead of pasting an API key (FiestaBot).

A provider in ``config.json → ai_providers.providers[]`` may carry
``"sign_in": {"preset": "<name>"}``. Its tokens then live in the OAuth token
store under ``ai.<provider id>`` (never in config, so never in a backup or a
masked response), and :func:`resolve_provider_auth` swaps the current access
token in as the provider's ``api_key`` before every request.

A provider without ``sign_in`` takes exactly the path it always did: the
same dict object goes to the request, key and all.

The OAuth service sees these providers through :class:`AiProviderConnectionSource`,
combined with the plugin registry by :class:`CompositeConnectionSource`.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.oauth import install_id
from src.oauth.overrides import override_url
from src.oauth.provider import FLOW_KEY_EXCHANGE, FLOW_RELAY, OAuthProvider
from src.oauth.service import AI_CONNECTION_PREFIX, ConnectionSource, ConnectionTarget
from src.paths import get_data_dir

from .generator import AINotConfiguredError, AIRejectedError

PRESET_OPENROUTER = "openrouter"
PRESET_HUGGINGFACE = "huggingface"
PRESET_OPENAI_CHATGPT = "openai_chatgpt"

_AGENT_HOST_ID_FILENAME = ".oauth_agent_host_id"

#: FiestaBoard's registered OpenAI app (public client ID, no secret). Empty
#: until OpenAI approves the app: ChatGPT sign-in then falls back to the
#: dynamic client and the loopback redirect, finished by paste. Once set,
#: sign-in comes back through the relay like any other provider.
OPENAI_REGISTERED_CLIENT_ID = ""
#: Overrides :data:`OPENAI_REGISTERED_CLIENT_ID` (testing a registered app).
OPENAI_CLIENT_ID_ENV = "FIESTABOARD_OPENAI_CLIENT_ID"


@dataclass(frozen=True)
class Preset:
    """A built-in sign-in: the OAuth provider plus where requests go afterwards."""

    provider: OAuthProvider
    base_url: str
    protocol: str


PRESETS: dict[str, Preset] = {
    PRESET_OPENROUTER: Preset(
        provider=OAuthProvider(
            name="OpenRouter",
            flows=(FLOW_KEY_EXCHANGE,),
            authorization_url="https://openrouter.ai/auth",
            token_url="https://openrouter.ai/api/v1/auth/keys",
            user_client_id=False,
            user_client_secret=False,
        ),
        base_url="https://openrouter.ai/api/v1",
        protocol="openai",
    ),
    PRESET_HUGGINGFACE: Preset(
        # TODO(oauth-rollout): add "device" (https://huggingface.co/oauth/device)
        # once Hugging Face's device flow is confirmed to accept a CIMD client_id.
        provider=OAuthProvider(
            name="Hugging Face",
            flows=(FLOW_RELAY,),
            authorization_url="https://huggingface.co/oauth/authorize",
            token_url="https://huggingface.co/oauth/token",
            scopes=("inference-api",),
            client_id="https://fiestaboard.app/auth/clients/huggingface.json",
            user_client_id=False,
            user_client_secret=False,
        ),
        base_url="https://router.huggingface.co/v1",
        protocol="openai",
    ),
    PRESET_OPENAI_CHATGPT: Preset(
        # Sign in with ChatGPT, without a registered app (the fallback; see
        # chatgpt_provider). The redirect is loopback only, so the user
        # pastes the address the browser failed to load. OpenAI issues a
        # client (``oaiapp_…``) during the first sign-in; it is kept with the
        # tokens and used from then on.
        #
        # Decision: the ``id_token`` in the token response is discarded
        # unread. FiestaBot never uses identity claims, so validating it
        # (which needs JWKS and a crypto dependency) would protect nothing.
        # If OpenAI's review requires validation, add PyJWT[crypto] then.
        provider=OAuthProvider(
            name="ChatGPT",
            flows=(FLOW_RELAY,),
            authorization_url="https://auth.openai.com/api/accounts/authorize",
            token_url="https://auth.openai.com/api/accounts/oauth/token",
            scopes=("openid", "profile", "email", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct"),
            client_id="dynamic_agent_client",
            user_client_id=False,
            user_client_secret=False,
            authorization_params={"resource": "https://api.openai.com/v1"},
            redirect_uri_override="http://127.0.0.1:1455/auth/callback",
            token_params={"resource": "https://api.openai.com/v1"},
            accept_issued_client_id=True,
            first_sign_in_params={"agent_name_hint": "FiestaBoard"},
        ),
        base_url="https://api.openai.com/v1",
        protocol="openai_responses",
    ),
}


def openai_registered_client_id() -> str:
    """FiestaBoard's registered OpenAI client ID: the env override, else the constant ("" if neither)."""
    return os.environ.get(OPENAI_CLIENT_ID_ENV, "").strip() or OPENAI_REGISTERED_CLIENT_ID.strip()


def chatgpt_provider(agent_host_id: Callable[[], str]) -> OAuthProvider:
    """The ChatGPT sign-in for this build.

    With a registered client ID: that client, the standard relay redirect
    (the browser comes back on its own), no dynamic client and no
    first-sign-in hints. Without one: the dynamic client on the loopback
    redirect, finished by paste, with this install's ``ext_agent_host_id``.
    """
    base = PRESETS[PRESET_OPENAI_CHATGPT].provider
    registered = openai_registered_client_id()
    if registered:
        return replace(
            base,
            client_id=registered,
            redirect_uri_override="",
            accept_issued_client_id=False,
            first_sign_in_params={},
        )
    return replace(
        base,
        authorization_params={**base.authorization_params, "ext_agent_host_id": f"urn:uuid:{agent_host_id()}"},
    )


def load_agent_host_id(data_dir: Path) -> str:
    """This install's id for OpenAI's ``ext_agent_host_id``, created on first use (0600)."""
    return install_id.load_or_create(Path(data_dir) / _AGENT_HOST_ID_FILENAME)


def connection_id_for(provider_id: str) -> str:
    return f"{AI_CONNECTION_PREFIX}{provider_id}"


def sign_in_preset(provider: dict[str, Any]) -> str | None:
    """The provider's known sign-in preset, or ``None`` (an api_key provider)."""
    block = provider.get("sign_in")
    preset = block.get("preset") if isinstance(block, dict) else None
    return preset if isinstance(preset, str) and preset in PRESETS else None


def _oauth() -> Any:
    from src.oauth.service import get_oauth_service

    return get_oauth_service()


# ── request time ────────────────────────────────────────────────────────────


def resolve_provider_auth(provider: dict[str, Any], service: Any = None) -> dict[str, Any]:
    """*provider* ready to send: unchanged without sign-in, else with the current token as ``api_key``.

    A pasted ``api_key`` is ignored while ``sign_in`` is set. Raises
    :class:`AIRejectedError` when the sign-in is missing or must be redone
    (:class:`AINotConfiguredError` when *provider* points it at another host).
    """
    preset_name = sign_in_preset(provider)
    if preset_name is None:
        return provider
    preset = PRESETS[preset_name]
    if provider.get("base_url") and not _on_preset_host(str(provider["base_url"]), preset.base_url):
        # The sign-in's token belongs to the preset's service, never another host.
        raise AINotConfiguredError(
            f"{preset.provider.name} sign-in only works with {override_url(preset.base_url)}. "
            "Clear the base URL, or use an API key for this one."
        )
    token = (service or _oauth()).get_access_token(connection_id_for(str(provider.get("id", ""))))
    if not token:
        name = provider.get("name") or preset.provider.name
        raise AIRejectedError(f"Sign in to {name} again in Settings → AI.")
    resolved = dict(provider)
    resolved["api_key"] = token
    if not resolved.get("base_url"):
        resolved["base_url"] = override_url(preset.base_url)
    if not resolved.get("protocol"):
        resolved["protocol"] = preset.protocol
    return resolved


async def resolve_provider_auth_async(provider: dict[str, Any]) -> dict[str, Any]:
    """:func:`resolve_provider_auth` off the event loop (a refresh is a blocking request)."""
    if sign_in_preset(provider) is None:
        return provider
    return await asyncio.to_thread(resolve_provider_auth, provider)


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url.strip())
    return parts.scheme.lower(), parts.netloc.lower()


def _on_preset_host(base_url: str, preset_base_url: str) -> bool:
    """Whether *base_url* is on the preset's own scheme and host (or its dev override's)."""
    origin = _origin(base_url)
    return origin in {_origin(preset_base_url), _origin(override_url(preset_base_url))}


async def report_provider_rejected(provider: dict[str, Any], rejected_token: str | None = None) -> None:
    """The provider answered 401 to *rejected_token*: let the OAuth service refresh or mark the sign-in.

    *provider* is the stored (unresolved) provider; *rejected_token* is the
    key that was actually sent, so a 401 for a token that has since been
    replaced does not mark the new one rejected.
    """
    if sign_in_preset(provider) is None:
        return
    await asyncio.to_thread(
        _oauth().report_rejected, connection_id_for(str(provider.get("id", ""))), rejected_token or None
    )


def forget_removed_providers(before: dict[str, Any], after: dict[str, Any], service: Any = None) -> None:
    """Drop the tokens of every provider signed in in *before* that is not, with the same preset, in *after*.

    Switching a provider to another preset forgets too: the old service's
    token must never be sent to the new one.
    """

    def signed_in(block: dict[str, Any]) -> set[tuple[str, str]]:
        return {
            (str(p["id"]), str(sign_in_preset(p)))
            for p in block.get("providers") or []
            if isinstance(p, dict) and p.get("id") and sign_in_preset(p) is not None
        }

    removed = {provider_id for provider_id, _ in signed_in(before) - signed_in(after)}
    if not removed:
        return
    oauth = service or _oauth()
    for provider_id in sorted(removed):
        oauth.forget(connection_id_for(provider_id))


# ── connection sources ──────────────────────────────────────────────────────


def _configured_providers() -> dict[str, Any]:
    from src.config_manager import get_config_manager

    return get_config_manager().get_ai_providers()


class AiProviderConnectionSource:
    """Connection targets for FiestaBot's signed-in AI providers (ids ``ai.<provider id>``)."""

    def __init__(
        self,
        providers: Callable[[], dict[str, Any]] | None = None,
        agent_host_id: Callable[[], str] | None = None,
    ) -> None:
        self._providers = providers or _configured_providers
        self._agent_host_id = agent_host_id or (lambda: load_agent_host_id(get_data_dir()))

    def _target(self, provider: dict[str, Any]) -> ConnectionTarget | None:
        preset_name = sign_in_preset(provider)
        if preset_name is None or not provider.get("id"):
            return None
        oauth_provider = PRESETS[preset_name].provider
        if preset_name == PRESET_OPENAI_CHATGPT:
            oauth_provider = chatgpt_provider(self._agent_host_id)
        name = provider.get("name") or oauth_provider.name
        return ConnectionTarget(
            connection_id=connection_id_for(str(provider["id"])),
            plugin_id="ai",
            instance_label=None,
            plugin_name=f"{name} (FiestaBot)",
            provider=oauth_provider,
            kind="ai",
        )

    def _provider_list(self) -> list[dict[str, Any]]:
        return [p for p in self._providers().get("providers") or [] if isinstance(p, dict)]

    def get(self, connection_id: str) -> ConnectionTarget | None:
        if not connection_id.startswith(AI_CONNECTION_PREFIX):
            return None
        provider_id = connection_id[len(AI_CONNECTION_PREFIX) :]
        for provider in self._provider_list():
            if str(provider.get("id")) == provider_id:
                return self._target(provider)
        return None

    def all(self) -> list[ConnectionTarget]:
        targets = (self._target(p) for p in self._provider_list())
        return [t for t in targets if t is not None]

    def id_for(self, plugin: object) -> str | None:
        return None

    def invalidate(self, connection_id: str) -> None:
        """Nothing is cached: every request resolves the token afresh."""


class CompositeConnectionSource:
    """Plugins from the registry, plus FiestaBot's AI providers under ``ai.``."""

    def __init__(self, plugins: ConnectionSource, ai: ConnectionSource) -> None:
        self._plugins = plugins
        self._ai = ai

    def _for(self, connection_id: str) -> ConnectionSource:
        return self._ai if connection_id.startswith(AI_CONNECTION_PREFIX) else self._plugins

    def get(self, connection_id: str) -> ConnectionTarget | None:
        return self._for(connection_id).get(connection_id)

    def all(self) -> list[ConnectionTarget]:
        return [*self._plugins.all(), *self._ai.all()]

    def id_for(self, plugin: object) -> str | None:
        return self._plugins.id_for(plugin)

    def invalidate(self, connection_id: str) -> None:
        self._for(connection_id).invalidate(connection_id)
