"""The server-side agent loop.

One ``POST /pages/ai/chat`` now spans several model calls and tool
executions. These tests drive :func:`src.ai.agent.run_chat_turn` with a
scripted provider (``httpx.MockTransport`` answering OpenAI-style SSE, one
body per model call) and a fake tool backend, and pin the event stream the
browser depends on: what is emitted, in what order, and what the model is
shown on the next call.

Nothing here touches the ``mcp`` package — the backend is the
:class:`ToolBackend` protocol, which is the point of that seam.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from src.ai.agent import TurnLimits, run_chat_turn
from src.ai.mcp_bridge import ToolDescriptor, ToolOutcome

# ---------------------------------------------------------------------------
# Fixtures: a scripted provider and a fake tool backend
# ---------------------------------------------------------------------------

PROVIDERS = {
    "enabled": True,
    "default_provider_id": "p1",
    "providers": [
        {
            "id": "p1",
            "name": "Mock",
            "protocol": "openai",
            "base_url": "http://mock",
            "api_key": "k",
            "default_model": "m",
        }
    ],
}


def _sse(text: str, *, usage: dict[str, int] | None = None) -> bytes:
    """One OpenAI-style streamed completion carrying ``text`` in two chunks."""
    lines = []
    for chunk in (text[: len(text) // 2], text[len(text) // 2 :]):
        lines.append("data: " + json.dumps({"choices": [{"delta": {"content": chunk}}]}))
    if usage:
        lines.append("data: " + json.dumps({"choices": [], "usage": usage}))
    lines.append("data: [DONE]")
    return ("\n".join(lines) + "\n").encode()


def _block(name: str, args: dict[str, Any]) -> str:
    return "```fiestaboard\n" + json.dumps({"op": name, "args": args}) + "\n```"


class ScriptedProvider:
    """Answers each model call with the next scripted body."""

    def __init__(self, *bodies: bytes | int) -> None:
        self.bodies = list(bodies)
        self.requests: list[dict[str, Any]] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(json.loads(request.content))
            if not self.bodies:
                return httpx.Response(500, json={"error": {"message": "script exhausted"}})
            body = self.bodies.pop(0)
            if isinstance(body, int):
                return httpx.Response(body, json={"error": {"message": "scripted failure"}})
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

        return httpx.MockTransport(handler)

    def messages_of(self, call_index: int) -> list[dict[str, str]]:
        return self.requests[call_index]["messages"]


def _d(name: str, *, read_only=False, destructive=False, source="mcp", required=()):
    return ToolDescriptor(
        name=name,
        title=name.replace("_", " ").capitalize(),
        description=f"{name}.",
        input_schema={
            "type": "object",
            "properties": {k: {"type": "string"} for k in required},
            "required": list(required),
        },
        read_only=read_only,
        destructive=destructive,
        idempotent=read_only,
        open_world=False,
        source=source,
    )


class FakeBackend:
    def __init__(self, outcomes: dict[str, Any] | None = None) -> None:
        self.descriptors = [
            _d("list_pages", read_only=True),
            _d("create_page", required=("name",)),
            _d("delete_page", destructive=True, required=("page_id",)),
            # System tier: destructive AND always gated, whatever the mode.
            _d("restart_system", destructive=True),
            _d("ask_user", read_only=True, source="chat", required=("question",)),
        ]
        self.outcomes = outcomes or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self):
        return self.descriptors

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        outcome = self.outcomes.get(
            name, ToolOutcome(status="ok", result={"status": "success", "message": f"{name} done"})
        )
        if callable(outcome):
            return await outcome(args)
        return outcome


async def _collect(gen) -> list[dict[str, Any]]:
    return [ev async for ev in gen]


def _run_turn(provider: ScriptedProvider, backend: FakeBackend, messages, **overrides) -> list[dict[str, Any]]:
    async def go():
        async with httpx.AsyncClient(transport=provider.transport()) as client:
            kwargs: dict[str, Any] = {
                "messages": messages,
                "resume": None,
                "device_type": "flagship",
                "surface": "global",
                "providers_block": PROVIDERS,
                "backend": backend,
                "client": client,
            }
            kwargs.update(overrides)
            return await _collect(run_chat_turn(**kwargs))

    return asyncio.run(go())


def _names(events):
    return [e["event"] for e in events]


def _only(events, name):
    return [e["data"] for e in events if e["event"] == name]


USER = [{"role": "user", "content": "hello"}]


# ---------------------------------------------------------------------------
# Plain turns
# ---------------------------------------------------------------------------


def test_prose_only_turn_streams_text_then_done_complete():
    provider = ScriptedProvider(_sse("Hi there."))
    events = _run_turn(provider, FakeBackend(), USER)
    assert _names(events)[0] == "status"
    assert "".join(d["delta"] for d in _only(events, "text")) == "Hi there."
    done = _only(events, "done")[0]
    assert done["reason"] == "complete" and done["pending_tool_call_id"] is None and done["steps"] == 1
    assert len(provider.requests) == 1


def test_no_provider_configured_is_an_error_event():
    events = _run_turn(ScriptedProvider(), FakeBackend(), USER, providers_block={"enabled": False})
    assert _names(events) == ["error"]


def test_the_system_prompt_teaches_the_backends_tools_not_the_old_grammar():
    provider = ScriptedProvider(_sse("ok"))
    _run_turn(provider, FakeBackend(), USER)
    system = provider.messages_of(0)[0]
    assert system["role"] == "system"
    assert "### create_page" in system["content"]
    assert "### delete_page" in system["content"]
    assert "replace_page" in system["content"]  # named once, as retired
    assert '"op": "replace_page"' not in system["content"]


# ---------------------------------------------------------------------------
# Read-only and write tools run in the loop
# ---------------------------------------------------------------------------


def test_read_only_tool_runs_in_loop_and_model_is_called_again():
    provider = ScriptedProvider(_sse("Let me look. " + _block("list_pages", {})), _sse("You have no pages."))
    backend = FakeBackend({"list_pages": ToolOutcome(status="ok", result=[])})
    events = _run_turn(provider, backend, USER)

    assert backend.calls == [("list_pages", {})]
    assert len(provider.requests) == 2
    names = _names(events)
    assert names.index("tool_call") < names.index("tool_result") < names.index("done")
    call = _only(events, "tool_call")[0]
    assert call["name"] == "list_pages" and call["read_only"] is True and call["requires_approval"] is False
    result = _only(events, "tool_result")[0]
    assert result["id"] == call["id"] and result["status"] == "ok" and result["result"] == []
    assert _only(events, "done")[0]["reason"] == "complete"
    # The model saw the outcome as a [Tool result] user turn.
    second = provider.messages_of(1)
    assert second[-1]["role"] == "user" and second[-1]["content"].startswith("[Tool result] list_pages")
    assert "```fiestaboard" in second[-2]["content"]


def test_write_tool_runs_immediately_emitting_call_before_result():
    provider = ScriptedProvider(_sse(_block("create_page", {"name": "A"})), _sse("Created."))
    backend = FakeBackend(
        {
            "create_page": ToolOutcome(
                status="ok", result={"status": "success", "message": "Page created.", "page_id": "p9"}
            )
        }
    )
    events = _run_turn(provider, backend, USER)

    assert backend.calls == [("create_page", {"name": "A"})]
    call, result = _only(events, "tool_call")[0], _only(events, "tool_result")[0]
    assert call["requires_approval"] is False and call["read_only"] is False
    assert result["status"] == "ok" and result["result"]["page_id"] == "p9" and result["summary"] == "Page created."
    statuses = _only(events, "status")
    assert any(s["phase"] == "tool_running" and s["tool_call_id"] == call["id"] for s in statuses)


def test_multiple_read_only_calls_in_one_response_all_run_in_order():
    provider = ScriptedProvider(_sse(_block("list_pages", {}) + "\n" + _block("list_pages", {"x": "y"})), _sse("done"))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER)
    assert backend.calls == [("list_pages", {}), ("list_pages", {"x": "y"})]
    assert len(_only(events, "tool_result")) == 2


def test_tool_failure_is_a_result_not_a_fatal_error():
    provider = ScriptedProvider(_sse(_block("create_page", {"name": "A"})), _sse("Sorry, that failed."))
    backend = FakeBackend({"create_page": ToolOutcome(status="error", error="Name already taken.")})
    events = _run_turn(provider, backend, USER)
    result = _only(events, "tool_result")[0]
    assert result["status"] == "error" and result["error"] == "Name already taken."
    assert "error" not in _names(events)
    assert "Name already taken." in provider.messages_of(1)[-1]["content"]


# ---------------------------------------------------------------------------
# Destructive tools pause for approval
# ---------------------------------------------------------------------------


def test_destructive_tool_pauses_with_awaiting_approval_and_runs_nothing():
    provider = ScriptedProvider(_sse("Deleting. " + _block("delete_page", {"page_id": "p1"})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER)

    assert backend.calls == []
    assert len(provider.requests) == 1
    call = _only(events, "tool_call")[0]
    assert call["requires_approval"] is True and call["destructive"] is True
    done = _only(events, "done")[0]
    assert done["reason"] == "awaiting_approval" and done["pending_tool_call_id"] == call["id"]
    assert "tool_result" not in _names(events)


def test_further_tool_blocks_after_a_pause_are_dropped_with_warning():
    provider = ScriptedProvider(_sse(_block("delete_page", {"page_id": "p1"}) + _block("create_page", {"name": "B"})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER)
    assert len(_only(events, "tool_call")) == 1
    assert backend.calls == []
    assert any("ignored" in w["message"].lower() for w in _only(events, "warning"))


# ---------------------------------------------------------------------------
# Approval modes (#2021): the install-level setting and the per-conversation
# request flag decide whether a destructive call pauses; the system tier
# pauses regardless of either.
# ---------------------------------------------------------------------------


def test_auto_mode_runs_a_destructive_call_without_pausing_and_flags_it():
    provider = ScriptedProvider(_sse("Deleting. " + _block("delete_page", {"page_id": "p1"})), _sse("Gone."))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER, approval_mode="auto")

    assert backend.calls == [("delete_page", {"page_id": "p1"})]
    call = _only(events, "tool_call")[0]
    assert call["requires_approval"] is True, "the annotation is unchanged; only the pause is skipped"
    assert call["auto_approved"] is True
    assert call["system_gated"] is False
    names = _names(events)
    assert names.index("tool_call") < names.index("tool_result")
    assert _only(events, "done")[0]["reason"] == "complete"


def test_ask_mode_still_pauses_a_destructive_call():
    provider = ScriptedProvider(_sse("Deleting. " + _block("delete_page", {"page_id": "p1"})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER, approval_mode="ask")

    assert backend.calls == []
    call = _only(events, "tool_call")[0]
    assert call["auto_approved"] is False
    assert _only(events, "done")[0]["reason"] == "awaiting_approval"


def test_system_tier_pauses_even_in_auto_mode():
    provider = ScriptedProvider(_sse("Restarting. " + _block("restart_system", {})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER, approval_mode="auto")

    assert backend.calls == []
    call = _only(events, "tool_call")[0]
    assert call["system_gated"] is True
    assert call["auto_approved"] is False
    done = _only(events, "done")[0]
    assert done["reason"] == "awaiting_approval" and done["pending_tool_call_id"] == call["id"]


def test_request_flag_runs_a_destructive_call_when_the_setting_is_ask():
    provider = ScriptedProvider(_sse("Deleting. " + _block("delete_page", {"page_id": "p1"})), _sse("Gone."))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER, approval_mode="ask", auto_approve_destructive=True)

    assert backend.calls == [("delete_page", {"page_id": "p1"})]
    assert _only(events, "tool_call")[0]["auto_approved"] is True
    assert _only(events, "done")[0]["reason"] == "complete"


def test_request_flag_does_not_bypass_the_system_tier():
    provider = ScriptedProvider(_sse("Restarting. " + _block("restart_system", {})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER, approval_mode="auto", auto_approve_destructive=True)

    assert backend.calls == []
    assert _only(events, "done")[0]["reason"] == "awaiting_approval"


def test_auto_mode_teaches_the_model_that_destructive_tools_run_immediately():
    provider = ScriptedProvider(_sse("Hi."))
    _run_turn(provider, FakeBackend(), USER, approval_mode="auto")
    system = provider.messages_of(0)[0]["content"]
    assert "not to be asked" in system
    assert "runs immediately" in system.split("### delete_page")[1].split("### ")[0]
    assert "must approve" in system.split("### restart_system")[1].split("### ")[0]


def test_ask_mode_teaches_the_model_that_destructive_tools_pause():
    provider = ScriptedProvider(_sse("Hi."))
    _run_turn(provider, FakeBackend(), USER, approval_mode="ask")
    system = provider.messages_of(0)[0]["content"]
    assert "pause until the user approves" in system
    assert "must approve" in system.split("### delete_page")[1].split("### ")[0]


def test_the_conversation_flag_teaches_the_model_the_same_as_auto_mode():
    provider = ScriptedProvider(_sse("Hi."))
    _run_turn(provider, FakeBackend(), USER, approval_mode="ask", auto_approve_destructive=True)
    assert "not to be asked" in provider.messages_of(0)[0]["content"]


def test_a_non_destructive_call_is_never_reported_as_auto_approved():
    provider = ScriptedProvider(_sse(_block("create_page", {"name": "A"})), _sse("Made it."))
    events = _run_turn(provider, FakeBackend(), USER, approval_mode="auto")
    call = _only(events, "tool_call")[0]
    assert call["requires_approval"] is False and call["auto_approved"] is False


def _pending_transcript(call):
    return [*USER, {"role": "assistant", "content": "Deleting.", "tool_calls": [call]}]


def test_tool_drafts_reach_the_client_before_the_call():
    """The loop forwards the parser's ``tool_streaming`` frames as they
    come, ahead of the ``tool_call`` they precede."""
    text = _block("create_page", {"name": "Morning", "template_lines": ["HELLO"]})
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": text[i : i + 4]}}]}) for i in range(0, len(text), 4)
    ]
    provider = ScriptedProvider(("\n".join([*lines, "data: [DONE]"]) + "\n").encode())
    backend = FakeBackend({"create_page": ToolOutcome(status="ok", result={"page_id": "p1"})})
    events = _run_turn(provider, backend, USER)
    names = _names(events)
    assert "tool_streaming" in names
    assert names.index("tool_streaming") < names.index("tool_call")
    drafts = _only(events, "tool_streaming")
    assert drafts[-1]["op"] == "create_page"


def test_resume_approve_executes_then_continues():
    call = {"id": "c1", "name": "delete_page", "args": {"page_id": "p1"}}
    provider = ScriptedProvider(_sse("Gone."))
    backend = FakeBackend(
        {"delete_page": ToolOutcome(status="ok", result={"status": "success", "message": "Deleted."})}
    )
    events = _run_turn(
        provider, backend, _pending_transcript(call), resume={"tool_call_id": "c1", "decision": "approve"}
    )

    assert backend.calls == [("delete_page", {"page_id": "p1"})]
    names = _names(events)
    assert names.index("tool_result") < names.index("text")
    assert _only(events, "tool_result")[0] == {
        "id": "c1",
        "name": "delete_page",
        "status": "ok",
        "summary": "Deleted.",
        "result": {"status": "success", "message": "Deleted."},
        "error": None,
    }
    assert _only(events, "done")[0]["reason"] == "complete"
    assert "[Tool result] delete_page (#c1) → ok" in provider.messages_of(0)[-1]["content"]


def test_resume_deny_records_denied_and_model_sees_it_as_denied():
    call = {"id": "c1", "name": "delete_page", "args": {"page_id": "p1"}}
    provider = ScriptedProvider(_sse("Okay, leaving it."))
    backend = FakeBackend()
    events = _run_turn(provider, backend, _pending_transcript(call), resume={"tool_call_id": "c1", "decision": "deny"})

    assert backend.calls == []
    assert _only(events, "tool_result")[0]["status"] == "denied"
    assert "denied by the user" in provider.messages_of(0)[-1]["content"]


def test_resume_with_a_trailing_user_message_denies_then_continues_with_it():
    call = {"id": "c1", "name": "delete_page", "args": {"page_id": "p1"}}
    provider = ScriptedProvider(_sse("Sure."))
    messages = [*_pending_transcript(call), {"role": "user", "content": "actually rename it instead"}]
    events = _run_turn(provider, FakeBackend(), messages, resume={"tool_call_id": "c1", "decision": "deny"})
    assert _only(events, "tool_result")[0]["status"] == "denied"
    last = provider.messages_of(0)[-1]["content"]
    assert "denied by the user" in last and "rename it instead" in last
    # The denial is recorded where the server would have put it — right
    # after the call — so the renderer never also flushes it as interrupted.
    assert "interrupted" not in last
    assert last.index("denied by the user") < last.index("rename it instead")


def test_resume_is_rejected_when_no_matching_pending_call():
    events = _run_turn(ScriptedProvider(), FakeBackend(), USER, resume={"tool_call_id": "zzz", "decision": "approve"})
    assert _names(events) == ["error"]
    assert "zzz" in events[0]["data"]["message"]


# ---------------------------------------------------------------------------
# Questions to the user
# ---------------------------------------------------------------------------


def test_ask_user_ends_turn_awaiting_input_with_an_elicitation_event():
    provider = ScriptedProvider(_sse(_block("ask_user", {"question": "Which board?", "options": ["Kitchen", "Hall"]})))
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER)

    assert backend.calls == []
    call = _only(events, "tool_call")[0]
    el = _only(events, "elicitation")[0]
    assert el["id"] == call["id"] and el["name"] == "ask_user" and el["message"] == "Which board?"
    assert el["requested_schema"]["properties"]["answer"]["enum"] == ["Kitchen", "Hall"]
    done = _only(events, "done")[0]
    assert done["reason"] == "awaiting_input" and done["pending_tool_call_id"] == call["id"]


def test_resume_answer_feeds_the_answer_to_the_model():
    call = {"id": "q1", "name": "ask_user", "args": {"question": "Which board?"}}
    provider = ScriptedProvider(_sse("Kitchen it is."))
    events = _run_turn(
        provider,
        FakeBackend(),
        _pending_transcript(call),
        resume={
            "tool_call_id": "q1",
            "decision": "answer",
            "answer": {"action": "accept", "content": {"answer": "Kitchen"}},
        },
    )
    assert "tool_result" not in _names(events)
    assert _only(events, "done")[0]["reason"] == "complete"
    assert "[User's answer to your question] Kitchen" in provider.messages_of(0)[-1]["content"]


def test_resume_answer_decline_is_shown_to_the_model_as_declined():
    call = {"id": "q1", "name": "ask_user", "args": {"question": "Which board?"}}
    provider = ScriptedProvider(_sse("No problem."))
    _run_turn(
        provider,
        FakeBackend(),
        _pending_transcript(call),
        resume={"tool_call_id": "q1", "decision": "answer", "answer": {"action": "decline"}},
    )
    assert "declined to answer" in provider.messages_of(0)[-1]["content"]


# ---------------------------------------------------------------------------
# Loop limits and self-correction
# ---------------------------------------------------------------------------


def test_step_limit_ends_with_warning_and_done():
    provider = ScriptedProvider(*[_sse(_block("list_pages", {}))] * 5)
    events = _run_turn(provider, FakeBackend(), USER, limits=TurnLimits(max_model_calls=3))
    done = _only(events, "done")[0]
    assert done["reason"] == "step_limit" and done["steps"] == 3
    assert any("limit" in w["message"] for w in _only(events, "warning"))
    assert len(provider.requests) == 3


def test_unknown_tool_is_fed_back_once_for_self_correction():
    provider = ScriptedProvider(
        _sse(_block("replace_page", {"template": ["x"]})), _sse("Right: " + _block("list_pages", {})), _sse("ok")
    )
    backend = FakeBackend()
    events = _run_turn(provider, backend, USER)
    assert any("replace_page" in w["message"] for w in _only(events, "warning"))
    assert "[Tool error]" in provider.messages_of(1)[-1]["content"]
    assert backend.calls == [("list_pages", {})]
    assert _only(events, "done")[0]["reason"] == "complete"


def test_self_correction_is_bounded():
    provider = ScriptedProvider(*[_sse(_block("nope", {}))] * 6)
    events = _run_turn(provider, FakeBackend(), USER, limits=TurnLimits(max_self_corrections=1))
    assert len(provider.requests) == 2
    assert _only(events, "done")[0]["reason"] == "complete"


def test_provider_failure_mid_loop_is_a_fatal_error_frame():
    provider = ScriptedProvider(_sse(_block("list_pages", {})), 503)
    events = _run_turn(provider, FakeBackend(), USER)
    assert _names(events)[-1] == "error"
    assert "done" not in _names(events)
    assert len(_only(events, "tool_result")) == 1  # the tool ran before the provider died


def test_usage_is_aggregated_across_model_calls():
    provider = ScriptedProvider(
        _sse(_block("list_pages", {}), usage={"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}),
        _sse("ok", usage={"prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23}),
    )
    events = _run_turn(provider, FakeBackend(), USER)
    assert _only(events, "done")[0]["usage"] == {"prompt_tokens": 30, "completion_tokens": 5, "total_tokens": 35}


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_provider_gate_is_free_while_a_tool_runs():
    gate = asyncio.Semaphore(1)
    seen: list[bool] = []

    async def tool(args):
        seen.append(gate.locked())
        return ToolOutcome(status="ok", result=[])

    provider = ScriptedProvider(_sse(_block("list_pages", {})), _sse("ok"))
    _run_turn(provider, FakeBackend({"list_pages": tool}), USER, provider_gate=gate)
    assert seen == [False]


def test_client_abort_lets_in_flight_tool_finish():
    """Starlette cancels the response task when the browser disconnects.
    The tool that was already running must complete anyway — a half-applied
    write is worse than one the user did not watch finish."""
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow_tool(args):
        started.set()
        await asyncio.sleep(0.05)
        finished.set()
        return ToolOutcome(status="ok", result=[])

    provider = ScriptedProvider(_sse(_block("list_pages", {})), _sse("ok"))

    async def go():
        async with httpx.AsyncClient(transport=provider.transport()) as client:
            gen = run_chat_turn(
                messages=USER,
                resume=None,
                device_type="flagship",
                surface="global",
                providers_block=PROVIDERS,
                backend=FakeBackend({"list_pages": slow_tool}),
                client=client,
            )

            async def consume():
                async for _ in gen:
                    pass

            task = asyncio.create_task(consume())
            await asyncio.wait_for(started.wait(), timeout=1.0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not finished.is_set(), "the cancel landed after the tool had already finished; test proves nothing"
            await asyncio.wait_for(finished.wait(), timeout=1.0)

    asyncio.run(go())
    assert finished.is_set()


# ---------------------------------------------------------------------------
# Replay fidelity
# ---------------------------------------------------------------------------


def test_replayed_transcript_renders_identically_to_in_loop_transcript():
    """What the client sends back next turn must render exactly as the loop
    rendered its own steps — otherwise a resumed conversation reads
    differently to the model than an uninterrupted one."""
    provider = ScriptedProvider(_sse("Looking. " + _block("list_pages", {})), _sse("None yet."))
    backend = FakeBackend({"list_pages": ToolOutcome(status="ok", result=[])})
    events = _run_turn(provider, backend, USER)
    in_loop = provider.messages_of(1)

    call = _only(events, "tool_call")[0]
    result = _only(events, "tool_result")[0]
    replay = [
        *USER,
        {
            "role": "assistant",
            "content": "Looking. ",
            "tool_calls": [{"id": call["id"], "name": call["name"], "args": call["args"]}],
        },
        {
            "role": "tool",
            "tool_call_id": result["id"],
            "name": result["name"],
            "status": result["status"],
            "result": result["result"],
        },
    ]
    provider2 = ScriptedProvider(_sse("welcome"))
    _run_turn(provider2, FakeBackend(), replay)
    replayed = provider2.messages_of(0)
    assert replayed[1:] == in_loop[1:]
