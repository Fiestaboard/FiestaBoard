"""Contract test: the chat's TypeScript mirror must agree with the server.

``POST /pages/ai/chat`` streams frames the browser switches on, and the
browser labels tool calls by MCP tool name. Two places must agree with the
server:

1. ``web/src/lib/ai-chat-types.ts`` — the ``KNOWN_TOOL_NAMES`` list the
   labels and choreography key on, and the literal unions that mirror the
   Pydantic ``Literal`` fields of the stream models.
2. ``web/src/lib/api-stream.ts`` — the ``switch (ev.event)`` that dispatches
   frames; an event the server emits that the client ignores is a silent
   feature loss.

Why regex and not a TS parser: the Python test image has no TypeScript
toolchain. The patterns matched here are narrow enough to parse reliably,
and the meta-tests prove the parser resolves symbols rather than silently
finding nothing.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

import pytest

from src.ai.page_routes import CHAT_STREAM_EVENTS, ChatResumeDecision, ChatStreamDoneData, ChatStreamToolResultData

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB = REPO_ROOT / "web"
TS_TYPES = WEB / "src/lib/ai-chat-types.ts"
TS_STREAM = WEB / "src/lib/api-stream.ts"
TS_LABELS = WEB / "src/components/ai-tool-labels.ts"

MIN_KNOWN_TOOLS = 30


def _ts_known_tool_names() -> list[str]:
    text = TS_TYPES.read_text(encoding="utf-8")
    m = re.search(r"export const KNOWN_TOOL_NAMES = \[(.*?)\] as const;", text, re.S)
    assert m, "KNOWN_TOOL_NAMES not found in ai-chat-types.ts"
    return re.findall(r'"([a-z_]+)"', m.group(1))


def _ts_union(name: str) -> set[str]:
    text = TS_TYPES.read_text(encoding="utf-8")
    m = re.search(rf"export type {name} =\s*(.*?);", text, re.S)
    assert m, f"type {name} not found in ai-chat-types.ts"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def _literal_values(model: type, field: str) -> set[str]:
    annotation = model.model_fields[field].annotation
    return set(typing.get_args(annotation))


def _client_switch_events() -> set[str]:
    text = TS_STREAM.read_text(encoding="utf-8")
    m = re.search(r"switch \(ev\.event\) \{(.*?)\n\s*\}\n", text, re.S)
    assert m, "no switch (ev.event) in api-stream.ts"
    return set(re.findall(r'case "([a-z_]+)":', m.group(1)))


# ---------------------------------------------------------------------------
# Meta-tests — the parsers resolve something real
# ---------------------------------------------------------------------------


def test_known_tool_names_parser_resolves_a_realistic_floor():
    assert len(_ts_known_tool_names()) >= MIN_KNOWN_TOOLS


def test_union_parser_resolves_the_status_union():
    assert "denied" in _ts_union("ToolResultStatus")


def test_switch_parser_sees_the_text_event():
    assert "text" in _client_switch_events()


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


def test_every_known_tool_name_is_a_real_tool():
    """The client may know a subset of the tools, never a tool that does not exist."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    from src.ai.chat_tools import ASK_USER
    from src.mcp_server import _build_mcp_server

    mcp = _build_mcp_server()
    real = set(mcp._tool_manager._tools) | {ASK_USER}
    phantom = sorted(set(_ts_known_tool_names()) - real)
    assert phantom == [], f"ai-chat-types.ts names tools the server does not have: {phantom}"


def test_known_tool_names_are_unique():
    names = _ts_known_tool_names()
    assert len(names) == len(set(names))


def test_tool_result_status_union_mirrors_the_server():
    assert _ts_union("ToolResultStatus") == _literal_values(ChatStreamToolResultData, "status")


def test_done_reason_union_mirrors_the_server():
    assert _ts_union("DoneReason") == _literal_values(ChatStreamDoneData, "reason")


def test_resume_decisions_mirror_the_server():
    text = TS_TYPES.read_text(encoding="utf-8")
    # A multi-line union: read to the blank line that ends the declaration,
    # not to the first ';' (which sits inside the first member).
    m = re.search(r"export type ResumePayload =(.*?)\n\n", text, re.S)
    assert m
    client = set(re.findall(r'decision: "([a-z]+)"', m.group(1))) | _ts_union("ApprovalDecision")
    assert client == _literal_values(ChatResumeDecision, "decision")


def test_the_client_switches_on_every_event_the_server_emits():
    missing = sorted(set(CHAT_STREAM_EVENTS) - _client_switch_events())
    assert missing == [], f"api-stream.ts ignores events the server emits: {missing}"


def test_the_client_switches_on_no_event_the_server_does_not_emit():
    extra = sorted(_client_switch_events() - set(CHAT_STREAM_EVENTS))
    assert extra == [], f"api-stream.ts handles events the server never emits: {extra}"


def test_every_known_tool_has_a_label_and_unknown_tools_fall_back():
    text = TS_LABELS.read_text(encoding="utf-8")
    m = re.search(r"const LABEL_KEYS: Record<string, string> = \{(.*?)\};", text, re.S)
    assert m, "LABEL_KEYS not found in ai-tool-labels.ts"
    labelled = set(re.findall(r"^\s*([a-z_]+):", m.group(1), re.M))
    missing = sorted(set(_ts_known_tool_names()) - labelled)
    assert missing == [], f"known tools without a label key: {missing}"
    # The fallback: an unknown name renders the server's own title.
    assert "call.title || call.name" in text
