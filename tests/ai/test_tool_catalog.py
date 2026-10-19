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
from src.ai.tool_catalog import RETIRED_OPS, ParsedToolCall, ToolCallValidationError, ToolCatalog, dropped_paragraphs


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


def test_a_null_default_is_not_printed_after_an_optional_arg():
    """``?`` already says the arg may be omitted, and omitting it is what a
    null default means. 133 real args printed `` = null`` — ~930 B of the
    addendum on every surface (#2036) — and told the model nothing."""
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "default": None}, "enabled": {"type": "boolean", "default": False}},
    }
    text = ToolCatalog([_d("update_thing", schema=schema)]).render_addendum("global")
    assert "Args: name?: string, enabled?: boolean = false\n" in text


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


def test_the_editor_surface_does_not_teach_the_system_tier():
    """#2036: the editor chat edits one page, and the system/hardware tools
    (restart, update, Wi-Fi, backups) were ~1.6 kB of its addendum it never
    needs. The global drawer, open on every screen, still teaches them."""
    catalog = ToolCatalog([_d("create_page"), _d("restart_system", destructive=True), _d("disconnect_wifi")])
    editor = catalog.render_addendum("editor")
    global_ = catalog.render_addendum("global")
    assert "### create_page" in editor
    assert "### restart_system" not in editor
    assert "### disconnect_wifi" not in editor
    assert "### restart_system" in global_
    assert "### disconnect_wifi" in global_


def test_a_surface_catalog_rejects_a_tool_that_surface_does_not_teach():
    """What the model is taught and what the parser accepts stay the same
    set: the editor surface refuses a system call it was never shown."""
    catalog = ToolCatalog([_d("create_page"), _d("restart_system", destructive=True)])
    with pytest.raises(ToolCallValidationError, match="restart_system"):
        catalog.for_surface("editor").validate({"op": "restart_system", "args": {"x": "1"}})
    assert catalog.for_surface("global").validate({"op": "restart_system", "args": {"x": "1"}}).name == (
        "restart_system"
    )


def test_every_tool_a_surface_omits_is_one_the_real_server_publishes():
    """A renamed tool would silently slip back onto the surface it was left
    off, and its bytes back into that surface's budget."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend
    from src.ai.tool_catalog import _SURFACE_OMITTED_TOOLS

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    published = {d.name for d in descriptors}
    for surface, omitted in _SURFACE_OMITTED_TOOLS.items():
        assert omitted <= published, f"{surface} omits tools the server does not publish: {sorted(omitted - published)}"


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


#: Byte ceiling for one rendered addendum, raised 40,000 -> 41,000 for #2036.
#: The extra kilobyte buys room for destructive preconditions ("the last board
#: cannot be removed", "needs the updater sidecar") to sit in the first
#: paragraph, which is the only part of a docstring the chat surface renders.
#: Bytes are a tokenizer-free proxy for the real cost: measured just before
#: this change, 38,137 B of addendum was ~9,032 cl100k tokens.
# The five generic display tools and their parameter guidance produce a
# measured global/ask addendum of 40,958 bytes (40,799 in auto mode).
# Retain that complete surface and leave more than the 1,000-byte margin;
# using the historical ratio above, this is approximately 9,700 tokens.
ADDENDUM_BYTE_BUDGET = 43_000

#: How close to the budget a surface may get before this test fails (#2036).
#: The budget was found one sentence at a time twice (125 B of headroom before
#: #2043, 271 B before this change), each time by whoever added the next
#: sentence. Failing a kilobyte early (~240 cl100k tokens) leaves room to make
#: the call on purpose: render fewer tools on that surface
#: (``_SURFACE_OMITTED_TOOLS``), trim, or raise the budget against a measured
#: token cost.
ADDENDUM_HEADROOM_MARGIN = 1_000


@pytest.mark.parametrize("surface", ["editor", "global"])
@pytest.mark.parametrize("skip_destructive_pause", [False, True])
def test_addendum_for_the_real_server_stays_under_the_size_budget(surface, skip_destructive_pause):
    """Every surface/mode combination, not just the cheapest one, with
    ADDENDUM_HEADROOM_MARGIN to spare.

    ``auto`` renders more than ``ask``. Before #2036 the editor rendered every
    tool and was the largest; it now leaves the system tier out, so ``global``
    is. Sizes at the time of writing: global/auto 39,662 · global/ask 39,496
    · editor/auto 38,154 · editor/ask 38,058 (#2036 measured editor/auto at
    40,729 before the change: 271 B of headroom).
    """
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    text = ToolCatalog(descriptors).render_addendum(surface, skip_destructive_pause=skip_destructive_pause)
    size = len(text.encode())
    assert size + ADDENDUM_HEADROOM_MARGIN <= ADDENDUM_BYTE_BUDGET, (
        f"{surface}/{'auto' if skip_destructive_pause else 'ask'} addendum is {size} bytes: "
        f"{ADDENDUM_BYTE_BUDGET - size} B of headroom under the {ADDENDUM_BYTE_BUDGET} budget, "
        f"less than the {ADDENDUM_HEADROOM_MARGIN} B margin. Decide, don't squeeze: leave tools "
        "this surface does not need out of it (_SURFACE_OMITTED_TOOLS), trim descriptions, "
        "or raise the budget against a measured token cost."
    )
    # A ratchet, not a target: it catches a backend that silently stops
    # publishing tools. 83 today.
    assert len(descriptors) >= 80


# ---------------------------------------------------------------------------
# Destructive preconditions reach the chat surface (#2036)
# ---------------------------------------------------------------------------


def _real_server_addendum(surface="global", *, skip_destructive_pause=False):
    """The addendum rendered from the live MCP + chat descriptors."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    return ToolCatalog(descriptors).render_addendum(surface, skip_destructive_pause=skip_destructive_pause)


@pytest.mark.parametrize(
    ("tool", "precondition"),
    [
        (
            "remove_board",
            "The last board cannot be removed, and a board driven by a FiestaPanel "
            "must be removed via delete_panel() instead",
        ),
        ("restart_system", "Needs the updater sidecar (get_system_status() → update.updater_available)"),
        ("trigger_system_update", "Needs the updater sidecar (get_system_status() → update.updater_available)"),
    ],
)
def test_a_destructive_tools_precondition_is_in_the_paragraph_chat_renders(tool, precondition):
    """A hard precondition has to be in the docstring's FIRST paragraph.

    ``_compact_description`` keeps that paragraph plus ``Args:`` and drops
    everything after, so a precondition parked in a later WARNING paragraph is
    invisible to the in-app chat: the model proposes the call, the user approves
    it, and the API refuses. These three are refusals, not consequences — the
    model can avoid them if it is told, which is why they pay for their bytes
    where the seven remaining WARNING paragraphs do not.
    """
    section = _real_server_addendum().split(f"### {tool}")[1].split("### ")[0]
    assert precondition in section, f"{tool} renders as:\n{section}"


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
    test_list_panels_advertises_the_page_grid_it_is_meant_to_be_read_for."""
    text = catalog.render_addendum(surface, skip_destructive_pause=skip_destructive_pause)
    assert "list_panels" in text
    assert "never the flagship default" in text


def test_list_panels_advertises_the_page_grid_it_is_meant_to_be_read_for():
    """The rule above sends the model to list_panels() for a panel's shape, so
    list_panels' own description has to say how that shape becomes a page.
    Panels are fit per character (device_type 'panel'), so the page fields are
    grid_rows/grid_cols — a model still reaching for notes_wide/notes_tall
    would author a Note-multiple page that fits no panel."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    text = ToolCatalog(descriptors).render_addendum("global")
    section = text.split("### list_panels")[1].split("### ")[0]
    assert "grid_rows" in section and "grid_cols" in section


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


# ---------------------------------------------------------------------------
# Guidance below the first paragraph never reaches in-app chat (#2036)
# ---------------------------------------------------------------------------


def test_dropped_paragraphs_matches_what_the_renderer_omits():
    doc = "Do the thing.\n\nReturns a dict with notes_wide.\n\nArgs:\n    x: The x.\n\nTip: call it twice."
    assert dropped_paragraphs(doc) == ["Returns a dict with notes_wide.", "Tip: call it twice."]
    assert dropped_paragraphs("One paragraph only.") == []
    assert dropped_paragraphs("") == []
    # Only the first Args: block is rendered, so a second one counts as dropped.
    assert dropped_paragraphs("Do it.\n\nArgs:\n    x: X.\n\nArgs:\n    y: Y.") == ["Args:\n    y: Y."]


def test_an_argument_free_tool_loses_every_paragraph_after_the_first():
    """The sharp edge from #2035: no ``Args:`` block, so nothing below the
    first paragraph survives — not even a line the model needs."""
    doc = "List things.\n\nEach entry has notes_wide."
    no_args = {"type": "object", "properties": {}}
    text = ToolCatalog([_d("list_things", schema=no_args, description=doc)]).render_addendum("global")
    assert "List things." in text
    assert "notes_wide" not in text
    assert dropped_paragraphs(doc) == ["Each entry has notes_wide."]


#: Reviewed snapshot (#2036) of how many docstring paragraphs each real tool
#: has that in-app chat never sees. These are return shapes, WARNING
#: consequences and tips that external MCP clients still receive in full.
#: A RATCHET: a count may go down (or a tool drop off) freely; it may not go
#: up, and a tool not listed may not start dropping paragraphs, without
#: someone deciding here that the new text is fine for chat to miss.
REVIEWED_DROPPED_PARAGRAPHS: dict[str, int] = {
    "add_board": 1,
    "blank_board": 1,
    "cancel_temporary_override": 2,
    "check_for_update": 1,
    "check_plugin_updates": 2,
    "clear_board_cache": 1,
    "configure_plugin": 5,
    "create_collection": 1,
    "create_page": 3,
    "create_panel": 1,
    "create_plugin_demo_page": 2,
    "create_plugin_instance": 2,
    "create_schedule": 1,
    "delete_page": 1,
    "delete_panel": 1,
    "delete_plugin_instance": 1,
    "detect_board_size": 2,
    "disable_plugin": 1,
    "disconnect_wifi": 1,
    "enable_plugin": 1,
    "export_backup": 1,
    "export_page": 2,
    "fill_board": 1,
    "force_refresh": 2,
    "forget_wifi_network": 1,
    "get_active_page": 2,
    "get_board_content": 2,
    "get_current_display": 2,
    "get_page": 1,
    "get_plugin_data": 2,
    "get_plugin_demo_page": 1,
    "get_plugin_manifest": 1,
    "get_settings_summary": 2,
    "get_silence_status": 2,
    "get_system_status": 2,
    "get_template_variables": 2,
    "get_temporary_override": 2,
    "identify_tile": 1,
    "import_page": 2,
    "import_staff_pick": 2,
    "install_plugin": 2,
    "list_collections": 1,
    "list_formula_functions": 2,
    "list_installed_plugins": 1,
    "list_pages": 1,
    "list_panels": 1,
    "list_pending_plugin_updates": 2,
    "list_plugin_errors": 1,
    "list_plugin_instances": 1,
    "list_plugin_options": 2,
    "list_registry_plugins": 2,
    "list_schedules": 2,
    "list_staff_picks": 1,
    "list_transition_plugins": 2,
    "pause_board": 1,
    "preview_saved_page": 2,
    "remove_board": 1,
    "render_page_preview": 2,
    "restart_system": 1,
    "restore_board": 2,
    "resume_board": 1,
    "run_network_diagnostics": 1,
    "send_message": 2,
    "set_active_page": 1,
    "set_default_page": 1,
    "set_schedule_mode": 1,
    "set_temporary_override": 1,
    "show_board_debug_info": 1,
    "shutdown_system": 1,
    "test_ai_provider": 1,
    "test_transition_live": 3,
    "trigger_system_update": 1,
    "uninstall_plugin": 1,
    "update_all_plugins": 1,
    "update_board": 1,
    "update_collection": 1,
    "update_page": 2,
    "update_panel": 1,
    "update_plugin": 1,
    "update_schedule": 1,
    "update_setting": 3,
    "validate_schedules": 2,
    "validate_template": 2,
}


def test_no_tool_hides_new_guidance_below_its_first_paragraph():
    """Fails when a tool's docstring gains a paragraph the chat renderer drops.

    Anything the in-app model must know goes in the FIRST paragraph (or the
    ``Args:`` block, for a parameter). If the new paragraph really is only for
    human readers and external MCP clients, bump that tool's count in
    REVIEWED_DROPPED_PARAGRAPHS — deliberately, in the same change.
    """
    pytest.importorskip("mcp", reason="mcp package not installed")
    import asyncio

    from src.ai.chat_tools import ChatExtensionBackend
    from src.ai.mcp_bridge import CompositeToolBackend, McpToolBackend

    descriptors = asyncio.run(CompositeToolBackend(McpToolBackend(), ChatExtensionBackend()).list_tools())
    grown = {}
    for d in descriptors:
        dropped = dropped_paragraphs(d.description)
        if len(dropped) > REVIEWED_DROPPED_PARAGRAPHS.get(d.name, 0):
            grown[d.name] = dropped
    assert not grown, (
        "These tools have docstring paragraphs that in-app chat never sees "
        "(only the first paragraph and Args: are rendered). Move anything the "
        "model must know into the first paragraph, or raise the tool's count in "
        "REVIEWED_DROPPED_PARAGRAPHS if it is only for human/MCP readers:\n"
        + "\n".join(f"- {name}: {paras[-1][:120]!r}" for name, paras in sorted(grown.items()))
    )


def test_editor_keeps_display_discovery_and_omits_display_management():
    discovery = {"list_display_outputs", "get_display_info"}
    management = {"create_display", "configure_display", "run_display_action"}
    catalog = ToolCatalog([_d(name) for name in sorted(discovery | management)])
    assert set(catalog.for_surface("global").names) == discovery | management
    assert set(catalog.for_surface("editor").names) == discovery
    for name in management:
        with pytest.raises(ToolCallValidationError):
            catalog.for_surface("editor").validate({"op": name})


def test_tv_can_discover_its_display_without_managing_display_settings():
    catalog = ToolCatalog(
        [
            _d(name, schema={"type": "object", "properties": {}})
            for name in ("get_display_info", "create_display", "configure_display", "run_display_action")
        ]
    ).for_tv("living-room")
    assert catalog.validate({"op": "get_display_info"}).args == {"board_id": "living-room"}
    for name in ("create_display", "configure_display", "run_display_action"):
        with pytest.raises(ToolCallValidationError):
            catalog.validate({"op": name})


def test_typed_canvas_signature_names_the_model_without_expanding_its_schema():
    schema = {
        "type": "object",
        "properties": {
            "canvases": {
                "anyOf": [{"type": "array", "items": {"$ref": "#/$defs/Canvas"}}, {"type": "null"}],
                "default": None,
            }
        },
        "$defs": {
            "Canvas": {"type": "object", "properties": {"area": {"type": "object"}, "content": {"type": "object"}}}
        },
    }
    rendered = ToolCatalog([_d("create_page", schema=schema)]).render_addendum("editor")
    assert "canvases?: array of Canvas" in rendered
    assert '"properties"' not in rendered


@pytest.mark.parametrize("surface", ["editor", "global"])
def test_the_catalog_directs_authors_to_effective_display_facts(catalog, surface):
    rendered = catalog.render_addendum(surface)
    assert "get_display_info" in rendered
    assert "character set" in rendered
    assert "canvas" in rendered.lower()


def test_editor_create_workflow_preserves_complete_unsaved_draft(catalog):
    intro = catalog.render_addendum("editor").split("AVAILABLE TOOLS")[0]
    for field in ("geometry", "canvases", "formatting", "duration", "transition"):
        assert field in intro


@pytest.mark.parametrize("surface", ["editor", "global"])
def test_real_catalog_preserves_the_display_tools_for_each_surface(surface):
    text = _real_server_addendum(surface)
    for name in ("list_display_outputs", "get_display_info"):
        assert f"### {name}" in text
    for name in ("create_display", "configure_display", "run_display_action"):
        assert (f"### {name}" in text) == (surface == "global")


def test_real_canvas_tools_publish_a_named_canvas_argument():
    text = _real_server_addendum("editor")
    for name in ("create_page", "update_page", "render_page_preview", "validate_template"):
        section = text.split(f"### {name}\n", 1)[1].split("### ", 1)[0]
        assert "canvases?: array of Canvas" in section


@pytest.mark.parametrize("inline", [False, True])
def test_named_structured_arguments_stay_named_when_schema_is_inlined(inline):
    canvas = {
        "type": "object",
        "title": "Canvas",
        "properties": {"area": {"type": "object"}, "content": {"type": "object"}},
    }
    item = canvas if inline else {"$ref": "#/$defs/Canvas"}
    schema = {
        "type": "object",
        "properties": {"canvases": {"type": "array", "items": item}},
        "$defs": {"Canvas": canvas},
    }
    text = ToolCatalog([_d("create_page", schema=schema)]).render_addendum("editor")
    assert "canvases?: array of Canvas" in text
