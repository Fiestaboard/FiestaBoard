"""The split-flap extended-markup flip (plan Task 12, D16/D19; pairs with FiestaUI #336).

Before the flip only a board whose character set is rich (an LED set)
parsed extended markup. A split-flap board drew ``{red:HOT}`` as the
literal characters ``{RED:HOT}`` (braces as blanks), ``{icon:sun}`` as
``ICON:SUN``, and the legacy shortcuts as ASCII (``{sun}`` -> ``*``).

After it, every board parses extended markup and a split-flap board draws
the degradation FiestaUI's renderers now preview by default:

- a colour or block span draws its letters, uncoloured;
- an icon draws its registry fallback (a colour tile, a character or blank);
- a legacy shortcut is an alias of its icon (``{sun}`` is ``{icon:sun}``,
  a yellow tile); ``{heart}`` is the typed ``♥``, one cell where it was two.

Plain text (no shortcut, no extended-markup head) is byte-identical, and the
data-vs-markup rule is unchanged: a variable's value still cannot open a
span or an icon.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.board_chars import BoardChars
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.cells import extended_markup_kw, output_extended_markup, project_for_output, project_message
from src.templates.engine import TemplateEngine
from src.text_to_board import count_tiles, text_to_board_array, wrap_message_text

V1 = BUILTIN_CHARACTER_SETS["vestaboard_v1"]
V2 = BUILTIN_CHARACTER_SETS["vestaboard_v2"]

# What each shortcut draws on a split-flap board after the flip, as the 0-71
# code of its one cell. Spelled out (not read from the registry) so a registry
# change fails here and reaches the release notes.
SHORTCUT_FLAP = {
    "sun": 65,  # yellow tile (was "*")
    "star": 65,  # yellow tile (was "*")
    "cloud": 69,  # white tile (was "O")
    "rain": 67,  # blue tile (was "/")
    "snow": 68,  # violet tile (was "*")
    "storm": 64,  # orange tile, icon "bolt" (was "!")
    "fog": BoardChars.get_char_code("-"),  # "-", unchanged
    "partly": 69,  # white tile (was "%")
    "heart": 62,  # the code-62 flap, one cell (was "<3", two)
    "check": 66,  # green tile (was "+")
    "x": 63,  # red tile, icon "cross" (was "X")
}


@pytest.fixture
def engine():
    return TemplateEngine()


# --- the per-output rule ------------------------------------------------------------------


@pytest.mark.parametrize(
    "client",
    [
        SimpleNamespace(),  # a driver that names no set: split-flap
        SimpleNamespace(character_set=V1),
        SimpleNamespace(character_set=V2),
    ],
    ids=["no-set", "vestaboard_v1", "vestaboard_v2"],
)
def test_a_split_flap_output_speaks_extended_markup(client):
    assert output_extended_markup(client) is True
    # No keyword: the renderers' default is the split-flap mode, which is on,
    # so a split-flap board's render call keeps its shape.
    assert extended_markup_kw(client) == {}
    assert TemplateEngine().render("{icon:sun}{sun}", **extended_markup_kw(client)) == "{icon:sun}{icon:sun}"


def test_a_split_flap_board_draws_a_spans_letters_and_an_icons_fallback():
    grid, rich = project_for_output(SimpleNamespace(character_set=V2), "{red:HOT} {icon:sun}", 1, 22)
    assert grid[0][:5] == [BoardChars.get_char_code(c) for c in "HOT "] + [65]
    assert rich == {}  # a split-flap set gets no rich cells


def test_a_split_flap_block_span_draws_its_letters():
    frame = project_message("{black/white:OPEN}", 1, 22, None)
    assert frame.characters[0][:5] == [BoardChars.get_char_code(c) for c in "OPEN"] + [0]
    assert frame.cells is None


def test_text_to_board_array_parses_extended_markup_by_default():
    assert text_to_board_array("{icon:check}", rows=1, cols=3) == [[66, 0, 0]]


def test_count_tiles_measures_extended_markup_by_default():
    assert count_tiles("{red:HOT}{icon:sun}") == 4


# --- legacy shortcuts are icon aliases --------------------------------------------------------


@pytest.mark.parametrize("shortcut", sorted(SHORTCUT_FLAP))
def test_each_shortcut_draws_its_registry_fallback_on_a_split_flap(engine, shortcut):
    rendered = engine.render("{" + shortcut + "}")
    assert text_to_board_array(rendered, rows=1, cols=3)[0] == [SHORTCUT_FLAP[shortcut], 0, 0]


def test_ten_of_eleven_shortcuts_change_what_a_split_flap_draws(engine):
    legacy = TemplateEngine()
    changed = {
        s
        for s in SHORTCUT_FLAP
        if text_to_board_array(engine.render("{" + s + "}"), rows=1, cols=2)
        != text_to_board_array(
            legacy.render("{" + s + "}", extended_markup=False), rows=1, cols=2, extended_markup=False
        )
    }
    assert changed == set(SHORTCUT_FLAP) - {"fog"}


def test_heart_is_one_cell_where_it_was_two(engine):
    assert engine.render_lines(["{heart}A"], context={}).split("\n")[0].rstrip() == "♥A"


def test_a_line_with_shortcuts_is_measured_by_its_rendered_tiles(engine):
    # 22 tiles once each shortcut is one cell; the legacy "<3" made it 23 and cut the last letter.
    line = "{heart}" + "B" * 21
    assert engine.render_lines([line], context={}).split("\n")[0] == "♥" + "B" * 21


# --- every send path wraps by rendered tiles -----------------------------------------------------


def test_a_message_wraps_by_rendered_tiles_by_default():
    # 20 tiles of span + " B" fit a 22-column row; measured literally (27 chars) they wrapped.
    text = "{red:" + "A" * 20 + "} B"
    assert wrap_message_text(text, rows=2, cols=22) == text


def test_render_message_on_a_split_flap_board_draws_the_degradation():
    from unittest.mock import Mock

    from src.displays.messages import render_message

    target = Mock()
    target.render.return_value = (True, True)
    render_message(
        target, "{red:HOT} {icon:sun}", rows=1, cols=22, strategy=None, step_interval_ms=None, step_size=None
    )
    (grid,) = target.render.call_args.args
    assert grid[0][:5] == [BoardChars.get_char_code(c) for c in "HOT "] + [65]
    assert "cells" not in target.render.call_args.kwargs


# --- pages ------------------------------------------------------------------------------------


def test_a_page_preview_renders_extended_markup_and_is_cached(tmp_path):
    from src.pages.models import PageCreate
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    service = PageService(PageStorage(str(tmp_path / "pages.json")))
    page = service.create_page(PageCreate(name="Sun", type="template", template=["{sun} {{red:HOT}}"]))
    first = service.preview_page(page.id)
    assert first.formatted.startswith("{icon:sun} {red:HOT}")
    # The board's render is the cached render: one render serves both.
    assert service.preview_page(page.id, extended_markup=True) is first


# --- what does not change ---------------------------------------------------------------------------

# Plain text: no shortcut, no extended-markup head, at board or template level.
PLAIN_CORPUS = [
    "",
    "HELLO WORLD",
    "THIS IS A VERY LONG LINE THAT EXCEEDS THE BOARD WIDTH BY A LOT",
    "{red}HOT{/red} COLD{/} WARM {63}{64}{65}{66}{67}{68}{69}{70}{71}",
    "{{red}} ALERT {{blue}}{{green}} {{filled}}",
    "TEMP {{demo.short}}° F",
    "{{demo.long}}",
    "{{demo.tiles}} {{demo.braces}} {{demo.endtag}}",
    "LEFT{{fill_space}}RIGHT",
    "{{red}}{{fill_space_repeat:-}}{{red}}",
    "PRE {{demo.spaced|wrap}} POST",
    '{{= UPPER("formula") }}',
    "{center}CENTRED",
    "{right}RIGHTED",
    "{wrap}" + "WORD " * 12,
    "}}}} {{ }} { } {} {/} {sunny} {{sun}}",
    "a{b}c ~!@#$%^&*()_+-=[];':\",./<>? ♥ ° ❤",
    "SUPERCALIFRAGILISTICEXPIALIDOCIOUSLY LONGWORD",
]
PLAIN_CTX = {
    "demo": {
        "short": "72",
        "long": "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG AGAIN AND AGAIN",
        "tiles": "{63}{64}{65}",
        "braces": "a{b}c {red:x} {sun}",
        "spaced": "ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN",
        "endtag": "{red}HOT{/red}",
    }
}


@pytest.mark.parametrize("line", PLAIN_CORPUS)
@pytest.mark.parametrize(
    "device",
    [
        {"device_type": "flagship"},
        {"device_type": "note"},
        {"device_type": "note_array", "notes_wide": 2, "notes_tall": 1},
    ],
    ids=["flagship", "note", "note_array"],
)
def test_plain_text_renders_and_projects_byte_identically(engine, line, device):
    """The plain-text corpus: every render path and the 0-71 projection are
    byte-identical with the flip and without it."""
    from src.markup_compat import scan_text

    assert scan_text(line) == []  # the corpus really is plain
    for alignment in ("left", "center", "right"):
        for wrap in (False, True):
            meta = [{"alignment": alignment, "wrap": wrap}]
            new = engine.render_lines([line], PLAIN_CTX, line_metadata=meta, **device)
            old = engine.render_lines([line], PLAIN_CTX, line_metadata=meta, extended_markup=False, **device)
            assert new == old
            rows = len(new.split("\n"))
            assert text_to_board_array(new, rows=rows, cols=40) == text_to_board_array(
                old, rows=rows, cols=40, extended_markup=False
            )
    assert wrap_message_text(line, rows=6, cols=22) == wrap_message_text(line, rows=6, cols=22, extended_markup=False)
    assert engine.validate_template(line) == engine.validate_template(line, extended_markup=False)


def test_variable_values_stay_data(engine):
    ctx = {"demo": {"value": "{red:x} {sun} {icon:moon} {63}"}}
    rendered = engine.render("{{demo.value}}", ctx)
    assert rendered == "(red:x) (sun) (icon:moon) {63}"
    assert text_to_board_array(rendered, rows=1, cols=22) == text_to_board_array(
        rendered, rows=1, cols=22, extended_markup=False
    )
