"""Emulators for the request validation real LLM providers actually perform.

Why this exists
---------------

``integration-tests/mock-llm/server.py`` accepts any well-formed body. That
is what let #1560 ship: ``_openai_body()`` hardcodes
``response_format: {"type": "json_object"}``, LM Studio validates that field
and returns HTTP 400, and every AI page generation against an LM Studio
provider fails. No test noticed, because nothing in the suite could say no.

A mock that agrees with whatever you send it cannot tell you the wire format
is wrong. These emulators are the opposite: each one encodes what a specific
provider *rejects*, so an outbound body that would 400 in production 400s in
the test suite instead.

Scope and honesty
-----------------

These are emulators, not the real services. They encode the validation rules
we have evidence for — from provider documentation and from bug reports
against this repo — and nothing more. An emulator accepting a body is
evidence that the body does not trip a *known* rule, not proof the provider
will accept it. Each rule below cites its source.

Every emulator is paired with a test asserting it rejects what it should
reject. An emulator that accepts everything is the bug being fixed,
re-introduced one layer down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderRejection(Exception):
    """A provider refused the request.

    Carries the status and the provider's own error envelope so tests can
    assert on how FiestaBoard surfaces it, not just that it failed.
    """

    def __init__(self, status: int, message: str, body: dict[str, Any]) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.body = body


@dataclass(frozen=True)
class ProviderEmulator:
    """Base emulator. Subclasses override :meth:`validate`."""

    name: str = "base"
    protocol: str = "openai"

    def error_body(self, message: str) -> dict[str, Any]:
        """The provider's error envelope shape."""
        return {"error": {"message": message, "type": "invalid_request_error"}}

    def reject(self, status: int, message: str) -> None:
        raise ProviderRejection(status, message, self.error_body(message))

    def validate(self, body: dict[str, Any], headers: dict[str, str]) -> None:
        """Raise :class:`ProviderRejection` if this provider would refuse."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# OpenAI-compatible family
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _OpenAICompatible(ProviderEmulator):
    """Validation shared by every server speaking /chat/completions.

    Source: OpenAI Chat Completions API reference — ``model`` and ``messages``
    are required; ``messages`` entries require ``role`` and ``content``.
    """

    name: str = "openai-compatible"
    protocol: str = "openai"
    #: response_format.type values this server accepts. Empty set = the field
    #: is ignored entirely rather than validated.
    allowed_response_formats: frozenset[str] = field(default_factory=frozenset)
    requires_auth: bool = True

    def validate(self, body: dict[str, Any], headers: dict[str, str]) -> None:
        lower = {k.lower(): v for k, v in headers.items()}

        if self.requires_auth and not lower.get("authorization", "").startswith("Bearer "):
            self.reject(401, "Missing bearer credentials.")

        if not body.get("model"):
            self.reject(400, "'model' is a required property")
        if not isinstance(body.get("messages"), list):
            self.reject(400, "'messages' is a required property")
        for i, msg in enumerate(body.get("messages") or []):
            if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                self.reject(400, f"messages[{i}] must have 'role' and 'content'")

        rf = body.get("response_format")
        if rf is not None and self.allowed_response_formats:
            if not isinstance(rf, dict) or "type" not in rf:
                self.reject(400, "'response_format' must be an object with a 'type'")
            if rf["type"] not in self.allowed_response_formats:
                allowed = " or ".join(f"'{v}'" for v in sorted(self.allowed_response_formats))
                self.reject(400, f"'response_format.type' must be {allowed}")


@dataclass(frozen=True)
class OpenAIEmulator(_OpenAICompatible):
    """OpenAI proper.

    Source: OpenAI docs — ``response_format`` accepts ``text``,
    ``json_object`` and ``json_schema``.
    """

    name: str = "openai"
    allowed_response_formats: frozenset[str] = frozenset({"text", "json_object", "json_schema"})


@dataclass(frozen=True)
class OpenRouterEmulator(_OpenAICompatible):
    """OpenRouter. Proxies to many models; mirrors OpenAI's surface."""

    name: str = "openrouter"
    allowed_response_formats: frozenset[str] = frozenset({"text", "json_object", "json_schema"})


@dataclass(frozen=True)
class LMStudioEmulator(_OpenAICompatible):
    """LM Studio's local OpenAI-compatible server.

    Source: Fiestaboard/FiestaBoard#1560. LM Studio validates
    ``response_format.type`` and rejects anything other than ``json_schema``
    or ``text``::

        {"error":"'response_format.type' must be 'json_schema' or 'text'"}

    Note the envelope: LM Studio returns ``error`` as a flat **string**, not
    the ``{"error": {"message": ...}}`` object OpenAI uses. That matters —
    ``src.ai.protocols._openai_error`` only reads the object form, so it
    returns None here and the generator falls back to dumping the raw
    response body at ``generator.py:391``.

    Local server: no API key required.
    """

    name: str = "lmstudio"
    allowed_response_formats: frozenset[str] = frozenset({"json_schema", "text"})
    requires_auth: bool = False

    def error_body(self, message: str) -> dict[str, Any]:
        return {"error": message}


@dataclass(frozen=True)
class OllamaEmulator(_OpenAICompatible):
    """Ollama's ``/v1`` OpenAI-compatibility layer.

    Source: Ollama OpenAI-compatibility docs — supports ``response_format``
    with ``json_object``, and ignores parameters it does not implement rather
    than rejecting them. Local server: no API key required.
    """

    name: str = "ollama"
    allowed_response_formats: frozenset[str] = frozenset({"text", "json_object"})
    requires_auth: bool = False


@dataclass(frozen=True)
class VLLMEmulator(_OpenAICompatible):
    """vLLM's OpenAI-compatible server.

    Source: vLLM docs — implements ``response_format`` with ``json_object``
    and ``json_schema`` via guided decoding.
    """

    name: str = "vllm"
    allowed_response_formats: frozenset[str] = frozenset({"text", "json_object", "json_schema"})
    requires_auth: bool = False


# ---------------------------------------------------------------------------
# Anthropic Messages API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnthropicEmulator(ProviderEmulator):
    """Anthropic's native Messages API.

    Source: Anthropic Messages API reference —

    - auth via ``x-api-key``, not ``Authorization: Bearer``
    - ``anthropic-version`` header is required
    - ``max_tokens`` is required
    - ``messages`` roles are limited to ``user``/``assistant``; the system
      prompt is a top-level ``system`` field
    - unknown top-level parameters are rejected as ``invalid_request_error``,
      which is why sending OpenAI's ``response_format`` here is a bug
    """

    name: str = "anthropic"
    protocol: str = "anthropic"

    def validate(self, body: dict[str, Any], headers: dict[str, str]) -> None:
        lower = {k.lower(): v for k, v in headers.items()}

        if not lower.get("x-api-key"):
            self.reject(401, "missing x-api-key header")
        if not lower.get("anthropic-version"):
            self.reject(400, "missing anthropic-version header")

        if not body.get("model"):
            self.reject(400, "model: field required")
        if not isinstance(body.get("messages"), list):
            self.reject(400, "messages: field required")
        if not isinstance(body.get("max_tokens"), int):
            self.reject(400, "max_tokens: field required")

        for i, msg in enumerate(body.get("messages") or []):
            role = msg.get("role") if isinstance(msg, dict) else None
            if role not in ("user", "assistant"):
                self.reject(400, f"messages.{i}.role: must be 'user' or 'assistant'")

        if "response_format" in body:
            self.reject(400, "response_format: extra fields not permitted")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


OPENAI_FAMILY: list[ProviderEmulator] = [
    OpenAIEmulator(),
    OpenRouterEmulator(),
    LMStudioEmulator(),
    OllamaEmulator(),
    VLLMEmulator(),
]

ALL_EMULATORS: list[ProviderEmulator] = [*OPENAI_FAMILY, AnthropicEmulator()]

BY_NAME: dict[str, ProviderEmulator] = {e.name: e for e in ALL_EMULATORS}
