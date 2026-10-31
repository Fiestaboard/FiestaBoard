"""Flexible pages fit every board, unless their ``targets`` exclude it (spec section 7).

A flexible page has no grid, so the grid fit rule (size keys, producible
grids, text size) never applies to it. Only ``targets`` narrows where it shows.
"""

from src.devices import pages_compatible_with_board
from src.pages.fit import PageFit, board_technology, page_fit_for_board
from src.pages.flexible import FlexTargets
from src.pages.models import Page
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401

FLEX_PAGE = Page.model_validate(
    {"name": "Morning", "type": "flexible", "blocks": [{"id": "b1", "kind": "text", "text": "HI"}]}
)
FLAGSHIP_BOARD = {"id": "board-flagship", "name": "Big Board", "device_type": "flagship"}
LED_ONLY = "This page is set to show only on LED displays"
LISTED_ONLY = "This page is set to show only on the boards it lists"


def _targets(**kwargs) -> Page:
    return FLEX_PAGE.model_copy(update={"targets": FlexTargets(**kwargs)})


def test_flexible_page_fits_a_split_flap_board():
    assert page_fit_for_board(FLEX_PAGE, FLAGSHIP_BOARD) == PageFit(True, None, None)


def test_flexible_page_is_compatible_with_a_split_flap_board():
    assert pages_compatible_with_board(FLEX_PAGE, FLAGSHIP_BOARD)


def test_flexible_page_is_compatible_with_an_led_board(pixoo_output):  # noqa: F811
    assert pages_compatible_with_board(FLEX_PAGE, _board())


def test_flexible_page_dict_is_compatible_with_any_board():
    page = {"name": "Morning", "type": "flexible", "blocks": []}
    assert pages_compatible_with_board(page, {"id": "n", "device_type": "note"})


def test_targets_technology_excludes_with_plain_reason():
    fit = page_fit_for_board(_targets(technology=["led_matrix"]), FLAGSHIP_BOARD)
    assert fit == PageFit(False, None, LED_ONLY)


def test_targets_technology_exclusion_makes_page_incompatible():
    assert not pages_compatible_with_board(_targets(technology=["led_matrix"]), FLAGSHIP_BOARD)


def test_targets_technology_admits_a_matching_board(pixoo_output):  # noqa: F811
    assert page_fit_for_board(_targets(technology=["led_matrix"]), _board()) == PageFit(True, None, None)


def test_targets_board_ids_exclude_an_unlisted_board():
    fit = page_fit_for_board(_targets(boards=["pixoo-1"]), FLAGSHIP_BOARD)
    assert fit == PageFit(False, None, LISTED_ONLY)


def test_targets_board_ids_admit_a_listed_board():
    assert page_fit_for_board(_targets(boards=["board-flagship"]), FLAGSHIP_BOARD) == PageFit(True, None, None)


def test_targets_in_a_page_dict_are_honoured():
    page = {"name": "M", "type": "flexible", "blocks": [], "targets": {"boards": ["pixoo-1"]}}
    assert not pages_compatible_with_board(page, FLAGSHIP_BOARD)


def test_text_size_change_never_invalidates_a_flexible_page(pixoo_output):  # noqa: F811
    for font, rows, cols in (("3x5", 10, 16), ("5x7", 8, 10)):
        board = _board(grid_rows=rows, grid_cols=cols, output_config={"font": font})
        assert pages_compatible_with_board(FLEX_PAGE, board), font


def test_board_technology_of_an_led_board(pixoo_output):  # noqa: F811
    assert board_technology(_board()) == "led_matrix"


def test_board_technology_of_a_vestaboard():
    assert board_technology(FLAGSHIP_BOARD) == "split_flap"


def test_board_technology_of_a_fiestapanel():
    assert board_technology({"id": "p", "device_type": "flagship", "output": "fiestapanel"}) == "split_flap"


def test_board_technology_of_an_uninstalled_output():
    assert board_technology({"id": "x", "device_type": "panel", "output": "not_installed_here"}) == "unknown"
