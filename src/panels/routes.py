"""FastAPI router for the FiestaPanel endpoints.

Two surfaces with different auth:

* ``/panels``  (plural)  — CRUD for the app, authenticated like everything else.
* ``/panel/``  (singular) — read-only viewer endpoints for TVs, exempted from
  auth via ``AuthMiddleware(extra_public_paths)``.

A panel's virtual board is co-created on POST and co-deleted on DELETE so
"a FiestaPanel" stays one concept for the user.

Handlers were moved here from ``src/api_server.py`` (Phase 2 slice 8, Task 8)
into the existing ``src/panels`` package, and the conventions pass was applied
in the same commit.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter). Two of them had no canonical home and got one in this PR:
``characters_to_message`` moved to ``src/board_chars.py`` and
``reinitialize_board_clients`` to ``src/display_runtime.py``, next to the
``DisplayService`` singleton it acts on. ``src.api_server`` imports both under
their old private names, so its own handlers and their patch targets are
unchanged.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.board_chars import characters_to_message
from src.board_guards import _board_dims, _find_board
from src.devices import NOTE_COLS, NOTE_ROWS, is_note_array, resolve_dimensions
from src.display_runtime import get_service, reinitialize_board_clients, release_board_frames
from src.outputs.cells import cells_to_json
from src.pages.service import find_incompatible_board_references
from src.settings.service import get_settings_service

from .models import (
    PanelCreate,
    PanelDeleteResponse,
    PanelFrameResponse,
    PanelListResponse,
    PanelPublicResponse,
    PanelResponse,
    PanelUpdate,
    PanelUpdateResponse,
)
from .reconcile import board_matches_grid, fit_board_to_grid
from .service import get_panel_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["panels"])


def _panel_not_found_detail(ref: str) -> str:
    """404 detail for the public viewer: the reserved display ref gets
    actionable copy (the HDMI kiosk shows it before a panel is designated)."""
    if ref == "display":
        return "No display panel selected"
    return "Panel not found"


def _panel_board_fields(board: dict | None) -> dict:
    """Board-derived fields attached to panel payloads (orphan-aware).

    ``rows``/``cols`` are the grid in flaps — what the TV viewer scales from
    and what a page authored for this panel is sized to (a ``panel`` page
    with ``grid_rows``/``grid_cols`` equal to them). ``notes_wide``/
    ``notes_tall`` count the grid in Notes and are only non-null for a
    note-array board: a panel is fit per character, so it is generally not a
    whole number of Notes.
    """
    if board is None:
        return {
            "device_type": None,
            "board_missing": True,
            "rows": None,
            "cols": None,
            "notes_wide": None,
            "notes_tall": None,
        }
    dims = _board_dims(board)
    array = is_note_array(board.get("device_type") or "")
    return {
        "device_type": board.get("device_type"),
        "board_missing": False,
        "rows": dims.rows,
        "cols": dims.cols,
        "notes_wide": dims.cols // NOTE_COLS if array else None,
        "notes_tall": dims.rows // NOTE_ROWS if array else None,
    }


# No 4xx of its own: an instance with no panels answers an empty list. See
# the declared_errors exception in tests/conventions_manifest.json.
@router.get("/panels", response_model=PanelListResponse)
async def list_panels():
    """List all panels with their virtual board's shape attached."""
    panel_service = get_panel_service()
    panels = []
    for panel in panel_service.list_panels():
        board = _find_board(panel.board_id)
        panels.append({**panel.model_dump(mode="json"), **_panel_board_fields(board)})
    return PanelListResponse(panels=panels, total=len(panels))


@router.post("/panels", response_model=PanelResponse, status_code=201, responses=errors(400, 422))
async def create_panel(data: PanelCreate):
    """Create a panel and its backing auto-fit virtual board.

    The board's grid (a ``panel``: rows × cols of characters) is computed
    from the TV size so each flap renders at real-world scale while filling
    the screen. The
    virtual board is added first; if panel creation then fails the board
    is rolled back so no orphan is left behind.
    """
    from .autofit import compute_autofit_grid

    settings_service = get_settings_service()
    board_id = str(uuid.uuid4())
    grid = compute_autofit_grid(data.screen_diagonal_inches, data.screen_aspect_w, data.screen_aspect_h)
    settings_service.add_board(
        {
            "id": board_id,
            "device_type": "panel",
            "api_mode": "virtual",
            "grid_rows": grid.rows,
            "grid_cols": grid.cols,
            "name": f"{data.name} (Panel)",
        }
    )
    reinitialize_board_clients()
    panel_service = get_panel_service()
    try:
        panel = panel_service.create_panel(data, board_id=board_id)
    except Exception:
        with contextlib.suppress(Exception):
            settings_service.remove_board(board_id)
            reinitialize_board_clients()
        raise
    board = _find_board(board_id)
    return PanelResponse.model_validate({**panel.model_dump(mode="json"), **_panel_board_fields(board)})


@router.patch("/panels/{panel_id}", response_model=PanelUpdateResponse, responses=errors(404, 422))
async def update_panel(panel_id: str, data: PanelUpdate):
    """Update a panel's display configuration.

    A screen-size change re-fits the virtual board's grid: content keeps
    flowing at the new dimensions on the next send.
    """
    from .autofit import compute_autofit_grid

    panel_service = get_panel_service()
    panel = panel_service.update_panel(panel_id, data)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel not found")

    incompatible_references: list[dict] | None = None
    updates = data.model_dump(exclude_unset=True)
    screen_changed = any(
        updates.get(field) is not None for field in ("screen_diagonal_inches", "screen_aspect_w", "screen_aspect_h")
    )
    if screen_changed:
        settings_service = get_settings_service()
        boards = [dict(b) for b in (settings_service.get_board_settings().boards or [])]
        target = next((b for b in boards if b.get("id") == panel.board_id), None)
        if target is not None and target.get("api_mode") == "virtual":
            grid = compute_autofit_grid(panel.screen_diagonal_inches, panel.screen_aspect_w, panel.screen_aspect_h)
            if not board_matches_grid(target, grid):
                fit_board_to_grid(target, grid)
                settings_service.set_boards(boards)
                # Drop the old-shape frame BEFORE rebuilding the client. The
                # panel frame refuses a frame whose shape no longer matches
                # the board (core's stale-shape guard), but the
                # `expected_characters` half of /board/current-message is the
                # raw last-sent grid. Releasing the board's runtime frames
                # clears the displayed and last-sent frames together.
                release_board_frames(panel.board_id)
                reinitialize_board_clients()
                # The grid changed shape: pages authored for the old grid stay
                # referenced but can no longer render here. Warn-only, exactly
                # like PUT /pages/{id} after a size retarget (issue #1250).
                incompatible_references = find_incompatible_board_references(target)

    board = _find_board(panel.board_id)
    return PanelUpdateResponse.model_validate(
        {
            **panel.model_dump(mode="json"),
            **_panel_board_fields(board),
            "incompatible_references": incompatible_references,
        }
    )


@router.delete("/panels/{panel_id}", response_model=PanelDeleteResponse, responses=errors(404))
async def delete_panel(panel_id: str):
    """Delete a panel and its virtual board (tolerating an already-gone board).

    When the virtual board is the ONLY board, the last-board rule forbids
    removing it outright — deleting the panel would otherwise strand an
    unremovable virtual board as the primary. A fresh default board is
    swapped in instead (the same state a data reset produces).
    """
    panel_service = get_panel_service()
    panel = panel_service.delete_panel(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel not found")
    settings_service = get_settings_service()
    try:
        settings_service.remove_board(panel.board_id)
    except ValueError:
        # Either the board is already gone (fine) or it is the last board.
        boards = settings_service.get_board_settings().boards or []
        if len(boards) == 1 and boards[0].get("id") == panel.board_id:
            with contextlib.suppress(Exception):
                settings_service.set_boards([{"device_type": "flagship"}])
    release_board_frames(panel.board_id)
    reinitialize_board_clients()
    return PanelDeleteResponse(id=panel_id)


@router.get("/panel/{panel_id}", response_model=PanelPublicResponse, responses=errors(404))
async def get_panel_public(panel_id: str):
    """Public viewer config: panel settings + board geometry. No auth."""
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    out = panel.model_dump(mode="json")
    from src.fiestaui import fiestapanel_device_models

    model = fiestapanel_device_models()[panel.render_style]
    out.update({"device_model": model["id"], "device_model_spec": dict(model)})
    board = _find_board(panel.board_id)
    # One source for the board-derived block, so the viewer and the app can
    # never be told different geometry for the same panel.
    out.update(_panel_board_fields(board))
    if board is None:
        out.update({"board_color": None, "code62_glyph": None})
        return PanelPublicResponse.model_validate(out)
    from src.devices import BoardInstance

    out.update(
        {
            "board_color": board.get("board_color") or "black",
            "code62_glyph": BoardInstance.from_dict(board).effective_code62_glyph,
        }
    )
    return PanelPublicResponse.model_validate(out)


@router.get(
    "/panel/{panel_id}/frame",
    response_model=PanelFrameResponse,
    response_model_exclude_unset=True,
    responses=errors(404),
)
async def get_panel_frame(panel_id: str):
    """Public viewer frame: the board's last-frame store. No auth.

    Served from core: the board's live runtime keeps the last frame sent
    (plan D4), with the stale-shape refusal — a frame whose shape no longer
    matches the board (a TV-size re-fit) is served as no frame. Never
    triggers a live HTTP read, and never consults the poll cache: the viewer
    shows what FiestaBoard last displayed, immediately. A panel
    misconfigured onto a pushed (physical) board serves that board's
    last-sent cache, as it always has.
    """
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    board = _find_board(panel.board_id)
    dims = _board_dims(board) if board is not None else resolve_dimensions("flagship")

    service = get_service()
    rt = service.runtime_for(panel.board_id) if service is not None else None
    characters: list[list[int]] | None = None
    cells = None
    updated_at = None
    if rt is not None and rt.client is not None:
        output = rt.output
        if output.delivery == "pull":
            characters = output.displayed_frame(dims.rows, dims.cols)
            cells = output.displayed_cells(dims.rows, dims.cols) if characters is not None else None
            # When the frame was stored, whether or not it is served — a
            # refused stale-shape frame still reports when it was sent.
            if output.last_sent_at is not None:
                updated_at = datetime.fromtimestamp(output.last_sent_at, tz=UTC).isoformat()
        else:
            characters = output.frames.characters
            cells = output.frames.cells

    if characters is None:
        return PanelFrameResponse(
            characters=None,
            message=None,
            rows=dims.rows,
            cols=dims.cols,
            updated_at=updated_at,
        )
    # `cells` is set only for a frame that has rich cells, so every other
    # board's response is byte-for-byte what it was (exclude_unset).
    rich = {"cells": cells_to_json(cells)} if cells is not None else {}
    return PanelFrameResponse(
        characters=characters,
        **rich,
        message=characters_to_message(characters),
        rows=len(characters),
        cols=len(characters[0]) if characters else 0,
        updated_at=updated_at,
    )
