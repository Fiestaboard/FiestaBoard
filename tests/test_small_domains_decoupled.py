"""The slice-8 routers must not depend on ``src.api_server`` (Phase 2 §2.3).

Six small domains — displays, templates, triggers, transitions, panels and
staff-picks — moved out of the 10k-line ``src/api_server.py`` in this PR. The
failure mode the 2026-09 audit measured is an extraction that *looks* clean
because importing the router works, while every handler still does a call-time
``from src.api_server import ...`` so that the suite's
``patch("src.api_server.<name>")`` targets keep resolving. Serving one request
then drags the whole app module — its route table, its background threads, its
MCP mount — back into the process.

Each test below runs in a **fresh interpreter**: it imports one router, drives
its handlers end to end against stubs patched at the router's own binding
(``src.<domain>.routes.<name>``), asserts the stubs really were driven (so a
handler that silently no-op'd could not pass), and only then asserts
``src.api_server`` never entered ``sys.modules``.

A module-level import check alone would be a much weaker claim: the seams are
call time, so importing the module passes with every one of them still there.
That is why each script drives the handlers before it looks at ``sys.modules``,
and why :func:`test_no_slice_8_router_imports_api_server_anywhere` adds a
static AST backstop over the branches the drivers do not reach.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every router this slice extracted, in the order the PR converts them.
SLICE_8_ROUTERS = ("src/displays/routes.py",)


def _run(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "DECOUPLED" in result.stdout


DISPLAYS_SCRIPT = r"""
import asyncio
import sys
from unittest.mock import MagicMock, patch

import src.displays.routes as routes
from src.displays.models import DisplayRawBatchRequest
from src.displays.service import DisplayResult

assert "src.api_server" not in sys.modules, "importing the displays router must not import api_server"

available = DisplayResult(
    display_type="weather", formatted="SUNNY 72F", raw={"temp": 72}, available=True, error=None
)

display_service = MagicMock()
display_service.get_available_displays.return_value = [
    {"type": "weather", "available": True, "description": "Weather", "source": "plugin"}
]
display_service.get_display.return_value = available

settings_service = MagicMock()
settings_service.should_send_to_board.return_value = False
settings_service.get_output_settings.return_value = MagicMock(target="ui")

response = MagicMock()
response.headers = {}

with (
    patch("src.displays.routes.get_display_service", return_value=display_service),
    patch("src.displays.routes.get_settings_service", return_value=settings_service),
    patch("src.displays.routes.get_service", return_value=MagicMock()),
):
    listed = asyncio.run(routes.list_displays())
    assert listed.total == 1, listed
    one = asyncio.run(routes.get_display("weather"))
    assert one.message == "SUNNY 72F", one
    raw = asyncio.run(routes.get_display_raw("weather", response))
    assert raw.data == {"temp": 72}, raw
    batch = asyncio.run(routes.get_displays_raw_batch(DisplayRawBatchRequest(display_types=["weather"])))
    assert batch.total == 1, batch
    sent = asyncio.run(routes.send_display("weather"))
    assert sent.sent_to_board is False, sent
    assert sent.target == "ui", sent

display_service.get_available_displays.assert_called_once()
assert display_service.get_display.call_count == 4
settings_service.get_output_settings.assert_called_once()

assert "src.api_server" not in sys.modules, "a displays handler imported src.api_server"
print("DECOUPLED")
"""


def test_displays_router_serves_every_route_without_importing_api_server():
    _run(DISPLAYS_SCRIPT)


@pytest.mark.parametrize("module_path", SLICE_8_ROUTERS)
def test_no_slice_8_router_imports_api_server_anywhere(module_path):
    """A static backstop over every branch, not just the exercised ones.

    The subprocess drivers can only catch a seam on a path they drive. This
    walks the module's AST, so an ``import api_server`` hidden inside a rarely
    taken ``except`` branch fails the build too.
    """
    tree = ast.parse((REPO_ROOT / module_path).read_text())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [alias.name for alias in node.names if "api_server" in alias.name]
        elif isinstance(node, ast.ImportFrom) and "api_server" in (node.module or ""):
            offenders.append(node.module)

    assert offenders == [], f"{module_path} imports api_server: {offenders}"
