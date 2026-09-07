"""The schedules router must not depend on ``src.api_server`` (Phase 2 §2.3).

The #1756 extraction moved the eleven schedule handlers out of the 10k-line
``src/api_server.py`` but left eleven call-time ``from src.api_server import
...`` statements behind, purely so the suite's ``patch("src.api_server.<name>")``
targets kept resolving. That is not an extraction: importing the router was
clean, but *serving a request* pulled the whole module — its route table, its
background tasks, its MCP mount — back in, and the 2026-09 audit counted those
seams going up 4.2x across Phase 1.

Retiring them needed three names to grow a canonical home first, because they
had none outside the app module: ``_require_board`` (now
``src/board_guards.py``),
``resolve_active_page_id`` / ``resolve_next_check_seconds`` (now
``src/collections/service.py``) and ``temporary_override_payload`` (now
``src/settings/service.py``).

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives all eleven handlers end to end against patched canonical seams
(``src.schedules.routes.<name>``), asserts the stubs really were driven — so a
handler that silently no-op'd could not pass — and then asserts
``src.api_server`` never entered ``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes even with every one of them still
in place.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import asyncio
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import src.schedules.routes as routes
from src.schedules.models import (
    DefaultPageUpdate,
    ScheduleCreate,
    ScheduleEnabledUpdate,
    ScheduleEntry,
    ScheduleUpdate,
    ScheduleValidateRequest,
    ScheduleValidationResult,
)

assert "src.api_server" not in sys.modules, "importing the schedules router must not import api_server"


def call(coro):
    return asyncio.run(coro)


sample = ScheduleEntry(id="sched-1", board_id="board-1", page_id="p1", start_time="09:00", end_time="17:00")

schedule_service = MagicMock()
schedule_service.list_schedules.return_value = [sample]
schedule_service.get_schedule.return_value = sample
schedule_service.create_schedule.return_value = sample
schedule_service.update_schedule.return_value = sample
schedule_service.delete_schedule.return_value = True
schedule_service.get_default_page.return_value = "p1"
schedule_service.get_active_page_id.return_value = "p1"
schedule_service.validate_schedules.return_value = ScheduleValidationResult(valid=True, overlaps=[], gaps=[])

settings_service = MagicMock()
settings_service.is_schedule_enabled.return_value = True
settings_service.get_temporary_override.return_value = None
settings_service.get_active_page_id.return_value = "p1"

page_service = MagicMock()
page_service.get_page.return_value = object()

time_service = MagicMock()
time_service.get_current_time.return_value = datetime(2026, 9, 7, 10, 30)

compat = MagicMock()
compat.ok = True
compat.warnings = ["mixed sizes"]

with (
    patch("src.schedules.routes.get_schedule_service", return_value=schedule_service),
    patch("src.schedules.routes.get_settings_service", return_value=settings_service),
    patch("src.schedules.routes.get_page_service", return_value=page_service),
    patch("src.schedules.routes.get_time_service", return_value=time_service),
    patch("src.schedules.routes.check_ref_board_compatibility", return_value=compat),
    patch("src.schedules.routes._require_board") as require_board,
):
    listed = call(routes.list_schedules())
    assert listed.total == 1, listed
    assert listed.schedules[0].id == "sched-1"
    assert listed.default_page_id == "p1"
    assert listed.enabled is True

    wildcard = call(routes.list_schedules(board_id="*"))
    assert wildcard.enabled is None, wildcard

    created = call(routes.create_schedule(ScheduleCreate(board_id="board-1", page_id="p1", start_time="09:00")))
    assert created["id"] == "sched-1", created
    assert created["warnings"] == ["mixed sizes"], created

    active = call(routes.get_active_schedule())
    assert active.page_id == "p1", active
    assert active.source == "schedule", active
    assert active.current_time == "10:30", active
    assert active.temporary_override.active is False, active

    settings_service.is_schedule_enabled.return_value = False
    manual = call(routes.get_active_schedule())
    assert manual.source == "manual", manual
    assert manual.current_time is None, manual
    settings_service.is_schedule_enabled.return_value = True

    validated = call(routes.validate_schedules(ScheduleValidateRequest(board_id="board-1")))
    assert validated.valid is True, validated

    default_page = call(routes.get_default_page())
    assert default_page.default_page_id == "p1", default_page

    set_default = call(routes.set_default_page(DefaultPageUpdate(page_id="p1", board_id="board-1")))
    assert set_default.default_page_id == "p1", set_default

    enabled = call(routes.get_schedule_enabled())
    assert enabled.enabled is True, enabled

    set_enabled = call(routes.set_schedule_enabled(ScheduleEnabledUpdate(enabled=True, board_id="board-1")))
    assert set_enabled.enabled is True, set_enabled

    fetched = call(routes.get_schedule("sched-1"))
    assert fetched["id"] == "sched-1", fetched

    updated = call(routes.update_schedule("sched-1", ScheduleUpdate(board_id="board-1")))
    assert updated["id"] == "sched-1", updated

    deleted = call(routes.delete_schedule("sched-1"))
    assert deleted.id == "sched-1", deleted

# Not vacuous: the handlers really drove their collaborators. A handler that
# silently returned a canned value would fail here rather than pass above.
schedule_service.list_schedules.assert_any_call(board_id=None)
schedule_service.list_schedules.assert_any_call(board_id="*")
schedule_service.create_schedule.assert_called_once()
schedule_service.get_schedule.assert_called_once_with("sched-1")
schedule_service.update_schedule.assert_called_once()
schedule_service.delete_schedule.assert_called_once_with("sched-1")
schedule_service.set_default_page.assert_called_once_with("p1", board_id="board-1")
schedule_service.validate_schedules.assert_called_once_with(board_id="board-1")
schedule_service.get_active_page_id.assert_called_once()
settings_service.set_schedule_enabled.assert_called_once_with(True, board_id="board-1")
settings_service.get_temporary_override.assert_called()
page_service.get_page.assert_called_with("p1")
time_service.get_current_time.assert_called()
# Every board-scoped write validated the board through the shared helper.
assert require_board.call_count == 4, require_board.call_args_list

assert "src.api_server" not in sys.modules, (
    "a schedules handler imported src.api_server — the call-time seam regrew"
)
print("DECOUPLED")
"""


def test_schedules_router_serves_every_route_without_importing_api_server():
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DECOUPLED" in result.stdout


def test_schedules_router_source_declares_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the module's AST, so an ``import api_server`` hidden inside a
    rarely-taken ``except`` branch fails the build too.
    """
    import ast

    tree = ast.parse((REPO_ROOT / "src" / "schedules" / "routes.py").read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "api_server" in a.name]
        elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
            offenders.append(node.module)

    assert offenders == [], f"src/schedules/routes.py imports api_server: {offenders}"
