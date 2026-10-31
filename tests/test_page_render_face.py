"""Rendering a grid page at a given LED face (text size) other than the board's.

A page made for a grid the board reaches only at another text size renders as
if the board were set to that size: its template, plugin context and canvases
all use :func:`~src.outputs.display_profile.display_for_face`. The result
records the face, and its content key moves with it.
"""

from __future__ import annotations

import pytest

from src.displays.service import DisplayResult
from src.outputs.display_profile import display_for_face, display_profile_for_board
from src.pages.models import Page, PageCreate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401

CANVAS = {"id": "c", "area": {"row": 1, "col": 1, "rows": 1, "cols": 2}, "content": {"background": "#ff0000"}}


@pytest.fixture
def service(tmp_path):
    return PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))


@pytest.fixture
def pixoo_5x7(pixoo_output):  # noqa: F811
    """The 5x7 Pixoo 64 profile (8 x 10), the way the board itself resolves it."""
    return display_profile_for_board(_board(grid_rows=8, grid_cols=10, output_config={"font": "5x7"}))


def _page(rows=10, cols=16, *, canvases=None, device_type="panel") -> Page:
    return Page(
        name=f"{rows}x{cols}",
        type="template",
        template=["HELLO"],
        canvases=canvases,
        device_type=device_type,
        grid_rows=rows,
        grid_cols=cols,
    )


def test_a_face_render_places_canvases_on_that_faces_grid(service, pixoo_5x7):
    r = service.render_page(_page(canvases=[CANVAS]), context={}, display=pixoo_5x7, face="3x5")
    assert r.face == "3x5" and [(lay.x, lay.y, lay.w, lay.h) for lay in r.layers] == [(0, 2, 7, 5)]


def test_plugins_are_fetched_for_the_face_display(service, pixoo_5x7):
    contexts: dict = {}
    service.render_page(_page(), contexts=contexts, display=pixoo_5x7, face="3x5")
    assert any(k.endswith(display_for_face(pixoo_5x7, "3x5", (10, 16)).key) for k in contexts)


def test_the_content_key_moves_with_the_face():
    a = DisplayResult("page", "HI", {}, True)
    b = DisplayResult("page", "HI", {}, True, face="3x5")
    assert a.content_key() != b.content_key() and a.content_key() == "HI"


def test_a_face_is_ignored_off_a_pixel_display(service):
    flagship_page = _page(6, 22, device_type="flagship")
    assert service.render_page(flagship_page, context={}, face="3x5").face is None


def _stored(service, rows, cols) -> Page:
    return service.create_page(
        PageCreate(
            name=f"{rows}x{cols}",
            type="template",
            template=["HELLO"],
            device_type="panel",
            grid_rows=rows,
            grid_cols=cols,
        )
    )


def test_the_batch_renders_each_page_at_its_own_face(service, pixoo_5x7):
    p10x16 = _stored(service, 10, 16)
    p8x10 = _stored(service, 8, 10)
    out = service.preview_pages_batch([p10x16.id, p8x10.id], display=pixoo_5x7, faces={p10x16.id: "3x5"})
    assert (out[p10x16.id].face, out[p8x10.id].face) == ("3x5", None)


def test_a_preview_forwards_the_face(service, pixoo_5x7):
    page = _stored(service, 10, 16)
    assert service.preview_page(page.id, display=pixoo_5x7, face="3x5").face == "3x5"
