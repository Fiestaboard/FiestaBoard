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


def _with_system_tier(catalog_descriptors):
    return ToolCatalog([*catalog_descriptors, _d("restart_system", destructive=True)])


def test_addendum_in_ask_mode_says_destructive_tools_pause(catalog):
    text = catalog.render_addendum("global")
    assert "pause until the user approves" in text
    assert "must approve" in text.split("### delete_page")[1].split("### ")[0]


def test_addendum_in_ask_mode_forbids_narrating_a_destructive_call_as_done(catalog):
    # #2024: the model printed "I've removed the Goodnight schedule entry"
    # while the approval card was still waiting for an answer, so the
    # transcript claimed something that had not happened and might not.
    text = catalog.render_addendum("global")
    assert "Do not say you have done it" in text
    assert "stop after the call" in text


def test_addendum_does_not_forbid_narration_when_nothing_will_pause():
    # In Auto the call runs immediately, so "stop and wait" would be wrong
    # advice — the rule belongs only to the mode that actually pauses.
    catalog = _with_system_tier([_d("delete_page", destructive=True)])
    text = catalog.render_addendum("global", skip_destructive_pause=True)
    assert "Do not say you have done it" not in text


def test_addendum_when_destructive_pauses_are_skipped_says_they_run_immediately():
    catalog = _with_system_tier(
        [
            _d("list_pages", read_only=True),
            _d("delete_page", destructive=True),
            _d("ask_user", read_only=True, source="chat"),
        ]
    )
    text = catalog.render_addendum("global", skip_destructive_pause=True)
    section = lambda n: text.split(f"### {n}")[1].split("### ")[0]  # noqa: E731
    assert "runs immediately" in section("delete_page")
    assert "must approve" not in section("delete_page")
    assert "not to be asked" in text
    # The system tier is described, and still pauses.
    assert "SYSTEM" in section("restart_system")
    assert "must approve" in section("restart_system")


def test_addendum_in_ask_mode_still_marks_the_system_tier_as_gated():
    catalog = _with_system_tier([_d("delete_page", destructive=True)])
    text = catalog.render_addendum("global")
    assert "SYSTEM" in text.split("### restart_system")[1]
    assert "must approve" in text.split("### restart_system")[1]


def test_addendum_for_the_real_server_stays_under_the_size_budget():
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    for skip in (False, True):
        text = ToolCatalog(descriptors).render_addendum("global", skip_destructive_pause=skip)
        assert len(text.encode()) < 40_000, f"addendum is {len(text.encode())} bytes; trim descriptions"
    assert len(descriptors) >= 34


# ---------------------------------------------------------------------------
# Panel-sized pages (#2032 follow-up)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface", ["editor", "global"])
@pytest.mark.parametrize("skip_destructive_pause", [False, True])
def test_addendum_sends_the_model_to_list_panels_for_a_panel_sized_page(catalog, surface, skip_destructive_pause):
    """A page is authored for one board shape, so "make a page for my panel"
    has to read the panel's shape instead of falling back to the flagship
    default. The rule lives in the shared tail, so it is taught on every
    surface and in both approval modes. Which FIELDS to read is pinned on
    list_panels' own description instead of restated here — see
    test_list_panels_advertises_the_note_grid_it_is_meant_to_be_read_for."""
    text = catalog.render_addendum(surface, skip_destructive_pause=skip_destructive_pause)
    assert "list_panels" in text
    assert "never the flagship default" in text


def test_list_panels_advertises_the_note_grid_it_is_meant_to_be_read_for():
    """The rule above sends the model to list_panels() for notes_wide/notes_tall,
    so list_panels' own description has to name them. A model planning from a
    description that lists only rows/cols divides cols by 15 itself — the exact
    guesswork the two fields exist to remove."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    text = ToolCatalog(descriptors).render_addendum("global")
    section = text.split("### list_panels")[1].split("### ")[0]
    assert "notes_wide" in section and "notes_tall" in section


# ---------------------------------------------------------------------------
# Acting instead of announcing (#2042)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface", ["editor", "global"])
@pytest.mark.parametrize("skip_destructive_pause", [False, True])
def test_the_rules_tell_the_model_to_act_in_the_reply_that_announces_it(catalog, surface, skip_destructive_pause):
    """Prevention for #2042. A reply that says "I'll create that page" and
    emits no block leaves the user with a promise and nothing done; the
    agent loop asks about it afterwards, and this rule is what stops it
    happening. It lives in the shared head, so it is taught on every
    surface and in both approval modes."""
    text = catalog.render_addendum(surface, skip_destructive_pause=skip_destructive_pause)
    assert "Never say you will act and then stop" in text


def test_a_title_that_only_respells_the_tool_name_is_not_printed():
    """MCP titles are mostly the name re-spelled, and the addendum is paid
    for on every turn (#2036). Repeating "create_page — Create page" buys
    the model nothing."""
    text = ToolCatalog([_d("create_page")]).render_addendum("global")
    assert "### create_page\n" in text
    assert "Create page" not in text


def test_a_title_that_says_something_the_name_does_not_is_kept():
    descriptor = ToolDescriptor(
        name="ask_user",
        title="Ask the user",
        description="Ask.",
        input_schema={"type": "object", "properties": {}},
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=False,
        source="chat",
    )
    assert "### ask_user — Ask the user" in ToolCatalog([descriptor]).render_addendum("global")
