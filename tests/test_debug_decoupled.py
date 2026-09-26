"""The debug router must not depend on ``src.api_server`` (Phase 2 §2.3).

The extraction commit moved twelve handlers out of the 10k-line
``src/api_server.py`` but left thin call-time proxies behind, purely so the
suite's ``patch("src.api_server.<name>")`` targets kept resolving. That is not
an extraction: importing the router was clean, but *serving a request* pulled
the whole module — its route table, its background tasks, its MCP mount — back
in, and the 2026-09 audit counted those seams going up 4.2x across Phase 1.

The conversion commit gave the homeless collaborators real modules
(``src/display_runtime.py`` for the display-service runtime and the board
helpers, ``src/log_store.py`` for the log ring and its reader) and pointed the
router at those.

This test pins the fix the honest way. In a fresh interpreter it imports the
router, drives all twelve handlers end to end against patched canonical seams,
asserts the stubs really were driven — so a handler that silently no-op'd
could not pass — and only then asserts ``src.api_server`` never entered
``sys.modules``.

Importing the module alone would be a much weaker claim: the seams were call
time, so a module-level import check passes with every one of them still in
place.
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

import src.debug.routes as routes
from src.debug.models import BoardFillRequest

assert "src.api_server" not in sys.modules, "importing the debug router must not import api_server"


def call(coro):
    return asyncio.run(coro)


CACHE = {
    "has_cached_text": True,
    "has_cached_characters": False,
    "skip_unchanged_enabled": True,
    "cached_text_preview": "HI",
}

board = MagicMock()
board.send_characters.return_value = (True, True)
board.test_connection.return_value = True
board.get_cache_status.return_value = dict(CACHE)
board.last_send_throttled = False

settings = MagicMock()
settings.should_send_to_board.return_value = True
settings.is_paused.return_value = False

service = MagicMock()
service.vb_client = board
service.board_clients = {}
service.check_and_send_active_page_with_status.return_value = (True, None)

dims = MagicMock()
dims.rows, dims.cols = 6, 22

diagnostics = {
    "dns": {"ok": True},
    "internet": {"ok": True},
    "vestaboard": {"ok": True, "mode": "local", "steps": {}},
    "overall_ok": True,
    "recommendations": [],
}

with (
    patch("src.display_runtime._get_board_client", return_value=board),
    patch("src.display_runtime.get_settings_service", return_value=settings),
    patch("src.display_runtime.get_service", return_value=service),
    patch("src.display_runtime._board_is_paused", return_value=False),
    patch("src.display_runtime._get_first_board_dims", return_value=dims),
    patch("src.display_runtime._note_out_of_band_write") as noted,
    patch("src.display_runtime._primary_board_entry", return_value={"host": "192.0.2.10"}),
    patch("src.display_runtime._primary_connection_info", return_value=("local", "192.0.2.10")),
    patch("src.display_runtime._send_with_status", return_value=(True, None)) as sent,
    patch("src.log_store._read_logs_from_files", return_value=([], 0, False)) as read_logs,
    patch("src.network_diagnostics.run_full_diagnostics", return_value=diagnostics) as diag,
):
    assert call(routes.debug_blank_board()).message == "Board blanked successfully"
    assert call(routes.debug_fill_board(BoardFillRequest(character_code=7))).message.endswith("character 7")
    info = call(routes.debug_show_info())
    assert info.debug_info.startswith("DEBUG INFO"), info
    probe = call(routes.debug_test_connection())
    assert probe.connected is True, probe
    assert call(routes.debug_clear_cache()).message.startswith("Cache cleared")
    assert call(routes.debug_get_cache_status())["has_cached_text"] is True
    sysinfo = call(routes.debug_get_system_info())
    assert sysinfo.board_ip == "192.0.2.10", sysinfo
    assert sysinfo.service_running is False, "no api_server means no running probe, so: not running"
    assert call(routes.debug_network_diagnostics())["overall_ok"] is True
    assert call(routes.get_cache_status())["has_cached_text"] is True
    assert call(routes.clear_cache()).message.startswith("Cache cleared")
    refreshed = call(routes.force_refresh())
    assert refreshed.sent is True, refreshed
    logs = call(routes.get_logs(limit=5, offset=0, level="ERROR", search=None))
    assert logs.filters.level == "ERROR", logs

# Not vacuous: the handlers really drove their collaborators.
assert board.send_characters.call_count == 3, board.send_characters.call_count
board.test_connection.assert_called_once()
# /debug/clear-cache, /clear-cache, and the forced pass inside /force-refresh.
assert board.clear_cache.call_count == 3, board.clear_cache.call_count
assert board.get_cache_status.call_count == 3, board.get_cache_status.call_count
assert noted.call_count == 3, noted.call_count
sent.assert_called_once()
read_logs.assert_called_once()
diag.assert_called_once()
service.invalidate_all_board_content.assert_called_once()

assert "src.api_server" not in sys.modules, "a debug handler imported src.api_server — the call-time seam regrew"
print("DECOUPLED")
"""


def test_debug_router_serves_every_route_without_importing_api_server():
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


def _api_server_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if "api_server" in a.name]
        elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
            offenders.append(node.module)
    return offenders


def test_debug_module_sources_declare_no_api_server_import():
    """A static backstop over every branch, not just the exercised ones.

    The subprocess test above can only catch a seam on a code path it drives.
    This walks the AST, so an ``import api_server`` hidden inside a
    rarely-taken ``except`` branch fails the build too — and it covers the two
    modules the router now depends on, because a seam in either of them is a
    seam in the router.
    """
    for relative in ("src/debug/routes.py", "src/debug/models.py", "src/display_runtime.py", "src/log_store.py"):
        offenders = _api_server_imports(REPO_ROOT / relative)
        assert offenders == [], f"{relative} imports api_server: {offenders}"
