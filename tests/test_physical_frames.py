"""Physical flexible frames require explicit versioned adapter support."""

import pytest

from src.outputs.output_manifest import parse_output_block


def declaration(**overrides):
    return {
        "version": 1,
        "models": {"divoom_pixoo64": {"width": 64, "height": 64, "modes": ["ordinary"]}},
        **overrides,
    }


def parse(**overrides):
    return parse_output_block(
        {"output_api": 2, "device_models": ["divoom_pixoo64"], **overrides}, base_dir=None, data_files=[]
    )


def test_api_two_declares_a_physical_surface_without_changing_legacy_geometry():
    manifest, errors = parse(physical_frames=declaration())
    assert errors == []
    surface = manifest.capabilities.physical_frames["divoom_pixoo64"]
    assert (surface.width, surface.height, surface.modes) == (64, 64, frozenset({"ordinary"}))
    assert manifest.model()["geometry"] == {"kind": "pixels", "width": 64, "height": 64}


def test_legacy_output_has_no_implicit_physical_frame_promise():
    manifest, errors = parse(output_api=1)
    assert errors == []
    assert manifest.capabilities.physical_frames == {}


@pytest.mark.parametrize(
    "value",
    [
        declaration(version=2),
        declaration(models={"unknown": {"width": 64, "height": 64, "modes": ["ordinary"]}}),
        declaration(models={"divoom_pixoo64": {"width": True, "height": 64, "modes": ["ordinary"]}}),
        declaration(models={"divoom_pixoo64": {"width": 64, "height": 64, "modes": ["guess"]}}),
        declaration(models={"divoom_pixoo64": {"width": 64, "height": 64, "modes": []}}),
    ],
)
def test_invalid_physical_contract_is_refused(value):
    manifest, errors = parse(physical_frames=value)
    assert manifest is None
    assert any("physical_frames" in error for error in errors)


def test_physical_contract_requires_the_new_output_api_major():
    manifest, errors = parse(output_api=1, physical_frames=declaration())
    assert manifest is None
    assert any("output_api 2" in error for error in errors)


def test_physical_marker_keeps_exact_mono_rgb_separate_from_preview_encoding():
    from src.led.matrix import LedFrame
    from src.led.page_frame import full_frame_layer
    from src.outputs import physical_frames
    from src.outputs.cells import RichCells, cells_from_codes
    from src.outputs.native_playlist import NativePlaylistEntry

    make = getattr(physical_frames, "physical_frame_layer", None)
    assert callable(make), "physical payloads need an explicit marker rather than inferred dimensions"
    frame = LedFrame(2, 1, b"\x10\x20\x00\x00\x00\x00")
    layer = make(frame, monochrome="#102000")
    cells = RichCells(cells_from_codes([[0]]), layers=(layer,))
    assert layer.to_json() == {**full_frame_layer(frame, monochrome="#102000").to_json(), "physical_frame_version": 1}
    assert physical_frames.physical_frame_pixels(cells, 2, 1) == frame.pixels
    copied = NativePlaylistEntry("flex", cells, 1000).cells
    assert physical_frames.physical_frame_pixels(copied, 2, 1) == frame.pixels
    legacy = RichCells(cells_from_codes([[0]]), layers=(full_frame_layer(frame),))
    assert physical_frames.physical_frame_pixels(legacy, 2, 1) is None
    with pytest.raises(ValueError, match="surface"):
        physical_frames.physical_frame_pixels(cells, 2, 2)


def test_dedupe_distinguishes_physical_payloads_even_when_preview_pixels_match():
    from src.displays.service import DisplayResult
    from src.led.matrix import LedFrame
    from src.led.page_frame import full_frame_layer
    from src.outputs.physical_frames import physical_frame_layer

    dim = LedFrame(1, 1, b"\x01\x02\x00")
    brighter = LedFrame(1, 1, b"\x10\x20\x00")
    a = DisplayResult("page:flexible", "", {}, True, layers=[physical_frame_layer(dim, monochrome="#010200")])
    b = DisplayResult("page:flexible", "", {}, True, layers=[physical_frame_layer(brighter, monochrome="#102000")])
    legacy = DisplayResult("page:template", "", {}, True, layers=[full_frame_layer(dim, monochrome="#010200")])
    assert a.layers[0].rgba == b.layers[0].rgba == legacy.layers[0].rgba
    assert len({a.content_key(), b.content_key(), legacy.content_key()}) == 3


@pytest.mark.parametrize("declared", [False, True])
def test_flexible_render_requires_and_uses_the_declared_physical_surface(tmp_path, monkeypatch, declared):
    from dataclasses import replace

    from src.led.charsets import BUILTIN_CHARACTER_SETS
    from src.outputs.display_profile import display_profile_for_client
    from src.outputs.physical_frames import PhysicalSurface
    from src.outputs.plugin_driver import OutputPluginDriver
    from src.pages.service import PageService
    from src.pages.storage import PageStorage
    from tests.layout.test_flexible_call_sites import red_band
    from tests.test_routes_page_face import PIXOO_5X7, Sign

    model = {
        **PIXOO_5X7,
        "id": "fixture_virtual_52",
        "font": "3x5",
        "geometry": {"kind": "pixels", "width": 52, "height": 17},
    }
    plugin = Sign()
    plugin.bind_board(device_model=model, character_set=BUILTIN_CHARACTER_SETS["led_3x5"], geometry=(3, 13))
    capabilities = plugin.capabilities()
    surfaces = {model["id"]: PhysicalSurface(52, 16, frozenset({"ordinary", "native"}))} if declared else {}
    monkeypatch.setattr(plugin, "capabilities", lambda: replace(capabilities, physical_frames=surfaces))
    display = display_profile_for_client(OutputPluginDriver(plugin, character_set=plugin.character_set))
    assert (display.width, display.height) == (52, 17), "legacy geometry must remain unchanged"
    service = PageService(storage=PageStorage(tmp_path / "pages.json"))
    result = service.render_page(
        red_band(),
        context={},
        display=display,
        board={"id": "fixture", "device_type": "panel", "grid_rows": 3, "grid_cols": 13},
    )
    if not declared:
        assert result.available is False
        assert "physical" in result.error.lower()
    else:
        assert result.available
        assert (result.layers[0].w, result.layers[0].h) == (52, 16)
        assert len(result.formatted.splitlines()) == 3
        assert result.raw["surface"] == {"kind": "pixels", "width": 52, "height": 16}


@pytest.mark.parametrize(
    "declared_mode,native,allowed", [("native", False, False), ("native", True, True), (None, True, False)]
)
def test_delivery_requires_the_current_models_explicit_mode(monkeypatch, declared_mode, native, allowed):
    from dataclasses import replace

    from src.displays.service import DisplayResult
    from src.led.matrix import LedFrame
    from src.outputs.physical_frames import PhysicalSurface, physical_frame_layer
    from src.outputs.plugin_driver import OutputPluginDriver
    from src.pages.board_render import flexible_frame_error
    from tests.layout.test_flexible_call_sites import red_band
    from tests.test_native_playlist import NativeSign
    from tests.test_routes_page_face import LED_5X7, PIXOO_5X7

    plugin = NativeSign()
    plugin.bind_board(device_model=PIXOO_5X7, character_set=LED_5X7, geometry=(8, 10))
    caps = plugin.capabilities()
    surfaces = {PIXOO_5X7["id"]: PhysicalSurface(64, 64, frozenset({declared_mode}))} if declared_mode else {}
    monkeypatch.setattr(plugin, "capabilities", lambda: replace(caps, physical_frames=surfaces))
    driver = OutputPluginDriver(plugin, character_set=LED_5X7)
    result = DisplayResult(
        "page:flexible", "", {}, True, layers=[physical_frame_layer(LedFrame(64, 64, bytes(64 * 64 * 3)))]
    )
    error = flexible_frame_error(red_band(), result, driver, native=native)
    assert (error is None) is allowed


@pytest.mark.parametrize("declared", [False, True])
def test_fit_gates_flexible_pixels_without_affecting_legacy_grid_pages(monkeypatch, declared):
    from dataclasses import replace

    from src.outputs.physical_frames import PhysicalSurface
    from src.pages.fit import page_fit_for_board
    from src.pages.models import Page
    from tests.layout.devices import profile
    from tests.layout.test_flexible_call_sites import red_band

    display = replace(profile("divoom_pixoo64", "3x5"), physical_surface=None)
    if declared:
        display = replace(display, physical_surface=PhysicalSurface(64, 64, frozenset({"ordinary"})))
    monkeypatch.setattr("src.outputs.display_profile.display_profile_for_board", lambda _: display)
    board = {"id": "fixture", "device_type": "panel", "grid_rows": 10, "grid_cols": 16}
    assert page_fit_for_board(red_band(), board).fits is declared
    legacy = Page(name="Legacy", type="template", device_type="panel", grid_rows=10, grid_cols=16, template=["HELLO"])
    assert page_fit_for_board(legacy, board).fits


def test_leaving_a_physical_frame_never_uses_per_cell_transition():
    from src.led.matrix import LedFrame
    from src.outputs.cells import RichCells, cells_from_codes
    from src.outputs.physical_frames import physical_frame_layer
    from src.outputs.plugin_driver import OutputPluginDriver
    from tests.test_routes_page_face import LED_5X7, PIXOO_5X7, Sign

    plugin = Sign()
    model = {**PIXOO_5X7, "geometry": {"kind": "pixels", "width": 52, "height": 17}}
    plugin.bind_board(device_model=model, character_set=LED_5X7, geometry=(3, 13))
    driver = OutputPluginDriver(plugin, character_set=LED_5X7)
    before = RichCells(cells_from_codes([[0]]), layers=(physical_frame_layer(LedFrame(52, 16, bytes(52 * 16 * 3))),))
    after = cells_from_codes([[1]])
    transition = driver.resolve_transition("flip")
    assert transition.id == "flip"
    assert driver._transition_around_full_frame(transition, before, after).id not in {"flip", "cascade"}


def test_public_declaration_revision_tracks_physical_contract():
    from dataclasses import replace

    from src.outputs.actions import describe_output
    from src.outputs.physical_frames import PhysicalSurface
    from src.outputs.registry import OutputDefinition

    manifest, errors = parse(physical_frames=declaration())
    assert not errors
    definition = OutputDefinition("fixture", "Fixture", manifest.capabilities, lambda _: None, output_manifest=manifest)
    first = describe_output(definition)
    assert first["capabilities"]["physical_frames"]["divoom_pixoo64"]["height"] == 64
    changed = replace(
        definition,
        capabilities=replace(
            definition.capabilities,
            physical_frames={"divoom_pixoo64": PhysicalSurface(64, 32, frozenset({"ordinary"}))},
        ),
    )
    assert describe_output(changed)["declaration_revision"] != first["declaration_revision"]


def test_board_settings_carries_effective_physical_surface(monkeypatch):
    from src.settings.service import BoardSettings
    from tests.layout.devices import profile

    monkeypatch.setattr("src.outputs.display_profile.display_profile_for_board", lambda _: profile("divoom_pixoo64"))
    board = {
        "id": "fixture",
        "device_type": "panel",
        "grid_rows": 10,
        "grid_cols": 16,
        "output": "unknown",
        "output_config": {},
        "device_model": "divoom_pixoo64",
    }
    view = BoardSettings._mask_board(board)
    assert view["physical_surface"] == {"version": 1, "width": 64, "height": 64, "modes": ["native", "ordinary"]}
    assert "physical_surface" not in board


def test_board_reports_cell_only_flexible_support_for_integer_pixel_output(monkeypatch):
    from dataclasses import replace

    from src.settings.service import BoardSettings
    from tests.layout.devices import profile

    display = replace(profile("divoom_pixoo64"), width=None, height=None, physical_surface=None)
    monkeypatch.setattr("src.outputs.display_profile.display_profile_for_board", lambda _: display)
    board = {"id": "fixture", "device_type": "panel", "output": "unknown", "output_config": {}}
    view = BoardSettings._mask_board(board)
    assert view["flexible_page_support"] == "cells"
    assert "physical_surface" not in view


def test_layer_wire_schema_preserves_marker_and_omits_it_for_legacy():
    from src.canvas.schemas import CanvasLayerModel

    legacy = {"x": 0, "y": 0, "width": 1, "height": 1, "rgba": "AAAA/w=="}
    assert CanvasLayerModel.model_validate(legacy).model_dump() == legacy
    physical = {**legacy, "physical_frame_version": 1}
    assert CanvasLayerModel.model_validate(physical).model_dump() == physical
