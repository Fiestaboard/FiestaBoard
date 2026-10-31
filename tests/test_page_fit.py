"""The fit rule for grid pages: whether a page shows on a board, at which
text size (face), and why not when it doesn't."""

from src.pages.fit import PageFit, page_fit_for_board
from src.pages.models import Page
from tests.test_led_text_size import _board, declared_set_output, pixoo_output  # noqa: F401


def _page(device_type: str, grid_rows: int | None = None, grid_cols: int | None = None) -> Page:
    return Page(
        name="Page",
        type="template",
        device_type=device_type,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        template=["HI"],
    )


def test_a_page_at_the_boards_own_grid_takes_todays_path(pixoo_output):  # noqa: F811
    assert page_fit_for_board(_page("panel", 10, 16), _board(output_config={"font": "3x5"})) == PageFit(
        True, None, None
    )


def test_a_page_at_the_other_text_size_fits_at_that_face(pixoo_output):  # noqa: F811
    board = _board(grid_rows=8, grid_cols=10, output_config={"font": "5x7"})
    assert page_fit_for_board(_page("panel", 10, 16), board) == PageFit(True, "3x5", None)


def test_a_flagship_page_on_a_pixoo_is_flagged_with_a_reason(pixoo_output):  # noqa: F811
    assert page_fit_for_board(_page("flagship"), _board()) == PageFit(False, None, "Made for a 6×22 board")


def test_a_panel_page_on_a_flagship_is_flagged(pixoo_output):  # noqa: F811
    fit = page_fit_for_board(_page("panel", 10, 16), {"id": "v", "device_type": "flagship"})
    assert (fit.fits, fit.reason) == (False, "Made for a 10×16 board")


def test_a_note_page_never_fits_a_one_by_one_note_array():
    assert not page_fit_for_board(_page("note"), {"id": "a", "device_type": "note_array"}).fits


def test_a_fixed_face_output_keeps_exact_fit(declared_set_output):  # noqa: F811
    assert not page_fit_for_board(_page("panel", 8, 10), _board()).fits


def test_a_page_passed_as_the_board_uses_the_exact_rule():
    assert page_fit_for_board(_page("flagship"), _page("flagship")).fits


# [RF1]
def test_a_legacy_board_without_a_stored_face_fits_the_other_size(pixoo_output):  # noqa: F811
    board = _board(output_config={"host": "192.0.2.50"})  # 10x16, no font key
    assert page_fit_for_board(_page("panel", 8, 10), board) == PageFit(True, "5x7", None)


# [RF2]
def test_a_board_whose_output_is_not_installed_falls_back_to_exact_fit():
    board = _board(output="not_installed")
    assert page_fit_for_board(_page("panel", 8, 10), board) == PageFit(False, None, "Made for a 8×10 board")
