"""Response-shape golden tests for the pages / schedules / collections domains,
extended to the plugins domain for issue #1757.

Issue #1756 moves the first three route families out of ``src/api_server.py``
into per-domain routers; #1757 does the same for the ``/plugins`` family. The move must be behavior-preserving, and the classic way
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
from types import SimpleNamespace
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

# The /plugins family issue #1757 moves. Deliberately excluded, other domains:
# /transitions/plugins (transitions), /settings/plugins (settings), /triggers.
PLUGINS_ROUTES = {
    ("GET", "/plugins"),
    ("GET", "/plugins/variables/all"),
    ("GET", "/plugins/errors"),
    ("GET", "/plugins/registry"),
    ("GET", "/plugins/updates"),
    ("GET", "/plugins/{plugin_id}"),
    ("GET", "/plugins/{plugin_id}/manifest"),
    ("PUT", "/plugins/{plugin_id}/config"),
    ("POST", "/plugins/{plugin_id}/enable"),
    ("POST", "/plugins/{plugin_id}/disable"),
    ("GET", "/plugins/{plugin_id}/data"),
    ("GET", "/plugins/{plugin_id}/variables"),
    ("POST", "/plugins/{plugin_id}/options/{options_id}"),
    ("GET", "/plugins/{plugin_id}/demo-page"),
    ("POST", "/plugins/{plugin_id}/demo-page"),
    ("GET", "/plugins/{plugin_id}/instances"),
    ("POST", "/plugins/{plugin_id}/instances"),
    ("DELETE", "/plugins/{plugin_id}/instances/{instance_label}"),
    ("POST", "/plugins/{plugin_id}/receive"),
    ("POST", "/plugins/registry/{plugin_id}/install"),
    ("POST", "/plugins/install"),
    ("DELETE", "/plugins/{plugin_id}/uninstall"),
    ("POST", "/plugins/updates/check"),
    ("POST", "/plugins/{plugin_id}/update"),
    ("POST", "/plugins/updates/apply"),
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


# ---------------------------------------------------------------------------
# Plugins domain (#1757)
#
# The plugin routes reach network (git clones, upstream APIs) and the live
# registry, so this scenario patches the same seams the rest of the API suite
# patches — ``src.api_server.get_plugin_registry`` / ``get_config_manager`` /
# ``reset_display_service`` / ``reset_template_engine`` /
# ``PLUGIN_SYSTEM_AVAILABLE`` — with deterministic stubs. The recorded shapes
# are of the stub-driven responses; identical stubs re-drive identical shapes
# on re-record, and the golden then proves the extracted router still resolves
# every one of those seams through ``src.api_server`` at call time.
# ---------------------------------------------------------------------------


_ALPHA_SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "api_key": {"type": "string", "title": "API Key"},
        "location": {"type": "string", "title": "Location"},
        "symbols": {
            "type": "array",
            "ui:widget": "remote-options",
            "ui:options": {"options_id": "symbols"},
        },
    },
    "required": ["api_key"],
}


class _GoldenManifest:
    """Just enough manifest surface for the plugin routes."""

    def __init__(self, plugin_id: str, demo: dict[str, Any] | None) -> None:
        self.name = plugin_id.title()
        self.version = "1.0.0"
        self.description = f"Golden fixture plugin '{plugin_id}'."
        self.author = "FiestaBoard Tests"
        self.icon = "puzzle"
        self.category = "utility"
        self.plugin_type = "data"
        self.settings_schema = _ALPHA_SETTINGS_SCHEMA
        self.raw = {
            "variables": {"value": {"description": "A value", "example": "X"}},
            "color_rules_schema": {},
        }
        self.max_lengths = {"value": 10}
        self.env_vars = []
        self.documentation = None
        self.demo = demo


class _GoldenPlugin:
    """A live-plugin stand-in for the receive endpoint."""

    def __init__(self, supports_receive: bool) -> None:
        self._supports_receive = supports_receive

    def receive_payload(self, body: Any, headers: Any, raw_body: bytes | None = None) -> None:
        if not self._supports_receive:
            raise NotImplementedError("receive is not supported")


class _GoldenRegistry:
    """Deterministic registry stub covering the whole /plugins route family."""

    def __init__(self) -> None:
        from src.plugins.base import Option, OptionsResult

        self.plugins = {"alpha": _GoldenPlugin(True), "norecv": _GoldenPlugin(False)}
        self.manifests = {
            "alpha": _GoldenManifest("alpha", demo={"flagship": {"template": ["DEMO"]}}),
            "norecv": _GoldenManifest("norecv", demo=None),
        }
        self.enabled = {"alpha": True, "norecv": True}
        self.enable_ok = True
        self.config_errors: list[str] = []
        self.fetch_result: Any = SimpleNamespace(
            available=True, data={"value": "X"}, formatted_lines=["LINE"], error=None
        )
        self.update_status = {"ext_plugin": True}
        self.sources = {"alpha": SimpleNamespace(source_type="builtin", local_path=None)}
        self.options_result = OptionsResult(options=[Option(value="AAPL", label="Apple")])

    # -- read surface -------------------------------------------------------
    def list_plugins(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "alpha",
                "name": "Alpha",
                "version": "1.0.0",
                "description": "Golden fixture plugin 'alpha'.",
                "enabled": True,
                "base_plugin_id": None,
                "instance_label": None,
            },
            {
                "id": "ext_plugin",
                "name": "Ext Plugin",
                "version": "0.1.0",
                "description": "Golden fixture external plugin.",
                "enabled": False,
                "base_plugin_id": None,
                "instance_label": None,
            },
        ]

    def get_all_variables(self) -> dict[str, Any]:
        return {"alpha": {"value": {"description": "A value", "example": "X"}}}

    def get_all_max_lengths(self) -> dict[str, Any]:
        return {"alpha": {"value": 10}}

    def get_load_errors(self) -> dict[str, Any]:
        return {"broken_plugin": ["ImportError: golden fixture"]}

    def get_registry_entries(self) -> list[dict[str, Any]]:
        return [{"id": "beta", "name": "Beta", "installed": False, "repository": "fiestaboard-plugin--beta"}]

    def get_update_status(self) -> dict[str, bool]:
        return dict(self.update_status)

    def get_update_blocked_reasons(self) -> dict[str, str]:
        return {"blocked_plugin": "the incoming manifest needs a newer FiestaBoard core"}

    def get_manifest(self, plugin_id: str) -> Any:
        return self.manifests.get(plugin_id)

    def get_plugin(self, plugin_id: str) -> Any:
        return self.plugins.get(plugin_id)

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any] | None:
        return {"api_key": "test_key_123"} if plugin_id == "alpha" else None

    def is_enabled(self, plugin_id: str) -> bool:
        return self.enabled.get(plugin_id, False)

    def fetch_plugin_data(self, plugin_id: str) -> Any:
        return self.fetch_result

    def get_plugin_options(self, plugin_id: str, options_id: str, request: Any, draft_config: Any = None) -> Any:
        return self.options_result

    # -- instances ----------------------------------------------------------
    def parse_instance_key(self, plugin_id: str) -> tuple[str, str | None]:
        base, _, label = plugin_id.partition(":")
        return base, (label or None)

    def make_instance_key(self, base_id: str, label: str) -> str:
        return f"{base_id}:{label}"

    def list_instances(self, base_id: str) -> list[dict[str, Any]]:
        return [{"label": "work", "enabled": False}] if base_id == "alpha" else []

    def create_instance(self, base_id: str, label: str) -> list[str]:
        return [] if label != "bad label" else ["Invalid instance label"]

    def delete_instance(self, base_id: str, label: str) -> list[str]:
        return []

    def apply_stored_config(self, compound_key: str, stored: dict[str, Any]) -> list[str]:
        return []

    # -- mutation surface ---------------------------------------------------
    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> list[str]:
        return list(self.config_errors)

    def enable_plugin(self, plugin_id: str) -> bool:
        return self.enable_ok

    def disable_plugin(self, plugin_id: str) -> bool:
        return True

    # -- install / update surface -------------------------------------------
    def install_from_registry(self, plugin_id: str) -> list[str]:
        return [] if plugin_id == "beta" else [f"Plugin '{plugin_id}' not found in the registry"]

    def install_from_git(self, repository: str, plugin_id: str | None = None, branch: str = "") -> list[str]:
        return []

    def uninstall_external_plugin(self, plugin_id: str) -> list[str]:
        return [] if plugin_id == "ext_plugin" else [f"Plugin '{plugin_id}' is a built-in plugin"]

    def check_for_updates(self) -> dict[str, bool]:
        return {"ext_plugin": True, "quiet_plugin": False}

    def get_plugin_source(self, plugin_id: str) -> Any:
        return self.sources.get(plugin_id)


class _GoldenConfigManager:
    """ConfigManager stub with the same masking contract as the real one."""

    SENSITIVE = {"api_key"}

    def __init__(self) -> None:
        self.configs: dict[str, dict[str, Any]] = {
            "alpha": {"enabled": True, "api_key": "test_key_123", "location": "New York, NY"},
        }

    def get_plugin_config(self, plugin_id: str, include_env_overrides: bool = True) -> dict[str, Any] | None:
        config = self.configs.get(plugin_id)
        return dict(config) if config else None

    def get_plugin_env_overrides(self, plugin_id: str) -> dict[str, Any]:
        return {}

    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> None:
        self.configs[plugin_id] = dict(config)

    def enable_plugin(self, plugin_id: str) -> None:
        self.configs.setdefault(plugin_id, {})["enabled"] = True

    def disable_plugin(self, plugin_id: str) -> None:
        self.configs.setdefault(plugin_id, {})["enabled"] = False

    def delete_plugin_config(self, plugin_id: str) -> None:
        self.configs.pop(plugin_id, None)

    def mark_plugin_removed(self, plugin_id: str) -> None:
        pass

    def clear_plugin_removed(self, plugin_id: str) -> None:
        pass

    def _mask_sensitive(self, obj: Any, path: str = "") -> Any:
        if isinstance(obj, dict):
            return {
                key: ("***" if key in self.SENSITIVE and isinstance(value, str) else self._mask_sensitive(value))
                for key, value in obj.items()
            }
        return obj


def test_plugins_response_shapes():
    client = TestClient(app)
    rec = Recorder(client)

    registry = _GoldenRegistry()
    config_manager = _GoldenConfigManager()
    page_service = SimpleNamespace(
        get_demo_page=lambda plugin_id, device_type=None: None,
        create_demo_page=lambda plugin_id, schema: (
            SimpleNamespace(model_dump=lambda: {"id": "demo-page-1", "name": "Alpha Demo", "type": "template"}),
            False,
        ),
    )

    with (
        patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", True),
        patch("src.api_server.get_plugin_registry", new=lambda: registry),
        patch("src.api_server.get_config_manager", new=lambda: config_manager),
        patch("src.api_server.reset_display_service", new=Mock()),
        patch("src.api_server.reset_template_engine", new=Mock()),
        patch("src.api_server.get_page_service", new=lambda: page_service),
        # Process-global options caches: isolate the scenario from other tests.
        patch("src.api_server._PLUGIN_OPTIONS_CACHE", new={}),
        patch("src.api_server._plugin_options_last_refresh", new={}),
    ):
        with patch("src.api_server.PLUGIN_SYSTEM_AVAILABLE", False):
            rec.hit("plugin_system_unavailable", "GET", "/plugins")

        rec.hit("list_plugins", "GET", "/plugins")
        rec.hit("all_variables", "GET", "/plugins/variables/all")
        rec.hit("plugin_errors", "GET", "/plugins/errors")
        rec.hit("registry_list", "GET", "/plugins/registry")
        rec.hit("updates_status", "GET", "/plugins/updates")

        rec.hit("get_plugin_ok", "GET", "/plugins/{plugin_id}", path_params={"plugin_id": "alpha"})
        rec.hit("get_plugin_missing", "GET", "/plugins/{plugin_id}", path_params={"plugin_id": "missing"})
        rec.hit("get_manifest_ok", "GET", "/plugins/{plugin_id}/manifest", path_params={"plugin_id": "alpha"})
        rec.hit("get_manifest_missing", "GET", "/plugins/{plugin_id}/manifest", path_params={"plugin_id": "missing"})

        # Config update: the masked-secret round trip ("***" posted back must
        # not clobber the stored credential) plus validation + missing errors.
        rec.hit(
            "update_config_ok",
            "PUT",
            "/plugins/{plugin_id}/config",
            path_params={"plugin_id": "alpha"},
            json_body={"config": {"api_key": "***", "location": "London, UK", "refresh_seconds": 300}},
        )
        registry.config_errors = ["api_key: does not match the schema"]
        rec.hit(
            "update_config_invalid",
            "PUT",
            "/plugins/{plugin_id}/config",
            path_params={"plugin_id": "alpha"},
            json_body={"config": {"api_key": 5}},
        )
        registry.config_errors = []
        rec.hit(
            "update_config_missing",
            "PUT",
            "/plugins/{plugin_id}/config",
            path_params={"plugin_id": "missing"},
            json_body={"config": {}},
        )

        rec.hit("enable_ok", "POST", "/plugins/{plugin_id}/enable", path_params={"plugin_id": "alpha"})
        rec.hit("enable_missing", "POST", "/plugins/{plugin_id}/enable", path_params={"plugin_id": "missing"})
        registry.enable_ok = False
        rec.hit("enable_failed", "POST", "/plugins/{plugin_id}/enable", path_params={"plugin_id": "alpha"})
        registry.enable_ok = True
        rec.hit("disable_ok", "POST", "/plugins/{plugin_id}/disable", path_params={"plugin_id": "alpha"})

        rec.hit("get_data_ok", "GET", "/plugins/{plugin_id}/data", path_params={"plugin_id": "alpha"})
        registry.fetch_result = SimpleNamespace(
            available=False, data=None, formatted_lines=None, error="not configured"
        )
        rec.hit("get_data_unavailable", "GET", "/plugins/{plugin_id}/data", path_params={"plugin_id": "alpha"})
        registry.enabled["alpha"] = False
        rec.hit("get_data_disabled", "GET", "/plugins/{plugin_id}/data", path_params={"plugin_id": "alpha"})
        registry.enabled["alpha"] = True

        rec.hit("get_variables_ok", "GET", "/plugins/{plugin_id}/variables", path_params={"plugin_id": "alpha"})

        rec.hit(
            "options_ok",
            "POST",
            "/plugins/{plugin_id}/options/{options_id}",
            path_params={"plugin_id": "alpha", "options_id": "symbols"},
            json_body={"query": "AAP"},
        )
        rec.hit(
            "options_undeclared",
            "POST",
            "/plugins/{plugin_id}/options/{options_id}",
            path_params={"plugin_id": "alpha", "options_id": "not_declared"},
            json_body={},
        )

        rec.hit("demo_get", "GET", "/plugins/{plugin_id}/demo-page", path_params={"plugin_id": "alpha"})
        rec.hit("demo_get_no_demo", "GET", "/plugins/{plugin_id}/demo-page", path_params={"plugin_id": "norecv"})
        rec.hit(
            "demo_create",
            "POST",
            "/plugins/{plugin_id}/demo-page",
            path_params={"plugin_id": "alpha"},
            params={"device_type": "flagship"},
        )
        rec.hit(
            "demo_create_no_demo",
            "POST",
            "/plugins/{plugin_id}/demo-page",
            path_params={"plugin_id": "norecv"},
            params={"device_type": "flagship"},
        )

        rec.hit("instances_list", "GET", "/plugins/{plugin_id}/instances", path_params={"plugin_id": "alpha"})
        rec.hit(
            "instance_create",
            "POST",
            "/plugins/{plugin_id}/instances",
            path_params={"plugin_id": "alpha"},
            json_body={"label": "work2"},
        )
        rec.hit(
            "instance_create_invalid",
            "POST",
            "/plugins/{plugin_id}/instances",
            path_params={"plugin_id": "alpha"},
            json_body={"label": "bad label"},
        )
        rec.hit(
            "instance_delete",
            "DELETE",
            "/plugins/{plugin_id}/instances/{instance_label}",
            path_params={"plugin_id": "alpha", "instance_label": "work2"},
        )

        rec.hit(
            "receive_ok",
            "POST",
            "/plugins/{plugin_id}/receive",
            path_params={"plugin_id": "alpha"},
            json_body={"event": "golden"},
        )
        rec.hit(
            "receive_not_supported",
            "POST",
            "/plugins/{plugin_id}/receive",
            path_params={"plugin_id": "norecv"},
            json_body={"event": "golden"},
        )

        rec.hit(
            "registry_install_ok",
            "POST",
            "/plugins/registry/{plugin_id}/install",
            path_params={"plugin_id": "beta"},
        )
        rec.hit(
            "registry_install_error",
            "POST",
            "/plugins/registry/{plugin_id}/install",
            path_params={"plugin_id": "nope"},
        )

        rec.hit(
            "install_git_ok",
            "POST",
            "/plugins/install",
            json_body={"repository": "https://github.com/example/fiestaboard-plugin--goldenext.git"},
        )
        rec.hit(
            "install_git_bad_branch",
            "POST",
            "/plugins/install",
            json_body={
                "repository": "https://github.com/example/fiestaboard-plugin--goldenext.git",
                "branch": "bad branch",
            },
        )

        rec.hit("uninstall_ok", "DELETE", "/plugins/{plugin_id}/uninstall", path_params={"plugin_id": "ext_plugin"})
        rec.hit("uninstall_error", "DELETE", "/plugins/{plugin_id}/uninstall", path_params={"plugin_id": "alpha"})

        rec.hit("updates_check", "POST", "/plugins/updates/check")
        rec.hit(
            "update_plugin_missing_source",
            "POST",
            "/plugins/{plugin_id}/update",
            path_params={"plugin_id": "missing"},
        )
        rec.hit("update_plugin_builtin", "POST", "/plugins/{plugin_id}/update", path_params={"plugin_id": "alpha"})
        registry.update_status = {}
        rec.hit("updates_apply_none", "POST", "/plugins/updates/apply")

    _assert_matches_golden("plugins", rec, PLUGINS_ROUTES)
