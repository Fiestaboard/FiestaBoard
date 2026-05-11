"""Wire-format adapters for the LLM providers we support.

The rest of the AI generator code is protocol-agnostic. All differences
between e.g. an OpenAI-compatible ``/chat/completions`` endpoint and
Anthropic's native ``/messages`` API live here as small pure functions:

- ``request_path``  — path to append to the provider's ``base_url``.
- ``build_headers`` — auth + content-type headers.
- ``build_body``    — JSON request body for a chat completion.
- ``parse_content`` — pull the assistant's text out of the response.
- ``parse_usage``   — normalize token usage into a common shape.

Adding another protocol (Google, Cohere, raw Mistral, …) means adding
one more entry to ``PROTOCOLS`` — no branching elsewhere in the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# A thin alias to keep the function signatures readable.
Headers = Dict[str, str]
Body = Dict[str, Any]


@dataclass(frozen=True)
class Protocol:
    """A wire-format adapter for one provider family."""

    name: str
    request_path: str
    # (api_key, extra_headers) -> headers
    build_headers: Callable[[str, Dict[str, str]], Headers]
    # (model, messages, temperature, max_tokens) -> body
    build_body: Callable[[str, List[Dict[str, Any]], float, int], Body]
    # api_response -> assistant text
    parse_content: Callable[[Dict[str, Any]], str]
    # api_response -> {prompt_tokens, completion_tokens, total_tokens}
    parse_usage: Callable[[Dict[str, Any]], Dict[str, Optional[int]]]
    # Provider-side error message extractor for non-2xx responses.
    parse_error: Callable[[Dict[str, Any]], Optional[str]]


# ---------------------------------------------------------------------------
# OpenAI-compatible (OpenAI, OpenRouter, Ollama, LM Studio, vLLM, …)
# ---------------------------------------------------------------------------


def _openai_headers(api_key: str, extra: Dict[str, str]) -> Headers:
    headers: Headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers.update({k: v for k, v in extra.items() if isinstance(v, str)})
    return headers


def _openai_body(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> Body:
    return {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Honored by OpenAI / OpenRouter / many local servers; ignored
        # silently by the rest. Prompt also asks for JSON explicitly.
        "response_format": {"type": "json_object"},
    }


def _openai_content(api_response: Dict[str, Any]) -> str:
    choices = api_response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        # Some OpenAI-compatible servers (and OpenAI's newer responses)
        # return content as a list of typed parts.
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in (None, "text"):
                text = part.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        content = "".join(parts)
    return content if isinstance(content, str) else ""


def _openai_usage(api_response: Dict[str, Any]) -> Dict[str, Optional[int]]:
    usage = api_response.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _openai_error(api_response: Dict[str, Any]) -> Optional[str]:
    err = api_response.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str):
            return msg
    return None


# ---------------------------------------------------------------------------
# Anthropic Messages API (https://api.anthropic.com/v1/messages)
# ---------------------------------------------------------------------------
#
# Differences from OpenAI:
#   - Auth via ``x-api-key`` (not ``Authorization: Bearer``).
#   - Requires the ``anthropic-version`` header.
#   - System prompt is a top-level ``system`` field, not a message role.
#   - ``max_tokens`` is required.
#   - Response ``content`` is always an array of content blocks; we
#     concatenate the ``text`` blocks.
#   - Usage uses ``input_tokens`` / ``output_tokens``.


_ANTHROPIC_VERSION = "2023-06-01"


def _anthropic_headers(api_key: str, extra: Dict[str, str]) -> Headers:
    headers: Headers = {
        "Content-Type": "application/json",
        "anthropic-version": _ANTHROPIC_VERSION,
    }
    if api_key:
        headers["x-api-key"] = api_key
    headers.update({k: v for k, v in extra.items() if isinstance(v, str)})
    return headers


def _split_system(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
    """Pull system messages out into a single concatenated string.

    Anthropic's Messages API takes ``system`` as a top-level field and
    only allows ``user``/``assistant`` roles in ``messages``.
    """
    system_chunks: List[str] = []
    rest: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_chunks.append(content)
            continue
        # Anthropic accepts role: user|assistant; coerce anything else
        # to user so we never send an invalid request.
        if role not in ("user", "assistant"):
            role = "user"
        rest.append({"role": role, "content": content})
    return "\n\n".join(s for s in system_chunks if s), rest


def _anthropic_body(
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> Body:
    system, chat = _split_system(messages)
    body: Body = {
        "model": model,
        "messages": chat,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    return body


def _anthropic_content(api_response: Dict[str, Any]) -> str:
    content = api_response.get("content")
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _anthropic_usage(api_response: Dict[str, Any]) -> Dict[str, Optional[int]]:
    usage = api_response.get("usage") or {}
    prompt = usage.get("input_tokens")
    completion = usage.get("output_tokens")
    total: Optional[int]
    if isinstance(prompt, int) and isinstance(completion, int):
        total = prompt + completion
    else:
        total = None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def _anthropic_error(api_response: Dict[str, Any]) -> Optional[str]:
    err = api_response.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str):
            return msg
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


PROTOCOLS: Dict[str, Protocol] = {
    "openai": Protocol(
        name="openai",
        request_path="/chat/completions",
        build_headers=_openai_headers,
        build_body=_openai_body,
        parse_content=_openai_content,
        parse_usage=_openai_usage,
        parse_error=_openai_error,
    ),
    "anthropic": Protocol(
        name="anthropic",
        request_path="/messages",
        build_headers=_anthropic_headers,
        build_body=_anthropic_body,
        parse_content=_anthropic_content,
        parse_usage=_anthropic_usage,
        parse_error=_anthropic_error,
    ),
}


DEFAULT_PROTOCOL = "openai"


def get_protocol(name: Optional[str]) -> Protocol:
    """Look up a protocol adapter, falling back to OpenAI-compatible."""
    if not name:
        return PROTOCOLS[DEFAULT_PROTOCOL]
    proto = PROTOCOLS.get(name)
    if proto is None:
        # Unknown protocol — treat as OpenAI-compatible for forward-
        # compatibility with old configs and typos.
        return PROTOCOLS[DEFAULT_PROTOCOL]
    return proto


def supported_protocols() -> List[str]:
    """List of supported protocol identifiers (stable order)."""
    return list(PROTOCOLS.keys())
