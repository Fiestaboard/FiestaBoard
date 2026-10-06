"""What a display can draw, as data plugins see it (``self.board.display``).

The profile is built from what the output plugin declares (FiestaUI device
model + character set), so these tests use the real built-in models: a Divoom
Pixoo 64 (full-colour LED, lowercase, coloured text, backgrounds, icons) and a
Vestaboard Flagship (split-flap: capitals and colour tiles only).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.devices import BoardContext, board_context_for
from src.fiestaui import builtin_device_models
from src.led.charsets import resolve_character_set
from src.outputs.display_profile import (
    DisplayProfile,
    display_profile_for_client,
    render_kw,
)
from src.plugins.base import PluginBase

PIXOO = builtin_device_models()["divoom_pixoo64"]
FLAGSHIP = builtin_device_models()["vestaboard_flagship"]


def _driver(model, charset_id=None, config=None):
    """A stand-in output driver: what the render path reads off a board's client."""
    plugin = SimpleNamespace(device_model=model, config=config or {})
    charset = resolve_character_set(charset_id) if charset_id else None
    return SimpleNamespace(plugin=plugin, character_set=charset)


def _pixoo(tile_gap=None):
    return display_profile_for_client(_driver(PIXOO, "led_3x5", {"tile_gap": tile_gap} if tile_gap else {}))


def _flagship():
    return display_profile_for_client(_driver(FLAGSHIP))


# ── the profile says what the output plugin declares ─────────────────────────


def test_a_pixoo_is_a_full_colour_led_with_lowercase_coloured_text_backgrounds_and_icons():
    profile = _pixoo()
    assert (profile.technology, profile.device_model, profile.charset, profile.color) == (
        "led_matrix",
        "divoom_pixoo64",
        "led_3x5",
        "rgb",
    )
    assert profile.mixed_case and profile.color_spans and profile.block_spans and profile.tiles
    assert "sun" in profile.icons and "a" in profile.chars


def test_a_flagship_is_a_split_flap_with_capitals_and_tiles_only():
    profile = _flagship()
    assert (profile.technology, profile.color) == ("split_flap", "tiles")
    assert not (profile.mixed_case or profile.color_spans or profile.block_spans)
    assert profile.icons == () and profile.tile_gap is None


def test_the_led_tile_style_is_the_one_the_device_is_drawn_with():
    assert _pixoo().tile_gap == "gap"  # the model's default
    assert _pixoo("fill").tile_gap == "fill"
    assert _pixoo("fill").supports("solid_shapes") and not _pixoo("gap").supports("solid_shapes")


def test_supports_answers_each_feature_and_refuses_an_unknown_one():
    pixoo, flagship = _pixoo(), _flagship()
    for feature in ("lowercase", "color_text", "background", "icons", "rgb"):
        assert pixoo.supports(feature) and not flagship.supports(feature)
    assert pixoo.supports("tiles") and flagship.supports("tiles")
    with pytest.raises(ValueError, match="Unknown display feature"):
        pixoo.supports("holograms")


def test_a_driver_that_does_not_describe_its_device_has_no_profile():
    assert display_profile_for_client(SimpleNamespace()) is None
    assert "display" not in render_kw(SimpleNamespace())


def test_render_kw_carries_the_profile_beside_extended_markup():
    kw = render_kw(_driver(PIXOO, "led_3x5"))
    assert kw["display"] == _pixoo() and kw["extended_markup"] is True


# ── ai_brief: one generated description of the markup a board draws ──────────


def test_an_led_brief_teaches_lowercase_coloured_text_highlights_and_its_icons():
    brief = _pixoo("fill").ai_brief()
    assert "full-colour LED" in brief
    assert "sentence case" in brief
    assert "{green:63F}" in brief and "#rrggbb" in brief
    assert "{yellow/black:" in brief
    assert "{icon:name}" in brief and "sun" in brief
    assert "join into one solid shape" in brief


def test_a_split_flap_brief_keeps_the_vestaboard_rules_and_offers_nothing_it_cannot_draw():
    brief = _flagship().ai_brief()
    assert "split-flap" in brief and "CAPITALS" in brief
    assert "{green:63F}" not in brief and "{icon:" not in brief and "solid shape" not in brief


# ── check: the same validation the template editor warns with ────────────────


def test_check_reports_what_the_display_cannot_draw_and_passes_what_it_can():
    assert _pixoo().check("{green:Night walk} {icon:sun}") == []
    assert _flagship().check("NIGHT WALK") == []
    lowercase = _flagship().check("walk")  # a flap has no lowercase: each letter falls back to its capital
    assert [i["fallback"]["value"] for i in lowercase] == ["W", "A", "L", "K"]
    assert {"row", "col", "reason", "fallback"} <= set(lowercase[0])


# ── one size, two displays: never one cache entry ────────────────────────────


def test_a_board_context_without_a_display_keeps_its_old_cache_key():
    board = board_context_for("panel", grid_rows=10, grid_cols=16)
    assert board.display is None
    assert PluginBase._cache_key(board) == "panel:16x10"


def test_two_displays_of_one_size_never_share_a_plugin_cache_entry():
    led = BoardContext("panel", rows=10, cols=16, display=_pixoo())
    flap = BoardContext("panel", rows=10, cols=16, display=_flagship())
    plain = BoardContext("panel", rows=10, cols=16)
    keys = {PluginBase._cache_key(b) for b in (led, flap, plain)}
    assert len(keys) == 3


# ── the render path hands the display to the plugins ─────────────────────────


class _RecordingRegistry:
    def __init__(self):
        self.boards: list[BoardContext] = []
        self.trigger_plugins: dict = {}

    def build_template_context(self, board=None, plugin_ids=None, fingerprints=None):
        self.boards.append(board)
        return {}


def test_a_shared_context_for_a_display_passes_it_to_the_plugins_and_keeps_its_own_entry(monkeypatch):
    from src.pages.service import PageService

    registry = _RecordingRegistry()
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: registry)
    service = PageService.__new__(PageService)
    contexts: dict = {}
    service.shared_context_for(contexts, "panel", grid_rows=10, grid_cols=16, display=_pixoo())
    service.shared_context_for(contexts, "panel", grid_rows=10, grid_cols=16)
    assert [b.display for b in registry.boards] == [_pixoo(), None]
    sizes = [k for k in contexts if not k.startswith("\x00")]
    assert len(sizes) == 2, "a display-specific context shared the plain one's entry"


def test_a_preview_for_a_display_neither_reads_nor_writes_the_shared_preview_cache(monkeypatch):
    from src.pages.service import PageService

    service = PageService.__new__(PageService)
    page = SimpleNamespace(id="p1", updated_at="t")
    service._preview_cache = {"p1": SimpleNamespace(is_valid=lambda _p: True, result="SHARED")}
    monkeypatch.setattr(service, "get_page", lambda _id: page, raising=False)
    rendered = []
    monkeypatch.setattr(
        service, "render_page", lambda *a, **kw: rendered.append(kw.get("display")) or "FOR-DISPLAY", raising=False
    )
    assert service.preview_page("p1", display=_pixoo()) == "FOR-DISPLAY"
    assert rendered == [_pixoo()]
    assert service._preview_cache["p1"].result == "SHARED"
    assert service.preview_page("p1") == "SHARED"  # the display-agnostic render is unchanged
