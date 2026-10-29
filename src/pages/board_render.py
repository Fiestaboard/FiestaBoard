"""Render a stored page for one board, at the text size the page needs.

The route sends (``POST /pages/{id}/send``, ``PUT /settings/active-page``,
``POST /v1/boards/{board}/message`` with a ``page_id``) share this. A grid
page an LED board produces only at another face (:func:`~src.pages.fit.page_fit_for_board`)
is rendered at that face, and its layers become one full-frame layer
(:func:`~src.led.page_frame.send_layers`); the caller projects the text to the
board's own grid under it (design section 7). Routes don't gate: a page that
doesn't fit is rendered as today (no face), and the send crops it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from src.canvas.layer import CanvasLayer
from src.devices import dimensions_of
from src.led.page_frame import send_layers

from .fit import PageFit, page_fit_for_board

if TYPE_CHECKING:
    from src.displays.service import DisplayResult

__all__ = ["render_page_for_board"]

#: No board to fit against (a legacy primary-client send): today's path.
_NO_FACE = PageFit(True, None, None)


def render_page_for_board(
    page_service: Any,
    page_id: str,
    board: Mapping | None,
    render_kw: Mapping[str, Any],
    *,
    force_refresh: bool = True,
) -> tuple[DisplayResult | None, list[CanvasLayer], PageFit]:
    """``(result, layers, fit)`` for *page_id* sent to *board*.

    *render_kw* is the board client's render keywords
    (:func:`~src.outputs.display_profile.render_kw`). The page renders at
    ``fit.face`` (``None`` for a page at the board's own grid, one that
    doesn't fit, or no *board*). ``layers`` are the layers to send: one
    full-frame layer for a face render on a pixel board, else the render's
    own. ``result`` is ``None`` when the page does not exist; ``layers`` is
    then empty, as it is for an unavailable render.
    """
    page = page_service.get_page(page_id)
    if page is None:
        return None, [], _NO_FACE
    fit = page_fit_for_board(page, board) if board is not None else _NO_FACE
    result = page_service.preview_page(page_id, force_refresh=force_refresh, face=fit.face, **render_kw)
    if result is None or not result.available:
        return result, [], fit
    if not fit.face:
        return result, result.layers, fit
    dims = dimensions_of(page)
    return result, send_layers(result, dims.rows, dims.cols, render_kw.get("display")), fit
