"""Legacy symbol shortcuts as icon-registry aliases (plan D16), behind a flag.

``{sun}``, ``{cloud}``, ``{storm}``, ``{x}`` … are template shortcuts that
render today as ASCII stand-ins (``{sun}`` -> ``*``). D16 makes them aliases
of the icon registry, so ``{sun}`` means ``{icon:sun}``. ``{heart}`` stays the
typed ``♥`` (code 62). This is gated exactly like extended markup: with
``extended_markup`` off (the default and every caller today) the output is
byte-identical to before; the visible change ships only with the coordinated
v10 markup switch-over.
"""

from __future__ import annotations

import pytest

from src.markup import parse_line
from src.templates import engine as engine_module
from src.templates.engine import SYMBOL_CHARS, TemplateEngine
from src.text_to_board import text_to_board_array

# What every shortcut renders as today. Spelled out rather than read from
# SYMBOL_CHARS, so a change to that table fails here instead of passing along.
LEGACY_OUTPUT = {
    "sun": "*",
    "star": "*",
    "cloud": "O",
    "rain": "/",
    "snow": "*",
    "storm": "!",
    "fog": "-",
    "partly": "%",
    "heart": "<3",
    "check": "+",
    "x": "X",
}

# Shortcut -> registry icon (canonical name), or the typed character for heart.
EXTENDED_OUTPUT = {
    "sun": "{icon:sun}",
    "star": "{icon:star}",
    "cloud": "{icon:cloud}",
    "rain": "{icon:rain}",
    "snow": "{icon:snow}",
    "storm": "{icon:bolt}",
    "fog": "{icon:fog}",
    "partly": "{icon:partly}",
    "heart": "♥",
    "check": "{icon:check}",
    "x": "{icon:cross}",
}


@pytest.fixture
def engine():
    return TemplateEngine()


def test_the_tables_cover_every_shortcut():
    assert set(LEGACY_OUTPUT) == set(SYMBOL_CHARS) == set(EXTENDED_OUTPUT)


@pytest.mark.parametrize("shortcut", sorted(LEGACY_OUTPUT))
def test_shortcut_renders_its_legacy_ascii_by_default(engine, shortcut):
    assert engine.render(f"A{{{shortcut}}}B", context={}) == f"A{LEGACY_OUTPUT[shortcut]}B"


@pytest.mark.parametrize("shortcut", sorted(LEGACY_OUTPUT))
def test_shortcut_renders_its_legacy_ascii_with_extended_markup_off(engine, shortcut):
    rendered = engine.render(f"A{{{shortcut.upper()}}}B", context={}, extended_markup=False)
    assert rendered == f"A{LEGACY_OUTPUT[shortcut]}B"


@pytest.mark.parametrize("shortcut", sorted(EXTENDED_OUTPUT))
def test_shortcut_resolves_through_the_icon_registry_with_extended_markup(engine, shortcut):
    assert engine.render(f"A{{{shortcut}}}B", context={}, extended_markup=True) == f"A{EXTENDED_OUTPUT[shortcut]}B"


def test_shortcut_case_is_ignored_with_extended_markup(engine):
    assert engine.render("{SUN}{Storm}", context={}, extended_markup=True) == "{icon:sun}{icon:bolt}"


def test_sun_shortcut_is_a_yellow_tile_on_a_split_flap_with_extended_markup(engine):
    rendered = engine.render("{sun} 72", context={}, extended_markup=True)
    assert text_to_board_array(rendered, rows=1, cols=4, extended_markup=True) == [[65, 0, 33, 28]]


def test_sun_shortcut_is_an_icon_token_for_rich_outputs(engine):
    rendered = engine.render("{sun}", context={}, extended_markup=True)
    assert [t.to_dict() for t in parse_line(rendered, extended_markup=True)] == [
        {"type": "color", "code": "65", "icon": "sun"}
    ]


def test_heart_shortcut_is_code_62_with_extended_markup(engine):
    rendered = engine.render("{heart}", context={}, extended_markup=True)
    assert text_to_board_array(rendered, rows=1, cols=1, extended_markup=True) == [[62]]


def test_shortcut_without_a_registry_icon_keeps_its_legacy_ascii(engine, monkeypatch):
    real = engine_module.resolve_icon_name
    monkeypatch.setattr(engine_module, "resolve_icon_name", lambda name: None if name == "fog" else real(name))
    assert engine.render("{fog}{sun}", context={}, extended_markup=True) == "-{icon:sun}"
