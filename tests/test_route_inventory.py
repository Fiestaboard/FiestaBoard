"""Golden test over the FastAPI route inventory (issue #1731).

``src/api_server.py`` declares ~200 routes inline. Epic #1730 extracts them
into routers, and the classic failure mode of that refactor is a route that
silently changes path, loses a method, or disappears entirely — nothing in
the suite notices, because every *other* test only asserts on the endpoints
it happens to exercise.

This test snapshots the whole route table (path + sorted methods + endpoint
name) into ``tests/golden/api_routes.json`` and fails on any drift. Adding a
route is not forbidden — it just has to be a deliberate, reviewable change to
the golden file rather than an invisible side effect of a refactor.

Regenerating the golden file
----------------------------
Only ever do this when the route change is intentional, and read the diff::

    docker compose -f docker-compose.dev.yml exec fiestaboard \\
        env UPDATE_ROUTE_INVENTORY=1 pytest tests/test_route_inventory.py

Then ``git diff tests/golden/api_routes.json`` and confirm every line is a
change you meant to make.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.api_server import app

GOLDEN_PATH = Path(__file__).parent / "golden" / "api_routes.json"

REGENERATE_HINT = (
    "If this change is intentional, regenerate the golden file with:\n"
    "    UPDATE_ROUTE_INVENTORY=1 pytest tests/test_route_inventory.py\n"
    "then review `git diff tests/golden/api_routes.json` line by line."
)


def _describe(route: Any, prefix: str) -> dict[str, Any]:
    """Render a single route as a stable, JSON-serializable record."""
    return {
        "path": prefix + getattr(route, "path", ""),
        "methods": sorted(getattr(route, "methods", None) or []),
        "name": getattr(route, "name", None),
        "kind": type(route).__name__,
    }


def _walk(routes: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Flatten a Starlette/FastAPI route list into inventory records.

    Two node types need special handling:

    * ``Mount`` wraps a foreign ASGI app (the MCP server). Its internal
      routes belong to that app, not to us, so the mount point is recorded
      as a single entry and not descended into.
    * FastAPI >= 0.130 wraps ``include_router()`` results in an internal
      ``_IncludedRouter`` node that exposes no ``path``. The real routes
      hang off ``include_context``, so recurse through that with the
      router's prefix applied.
    """
    collected: list[dict[str, Any]] = []
    for route in routes:
        include_context = getattr(route, "include_context", None)
        if include_context is not None:
            collected.extend(
                _walk(
                    include_context.included_router.routes,
                    prefix + (include_context.prefix or ""),
                )
            )
            continue
        collected.append(_describe(route, prefix))
    return collected


def build_route_inventory() -> list[dict[str, Any]]:
    """Return the app's full route table, sorted deterministically."""
    records = _walk(app.routes)
    return sorted(records, key=lambda r: (r["path"], r["methods"], r["name"] or "", r["kind"]))


def _key(record: dict[str, Any]) -> str:
    """Identity of a route for diffing: what it answers, not how it's named."""
    methods = ",".join(record["methods"]) or "-"
    return f"{record['path']} [{methods}]"


def _load_golden() -> list[dict[str, Any]]:
    with GOLDEN_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["routes"]


def _write_golden(routes: list[dict[str, Any]]) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Golden snapshot of src.api_server.app route table (issue #1731). "
            "Do not hand-edit: regenerate with "
            "`UPDATE_ROUTE_INVENTORY=1 pytest tests/test_route_inventory.py` "
            "and review the diff."
        ),
        "routes": routes,
    }
    with GOLDEN_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _format_drift(current: list[dict[str, Any]], golden: list[dict[str, Any]]) -> str:
    current_by_key = {_key(r): r for r in current}
    golden_by_key = {_key(r): r for r in golden}

    added = sorted(set(current_by_key) - set(golden_by_key))
    removed = sorted(set(golden_by_key) - set(current_by_key))
    renamed = sorted(
        key
        for key in set(current_by_key) & set(golden_by_key)
        if current_by_key[key]["name"] != golden_by_key[key]["name"]
        or current_by_key[key]["kind"] != golden_by_key[key]["kind"]
    )

    lines = ["Route inventory drifted from tests/golden/api_routes.json.", ""]
    if added:
        lines.append(f"ADDED ({len(added)}) — routes the app serves but the golden file doesn't list:")
        lines.extend(f"  + {key} -> {current_by_key[key]['name']}" for key in added)
        lines.append("")
    if removed:
        lines.append(f"REMOVED ({len(removed)}) — routes the golden file lists but the app no longer serves:")
        lines.extend(f"  - {key} -> {golden_by_key[key]['name']}" for key in removed)
        lines.append("")
    if renamed:
        lines.append(f"CHANGED ({len(renamed)}) — same path+methods, different endpoint name or route class:")
        for key in renamed:
            before, after = golden_by_key[key], current_by_key[key]
            lines.append(f"  ~ {key}: {before['name']} ({before['kind']}) -> {after['name']} ({after['kind']})")
        lines.append("")
    lines.append(REGENERATE_HINT)
    return "\n".join(lines)


def test_route_inventory_matches_golden():
    """The live route table equals the reviewed golden snapshot."""
    current = build_route_inventory()

    if os.environ.get("UPDATE_ROUTE_INVENTORY"):
        _write_golden(current)
        return

    golden = _load_golden()
    assert current == golden, _format_drift(current, golden)


def test_route_inventory_is_not_trivially_empty():
    """Guard the guard: an import failure must not read as 'no drift'.

    If ``app`` ever came back with a handful of routes (a broken import, a
    conditional mount that silently no-ops), the comparison above would
    still be a meaningful assertion — but a golden file regenerated in that
    state would lock in the damage. Assert the table is the size we expect
    a real app to have.
    """
    assert len(build_route_inventory()) > 150


def test_route_inventory_has_no_duplicate_path_method_pairs():
    """No two routes claim the same path+method — the second is unreachable."""
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for record in build_route_inventory():
        for method in record["methods"]:
            key = f"{method} {record['path']}"
            if key in seen:
                duplicates.append(f"{key}: {seen[key]} then {record['name']}")
            else:
                seen[key] = record["name"] or "<unnamed>"
    assert not duplicates, "Shadowed routes (only the first is ever reached):\n  " + "\n  ".join(duplicates)
