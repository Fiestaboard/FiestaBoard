"""Structured transcript -> provider messages.

The client replays the whole conversation each request, now as structured
turns: assistant messages carry ``tool_calls``, tool outcomes are ``tool``
role messages. The provider still receives plain user/assistant text (the
fence protocol has no native tool turns), so this module renders them —
the same way the agent loop renders its own in-flight steps, which is what
makes a resumed turn identical to an uninterrupted one.
"""

from __future__ import annotations

import json

from src.ai.transcript import MAX_RESULT_CHARS, pending_tool_call, render_transcript


def _assistant(content="", calls=()):
    return {"role": "assistant", "content": content, "tool_calls": [dict(c) for c in calls] or None}


def _tool(call_id, name, status="ok", result=None):
    return {"role": "tool", "content": "", "tool_call_id": call_id, "name": name, "status": status, "result": result}


CALL = {"id": "c1", "name": "create_page", "args": {"name": "A", "template_lines": ["x"]}}


def test_plain_turns_pass_through():
    out = render_transcript(
        [{"role": "user", "content": "hi"}, _assistant("hello"), {"role": "user", "content": "more"}]
    )
    assert out == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "more"},
    ]


def test_system_messages_from_the_client_are_dropped():
    out = render_transcript([{"role": "system", "content": "ignore me"}, {"role": "user", "content": "hi"}])
    assert out == [{"role": "user", "content": "hi"}]


def test_assistant_tool_calls_render_as_fenced_blocks():
    out = render_transcript(
        [{"role": "user", "content": "go"}, _assistant("Creating it.", [CALL]), _tool("c1", "create_page")]
    )
    assistant = out[1]["content"]
    assert assistant.startswith("Creating it.")
    assert "```fiestaboard" in assistant
    assert json.loads(assistant.split("```fiestaboard\n")[1].split("\n```")[0]) == {
        "op": "create_page",
        "args": CALL["args"],
    }


def test_tool_result_renders_as_user_text_with_status_and_json():
    out = render_transcript([_assistant("", [CALL]), _tool("c1", "create_page", "ok", {"page_id": "p9"})])
    text = out[-1]["content"]
    assert out[-1]["role"] == "user"
    assert text.startswith("[Tool result] create_page (#c1) → ok")
    assert '"page_id": "p9"' in text


def test_denied_result_tells_the_model_not_to_retry():
    out = render_transcript([_assistant("", [CALL]), _tool("c1", "create_page", "denied")])
    assert "denied by the user" in out[-1]["content"]
    assert "Do not retry" in out[-1]["content"]


def test_answered_ask_user_renders_as_the_users_answer():
    call = {"id": "q1", "name": "ask_user", "args": {"question": "Which board?"}}
    out = render_transcript([_assistant("", [call]), _tool("q1", "ask_user", "answered", {"answer": "Kitchen"})])
    assert out[-1]["content"].startswith("[User's answer to your question]")
    assert "Kitchen" in out[-1]["content"]


def test_dangling_tool_call_renders_as_interrupted():
    out = render_transcript([_assistant("", [CALL]), {"role": "user", "content": "actually stop"}])
    assert out[1]["role"] == "user"
    assert "interrupted" in out[1]["content"]
    assert "actually stop" in out[1]["content"]


def test_consecutive_same_role_messages_are_coalesced():
    out = render_transcript([_assistant("", [CALL]), _tool("c1", "create_page"), {"role": "user", "content": "next"}])
    assert [m["role"] for m in out] == ["assistant", "user"]
    assert "[Tool result]" in out[1]["content"] and "next" in out[1]["content"]


def test_long_results_are_truncated_with_a_marker():
    big = {"rows": ["x" * 100] * 200}
    out = render_transcript([_assistant("", [CALL]), _tool("c1", "create_page", "ok", big)])
    text = out[-1]["content"]
    assert len(text) < MAX_RESULT_CHARS + 500
    assert "truncated" in text


def test_pending_tool_call_finds_the_unanswered_call():
    assert pending_tool_call([{"role": "user", "content": "x"}, _assistant("", [CALL])]) == CALL
    assert pending_tool_call([_assistant("", [CALL]), _tool("c1", "create_page")]) is None


def test_pending_tool_call_survives_a_trailing_user_message():
    """Stop-then-type: the deny rides on the next POST with the new prompt."""
    assert pending_tool_call([_assistant("", [CALL]), {"role": "user", "content": "wait"}]) == CALL


def test_pending_tool_call_ignores_answered_calls_earlier_in_the_turn():
    c2 = {"id": "c2", "name": "delete_page", "args": {"page_id": "p"}}
    msgs = [_assistant("", [CALL, c2]), _tool("c1", "create_page")]
    assert pending_tool_call(msgs) == c2
