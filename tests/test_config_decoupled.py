"""The config router must not depend on ``src.api_server`` (Phase 2 §2.3).

The extraction commit moved the eleven ``/config`` handlers out of the
10k-line ``src/api_server.py`` but left nine call-time
``from src.api_server import ...`` statements behind, purely so the suite's
``patch("src.api_server.<name>")`` targets kept resolving. That is not an
extraction: importing the router was clean, but *serving a request* pulled the
whole module — its route table, its background tasks, its MCP mount — back in,
and the 2026-09 audit counted those seams going up 4.2x across Phase 1.

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives every handler that has a collaborator to stub end to end against
the canonical seams (``src.config_api.routes.<name>``), asserts the stubs
really were driven — so a handler that silently no-op'd could not pass — and
then asserts ``src.api_server`` never entered ``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes even with every one of them still
in place.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import asyncio
import sys
from unittest.mock import MagicMock, patch

import src.config_api.routes as routes
from src.config_api.models import BoardConfigUpdate, BoardScanRequest, GeneralConfigUpdate

assert "src.api_server" not in sys.modules, "importing the config router must not import api_server"


def call(coro):
    return asyncio.run(coro)


class FakeResponse:
    def __init__(self):
        self.headers = {}


config_manager = MagicMock()
config_manager.get_all_masked.return_value = {"board": {"local_api_key": "***"}}
config_manager.get_general.return_value = {"timezone": "UTC", "refresh_interval_seconds": 60}
config_manager.set_general.return_value = True
config_manager.validate.return_value = (True, [])
config_manager.get_board.return_value = {"api_mode": "local", "local_api_key": "k", "host": "h"}

transitions = MagicMock()
transitions.strategy = "column"
transitions.step_interval_ms = 100
transitions.step_size = 1

settings_service = MagicMock()
settings_service.get_transition_settings.return_value = transitions
settings_service.get_board_settings.return_value.boards = [
    {"id": "b1", "device_type": "flagship", "host": "192.0.2.4", "local_api_key": "stored"}
]

service = MagicMock()

with (
    patch("src.config_api.routes.get_config_manager", return_value=config_manager),
    patch("src.config_api.routes.get_settings_service", return_value=settings_service),
    patch("src.config_api.routes.primary_board_entry", return_value={"host": "192.0.2.4", "local_api_key": "stored"}),
    patch("src.config_api.routes.reinitialize_board_clients") as reinit,
    patch("src.config_api.routes.get_service", return_value=service),
    patch("src.config_api.routes.reset_time_service") as reset_clock,
    patch("src.system.mdns.scan_for_boards", return_value=[]),
):
    full = call(routes.get_full_config())
    assert full["board"]["local_api_key"] == "***", full

    board = call(routes.get_board_config(FakeResponse()))
    assert board.config.local_api_key == "***", board
    assert board.config.host == "192.0.2.4", board

    updated = call(routes.update_board_config(BoardConfigUpdate(host="192.0.2.9"), FakeResponse()))
    assert updated.status == "success", updated

    reset = call(routes.reset_board_config())
    assert reset.status == "reset", reset

    verdict = call(routes.validate_config())
    assert verdict.is_first_run is False, verdict

    scanned = call(routes.scan_for_boards(BoardScanRequest(timeout=1.0)))
    assert scanned.boards == [], scanned

    # get_general_config hands FastAPI the stored dict; response_model
    # validation happens at serialization, not here.
    general = call(routes.get_general_config())
    assert general["timezone"] == "UTC", general

    saved = call(routes.update_general_config(GeneralConfigUpdate(timezone="Europe/Berlin")))
    assert saved.timezone == "Europe/Berlin", saved

# Not vacuous: the handlers really drove their collaborators.
config_manager.get_all_masked.assert_called_once()
config_manager.reset_board_config.assert_called_once()
config_manager.validate.assert_called_once()
config_manager.set_general.assert_called_once()
settings_service.set_boards.assert_called()
service.reinitialize_board_client.assert_called_once()
reinit.assert_called_once()
reset_clock.assert_called_once()

assert "src.api_server" not in sys.modules, "a config handler imported src.api_server — the call-time seam regrew"
print("DECOUPLED")
"""


def test_config_router_serves_its_routes_without_importing_api_server():
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


def test_config_router_source_declares_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the module's AST, so an ``import api_server`` hidden inside a
    rarely-taken ``except`` branch fails the build too.
    """
    offenders: list[str] = []
    for name in ("routes.py", "models.py", "__init__.py"):
        tree = ast.parse((REPO_ROOT / "src" / "config_api" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{name}: {a.name}" for a in node.names if "api_server" in a.name]
            elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
                offenders.append(f"{name}: {node.module}")

    assert offenders == [], f"src/config_api/ imports api_server: {offenders}"
