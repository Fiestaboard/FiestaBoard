"""End to end, minus the browser: the real app, loop, MCP server and stores.

Every other AI test mocks one seam — the provider, the tool backend, or the
loop itself. This one mocks nothing inside the process. The FastAPI app is
served by ``TestClient``; ``POST /pages/ai/chat`` runs the real agent loop
(:mod:`src.ai.agent`), which calls the real in-process MCP server
(:mod:`src.mcp_server`) against real page/schedule stores in a temp data
dir, and the "model" is ``integration-tests/mock-llm/server.py`` — the same
stdlib server the Playwright suite drives — started on a local port and
scripted per test.

What this proves that the unit tests cannot: a scripted tool call from the
model ends as a row in the page store, reachable over the REST API, with
the stream frames in between exactly as the browser will see them; and
the pause/resume round trips (approval, question) survive the wire.

Skipped when ``mcp`` is not installed, like the rest of the MCP tests.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mcp", reason="mcp package not installed")

from src.api_server import app
from src.config_manager import ConfigManager

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_LLM = REPO_ROOT / "integration-tests" / "mock-llm" / "server.py"


# ---------------------------------------------------------------------------
# The mock model on a local port
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read() or b"{}")


@pytest.fixture(scope="module")
def mock_llm():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(MOCK_LLM)],
        env={**os.environ, "PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while True:
        try:
            _http("GET", f"{base}/mock/state")
            break
        except Exception:
            if time.monotonic() > deadline or proc.poll() is not None:
                proc.kill()
                pytest.fail("mock LLM did not come up")
            time.sleep(0.1)

    def script(steps: list[dict[str, Any]]) -> None:
        _http("POST", f"{base}/mock/reset")
        _http("POST", f"{base}/mock/script", {"steps": steps})

    def history() -> list[dict[str, Any]]:
        return _http("GET", f"{base}/mock/state")["history"]

    yield SimpleNamespace(base_url=f"{base}/v1", script=script, history=history)
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def cm(tmp_path, monkeypatch, mock_llm):
    """A provider block pointing the real loop at the mock model."""
    manager = ConfigManager(config_path=str(tmp_path / "config.json"))
    manager.set_ai_providers(
        {
            "enabled": True,
            "default_provider_id": "mock",
            "providers": [
                {
                    "id": "mock",
                    "name": "Mock",
                    "protocol": "openai",
                    "base_url": mock_llm.base_url,
                    "api_key": "test_key",
                    "models": ["mock-model"],
                    "default_model": "mock-model",
                }
            ],
        }
    )
    monkeypatch.setattr("src.ai.page_routes.get_config_manager", lambda: manager)
    return manager


@pytest.fixture
def client():
    return TestClient(app)


def _frames(raw: str) -> list[tuple[str, dict[str, Any]]]:
    parsed: list[tuple[str, dict[str, Any]]] = []
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        name = next((line[len("event: ") :] for line in lines if line.startswith("event: ")), None)
        payload = next((line[len("data: ") :] for line in lines if line.startswith("data: ")), None)
        if name is not None and payload is not None:
            parsed.append((name, json.loads(payload)))
    return parsed


def _only(frames, name):
    return [data for event, data in frames if event == name]


def _block(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"op": name, "args": args}


def _chat(
    client: TestClient,
    messages: list[dict[str, Any]],
    resume: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
):
    body: dict[str, Any] = {"messages": messages, "device_type": "flagship", "surface": "global"}
    if resume is not None:
        body["resume"] = resume
    if approval is not None:
        body["approval"] = approval
    res = client.post("/pages/ai/chat", json=body)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    return _frames(res.text)


def _page_names(client: TestClient) -> dict[str, str]:
    body = client.get("/pages").json()
    pages = body["pages"] if isinstance(body, dict) else body
    return {p["id"]: p["name"] for p in pages}


USER = [{"role": "user", "content": "make a morning page"}]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_a_scripted_create_page_lands_in_the_page_store_through_mcp(client, cm, mock_llm):
    mock_llm.script(
        [
            {
                "prose": "Creating it. ",
                "ops": [_block("create_page", {"name": "E2E Morning", "template_lines": ["HELLO"]})],
            },
            {"prose": "Done — it is saved."},
        ]
    )

    frames = _chat(client, USER)

    names = [event for event, _ in frames]
    assert names[0] == "status"
    call = _only(frames, "tool_call")[0]
    assert call["name"] == "create_page"
    assert call["requires_approval"] is False and call["read_only"] is False and call["source"] == "mcp"
    result = _only(frames, "tool_result")[0]
    assert result["id"] == call["id"] and result["status"] == "ok", result
    page_id = result["result"]["page_id"]
    assert names.index("tool_call") < names.index("tool_result") < names.index("done")
    done = _only(frames, "done")[0]
    assert done["reason"] == "complete" and done["steps"] == 2

    # The page exists, over REST, with the name the model chose.
    assert _page_names(client)[page_id] == "E2E Morning"

    # The model was called twice, and the second call carried the outcome.
    history = mock_llm.history()
    assert len(history) == 2
    last = history[-1]["messages"][-1]
    assert last["role"] == "user" and last["content"].startswith("[Tool result] create_page")
    assert '"page_id"' in last["content"]
    # …and the first call taught the MCP catalog, not the old grammar.
    system = history[0]["messages"][0]["content"]
    assert "### create_page" in system and "### update_setting" in system
    assert '"op": "replace_page"' not in system


def test_read_only_tools_run_mid_turn_without_pausing(client, cm, mock_llm):
    mock_llm.script(
        [
            {"prose": "Let me check. ", "ops": [_block("list_pages", {})]},
            {"prose": "You have no pages yet."},
        ]
    )
    frames = _chat(client, USER)
    call = _only(frames, "tool_call")[0]
    assert call["name"] == "list_pages" and call["read_only"] is True
    result = _only(frames, "tool_result")[0]
    assert result["status"] == "ok" and isinstance(result["result"], list)
    assert _only(frames, "done")[0]["reason"] == "complete"
    assert "".join(d["delta"] for d in _only(frames, "text")).endswith("You have no pages yet.")


def test_a_destructive_call_waits_for_approval_and_only_runs_on_approve(client, cm, mock_llm):
    # Turn 1: create the page the model will later try to delete.
    mock_llm.script(
        [{"prose": "", "ops": [_block("create_page", {"name": "Doomed", "template_lines": ["X"]})]}, {"prose": "ok"}]
    )
    created = _only(_chat(client, USER), "tool_result")[0]["result"]["page_id"]
    assert created in _page_names(client)

    # Turn 2: the model asks to delete it — the loop pauses, nothing runs.
    mock_llm.script([{"prose": "Deleting it. ", "ops": [_block("delete_page", {"page_id": created})]}])
    ask = [{"role": "user", "content": "delete the doomed page"}]
    frames = _chat(client, ask)
    call = _only(frames, "tool_call")[0]
    assert call["name"] == "delete_page" and call["requires_approval"] is True
    done = _only(frames, "done")[0]
    assert done["reason"] == "awaiting_approval" and done["pending_tool_call_id"] == call["id"]
    assert "tool_result" not in [event for event, _ in frames]
    assert created in _page_names(client), "the page must survive until the user approves"

    # The client replays the transcript with its decision.
    transcript = [
        *ask,
        {
            "role": "assistant",
            "content": "".join(d["delta"] for d in _only(frames, "text")),
            "tool_calls": [{"id": call["id"], "name": call["name"], "args": call["args"]}],
        },
    ]

    # Deny first: still there, and the model is told.
    mock_llm.script([{"prose": "Okay, leaving it."}])
    denied = _chat(client, transcript, resume={"tool_call_id": call["id"], "decision": "deny"})
    assert _only(denied, "tool_result")[0]["status"] == "denied"
    assert created in _page_names(client)
    assert "denied by the user" in mock_llm.history()[-1]["messages"][-1]["content"]

    # Approve: gone, through the same MCP tool an external client would use.
    mock_llm.script([{"prose": "Gone."}])
    approved = _chat(client, transcript, resume={"tool_call_id": call["id"], "decision": "approve"})
    result = _only(approved, "tool_result")[0]
    assert result["id"] == call["id"] and result["status"] == "ok", result
    assert _only(approved, "done")[0]["reason"] == "complete"
    assert created not in _page_names(client)


def _create_doomed_page(client, mock_llm) -> str:
    mock_llm.script(
        [{"prose": "", "ops": [_block("create_page", {"name": "Doomed", "template_lines": ["X"]})]}, {"prose": "ok"}]
    )
    created = _only(_chat(client, USER), "tool_result")[0]["result"]["page_id"]
    assert created in _page_names(client)
    return created


def test_auto_mode_deletes_without_a_pause_and_the_frame_says_so(client, cm, mock_llm):
    """#2021: with the install set to Auto the same delete runs in one
    request — no ``awaiting_approval``, no second POST — through the same
    MCP tool, and the ``tool_call`` frame is badged ``auto_approved``."""
    created = _create_doomed_page(client, mock_llm)
    cm.set_ai_providers({"approval_mode": "auto"})

    mock_llm.script(
        [{"prose": "Deleting it. ", "ops": [_block("delete_page", {"page_id": created})]}, {"prose": "Gone."}]
    )
    frames = _chat(client, [{"role": "user", "content": "delete the doomed page"}])
    call = _only(frames, "tool_call")[0]
    assert call["name"] == "delete_page" and call["requires_approval"] is True
    assert call["auto_approved"] is True and call["system_gated"] is False
    assert _only(frames, "tool_result")[0]["status"] == "ok"
    assert _only(frames, "done")[0]["reason"] == "complete"
    assert created not in _page_names(client)


def test_the_conversation_flag_deletes_without_a_pause_while_the_install_still_asks(client, cm, mock_llm):
    created = _create_doomed_page(client, mock_llm)
    assert cm.get_ai_providers()["approval_mode"] == "ask"

    mock_llm.script(
        [{"prose": "Deleting it. ", "ops": [_block("delete_page", {"page_id": created})]}, {"prose": "Gone."}]
    )
    frames = _chat(
        client,
        [{"role": "user", "content": "delete the doomed page"}],
        approval={"auto_approve_destructive": True},
    )
    assert _only(frames, "tool_call")[0]["auto_approved"] is True
    assert _only(frames, "done")[0]["reason"] == "complete"
    assert created not in _page_names(client)


def test_a_system_action_still_pauses_in_auto_mode(client, cm, mock_llm):
    cm.set_ai_providers({"approval_mode": "auto"})
    mock_llm.script([{"prose": "Restarting. ", "ops": [_block("restart_system", {})]}])
    frames = _chat(
        client,
        [{"role": "user", "content": "restart the system"}],
        approval={"auto_approve_destructive": True},
    )
    call = _only(frames, "tool_call")[0]
    assert call["name"] == "restart_system" and call["system_gated"] is True and call["auto_approved"] is False
    done = _only(frames, "done")[0]
    assert done["reason"] == "awaiting_approval" and done["pending_tool_call_id"] == call["id"]
    assert "tool_result" not in [event for event, _ in frames]


def test_a_question_to_the_user_pauses_and_the_answer_reaches_the_model(client, cm, mock_llm):
    mock_llm.script(
        [{"prose": "", "ops": [_block("ask_user", {"question": "Which board?", "options": ["Kitchen", "Hall"]})]}]
    )
    frames = _chat(client, USER)
    el = _only(frames, "elicitation")[0]
    assert el["message"] == "Which board?" and el["requested_schema"]["properties"]["answer"]["enum"] == [
        "Kitchen",
        "Hall",
    ]
    done = _only(frames, "done")[0]
    assert done["reason"] == "awaiting_input" and done["pending_tool_call_id"] == el["id"]

    transcript = [
        *USER,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": el["id"], "name": "ask_user", "args": {"question": "Which board?"}}],
        },
    ]
    mock_llm.script([{"prose": "Kitchen it is."}])
    answered = _chat(
        client,
        transcript,
        resume={
            "tool_call_id": el["id"],
            "decision": "answer",
            "answer": {"action": "accept", "content": {"answer": "Kitchen"}},
        },
    )
    assert _only(answered, "done")[0]["reason"] == "complete"
    assert "[User's answer to your question] Kitchen" in mock_llm.history()[-1]["messages"][-1]["content"]


def test_a_retired_op_is_corrected_once_and_the_turn_still_completes(client, cm, mock_llm):
    mock_llm.script(
        [
            {"prose": "", "ops": [_block("replace_page", {"name": "Old", "template": ["x"]})]},
            {"prose": "Right — ", "ops": [_block("create_page", {"name": "Corrected", "template_lines": ["OK"]})]},
            {"prose": "Created."},
        ]
    )
    frames = _chat(client, USER)
    warnings = _only(frames, "warning")
    assert any("replace_page" in w["message"] and "retired" in w["message"] for w in warnings)
    assert _only(frames, "tool_result")[0]["status"] == "ok"
    assert "Corrected" in _page_names(client).values()
    assert "[Tool error]" in mock_llm.history()[1]["messages"][-1]["content"]


def test_a_tool_failure_is_reported_not_fatal(client, cm, mock_llm):
    mock_llm.script(
        [
            {"prose": "", "ops": [_block("get_page", {"page_id": "no-such-page"})]},
            {"prose": "That page does not exist."},
        ]
    )
    frames = _chat(client, USER)
    result = _only(frames, "tool_result")[0]
    assert result["status"] == "error" and "no-such-page" in result["error"]
    assert "error" not in [event for event, _ in frames]
    assert _only(frames, "done")[0]["reason"] == "complete"


def test_the_stream_is_the_published_contract(client, cm, mock_llm):
    """Every frame validates against CHAT_STREAM_EVENTS, with no undeclared keys."""
    from src.ai.page_routes import CHAT_STREAM_EVENTS

    mock_llm.script([{"prose": "Look: ", "ops": [_block("list_pages", {})]}, {"prose": "done"}])
    frames = _chat(client, USER)
    assert {event for event, _ in frames} >= {"status", "text", "tool_call", "tool_result", "done"}
    for event, data in frames:
        model = CHAT_STREAM_EVENTS[event]
        model.model_validate(data)
        assert set(data) <= set(model.model_fields), f"{event} carries undeclared keys: {sorted(data)}"
