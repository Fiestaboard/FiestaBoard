"""The tool catalog: MCP descriptors -> the prose the model is taught, and
the validator the fence parser uses.

Replaces the hand-written grammar that used to live in ``src/ai/chat.py``.
Because the text is generated from the same ``list_tools()`` the MCP server
publishes, chat and MCP cannot drift; these tests pin what the generator
must say and what the validator must accept.
"""

from __future__ import annotations

import pytest

from src.ai.mcp_bridge import ToolDescriptor
from src.ai.tool_catalog import RETIRED_OPS, ParsedToolCall, ToolCallValidationError, ToolCatalog


def _d(
    name,
    *,
    read_only=False,
    destructive=False,
    source="mcp",
    schema=None,
    description="Do a thing.\n\nArgs:\n    x: the x.",
):
    return ToolDescriptor(
        name=name,
        title=name.replace("_", " ").capitalize(),
        description=description,
        input_schema=schema or {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        read_only=read_only,
        destructive=destructive,
        idempotent=read_only,
        open_world=False,
        source=source,
    )


@pytest.fixture
def catalog():
    return ToolCatalog(
        [
            _d("list_pages", read_only=True, schema={"type": "object", "properties": {}}),
            _d(
                "create_page",
                schema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "template_lines": {"type": "array", "items": {"type": "string"}},
                        "duration_seconds": {"type": "integer", "default": 300},
                    },
                    "required": ["name", "template_lines"],
                },
                description="Create a page.\n\nArgs:\n    name: Page name.\n    template_lines: Rows.\n    duration_seconds: Seconds.\n\nAfter creating, preview it.",
            ),
            _d("delete_page", destructive=True),
            _d("ask_user", read_only=True, source="chat"),
        ]
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_accepts_a_known_tool_with_required_args(catalog):
    call = catalog.validate({"op": "create_page", "args": {"name": "A", "template_lines": ["x"]}})
    assert call == ParsedToolCall(name="create_page", args={"name": "A", "template_lines": ["x"]})


def test_validate_accepts_tool_as_an_alias_of_op(catalog):
    assert catalog.validate({"tool": "list_pages", "args": {}}).name == "list_pages"


def test_validate_defaults_missing_args_to_empty(catalog):
    assert catalog.validate({"op": "list_pages"}).args == {}


def test_validate_rejects_unknown_tool_with_closest_match_hint(catalog):
    with pytest.raises(ToolCallValidationError) as exc:
        catalog.validate({"op": "replace_page", "args": {}})
    assert "replace_page" in str(exc.value)
    assert "create_page" in str(exc.value)


def test_validate_names_retired_ops_explicitly(catalog):
    with pytest.raises(ToolCallValidationError) as exc:
        catalog.validate({"op": "navigate_to_page", "args": {"page_id": "new"}})
    assert "retired" in str(exc.value).lower()


def test_validate_reports_missing_required_args(catalog):
    with pytest.raises(ToolCallValidationError, match="template_lines"):
        catalog.validate({"op": "create_page", "args": {"name": "A"}})


def test_validate_checks_top_level_primitive_types(catalog):
    with pytest.raises(ToolCallValidationError, match="name"):
        catalog.validate({"op": "create_page", "args": {"name": 1, "template_lines": []}})


def test_validate_rejects_non_object_payloads(catalog):
    with pytest.raises(ToolCallValidationError):
        catalog.validate(["op"])
    with pytest.raises(ToolCallValidationError):
        catalog.validate({"args": {}})
    with pytest.raises(ToolCallValidationError, match="args"):
        catalog.validate({"op": "list_pages", "args": "nope"})


# ---------------------------------------------------------------------------
# The taught addendum
# ---------------------------------------------------------------------------


def test_addendum_names_every_descriptor(catalog):
    text = catalog.render_addendum("global")
    for name in ("list_pages", "create_page", "delete_page", "ask_user"):
        assert f"### {name}" in text


def test_addendum_marks_read_only_write_and_destructive_tools(catalog):
    text = catalog.render_addendum("global")
    section = lambda n: text.split(f"### {n}")[1].split("### ")[0]  # noqa: E731
    assert "read-only" in section("list_pages")
    assert "runs immediately" in section("create_page")
    assert "must approve" in section("delete_page")


def test_addendum_renders_required_args_starred_and_typed(catalog):
    text = catalog.render_addendum("global")
    assert "name*: string" in text
    assert "template_lines*: array of string" in text
    assert "duration_seconds?: integer = 300" in text


def test_addendum_keeps_the_first_paragraph_and_the_args_block_only(catalog):
    text = catalog.render_addendum("global")
    assert "Create a page." in text
    assert "template_lines: Rows." in text
    assert "After creating, preview it." not in text


def test_addendum_example_uses_the_fiestaboard_fence_and_op_key(catalog):
    text = catalog.render_addendum("global")
    assert "```fiestaboard" in text
    assert '{"op":' in text


def test_addendum_lists_retired_op_names_once(catalog):
    text = catalog.render_addendum("global")
    for op in RETIRED_OPS:
        assert text.count(op) == 1, op


def test_addendum_contains_no_retired_op_as_a_tool(catalog):
    text = catalog.render_addendum("global")
    for op in RETIRED_OPS:
        assert f"### {op}" not in text


def test_editor_and_global_surfaces_differ_only_in_the_surface_intro(catalog):
    editor = catalog.render_addendum("editor")
    global_ = catalog.render_addendum("global")
    assert editor != global_
    assert editor.split("### ")[1:] == global_.split("### ")[1:]
    assert "update_page" in editor.split("### ")[0]
    assert "create_page" in global_.split("### ")[0]


def test_addendum_for_the_real_server_stays_under_the_size_budget():
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    text = ToolCatalog(descriptors).render_addendum("global")
    assert len(text.encode()) < 40_000, f"addendum is {len(text.encode())} bytes; trim descriptions"
    assert len(descriptors) >= 34
