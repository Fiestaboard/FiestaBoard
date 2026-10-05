"""The ``openai_responses`` protocol (Sign in with ChatGPT): body, SSE stream, one-shot collect."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.ai.chat import _FenceParser, stream_model
from src.ai.generator import AIGenerationError, _post_chat_completion
from src.ai.generator import test_provider as smoke_test_provider
from src.ai.protocols import get_protocol
from src.ai.tool_catalog import ParsedToolCall

PROVIDER = {
    "id": "gpt",
    "name": "ChatGPT",
    "protocol": "openai_responses",
    "base_url": "https://example.test/v1",
    "api_key": "test_token",
    "models": ["test-model"],
}
MESSAGES = [
    {"role": "system", "content": "sys one"},
    {"role": "system", "content": "sys two"},
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
]


def _sse(*events: dict[str, Any]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _delta(text: str) -> dict[str, Any]:
    return {"type": "response.output_text.delta", "delta": text}


COMPLETED = {
    "type": "response.completed",
    "response": {"usage": {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14}},
}


def _client(body: bytes, seen: list | None = None, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=body, headers={"content-type": "text/event-stream"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _validate(payload: object) -> ParsedToolCall:
    assert isinstance(payload, dict)
    return ParsedToolCall(name=payload["op"], args=payload.get("args", {}))


async def _stream(body: bytes, usage: dict, seen: list | None = None) -> list[dict[str, Any]]:
    async with _client(body, seen) as client:
        return [
            e
            async for e in stream_model(
                protocol=get_protocol("openai_responses"),
                provider=PROVIDER,
                model="test-model",
                messages=MESSAGES,
                parser=_FenceParser(_validate),
                usage=usage,
                client=client,
            )
        ]


def _usage() -> dict[str, int | None]:
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


def test_body_moves_system_to_instructions_and_sends_no_sampling_fields():
    body = get_protocol("openai_responses").build_body("test-model", MESSAGES, 0.7, 2000)
    assert body == {
        "model": "test-model",
        "instructions": "sys one\n\nsys two",
        "input": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        "store": False,
        "stream": True,
    }


def test_responses_protocol_posts_to_responses_with_bearer():
    proto = get_protocol("openai_responses")
    assert proto.request_path == "/responses"
    assert proto.build_headers("test_token", {})["Authorization"] == "Bearer test_token"


def test_existing_protocols_are_unchanged():
    assert get_protocol("openai").request_path == "/chat/completions"
    assert "temperature" in get_protocol("openai").build_body("m", [], 0.5, 10)
    assert get_protocol("anthropic").request_path == "/messages"


@pytest.mark.asyncio
async def test_stream_yields_text_deltas_and_completed_usage():
    usage = _usage()
    seen: list = []
    events = await _stream(_sse(_delta("Hel"), _delta("lo"), COMPLETED), usage, seen)
    assert "".join(e["data"]["delta"] for e in events if e["event"] == "text") == "Hello"
    assert usage == {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}
    assert str(seen[0].url) == "https://example.test/v1/responses"
    assert "temperature" not in json.loads(seen[0].content)


@pytest.mark.asyncio
async def test_failed_response_is_an_error_event():
    failed = {
        "type": "response.failed",
        "response": {"error": {"message": "subscription_sharing_usage_limit_exceeded"}},
    }
    events = await _stream(_sse(_delta("x"), failed), _usage())
    assert events[-1] == {"event": "error", "data": {"message": "subscription_sharing_usage_limit_exceeded"}}


@pytest.mark.asyncio
async def test_error_event_is_an_error():
    events = await _stream(_sse({"type": "error", "message": "test_boom"}), _usage())
    assert events[-1] == {"event": "error", "data": {"message": "test_boom"}}


@pytest.mark.asyncio
async def test_stream_that_ends_without_completed_is_an_error():
    events = await _stream(_sse(_delta("partial")), _usage())
    assert events[-1]["event"] == "error"


@pytest.mark.asyncio
async def test_fenced_tool_call_is_parsed_from_responses_deltas():
    call = json.dumps({"op": "create_page", "args": {"name": "A"}})
    text = f"Sure\n```fiestaboard\n{call}\n```\nDone"
    events = await _stream(_sse(_delta(text[:12]), _delta(text[12:30]), _delta(text[30:]), COMPLETED), _usage())
    calls = [e for e in events if e["event"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["data"]["name"] == "create_page"


@pytest.mark.asyncio
async def test_one_shot_generator_collects_the_stream():
    proto = get_protocol("openai_responses")
    async with _client(_sse(_delta('{"a":'), _delta(" 1}"), COMPLETED)) as client:
        response = await _post_chat_completion(PROVIDER, proto.build_body("m", MESSAGES, 0, 5), client=client)
    assert proto.parse_content(response) == '{"a": 1}'
    assert proto.parse_usage(response) == {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}


@pytest.mark.asyncio
async def test_one_shot_generator_raises_on_failed_stream():
    failed = {"type": "response.failed", "response": {"error": {"message": "test_limit"}}}
    async with _client(_sse(failed)) as client:
        with pytest.raises(AIGenerationError, match="test_limit"):
            await _post_chat_completion(PROVIDER, {"model": "m"}, client=client)


@pytest.mark.asyncio
async def test_provider_smoke_test_works_over_responses():
    async with _client(_sse(_delta("ok"), COMPLETED)) as client:
        result = await smoke_test_provider(PROVIDER, client=client)
    assert result["ok"] is True
