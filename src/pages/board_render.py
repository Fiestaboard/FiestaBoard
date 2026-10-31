"""Render a stored page for one board, at the text size the page needs.

The route sends (``POST /pages/{id}/send``, ``PUT /settings/active-page``,
``POST /v1/boards/{board}/message`` with a ``page_id``) share this. A grid
page an LED board produces only at another face (:func:`~src.pages.fit.page_fit_for_board`)
is rendered at that face, and its layers become one full-frame layer
(:func:`~src.led.page_frame.send_layers`); the caller projects the text to the
board's own grid under it (design section 7). Legacy grid pages retain their
crop fallback. Flexible pages enforce their targets and require a writer
that preserves their pixel frame.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from src.canvas.layer import CanvasLayer
from src.devices import dimensions_of, is_flexible_page
from src.led.page_frame import send_layers

from .fit import PageFit, page_fit_for_board

if TYPE_CHECKING:
    from src.displays.service import DisplayResult

__all__ = ["render_page_for_board"]

#: No board to fit against (a legacy primary-client send): today's path.
_NO_FACE = PageFit(True, None, None)


def flexible_frame_error(page: Any, result: Any, client: Any, *, native: bool = False) -> str | None:
    """Refuse a flexible image when a real driver's path would discard it.

    This verifies transport of layers, not an adapter's physical pixel mapping.
    Legacy grid/Canvas fallback remains unchanged. Native snapshots have their
    own rich-frame contract and do not require an ordinary cell writer.
    """
    from src.outputs.cells import charset_uses_cells
    from src.outputs.plugin_driver import OutputPluginDriver

    if not is_flexible_page(page) or not result.layers or not isinstance(client, OutputPluginDriver):
        return None
    if client.takes_cells or (native and client.native_rotation_enabled and charset_uses_cells(client.character_set)):
        return None
    return "This output cannot receive flexible pixel frames; update its output plugin before using this page"


def render_page_for_board(
    page_service: Any,
    page_id: str,
    board: Mapping | None,
    render_kw: Mapping[str, Any],
    *,
    force_refresh: bool = True,
    client: Any = None,
) -> tuple[DisplayResult | None, list[CanvasLayer], PageFit]:
    """``(result, layers, fit)`` for *page_id* sent to *board*.

    *render_kw* is the board client's render keywords
    (:func:`~src.outputs.display_profile.render_kw`). The page renders at
    ``fit.face`` (``None`` for a page at the board's own grid, one that
    doesn't fit, or no *board*). ``layers`` are the layers to send: one
    full-frame layer for a face render on a pixel board, else the render's
    own. ``result`` is ``None`` when the page does not exist; ``layers`` is
    then empty, as it is for an unavailable render.

    A flexible page has no grid and never a face: it is laid out for *board*
    (``None``: the primary board), and its layers are its own full frame.
    """
    page = page_service.get_page(page_id)
    if page is None:
        return None, [], _NO_FACE
    fit = page_fit_for_board(page, board) if board is not None else _NO_FACE
    board_kw = {"board": board} if is_flexible_page(page) and board is not None else {}
    result = page_service.preview_page(page_id, force_refresh=force_refresh, face=fit.face, **board_kw, **render_kw)
    if result is None or not result.available:
        return result, [], fit
    refusal = fit.reason if is_flexible_page(page) and not fit.fits else flexible_frame_error(page, result, client)
    if refusal:
        return replace(result, available=False, error=refusal), [], fit
    if not fit.face:
        return result, result.layers, fit
    dims = dimensions_of(page)
    return result, send_layers(result, dims.rows, dims.cols, render_kw.get("display")), fit
