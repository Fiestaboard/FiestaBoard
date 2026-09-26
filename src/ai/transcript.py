"""Structured chat transcript -> the plain messages a provider accepts.

The client replays the whole conversation on every request (there is no
server-side session), now as structured turns: an assistant message may
carry ``tool_calls`` and a tool's outcome is a ``tool`` role message. The
fence protocol has no native tool turns, so the provider receives plain
user/assistant text and this module does the rendering — the assistant's
calls re-appear as the fenced blocks it emitted, tool outcomes as
``[Tool result]`` user text.

The agent loop renders its own in-flight steps through the same function,
which is what makes a turn resumed by the client (approve / deny / answer)
byte-identical to one the loop ran uninterrupted.
"""

from __future__ import annotations

import json
from typing import Any

#: Longest JSON result rendered into a message. Bigger payloads (a plugin
#: registry listing, every page with its template) are cut with a marker;
#: the addendum tells the model how to ask for less.
MAX_RESULT_CHARS = 8_000

_DENIED = "→ denied by the user. Do not retry this action; ask how to proceed or continue with the remaining steps."
_INTERRUPTED = (
    "→ interrupted: the user stopped the assistant while this tool was running. "
    "It may or may not have completed — check with a read-only tool before repeating a non-idempotent call."
)


def render_transcript(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Render structured messages as ``{"role", "content"}`` pairs.

    ``system`` messages from the client are dropped — the server owns the
    system prompt. Consecutive same-role messages are merged, because the
    Anthropic wire format requires alternation and OpenAI-compatible
    servers are happier with it too.
    """
    rendered: list[dict[str, str]] = []
    unanswered: dict[str, dict[str, Any]] = {}

    def emit(role: str, content: str) -> None:
        if rendered and rendered[-1]["role"] == role:
            rendered[-1]["content"] = rendered[-1]["content"] + "\n\n" + content
        else:
            rendered.append({"role": role, "content": content})

    def flush_interrupted() -> None:
        for call in list(unanswered.values()):
            emit("user", f"[Tool result] {call['name']} (#{call['id']}) {_INTERRUPTED}")
        unanswered.clear()

    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "assistant":
            flush_interrupted()
            if not (message.get("content") or "").strip() and not message.get("tool_calls"):
                # A turn that produced nothing (a malformed fence, a Stop
                # while thinking) is kept in the transcript but not shown to
                # the model: Anthropic rejects an empty non-final assistant
                # message, and the neighbours coalesce anyway.
                continue
            parts = [message.get("content") or ""]
            for call in message.get("tool_calls") or []:
                unanswered[call["id"]] = call
                body = json.dumps({"op": call["name"], "args": call.get("args") or {}}, ensure_ascii=False)
                parts.append(f"```fiestaboard\n{body}\n```")
            emit("assistant", "\n\n".join(p for p in parts if p))
            continue
        if role == "tool":
            call_id = message.get("tool_call_id") or ""
            unanswered.pop(call_id, None)
            emit("user", _render_tool_message(message))
            continue
        # user (or anything unknown, treated as user text)
        flush_interrupted()
        emit("user", message.get("content") or "")

    # Calls still unanswered at the end were interrupted (the client
    # stopped the stream); a call awaiting approval is answered by the
    # agent before rendering, so it never reaches here.
    flush_interrupted()
    return rendered


def _render_tool_message(message: dict[str, Any]) -> str:
    name = message.get("name") or "tool"
    call_id = message.get("tool_call_id") or "?"
    status = message.get("status") or "ok"
    result = message.get("result")
    head = f"[Tool result] {name} (#{call_id})"
    if status == "denied":
        return f"{head} {_DENIED}"
    if status == "interrupted":
        return f"{head} {_INTERRUPTED}"
    if status == "answered":
        answer = result.get("answer") if isinstance(result, dict) and "answer" in result else result
        return f"[User's answer to your question] {_as_text(answer)}"
    body = _as_json(result)
    return f"{head} → {status}\n{body}" if body else f"{head} → {status}"


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _as_json(value: Any) -> str:
    if value is None:
        return ""
    text = json.dumps(value, indent=2, ensure_ascii=False)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "\n…truncated; ask for fewer fields or a smaller page."
    return text


def pending_tool_call(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most recent assistant tool call that has no ``tool`` message yet.

    A trailing ``user`` message does not clear it (Stop-then-type: the
    client's deferred deny rides on the next POST with the new prompt).
    """
    answered: set[str] = set()
    for message in reversed(messages):
        role = message.get("role")
        if role == "tool":
            answered.add(message.get("tool_call_id") or "")
            continue
        if role == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                if call["id"] not in answered:
                    return dict(call)
            return None
    return None


__all__ = ["MAX_RESULT_CHARS", "pending_tool_call", "render_transcript"]
