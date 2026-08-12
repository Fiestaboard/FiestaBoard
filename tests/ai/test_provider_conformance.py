"""Every body FiestaBoard sends must be accepted by every provider it claims to support.

``src/ai/protocols.py`` buckets OpenAI, OpenRouter, LM Studio, Ollama and
vLLM under a single ``openai`` protocol, so one wire format has to satisfy
all of them. Nothing checked that. #1560 is the result: the generator
hardcodes ``response_format: {"type": "json_object"}``, which LM Studio
rejects with a 400, so page generation is hard-blocked against a provider
this repo names as supported.

Two halves to this module:

1. **Emulator self-tests** — prove each emulator actually rejects what it is
   supposed to reject. An emulator that accepts everything would make the
   conformance matrix below pass vacuously, which is the original bug one
   layer down.
2. **The conformance matrix** — every outbound body, against every emulator.
"""

from __future__ import annotations

import pytest

from src.ai.protocols import PROTOCOLS, get_protocol
from tests.ai.provider_emulators import (
    ALL_EMULATORS,
    OPENAI_FAMILY,
    AnthropicEmulator,
    LMStudioEmulator,
    OllamaEmulator,
    OpenAIEmulator,
    ProviderRejection,
)

MESSAGES = [
    {"role": "system", "content": "You are a board designer."},
    {"role": "user", "content": "A page that says hello."},
]

OPENAI_HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer sk-test"}
ANTHROPIC_HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": "sk-ant-test",
    "anthropic-version": "2023-06-01",
}


# ---------------------------------------------------------------------------
# Emulator self-tests — each must be able to say no
# ---------------------------------------------------------------------------


def test_lmstudio_rejects_json_object():
    """The #1560 rule, stated directly."""
    with pytest.raises(ProviderRejection) as exc:
        LMStudioEmulator().validate(
            {"model": "m", "messages": MESSAGES, "response_format": {"type": "json_object"}},
            {},
        )
    assert exc.value.status == 400
    assert "json_schema" in exc.value.message


def test_lmstudio_accepts_text_and_json_schema():
    for kind in ("text", "json_schema"):
        LMStudioEmulator().validate({"model": "m", "messages": MESSAGES, "response_format": {"type": kind}}, {})


def test_lmstudio_error_envelope_is_a_flat_string():
    """LM Studio returns ``{"error": "..."}``, not ``{"error": {"message": ...}}``."""
    body = LMStudioEmulator().error_body("boom")
    assert body == {"error": "boom"}


def test_openai_accepts_json_object():
    OpenAIEmulator().validate(
        {"model": "m", "messages": MESSAGES, "response_format": {"type": "json_object"}},
        OPENAI_HEADERS,
    )


def test_openai_rejects_missing_model():
    with pytest.raises(ProviderRejection):
        OpenAIEmulator().validate({"messages": MESSAGES}, OPENAI_HEADERS)


def test_openai_rejects_missing_credentials():
    with pytest.raises(ProviderRejection) as exc:
        OpenAIEmulator().validate({"model": "m", "messages": MESSAGES}, {})
    assert exc.value.status == 401


def test_ollama_rejects_json_schema_it_does_not_implement():
    with pytest.raises(ProviderRejection):
        OllamaEmulator().validate({"model": "m", "messages": MESSAGES, "response_format": {"type": "json_schema"}}, {})


def test_anthropic_requires_version_header():
    with pytest.raises(ProviderRejection):
        AnthropicEmulator().validate(
            {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10},
            {"x-api-key": "k"},
        )


def test_anthropic_rejects_system_role_in_messages():
    with pytest.raises(ProviderRejection) as exc:
        AnthropicEmulator().validate(
            {"model": "m", "messages": MESSAGES, "max_tokens": 10},
            ANTHROPIC_HEADERS,
        )
    assert "role" in exc.value.message


def test_anthropic_rejects_response_format():
    with pytest.raises(ProviderRejection):
        AnthropicEmulator().validate(
            {
                "model": "m",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 10,
                "response_format": {"type": "json_object"},
            },
            ANTHROPIC_HEADERS,
        )


def test_every_emulator_rejects_a_garbage_body():
    """Floor: no emulator is a pass-through."""
    for emulator in ALL_EMULATORS:
        with pytest.raises(ProviderRejection):
            emulator.validate({}, {})


# ---------------------------------------------------------------------------
# Conformance: the generator's outbound body
# ---------------------------------------------------------------------------


def _generator_body() -> dict:
    return PROTOCOLS["openai"].build_body("test-model", MESSAGES, 0.7, 1200)


@pytest.mark.parametrize("emulator", OPENAI_FAMILY, ids=lambda e: e.name)
def test_generator_body_is_accepted_by_every_openai_compatible_provider(emulator):
    """Regression for #1560 — lmstudio is the parametrization that used to fail."""
    headers = PROTOCOLS["openai"].build_headers("sk-test", {})
    emulator.validate(_generator_body(), headers)


def test_generator_does_not_request_json_object_mode():
    """Pins the #1560 fix against a well-meaning revert.

    LM Studio validates ``response_format.type`` and 400s on
    ``json_object``. The prompt asks for JSON and
    ``_extract_json_object()`` recovers it from prose, so ``text`` is the
    portable choice.
    """
    assert _generator_body()["response_format"] == {"type": "text"}


@pytest.mark.parametrize(
    "raw",
    [
        '{"name": "A", "template": ["HI"]}',
        '```json\n{"name": "A", "template": ["HI"]}\n```',
        'Sure! Here is your page:\n\n{"name": "A", "template": ["HI"]}\n\nHope that helps.',
    ],
    ids=["bare", "fenced", "prose-wrapped"],
)
def test_json_is_recovered_without_json_object_mode(raw):
    """The safety net that makes dropping ``json_object`` viable.

    Without a server-enforced JSON mode a model may wrap its object in
    prose or a markdown fence. If this ever stops holding, the #1560 fix
    needs revisiting rather than the parser.
    """
    from src.ai.generator import _extract_json_object

    assert _extract_json_object(raw)["name"] == "A"


def test_anthropic_generator_body_is_accepted():
    proto = PROTOCOLS["anthropic"]
    body = proto.build_body("claude-test", MESSAGES, 0.7, 1200)
    headers = proto.build_headers("sk-ant-test", {})
    AnthropicEmulator().validate(body, headers)


def test_anthropic_body_moves_system_out_of_messages():
    """Guards the split that keeps the Anthropic body legal."""
    body = PROTOCOLS["anthropic"].build_body("claude-test", MESSAGES, 0.7, 1200)
    assert body["system"] == "You are a board designer."
    assert [m["role"] for m in body["messages"]] == ["user"]


# ---------------------------------------------------------------------------
# Conformance: the chat (streaming) outbound body
# ---------------------------------------------------------------------------


def _chat_body(protocol_name: str) -> dict:
    """Reproduce what ``src/ai/chat.py`` puts on the wire.

    Mirrors chat.py's build → ``stream = True`` → ``pop("response_format")``
    sequence. Kept in step with the source by
    ``test_chat_still_strips_response_format`` below, which fails if chat.py
    stops popping the field.
    """
    proto = get_protocol(protocol_name)
    payload = proto.build_body("test-model", MESSAGES, 0.7, 2000)
    payload["stream"] = True
    payload.pop("response_format", None)
    return payload


@pytest.mark.parametrize("emulator", OPENAI_FAMILY, ids=lambda e: e.name)
def test_chat_body_is_accepted_by_every_openai_compatible_provider(emulator):
    emulator.validate(_chat_body("openai"), PROTOCOLS["openai"].build_headers("sk-test", {}))


def test_chat_body_is_accepted_by_anthropic():
    AnthropicEmulator().validate(_chat_body("anthropic"), PROTOCOLS["anthropic"].build_headers("sk-ant-test", {}))


def test_chat_still_strips_response_format():
    """chat.py pops the field; if that stops, this local reproduction is stale.

    Pins the asymmetry #1560 describes: chat works against LM Studio because
    it drops ``response_format``, while the generator does not.
    """
    source = (__import__("pathlib").Path(__file__).resolve().parents[2] / "src" / "ai" / "chat.py").read_text(
        encoding="utf-8"
    )
    assert 'payload.pop("response_format", None)' in source, (
        "src/ai/chat.py no longer strips response_format — _chat_body() above "
        "no longer reproduces what chat puts on the wire."
    )


# ---------------------------------------------------------------------------
# Error-envelope handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("emulator", ALL_EMULATORS, ids=lambda e: e.name)
def test_provider_error_messages_reach_the_user(emulator):
    """``parse_error`` should extract the provider's message, whatever its shape.

    When it returns None, ``generator.py:391`` falls back to dumping the raw
    response body into the user-facing error. LM Studio's flat-string
    envelope is the case that trips this.
    """
    proto = get_protocol(emulator.protocol)
    body = emulator.error_body("Invalid API key.")
    assert proto.parse_error(body) == "Invalid API key.", (
        f"{emulator.name} returns {body!r}; parse_error could not extract the "
        "message, so the user sees a raw JSON dump instead."
    )
