"""Conventions are a build failure, not a document (Phase 2, spec §2).

``docs/internal/reference/API_CONVENTIONS.md`` describes four rules that
Phase 1 wrote down and nothing enforced. This module makes them real: a
domain listed in ``tests/conventions_manifest.json`` must satisfy every rule
on every one of its routes. Exceptions are allowed but must be checked in
with a reason — silence is not.

How a domain opts in
--------------------
Append its router tag (``APIRouter(tags=["collections"])`` → ``collections``)
to ``converted_domains`` in the manifest, in the same PR that converts it.
Until then the domain is invisible to this file: the ratchet is a floor that
only ever moves up.

The four rules
--------------
``response_model``
    Every route declares ``response_model=`` so the response is a typed
    contract instead of whatever dict the handler happened to build.
``no_200_on_failure``
    No handler returns a 2xx on a failure path — no ``return`` inside an
    ``except``, no ``{"success": False}`` / ``{"status": "error"}`` /
    ``{"valid": False}`` body on a route that answers 200.
``typed_body``
    No request body parameter annotated as a bare ``dict`` /
    ``dict[str, Any]`` / ``Any``.
``declared_errors``
    Every route declares at least one 4xx in ``responses=``.

Precision over cleverness
-------------------------
A ratchet that cries wolf gets deleted. The source scan below only walks the
handler's own body (never a nested closure's), and only flags literal dict
constants it can see in a ``return``. Where a construct is genuinely
ambiguous — an ``except`` that returns, a ``Response(status_code=<variable>)``
— it flags, and the domain records a documented exception. That trade is
deliberate: a false positive costs one manifest entry and a code review; a
false negative costs a shipped 200-on-failure.
"""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
import types
import typing
from pathlib import Path
from typing import Any

from tests.test_route_inventory import build_route_metadata

MANIFEST_PATH = Path(__file__).parent / "conventions_manifest.json"

#: The only rule ids an exception entry may name. A typo here must fail the
#: build rather than silently excuse nothing (or, worse, look like it did).
RULE_IDS = frozenset(
    {
        "response_model",
        "no_200_on_failure",
        "typed_body",
        "declared_errors",
    }
)

#: ``(key, value)`` pairs that mark a response body as reporting a failure.
FAILURE_MARKERS = frozenset(
    {
        ("success", False),
        ("status", "error"),
        ("valid", False),
    }
)

MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Manifest plumbing
# --------------------------------------------------------------------------


def _route_keys(record: dict[str, Any]) -> list[str]:
    """``["POST /collections"]`` — one key per HTTP method on the route."""
    return [f"{method} {record['path']}" for method in record["methods"]]


def _excused(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e["route"], e["rule"]) for e in manifest.get("exceptions", [])}


def _records_for_domain(records: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Routes belonging to ``domain``, identified by their router tag."""
    return [r for r in records if r["kind"] == "APIRoute" and domain in (r["tags"] or [])]


def _converted_records(
    manifest: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    manifest = MANIFEST if manifest is None else manifest
    records = build_route_metadata() if records is None else records
    collected: list[dict[str, Any]] = []
    for domain in manifest.get("converted_domains", []):
        collected.extend(_records_for_domain(records, domain))
    return collected


def _violations(
    rule: str,
    check: typing.Callable[[dict[str, Any]], list[str]],
    manifest: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Run ``check`` over every converted route, minus the excused ones."""
    manifest = MANIFEST if manifest is None else manifest
    excused = _excused(manifest)
    found: list[str] = []
    for record in _converted_records(manifest, records):
        keys = [k for k in _route_keys(record) if (k, rule) not in excused]
        if not keys:
            continue
        problems = check(record)
        for key in keys:
            found.extend(f"{key}: {problem}" for problem in problems)
    return sorted(found)


# --------------------------------------------------------------------------
# Rule 1 — response_model
# --------------------------------------------------------------------------


def check_response_model(record: dict[str, Any]) -> list[str]:
    if record["response_model"] is None:
        return ["no response_model= declared"]
    return []


# --------------------------------------------------------------------------
# Rule 2 — no 200 on a failure path
# --------------------------------------------------------------------------


def _handler_ast(endpoint: Any) -> tuple[ast.AST, list[str], str, int]:
    """The handler's own AST, plus enough to name a real file:line in the report."""
    func = inspect.unwrap(endpoint)
    raw, first_lineno = inspect.getsourcelines(func)
    source = textwrap.dedent("".join(raw))
    return ast.parse(source).body[0], source.splitlines(), inspect.getsourcefile(func) or "?", first_lineno


def _short_path(filename: str) -> str:
    """Repo-relative path where possible; the messages are read in CI logs."""
    root = Path(__file__).resolve().parent.parent
    try:
        return str(Path(filename).resolve().relative_to(root))
    except ValueError:
        return filename


def _own_returns(func: ast.AST) -> list[tuple[ast.Return, bool]]:
    """``(return_node, is_inside_except)`` for returns belonging to ``func``.

    Returns inside a nested ``def``/``lambda`` belong to that callable, not to
    the handler — counting them is the obvious false positive, so they are
    skipped explicitly.
    """
    found: list[tuple[ast.Return, bool]] = []

    def walk(node: ast.AST, owner: ast.AST, in_except: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                walk(child, child, False)
                continue
            if isinstance(child, ast.Return) and owner is func:
                found.append((child, in_except))
            walk(child, owner, in_except or isinstance(child, ast.ExceptHandler))

    walk(func, func, False)
    return found


def _explicit_error_status(node: ast.expr | None) -> bool:
    """True if ``node`` is a ``Response(...)`` construction with a 4xx/5xx code.

    Only a *literal* status code counts. A computed one (``status_code=code``)
    is unknowable statically, so it is treated as not-an-error and the return
    stays flagged — see the module docstring on ambiguity.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if not name.endswith("Response"):
        return False
    for keyword in node.keywords:
        if keyword.arg == "status_code" and isinstance(keyword.value, ast.Constant):
            return isinstance(keyword.value.value, int) and keyword.value.value >= 400
    return False


def check_no_200_on_failure(record: dict[str, Any]) -> list[str]:
    endpoint = record["endpoint"]
    if endpoint is None:
        return []
    declared = record["status_code"]
    if isinstance(declared, int) and declared >= 400:
        # The route never answers 2xx at all.
        return []
    try:
        func, lines, filename, first_lineno = _handler_ast(endpoint)
    except (OSError, TypeError, SyntaxError, IndexError) as exc:  # pragma: no cover - defensive
        return [f"could not read handler source ({exc.__class__.__name__}: {exc})"]

    problems: list[str] = []
    for node, in_except in _own_returns(func):
        if _explicit_error_status(node.value):
            continue
        line = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "?"
        where = f"{_short_path(filename)}:{first_lineno + node.lineno - 1}"
        if in_except:
            problems.append(f"{where}: return inside an except block -> `{line}`")
        for descendant in ast.walk(node):
            if not isinstance(descendant, ast.Dict):
                continue
            for key, value in zip(descendant.keys, descendant.values, strict=True):
                if not (isinstance(key, ast.Constant) and isinstance(value, ast.Constant)):
                    continue
                if (key.value, value.value) in FAILURE_MARKERS:
                    problems.append(f'{where}: returns {{"{key.value}": {value.value!r}}} on a 2xx path -> `{line}`')
    return problems


# --------------------------------------------------------------------------
# Rule 3 — typed request bodies
# --------------------------------------------------------------------------


def _is_untyped_body(annotation: Any) -> bool:
    """True for ``dict``, ``dict[str, Any]``, ``Any``, and Optionals of those.

    Path and query parameters never reach here: the caller reads FastAPI's
    resolved ``dependant.body_params``, which is exactly the set of
    parameters FastAPI decided are request body.
    """
    if annotation is Any or annotation is dict:
        return True
    origin = typing.get_origin(annotation)
    if origin is dict:
        return True
    if origin is typing.Union or origin is types.UnionType:
        return any(_is_untyped_body(arg) for arg in typing.get_args(annotation))
    return False


def check_typed_body(record: dict[str, Any]) -> list[str]:
    dependant = getattr(record["route"], "dependant", None)
    problems: list[str] = []
    for field in getattr(dependant, "body_params", None) or []:
        annotation = getattr(getattr(field, "field_info", None), "annotation", None)
        if _is_untyped_body(annotation):
            shown = (
                str(annotation)
                if typing.get_origin(annotation) is not None
                else (getattr(annotation, "__name__", None) or str(annotation))
            )
            problems.append(f"body param `{field.name}` is annotated `{shown}` — use a Pydantic model")
    return problems


# --------------------------------------------------------------------------
# Rule 4 — declared error responses
# --------------------------------------------------------------------------


def check_declared_errors(record: dict[str, Any]) -> list[str]:
    for code in record["responses"]:
        try:
            numeric = int(code)
        except (TypeError, ValueError):
            continue
        if 400 <= numeric <= 499:
            return []
    return ["declares no 4xx in responses="]


# --------------------------------------------------------------------------
# The ratchet
# --------------------------------------------------------------------------


def test_converted_domains_declare_response_models():
    """Every route in a converted domain declares response_model=."""
    offenders = _violations("response_model", check_response_model)
    assert offenders == [], (
        "Converted domains must declare response_model on every route "
        "(API_CONVENTIONS.md §response shape). Fix the route, or add a "
        '{"rule": "response_model", ...} exception to '
        "tests/conventions_manifest.json with a reason:\n  " + "\n  ".join(offenders)
    )


def test_converted_domains_never_return_200_on_failure():
    """No route in a converted domain answers 2xx on a failure path."""
    offenders = _violations("no_200_on_failure", check_no_200_on_failure)
    assert offenders == [], (
        "Converted domains must signal failure with a status code, not a 200 "
        "body (API_CONVENTIONS.md §errors). Raise HTTPException instead, or "
        'add a {"rule": "no_200_on_failure", ...} exception to '
        "tests/conventions_manifest.json with a reason:\n  " + "\n  ".join(offenders)
    )


def test_converted_domains_use_typed_request_bodies():
    """No route in a converted domain accepts an untyped dict body."""
    offenders = _violations("typed_body", check_typed_body)
    assert offenders == [], (
        "Converted domains must take Pydantic request models, not bare dicts "
        "(API_CONVENTIONS.md §request bodies). Fix the signature, or add a "
        '{"rule": "typed_body", ...} exception to '
        "tests/conventions_manifest.json with a reason:\n  " + "\n  ".join(offenders)
    )


def test_converted_domains_declare_error_responses():
    """Every route in a converted domain documents at least one 4xx."""
    offenders = _violations("declared_errors", check_declared_errors)
    assert offenders == [], (
        "Converted domains must declare the errors they raise so the OpenAPI "
        "schema and the web client agree (API_CONVENTIONS.md §errors). Add "
        'responses={404: ...}, or add a {"rule": "declared_errors", ...} '
        "exception to tests/conventions_manifest.json with a reason:\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------
# Guarding the guard
# --------------------------------------------------------------------------


def validate_manifest(manifest: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    """Return every structural problem with ``manifest``.

    An empty ``converted_domains`` makes the four rules above vacuously true,
    which is fine as a starting point but fatal if a typo can put the manifest
    back into that state unnoticed. So: unknown keys, unknown rule ids,
    duplicate exceptions, domains that match no route, and exceptions naming a
    route the app does not serve are all build failures.
    """
    problems: list[str] = []

    allowed_top_level = {"_comment", "converted_domains", "exceptions"}
    unknown_top_level = sorted(set(manifest) - allowed_top_level)
    if unknown_top_level:
        problems.append(f"unknown top-level key(s): {unknown_top_level}")

    domains = manifest.get("converted_domains")
    if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
        problems.append("converted_domains must be a list of strings")
        domains = []
    if len(set(domains)) != len(domains):
        problems.append(f"converted_domains has duplicates: {sorted(domains)}")

    known_routes = {key for r in records if r["kind"] == "APIRoute" for key in _route_keys(r)}
    route_domain = {key: set(r["tags"] or []) for r in records if r["kind"] == "APIRoute" for key in _route_keys(r)}

    for domain in domains:
        if not _records_for_domain(records, domain):
            problems.append(
                f"converted domain {domain!r} matches no route on the app — a typo here silently converts nothing"
            )

    exceptions = manifest.get("exceptions")
    if not isinstance(exceptions, list):
        problems.append("exceptions must be a list")
        exceptions = []

    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(exceptions):
        where = f"exceptions[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where} is not an object")
            continue
        unknown_keys = sorted(set(entry) - {"route", "rule", "reason"})
        if unknown_keys:
            problems.append(f"{where} has unknown key(s): {unknown_keys}")
        route = entry.get("route")
        rule = entry.get("rule")
        reason = entry.get("reason")
        if not isinstance(route, str) or not route:
            problems.append(f'{where} needs a "route" of the form "METHOD /path"')
            continue
        if rule not in RULE_IDS:
            problems.append(f"{where} names unknown rule {rule!r}; known rules: {sorted(RULE_IDS)}")
        if not isinstance(reason, str) or len(reason.strip()) < 10:
            problems.append(f"{where} ({route}) needs a substantive reason, not {reason!r}")
        if (route, rule) in seen:
            problems.append(f"{where} duplicates the exception for {route} / {rule}")
        seen.add((route, rule))
        if route not in known_routes:
            problems.append(f"{where} excuses {route!r}, which the app does not serve")
        elif not route_domain[route] & set(domains):
            problems.append(
                f"{where} excuses {route!r}, which is not in any converted domain — "
                "dead exceptions rot; delete it or convert its domain"
            )
    return problems


def test_conventions_manifest_is_well_formed():
    """A typo in the manifest fails the build instead of excusing a rule."""
    problems = validate_manifest(MANIFEST, build_route_metadata())
    assert problems == [], "tests/conventions_manifest.json is malformed:\n  " + "\n  ".join(problems)


def test_manifest_rule_ids_match_the_documented_set():
    """The rule ids the doc and the slice plan name are the ones enforced."""
    enforced = {
        "response_model": test_converted_domains_declare_response_models,
        "no_200_on_failure": test_converted_domains_never_return_200_on_failure,
        "typed_body": test_converted_domains_use_typed_request_bodies,
        "declared_errors": test_converted_domains_declare_error_responses,
    }
    assert set(enforced) == set(RULE_IDS)


# --------------------------------------------------------------------------
# Proving each rule bites
#
# The ratchet starts with an empty converted_domains list, so the four tests
# above pass without asserting anything about the real app. That is by
# design — and it is exactly why they cannot be their own evidence. These
# tests point each checker at a purpose-built app whose routes break one rule
# each, and assert the checker says so. If a rule is ever quietly defanged,
# these fail even though converted_domains is still empty.
# --------------------------------------------------------------------------

SAMPLE_MANIFEST = {"converted_domains": ["sample"], "exceptions": []}


def _sample_records() -> list[dict[str, Any]]:
    """An app whose ``sample`` domain breaks one rule per route."""
    from fastapi import APIRouter, FastAPI, Response
    from pydantic import BaseModel

    class Thing(BaseModel):
        name: str

    router = APIRouter(tags=["sample"])
    ok = {404: {"description": "not found"}}

    @router.get("/sample/compliant", response_model=Thing, responses=ok)
    async def compliant() -> Thing:
        return Thing(name="ok")

    # No `response_model=` and no return annotation for FastAPI to infer one from.
    @router.get("/sample/no-model", responses=ok)
    async def no_model():
        return {"name": "ok"}

    @router.post("/sample/untyped-body", response_model=Thing, responses=ok)
    async def untyped_body(payload: dict, other: dict[str, Any], maybe: dict | None = None) -> Thing:
        return Thing(name="ok")

    @router.get("/sample/no-errors", response_model=Thing)
    async def no_errors() -> Thing:
        return Thing(name="ok")

    @router.get("/sample/returns-in-except", response_model=Thing, responses=ok)
    async def returns_in_except() -> Any:
        try:
            return Thing(name="ok")
        except ValueError:
            return {"detail": "boom"}

    @router.get("/sample/success-false", response_model=Thing, responses=ok)
    async def success_false() -> Any:
        return {"success": False, "message": "nope"}

    @router.get("/sample/nested-closure", response_model=Thing, responses=ok)
    async def nested_closure() -> Thing:
        def helper() -> str:
            try:
                raise ValueError
            except ValueError:
                return "handled"

        helper()
        return Thing(name="ok")

    @router.get("/sample/explicit-error-response", response_model=Thing, responses=ok)
    async def explicit_error_response(fail: bool = False) -> Any:
        if fail:
            return Response(content='{"success": false}', status_code=400)
        return Thing(name="ok")

    sample_app = FastAPI()
    sample_app.include_router(router)
    return build_route_metadata(sample_app)


def _sample_violations(rule: str, check: Any) -> list[str]:
    return _violations(rule, check, manifest=SAMPLE_MANIFEST, records=_sample_records())


def test_response_model_rule_flags_a_route_that_declares_none():
    offenders = _sample_violations("response_model", check_response_model)
    assert offenders == ["GET /sample/no-model: no response_model= declared"]


def test_typed_body_rule_flags_bare_dict_body_params():
    offenders = _sample_violations("typed_body", check_typed_body)
    assert offenders == [
        "POST /sample/untyped-body: body param `maybe` is annotated `dict | None` — use a Pydantic model",
        "POST /sample/untyped-body: body param `other` is annotated `dict[str, typing.Any]` — use a Pydantic model",
        "POST /sample/untyped-body: body param `payload` is annotated `dict` — use a Pydantic model",
    ]


def test_declared_errors_rule_flags_a_route_with_no_4xx():
    offenders = _sample_violations("declared_errors", check_declared_errors)
    assert offenders == ["GET /sample/no-errors: declares no 4xx in responses="]


def test_no_200_on_failure_rule_flags_a_return_inside_except():
    offenders = [
        o for o in _sample_violations("no_200_on_failure", check_no_200_on_failure) if "returns-in-except" in o
    ]
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("GET /sample/returns-in-except: tests/test_api_conventions_ratchet.py:")
    assert offenders[0].endswith('return inside an except block -> `return {"detail": "boom"}`')


def test_no_200_on_failure_rule_flags_a_success_false_body():
    offenders = [o for o in _sample_violations("no_200_on_failure", check_no_200_on_failure) if "success-false" in o]
    assert len(offenders) == 1, offenders
    assert offenders[0].startswith("GET /sample/success-false: tests/test_api_conventions_ratchet.py:")
    assert offenders[0].endswith(
        'returns {"success": False} on a 2xx path -> `return {"success": False, "message": "nope"}`'
    )


def test_no_200_on_failure_rule_ignores_returns_in_a_nested_closure():
    """A closure's except-return is the closure's business, not the route's."""
    offenders = _sample_violations("no_200_on_failure", check_no_200_on_failure)
    assert [o for o in offenders if "nested-closure" in o] == []


def test_no_200_on_failure_rule_ignores_an_explicit_4xx_response():
    """`return Response(status_code=400, ...)` is not a 200 on failure."""
    offenders = _sample_violations("no_200_on_failure", check_no_200_on_failure)
    assert [o for o in offenders if "explicit-error-response" in o] == []


def test_no_rule_fires_on_the_compliant_sample_route():
    """A checker that flags everything is as useless as one that flags nothing."""
    records = _sample_records()
    checks = {
        "response_model": check_response_model,
        "no_200_on_failure": check_no_200_on_failure,
        "typed_body": check_typed_body,
        "declared_errors": check_declared_errors,
    }
    for rule, check in checks.items():
        offenders = _violations(rule, check, manifest=SAMPLE_MANIFEST, records=records)
        assert [o for o in offenders if o.startswith("GET /sample/compliant")] == [], rule


def test_an_exception_entry_excuses_exactly_its_route_and_rule():
    records = _sample_records()
    manifest = {
        "converted_domains": ["sample"],
        "exceptions": [
            {
                "route": "GET /sample/no-model",
                "rule": "response_model",
                "reason": "sample fixture: proves an exception suppresses one pair",
            }
        ],
    }
    assert _violations("response_model", check_response_model, manifest, records) == []
    # ...and leaks into no other route: the other missing-model route (if any)
    # and every other rule are still enforced.
    assert "GET /sample/no-errors: declares no 4xx in responses=" in _violations(
        "declared_errors", check_declared_errors, manifest, records
    )


def test_a_domain_with_no_routes_is_rejected_as_a_typo():
    problems = validate_manifest({"converted_domains": ["collectionz"], "exceptions": []}, _sample_records())
    assert any("collectionz" in p and "matches no route" in p for p in problems), problems


def test_an_unknown_rule_id_is_rejected():
    manifest = {
        "converted_domains": ["sample"],
        "exceptions": [
            {
                "route": "GET /sample/no-model",
                "rule": "responsemodel",
                "reason": "typo that must not silently excuse nothing",
            }
        ],
    }
    problems = validate_manifest(manifest, _sample_records())
    assert any("unknown rule" in p for p in problems), problems


def test_an_exception_for_a_nonexistent_route_is_rejected():
    manifest = {
        "converted_domains": ["sample"],
        "exceptions": [
            {
                "route": "GET /sample/typo",
                "rule": "response_model",
                "reason": "route was renamed and the exception was left behind",
            }
        ],
    }
    problems = validate_manifest(manifest, _sample_records())
    assert any("does not serve" in p for p in problems), problems


def test_duplicate_exceptions_are_rejected():
    entry = {
        "route": "GET /sample/no-model",
        "rule": "response_model",
        "reason": "duplicated by a bad merge resolution",
    }
    problems = validate_manifest(
        {"converted_domains": ["sample"], "exceptions": [entry, dict(entry)]},
        _sample_records(),
    )
    assert any("duplicates" in p for p in problems), problems


def test_an_exception_without_a_real_reason_is_rejected():
    manifest = {
        "converted_domains": ["sample"],
        "exceptions": [{"route": "GET /sample/no-model", "rule": "response_model", "reason": "TODO"}],
    }
    problems = validate_manifest(manifest, _sample_records())
    assert any("substantive reason" in p for p in problems), problems


def test_an_exception_outside_every_converted_domain_is_rejected():
    manifest = {
        "converted_domains": [],
        "exceptions": [
            {
                "route": "GET /sample/no-model",
                "rule": "response_model",
                "reason": "left behind after the domain was removed from the list",
            }
        ],
    }
    problems = validate_manifest(manifest, _sample_records())
    assert any("not in any converted domain" in p for p in problems), problems
