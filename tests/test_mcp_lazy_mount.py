"""The MCP server is mounted eagerly but imported lazily.

``src/api_server.py`` used to call ``build_streamable_http_app()`` at module
scope, which dragged the whole ``mcp`` package into every boot whether or not
anyone spoke MCP — measured at +434 ms of import time and +34.7 MB RSS (a
third of the process) on a warm CPython. On a Raspberry Pi that is seconds of
"did it survive the power cut?" for a feature most installs never touch.

Both halves of the contract need holding down, because either one alone is
easy to satisfy by accident:

1. importing the app must NOT import ``mcp`` — and the ``/mcp`` Mount must
   still be in the route table, so the deferral is invisible to the OpenAPI
   schema and to ``tests/golden/api_routes.json``;
2. a real request to ``/api/mcp/`` must still be served by a working MCP
   server, which is what makes the deferral a deferral and not a removal.

Both run in a **subprocess**: an in-process ``'mcp' not in sys.modules``
assertion is vacuous the moment any earlier test in the session imports it,
and ~10 test modules do.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(code: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT),
        "FIESTABOARD_DATA_DIR": str(tmp_path),
        "FIESTABOARD_AUTH_ENABLED": "false",
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_importing_the_app_does_not_import_the_mcp_package(tmp_path):
    """Boot cost: the ``mcp`` package stays out of ``sys.modules``."""
    code = (
        "import sys\n"
        "import src.api_server\n"
        "mcp_mods = sorted(m for m in sys.modules if m == 'mcp' or m.startswith('mcp.'))\n"
        "assert not mcp_mods, mcp_mods\n"
        "assert 'src.mcp_server' not in sys.modules\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, "importing src.api_server pulled in mcp:\n" + result.stdout + result.stderr


def test_the_mcp_mount_is_registered_without_importing_mcp(tmp_path):
    """Route table parity: the deferral must not cost the ``/mcp`` mount."""
    code = (
        "import sys\n"
        "from starlette.routing import Mount\n"
        "from src.api_server import app\n"
        "mounts = [r for r in app.routes if isinstance(r, Mount) and r.path == '/mcp']\n"
        "assert len(mounts) == 1, [getattr(r, 'path', r) for r in app.routes]\n"
        "assert mounts[0].name is None, mounts[0].name\n"
        "assert 'mcp' not in sys.modules\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_first_request_activates_a_working_mcp_server(tmp_path):
    """The deferral is a deferral: ``/api/mcp/`` still answers JSON-RPC.

    Run in the same subprocess as the "not imported" assertion so the two
    halves are proven about one process: nothing imported ``mcp``, then the
    request did, and the handshake succeeded.
    """
    code = (
        "import sys\n"
        "from fastapi.testclient import TestClient\n"
        "from src.api_server import app\n"
        "assert 'mcp' not in sys.modules\n"
        "with TestClient(app) as client:\n"
        "    r = client.post(\n"
        "        '/api/mcp/',\n"
        "        json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {\n"
        "            'protocolVersion': '2025-06-18', 'capabilities': {},\n"
        "            'clientInfo': {'name': 'pytest', 'version': '0'}}},\n"
        "        headers={'Accept': 'application/json, text/event-stream',\n"
        "                 'Content-Type': 'application/json'},\n"
        "    )\n"
        "assert r.status_code == 200, (r.status_code, r.text)\n"
        "assert r.json()['result']['serverInfo']['name'] == 'FiestaBoard', r.text\n"
        "assert 'mcp' in sys.modules\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
