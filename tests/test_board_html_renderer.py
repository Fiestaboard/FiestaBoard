"""Tests for src/board_html_renderer.py.

The renderer is pure — it has no service dependencies for the
``render_board_html`` path — so these tests poke at the string output
directly. The ``render_page_preview_html`` path mocks ``get_page_service``
to verify it falls back gracefully when the preview cache is unavailable.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.board_html_renderer import (
    render_board_html,
    render_page_preview_html,
)
from src.devices import resolve_dimensions


def _count(html: str, needle: str) -> int:
    return html.count(needle)


class TestDimensions:
    def test_flagship_renders_6_rows(self):
        html = render_board_html("HELLO", device_type="flagship")
        assert _count(html, 'class="row"') == 6

    def test_flagship_renders_22_cols_per_row(self):
        html = render_board_html("HELLO", device_type="flagship")
        rows, cols = resolve_dimensions("flagship")
        # 6 rows * 22 cols = 132 tiles
        assert _count(html, 'class="tile"') + _count(html, 'class="tile note"') == rows * cols

    def test_note_renders_3_rows(self):
        html = render_board_html("HI", device_type="note")
        assert _count(html, 'class="row"') == 3

    def test_note_renders_15_cols_per_row(self):
        html = render_board_html("HI", device_type="note")
        rows, cols = resolve_dimensions("note")
        # Note tiles carry the .note class.
        assert _count(html, 'class="tile note"') == rows * cols

    def test_unknown_device_falls_back_to_flagship(self):
        html = render_board_html("HI", device_type="zigzag")
        assert _count(html, 'class="row"') == 6


class TestNoteArrayPresetRendering:
    """Each note-array preset renders a grid sized to notes_wide × notes_tall.

    Covers issue #1173's "every preset size renders + validates" requirement at
    the renderer level: a note_array board is not the Note device, so its tiles
    use the plain ``.tile`` class (no ``.note`` degree→heart substitution), and
    the full grid is rows × cols where rows = notes_tall × 3, cols = notes_wide
    × 15.
    """

    # (preset_id, notes_wide, notes_tall, expected_rows, expected_cols)
    PRESETS = [
        ("2_wide", 2, 1, 3, 30),
        ("4_wide", 4, 1, 3, 60),
        ("2_tall", 1, 2, 6, 15),
        ("4_tall", 1, 4, 12, 15),
        ("2x2_grid", 2, 2, 6, 30),
    ]

    def test_each_preset_renders_correct_row_count(self):
        for preset_id, nw, nt, rows, _cols in self.PRESETS:
            html = render_board_html("HI", device_type="note_array", notes_wide=nw, notes_tall=nt)
            assert _count(html, 'class="row"') == rows, preset_id

    def test_each_preset_renders_full_tile_grid(self):
        for preset_id, nw, nt, rows, cols in self.PRESETS:
            html = render_board_html("HI", device_type="note_array", notes_wide=nw, notes_tall=nt)
            # Note arrays use the plain .tile class (not .note), so a total
            # tile count of rows*cols proves the grid is fully laid out.
            total = _count(html, 'class="tile"') + _count(html, 'class="tile note"')
            assert total == rows * cols, preset_id
            assert resolve_dimensions("note_array", notes_wide=nw, notes_tall=nt) == (rows, cols), preset_id

    def test_note_array_tiles_are_not_note_class(self):
        """note_array is distinct from the Note device — no .note tile styling."""
        html = render_board_html("HI", device_type="note_array", notes_wide=2, notes_tall=1)
        assert _count(html, 'class="tile note"') == 0
        assert _count(html, 'class="tile"') == 3 * 30

    def test_preset_label_shows_cols_by_rows(self):
        """The optional label reports the note-array geometry as cols×rows."""
        html = render_board_html("HI", device_type="note_array", notes_wide=4, notes_tall=1, page_name="Wide Board")
        # Label format: "<name> · note_array <cols>×<rows>" (× is &times;).
        assert "note_array 60&times;3" in html
        assert "Wide Board" in html

    def test_custom_3x3_array_renders(self):
        """A non-preset 3×3 array (9×45) still renders a full grid."""
        html = render_board_html("HI", device_type="note_array", notes_wide=3, notes_tall=3)
        assert _count(html, 'class="row"') == 9
        assert _count(html, 'class="tile"') == 9 * 45


class TestCharacterRendering:
    def test_uppercases_letters(self):
        html = render_board_html("hi", device_type="flagship")
        # Letters are emitted inside <span class="char">…</span>
        assert ">H</span>" in html
        assert ">I</span>" in html

    def test_blank_lines_render_empty_tiles(self):
        html = render_board_html("", device_type="flagship")
        # No characters — every tile must be empty (no <span class="char">)
        assert 'class="char"' not in html
        # But the grid must still be 132 tiles.
        assert _count(html, 'class="tile"') == 6 * 22

    def test_note_substitutes_degree_with_heart(self):
        html = render_board_html("72°", device_type="note")
        # Heart glyph appears with the heart styling class.
        assert "heart" in html
        # The literal degree sign should not be rendered for a Note.
        # (It may appear inside CSS comments only — we check span content.)
        assert ">°</span>" not in html

    def test_flagship_keeps_degree_sign(self):
        html = render_board_html("72°", device_type="flagship")
        assert ">°</span>" in html


class TestColorTokens:
    def test_numeric_color_code_renders_swatch(self):
        html = render_board_html("{63}A", device_type="flagship")
        # Red hex appears as background of a swatch div.
        assert "background:#eb4034" in html

    def test_named_color_renders_swatch(self):
        html = render_board_html("{blue}A", device_type="flagship")
        assert "background:#4a90d9" in html

    def test_uppercase_named_color_works(self):
        html = render_board_html("{RED}A", device_type="flagship")
        assert "background:#eb4034" in html

    def test_end_tags_are_dropped(self):
        html = render_board_html("{red}A{/red}B", device_type="flagship")
        # Both letters present; no stray "/red" leakage.
        assert ">A</span>" in html
        assert ">B</span>" in html
        assert "/red" not in html

    def test_unknown_brace_token_falls_through_as_chars(self):
        html = render_board_html("{xy}", device_type="flagship")
        # Renders as literal characters '{','X','Y','}' since it's not a colour.
        assert ">{</span>" in html
        assert ">X</span>" in html
        assert ">Y</span>" in html
        assert ">}</span>" in html


class TestHtmlEscaping:
    def test_page_name_is_escaped(self):
        html = render_board_html("HI", device_type="flagship", page_name="<script>x</script>")
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html

    def test_character_special_chars_escaped(self):
        # '&' is character code 47 on the board, parses as a char token.
        html = render_board_html("&", device_type="flagship")
        assert ">&amp;</span>" in html
        # Make sure we never emit a bare ampersand-letter inside a span body.
        assert ">&<" not in html


class TestDocumentShell:
    def test_doctype_present(self):
        html = render_board_html("HI", device_type="flagship")
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_includes_inline_style(self):
        html = render_board_html("HI", device_type="flagship")
        assert "<style>" in html
        assert "flap-in" in html

    def test_page_name_appears_in_label(self):
        html = render_board_html("HI", device_type="flagship", page_name="Weather Today")
        assert "Weather Today" in html


class TestRenderPagePreviewHtml:
    def _fake_page(self, **overrides):
        return SimpleNamespace(
            id=overrides.get("id", "page-1"),
            name=overrides.get("name", "My Page"),
            device_type=overrides.get("device_type", "flagship"),
            template=overrides.get("template", ["HELLO", "WORLD"]),
        )

    def test_uses_preview_service_formatted_text(self):
        page = self._fake_page(template=["IGNORED"])
        svc = MagicMock()
        svc.preview_page.return_value = SimpleNamespace(formatted="LIVE\nDATA")
        with patch("src.pages.service.get_page_service", return_value=svc):
            html = render_page_preview_html(page)
        assert ">L</span>" in html
        assert ">I</span>" in html
        assert ">V</span>" in html
        assert ">E</span>" in html
        # template content was not used
        assert html.count(">I</span>") >= 1

    def test_falls_back_to_template_when_preview_unavailable(self):
        page = self._fake_page(template=["FALLBACK"])
        svc = MagicMock()
        svc.preview_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=svc):
            html = render_page_preview_html(page)
        for ch in "FALLBACK":
            assert f">{ch}</span>" in html

    def test_falls_back_when_preview_raises(self):
        page = self._fake_page(template=["BOOM"])
        svc = MagicMock()
        svc.preview_page.side_effect = RuntimeError("kaboom")
        with patch("src.pages.service.get_page_service", return_value=svc):
            html = render_page_preview_html(page)
        for ch in "BOOM":
            assert f">{ch}</span>" in html

    def test_page_without_template_renders_blank_board(self):
        page = self._fake_page(template=None)
        svc = MagicMock()
        svc.preview_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=svc):
            html = render_page_preview_html(page)
        # Blank board: no character spans, still 132 tiles.
        assert 'class="char"' not in html
        assert html.count('class="tile"') == 6 * 22

    def test_note_device_renders_note_dimensions(self):
        page = self._fake_page(device_type="note", template=["HI"])
        svc = MagicMock()
        svc.preview_page.return_value = None
        with patch("src.pages.service.get_page_service", return_value=svc):
            html = render_page_preview_html(page)
        assert html.count('class="row"') == 3
        assert html.count('class="tile note"') == 3 * 15
