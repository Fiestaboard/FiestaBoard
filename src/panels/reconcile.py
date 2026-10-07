"""Keep every panel's virtual board fit to its TV.

A panel's grid is derived, never chosen: it is whatever
:func:`src.panels.autofit.compute_autofit_grid` says the screen holds. Two
things can leave a stored board out of step with that:

* A screen-size edit — handled inline by ``PATCH /panels/{id}``, which
  re-fits the board and warns about pages that no longer fit.
* A change to how grids are fit. Panels used to be fit in whole Note blocks
  and stored as ``note_array`` boards; they are now fit per character and
  stored as ``panel`` boards. :func:`reconcile_panel_boards` runs at startup
  and re-fits every panel whose board disagrees with the current fit.

When the startup re-fit moves a panel to a grid at least as large on both
axes (always true for the Note-block → per-character change), pages sized
exactly for the panel's old grid are retargeted with it, so the panel keeps
showing what it showed. Growing a page is lossless — content keeps its place
and gains room — whereas shrinking would crop, so a shrinking re-fit leaves
pages alone (and they are then reported as incompatible, like a manual
retarget). A page is only moved when nothing else still needs its old size:
not when another, non-panel board has that size, and not when two panels
that shared the old size now fit differently (there is no one right target).
"""

from __future__ import annotations

import logging

from src.devices import DeviceDimensions, geometry_of, size_key
from src.outputs.registry import FIESTAPANEL, resolve_output_id

logger = logging.getLogger(__name__)


def board_matches_grid(board: dict, grid: DeviceDimensions) -> bool:
    """True when *board* is already a ``panel`` board of exactly *grid*."""
    return board.get("device_type") == "panel" and (board.get("grid_rows"), board.get("grid_cols")) == (
        grid.rows,
        grid.cols,
    )


def fit_board_to_grid(board: dict, grid: DeviceDimensions) -> None:
    """Make *board* (a settings board dict, mutated in place) a panel of *grid*."""
    board["device_type"] = "panel"
    board["grid_rows"] = grid.rows
    board["grid_cols"] = grid.cols
    # A panel is not sized in Notes; reset them so a stale count can't
    # suggest otherwise to anything reading the raw dict.
    board["notes_wide"] = 1
    board["notes_tall"] = 1


def reconcile_panel_boards() -> int:
    """Re-fit every panel board that disagrees with its screen. Returns the count.

    Idempotent: once every board matches, this reads and changes nothing.
    Never raises — a failure is logged and the boot continues with the boards
    as they were.
    """
    try:
        return _reconcile()
    except Exception:
        logger.warning("Panel grid reconcile failed; panels keep their stored grids", exc_info=True)
        return 0


def _reconcile() -> int:
    from src.display_runtime import release_board_frames
    from src.pages.retarget import add_resize, retarget_pages
    from src.settings.service import get_settings_service

    from .autofit import compute_autofit_grid
    from .service import get_panel_service

    panels = get_panel_service().list_panels()
    if not panels:
        return 0

    settings_service = get_settings_service()
    boards = [dict(b) for b in (settings_service.get_board_settings().boards or []) if isinstance(b, dict)]
    by_id = {b.get("id"): b for b in boards}

    resizes: dict = {}
    refit_ids: list[str] = []
    for panel in panels:
        board = by_id.get(panel.board_id)
        if board is None or resolve_output_id(board) != FIESTAPANEL:
            continue
        grid = compute_autofit_grid(panel.screen_diagonal_inches, panel.screen_aspect_w, panel.screen_aspect_h)
        if board_matches_grid(board, grid):
            continue
        old_key = size_key(*geometry_of(board))
        old_board = dict(board)
        fit_board_to_grid(board, grid)
        add_resize(resizes, old_board, board)
        refit_ids.append(panel.board_id)
        logger.info(
            "Panel %r re-fit from %s to panel:%dx%d",
            panel.name,
            old_key,
            grid.rows,
            grid.cols,
        )

    if not refit_ids:
        return 0

    settings_service.set_boards(boards)
    for board_id in refit_ids:
        release_board_frames(board_id)

    # A re-fit is not the user's choice: pages only grow with it, never crop.
    retarget_pages(resizes, remaining_keys={size_key(*geometry_of(b)) for b in boards})
    return len(refit_ids)
