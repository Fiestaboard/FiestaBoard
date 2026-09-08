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
from src.board_send_executor import run_board_send
from src.devices import resolve_dimensions
from src.display_runtime import get_service, reinitialize_board_clients
from src.pages.service import find_incompatible_board_references
from src.settings.service import get_settings_service
from src.virtual_board_client import release_virtual_board_state

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
    """Board-derived fields attached to panel payloads (orphan-aware)."""
    if board is None:
        return {"device_type": None, "board_missing": True, "rows": None, "cols": None}
    dims = _board_dims(board)
    return {
        "device_type": board.get("device_type"),
        "board_missing": False,
        "rows": dims.rows,
        "cols": dims.cols,
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

    The board's grid (note-array blocks) is computed from the TV size so
    each flap renders at real-world scale while filling the screen. The
    virtual board is added first; if panel creation then fails the board
    is rolled back so no orphan is left behind.
    """
    from .autofit import compute_autofit_grid

    settings_service = get_settings_service()
    board_id = str(uuid.uuid4())
    notes_wide, notes_tall = compute_autofit_grid(
        data.screen_diagonal_inches, data.screen_aspect_w, data.screen_aspect_h
    )
    settings_service.add_board(
        {
            "id": board_id,
            "device_type": "note_array",
            "api_mode": "virtual",
            "notes_wide": notes_wide,
            "notes_tall": notes_tall,
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
            notes_wide, notes_tall = compute_autofit_grid(
                panel.screen_diagonal_inches, panel.screen_aspect_w, panel.screen_aspect_h
            )
            if (target.get("notes_wide"), target.get("notes_tall")) != (notes_wide, notes_tall) or target.get(
                "device_type"
            ) != "note_array":
                target["device_type"] = "note_array"
                target["notes_wide"] = notes_wide
                target["notes_tall"] = notes_tall
                settings_service.set_boards(boards)
                # Drop the old-shape frame BEFORE rebuilding the client.
                # read_current_message already refuses to serve a frame whose
                # shape no longer matches the board, but `_last_characters` is
                # read unguarded by /board/current-message (both the secondary
                # branch and the primary's `expected_characters`), which would
                # keep rendering the old grid — the exact stale-shape bug this
                # reshape path exists to prevent. Releasing the shared state
                # clears `displayed_characters` and `last_characters` together.
                release_virtual_board_state(panel.board_id)
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
    release_virtual_board_state(panel.board_id)
    reinitialize_board_clients()
    return PanelDeleteResponse(id=panel_id)


@router.get("/panel/{panel_id}", response_model=PanelPublicResponse, responses=errors(404))
async def get_panel_public(panel_id: str):
    """Public viewer config: panel settings + board geometry. No auth."""
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    out = panel.model_dump(mode="json")
    board = _find_board(panel.board_id)
    if board is None:
        out.update(
            {
                "device_type": None,
                "board_missing": True,
                "rows": None,
                "cols": None,
                "board_color": None,
                "code62_glyph": None,
            }
        )
        return PanelPublicResponse.model_validate(out)
    from src.devices import BoardInstance

    dims = _board_dims(board)
    instance = BoardInstance.from_dict(board)
    out.update(
        {
            "device_type": board.get("device_type"),
            "board_missing": False,
            "rows": dims.rows,
            "cols": dims.cols,
            "board_color": board.get("board_color") or "black",
            "code62_glyph": instance.effective_code62_glyph,
        }
    )
    return PanelPublicResponse.model_validate(out)


@router.get("/panel/{panel_id}/frame", response_model=PanelFrameResponse, responses=errors(404))
async def get_panel_frame(panel_id: str):
    """Public viewer frame: the virtual board's current content. No auth.

    Never triggers a live HTTP read — a panel misconfigured onto a physical
    board serves that board's last-sent cache instead of hammering it at the
    viewer's 2s poll cadence.
    """
    panel = get_panel_service().get_panel_by_ref(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail=_panel_not_found_detail(panel_id))
    board = _find_board(panel.board_id)
    dims = _board_dims(board) if board is not None else resolve_dimensions("flagship")

    service = get_service()
    client = service.get_board_client(panel.board_id) if service is not None else None
    if client is None and service is not None:
        # Primary runtimes may be keyed under a legacy sentinel rather than
        # the settings board id; fall back to the primary client.
        with contextlib.suppress(Exception):
            if panel.board_id == get_settings_service().get_primary_board_id():
                client = service.vb_client

    characters = None
    updated_at = None
    if client is not None:
        if getattr(client, "is_virtual", False):
            # A virtual board reads from memory, but the same call on a real
            # client is network I/O; keep it off the loop either way (#1878).
            characters = await run_board_send(client.read_current_message)
        else:
            characters = getattr(client, "_last_characters", None)
        ts = getattr(client, "_last_sent_at", None)
        if ts:
            updated_at = datetime.fromtimestamp(ts, tz=UTC).isoformat()

    if characters is None:
        return PanelFrameResponse(
            characters=None,
            message=None,
            rows=dims.rows,
            cols=dims.cols,
            updated_at=updated_at,
        )
    return PanelFrameResponse(
        characters=characters,
        message=characters_to_message(characters),
        rows=len(characters),
        cols=len(characters[0]) if characters else 0,
        updated_at=updated_at,
    )
