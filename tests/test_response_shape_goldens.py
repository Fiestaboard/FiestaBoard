"""Response-shape golden tests for the pages / schedules / collections domains.

Issue #1756 moves these three route families out of ``src/api_server.py`` into
per-domain routers. The move must be behavior-preserving, and the classic way
such a refactor goes wrong is subtle: a handler keeps its path but changes a
status code, drops a response key, or stops seeing a monkeypatched helper.

These tests drive every endpoint of the three domains through a seeded
``TestClient`` scenario and snapshot ``{method, path_template, status, shape}``
into ``tests/golden/responses/<domain>.json``, where ``shape`` is the response
JSON with every value replaced by its type name (dict keys are kept, values
become ``"str"`` / ``"int"`` / ``"float"`` / ``"bool"`` / ``"null"``, lists map
element-wise). Shapes, not values — so ids and timestamps don't churn — but the
scenarios are deterministic, so status codes and key sets are exact.

Regenerating the golden files
-----------------------------
Only when a response change is intentional (it never is in a pure-move PR)::

    RECORD_RESPONSE_GOLDEN=1 pytest tests/test_response_shape_goldens.py

then review ``git diff tests/golden/responses/`` line by line.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app

GOLDEN_DIR = Path(__file__).parent / "golden" / "responses"

RECORD = os.environ.get("RECORD_RESPONSE_GOLDEN") == "1"

REGENERATE_HINT = (
    "Response shapes drifted from tests/golden/responses/. In a pure-move "
    "refactor this is a regression — fix the code. If the change is "
    "intentional, regenerate with:\n"
    "    RECORD_RESPONSE_GOLDEN=1 pytest tests/test_response_shape_goldens.py\n"
    "then review `git diff tests/golden/responses/` line by line."
)

# ---------------------------------------------------------------------------
# Route scope: exactly the routes issue #1756 moves, per domain.
# /pages/ai/* stays behind deliberately — it is AI-domain surface that shares
# the AI semaphore/throttle helpers with /ai/* and moves with them later.
# ---------------------------------------------------------------------------

PAGES_ROUTES = {
    ("GET", "/pages"),
    ("GET", "/pages/current-display"),
    ("POST", "/pages"),
    ("GET", "/pages/{page_id}"),
    ("PUT", "/pages/{page_id}"),
    ("DELETE", "/pages/{page_id}"),
    ("GET", "/pages/{page_id}/share"),
    ("POST", "/pages/import/preview"),
    ("POST", "/pages/import"),
    ("GET", "/staff-picks"),
    ("GET", "/staff-picks/{pick_id}/share"),
    ("POST", "/pages/{page_id}/preview"),
    ("POST", "/pages/preview/batch"),
    ("GET", "/pages/cache/stats"),
    ("POST", "/pages/cache/clear"),
    ("POST", "/pages/{page_id}/send"),
}

SCHEDULES_ROUTES = {
    ("GET", "/schedules"),
    ("POST", "/schedules"),
    ("GET", "/schedules/active/page"),
    ("POST", "/schedules/validate"),
    ("GET", "/schedules/default-page"),
    ("PUT", "/schedules/default-page"),
    ("GET", "/schedules/enabled"),
    ("PUT", "/schedules/enabled"),
    ("GET", "/schedules/{schedule_id}"),
    ("PUT", "/schedules/{schedule_id}"),
    ("DELETE", "/schedules/{schedule_id}"),
}

COLLECTIONS_ROUTES = {
    ("GET", "/collections"),
    ("POST", "/collections"),
    ("GET", "/collections/{collection_id}"),
    ("PUT", "/collections/{collection_id}"),
    ("DELETE", "/collections/{collection_id}"),
}


# ---------------------------------------------------------------------------
# Shape machinery
# ---------------------------------------------------------------------------


def shape_of(value: Any) -> Any:
    """Recursively replace JSON values with their type names.

    Dict keys are preserved (they are part of the contract); values become
    type-name strings; lists map element-wise. ``bool`` must be checked
    before ``int`` (bool is an int subclass).
    """
    if isinstance(value, dict):
        return {key: shape_of(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [shape_of(item) for item in value]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if value is None:
        return "null"
    return type(value).__name__  # pragma: no cover - JSON has no other types


def _normalize_keys(value: Any, id_map: dict[str, str]) -> Any:
    """Replace scenario-generated ids appearing as *dict keys* with stable
    placeholders (e.g. the page-id keys of ``POST /pages/preview/batch``).

    Values don't need this — ``shape_of`` reduces them to type names.
    """
    if isinstance(value, dict):
        return {id_map.get(k, k): _normalize_keys(v, id_map) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_keys(item, id_map) for item in value]
    return value


class Recorder:
    """Hits endpoints through a TestClient and records response shapes."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.records: list[dict[str, Any]] = []
        self.id_map: dict[str, str] = {}

    def hit(
        self,
        label: str,
        method: str,
        path_template: str,
        *,
        path_params: dict[str, str] | None = None,
        json_body: Any = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        path = path_template
        for name, value in (path_params or {}).items():
            path = path.replace("{" + name + "}", value)
        response = self.client.request(method, path, json=json_body, params=params)
        try:
            body = response.json()
        except ValueError:  # pragma: no cover - all these endpoints return JSON
            body = None
        self.records.append(
            {
                "label": label,
                "method": method,
                "path_template": path_template,
                "status": response.status_code,
                "shape": shape_of(_normalize_keys(body, self.id_map)),
            }
        )
        return body

    def covered_routes(self) -> set[tuple[str, str]]:
        return {(r["method"], r["path_template"]) for r in self.records}


def _assert_matches_golden(domain: str, recorder: Recorder, expected_routes: set[tuple[str, str]]) -> None:
    """Full-scope + golden-equality assertion shared by the three tests."""
    # Every route in scope is exercised, and nothing out of scope sneaks in.
    assert recorder.covered_routes() == expected_routes, (
        f"{domain} scenario coverage drifted from the #1756 move scope."
    )
    # Every scoped route actually exists on the app with that method. Reuse
    # the inventory walker — FastAPI >= 0.130 hides include_router() routes
    # behind _IncludedRouter nodes, which it knows how to flatten.
    from tests.test_route_inventory import build_route_inventory

    app_routes = {(method, record["path"]) for record in build_route_inventory() for method in record["methods"]}
    missing = expected_routes - app_routes
    assert not missing, f"{domain} routes missing from the app: {sorted(missing)}"

    golden_path = GOLDEN_DIR / f"{domain}.json"
    payload = {
        "_comment": (
            f"Golden response shapes for the {domain} domain (issue #1756). "
            "Do not hand-edit: regenerate with "
            "`RECORD_RESPONSE_GOLDEN=1 pytest tests/test_response_shape_goldens.py` "
            "and review the diff."
        ),
        "records": recorder.records,
    }
    if RECORD:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        with golden_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        return
    if not golden_path.exists():
        pytest.fail(f"Missing golden file {golden_path}.\n{REGENERATE_HINT}")
    with golden_path.open(encoding="utf-8") as fh:
        golden = json.load(fh)["records"]
    golden_by_label = {r["label"]: r for r in golden}
    current_by_label = {r["label"]: r for r in recorder.records}
    assert list(current_by_label) == list(golden_by_label), REGENERATE_HINT
    for label, current in current_by_label.items():
        assert current == golden_by_label[label], (
            f"[{domain}] {label}: response drifted.\n"
            f"golden:  {json.dumps(golden_by_label[label], indent=2, sort_keys=True)}\n"
            f"current: {json.dumps(current, indent=2, sort_keys=True)}\n"
            f"{REGENERATE_HINT}"
        )


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _seed_page(client: TestClient, name: str, first_line: str) -> str:
    response = client.post(
        "/pages",
        json={
            "name": name,
            "type": "template",
            "device_type": "flagship",
            "template": [first_line, "", "", "", "", ""],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["page"]["id"]


MISSING_ID = "00000000-dead-beef-0000-000000000000"


# ---------------------------------------------------------------------------
# Domain scenarios
# ---------------------------------------------------------------------------


def test_pages_response_shapes():
    client = TestClient(app)
    rec = Recorder(client)

    page_id = _seed_page(client, "Golden Page A", "HELLO GOLDEN")
    other_id = _seed_page(client, "Golden Page B", "SECOND PAGE")
    rec.id_map = {page_id: "<page_id>", other_id: "<other_page_id>", MISSING_ID: "<missing_id>"}

    rec.hit("list_pages", "GET", "/pages")
    rec.hit(
        "create_page_ok",
        "POST",
        "/pages",
        json_body={
            "name": "Golden Created",
            "type": "template",
            "device_type": "flagship",
            "template": ["CREATED", "", "", "", "", ""],
        },
    )
    rec.hit("create_page_invalid", "POST", "/pages", json_body={"type": "template"})
    rec.hit("get_page_ok", "GET", "/pages/{page_id}", path_params={"page_id": page_id})
    rec.hit("get_page_missing", "GET", "/pages/{page_id}", path_params={"page_id": MISSING_ID})
    rec.hit(
        "update_page_ok",
        "PUT",
        "/pages/{page_id}",
        path_params={"page_id": page_id},
        json_body={"name": "Golden Page A Renamed"},
    )
    rec.hit(
        "update_page_missing",
        "PUT",
        "/pages/{page_id}",
        path_params={"page_id": MISSING_ID},
        json_body={"name": "Nobody"},
    )

    # Delete a non-active, non-last page so neither fallback branch fires and
    # the response shape stays deterministic.
    rec.hit("delete_page_ok", "DELETE", "/pages/{page_id}", path_params={"page_id": other_id})
    rec.hit("delete_page_missing", "DELETE", "/pages/{page_id}", path_params={"page_id": MISSING_ID})

    share_body = rec.hit("share_page_ok", "GET", "/pages/{page_id}/share", path_params={"page_id": page_id})
    rec.hit("share_page_missing", "GET", "/pages/{page_id}/share", path_params={"page_id": MISSING_ID})
    share_string = share_body["share_string"]
    rec.hit("import_preview_ok", "POST", "/pages/import/preview", json_body={"share_string": share_string})
    rec.hit("import_preview_invalid", "POST", "/pages/import/preview", json_body={"share_string": "not-a-share"})
    rec.hit("import_ok", "POST", "/pages/import", json_body={"share_string": share_string})

    picks = rec.hit("staff_picks_list", "GET", "/staff-picks")
    pick_id = picks[0]["id"] if picks else MISSING_ID
    rec.id_map[pick_id] = "<pick_id>"
    rec.hit("staff_pick_share_ok", "GET", "/staff-picks/{pick_id}/share", path_params={"pick_id": pick_id})
    rec.hit("staff_pick_share_missing", "GET", "/staff-picks/{pick_id}/share", path_params={"pick_id": MISSING_ID})

    rec.hit("preview_page_ok", "POST", "/pages/{page_id}/preview", path_params={"page_id": page_id})
    rec.hit("preview_page_missing", "POST", "/pages/{page_id}/preview", path_params={"page_id": MISSING_ID})
    rec.hit(
        "preview_batch_mixed",
        "POST",
        "/pages/preview/batch",
        json_body={"page_ids": [page_id, MISSING_ID]},
    )
    rec.hit("preview_batch_invalid", "POST", "/pages/preview/batch", json_body={"page_ids": "nope"})
    rec.hit("cache_stats", "GET", "/pages/cache/stats")
    rec.hit("cache_clear_all", "POST", "/pages/cache/clear", json_body={})
    rec.hit("cache_clear_one", "POST", "/pages/cache/clear", json_body={"page_id": page_id})

    # current-display: 404 with no active page, then 200 once one is set.
    rec.hit("current_display_no_active", "GET", "/pages/current-display")
    from src.settings.service import get_settings_service

    get_settings_service().set_active_page_id(page_id)
    rec.hit("current_display_ok", "GET", "/pages/current-display")

    # send: service unavailable, bad target, missing page, and a ui-only
    # success (never touches a board client).
    with patch("src.api_server.get_service", return_value=None):
        rec.hit("send_page_no_service", "POST", "/pages/{page_id}/send", path_params={"page_id": page_id})
    rec.hit(
        "send_page_bad_target",
        "POST",
        "/pages/{page_id}/send",
        path_params={"page_id": page_id},
        json_body={"target": "carrier-pigeon"},
    )
    mock_service = Mock()
    mock_service.vb_client = Mock()
    with patch("src.api_server.get_service", return_value=mock_service):
        rec.hit(
            "send_page_missing",
            "POST",
            "/pages/{page_id}/send",
            path_params={"page_id": MISSING_ID},
            json_body={"target": "ui"},
        )
        rec.hit(
            "send_page_ui_ok",
            "POST",
            "/pages/{page_id}/send",
            path_params={"page_id": page_id},
            json_body={"target": "ui"},
        )

    _assert_matches_golden("pages", rec, PAGES_ROUTES)


def test_schedules_response_shapes():
    client = TestClient(app)
    rec = Recorder(client)

    page_id = _seed_page(client, "Golden Sched Page", "SCHEDULED")
    rec.id_map = {page_id: "<page_id>", MISSING_ID: "<missing_id>"}

    rec.hit("list_schedules_empty", "GET", "/schedules")
    body = rec.hit(
        "create_schedule_ok",
        "POST",
        "/schedules",
        json_body={
            "page_id": page_id,
            "start_time": "00:00",
            "end_time": "23:59",
            "day_pattern": "all",
        },
    )
    schedule_id = body["id"]
    rec.id_map[schedule_id] = "<schedule_id>"
    rec.hit("create_schedule_invalid", "POST", "/schedules", json_body={"start_time": "25:99"})

    rec.hit("list_schedules", "GET", "/schedules")
    rec.hit("list_schedules_all_boards", "GET", "/schedules", params={"board_id": "*"})

    rec.hit("active_page_disabled", "GET", "/schedules/active/page")
    rec.hit("set_enabled_ok", "PUT", "/schedules/enabled", json_body={"enabled": True})
    rec.hit("active_page_enabled", "GET", "/schedules/active/page")
    rec.hit("get_enabled", "GET", "/schedules/enabled")
    rec.hit("set_enabled_invalid", "PUT", "/schedules/enabled", json_body={"enabled": "yes"})
    rec.hit("set_enabled_missing", "PUT", "/schedules/enabled", json_body={})

    rec.hit("validate_no_body", "POST", "/schedules/validate")
    rec.hit("validate_with_board", "POST", "/schedules/validate", json_body={"board_id": "board-1"})

    rec.hit("get_default_page", "GET", "/schedules/default-page")
    rec.hit("set_default_page_ok", "PUT", "/schedules/default-page", json_body={"page_id": page_id})
    rec.hit("set_default_page_missing_param", "PUT", "/schedules/default-page", json_body={})
    rec.hit("set_default_page_unknown_page", "PUT", "/schedules/default-page", json_body={"page_id": MISSING_ID})

    rec.hit("get_schedule_ok", "GET", "/schedules/{schedule_id}", path_params={"schedule_id": schedule_id})
    rec.hit("get_schedule_missing", "GET", "/schedules/{schedule_id}", path_params={"schedule_id": MISSING_ID})
    rec.hit(
        "update_schedule_ok",
        "PUT",
        "/schedules/{schedule_id}",
        path_params={"schedule_id": schedule_id},
        json_body={"start_time": "01:00"},
    )
    rec.hit(
        "update_schedule_missing",
        "PUT",
        "/schedules/{schedule_id}",
        path_params={"schedule_id": MISSING_ID},
        json_body={"start_time": "01:00"},
    )
    rec.hit(
        "delete_schedule_ok",
        "DELETE",
        "/schedules/{schedule_id}",
        path_params={"schedule_id": schedule_id},
    )
    rec.hit(
        "delete_schedule_missing",
        "DELETE",
        "/schedules/{schedule_id}",
        path_params={"schedule_id": MISSING_ID},
    )

    _assert_matches_golden("schedules", rec, SCHEDULES_ROUTES)


def test_collections_response_shapes():
    client = TestClient(app)
    rec = Recorder(client)

    page_a = _seed_page(client, "Golden Coll Page A", "COLL A")
    page_b = _seed_page(client, "Golden Coll Page B", "COLL B")
    rec.id_map = {page_a: "<page_a>", page_b: "<page_b>", MISSING_ID: "<missing_id>"}

    rec.hit("list_collections_empty", "GET", "/collections")
    body = rec.hit(
        "create_collection_ok",
        "POST",
        "/collections",
        json_body={"name": "Golden Collection", "page_ids": [page_a, page_b]},
    )
    collection_id = body["collection"]["id"]
    rec.id_map[collection_id] = "<collection_id>"
    rec.hit(
        "create_collection_unknown_page",
        "POST",
        "/collections",
        json_body={"name": "Bad Collection", "page_ids": [MISSING_ID]},
    )
    rec.hit("create_collection_invalid", "POST", "/collections", json_body={"name": "No Pages"})

    rec.hit("list_collections", "GET", "/collections")
    rec.hit(
        "get_collection_ok",
        "GET",
        "/collections/{collection_id}",
        path_params={"collection_id": collection_id},
    )
    rec.hit(
        "get_collection_missing",
        "GET",
        "/collections/{collection_id}",
        path_params={"collection_id": MISSING_ID},
    )
    rec.hit(
        "update_collection_ok",
        "PUT",
        "/collections/{collection_id}",
        path_params={"collection_id": collection_id},
        json_body={"name": "Golden Collection Renamed"},
    )
    rec.hit(
        "update_collection_unknown_page",
        "PUT",
        "/collections/{collection_id}",
        path_params={"collection_id": collection_id},
        json_body={"page_ids": [MISSING_ID]},
    )
    rec.hit(
        "update_collection_missing",
        "PUT",
        "/collections/{collection_id}",
        path_params={"collection_id": MISSING_ID},
        json_body={"name": "Nobody"},
    )
    rec.hit(
        "delete_collection_ok",
        "DELETE",
        "/collections/{collection_id}",
        path_params={"collection_id": collection_id},
    )
    rec.hit(
        "delete_collection_missing",
        "DELETE",
        "/collections/{collection_id}",
        path_params={"collection_id": MISSING_ID},
    )

    _assert_matches_golden("collections", rec, COLLECTIONS_ROUTES)
