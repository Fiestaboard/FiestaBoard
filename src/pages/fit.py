"""Whether a grid page shows on a board, and at which text size.

The one fit rule for grid pages (spec: "Pages that still don't fit are
flagged, not hidden"). A page whose :func:`~src.devices.size_key` matches the
board's takes today's path. An LED board that can draw more than one text
size (:func:`~src.outputs.board_profile.board_producible_grids`) also shows a
``panel`` page whose grid it produces at another face; the page is then drawn
at that face. Anything else does not fit, with a plain reason.

The family rule holds: only ``panel`` pages can match another face's grid,
so a flagship page never fits an LED board, even one at 6 x 22.

A flexible page has no grid and fits every board (spec section 7); only its
optional ``targets`` narrows that, by board technology or by board id. Text
size never enters into it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.devices import (
    BoardInstance,
    dimensions_of,
    geometry_of,
    is_flexible_page,
    resolve_dimensions,
    size_key,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageFit:
    """How *page* fits a board.

    ``fits`` with ``face`` ``None``: the page is at the board's own grid.
    ``fits`` with a ``face``: the board draws the page at that text size.
    Not ``fits``: ``reason`` says why, in user-facing words.
    """

    fits: bool
    face: str | None
    reason: str | None


def delivers_full_frame(page: Any, fit: PageFit, result: Any) -> bool:
    """Whether a send of *page*, fitted as *fit* and rendered as *result*,
    reaches its board as one opaque full-frame layer (design section 6).

    A grid page drawn at another face does (``fit.face``), and so does a
    flexible page whose render carries layers: it carries exactly one, its
    laid-out frame, and only on a pixel board. A flexible page on any other
    board is an ordinary grid of cells, and a grid page at the board's own
    size sends at most its canvas layers, never a full frame.
    """
    if fit.face:
        return True
    return is_flexible_page(page) and bool(getattr(result, "layers", None))


def fit_reason(page: Any) -> str:
    """Why *page* doesn't fit a board: ``"Made for a {rows}×{cols} board"``.

    A page whose grid cannot be resolved reads as the flagship's 6 x 22,
    mirroring :func:`~src.devices.size_key`'s fallback.
    """
    try:
        dims = dimensions_of(page)
    except ValueError:
        dims = resolve_dimensions("flagship")
    return f"Made for a {dims.rows}×{dims.cols} board"


def _board_mapping(board: Any) -> Mapping[str, Any] | None:
    if isinstance(board, Mapping):
        return board
    if isinstance(board, BoardInstance):
        return board.to_dict()
    return None


def _current_face(board: Mapping[str, Any]) -> str | None:
    """The face *board* draws in now: its effective model's own face."""
    from src.led.matrix import led_layout_options_for_model
    from src.outputs.board_profile import board_device_model, offers_font_choice

    model = board_device_model(board)
    if not offers_font_choice(model):
        return None
    assert model is not None
    return led_layout_options_for_model(model).font


def page_fit_for_board(page: Any, board: Any) -> PageFit:
    """Whether *page* shows on *board*, and at which face (see the module doc).

    *board* is a board dict or a :class:`~src.devices.BoardInstance`; any
    other object (a Page, say) gets the exact :func:`size_key` rule. A board
    whose producible grids cannot be read (its output is not installed, or
    resolving them fails) falls back to the exact rule too.

    A flexible page fits every board unless its ``targets`` exclude it
    (:func:`_flexible_fit`); it never reaches the grid rule.
    """
    if is_flexible_page(page):
        return _flexible_fit(page, board)
    if size_key(*geometry_of(page)) == size_key(*geometry_of(board)):
        return PageFit(True, None, None)
    mapping = _board_mapping(board)
    if mapping is not None and geometry_of(page).device_type == "panel":
        face = _face_for(page, mapping)
        if face is not None:
            return PageFit(True, face, None)
    return PageFit(False, None, fit_reason(page))


def _face_for(page: Any, board: Mapping[str, Any]) -> str | None:
    """The face other than *board*'s current one whose grid is *page*'s."""
    from src.outputs.board_profile import board_producible_grids

    try:
        grids = board_producible_grids(board)
        if not grids:
            return None
        dims = dimensions_of(page)
        current = _current_face(board)
    except Exception:
        logger.warning("Could not read the grids a board can produce; using the exact fit", exc_info=True)
        return None
    for face, grid in grids.items():
        if grid == (dims.rows, dims.cols) and face != current:
            return face
    return None


#: How a ``targets.technology`` restriction reads in a refusal: "LED displays".
_TECHNOLOGY_NOUNS = {
    "led_matrix": "LED displays",
    "split_flap": "split-flap boards",
    "screen": "screens",
}
LISTED_BOARDS_REASON = "This page is set to show only on the boards it lists"


def board_technology(board: Any) -> str:
    """What kind of display *board* is: ``"led_matrix"``, ``"split_flap"``, ...

    The board's :class:`~src.outputs.display_profile.DisplayProfile`
    technology when its device model is known; otherwise ``"split_flap"`` for
    the Vestaboard and FiestaPanel outputs, else ``"unknown"``.
    """
    from src.outputs.display_profile import display_profile_for_board
    from src.outputs.registry import FIRST_PARTY_OUTPUTS, resolve_output_id

    mapping = _board_mapping(board)
    if mapping is None:
        return "unknown"
    try:
        profile = display_profile_for_board(mapping)
    except Exception:
        logger.warning("Could not read a board's display profile; guessing its technology", exc_info=True)
        profile = None
    if profile is not None:
        return profile.technology
    if resolve_output_id(mapping) in FIRST_PARTY_OUTPUTS:
        return "split_flap"
    return "unknown"


def _targets_field(targets: Any, name: str) -> list[str] | None:
    value = targets.get(name) if isinstance(targets, Mapping) else getattr(targets, name, None)
    return list(value) if value else None


def _technology_reason(technologies: list[str]) -> str:
    nouns = [_TECHNOLOGY_NOUNS.get(tech, f"{tech} displays") for tech in technologies]
    return f"This page is set to show only on {' or '.join(nouns)}"


def _flexible_fit(page: Any, board: Any) -> PageFit:
    """A flexible page fits *board* unless its ``targets`` exclude it.

    Each non-empty ``targets`` list restricts on its own, so a page naming
    both a technology and boards shows only on listed boards of that
    technology. An empty or missing list restricts nothing.
    """
    targets = page.get("targets") if isinstance(page, Mapping) else getattr(page, "targets", None)
    if targets is None:
        return PageFit(True, None, None)
    technologies = _targets_field(targets, "technology")
    if technologies is not None and board_technology(board) not in technologies:
        return PageFit(False, None, _technology_reason(technologies))
    board_ids = _targets_field(targets, "boards")
    if board_ids is not None:
        mapping = _board_mapping(board)
        if mapping is None or mapping.get("id") not in board_ids:
            return PageFit(False, None, LISTED_BOARDS_REASON)
    return PageFit(True, None, None)
