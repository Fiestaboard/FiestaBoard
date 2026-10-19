"""Offline regression contracts for the MCP display and plugin audit."""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.ai.prompt_builder import build_prompt
from src.devices import BoardContext
from src.fiestaui import builtin_device_models
from src.led import LedLayoutOptions, layout_message, led_spec_for_model, rasterize
from src.led.charsets import materialize_character_set, resolve_character_set, validate_message
from src.markup import parse_line
from src.outputs.actions import describe_output
from src.outputs.display_profile import display_profile_for_client
from src.outputs.models import OutputSummary
from src.outputs.output_manifest import parse_output_block
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.registry import OutputDefinition, OutputRegistry
from src.plugins.base import PluginBase, PluginResult
from src.settings.service import BoardSettings


def _manifest(*, chars="0123456789", technology="split_flap", charset_id="audit_digits", builtin_model=None):
    """A valid plugin model and a non-builtin charset, accepted by core."""
    model = {
        "id": "audit_custom_model",
        "label": "Custom numeric display",
        "technology": technology,
        "family": "audit_vendor",
        "geometry": {"kind": "cells", "rows": 6, "cols": 22},
        "color": {"kind": "tiles"},
        "charset": "vestaboard_v1",
        "animation": {"delivery": "none", "maxFps": 0},
    }
    if technology == "led_matrix":
        model.update(
            geometry={"kind": "pixels", "width": 64, "height": 64},
            color={"kind": "rgb", "bitDepth": 24},
            font="3x5",
        )
    manifest, errors = parse_output_block(
        {
            "output_api": 1,
            "device_models": [builtin_model or model],
            "character_set": {
                "id": charset_id,
                "extends": "led_3x5" if technology == "led_matrix" else "vestaboard_v1",
                "chars": list(chars),
                "tiles": False,
                "mixedCase": False,
                "colorSpans": False,
                "blockSpans": False,
                "icons": [],
            },
            "delivery": "push",
            "min_interval_ms": 750,
            "read_back": {"supported": True, "cost": "network", "suggested_interval_s": 91},
            "write_timeout_ms": 1200,
        },
        base_dir=None,
        data_files=[],
    )
    assert errors == [] and manifest is not None, errors
    return manifest


def _driver(manifest, *, config=None):
    return SimpleNamespace(
        plugin=SimpleNamespace(device_model=manifest.model(), config=config or {}, board_geometry=(6, 22)),
        character_set=manifest.character_set,
    )


def _profile(manifest):
    profile = display_profile_for_client(_driver(manifest))
    assert profile is not None
    return profile


def _definition(manifest):
    return OutputDefinition(
        id="audit_output",
        name="Audit display",
        capabilities=manifest.capabilities,
        build=lambda _board: None,
        plugin=True,
        output_manifest=manifest,
        offered_device_models=manifest.device_model_ids,
        plugin_class=OutputPluginBase,
    )


class _CharsetAwareData(PluginBase):
    plugin_id = "charset_aware_audit"

    def fetch_data(self):
        return PluginResult(available=True, data={"text": self.board.display.chars})


def test_custom_numeric_declaration_is_accepted_and_direct_validation_rejects_letters():
    manifest = _manifest()
    profile = _profile(manifest)
    assert profile.chars == "0123456789" and not profile.tiles
    assert not profile.supports("lowercase") and not profile.supports("icons")
    assert validate_message("A", manifest.character_set).issues[0].fallback.value == " "
    assert validate_message("123", manifest.character_set).ok


def test_builtin_profile_check_still_reports_unsupported_lowercase():
    manifest = _manifest()
    driver = _driver(manifest)
    driver.character_set = resolve_character_set("vestaboard_v1")
    profile = display_profile_for_client(driver)
    assert profile.check("a")[0]["fallback"]["value"] == "A"


def test_profile_check_uses_the_accepted_custom_charset_document():
    manifest = _manifest()
    expected = validate_message("A", manifest.character_set).issues
    assert expected
    issues = _profile(manifest).check("A")
    assert issues and issues[0]["fallback"]["value"] == " ", issues


def test_two_plugin_scoped_charsets_with_equal_ids_do_not_share_cached_data():
    first = _profile(_manifest(chars="0123456789"))
    second = _profile(_manifest(chars="ABC"))
    assert first.chars != second.chars
    plugin = _CharsetAwareData({"id": "charset_aware_audit"})
    first_result = plugin.get_data(BoardContext("panel", rows=6, cols=22, display=first))
    second_result = plugin.get_data(BoardContext("panel", rows=6, cols=22, display=second))
    assert first_result.data == {"text": "0123456789"}
    assert second_result.data == {"text": "ABC"}, (first.key, second.key, second_result.data)


def test_profiles_distinguish_led_layouts_that_draw_different_block_pixels():
    model = builtin_device_models()["divoom_pixoo64"]
    charset = materialize_character_set({"id": "audit_led", "extends": "led_3x5"})
    spec = led_spec_for_model(model)
    frames = [
        rasterize(layout_message("{black/yellow:A}", spec, LedLayoutOptions(charset=charset, block_padding=p)))
        for p in (0, 1)
    ]
    assert frames[0].pixels != frames[1].pixels
    profiles = [
        display_profile_for_client(
            SimpleNamespace(
                plugin=SimpleNamespace(device_model=model, config={"block_padding": p}), character_set=charset
            )
        )
        for p in (0, 1)
    ]
    assert profiles[0].key != profiles[1].key, profiles


def test_outputs_wire_metadata_preserves_the_custom_device_model_document():
    manifest = _manifest(technology="led_matrix")
    wire = OutputSummary(**describe_output(_definition(manifest))).model_dump()
    model = wire["device_models"][0]
    assert model.get("geometry") == manifest.model()["geometry"], model
    assert model.get("color") == manifest.model()["color"], model
    assert model.get("animation") == manifest.model()["animation"], model


def test_outputs_wire_metadata_preserves_declared_transport_limits():
    manifest = _manifest()
    wire = OutputSummary(**describe_output(_definition(manifest))).model_dump()
    caps = wire["capabilities"]
    assert caps.get("min_interval_ms") == 750, caps
    assert caps.get("read_back") == {"supported": True, "cost": "network", "suggested_interval_s": 91}, caps
    assert caps.get("write_timeout_ms") == 1200, caps


def test_board_and_output_discovery_can_recover_a_declared_charset_override(monkeypatch):
    # A plugin may legitimately retain a builtin model while overriding its charset.
    manifest = _manifest(builtin_model="vestaboard_flagship")
    registry = OutputRegistry()
    registry.put_plugin(_definition(manifest))
    monkeypatch.setattr("src.outputs.registry.output_registry", lambda: registry)
    monkeypatch.setattr("src.outputs.board_profile.output_registry", lambda: registry)
    board = {
        "id": "custom-board",
        "name": "Numeric board",
        "output": "audit_output",
        "device_model": "vestaboard_flagship",
        "device_type": "panel",
        "grid_rows": 6,
        "grid_cols": 22,
        "output_config": {},
    }
    board_wire = BoardSettings._mask_board(board)
    output_wire = OutputSummary(**describe_output(_definition(manifest))).model_dump()
    assert board_wire["charset"] == "audit_digits"
    # No invented field name required: any discoverable copy of the document suffices.
    wire = json.dumps({"board": board_wire, "output": output_wire})
    assert '"chars"' in wire and '"mixedCase"' in wire, wire


def test_prompt_honors_a_valid_custom_split_flap_charset():
    profile = _profile(_manifest())
    context = build_prompt("Show only a number", "flagship", mode="chat", display=profile)
    assert "Vestaboards display only A-Z" not in context.system_prompt, context.system_prompt[:1800]


def test_prompt_does_not_advertise_markup_the_selected_custom_led_cannot_draw():
    manifest = _manifest(technology="led_matrix")
    profile = _profile(manifest)
    assert not any(profile.supports(feature) for feature in ("tiles", "icons", "color_text"))
    assert validate_message("{red} {red:HOT} {icon:sun}", manifest.character_set).issues
    context = build_prompt("Show a number", "flagship", mode="chat", display=profile)
    assert "`{{red}}`, `{{red:HOT}}` and `{{icon:sun}}` work too" not in context.system_prompt


def test_ai_brief_block_span_order_agrees_with_the_actual_markup_parser():
    model = builtin_device_models()["divoom_pixoo64"]
    charset = materialize_character_set({"id": "audit_led", "extends": "led_3x5"})
    profile = display_profile_for_client(
        SimpleNamespace(plugin=SimpleNamespace(device_model=model), character_set=charset)
    )
    token = parse_line("{yellow/black:A}", extended_markup=True, preserve_case=True)[0]
    assert (token.color, token.background) == ("yellow", "black")
    assert "{background/text colour:words}" not in profile.ai_brief(), profile.ai_brief()


def test_profile_check_does_not_silently_approve_an_unknown_charset():
    from src.outputs.display_profile import DisplayProfile

    issues = DisplayProfile(charset="unavailable_custom_charset").check("A")
    assert len(issues) == 1
    assert issues[0]["reason"] == "unknown_charset"
    assert "unavailable_custom_charset" in issues[0]["message"]
    assert issues[0]["fallback"] is None
