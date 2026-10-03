"""The public AI API for plugins: one completion from FiestaBot's AI providers.

A plugin calls :meth:`PluginBase.ai_complete <src.plugins.base.PluginBase.ai_complete>`
(or :func:`complete` / :func:`complete_async` directly). The request goes
through exactly what FiestaBot uses: the providers in Settings → AI Providers,
their protocol (``openai``, ``anthropic``, ``openai_responses``) and, for a
signed-in provider (OpenRouter, Hugging Face, ChatGPT), its current token. AI
turned off in Settings (``enabled: false``) is honoured: nothing is sent.

Failures are one of three :class:`AIError` subclasses a plugin can catch:

- :class:`AINotConfiguredError`: AI is off, no provider, unknown
  ``provider_id``, or the provider has no model.
- :class:`AIRejectedError`: the key or sign-in was refused, or the user must
  sign in again (Settings → AI Providers).
- :class:`AIProviderError`: unreachable, an error answer, or an empty or
  unparseable reply.

Added in FiestaBoard 9.9.0.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from .generator import (
    _DEFAULT_MAX_TOKENS,
    _DEFAULT_TEMPERATURE,
    AIGenerationError,
    AINotConfiguredError,
    AIProviderError,
    AIRejectedError,
    _extract_json_object,
    _extract_message_content,
    _post_chat_completion,
    _resolve_model,
    _resolve_provider,
)
from .protocols import get_protocol

logger = logging.getLogger(__name__)

__all__ = [
    "AI_PROVIDERS_OPTIONS_ID",
    "AICompletion",
    "AIError",
    "AINotConfiguredError",
    "AIProviderError",
    "AIRejectedError",
    "complete",
    "complete_async",
    "provider_options",
    "providers",
]

#: Every AI failure a plugin can see. The same class as core's
#: ``AIGenerationError``, so ``except AIError`` catches all three kinds.
AIError = AIGenerationError

#: The ``ui:options.options_id`` core answers for any plugin: FiestaBot's providers.
AI_PROVIDERS_OPTIONS_ID = "ai_providers"

DEFAULT_TIMEOUT_SECONDS = 60.0
_ROLES = frozenset({"system", "user", "assistant"})
_PROTOCOL_LABELS = {
    "openai": "OpenAI-compatible",
    "anthropic": "Anthropic",
    "openai_responses": "OpenAI Responses",
}
_JSON_INSTRUCTION = "Reply with one JSON object and nothing else: no prose, no markdown fences."


@dataclass(frozen=True)
class AICompletion:
    """One answer. ``str(result)`` is its text.

    Attributes:
        text: The model's reply.
        model: The model that answered.
        provider_id: The FiestaBot provider used.
        usage: ``{prompt_tokens, completion_tokens, total_tokens}`` (values may be ``None``).
        data: The parsed object when ``json=True``, else ``None``.
    """

    text: str
    model: str
    provider_id: str
    usage: dict[str, int | None] = field(default_factory=dict)
    data: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.text


# ── settings ────────────────────────────────────────────────────────────────


def _providers_block() -> dict[str, Any]:
    from src.config_manager import get_config_manager

    return get_config_manager().get_ai_providers() or {}


def _effective_protocol(provider: dict[str, Any]) -> str:
    """The protocol a request will use (a sign-in preset fills in a missing one)."""
    from .sign_in import PRESETS, sign_in_preset

    protocol = provider.get("protocol")
    if not protocol:
        preset = sign_in_preset(provider)
        protocol = PRESETS[preset].protocol if preset else None
    return get_protocol(protocol).name


def providers() -> list[dict[str, Any]]:
    """FiestaBot's providers, safe to show: no keys, no tokens.

    Each is ``{id, name, protocol, model, models, default, sign_in}``;
    ``model`` is the one used when a call names none, ``default`` marks the
    provider used when a call passes no ``provider_id``, and ``sign_in`` is
    the sign-in preset name or ``None``. Empty while AI is off.
    """
    from .sign_in import sign_in_preset

    block = _providers_block()
    if not block.get("enabled"):
        return []
    listed = [p for p in block.get("providers") or [] if isinstance(p, dict) and p.get("id")]
    ids = [str(p["id"]) for p in listed]
    default_id = block.get("default_provider_id")
    if default_id not in ids:
        default_id = ids[0] if ids else None
    out = []
    for provider in listed:
        models = [m for m in provider.get("models") or [] if isinstance(m, str) and m]
        out.append(
            {
                "id": str(provider["id"]),
                "name": str(provider.get("name") or provider["id"]),
                "protocol": _effective_protocol(provider),
                "model": provider.get("default_model") or (models[0] if models else None),
                "models": models,
                "default": provider["id"] == default_id,
                "sign_in": sign_in_preset(provider),
            }
        )
    return out


def provider_options(request: Any) -> Any:
    """The ``ai_providers`` picker: one :class:`~src.plugins.base.Option` per provider.

    Every protocol is listed. Raises
    :class:`~src.plugins.base.OptionsUnavailable` while AI is off or no
    provider is set up, so the field shows why it is empty.
    """
    from src.plugins.base import Option, OptionsResult, OptionsUnavailable

    if not _providers_block().get("enabled"):
        raise OptionsUnavailable("FiestaBot's AI is turned off. Turn it on in Settings → AI Providers.")
    listed = providers()
    if not listed:
        raise OptionsUnavailable("No AI provider is set up. Add one in Settings → AI Providers.")
    query = (getattr(request, "query", "") or "").strip().lower()
    options = []
    for p in listed:
        label = _PROTOCOL_LABELS.get(p["protocol"], p["protocol"])
        parts = [label]
        if p["model"]:
            parts.append(p["model"])
        if p["sign_in"]:
            parts.append("signed in")
        if p["default"]:
            parts.append("FiestaBot's default")
        if query and not any(query in s.lower() for s in (p["id"], p["name"], label)):
            continue
        options.append(Option(value=p["id"], label=p["name"], description=" · ".join(parts)))
    limit = getattr(request, "limit", None) or len(options)
    return OptionsResult(options=options[:limit], has_more=len(options) > limit, total=len(options))


# ── completion ──────────────────────────────────────────────────────────────


def _messages(messages: Any) -> list[dict[str, str]]:
    if isinstance(messages, str):
        if not messages.strip():
            raise ValueError("ai_complete: the prompt is empty")
        return [{"role": "user", "content": messages}]
    if not isinstance(messages, list) or not messages:
        raise ValueError("ai_complete: messages must be a prompt string or a non-empty list of messages")
    out = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in _ROLES:
            raise ValueError("ai_complete: each message needs a role of system, user or assistant")
        if not isinstance(message.get("content"), str):
            raise ValueError("ai_complete: each message needs a string content")
        out.append({"role": message["role"], "content": message["content"]})
    return out


async def complete_async(
    messages: str | list[dict[str, str]],
    *,
    provider_id: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> AICompletion:
    """Ask one of FiestaBot's AI providers; see :meth:`PluginBase.ai_complete`.

    Always reads Settings → AI Providers and sends with core's own HTTP
    client: a plugin can neither hand in its own client (it would see the
    key or sign-in token) nor its own settings (they would skip "AI is off").
    """
    return await _complete_async(
        messages,
        provider_id=provider_id,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json=json,
        timeout=timeout,
    )


async def _complete_async(
    messages: str | list[dict[str, str]],
    *,
    provider_id: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json: bool = False,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    providers_block: dict[str, Any] | None = None,
    client: httpx.AsyncClient | None = None,
) -> AICompletion:
    """:func:`complete_async` with core-only test seams (settings and HTTP client)."""
    chat = _messages(messages)
    block = _providers_block() if providers_block is None else providers_block
    provider = _resolve_provider(block, provider_id)
    chosen_model = _resolve_model(provider, model)
    protocol = get_protocol(_effective_protocol(provider))
    if json:
        chat = [{"role": "system", "content": _JSON_INSTRUCTION}, *chat]
    payload = protocol.build_body(
        chosen_model,
        chat,
        _DEFAULT_TEMPERATURE if temperature is None else float(temperature),
        _DEFAULT_MAX_TOKENS if max_tokens is None else int(max_tokens),
    )
    from .sign_in import sign_in_preset

    signed_in = sign_in_preset(provider) is not None
    for attempt in (1, 2):
        try:
            response = await _post_chat_completion(
                provider, payload, protocol=protocol, timeout_seconds=timeout, client=client
            )
            break
        except AIRejectedError:
            # A 401 on a signed-in provider was reported; the platform may have
            # refreshed the token. Try once more; a dead sign-in raises again.
            if attempt == 2 or not signed_in:
                raise
    text = _extract_message_content(response, protocol)
    data = None
    if json:
        try:
            data = _extract_json_object(text)
        except AIGenerationError as exc:
            raise AIProviderError(str(exc)) from exc
        if not isinstance(data, dict):
            raise AIProviderError("Model output was not a JSON object.")
    logger.debug("AI completion for a plugin from %s (%s)", provider.get("id"), chosen_model)
    return AICompletion(
        text=text,
        model=chosen_model,
        provider_id=str(provider.get("id")),
        usage=protocol.parse_usage(response),
        data=data,
    )


def complete(messages: str | list[dict[str, str]], **kwargs: Any) -> AICompletion:
    """:func:`complete_async` for synchronous code, such as ``fetch_data``.

    Inside a running event loop the call runs on a worker thread, so it never
    deadlocks; async code should await :func:`complete_async` instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(complete_async(messages, **kwargs))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, complete_async(messages, **kwargs)).result()
