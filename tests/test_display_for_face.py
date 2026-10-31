"""A display profile for drawing a page at another text size (face) than the
board's own: the face's character set and the page's grid, on the board's
own pixel surface."""

import pytest

from src.outputs.display_profile import display_for_face, display_profile_for_board
from tests.test_led_text_size import _board, pixoo_output  # noqa: F401


@pytest.fixture
def five_by_seven(pixoo_output):  # noqa: F811
    """The 5x7 Pixoo 64 profile (8 x 10), the way the board itself resolves it."""
    return display_profile_for_board(_board(grid_rows=8, grid_cols=10, output_config={"font": "5x7"}))


def test_the_face_profile_names_the_face_its_set_and_the_pages_grid(five_by_seven):
    d = display_for_face(five_by_seven, "3x5", (10, 16))
    assert (d.font, d.charset, d.rows, d.cols, d.width, d.height) == ("3x5", "led_3x5", 10, 16, 64, 64)


def test_the_face_profile_offers_only_the_faces_icons(five_by_seven):
    assert "snow" in five_by_seven.icons and "snow" not in display_for_face(five_by_seven, "3x5", (10, 16)).icons


def test_the_face_profile_keys_caches_apart_from_the_board(five_by_seven):
    assert display_for_face(five_by_seven, "3x5", (10, 16)).key != five_by_seven.key
