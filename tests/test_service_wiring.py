"""Contract test: service calls in client-facing surfaces must actually exist.

Issue #1559 — the MCP tool ``set_active_page`` called
``ConfigManager.set_active_page()``, a method that has never existed. The tool
caught its own ``AttributeError`` and returned it as an error string, so it
failed silently for every user, in every release, while its unit test passed.

The test passed because it asserted against ``MagicMock()``, which conjures any
attribute on access. A mock that agrees with whatever you call on it cannot
tell you that production code is calling into thin air.

Two things guard against that now:

1. ``tests/test_mcp_server.py`` builds its service mocks with
   ``create_autospec()``, so a phantom method raises instead of passing.
   That covers the code paths tests actually execute.
2. This module, which covers the rest. It parses each surface's AST, resolves
   every ``svc = get_x_service(); svc.method(...)`` call against the real class
   behind ``get_x_service``, and fails if the attribute does not exist —
   whether or not any test ever calls that tool.

The same scan found a second live bug in the same commit: ``set_schedule_mode``
called ``ScheduleService.set_schedule_enabled()``, which lives on
``SettingsService``. Nobody had reported it.

Scope: surfaces where a lazily-imported singleton is called by name and a typo
or a moved method degrades into a runtime error string rather than a crash.
"""

from __future__ import annotations

import ast
import importlib
import types
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

# Surfaces scanned. Each is a client-facing command layer that resolves service
# singletons by lazy import and swallows exceptions into an error response.
SCANNED_MODULES = [
    "src/mcp_server.py",
    "src/mqtt/commands.py",
    # #1764: the mutating MCP tool bodies moved into the shared operation
    # layer, which is now the surface that resolves service singletons by
    # lazy import and swallows exceptions into an error envelope — exactly
    # the failure mode this scan exists to catch.
    "src/ops/executors.py",
]

# A scan that resolves nothing passes vacuously. If the import or call style in
# these modules changes such that the analyzer stops recognizing it, this floor
# fails and tells us the test went blind rather than quietly finding nothing.
MIN_RESOLVED_CALLS = {
    # Dropped 35 -> 34 in #1588: the mutating plugin tools now delegate to the
    # REST handlers instead of calling PluginRegistry themselves, so there is
    # one fewer directly-resolvable service call in this module. Dropped
    # 34 -> 33 in #1741 for the same reason: update_plugin no longer calls
    # registry.reload_plugin() itself, it awaits the REST handler so the
    # built-in / realpath-containment / .git guards run. Dropped 33 -> 22 in
    # #1764: the mutating tool bodies (11 direct service calls) moved to
    # src/ops/executors.py, which is scanned with its own floor below, so
    # the total across both modules is unchanged. Lower this only alongside
    # a change that genuinely removes a direct service call.
    "src/mcp_server.py": 22,
    "src/mqtt/commands.py": 15,
    "src/ops/executors.py": 11,
}


@dataclass(frozen=True)
class MissingCall:
    """A call to a service attribute that the real class does not define."""

    path: str
    line: int
    func: str
    expr: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line} in {self.func}(): {self.expr} — {self.detail}"


def _own_nodes(fn: ast.AST) -> list[ast.AST]:
    """Every node in ``fn``'s body, not descending into nested functions.

    Required for ``mcp_server.py``: all ~39 tools are nested inside
    ``_build_mcp_server``, and a naive ``ast.walk`` would pool their locals
    into one namespace where ``svc`` means whatever the last tool assigned.
    """
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
    out: list[ast.AST] = []
    stack = [n for n in fn.body if not isinstance(n, nested)]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(c for c in ast.iter_child_nodes(node) if not isinstance(c, nested))
    return out


def _candidate_classes(annotation: object) -> list[type]:
    """Unwrap ``X | None`` / ``Optional[X]`` to the concrete classes.

    ``get_service() -> DisplayService | None`` is the common shape; callers
    null-check and then use it, so the attribute must exist on ``DisplayService``
    and ``None`` is not a counterexample.
    """
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return [a for arg in typing.get_args(annotation) for a in _candidate_classes(arg) if a is not type(None)]
    return [annotation] if isinstance(annotation, type) and annotation is not type(None) else []


def _collect_getters(tree: ast.AST) -> dict[str, str]:
    """Map imported ``get_*`` names to the module they come from."""
    getters: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            module = f"src.{node.module}" if node.level else node.module
            for alias in node.names:
                if alias.name.startswith("get_"):
                    getters[alias.asname or alias.name] = module
    return getters


def _resolve(getter: str, module: str) -> tuple[list[type], str | None]:
    """Resolve a getter to the class(es) it can return, via its return annotation."""
    try:
        mod = importlib.import_module(module)
    except Exception as exc:  # pragma: no cover - import failure is its own signal
        return [], f"cannot import {module}: {exc}"
    fn = getattr(mod, getter, None)
    if fn is None:
        return [], f"{module} has no attribute {getter!r}"
    try:
        hints = typing.get_type_hints(fn)
    except Exception as exc:  # pragma: no cover - unresolvable forward ref
        return [], f"cannot resolve type hints for {getter}: {exc}"
    if "return" not in hints:
        # Unannotated getter: nothing to check against, and not a defect.
        return [], None
    return _candidate_classes(hints["return"]), None


def scan_source(source: str, path: str, getters_scope: dict[str, str] | None = None) -> tuple[list[MissingCall], int]:
    """Find calls to service attributes that don't exist on the real class.

    Returns the findings plus how many attribute accesses were successfully
    resolved and checked — the latter is what proves the scan wasn't a no-op.

    Recognizes both shapes used in the codebase::

        svc = get_page_service()
        svc.list_pages()            # via local binding
        get_page_service().list_pages()   # chained
    """
    tree = ast.parse(source, path)
    getters = getters_scope if getters_scope is not None else _collect_getters(tree)
    findings: list[MissingCall] = []
    checked = 0

    def check(classes: list[type], attr: str, node: ast.AST, func: str, expr: str, err: str | None) -> None:
        nonlocal checked
        if err:
            findings.append(MissingCall(path, node.lineno, func, expr, err))
            return
        if not classes:
            return
        checked += 1
        if not any(hasattr(cls, attr) for cls in classes):
            names = " / ".join(c.__name__ for c in classes)
            findings.append(MissingCall(path, node.lineno, func, expr, f"{names} has no attribute {attr!r}"))

    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = _own_nodes(fn)

        bindings: dict[str, str] = {}
        for node in body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                target = node.value.func
                if isinstance(target, ast.Name) and target.id in getters:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            bindings[t.id] = target.id

        for node in body:
            if not isinstance(node, ast.Attribute):
                continue
            # svc.method
            if isinstance(node.value, ast.Name) and node.value.id in bindings:
                getter = bindings[node.value.id]
                classes, err = _resolve(getter, getters[getter])
                check(classes, node.attr, node, fn.name, f"{node.value.id}.{node.attr}", err)
            # get_x_service().method
            elif (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id in getters
            ):
                getter = node.value.func.id
                classes, err = _resolve(getter, getters[getter])
                check(classes, node.attr, node, fn.name, f"{getter}().{node.attr}", err)

    return findings, checked


# ---------------------------------------------------------------------------
# The analyzer has to be trustworthy before its green result means anything.
# ---------------------------------------------------------------------------

_GOOD_SOURCE = """
from src.settings.service import get_settings_service

def tool():
    svc = get_settings_service()
    svc.set_active_page_id("page-1")
"""

_BAD_SOURCE = """
from src.config_manager import get_config_manager

def tool():
    cm = get_config_manager()
    cm.set_active_page("page-1")
"""

_BAD_CHAINED_SOURCE = """
from src.settings.service import get_settings_service

def tool():
    get_settings_service().set_active_page("page-1")
"""

_NESTED_SOURCE = """
from src.pages.service import get_page_service
from src.settings.service import get_settings_service

def build():
    def tool_a():
        svc = get_page_service()
        return svc.list_pages()

    def tool_b():
        svc = get_settings_service()
        return svc.get_active_page_id()
"""


class TestAnalyzerIsNotVacuous:
    """If these fail, a green wiring scan means nothing."""

    def test_flags_the_call_from_issue_1559(self):
        findings, checked = scan_source(_BAD_SOURCE, "<bad>")

        assert checked == 1
        assert len(findings) == 1
        assert "set_active_page" in findings[0].detail
        assert "ConfigManager" in findings[0].detail

    def test_flags_a_chained_getter_call(self):
        findings, _ = scan_source(_BAD_CHAINED_SOURCE, "<bad-chained>")

        assert len(findings) == 1
        assert "SettingsService" in findings[0].detail

    def test_accepts_a_method_that_exists(self):
        findings, checked = scan_source(_GOOD_SOURCE, "<good>")

        assert findings == []
        assert checked == 1

    def test_does_not_leak_locals_between_sibling_functions(self):
        """``svc`` means a different class in each nested tool."""
        findings, checked = scan_source(_NESTED_SOURCE, "<nested>")

        assert findings == []
        assert checked == 2

    def test_optional_return_resolves_to_the_concrete_class(self):
        """``get_service() -> DisplayService | None`` must not degrade to Union."""
        from src.api_server import get_service

        classes, err = _resolve("get_service", "src.api_server")

        assert err is None
        assert get_service is not None
        assert classes, "Optional[...] unwrapped to nothing — every call would be skipped"
        assert type(None) not in classes


# ---------------------------------------------------------------------------
# The actual contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", SCANNED_MODULES)
def test_service_calls_resolve_to_real_methods(path):
    """Every service method a client surface calls must exist on the real class."""
    pytest.importorskip("mcp", reason="mcp package not installed")

    findings, checked = scan_source(Path(path).read_text(), path)

    assert checked >= MIN_RESOLVED_CALLS[path], (
        f"only resolved {checked} service calls in {path} (expected >= {MIN_RESOLVED_CALLS[path]}). "
        "The analyzer has likely stopped recognizing this module's call style — "
        "a low count makes this test pass without checking anything."
    )
    assert not findings, "Calls to methods that do not exist:\n" + "\n".join(f"  {f}" for f in findings)
