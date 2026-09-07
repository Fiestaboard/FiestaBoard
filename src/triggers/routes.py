"""FastAPI router for the trigger endpoints.

Handlers were moved here from ``src/api_server.py`` (Phase 2 slice 8, Task 8)
and the conventions pass was applied in the same commit.

Collaborators resolve from their canonical homes at **module import time**, so
this module never loads ``src.api_server``
(``tests/test_small_domains_decoupled.py`` asserts that in a fresh
interpreter). Tests that need to stub a collaborator patch it where this
module binds it — ``src.triggers.routes.<name>`` — not
``src.api_server.<name>``.

``PLUGIN_SYSTEM_AVAILABLE`` is the one collaborator with no canonical home:
it is a module-level flag ``src/api_server.py`` computes from its own
``try: import`` and that ``src/plugins/routes.py`` still reaches back for at
call time. Rather than grow a third pattern (or import the app module), this
router computes the same flag the same way ``src/displays/service.py`` does —
one ``try: import`` at module scope. A test that needs the plugin system to
look unavailable patches ``src.triggers.routes.PLUGIN_SYSTEM_AVAILABLE``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.api_errors import errors

try:
    from src.plugins.registry import get_plugin_registry

    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:  # pragma: no cover - the plugin package is always present in-tree
    PLUGIN_SYSTEM_AVAILABLE = False
    get_plugin_registry = None

from .models import (
    ActiveTriggerResponse,
    TriggerCheckResponse,
    TriggerClearResponse,
    TriggerDismissResponse,
    TriggerListResponse,
)
from .service import get_trigger_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["triggers"])


# No 4xx of its own: an instance with nothing fired answers an empty list.
# See the declared_errors exception in tests/conventions_manifest.json.
@router.get("/triggers", response_model=TriggerListResponse)
async def list_triggers():
    """List all active triggers with their status."""
    trigger_service = get_trigger_service()
    active = trigger_service.list_active_triggers()
    return TriggerListResponse(
        triggers=[t.to_dict() for t in active],
        count=len(active),
    )


# No 4xx of its own: "nothing is firing" is a null trigger at 200, not a 404 —
# this is polled by the dashboard on a timer and must not error on the common
# case. See the declared_errors exception in tests/conventions_manifest.json.
@router.get("/triggers/active", response_model=ActiveTriggerResponse)
async def get_active_trigger():
    """Get the current highest-priority active trigger, if any."""
    trigger_service = get_trigger_service()
    active = trigger_service.get_active_trigger()
    if active is None:
        return ActiveTriggerResponse(trigger=None)
    return ActiveTriggerResponse(trigger=active.to_dict())


@router.post("/triggers/{trigger_id}/dismiss", response_model=TriggerDismissResponse, responses=errors(404))
async def dismiss_trigger(trigger_id: str):
    """Dismiss (remove) a specific trigger by its id."""
    trigger_service = get_trigger_service()
    dismissed = trigger_service.dismiss_trigger(trigger_id)
    if not dismissed:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    return TriggerDismissResponse(trigger_id=trigger_id)


# No 4xx of its own: clearing an empty set is a no-op that succeeds. See the
# declared_errors exception in tests/conventions_manifest.json.
@router.post("/triggers/clear", response_model=TriggerClearResponse)
async def clear_triggers():
    """Clear all active triggers."""
    trigger_service = get_trigger_service()
    trigger_service.clear_all()
    return TriggerClearResponse()


@router.post("/triggers/check", response_model=TriggerCheckResponse, responses=errors(503))
async def check_triggers():
    """Manually trigger a check of all trigger-capable plugins.

    This is normally done automatically by the display loop, but this
    endpoint allows the UI or external systems to force an immediate check.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")

    registry = get_plugin_registry()
    trigger_service = get_trigger_service()

    checked = 0
    for _plugin_id, plugin in registry.trigger_plugins.items():
        trigger_service.check_plugin_triggers(plugin)
        checked += 1

    active = trigger_service.list_active_triggers()
    return TriggerCheckResponse(
        plugins_checked=checked,
        active_triggers=[t.to_dict() for t in active],
        count=len(active),
    )
