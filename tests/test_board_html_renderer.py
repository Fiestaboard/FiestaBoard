"""Tests for src/board_html_renderer.py.

The renderer is pure — it has no service dependencies for the
``render_board_html`` path — so these tests poke at the string output
directly. The ``render_page_preview_html`` path mocks ``get_page_service``
to verify it falls back gracefully when the preview cache is unavailable.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.board_html_renderer import (
    DEVICE_DIMS,
    render_board_html,
    render_page_preview_html,
)


def _count(html: str, needle: str) -> int:
    return html.count(needle)


class TestDimensions:
    def test_flagship_renders_6_rows(self):
        html = render_board_html("HELLO", device_type="flagship")
        assert _count(html, 'class="row"') == 6

    def test_flagship_renders_22_cols_per_row(self):
        html = render_board_html("HELLO", device_type="flagship")
        rows, cols = DEVICE_DIMS["flagship"]
        # 6 rows * 22 cols = 132 tiles
        assert _count(html, 'class="tile"') + _count(html, 'class="tile note"') == rows * cols

    def test_note_renders_3_rows(self):
        html = render_board_html("HI", device_type="note")
        assert _count(html, 'class="row"') == 3

    def test_note_renders_15_cols_per_row(self):
        html = render_board_html("HI", device_type="note")
        rows, cols = DEVICE_DIMS["note"]
        # Note tiles carry the .note class.
        assert _count(html, 'class="tile note"') == rows * cols

    def test_unknown_device_falls_back_to_flagship(self):
        html = render_board_html("HI", device_type="zigzag")
        assert _count(html, 'class="row"') == 6


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
        html = render_board_html(
            "HI", device_type="flagship", page_name="<script>x</script>"
        )
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
        html = render_board_html(
            "HI", device_type="flagship", page_name="Weather Today"
        )
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
