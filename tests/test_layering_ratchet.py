"""Layering is a build failure, not a diagram.

``docs/internal/reference/ARCHITECTURE.md`` draws four hops — router, service,
storage, disk — and states the rule that keeps them honest: *a service may not
import fastapi, and a router may not open a file.* Until this module existed
the first half was enforced for exactly one domain (``src/plugins``) and the
second half was enforced nowhere, which is how ~1,600 lines of domain logic
came to live in thirteen routers while the document said otherwise.

A rule nothing checks is a wish. These three are checked.

How a domain opts in
--------------------
Append its **package name** (``src/mqtt`` → ``mqtt``) to ``enforced_domains``
in ``tests/layering_manifest.json``, in the PR that makes it comply. Until
then the domain is invisible here: the ratchet is a floor that only ever moves
up. Opting a domain in by *loosening a rule* until it passes defeats the whole
mechanism — leave it out instead, and say so in the PR.

Transport vs. domain modules
----------------------------
Within a domain package ``src/<domain>/``:

* **Transport modules** are ``routes.py``, ``*_routes.py`` and
  ``middleware.py``. Their job *is* HTTP. ASGI middleware is on this list for
  the same structural reason a router is — it exists to read a request and
  short-circuit a response — not because some domain needed it to be.
* **Domain modules** are everything else: ``service.py``, ``models.py``,
  ``storage.py``, ``wifi.py``, ``client.py``, and any subpackage.

The three rules
---------------
``service_no_fastapi``
    No domain module imports ``fastapi`` or ``starlette``. A service that
    knows about ``HTTPException`` cannot be called from MQTT, MCP, the display
    loop or a test without dragging a web framework's error model along.
    Generalised from ``tests/test_plugins_decoupled.py``, which enforced this
    for ``src/plugins/service.py`` alone.
``router_no_file_io``
    No transport module touches the filesystem: no ``open()``, no
    ``Path.read_*``/``write_*``, no ``json.load``/``json.dump`` over a stream,
    no ``os``/``shutil`` filesystem verbs, and no import of a storage module,
    ``src.atomic_io`` or ``src.paths``. Persistence goes through a service so
    that locking, atomic writes and schema migrations happen in one place.
``router_no_domain_logic``
    A **proxy**, and deliberately a crude one — see below.

The proxy for "domain logic", and what it does not catch
--------------------------------------------------------
There is no mechanical definition of domain logic. Rather than invent a
subtle one that cries wolf, this rule caps two size metrics on **every
function defined at module level in a transport module** — decorated handlers
and their private helpers alike:

* body statements ≤ :data:`MAX_HANDLER_STATEMENTS` (docstrings excluded)
* cyclomatic complexity ≤ :data:`MAX_HANDLER_COMPLEXITY` (branch points + 1)

Both thresholds come from the measured distribution over all 240 router
functions in ``src/`` at the time this landed — p50 = 6 statements / cc 3,
p75 = 13 / cc 5, p90 = 25 / cc 10 — so a compliant thin adapter passes today
and the domains the audit flagged do not. The numbers are a floor to ratchet
*down*, never up.

What it catches: a handler that grew a decision tree, a validation cascade, a
retry loop, a frame-cap loop. What it does **not** catch, stated plainly so
nobody mistakes a green run for proof of good layering:

* Logic split across many *small* functions in the router module. Counting
  every module-level function (not only routes) closes the obvious version of
  this — extracting a 40-statement ``_do_the_thing`` helper next to the
  handler fails just as loudly — but ten five-statement helpers pass.
* Logic moved to a *different* non-transport module in the same package and
  called from the router. That is the move the ratchet is trying to
  encourage, so it is a feature; whether the destination is really a service
  is a code-review question.
* Genuinely HTTP-shaped code that happens to be long — a route with fifteen
  query parameters to marshal. Those record a checked-in exception with a
  reason.
* Semantically dense one-liners. A comprehension chain that computes a
  business rule in one statement scores 1.

A crude rule that fires honestly beats a subtle one that cries wolf; a ratchet
that cries wolf gets deleted.
"""

from __future__ import annotations

import ast
import json
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).parent / "layering_manifest.json"

#: The only rule ids an exception entry may name. A typo must fail the build
#: rather than silently excuse nothing (or, worse, look like it did).
RULE_IDS = frozenset(
    {
        "service_no_fastapi",
        "router_no_file_io",
        "router_no_domain_logic",
    }
)

#: Top-level packages a domain module may not import. ``starlette`` is on the
#: list because importing it is importing FastAPI's transport layer under
#: another name.
TRANSPORT_PACKAGES = frozenset({"fastapi", "starlette"})

#: Filenames whose job is HTTP. Everything else in a domain package is a
#: domain module. See the module docstring for why ``middleware.py`` is here.
TRANSPORT_FILENAMES = frozenset({"routes.py", "middleware.py"})

#: Builtins that open a file.
FILE_OPENING_BUILTINS = frozenset({"open"})

#: Method names that are unambiguous filesystem verbs. Deliberately excludes
#: ``exists``/``is_file``/``stat`` — those names collide with domain objects
#: often enough that flagging them would be the false positive that gets this
#: rule deleted. A router that only *probes* the filesystem is a smaller
#: problem than one that reads or writes it.
FILESYSTEM_METHODS = frozenset(
    {
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "mkdir",
        "rmdir",
        "unlink",
        "touch",
        "iterdir",
        "glob",
        "rglob",
        "open",
        "makedirs",
        "listdir",
        "removedirs",
        "rmtree",
        "copyfile",
        "copytree",
        "move",
    }
)

#: ``json.load``/``json.dump`` take a *stream*, so they only appear where a
#: file is already open. ``json.loads``/``dumps`` are string operations and
#: are not flagged.
STREAM_JSON_FUNCTIONS = frozenset({"load", "dump"})

#: Import targets that mean "this module reaches persistence directly". The
#: last path segment is matched, so ``src.pages.storage``, ``.storage`` and
#: ``src.storage`` all count.
PERSISTENCE_MODULE_LEAVES = frozenset({"storage", "atomic_io", "paths"})

#: Thresholds for :func:`check_router_no_domain_logic`. Set from the measured
#: distribution over every router function in ``src/`` (n=240): p75 = 13
#: statements and cc 5, p90 = 25 and cc 10. These sit just above p75, so three
#: quarters of the tree's router functions already comply. Ratchet down, never
#: up.
MAX_HANDLER_STATEMENTS = 15
MAX_HANDLER_COMPLEXITY = 8

#: Nodes that add one decision point each to cyclomatic complexity.
BRANCH_NODES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.comprehension,
    ast.Match,
)

MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Finding:
    """One violation. ``target`` is what an exception entry names."""

    target: str
    message: str

    def __str__(self) -> str:
        return f"{self.target}: {self.message}"


# --------------------------------------------------------------------------
# Walking a domain package
# --------------------------------------------------------------------------


def _is_transport(path: Path) -> bool:
    return path.name in TRANSPORT_FILENAMES or path.name.endswith("_routes.py")


def domain_root(domain: str, root: Path | None = None) -> Path:
    return (root or REPO_ROOT) / "src" / domain


def _modules(domain: str, root: Path | None, transport: bool) -> list[Path]:
    package = domain_root(domain, root)
    if not package.is_dir():
        return []
    return sorted(p for p in package.rglob("*.py") if _is_transport(p) is transport)


def transport_modules(domain: str, root: Path | None = None) -> list[Path]:
    """``routes.py`` / ``*_routes.py`` / ``middleware.py`` in the package."""
    return _modules(domain, root, transport=True)


def domain_modules(domain: str, root: Path | None = None) -> list[Path]:
    """Everything else in the package — service, models, storage, helpers."""
    return _modules(domain, root, transport=False)


def _rel(path: Path, root: Path | None = None) -> str:
    """Repo-relative path; these messages are read in CI logs."""
    base = (root or REPO_ROOT).resolve()
    try:
        return str(path.resolve().relative_to(base))
    except ValueError:  # pragma: no cover - defensive
        return str(path)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --------------------------------------------------------------------------
# Rule 1 — a service may not import fastapi
# --------------------------------------------------------------------------


def _imported_roots(tree: ast.Module) -> list[tuple[int, str]]:
    """``(lineno, dotted_name)`` for every import in the module."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            found.append((node.lineno, node.module or ""))
    return found


def check_service_no_fastapi(domain: str, root: Path | None = None) -> list[Finding]:
    """Flag a domain module that imports a web framework.

    Static, over every module in the package, because a runtime check only
    covers the branches some test happens to drive — the plugins version of
    this test learned that the hard way (``import api_server`` hidden in an
    ``except``).
    """
    findings: list[Finding] = []
    for path in domain_modules(domain, root):
        tree = _parse(path)
        offenders = sorted(
            {name for _lineno, name in _imported_roots(tree) if name.split(".")[0] in TRANSPORT_PACKAGES}
        )
        if offenders:
            findings.append(
                Finding(
                    _rel(path, root),
                    f"imports {', '.join(offenders)} — a domain module must be callable from MQTT, "
                    "MCP, the display loop and a test without a web framework",
                )
            )
    return findings


# --------------------------------------------------------------------------
# Rule 2 — a router may not open a file
# --------------------------------------------------------------------------


def _enclosing_function(tree: ast.Module) -> dict[int, str]:
    """Map every node id to the name of the module-level function holding it.

    Findings are reported against ``path::function`` where possible so an
    exception can excuse one helper rather than a whole router.
    """
    owner: dict[int, str] = {}

    def claim(node: ast.AST, name: str) -> None:
        for child in ast.walk(node):
            owner[id(child)] = name

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            claim(node, node.name)
    return owner


def _fs_offence(node: ast.Call) -> str | None:
    """Name the filesystem operation ``node`` performs, or ``None``."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in FILE_OPENING_BUILTINS:
        return f"{func.id}()"
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr in STREAM_JSON_FUNCTIONS and isinstance(func.value, ast.Name) and func.value.id == "json":
        return f"json.{func.attr}()"
    if func.attr in FILESYSTEM_METHODS:
        return f".{func.attr}()"
    return None


def check_router_no_file_io(domain: str, root: Path | None = None) -> list[Finding]:
    """Flag a transport module that reaches the filesystem itself."""
    findings: list[Finding] = []
    for path in transport_modules(domain, root):
        tree = _parse(path)
        owner = _enclosing_function(tree)
        rel = _rel(path, root)
        seen: set[tuple[str, str]] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                offence = _fs_offence(node)
                if offence is not None:
                    where = owner.get(id(node), "<module>")
                    seen.add((f"{rel}::{where}", f"line {node.lineno}: calls `{offence}`"))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for name in _import_names(node):
                    if name.split(".")[-1] not in PERSISTENCE_MODULE_LEAVES:
                        continue
                    where = owner.get(id(node), "<module>")
                    seen.add(
                        (
                            f"{rel}::{where}",
                            f"line {node.lineno}: imports `{name}` — persistence belongs behind a service",
                        )
                    )
                    break
        findings.extend(
            Finding(target, f"{message} (routers hold HTTP concerns; persistence goes through a service)")
            for target, message in sorted(seen)
        )
    return findings


def _import_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Every dotted target an import statement names, as written.

    Both halves of a ``from X import Y`` matter, because a module can be
    either: ``from .storage import STORE`` names the module in ``X``, while
    ``from src import paths`` names it in ``Y``. The strings keep their
    leading dots so the failure message quotes the source line.
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    prefix = "." * node.level + (node.module or "")
    joiner = "" if prefix.endswith(".") else "."
    return [prefix, *(f"{prefix}{joiner}{alias.name}" for alias in node.names)]


# --------------------------------------------------------------------------
# Rule 3 — a router may not hold domain logic (size proxy)
# --------------------------------------------------------------------------


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def function_metrics(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    """``(statements, cyclomatic_complexity)`` for ``func``'s whole body.

    Nested closures count toward their *enclosing* function: logic hidden in
    an inner ``def`` is still logic the router is holding.
    """
    statements = 0
    branches = 0
    for node in ast.walk(func):
        if isinstance(node, ast.stmt) and node is not func and not _is_docstring(node):
            statements += 1
        if isinstance(node, BRANCH_NODES):
            branches += 1
        elif isinstance(node, ast.BoolOp):
            branches += len(node.values) - 1
    return statements, branches + 1


def check_router_no_domain_logic(domain: str, root: Path | None = None) -> list[Finding]:
    """Flag a module-level function in a transport module that is too big.

    Every module-level function counts, not only the decorated handlers —
    otherwise "move it to a private helper three lines down" is a one-commit
    way around the rule.
    """
    findings: list[Finding] = []
    for path in transport_modules(domain, root):
        tree = _parse(path)
        rel = _rel(path, root)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            statements, complexity = function_metrics(node)
            problems = []
            if statements > MAX_HANDLER_STATEMENTS:
                problems.append(f"{statements} statements (max {MAX_HANDLER_STATEMENTS})")
            if complexity > MAX_HANDLER_COMPLEXITY:
                problems.append(f"cyclomatic complexity {complexity} (max {MAX_HANDLER_COMPLEXITY})")
            if problems:
                findings.append(
                    Finding(
                        f"{rel}::{node.name}",
                        f"line {node.lineno}: {' and '.join(problems)} — "
                        "move the decision-making into the domain's service",
                    )
                )
    return findings


#: The checker behind each rule id, so the manifest validator can ask "does
#: this exception still excuse anything?" using the same code the ratchet runs.
CHECKS: dict[str, typing.Callable[..., list[Finding]]] = {
    "service_no_fastapi": check_service_no_fastapi,
    "router_no_file_io": check_router_no_file_io,
    "router_no_domain_logic": check_router_no_domain_logic,
}


# --------------------------------------------------------------------------
# The ratchet
# --------------------------------------------------------------------------


def _excused(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    """``(target, rule)`` pairs the manifest excuses.

    Tolerant of a malformed entry on purpose: a missing key must surface as a
    :func:`validate_manifest` failure naming the entry, not as a ``KeyError``
    from whichever rule test happened to run first.
    """
    return {(e.get("target"), e.get("rule")) for e in manifest.get("exceptions", []) if isinstance(e, dict)}


def violations(
    rule: str,
    manifest: dict[str, Any] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Every unexcused finding for ``rule`` across the enforced domains."""
    manifest = MANIFEST if manifest is None else manifest
    excused = _excused(manifest)
    found: list[str] = []
    for domain in manifest.get("enforced_domains", []):
        for finding in CHECKS[rule](domain, root):
            if (finding.target, rule) not in excused:
                found.append(str(finding))
    return sorted(found)


def _fix_or_excuse(rule: str) -> str:
    return (
        f'Fix the module, or add a {{"rule": "{rule}", ...}} exception to '
        "tests/layering_manifest.json with a reason a reviewer can argue with:\n  "
    )


def test_enforced_domain_services_do_not_import_fastapi():
    """No domain module in an enforced domain imports fastapi or starlette."""
    offenders = violations("service_no_fastapi")
    assert offenders == [], (
        "A service may not import fastapi (ARCHITECTURE.md, 'The shape of a "
        "request'). A domain module has to stay callable from MQTT, MCP, the "
        "display loop and a test. " + _fix_or_excuse("service_no_fastapi") + "\n  ".join(offenders)
    )


def test_enforced_domain_routers_do_not_touch_the_filesystem():
    """No transport module in an enforced domain opens a file."""
    offenders = violations("router_no_file_io")
    assert offenders == [], (
        "A router may not open a file (ARCHITECTURE.md, 'The shape of a "
        "request'). Persistence goes through a service so locking, atomic "
        "writes and schema migrations happen in one place. "
        + _fix_or_excuse("router_no_file_io")
        + "\n  ".join(offenders)
    )


def test_enforced_domain_routers_hold_no_domain_logic():
    """No router function in an enforced domain exceeds the size proxy."""
    offenders = violations("router_no_domain_logic")
    assert offenders == [], (
        "A router holds HTTP concerns, not domain logic (ARCHITECTURE.md, "
        "'The layers, one paragraph each'). This rule is a size proxy — see "
        "the docstring of tests/test_layering_ratchet.py for exactly what it "
        "does and does not catch. " + _fix_or_excuse("router_no_domain_logic") + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# Guarding the guard
# --------------------------------------------------------------------------


def validate_manifest(manifest: dict[str, Any], root: Path | None = None) -> list[str]:
    """Return every structural problem with ``manifest``.

    An empty ``enforced_domains`` makes the three rules above vacuously true,
    so a typo must never be able to put the manifest back into that state
    unnoticed. Unknown keys, unknown rule ids, duplicate exceptions, domains
    that are not packages, domains with no router, and exceptions naming a
    file the tree does not contain are all build failures.

    So is a **dead exception** — one whose rule already passes on its target.
    It excuses nothing today and silently exempts that target from the rule
    forever, so a later regression on it goes unreported. The sibling
    conventions ratchet accumulated eleven of these through union merges
    before anyone noticed; re-running each rule's own checker here is the only
    thing that stops it happening again.
    """
    problems: list[str] = []

    allowed_top_level = {"_comment", "enforced_domains", "exceptions"}
    unknown_top_level = sorted(set(manifest) - allowed_top_level)
    if unknown_top_level:
        problems.append(f"unknown top-level key(s): {unknown_top_level}")

    domains = manifest.get("enforced_domains")
    if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
        problems.append("enforced_domains must be a list of strings")
        domains = []
    if len(set(domains)) != len(domains):
        problems.append(f"enforced_domains has duplicates: {sorted(domains)}")

    for domain in domains:
        package = domain_root(domain, root)
        if not package.is_dir():
            problems.append(f"enforced domain {domain!r} is not a package under src/ — a typo here enforces nothing")
        elif not transport_modules(domain, root):
            problems.append(
                f"enforced domain {domain!r} has no routes.py — two of the three rules would be vacuous there"
            )

    exceptions = manifest.get("exceptions")
    if not isinstance(exceptions, list):
        problems.append("exceptions must be a list")
        exceptions = []

    live: dict[tuple[str, str], bool] = {}
    for domain in domains:
        for rule, check in CHECKS.items():
            for finding in check(domain, root):
                live[(finding.target, rule)] = True

    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(exceptions):
        where = f"exceptions[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} is not an object")
            continue
        unknown_keys = sorted(set(entry) - {"target", "rule", "reason"})
        if unknown_keys:
            problems.append(f"{where} has unknown key(s): {unknown_keys}")
        target = entry.get("target")
        rule = entry.get("rule")
        reason = entry.get("reason")
        if not isinstance(target, str) or not target:
            problems.append(f'{where} needs a "target" — a module path, optionally "::function"')
            continue
        if rule not in RULE_IDS:
            problems.append(f"{where} names unknown rule {rule!r}; known rules: {sorted(RULE_IDS)}")
        if not isinstance(reason, str) or len(reason.strip()) < 10:
            problems.append(f"{where} ({target}) needs a substantive reason, not {reason!r}")
        if (target, rule) in seen:
            problems.append(f"{where} duplicates the exception for {target} / {rule}")
        seen.add((target, rule))

        module = target.split("::")[0]
        if not ((root or REPO_ROOT) / module).is_file():
            problems.append(f"{where} excuses {module!r}, which is not a file in the tree")
            continue
        module_domain = Path(module).parts[1] if len(Path(module).parts) > 1 else ""
        if module_domain not in domains:
            problems.append(
                f"{where} excuses {target!r}, whose domain {module_domain!r} is not enforced — "
                "dead exceptions rot; delete it or enforce its domain"
            )
        elif rule in RULE_IDS and not live.get((target, rule)):
            problems.append(
                f"{where} excuses {target!r} from {rule!r}, but the rule already passes there — "
                "a dead exception excuses nothing and exempts the target from the rule forever; delete it"
            )
    return problems


def test_layering_manifest_is_well_formed():
    """A typo in the manifest fails the build instead of excusing a rule."""
    problems = validate_manifest(MANIFEST)
    assert problems == [], "tests/layering_manifest.json is malformed:\n  " + "\n  ".join(problems)


def test_the_ratchet_is_not_vacuous():
    """An empty enforced_domains would make all three rules trivially green."""
    domains = MANIFEST["enforced_domains"]
    assert domains, "enforced_domains is empty — the ratchet asserts nothing about the app"
    checked = sum(len(transport_modules(d)) + len(domain_modules(d)) for d in domains)
    assert checked >= 20, f"only {checked} modules are under the ratchet; that is a floor, not a guard"


def test_manifest_rule_ids_match_the_documented_set():
    """The rule ids the doc names are the ones with tests behind them."""
    enforced = {
        "service_no_fastapi": test_enforced_domain_services_do_not_import_fastapi,
        "router_no_file_io": test_enforced_domain_routers_do_not_touch_the_filesystem,
        "router_no_domain_logic": test_enforced_domain_routers_hold_no_domain_logic,
    }
    assert set(enforced) == set(RULE_IDS) == set(CHECKS)


# --------------------------------------------------------------------------
# Proving each rule bites
#
# The three ratchet tests above assert against whatever is in
# ``enforced_domains`` today, so they cannot be their own evidence: if a
# checker were quietly defanged they would still pass. These tests build a
# throwaway ``src/`` tree whose domains break one rule each and assert the
# checkers say so — and, just as importantly, that they stay silent on the
# compliant domain next door.
# --------------------------------------------------------------------------

SAMPLE_TREE: dict[str, str] = {
    # A domain that complies with all three rules.
    "src/tidy/__init__.py": "",
    "src/tidy/service.py": """
from .models import Thing


class TidyService:
    def get(self, thing_id: str) -> Thing:
        return Thing(name=thing_id)
""",
    "src/tidy/models.py": """
from pydantic import BaseModel


class Thing(BaseModel):
    name: str
""",
    "src/tidy/routes.py": """
from fastapi import APIRouter, HTTPException

from .models import Thing
from .service import TidyService

router = APIRouter(tags=["tidy"])


@router.get("/tidy/{thing_id}", response_model=Thing)
async def get_thing(thing_id: str) -> Thing:
    thing = TidyService().get(thing_id)
    if thing is None:
        raise HTTPException(status_code=404, detail="nope")
    return thing
""",
    # An ASGI middleware: transport by definition, so its starlette import is
    # not a rule-1 violation.
    "src/tidy/middleware.py": """
from starlette.middleware.base import BaseHTTPMiddleware


class Guard(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        return await call_next(request)
""",
    # Rule 1: the service imports the web framework.
    "src/leaky/__init__.py": "",
    "src/leaky/routes.py": """
from fastapi import APIRouter

router = APIRouter(tags=["leaky"])


@router.get("/leaky")
async def get_leaky():
    return {}
""",
    "src/leaky/service.py": """
from fastapi import HTTPException


class LeakyService:
    def get(self):
        raise HTTPException(status_code=404, detail="the service picked a status code")
""",
    # Rule 2: the router reads a file, and imports a storage module.
    "src/filey/__init__.py": "",
    "src/filey/storage.py": "STORE = {}\n",
    "src/filey/routes.py": """
import json
from pathlib import Path

from fastapi import APIRouter

from .storage import STORE

router = APIRouter(tags=["filey"])


def _load():
    with open(Path("data/filey.json")) as handle:
        return json.load(handle)


@router.get("/filey")
async def get_filey():
    return _load() or STORE
""",
    # Rule 3: a fat handler, and a fat private helper next to it.
    "src/fatty/__init__.py": "",
    "src/fatty/routes.py": """
from fastapi import APIRouter

router = APIRouter(tags=["fatty"])


def _decide(payload):
    total = 0
    for key, value in payload.items():
        if key == "a":
            total += 1
        elif key == "b":
            total += 2
        elif key == "c":
            total += 3
        elif key == "d":
            total += 4
        elif key == "e":
            total += 5
        elif key == "f":
            total += 6
        elif key == "g":
            total += 7
        else:
            total += value
    return total


@router.post("/fatty")
async def post_fatty(payload: dict):
    return _decide(payload)
""",
    # A handler whose length is fine but whose branching is not: proves the
    # complexity arm is not redundant with the statement arm.
    "src/branchy/__init__.py": "",
    "src/branchy/routes.py": """
from fastapi import APIRouter

router = APIRouter(tags=["branchy"])


@router.get("/branchy")
async def get_branchy(a: int, b: int, c: int, d: int, e: int, f: int, g: int, h: int, i: int):
    return (a if a else 0) + (b if b else 0) + (c if c else 0) + (d if d else 0) + (
        e if e else 0
    ) + (f if f else 0) + (g if g else 0) + (h if h else 0) + (i if i else 0)
""",
    # A domain with no router at all: two of three rules would be vacuous.
    "src/routerless/__init__.py": "",
    "src/routerless/service.py": "VALUE = 1\n",
}


@pytest.fixture(scope="module")
def sample_root(tmp_path_factory) -> Path:
    """A throwaway ``src/`` tree, one broken rule per domain."""
    root = tmp_path_factory.mktemp("layering_sample")
    for relative, source in SAMPLE_TREE.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source.lstrip("\n"), encoding="utf-8")
    return root


def _sample_violations(rule: str, domains: list[str], sample_root: Path) -> list[str]:
    return violations(rule, {"enforced_domains": domains, "exceptions": []}, sample_root)


def test_service_rule_flags_a_service_that_imports_fastapi(sample_root):
    offenders = _sample_violations("service_no_fastapi", ["leaky"], sample_root)
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("src/leaky/service.py: imports fastapi —")


def test_service_rule_ignores_the_router_that_legitimately_imports_fastapi(sample_root):
    """``routes.py`` is where fastapi belongs; flagging it would be absurd."""
    assert _sample_violations("service_no_fastapi", ["tidy"], sample_root) == []


def test_service_rule_ignores_asgi_middleware(sample_root):
    """``middleware.py`` is transport by definition — see the module docstring."""
    offenders = _sample_violations("service_no_fastapi", ["tidy"], sample_root)
    assert [o for o in offenders if "middleware" in o] == []


def test_file_io_rule_flags_open_and_stream_json_and_a_storage_import(sample_root):
    offenders = _sample_violations("router_no_file_io", ["filey"], sample_root)
    assert offenders == [
        "src/filey/routes.py::<module>: line 6: imports `.storage` — persistence belongs behind a "
        "service (routers hold HTTP concerns; persistence goes through a service)",
        "src/filey/routes.py::_load: line 12: calls `open()` (routers hold HTTP concerns; "
        "persistence goes through a service)",
        "src/filey/routes.py::_load: line 13: calls `json.load()` (routers hold HTTP concerns; "
        "persistence goes through a service)",
    ]


def test_file_io_rule_stays_quiet_on_a_router_that_calls_a_service(sample_root):
    assert _sample_violations("router_no_file_io", ["tidy"], sample_root) == []


def test_domain_logic_rule_flags_a_fat_handler_and_its_fat_helper(sample_root):
    """Both, because "extract a private helper" must not be a way around it."""
    offenders = _sample_violations("router_no_domain_logic", ["fatty"], sample_root)
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("src/fatty/routes.py::_decide: line 6: 18 statements (max 15)")
    assert "cyclomatic complexity 9 (max 8)" in offenders[0]


def test_domain_logic_rule_flags_dense_branching_in_a_short_handler(sample_root):
    """The complexity arm is not redundant with the statement arm."""
    offenders = _sample_violations("router_no_domain_logic", ["branchy"], sample_root)
    assert len(offenders) == 1, offenders
    assert "cyclomatic complexity" in offenders[0]
    assert "statements" not in offenders[0]


def test_domain_logic_rule_stays_quiet_on_a_thin_adapter(sample_root):
    assert _sample_violations("router_no_domain_logic", ["tidy"], sample_root) == []


def test_no_rule_fires_on_the_compliant_sample_domain(sample_root):
    """A checker that flags everything is as useless as one that flags nothing."""
    for rule in RULE_IDS:
        assert _sample_violations(rule, ["tidy"], sample_root) == [], rule


def test_an_exception_excuses_exactly_its_target_and_rule(sample_root):
    manifest = {
        "enforced_domains": ["filey"],
        "exceptions": [
            {
                "target": "src/filey/routes.py::_load",
                "rule": "router_no_file_io",
                "reason": "sample fixture: proves an exception suppresses one target",
            }
        ],
    }
    remaining = violations("router_no_file_io", manifest, sample_root)
    assert remaining == [
        "src/filey/routes.py::<module>: line 6: imports `.storage` — persistence belongs behind a "
        "service (routers hold HTTP concerns; persistence goes through a service)"
    ]


def test_a_domain_that_is_not_a_package_is_rejected_as_a_typo(sample_root):
    problems = validate_manifest({"enforced_domains": ["tidee"], "exceptions": []}, sample_root)
    assert any("tidee" in p and "not a package" in p for p in problems), problems


def test_a_domain_with_no_router_is_rejected(sample_root):
    problems = validate_manifest({"enforced_domains": ["routerless"], "exceptions": []}, sample_root)
    assert any("has no routes.py" in p for p in problems), problems


def test_an_unknown_rule_id_is_rejected(sample_root):
    manifest = {
        "enforced_domains": ["filey"],
        "exceptions": [
            {
                "target": "src/filey/routes.py::_load",
                "rule": "router_no_fileio",
                "reason": "typo that must not silently excuse nothing",
            }
        ],
    }
    problems = validate_manifest(manifest, sample_root)
    assert any("unknown rule" in p for p in problems), problems


def test_an_exception_for_a_nonexistent_module_is_rejected(sample_root):
    manifest = {
        "enforced_domains": ["filey"],
        "exceptions": [
            {
                "target": "src/filey/typo.py::_load",
                "rule": "router_no_file_io",
                "reason": "module was renamed and the exception was left behind",
            }
        ],
    }
    problems = validate_manifest(manifest, sample_root)
    assert any("not a file in the tree" in p for p in problems), problems


def test_an_exception_outside_every_enforced_domain_is_rejected(sample_root):
    manifest = {
        "enforced_domains": ["tidy"],
        "exceptions": [
            {
                "target": "src/filey/routes.py::_load",
                "rule": "router_no_file_io",
                "reason": "left behind after the domain was removed from the list",
            }
        ],
    }
    problems = validate_manifest(manifest, sample_root)
    assert any("is not enforced" in p for p in problems), problems


def test_duplicate_exceptions_are_rejected(sample_root):
    entry = {
        "target": "src/filey/routes.py::_load",
        "rule": "router_no_file_io",
        "reason": "duplicated by a bad merge resolution",
    }
    problems = validate_manifest(
        {"enforced_domains": ["filey"], "exceptions": [entry, dict(entry)]},
        sample_root,
    )
    assert any("duplicates" in p for p in problems), problems


def test_an_exception_without_a_real_reason_is_rejected(sample_root):
    manifest = {
        "enforced_domains": ["filey"],
        "exceptions": [{"target": "src/filey/routes.py::_load", "rule": "router_no_file_io", "reason": "TODO"}],
    }
    problems = validate_manifest(manifest, sample_root)
    assert any("substantive reason" in p for p in problems), problems


def test_a_dead_exception_is_rejected(sample_root):
    """An exception whose rule already passes excuses nothing — fail the build.

    This is the check the sibling conventions ratchet was missing: eleven dead
    exceptions accumulated there through union merges, each one silently
    exempting a compliant route from ever being checked again. Built in from
    the start here rather than retrofitted after the same accident.
    """
    manifest = {
        "enforced_domains": ["tidy"],
        "exceptions": [
            {
                "target": "src/tidy/routes.py::get_thing",
                "rule": "router_no_domain_logic",
                "reason": "left behind after the handler was slimmed down",
            }
        ],
    }
    problems = validate_manifest(manifest, sample_root)
    assert any("already passes" in p for p in problems), problems


def test_a_live_exception_is_not_reported_as_dead(sample_root):
    """The liveness check must not reject an exception that still bites."""
    manifest = {
        "enforced_domains": ["filey"],
        "exceptions": [
            {
                "target": "src/filey/routes.py::_load",
                "rule": "router_no_file_io",
                "reason": "sample fixture: this helper really does open a file",
            },
            {
                "target": "src/filey/routes.py::<module>",
                "rule": "router_no_file_io",
                "reason": "sample fixture: this module really does import storage",
            },
        ],
    }
    assert validate_manifest(manifest, sample_root) == []


def test_the_architecture_doc_names_the_domains_actually_enforced():
    """The document that lied last time cannot drift from the manifest again.

    ``ARCHITECTURE.md`` used to claim both layering rules were "enforced by
    tests". One was enforced for a single domain and the other for none, and
    nothing noticed for two sessions because prose has no build step. It does
    now: the doc's "Enforced today:" line is parsed and compared against
    ``enforced_domains``, so widening the manifest without updating the
    document — or the reverse — fails here.
    """
    import re

    doc = (REPO_ROOT / "docs" / "internal" / "reference" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    match = re.search(r"^Enforced today:(.+?)(?:\n\n|\.\s)", doc, re.MULTILINE | re.DOTALL)
    assert match, "ARCHITECTURE.md no longer has an 'Enforced today:' line naming the enforced domains"
    documented = sorted(re.findall(r"`([a-z_]+)`", match.group(1)))
    assert documented == sorted(MANIFEST["enforced_domains"]), (
        "ARCHITECTURE.md and tests/layering_manifest.json disagree about which domains are enforced.\n"
        f"  document: {documented}\n"
        f"  manifest: {sorted(MANIFEST['enforced_domains'])}"
    )
