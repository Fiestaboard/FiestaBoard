"""FastAPI router for the staff-picks endpoints.

Moved out of ``src/pages/routes.py`` by Phase 2 slice 8. The handlers were
already conventions-compliant — the pages slice converted them — but they were
sharing the ``pages`` router tag, which made staff-picks invisible to the
conventions ratchet as a domain: it could not be excused, enforced or reviewed
on its own, and its one manifest exception was filed against ``pages``. The
tag is now ``staff-picks``.

The catalog is a checked-in file at the repo root with no service and no
storage behind it. A missing ``picks.json`` degrades to an empty list on
purpose: a broken install should show an empty gallery, not a 500 on the page
that offers people their first board.

This module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.api_errors import errors
from src.pages.models import ShareStringResponse

from .models import StaffPick

logger = logging.getLogger(__name__)

router = APIRouter(tags=["staff-picks"])

# One more .parent than api_server.py had — this file is a level deeper.
_STAFF_PICKS_PATH = Path(__file__).parent.parent.parent / "staff-picks" / "picks.json"


def _load_staff_picks() -> list:
    try:
        with open(_STAFF_PICKS_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# No 4xx of its own: a missing picks.json degrades to []. See the
# declared_errors exception in tests/conventions_manifest.json.
@router.get("/staff-picks", response_model=list[StaffPick])
async def list_staff_picks():
    """Return all staff picks (without share strings)."""
    picks = _load_staff_picks()
    return [{k: v for k, v in pick.items() if k != "share_string"} for pick in picks]


@router.get(
    "/staff-picks/{pick_id}/share",
    response_model=ShareStringResponse,
    responses=errors(404),
)
async def get_staff_pick_share(pick_id: str):
    """Return the share string for a specific staff pick."""
    picks = _load_staff_picks()
    pick = next((p for p in picks if p["id"] == pick_id), None)
    if not pick:
        raise HTTPException(status_code=404, detail=f"Staff pick not found: {pick_id}")
    return ShareStringResponse(share_string=pick["share_string"])
