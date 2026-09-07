"""The last extracted routers must not drag ``src.api_server`` into the process.

Phase 2 §2.3: an extracted router that reaches back into the app module for a
collaborator re-imports the whole application — its route table, its background
tasks and every module it touches — which is how the 2026-09 audit counted the
import seams going *up* 4.2x during Phase 1. This asserts the seam is gone in a
fresh interpreter rather than trusting a code review of the import block.

``src/board_api/routes.py`` is the interesting one: it is the last domain whose
collaborators (the pause and silence guards, the service singleton, the
out-of-band write notifier) all lived in ``api_server`` at the start of Phase 2.

``src/ai/page_routes.py`` is the last router extracted at all — the three
``/pages/ai`` handlers. Both ``src/ai`` routers carry the same ``ai`` tag: one
domain, two URL prefixes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

ROUTERS = [
    ("src.network.routes", "network"),
    ("src.service_api.routes", "service"),
    ("src.board_api.routes", "board"),
    ("src.mqtt.routes", "mqtt"),
    ("src.backup.routes", "backup"),
    ("src.plugin_support.routes", "plugin-support"),
    ("src.ai.routes", "ai"),
    ("src.ai.page_routes", "ai"),
]


@pytest.mark.parametrize("module,_tag", ROUTERS, ids=[m for m, _ in ROUTERS])
def test_router_does_not_import_api_server(module, _tag):
    code = (
        f"import sys; import {module}; "
        "assert 'src.api_server' not in sys.modules, "
        "sorted(m for m in sys.modules if m.startswith('src.'))"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module,tag", ROUTERS, ids=[m for m, _ in ROUTERS])
def test_router_is_tagged_so_the_conventions_ratchet_sees_it(module, tag):
    """An untagged router is invisible to the ratchet — silently unconverted."""
    import importlib

    router = importlib.import_module(module).router
    assert router.tags == [tag]


def test_the_display_loop_controls_are_registered_by_the_app_module():
    """``POST /start`` / ``POST /stop`` write api_server's lifecycle state
    through this seam; if the registration is ever dropped, both endpoints
    silently stop doing anything."""
    import src.api_server  # noqa: F401  (registers at import)
    import src.display_runtime as runtime

    assert runtime._loop_spawn is not None
    assert runtime._loop_halt is not None
