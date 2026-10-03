"""Pages, renders and plugins at a FiestaPanel's per-character grid.

Unit-level companion to tests/test_panel_grid_e2e.py: the page model's
grid rules, the v4 -> v5 page migration, share strings, the plugin cache,
and the welcome message.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.devices import BoardContext
from src.pages.models import Page, PageCreate, PageUpdate, RowConfig
from src.pages.share import decode_page, encode_page
from src.pages.storage import CURRENT_SCHEMA_VERSION, MIGRATIONS


def _panel_page(**overrides) -> Page:
    fields = {
        "name": "Wall",
        "type": "template",
        "template": ["HI"],
        "device_type": "panel",
        "grid_rows": 12,
        "grid_cols": 29,
    }
    return Page(**{**fields, **overrides})


class TestPageModel:
    def test_a_panel_page_keeps_its_grid(self):
        page = _panel_page()
        assert (page.grid_rows, page.grid_cols) == (12, 29)

    def test_a_panel_page_needs_both_axes(self):
        with pytest.raises(ValidationError, match="grid_rows and grid_cols"):
            _panel_page(grid_cols=None)

    def test_creating_a_panel_page_needs_a_grid(self):
        with pytest.raises(ValidationError):
            PageCreate(name="x", type="template", template=["HI"], device_type="panel")

    def test_a_grid_below_one_note_is_rejected(self):
        with pytest.raises(ValidationError):
            _panel_page(grid_rows=2)

    def test_a_grid_above_the_maximum_is_rejected(self):
        with pytest.raises(ValidationError):
            _panel_page(grid_cols=129)

    def test_a_non_panel_page_drops_a_stale_grid(self):
        """A panel -> flagship retarget must not leave the grid behind."""
        page = Page(name="x", type="template", template=["HI"], device_type="flagship", grid_rows=12, grid_cols=29)
        assert (page.grid_rows, page.grid_cols) == (None, None)

    def test_composite_rows_are_bounded_by_the_panel_rows(self):
        page = _panel_page(
            type="composite",
            template=None,
            rows=[RowConfig(source="weather", row_index=0, target_row=12)],
        )
        assert any("exceeds max 11" in e for e in page.validate_config())

    def test_composite_rows_inside_the_panel_are_valid(self):
        page = _panel_page(
            type="composite",
            template=None,
            rows=[RowConfig(source="weather", row_index=0, target_row=11)],
        )
        assert page.validate_config() == []


class TestRetarget:
    def test_retargeting_to_a_panel_without_a_grid_is_refused(self, tmp_path):
        from src.pages.service import PageService
        from src.pages.storage import PageStorage

        service = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
        page = service.create_page(PageCreate(name="x", type="template", template=["HI"]))
        with pytest.raises(ValueError, match="Cannot retarget page"):
            service.update_page(page.id, PageUpdate(device_type="panel"))

    def test_retargeting_to_a_panel_with_a_grid_is_stored(self, tmp_path):
        from src.pages.service import PageService
        from src.pages.storage import PageStorage

        service = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
        page = service.create_page(PageCreate(name="x", type="template", template=["HI"]))
        updated = service.update_page(page.id, PageUpdate(device_type="panel", grid_rows=12, grid_cols=29))
        assert (updated.device_type, updated.grid_rows, updated.grid_cols) == ("panel", 12, 29)


class TestMigration:
    def _v5(self):
        return dict(MIGRATIONS)[5]

    def test_schema_is_version_5(self):
        assert CURRENT_SCHEMA_VERSION == 5

    def test_v4_pages_gain_null_grid_fields(self):
        pages = [{"id": "a", "device_type": "flagship"}, {"id": "b", "device_type": "note_array"}]
        assert self._v5()(pages) == 2
        assert all(p["grid_rows"] is None and p["grid_cols"] is None for p in pages)

    def test_the_migration_is_idempotent(self):
        pages = [{"id": "a", "grid_rows": None, "grid_cols": None}]
        assert self._v5()(pages) == 0

    def test_an_existing_grid_is_kept(self):
        pages = [{"id": "a", "device_type": "panel", "grid_rows": 12, "grid_cols": 29}]
        self._v5()(pages)
        assert (pages[0]["grid_rows"], pages[0]["grid_cols"]) == (12, 29)

    def test_a_v4_file_loads_and_saves_at_v5(self, tmp_path):
        import json

        from src.pages.storage import PageStorage

        path = tmp_path / "pages.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 4,
                    "pages": [
                        {
                            "id": "p1",
                            "name": "Old",
                            "type": "template",
                            "template": ["HI"],
                            "device_type": "flagship",
                            "notes_wide": 1,
                            "notes_tall": 1,
                        }
                    ],
                }
            )
        )
        storage = PageStorage(storage_file=str(path))
        assert storage.get("p1") is not None
        saved = json.loads(path.read_text())
        assert saved["schema_version"] == 5
        assert saved["pages"][0]["grid_rows"] is None


class TestShareStrings:
    def test_a_panel_page_round_trips_its_grid(self):
        decoded = decode_page(encode_page(_panel_page()))
        recreated = PageCreate(**{k: v for k, v in decoded.items() if k in PageCreate.model_fields})
        assert (recreated.device_type, recreated.grid_rows, recreated.grid_cols) == ("panel", 12, 29)

    def test_a_note_array_page_round_trips_its_notes(self):
        page = Page(name="x", type="template", template=["HI"], device_type="note_array", notes_wide=2, notes_tall=3)
        decoded = decode_page(encode_page(page))
        assert (decoded["notes_wide"], decoded["notes_tall"]) == (2, 3)


class TestPluginCache:
    def test_two_panel_sizes_do_not_share_a_cache_entry(self):
        from src.plugins.base import PluginBase

        key = PluginBase._cache_key
        assert key(BoardContext("panel", rows=12, cols=29)) != key(BoardContext("panel", rows=14, cols=34))

    def test_fixed_size_families_keep_their_plain_key(self):
        from src.plugins.base import PluginBase

        assert PluginBase._cache_key(BoardContext.from_device_type("flagship")) == "flagship"


class TestWelcome:
    def test_the_welcome_message_fills_a_panel_and_is_centred(self):
        from src.board_api.welcome import build_welcome_template

        rows = build_welcome_template("panel", "", grid_rows=12, grid_cols=29)
        assert len(rows) == 12
        text_rows = [i for i, r in enumerate(rows) if r.strip()]
        assert text_rows == [6], "one centred line, on the middle row"


class TestEngineRender:
    def test_a_template_renders_to_the_panel_width(self):
        from src.templates.engine import get_template_engine

        rendered = get_template_engine().render_lines(
            ["{{filled:-}}"], context={}, device_type="panel", grid_rows=7, grid_cols=17
        )
        lines = rendered.split("\n")
        assert len(lines) == 7
        assert lines[0] == "-" * 17


class TestClientRebuild:
    def test_a_panel_re_fit_changes_the_client_signature(self):
        """The engine keeps a board's client while its signature is unchanged;
        a re-fit only moves the grid, so the grid must be in the signature or
        the client keeps sending the old shape."""
        from src.main import DisplayService

        board = {"id": "p", "device_type": "panel", "api_mode": "virtual", "grid_rows": 12, "grid_cols": 29}
        resized = {**board, "grid_rows": 14, "grid_cols": 34}
        assert DisplayService._config_signature(board) != DisplayService._config_signature(resized)
