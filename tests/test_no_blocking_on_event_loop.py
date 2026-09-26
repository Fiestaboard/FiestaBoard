"""Blocking work must not run on the event loop.

Every handler in this app is ``async def``, so anything blocking called
directly from one stalls the WHOLE process for its duration — every other
request, the health check, the MCP stream. The template routes were the worst
of them: ``GET /templates/variables`` and both render endpoints ran a
fetch-all ``build_template_context``, which waits on external HTTP for up to
the full context-build budget.

Two kinds of test here, because neither alone is enough:

* **behavioural** — the blocking callable is replaced by a probe that asks
  whether a loop is running on the thread it was called from. On the event
  loop thread ``asyncio.get_running_loop()`` succeeds; on a worker thread it
  raises. That is an exact answer, not a timing measurement, so it cannot
  flake and cannot pass by accident.
* **a ratchet** — an AST scan counting blocking calls that appear directly in
  an ``async def`` body (not inside a nested ``def`` that some ``to_thread``
  will run). The behavioural tests cover the routes we fixed; the ratchet is
  what stops a new one appearing next to them.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SRC = Path(__file__).resolve().parent.parent / "src"


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


class LoopThreadViolation(AssertionError):
    """Raised from inside a probe that finds itself on the event loop."""


def off_loop(return_value):
    """A stand-in that fails loudly if it is called on the event loop thread."""

    def probe(*_args, **_kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return return_value() if callable(return_value) else return_value
        raise LoopThreadViolation("blocking work ran on the event loop thread")

    return probe


# ---------------------------------------------------------------------------
# Behavioural: the routes that fetch plugin data
# ---------------------------------------------------------------------------


def test_templates_variables_builds_its_context_off_the_loop(client, monkeypatch):
    from src.plugins.registry import PluginRegistry

    monkeypatch.setattr(PluginRegistry, "get_all_variables_with_metadata", off_loop(dict))

    response = client.get("/templates/variables")

    assert response.status_code == 200
    assert response.json()["variable_metadata"] == {}


def test_templates_render_fetches_off_the_loop(client, monkeypatch):
    from src.plugins.registry import PluginRegistry

    monkeypatch.setattr(PluginRegistry, "build_template_context", off_loop(dict))

    response = client.post("/templates/render", json={"template": ["{{weather.temperature}}"]})

    assert response.status_code == 200


def test_templates_render_live_fetches_off_the_loop(client, monkeypatch):
    from src.plugins.registry import PluginRegistry

    monkeypatch.setattr(PluginRegistry, "build_template_context", off_loop(dict))

    response = client.post("/templates/render/live", json={"template": ["{{weather.temperature}}"]})

    assert response.status_code == 200


def test_display_get_fetches_off_the_loop(client, monkeypatch):
    from src.displays.service import DisplayResult
    from src.displays.service import DisplayService as DisplaysService

    stub = DisplayResult(display_type="date_time", formatted="STUB", raw={}, available=True)
    monkeypatch.setattr(DisplaysService, "get_display", off_loop(stub))

    response = client.get("/displays/date_time")

    assert response.status_code == 200
    assert response.json()["message"] == "STUB"


# ---------------------------------------------------------------------------
# Demand-driven render: /templates/render must not fetch every plugin
# ---------------------------------------------------------------------------


def test_templates_render_fetches_only_the_plugins_the_template_names(client, monkeypatch):
    """Rendering four variables must not fetch every installed plugin."""
    from src.plugins.registry import PluginRegistry

    seen: list = []

    def spy(self, board=None, plugin_ids=None, include_trigger_plugins=True, fingerprints=None):
        seen.append(plugin_ids)
        return {}

    monkeypatch.setattr(PluginRegistry, "build_template_context", spy)

    response = client.post("/templates/render", json={"template": ["{{weather.temperature}}"]})

    assert response.status_code == 200
    assert seen, "the render did not build a context at all"
    assert seen[0] == {"weather"}, f"render fetched {seen[0]} instead of just the referenced plugin"


def test_a_formula_template_still_falls_back_to_fetching_everything(client, monkeypatch):
    """A formula's variable owners are not statically knowable — fetch all."""
    from src.plugins.registry import PluginRegistry

    seen: list = []

    def spy(self, board=None, plugin_ids=None, include_trigger_plugins=True, fingerprints=None):
        seen.append(plugin_ids)
        return {}

    monkeypatch.setattr(PluginRegistry, "build_template_context", spy)

    response = client.post("/templates/render", json={"template": ["{{= weather.temperature + 1 }}"]})

    assert response.status_code == 200
    assert seen and seen[0] is None, f"formula render narrowed the fetch to {seen[0]}"


# ---------------------------------------------------------------------------
# The ratchet
# ---------------------------------------------------------------------------

BLOCKING_NAMES = {
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "http_requests.get",
    "http_requests.post",
    "build_template_context",
    "get_all_variables_with_metadata",
    "get_available_variables",
    "read_current_message",
    "send_characters",
    "get_display",
    "render_lines",
}
BOARD_RENDER_RECEIVERS = {"board_client", "vb_client", "client"}

# ``src/v1`` is a separate slice; its one remaining site is tracked there.
KNOWN_REMAINING = {("src/v1/routes_plugins.py", "get_display")}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class _LoopScan(ast.NodeVisitor):
    """Collect calls made directly in an ``async def`` body."""

    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []
        self._in_async = 0

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        outer, self._in_async = self._in_async, self._in_async + 1
        for child in node.body:
            self.visit(child)
        self._in_async = outer

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # A nested sync def is what gets handed to to_thread / run_board_send.
        outer, self._in_async = self._in_async, 0
        for child in node.body:
            self.visit(child)
        self._in_async = outer

    def visit_Lambda(self, node: ast.Lambda) -> None:
        outer, self._in_async = self._in_async, 0
        self.generic_visit(node)
        self._in_async = outer

    def visit_Await(self, node: ast.Await) -> None:
        return  # awaited work is off the loop by construction

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_async:
            name = _dotted(node.func)
            tail = name.rsplit(".", 1)[-1]
            head = name.rsplit(".", 2)[0] if "." in name else ""
            if (
                name in BLOCKING_NAMES
                or tail in BLOCKING_NAMES
                or (tail == "render" and head in BOARD_RENDER_RECEIVERS)
            ):
                self.hits.append((node.lineno, tail))
        self.generic_visit(node)


def _scan_src() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        scan = _LoopScan()
        scan.visit(ast.parse(path.read_text(encoding="utf-8")))
        rel = path.relative_to(SRC.parent).as_posix()
        for _lineno, name in scan.hits:
            found.add((rel, name))
    return found


def test_no_new_blocking_call_appears_directly_in_an_async_handler():
    """16 sites before this change; 1, in another slice, after it."""
    assert _scan_src() == KNOWN_REMAINING


def test_the_ratchet_can_actually_see_a_blocking_call():
    """Non-vacuity: the scanner must flag the thing it claims to flag."""
    source = "async def handler():\n    return requests.get('http://x')\n"
    scan = _LoopScan()
    scan.visit(ast.parse(source))
    assert [name for _lineno, name in scan.hits] == ["get"]


def test_the_ratchet_does_not_flag_work_handed_to_a_thread():
    source = (
        "async def handler():\n    def _work():\n        return requests.get('http://x')\n    return await run(_work)\n"
    )
    scan = _LoopScan()
    scan.visit(ast.parse(source))
    assert scan.hits == []
