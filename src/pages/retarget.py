"""Move pages sized for a board's old grid onto its new one.

A board's grid can change in place: a FiestaPanel is re-fit to its TV
(:mod:`src.panels.reconcile`), and an LED board's text size switches a Pixoo
between 10 x 16 (Small, 3x5) and 8 x 10 (Large, 5x7). Pages are authored for a
size, so without this every page the board showed would stop fitting it.

:func:`retarget_pages` moves every page sized exactly for a resized board's old
grid onto its new one, unless something else still needs the old size:

- another board still has it (the page keeps serving that board), or
- boards that shared the old size now have different sizes (no one right
  target).

Growing a page is lossless. Shrinking crops what no longer fits at render
time (the stored template keeps every line, so growing back restores it);
callers opt in with ``allow_shrink`` only when the user chose the new size.
"""

from __future__ import annotations

import logging
from typing import Any

from src.devices import Geometry, geometry_of, resolve_dimensions, size_key

logger = logging.getLogger(__name__)

#: old size key -> every (old geometry, new geometry) a resize of that size produced
Resizes = dict[str, list[tuple[Geometry, Geometry]]]


def add_resize(resizes: Resizes, old: Any, new: Any) -> None:
    """Record that a board (or dict) *old* became *new* in *resizes*."""
    old_geometry, new_geometry = geometry_of(old), geometry_of(new)
    if size_key(*old_geometry) == size_key(*new_geometry):
        return
    resizes.setdefault(size_key(*old_geometry), []).append((old_geometry, new_geometry))


def retarget_pages(resizes: Resizes, remaining_keys: set[str], *, allow_shrink: bool = False) -> list[dict[str, Any]]:
    """Move pages sized for a resized board's old grid onto its new grid.

    *remaining_keys* are the size keys of every board after the change: an
    old size still among them is still needed and its pages stay. Returns one
    ``{page_id, page_name, from_size, to_size}`` per page moved. Never raises:
    a page that cannot be moved is logged and left where it is.
    """
    from src.pages.models import PageUpdate
    from src.pages.service import get_page_service

    targets: dict[str, Geometry] = {}
    for old_key, moves in resizes.items():
        new_geometries = {new for _old, new in moves}
        if len(new_geometries) != 1:
            logger.info("Pages sized %s left in place: boards that shared it now differ", old_key)
            continue
        if old_key in remaining_keys:
            logger.info("Pages sized %s left in place: another board still has that size", old_key)
            continue
        new = next(iter(new_geometries))
        if not allow_shrink:
            new_dims = resolve_dimensions(*new)
            if any(new_dims.rows < old.rows or new_dims.cols < old.cols for old in _old_dims(moves)):
                logger.info("Pages sized %s left in place: the new grid is smaller and would crop them", old_key)
                continue
        targets[old_key] = new

    if not targets:
        return []

    page_service = get_page_service()
    moved: list[dict[str, Any]] = []
    for page in page_service.list_pages():
        old_key = size_key(*geometry_of(page))
        new = targets.get(old_key)
        if new is None:
            continue
        device_type, notes_wide, notes_tall, grid_rows, grid_cols = new
        try:
            page_service.update_page(
                page.id,
                PageUpdate(
                    device_type=device_type,
                    notes_wide=notes_wide,
                    notes_tall=notes_tall,
                    grid_rows=grid_rows,
                    grid_cols=grid_cols,
                ),
            )
        except ValueError:
            logger.warning("Could not retarget page %r to its board's new grid", page.name, exc_info=True)
            continue
        moved.append({"page_id": page.id, "page_name": page.name, "from_size": old_key, "to_size": size_key(*new)})
    if moved:
        logger.info("Retargeted %d page(s) to their boards' new grids", len(moved))
    return moved


def _old_dims(moves: list[tuple[Geometry, Geometry]]):
    for old, _new in moves:
        yield resolve_dimensions(*old)
