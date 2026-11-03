"""Schedule and active-page refusals say why a page can't show on a board.

Spec: docs/internal/superpowers/specs/2026-10-28-flexible-pages-design.md,
section 7, "Pages that still don't fit are flagged, not hidden": the refusal
carries the plain reason from :func:`src.pages.fit.page_fit_for_board`.
"""

from unittest.mock import MagicMock

import pytest

from src.collections.models import CollectionCreate
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.pages.models import PageCreate
from src.pages.service import PageService, check_ref_board_compatibility
from src.pages.storage import PageStorage
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401


@pytest.fixture
def services(monkeypatch, tmp_path):
    """Real page and collection services on temp storage; one 8x10 Pixoo at 5x7."""
    pages = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    collections = CollectionService(storage=CollectionStorage(storage_file=str(tmp_path / "collections.json")))
    settings = MagicMock()
    settings.get_board_settings.return_value.boards = [
        _board(grid_rows=8, grid_cols=10, output_config={"host": "192.0.2.50", "font": "5x7"})
    ]
    settings.get_primary_board_id.return_value = "pixoo-1"
    monkeypatch.setattr("src.pages.service.get_page_service", lambda: pages)
    monkeypatch.setattr("src.pages.service.get_settings_service", lambda: settings)
    monkeypatch.setattr("src.collections.service.get_collection_service", lambda: collections)
    return pages, collections


def _panel_page(pages: PageService, name: str, rows: int, cols: int) -> str:
    return pages.create_page(
        PageCreate(name=name, type="template", device_type="panel", grid_rows=rows, grid_cols=cols, template=["HI"])
    ).id


def test_a_flagship_page_on_a_pixoo_is_refused_with_the_reason(pixoo_output, services):  # noqa: F811
    pages, _ = services
    flagship_id = pages.create_page(PageCreate(name="Flag", type="template", template=["HI"])).id
    assert check_ref_board_compatibility(flagship_id, "pixoo-1").error.endswith("Made for a 6×22 board.")


# [RF3]
def test_a_collection_mixing_both_pixoo_sizes_fits_without_warnings(pixoo_output, services):  # noqa: F811
    pages, collections = services
    member_ids = [_panel_page(pages, "Big text", 10, 16), _panel_page(pages, "Small text", 8, 10)]
    mixed_collection_id = collections.create_collection(CollectionCreate(name="Both", page_ids=member_ids)).id
    result = check_ref_board_compatibility(mixed_collection_id, "pixoo-1")
    assert (result.error, result.warnings) == (None, [])
