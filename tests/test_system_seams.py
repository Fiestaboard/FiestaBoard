"""The system router stands on its own (Phase 2 §2 step 3, spec §4).

Phase 1 extracted `/version` + `/system/*` into `src/system/` but left every
collaborator resolved through ``src.api_server`` at call time, so the module
was extracted on paper and coupled in fact — and the audit measured the
call-time seam count going *up* 4.2x across the codebase because of exactly
this pattern.

The exit criterion for `next` -> `main` is "zero call-time api_server imports
in router modules, asserted by test". This file is the system domain's half of
that assertion. It is deliberately a *subprocess* check: an in-process
``'src.api_server' not in sys.modules`` assertion is vacuous once any earlier
test in the session has imported the app.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_DIR = REPO_ROOT / "src" / "system"


def test_importing_the_system_router_does_not_pull_in_api_server():
    """A fresh interpreter can import the router without the monolith."""
    code = (
        "import sys\n"
        "import src.system.routes\n"
        "assert 'src.api_server' not in sys.modules, sorted(\n"
        "    m for m in sys.modules if m.startswith('src.')\n"
        ")\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "importing src.system.routes dragged src.api_server in:\n" + result.stdout + result.stderr
    )


def test_importing_the_system_update_service_does_not_pull_in_api_server():
    """Same for the service — it owned two api_server read-back seams."""
    code = (
        "import sys\n"
        "import src.system.update_service\n"
        "assert 'src.api_server' not in sys.modules, sorted(\n"
        "    m for m in sys.modules if m.startswith('src.')\n"
        ")\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "importing src.system.update_service dragged src.api_server in:\n" + result.stdout + result.stderr
    )


def test_no_module_in_src_system_imports_api_server_at_all():
    """Not at module level, and not inside a handler either.

    The subprocess checks above only see module-level imports; a call-time
    ``from src.api_server import ...`` inside a route body would sail past
    them and re-open the seam on the next handler someone edits.
    """
    offenders: list[str] = []
    for path in sorted(SYSTEM_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [a.name for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if "api_server" in module or any("api_server" in n for n in names):
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], "src/system/ must not import src.api_server:\n  " + "\n  ".join(offenders)


def test_api_server_no_longer_re_exports_the_system_service_for_tests():
    """The re-export list is what api_server *uses*, not a patch surface.

    Before the slice, ``api_server`` re-imported all 41 update-service names
    plus all 9 system models under ``# noqa: F401`` purely so
    ``patch("src.api_server.<name>")`` would resolve. Those are ceremony: if
    one comes back with no reader in this module, this test says so.
    """
    api_server_src = (REPO_ROOT / "src" / "api_server.py").read_text(encoding="utf-8")
    tree = ast.parse(api_server_src)

    imported: dict[str, int] = {}
    import_lines: set[int] = set()
    for node in ast.walk(tree):
        # ``from .system.update_service import X`` parses as level=1,
        # module="system.update_service" — rebuild the written form.
        written = "." * getattr(node, "level", 0) + (getattr(node, "module", None) or "")
        if isinstance(node, ast.ImportFrom) and written.startswith(".system"):
            for alias in node.names:
                imported[alias.asname or alias.name] = node.lineno
            for line in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                import_lines.add(line)

    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.lineno not in import_lines}
    dead = sorted(f"{name} (line {line})" for name, line in imported.items() if name not in used)
    assert dead == [], (
        "src/api_server.py imports these names from src/system/ and never uses them. "
        "A re-export that exists only as a test patch target is the seam this slice "
        "retired — patch src.system.update_service.<name> instead:\n  " + "\n  ".join(dead)
    )
