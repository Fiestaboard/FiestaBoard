"""Read-only audit regressions: intended contracts, currently failing.

No network or hardware calls. Kept separate from production changes so the
discovery and prompt gaps can be reviewed before selecting fixes.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.ai.prompt_builder import _format_variables, build_prompt
from src.mcp_server import _build_mcp_server
from src.outputs.display_profile import DisplayProfile


@pytest.fixture(scope="module")
def server():
    return _build_mcp_server()


def test_chat_layout_agrees_with_the_matrix_display_it_teaches():
    display = DisplayProfile(technology="led_matrix", color="rgb", rows=10, cols=16, width=64, height=64)
    context = build_prompt("Draw a sunset", "flagship", mode="chat", display=display)
    assert (context.rows, context.cols) == (10, 16), context.system_prompt[:1200]


@pytest.mark.parametrize(
    "device_type,page,expected",
    [
        ("panel", {"device_type": "panel", "grid_rows": 10, "grid_cols": 16}, (10, 16)),
        ("note_array", {"device_type": "note_array", "notes_wide": 2, "notes_tall": 2}, (6, 30)),
    ],
)
def test_chat_accepts_editable_page_geometries(device_type, page, expected):
    context = build_prompt("Improve this", device_type, mode="chat", current_page=page)
    assert (context.rows, context.cols) == expected


def test_external_mcp_can_resolve_the_pixel_canvas_rules_it_references(server):
    description = server._tool_manager._tools["create_page"].description
    assert "PIXEL CANVASES rules" in description
    # This is a referenced instruction section, not an optional design tip.
    assert "PIXEL CANVASES" in server.instructions


def test_external_canvas_schema_teaches_at_least_the_required_canvas_fields(server):
    tools = asyncio.run(server.list_tools())
    create = next(t.model_dump(by_alias=True) for t in tools if t.name == "create_page")
    schema = json.dumps(create["inputSchema"])
    assert '"area"' in schema and '"content"' in schema and '"source"' in schema, schema


def test_canvas_variable_catalog_teaches_source_usage_instead_of_printable_text():
    rendered = _format_variables({"art": {"picture": {"format": "canvas", "description": "Artwork"}}})
    assert "canvas" in rendered.lower() and "source" in rendered.lower(), rendered


@pytest.mark.parametrize("device_type", ["panel", "note_array"])
def test_chat_request_accepts_all_supported_page_device_types(device_type):
    from src.ai.page_routes import AIChatRequest

    request = AIChatRequest.model_validate(
        {"messages": [{"role": "user", "content": "Draw"}], "device_type": device_type}
    )
    assert request.device_type == device_type


def test_profile_description_keeps_custom_declaration_defensive_and_reports_effective_layout():
    from types import SimpleNamespace

    from src.fiestaui import builtin_device_models
    from src.led.charsets import materialize_character_set
    from src.outputs.display_profile import display_profile_for_client

    charset = materialize_character_set({"id": "safe_profile", "extends": "led_3x5", "chars": list("012")})
    profile = display_profile_for_client(
        SimpleNamespace(
            plugin=SimpleNamespace(
                device_model=builtin_device_models()["divoom_pixoo64"], config={"block_padding": 0, "token": "private"}
            ),
            character_set=charset,
        )
    )
    description = profile.to_dict()
    assert description["block_padding"] == 0
    assert description["character_set"]["chars"] == list("012")
    assert "private" not in json.dumps(description)
    original_key = profile.key
    description["character_set"]["chars"].append("A")
    assert profile.key == original_key
    assert profile.check("A")
