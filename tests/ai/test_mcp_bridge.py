"""The chat's view of the MCP server: descriptors in, outcomes out.

``src/ai/mcp_bridge.py`` is the only chat-side module that knows the ``mcp``
package. Everything the agent loop needs — which tools exist, what they
accept, whether they are safe to run unasked, and what happened when one
ran — crosses this seam as plain dataclasses, so the loop and its tests
never touch SDK types.

Two SDK facts drive the mapping and are pinned here because they are easy
to get wrong from the SDK's public docs alone:

- in-process ``MCPServer.call_tool()`` **raises** ``ToolError`` for both a
  domain failure and an argument-validation failure (the ``isError`` result
  shape only exists on the transport), and prefixes the message with
  ``Error executing tool <name>:``;
- a tool whose return annotation is not a plain ``dict`` gets its value
  wrapped as ``{"result": ...}`` in ``structuredContent``.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.ai.mcp_bridge import (
    CompositeToolBackend,
    McpToolBackend,
    ToolBackendUnavailable,
    ToolDescriptor,
    ToolOutcome,
    descriptor_from_wire,
    outcome_from_call_tool_result,
    outcome_from_tool_error,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Descriptor mapping (pure)
# ---------------------------------------------------------------------------


def test_descriptor_reads_annotations_by_wire_name():
    wire = {
        "name": "delete_page",
        "title": "Delete page",
        "description": "Delete a page.",
        "inputSchema": {"type": "object", "properties": {"page_id": {"type": "string"}}, "required": ["page_id"]},
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    }
    d = descriptor_from_wire(wire)
    assert d == ToolDescriptor(
        name="delete_page",
        title="Delete page",
        description="Delete a page.",
        input_schema=wire["inputSchema"],
        read_only=False,
        destructive=True,
        idempotent=False,
        open_world=False,
        source="mcp",
    )
    assert d.requires_approval is True


def test_unannotated_tool_defaults_to_requiring_approval():
    """The spec default for a missing destructiveHint is *true*; so is ours."""
    d = descriptor_from_wire({"name": "mystery", "description": "?", "inputSchema": {"type": "object"}})
    assert d.read_only is False
    assert d.destructive is True
    assert d.requires_approval is True
    assert d.open_world is True
    assert d.title == "mystery"


def test_read_only_descriptor_never_requires_approval():
    d = descriptor_from_wire(
        {
            "name": "list_pages",
            "description": "List.",
            "inputSchema": {"type": "object"},
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }
    )
    assert d.requires_approval is False


# ---------------------------------------------------------------------------
# Outcome mapping (pure)
# ---------------------------------------------------------------------------


def test_structured_content_becomes_the_result():
    out = outcome_from_call_tool_result(
        {"content": [], "structuredContent": {"valid": True, "errors": []}, "isError": False}
    )
    assert out == ToolOutcome(status="ok", result={"valid": True, "errors": []})


def test_single_key_result_wrapper_is_unwrapped():
    out = outcome_from_call_tool_result(
        {"content": [], "structuredContent": {"result": [{"id": "p1"}]}, "isError": False}
    )
    assert out.result == [{"id": "p1"}]


def test_blocked_envelope_becomes_blocked_status():
    out = outcome_from_call_tool_result(
        {"content": [], "structuredContent": {"status": "blocked", "message": "Board is paused."}, "isError": False}
    )
    assert out.status == "blocked"
    assert out.result == {"status": "blocked", "message": "Board is paused."}


def test_text_only_content_is_parsed_as_json_when_possible():
    out = outcome_from_call_tool_result({"content": [{"type": "text", "text": '{"a": 1}'}], "isError": False})
    assert out.result == {"a": 1}


def test_text_only_content_that_is_not_json_is_kept_as_text():
    out = outcome_from_call_tool_result({"content": [{"type": "text", "text": "plain words"}], "isError": False})
    assert out.result == {"text": "plain words"}


def test_is_error_result_becomes_error_status():
    out = outcome_from_call_tool_result({"content": [{"type": "text", "text": "boom"}], "isError": True})
    assert out.status == "error"
    assert out.error == "boom"


def test_tool_error_prefix_is_stripped_and_message_bounded():
    out = outcome_from_tool_error("get_page", "Error executing tool get_page: Page 'nope' not found.")
    assert out == ToolOutcome(status="error", error="Page 'nope' not found.")
    long = outcome_from_tool_error("x", "Error executing tool x: " + "y" * 5000)
    assert len(long.error) <= 600


def test_multiline_validation_error_is_collapsed_to_one_line():
    msg = "Error executing tool create_page: 2 validation errors for create_pageArguments\nname\n  Input should be a valid string"
    out = outcome_from_tool_error("create_page", msg)
    assert "\n" not in out.error
    assert "name" in out.error and "valid string" in out.error


# ---------------------------------------------------------------------------
# The real server, in process
# ---------------------------------------------------------------------------


@pytest.fixture
def backend():
    return McpToolBackend()


def test_catalog_contains_every_registered_mcp_tool(backend):
    from src.mcp_server import mcp_server

    descriptors = _run(backend.list_tools())
    assert {d.name for d in descriptors} == set(mcp_server._tool_manager._tools)
    assert all(d.source == "mcp" for d in descriptors)


def test_descriptor_carries_input_schema_and_annotation_flags(backend):
    by_name = {d.name: d for d in _run(backend.list_tools())}
    create = by_name["create_page"]
    assert set(create.input_schema["required"]) == {"name", "template_lines"}
    assert create.destructive is False and create.read_only is False
    assert by_name["list_pages"].read_only is True
    assert by_name["delete_page"].requires_approval is True
    assert "Args:" in create.description


def test_list_tools_is_cached_per_backend(backend):
    first = _run(backend.list_tools())
    second = _run(backend.list_tools())
    assert first is second


def test_success_maps_structured_content_to_result(backend):
    out = _run(backend.call_tool("validate_template", {"template": "HELLO", "device_type": "flagship"}))
    assert out.status == "ok"
    assert out.result["valid"] is True


def test_wrapped_list_result_is_unwrapped_for_list_pages(backend):
    out = _run(backend.call_tool("list_pages", {}))
    assert out.status == "ok"
    assert isinstance(out.result, list)


def test_tool_error_becomes_error_outcome_with_prefix_stripped(backend):
    out = _run(backend.call_tool("get_page", {"page_id": "no-such-page"}))
    assert out.status == "error"
    assert out.error.startswith("Page 'no-such-page' not found")


def test_unknown_tool_is_an_error_outcome_not_an_exception(backend):
    out = _run(backend.call_tool("no_such_tool", {}))
    assert out.status == "error"
    assert "no_such_tool" in out.error


def test_argument_validation_failure_names_the_bad_field(backend):
    out = _run(backend.call_tool("create_page", {"name": 1}))
    assert out.status == "error"
    assert "name" in out.error and "template_lines" in out.error


def test_timeout_becomes_error_outcome():
    class SlowServer:
        async def list_tools(self):
            return []

        async def call_tool(self, name, arguments, context=None):
            await asyncio.sleep(10)

    backend = McpToolBackend(server=SlowServer(), timeout_seconds=0.05)
    out = _run(backend.call_tool("anything", {}))
    assert out.status == "error"
    assert "timed out" in out.error


def test_input_required_result_is_reported_not_crashed():
    from mcp.types import InputRequiredResult

    class ElicitingServer:
        async def list_tools(self):
            return []

        async def call_tool(self, name, arguments, context=None):
            return InputRequiredResult(inputRequests={}, requestState="s")

    backend = McpToolBackend(server=ElicitingServer())
    out = _run(backend.call_tool("asks", {}))
    assert out.status == "error"
    assert "interactive input" in out.error


def test_unavailable_server_raises_a_named_error():
    backend = McpToolBackend(server=None, server_factory=lambda: None)
    with pytest.raises(ToolBackendUnavailable):
        _run(backend.list_tools())


# ---------------------------------------------------------------------------
# Composite: MCP + chat-only extensions
# ---------------------------------------------------------------------------


class _Fake:
    def __init__(self, names, source="chat"):
        self._names = names
        self.source = source
        self.calls = []

    async def list_tools(self):
        return [
            ToolDescriptor(n, n, "d", {"type": "object"}, False, False, True, False, self.source) for n in self._names
        ]

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return ToolOutcome(status="ok", result={"from": self.source})


def test_composite_dispatches_by_tool_name():
    a, b = _Fake(["one"], "mcp"), _Fake(["two"], "chat")
    comp = CompositeToolBackend(a, b)
    assert [d.name for d in _run(comp.list_tools())] == ["one", "two"]
    assert _run(comp.call_tool("two", {"x": 1})).result == {"from": "chat"}
    assert b.calls == [("two", {"x": 1})]


def test_composite_refuses_colliding_tool_names():
    with pytest.raises(ValueError, match="one"):
        _run(CompositeToolBackend(_Fake(["one"]), _Fake(["one"])).list_tools())


def test_composite_unknown_tool_is_an_error_outcome():
    out = _run(CompositeToolBackend(_Fake(["one"])).call_tool("zzz", {}))
    assert out.status == "error" and "zzz" in out.error
