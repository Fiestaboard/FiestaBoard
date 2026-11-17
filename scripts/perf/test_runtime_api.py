"""Offline standard-library harness tests; root serializes execution.

These tests exercise actual harness validators and use only a bounded HTTP
transport double where a real hub would otherwise be needed. No app starts.
"""

import copy
import json
import tempfile
import unittest
import hashlib
import io
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
from email.message import Message
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from runtime_api import ApiOperation, api_operations, sample_api
from runtime_api import main as api_main
from runtime_common import (
    AMD64_MANIFEST,
    SOURCE_COMMIT,
    HttpResult,
    JsonClient,
    ProtocolError,
    nearest_rank,
    read_credentials,
    redact,
    summarize_requests,
    validate_preview,
)
from runtime_seed import main as seed_main
from runtime_seed import page_definitions, seed, verify_manifest, verify_semantics


def ownership():
    return {
        "schema_version": 1,
        "seed_id": "offline-test",
        "base_url": "http://hub.invalid:3000",
        "data_dir": "/app/data/perf-offline-test",
        "container_id": "isolated-test-container",
        "source_commit": SOURCE_COMMIT,
        "image_manifest": AMD64_MANIFEST,
        "empty_before_start": True,
        "prestart_entries": [],
        "attested_utc": datetime.now(timezone.utc).isoformat(),
    }


def run_context():
    marker = ownership()
    stamp = datetime.now(timezone.utc).isoformat()
    return {"schema_version": 1, "run_id": "offline-run", "captured_utc": stamp,
            "seed_id": marker["seed_id"], "data_dir": marker["data_dir"], "source_commit": SOURCE_COMMIT,
            "target_origin": marker["base_url"], "container": {"id": marker["container_id"], "image_id": "image-test",
                "manifest_digest": AMD64_MANIFEST, "architecture": "amd64"}, "ownership_sha256": "0" * 64,
            "manifest_sha256": None, "exclusion": {"task_id": "prod-test", "running_ids": ["prod-test"], "container_names": ["fb-dev-hub"],
                "checked_utc": stamp, "browser_lease_owner": None}, "host": {"os": "test", "architecture": "test",
                "cpu": None, "memory": None, "unavailable": ["cpu", "memory"]},
            "calibration": {"relay_report_path": None, "lifecycle_report_path": None}}


class MemoryTransport:
    """Only HTTP exchange is replaced; validators/seed orchestration stay real."""

    def __init__(self, responses):
        self.responses = responses
        self.exchanges = []

    def __call__(self, method, url, payload, headers, timeout):
        path = urlsplit(url).path
        query = urlsplit(url).query
        target = path + ("?" + query if query else "")
        self.exchanges.append((method, target, payload))
        result = self.responses.get((method, target))
        if result is None:
            raise AssertionError(f"Unexpected HTTP exchange: {method} {target}")
        return result(method, target, payload) if callable(result) else copy.deepcopy(result)


def fixture():
    """Hand-authored shape, generated IDs only; no production fixture builder."""
    boards = {}
    pages = []
    collections = []
    schedules = []
    for key, device, rows, cols in [
        ("flagship", "flagship", 6, 22),
        ("note", "note", 3, 15),
        ("array", "note_array", 6, 30),
        ("panel", "panel", 8, 40),
    ]:
        ids = [f"{key}-{i:02}" for i in range(1, 25)]
        boards[key] = {"id": f"board-{key}", "name": key, "device_type": device, "rows": rows, "cols": cols,
                       "page_ids": ids}
        for i, pid in enumerate(ids, 1):
            page = {"id": pid, "name": f"PERF {key} {i:02}", "geometry": key, "revision": f"rev-{pid}",
                    "kind": "literal" if i <= 8 else "formula" if i <= 16 else "single" if i <= 20 else "composite",
                    "device_type": device, "type": "template" if i <= 16 else "single" if i <= 20 else "composite"}
            if key == "array":
                page.update(notes_wide=2, notes_tall=2)
            if key == "panel":
                page.update(grid_rows=rows, grid_cols=cols)
            pages.append(page)
        for i, mode in enumerate(("time", "random", "variable")):
            collections.append({"id": f"collection:{key}-{mode}", "name": f"PERF {key} {mode}", "geometry": key,
                                "mode": mode, "selection_mode": mode, "page_ids": ids[i * 8:(i + 1) * 8],
                                "revision": f"rev-{key}-{mode}", mode: {"interval_seconds": 30} if mode != "variable" else {
                                    "rules": [{"expression": "date_time.hour >= 12", "page_id": ids[16]}],
                                    "default_page_id": ids[17], "poll_seconds": 10}})
        for i in range(8):
            schedules.append({"id": f"schedule-{key}-{i}", "board_id": f"board-{key}", "page_id": ids[i],
                              "start_time": "06:00", "end_time": "07:00", "day_pattern": "weekdays",
                              "recurrence_type": "weekly", "enabled": True})
    return {"schema_version": 1, "fixture": "published-alpha3-96-12-32", "source_commit": SOURCE_COMMIT,
            "seed_id": "offline-test", "base_url": "http://hub.invalid:3000", "boards": boards, "pages": pages,
            "collections": collections, "schedules": schedules, "panel_id": "panel-test",
            "browser_preferences": {"theme": "light", "locale": "en-US", "next_locale": "en", "timezone": "UTC",
                "display": {"reduce_motion": False, "board_animations": "on", "site_animations": "on", "board_flap_speed": "standard"}}}


def fixture_transport(manifest):
    pages = [{k: v for k, v in p.items() if k not in {"geometry", "kind"}} for p in manifest["pages"]]
    collections = [{k: v for k, v in c.items() if k not in {"geometry", "mode"}} for c in manifest["collections"]]
    schedules = copy.deepcopy(manifest["schedules"])
    board_rows = []
    for board in manifest["boards"].values():
        row = {k: v for k, v in board.items() if k != "page_ids"}
        row["output"] = "fiestapanel"
        row["api_mode"] = "virtual"
        row["paused"] = False
        row["enabled"] = True
        row["schedule_enabled"] = False
        if row["device_type"] == "note_array":
            row.update(notes_wide=2, notes_tall=2)
        if row["device_type"] == "panel":
            row.update(grid_rows=8, grid_cols=40)
        board_rows.append(row)
    statuses = {b["id"]: {"configured": True, "paused": False, "active_page_id": manifest["boards"][key]["page_ids"][0],
                           "error": None} for key, b in zip(manifest["boards"], board_rows)}
    responses = {
        ("GET", "/api/auth/status"): HttpResult(200, {"enabled": True, "authenticated": True,
                                                    "setup_required": False, "auth_kind": "browser"}),
        ("GET", "/api/auth/sessions"): HttpResult(200, {"current_session_id": "browser-1", "sessions": [
            {"id": "browser-1", "kind": "browser", "expires_at": "2099-01-01T00:00:00+00:00"}]}),
        ("GET", "/api/v1/pages"): HttpResult(200, {"pages": pages, "total": 96}),
        ("GET", "/api/v1/collections"): HttpResult(200, {"collections": collections, "total": 12}),
        ("GET", "/api/v1/schedules?board_id=*"): HttpResult(200, {"schedules": schedules, "total": 32,
                                                             "enabled": None, "default_page_id": None}),
        ("GET", "/api/settings/board"): HttpResult(200, {"boards": board_rows}),
        ("GET", "/api/settings/display"): HttpResult(200, {"reduce_motion": False, "board_animations": "on", "site_animations": "on", "board_flap_speed": "standard"}),
        ("GET", "/api/v1/boards"): HttpResult(200, {"boards": board_rows, "total": 4}),
        ("GET", "/api/v1/status"): HttpResult(200, {"running": True, "initialized": True, "boards": statuses}),
        ("GET", "/api/panels"): HttpResult(200, {"panels": [{"id": "panel-test", "board_id": "board-panel",
                                                           "device_type": "panel", "rows": 8, "cols": 40,
                                                           "board_missing": False}], "total": 1}),
    }
    for group, entries in (("pages", pages), ("collections", collections), ("schedules", schedules)):
        for item in entries:
            responses[("GET", f"/api/v1/{group}/{item['id']}")] = HttpResult(200, item)
    for board in board_rows:
        own = [s for s in schedules if s["board_id"] == board["id"]]
        responses[("GET", f"/api/v1/schedules?board_id={board['id']}")] = HttpResult(
            200, {"schedules": own, "total": 8, "enabled": False, "default_page_id": None}
        )
        page = next(p for p in pages if p["id"] == statuses[board["id"]]["active_page_id"])
        frame = [[0] * board["cols"] for _ in range(board["rows"])]
        responses[("GET", f"/api/v1/boards/{board['id']}")] = HttpResult(
            200, {**board, "active_page_id": page["id"], "resolved_page_id": page["id"], "source": "manual",
                  "characters": frame, "expected_characters": frame, "text": page["name"],
                  "override_started_at": None, "override_expires_at": None}
        )
        responses[("GET", f"/api/silence-status?board_id={board['id']}")] = HttpResult(
            200, {"enabled": False, "active": False, "board_id": board["id"], "held": None}
        )
    return MemoryTransport(responses)


class SemanticTransport:
    """Published endpoint boundary fixtures, including stateful schedule-enable behavior."""

    def __init__(self, manifest, *, fail_formula=False, fail_boundary=False):
        self.manifest = manifest
        self.enabled = {b["id"]: False for b in manifest["boards"].values()}
        self.fail_formula, self.fail_boundary = fail_formula, fail_boundary
        self.exchanges = []

    def __call__(self, method, url, payload, headers, timeout):
        path, query = urlsplit(url).path, parse_qs(urlsplit(url).query)
        self.exchanges.append((method, url, payload))
        if method == "POST" and path == "/api/templates/render":
            rows = {"flagship": 6, "note": 3, "note_array": 6, "panel": 8}[payload["device_type"]]
            values = ["3", "A", "N/A", "20"] if not self.fail_formula else ["3", "A", "#REF", "20"]
            lines = ["PERF", "3 A", values[2] + " 20"] + [""] * (rows - 3)
            return HttpResult(200, {"rendered": "\n".join(lines), "lines": lines, "line_count": rows,
                "diagnostics": {"formulas": [{"value": value, "error": "#REF" if value == "#REF" else None} for value in values]}})
        if method == "POST" and path.endswith("/dry-run"):
            cid = path.split("/")[3]
            collection = next(c for c in self.manifest["collections"] if c["id"] == cid)
            matched = payload["values"]["date_time.hour"] >= 12
            pid = collection["page_ids"][0 if matched else 1]
            return HttpResult(200, {"collection_id": cid, "selection_mode": "variable", "page_id": pid,
                "matched_rule": 0 if matched else None, "rules": [{"matched": matched, "error": None}],
                "timeline": [], "truncated": False, "truncated_reason": None})
        if method == "PUT" and path == "/api/schedules/enabled":
            self.enabled[payload["board_id"]] = payload["enabled"]
            return HttpResult(200, {"enabled": payload["enabled"]})
        if method == "GET" and path == "/api/schedules/active/page":
            bid, instant = query["board_id"][0], query["at"][0]
            board = next(b for b in self.manifest["boards"].values() if b["id"] == bid)
            at = datetime.fromisoformat(instant)
            hhmm = at.strftime("%H:%M")
            mapping = {"05:59": None, "06:00": 0, "07:00": None, "10:00": 5, "10:30": 6, "10:45": 5,
                       "11:00": None, "13:00": None, "20:00": 4, "23:00": 3, "00:59": 3, "01:00": None, "08:00": 2}
            index = 1 if at.date().isoformat() == "2026-11-22" else mapping.get(hhmm)
            ref = board["page_ids"][index] if index is not None else None
            if hhmm == "12:00":
                ref = next(c["id"] for c in self.manifest["collections"] if c["geometry"] == next(
                    key for key, value in self.manifest["boards"].items() if value["id"] == bid) and c["mode"] == "time")
            if self.fail_boundary and hhmm == "10:45":
                ref = board["page_ids"][6]
            if not self.enabled[bid]:
                ref = board["page_ids"][0]
            return HttpResult(200, {"page_id": ref, "resolved_page_id": board["page_ids"][0] if ref and ref.startswith("collection:") else ref,
                "source": "schedule" if ref else "none", "schedule_enabled": self.enabled[bid],
                "at": instant, "silenced": False, "temporary_override": {"active": False}})
        raise AssertionError(f"Unexpected semantic HTTP exchange: {method} {path}")


class SeedTransport:
    """In-memory HTTP boundary for seed orchestration, with generated server IDs."""

    def __init__(self, *, unexpected_page=False, refuse_send=False):
        self.exchanges = []
        self.user = None
        self.boards = [{"id": "bootstrap", "name": "My Board", "device_type": "flagship", "api_mode": "local",
                        "output": "vestaboard", "host": "", "local_api_key": "", "cloud_key": ""}]
        self.groups = {"pages": [], "collections": [], "schedules": [], "panels": []}
        self.config = {}
        self.active = {}
        self.refuse_send = refuse_send
        self.semantic = None
        if unexpected_page:
            self.groups["pages"] = [{"id": "unexpected", "name": "Owner Content", "type": "template"}]

    def __call__(self, method, url, payload, headers, timeout):
        path, query = urlsplit(url).path, parse_qs(urlsplit(url).query)
        self.exchanges.append((method, path, copy.deepcopy(payload)))
        if path == "/api/auth/status" and method == "GET":
            return HttpResult(200, {"enabled": True, "mode": "enabled", "setup_required": self.user is None,
                                    "authenticated": self.user is not None, "auth_kind": "browser" if self.user else None})
        if path == "/api/auth/setup" and method == "POST" and self.user is None:
            self.user = payload["username"]
            return HttpResult(201, {"status": "ok", "username": self.user},
                              {"Set-Cookie": "fiestaboard_session=seed-cookie-secret; HttpOnly"})
        if path == "/api/auth/sessions" and method == "GET":
            return HttpResult(200, {"current_session_id": "browser-1", "sessions": [
                {"id": "browser-1", "kind": "browser", "expires_at": "2099-01-01T00:00:00+00:00"}]})
        if path == "/api/settings/board":
            if method == "PUT":
                self.boards = copy.deepcopy(payload["boards"])
                for board in self.boards:
                    board["output"] = "fiestapanel" if board["api_mode"] == "virtual" else "vestaboard"
            return HttpResult(200, {"boards": copy.deepcopy(self.boards)})
        if path == "/api/panels" and method == "POST":
            panel = {**payload, "id": "generated-panel", "board_id": "generated-panel-board", "rows": 8, "cols": 40,
                     "device_type": "panel", "board_missing": False}
            self.groups["panels"].append(panel)
            self.boards.append({"id": panel["board_id"], "name": payload["name"] + " (Panel)", "device_type": "panel",
                                "grid_rows": 8, "grid_cols": 40, "api_mode": "virtual", "output": "fiestapanel",
                                "enabled": True, "paused": False, "schedule_enabled": False})
            return HttpResult(201, panel)
        if (path == "/api/templates/render" or path.endswith("/dry-run")
                or path in {"/api/schedules/enabled", "/api/schedules/active/page"}):
            if self.semantic is None:
                boards = {}
                for key, board in zip(("flagship", "note", "array", "panel"), self.boards):
                    rows, cols = {"flagship": (6, 22), "note": (3, 15), "note_array": (6, 30), "panel": (8, 40)}[board["device_type"]]
                    boards[key] = {**board, "rows": rows, "cols": cols, "page_ids": [p["id"] for p in self.groups["pages"]
                                                                                      if p["device_type"] == board["device_type"]]}
                collections = [{**collection, "mode": collection["selection_mode"], "geometry": next(
                    key for key, board in boards.items() if collection["page_ids"][0] in board["page_ids"])}
                    for collection in self.groups["collections"]]
                self.semantic = SemanticTransport({"boards": boards, "collections": collections})
            answer = self.semantic(method, url, payload, headers, timeout)
            if path == "/api/schedules/enabled":
                next(b for b in self.boards if b["id"] == payload["board_id"])["schedule_enabled"] = payload["enabled"]
            return answer
        for group in ("pages", "collections", "schedules", "panels"):
            prefix = "/api/panels" if group == "panels" else f"/api/v1/{group}"
            if path == prefix:
                if method == "POST" and group != "panels":
                    count = len(self.groups[group]) + 1
                    generated_id = f"collection:generated-{count}" if group == "collections" else f"{group}-{count}"
                    item = {**copy.deepcopy(payload), "id": generated_id, "revision": f"rev-{generated_id}"}
                    if group == "schedules":
                        item["warnings"] = []
                    self.groups[group].append(item)
                    return HttpResult(201, item)
                if method == "GET":
                    items = copy.deepcopy(self.groups[group])
                    if group == "schedules" and query.get("board_id", ["*"])[0] != "*":
                        items = [s for s in items if s["board_id"] == query["board_id"][0]]
                    return HttpResult(200, {group: items, "total": len(items)})
            if method == "GET" and path.startswith(prefix + "/"):
                pid = path[len(prefix) + 1:]
                return HttpResult(200, next(copy.deepcopy(p) for p in self.groups[group] if p["id"] == pid))
        if path == "/api/v1/status" and method == "GET":
            return HttpResult(200, {"running": True, "initialized": True, "boards": {
                b["id"]: {"configured": True, "paused": False, "error": None,
                           "active_page_id": self.active.get(b["id"])} for b in self.boards}})
        if path == "/api/v1/boards" and method == "GET":
            return HttpResult(200, {"boards": copy.deepcopy(self.boards), "total": len(self.boards)})
        if path == "/api/silence-status" and method == "GET":
            return HttpResult(200, {"enabled": False, "active": False, "board_id": query["board_id"][0], "held": None})
        if path.startswith("/api/v1/boards/"):
            bid = path.split("/")[4]
            if method == "PUT" and path.endswith("/active-page"):
                self.active[bid] = payload["page_id"]
                return HttpResult(200, {"board_id": bid, "page_id": payload["page_id"], "sent": not self.refuse_send,
                                        "error": "refused" if self.refuse_send else None, "warnings": []})
            if method == "GET":
                board = next(b for b in self.boards if b["id"] == bid)
                rows, cols = {"flagship": (6, 22), "note": (3, 15), "note_array": (6, 30), "panel": (8, 40)}[
                    board["device_type"]]
                page = next(p for p in self.groups["pages"] if p["id"] == self.active[bid])
                frame = [[0] * cols for _ in range(rows)]
                return HttpResult(200, {**board, "rows": rows, "cols": cols, "active_page_id": page["id"],
                                        "resolved_page_id": page["id"], "source": "manual", "text": page["name"],
                                        "characters": frame, "expected_characters": frame,
                                        "override_started_at": None, "override_expires_at": None})
        if path in {"/api/config/general", "/api/settings/plugins", "/api/settings/wizard", "/api/settings/display"}:
            if method == "PUT":
                self.config[path] = payload
            return HttpResult(200, copy.deepcopy(self.config.get(path, {})))
        if path.startswith("/api/plugins/"):
            plugin = path.split("/")[3]
            if method == "PUT" and path.endswith("/config"):
                self.config[plugin] = payload["config"]
                return HttpResult(200, {"plugin_id": plugin, "config": payload["config"]})
            if method == "POST" and path.endswith("/enable"):
                return HttpResult(200, {"plugin_id": plugin, "enabled": True})
            if method == "GET" and path.endswith("/data"):
                return HttpResult(200, {"plugin_id": plugin, "available": True, "data": {}, "formatted_lines": ["PERF"]})
            if method == "GET" and path == f"/api/plugins/{plugin}":
                return HttpResult(200, {"id": plugin, "version": "1.3.1", "enabled": True,
                                        "config": self.config.get(plugin, {})})
        if path == "/api/plugins" and method == "GET":
            return HttpResult(200, {"plugins": [{"id": "date_time", "enabled": True},
                                               {"id": "countdown", "enabled": True}], "total": 2, "enabled_count": 2})
        if path == "/api/pages/preview/batch" and method == "POST":
            previews = {}
            for pid in payload["page_ids"]:
                page = next(p for p in self.groups["pages"] if p["id"] == pid)
                rows = {"flagship": 6, "note": 3, "note_array": 6, "panel": 8}[page["device_type"]]
                previews[pid] = {"page_id": pid, "available": True, "lines": [page["name"]] + [""] * (rows - 1)}
            return HttpResult(200, {"previews": previews, "total": len(previews), "successful": len(previews)})
        raise AssertionError(f"Unexpected seed HTTP exchange: {method} {path}")


class RuntimeContractTests(unittest.TestCase):
    def test_client_construction_does_not_authenticate_or_contact_hub(self):
        # A constructor-side login would mutate the wrong store before ownership checking.
        transport = MemoryTransport({})
        JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "secret"}, transport=transport)
        self.assertEqual(transport.exchanges, [])

    def test_existing_account_rejected_before_any_mutation(self):
        # Removing the setup_required guard would permit resetting/seeding an existing install.
        transport = MemoryTransport({("GET", "/api/auth/status"): HttpResult(
            200, {"enabled": True, "setup_required": False, "authenticated": False, "mode": "enabled"})})
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "secret"}, transport=transport)
        client.run_context = run_context()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                seed(client, ownership(), Path(directory))
        self.assertEqual([x for x in transport.exchanges if x[0] != "GET"], [])
        self.assertEqual([x[:2] for x in transport.exchanges], [("GET", "/api/auth/status")])

    def test_wrong_origin_owner_attestation_rejected_before_network(self):
        # Ignoring owner-origin binding could seed another service with a valid marker.
        marker = ownership()
        marker["base_url"] = "http://other.invalid:3000"
        transport = MemoryTransport({})
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "secret"}, transport=transport)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                seed(client, marker, Path(directory))
        self.assertEqual(transport.exchanges, [])

    def test_missing_prestart_empty_inventory_rejected_before_network(self):
        # Name prefixes do not establish that the entire store was fresh before startup.
        marker = ownership()
        marker["prestart_entries"] = ["auth.json"]
        transport = MemoryTransport({})
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "secret"}, transport=transport)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                seed(client, marker, Path(directory))
        self.assertEqual(transport.exchanges, [])

    def test_fixture_verification_accepts_complete_matching_real_id_sets(self):
        data = fixture()
        client = JsonClient(data["base_url"], {}, transport=fixture_transport(data))
        self.assertIsNotNone(verify_manifest(client, data))

    def test_exact_readback_rejects_lie_about_total(self):
        # A list with 95 actual pages must fail even if the server reports total=96.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/v1/pages")].body["pages"].pop()
        client = JsonClient(data["base_url"], {}, transport=transport)
        with self.assertRaises(ProtocolError):
            verify_manifest(client, data)

    def test_exact_readback_rejects_replaced_id_with_unchanged_count(self):
        # Count-only assertions miss an unrelated object replacing a seeded object.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/v1/pages")].body["pages"][0]["id"] = "unrelated-owner-page"
        client = JsonClient(data["base_url"], {}, transport=transport)
        with self.assertRaises(ProtocolError):
            verify_manifest(client, data)

    def test_exact_readback_rejects_wrong_array_geometry(self):
        # Checking only device_type accepts a 1x1 Note array in a 2x2 fixture.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/v1/pages")].body["pages"][48]["notes_wide"] = 1
        client = JsonClient(data["base_url"], {}, transport=transport)
        with self.assertRaises(ProtocolError):
            verify_manifest(client, data)

    def test_http_200_preview_unavailable_item_is_semantic_failure(self):
        # HTTP status alone cannot establish success of a batch preview.
        body = {"total": 2, "successful": 2, "previews": {
            "p1": {"page_id": "p1", "available": True, "lines": ["PERF"]},
            "p2": {"page_id": "p2", "available": False, "error": "render failed"},
        }}
        with self.assertRaises(ProtocolError):
            validate_preview(body, ["p1", "p2"])

    def test_nearest_rank_p95_is_190_for_200_values(self):
        # Interpolation or off-by-one rank would quietly alter the regression baseline.
        self.assertEqual(nearest_rank(list(range(1, 201)), 0.95), 190)

    def test_fast_401_cannot_improve_latency_or_validity(self):
        # Pooling failures into latency allows quick authentication failures to look faster.
        records = [{"elapsed_ms": n, "http_status": 200, "semantic_success": True} for n in range(1, 201)]
        records.append({"elapsed_ms": 0.01, "http_status": 401, "semantic_success": False, "error": "unauthorized"})
        report = summarize_requests(records)
        self.assertFalse(report["valid"])
        self.assertEqual(report["successful"], 200)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["latency_ms"]["p95"], 190)

    def test_redacts_nested_credentials_headers_and_echoed_error_values(self):
        # Key-only redaction misses server/transport errors echoing a secret in free text.
        raw = {"password": "password-secret", "headers": {"Set-Cookie": "fiestaboard_session=cookie-secret",
                                                       "Cookie": "fiestaboard_session=cookie-secret"},
               "error": "password-secret then cookie-secret", "safe": {"page_id": "perf-note-01"}}
        saved = json.dumps(redact(raw, ("password-secret", "cookie-secret")))
        self.assertNotIn("password-secret", saved)
        self.assertNotIn("cookie-secret", saved)
        self.assertIn("perf-note-01", saved)

    def test_timeout_is_censored_without_retry(self):
        # Retrying or treating a timeout as a completed fast request hides failures.
        calls = []

        def timeout_transport(*args):
            calls.append(args)
            raise TimeoutError("timed out")

        client = JsonClient("http://hub.invalid:3000", {}, transport=timeout_transport, timeout=0.05)
        result = client.request("GET", "/api/v1/health")
        self.assertTrue(result.timed_out)
        self.assertEqual(result.status, 0)
        self.assertEqual(len(calls), 1)

    def test_explicit_login_verifies_current_browser_session_expiry(self):
        # A successful login envelope alone does not prove auth or sufficient session lifetime.
        transport = MemoryTransport({
            ("POST", "/api/auth/login"): HttpResult(200, {"status": "ok", "username": "perf"},
                                                   {"Set-Cookie": "fiestaboard_session=cookie-secret; HttpOnly"}),
            ("GET", "/api/auth/status"): HttpResult(200, {"enabled": True, "authenticated": True,
                                                        "setup_required": False, "auth_kind": "browser"}),
            ("GET", "/api/auth/sessions"): HttpResult(200, {"current_session_id": "browser-1", "sessions": [
                {"id": "browser-1", "kind": "browser", "expires_at": "2099-01-01T00:00:00+00:00"}]}),
        })
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "password-secret"},
                            transport=transport, run_context=run_context())
        session = client.login(min_valid_seconds=7800)
        self.assertIsNotNone(session)
        self.assertEqual(session["active_sessions"], 1)
        self.assertEqual(session["current_session_id"], "browser-1")
        self.assertNotIn("cookie-secret", json.dumps(client.safe_result(transport.responses[("POST", "/api/auth/login")])) )

    def test_short_session_cannot_start_long_measurement(self):
        # Ignoring actual expiry makes a long run end in 401s despite a fresh context.
        transport = MemoryTransport({
            ("POST", "/api/auth/login"): HttpResult(200, {"status": "ok", "username": "perf"}),
            ("GET", "/api/auth/status"): HttpResult(200, {"enabled": True, "authenticated": True,
                                                        "setup_required": False, "auth_kind": "browser"}),
            ("GET", "/api/auth/sessions"): HttpResult(200, {"current_session_id": "browser-1", "sessions": [
                {"id": "browser-1", "kind": "browser", "expires_at": "2000-01-01T00:00:00+00:00"}]}),
        })
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "password-secret"},
                            transport=transport, run_context=run_context())
        with self.assertRaises(ProtocolError):
            client.login(min_valid_seconds=7800)

    def test_page_definitions_preserve_four_exact_geometries_and_content_mix(self):
        # Dropping explicit panel/array dimensions changes real rendering and library counts.
        definitions = page_definitions(fixture()["boards"])
        self.assertEqual(len(definitions), 96)
        self.assertEqual(len({p["name"] for p in definitions}), 96)
        for geometry, device, rows, cols in [("flagship", "flagship", 6, 22), ("note", "note", 3, 15),
                                             ("array", "note_array", 6, 30), ("panel", "panel", 8, 40)]:
            group = [p for p in definitions if p["geometry"] == geometry]
            self.assertEqual(len(group), 24)
            self.assertEqual([sum(p["kind"] == kind for p in group) for kind in
                              ("literal", "formula", "single", "composite")], [8, 8, 4, 4])
            for page in group:
                self.assertEqual(page["device_type"], device)
                if geometry == "array":
                    self.assertEqual((page["notes_tall"], page["notes_wide"]), (2, 2))
                if geometry == "panel":
                    self.assertEqual((page["grid_rows"], page["grid_cols"]), (rows, cols))
            self.assertTrue(any(any(m.get("wrap") for m in p.get("line_metadata", [])) for p in group))

    def test_sampling_retains_semantic_failure_raw_record(self):
        # A 200 with an unavailable preview must survive JSONL and invalidate the batch.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("POST", "/api/pages/preview/batch")] = HttpResult(
            200, {"total": 1, "successful": 0, "previews": {"flagship-01": {"available": False, "error": "bad"}}},
            elapsed_ms=4.0, body_bytes=80
        )
        client = JsonClient(data["base_url"], {}, transport=transport)
        op = ApiOperation("preview", "flagship", "forced", "POST", "/api/pages/preview/batch",
                          {"page_ids": ["flagship-01"]}, lambda body: validate_preview(body, ["flagship-01"]))
        with tempfile.TemporaryDirectory() as directory:
            report = sample_api(client, data, Path(directory), batches=1, samples=1, warmups=0, operations=[op])
            self.assertIs(report.get("valid"), False)
            raw_file = Path(directory) / "requests.jsonl"
            self.assertTrue(raw_file.exists())
            records = [json.loads(line) for line in raw_file.read_text().splitlines()]
        requests = [r for r in records if r["record_type"] == "request"]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["http_status"], 200)
        self.assertFalse(requests[0]["semantic_success"])
        self.assertEqual(report["strata"][0]["failed"], 1)

    def test_sampling_auth_failure_aborts_without_hidden_relogin_or_retry(self):
        # Once auth expires, producing remaining fast 401 samples would misrepresent the batch.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/v1/health")] = HttpResult(401, {"detail": "unauthorized"}, elapsed_ms=0.1)
        client = JsonClient(data["base_url"], {}, transport=transport)
        op = ApiOperation("health", "all", "n/a", "GET", "/api/v1/health", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            report = sample_api(client, data, Path(directory), batches=1, samples=3, warmups=0, operations=[op])
            self.assertIs(report.get("valid"), False)
            self.assertIs(report.get("aborted"), True)
        sampled = [x for x in transport.exchanges if x[1] == "/api/v1/health"]
        self.assertEqual(len(sampled), 1)
        self.assertEqual([x for x in transport.exchanges if x[1] == "/api/auth/login"], [])

    def test_seed_reads_actual_generated_ids_and_never_sends_wrong_geometry(self):
        # A seed that guesses IDs/dimensions or leaves a partial content set is unusable for browser/API runs.
        transport = SeedTransport()
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "password-secret"},
                            transport=transport, run_context=run_context())
        with tempfile.TemporaryDirectory() as directory:
            manifest = seed(client, ownership(), Path(directory))
            self.assertEqual([len(manifest[group]) for group in ("pages", "collections", "schedules")], [96, 12, 32])
            self.assertEqual(manifest["boards"]["panel"]["id"], "generated-panel-board")
            self.assertEqual((manifest["boards"]["panel"]["rows"], manifest["boards"]["panel"]["cols"]), (8, 40))
            self.assertTrue(manifest["verification"]["exact_ids"])
            self.assertTrue(manifest["verification"].get("h6_formula"))
            self.assertTrue(manifest["verification"].get("h8_boundaries"))
            self.assertEqual(manifest.get("browser_preferences"), {"theme": "light", "locale": "en-US", "next_locale": "en", "timezone": "UTC",
                "display": {"reduce_motion": False, "board_animations": "on", "site_animations": "on", "board_flap_speed": "standard"}})
            for artifact in Path(directory).iterdir():
                raw = artifact.read_text()
                self.assertNotIn("password-secret", raw)
                self.assertNotIn("seed-cookie-secret", raw)
        pins = [x for x in transport.exchanges if x[0] == "PUT" and x[1].endswith("/active-page")]
        self.assertEqual(len(pins), 4)
        self.assertEqual(transport.exchanges[0][:2], ("GET", "/api/auth/status"))

    def test_unexpected_content_after_setup_prevents_seed_configuration_writes(self):
        # Public status cannot inspect protected content; the first post-setup inventory must stop wrong-store writes.
        transport = SeedTransport(unexpected_page=True)
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "password-secret"},
                            transport=transport, run_context=run_context())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                seed(client, ownership(), Path(directory))
        writes = [x[1] for x in transport.exchanges if x[0] != "GET"]
        self.assertEqual(writes, ["/api/auth/setup"])

    def test_pin_refusal_does_not_produce_verified_manifest(self):
        # Persisted selection must not masquerade as successful virtual delivery.
        transport = SeedTransport(refuse_send=True)
        client = JsonClient("http://hub.invalid:3000", {"username": "perf", "password": "password-secret"},
                            transport=transport, run_context=run_context())
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                seed(client, ownership(), Path(directory))
            self.assertFalse((Path(directory) / "manifest.json").exists())
        self.assertTrue(any(x[1].endswith("/active-page") for x in transport.exchanges))

    def test_private_credentials_reject_world_readable_file(self):
        # Accepting a public credentials artifact would leak the synthetic admin secret.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text('{"username":"perf","password":"password-secret"}')
            path.chmod(0o644)
            with self.assertRaises(ProtocolError):
                read_credentials(path)

    def test_api_strata_use_variable_only_dryrun_and_exact_geometry(self):
        # Generic3600s time/random dryruns silently truncate; omitted panel axes render wrong shape.
        operations = api_operations(fixture())
        self.assertTrue(operations)
        self.assertTrue({"health", "status", "pages", "collections", "schedules_all"} <= {op.name for op in operations})
        dryruns = [op for op in operations if op.name == "collection_dry_run"]
        self.assertEqual(len(dryruns), 4)
        for op in dryruns:
            self.assertIn("-variable/", op.path)
            self.assertEqual((op.payload["window_seconds"], op.payload["step_seconds"]), (3600, 300))
        renders = [op for op in operations if op.name.startswith("render") and op.geometry == "panel"]
        self.assertTrue(renders)
        for op in renders:
            self.assertEqual((op.payload["grid_rows"], op.payload["grid_cols"]), (8, 40))
        previews = [op for op in operations if op.name == "preview_batch_forced"]
        self.assertEqual(len(previews), 4)
        for op in previews:
            self.assertEqual(len(op.payload["page_ids"]), 12)
            self.assertTrue(op.payload["force_refresh"])

    def test_save_uses_returned_nested_revision_on_next_changed_save(self):
        # Stale expected_revision reuse would turn most of the save baseline into fast412s.
        data = fixture()
        operations = api_operations(data)
        saves = [op for op in operations if op.name == "save" and op.geometry == "note"]
        self.assertEqual(len(saves), 1)
        op = saves[0]
        transport = fixture_transport(data)
        page_id = op.path.rsplit("/", 1)[1]
        original = next(p for p in data["pages"] if p["id"] == page_id)
        original_revision = original["revision"]
        transport.responses[("PUT", op.path)] = lambda method, target, payload: HttpResult(
            200, {"page": {**original, "template": payload["template"], "revision": "next-generation"},
                  "incompatible_references": []}
        )
        client = JsonClient(data["base_url"], {}, transport=transport)
        with tempfile.TemporaryDirectory() as directory:
            sample_api(client, data, Path(directory), batches=1, samples=2, warmups=0, operations=[op])
        saves = [x for x in transport.exchanges if x[:2] == ("PUT", op.path)]
        self.assertEqual(saves[0][2]["expected_revision"], original_revision)
        self.assertEqual(saves[1][2]["expected_revision"], "next-generation")
        self.assertNotEqual(saves[0][2]["template"][0], saves[1][2]["template"][0])

    def test_stale_or_future_empty_attestation_stops_before_network(self):
        # A replayed marker must not authorize provisioning on a repurposed hub.
        for offset in (-3600, 3600):
            with self.subTest(offset=offset):
                marker = ownership()
                marker["attested_utc"] = (datetime.now(timezone.utc) + timedelta(seconds=offset)).isoformat()
                transport = MemoryTransport({("GET", "/api/auth/status"): HttpResult(
                    200, {"enabled": True, "mode": "enabled", "setup_required": False})})
                client = JsonClient(marker["base_url"], {}, transport=transport, run_context=run_context())
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ProtocolError):
                        seed(client, marker, Path(directory))
                self.assertEqual(transport.exchanges, [])

    def test_independent_live_context_must_match_complete_store_binding(self):
        # Checking only a nonempty container ID accepts an ownership marker for another container.
        for field in ("container_id", "data_dir", "seed_id", "image_manifest", "source_commit", "base_url"):
            with self.subTest(field=field):
                marker, context = ownership(), run_context()
                if field == "container_id":
                    context["container"]["id"] = "different"
                elif field == "image_manifest":
                    context["container"]["manifest_digest"] = "different"
                else:
                    context["target_origin" if field == "base_url" else field] = "different"
                transport = MemoryTransport({("GET", "/api/auth/status"): HttpResult(
                    200, {"enabled": True, "mode": "enabled", "setup_required": False})})
                client = JsonClient(marker["base_url"], {}, transport=transport, run_context=context)
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ProtocolError):
                        seed(client, marker, Path(directory))
                self.assertEqual(transport.exchanges, [])

    def test_sampler_refuses_auth_disabled_target_before_timed_requests(self):
        # A matching fixture in an open install must never be labeled browser-cookie measurements.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/auth/status")].body["enabled"] = False
        transport.responses[("GET", "/api/v1/health")] = HttpResult(200, {"status": "healthy"})
        client = JsonClient(data["base_url"], {}, transport=transport)
        operation = ApiOperation("health", "all", "n/a", "GET", "/api/v1/health", None, lambda body: None)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProtocolError):
                sample_api(client, data, Path(directory), batches=1, samples=1, warmups=0, operations=[operation])
        self.assertEqual([x for x in transport.exchanges if x[1] == "/api/v1/health"], [])

    def test_batch_fixture_rejects_changed_schedule_or_override_or_silence(self):
        # Exact content counts do not prove that manual-page01 is actually the frame being exercised.
        for changed in ("schedule", "override", "silence", "uninitialized"):
            with self.subTest(changed=changed):
                data = fixture()
                transport = fixture_transport(data)
                if changed == "schedule":
                    transport.responses[("GET", "/api/settings/board")].body["boards"][0]["schedule_enabled"] = True
                elif changed == "override":
                    transport.responses[("GET", "/api/v1/boards/board-flagship")].body["override_started_at"] = "2026-11-17T00:00:00+00:00"
                elif changed == "silence":
                    transport.responses[("GET", "/api/silence-status?board_id=board-flagship")].body["active"] = True
                else:
                    transport.responses[("GET", "/api/v1/status")].body["initialized"] = False
                with self.assertRaises(ProtocolError):
                    verify_manifest(JsonClient(data["base_url"], {}, transport=transport), data)

    def test_h6_h8_smoke_verifies_values_boundaries_and_restores_schedule_state(self):
        # HTTP200 alone cannot prove sampled formulas, calendar priorities or the end-exclusive boundary.
        data = fixture()
        transport = SemanticTransport(data)
        report = verify_semantics(JsonClient(data["base_url"], {}, transport=transport), data)
        self.assertEqual(report, {"h6_formula": True, "h8_boundaries": True, "variable_rules": True})
        self.assertTrue(all(enabled is False for enabled in transport.enabled.values()))

    def test_wrong_formula_or_boundary_fails_and_restores_schedule_state(self):
        # A failing boundary query must not leave scheduling enabled and contaminate later browser runs.
        for kwargs in ({"fail_formula": True}, {"fail_boundary": True}):
            with self.subTest(kwargs=kwargs):
                data = fixture()
                transport = SemanticTransport(data, **kwargs)
                with self.assertRaises(ProtocolError):
                    verify_semantics(JsonClient(data["base_url"], {}, transport=transport), data)
                self.assertTrue(all(enabled is False for enabled in transport.enabled.values()))

    def test_cli_hash_mismatch_prevents_any_network_request(self):
        # Comparing parsed owner contents to themselves does not bind the original operator file bytes.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = ownership()
            context = run_context()
            context["ownership_sha256"] = "f" * 64
            for filename, value in (("owner.json", marker), ("context.json", context),
                                    ("credentials.json", {"username": "perf", "password": "password-secret"})):
                file = root / filename
                file.write_text(json.dumps(value))
                file.chmod(0o600)
            transport = MemoryTransport({})
            client = JsonClient(marker["base_url"], {"username": "perf", "password": "password-secret"}, transport=transport)
            with patch("runtime_seed.JsonClient", return_value=client), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = seed_main(["seed", "--base-url", marker["base_url"], "--ownership", str(root / "owner.json"),
                    "--run-context", str(root / "context.json"), "--credentials", str(root / "credentials.json"),
                    "--out-dir", str(root / "out")])
            self.assertEqual(code, 2)
            self.assertEqual(transport.exchanges, [])

    def test_real_default_preview_validator_accepts_only_complete_success(self):
        # A missing import inside the generated lambda escaped operation-definition-only tests.
        operation = next(op for op in api_operations(fixture()) if op.name == "preview_batch_forced")
        ids = operation.payload["page_ids"]
        body = {"total": 12, "successful": 12, "previews": {pid: {"page_id": pid, "available": True,
                "lines": ["PERF"]} for pid in ids}}
        self.assertIsNone(operation.validate(body))
        body["previews"][ids[-1]]["available"] = False
        with self.assertRaises(ProtocolError):
            operation.validate(body)

    def test_default_send_401_aborts_before_cleanup_and_retains_summary(self):
        # Cleanup must not issue a mutation after the immediate auth-abort boundary.
        data = fixture()
        operation = next(op for op in api_operations(data) if op.name == "send" and op.geometry == "note")
        transport = fixture_transport(data)
        transport.responses[("POST", operation.path)] = HttpResult(401, {"detail": "unauthorized"})
        client = JsonClient(data["base_url"], {}, transport=transport)
        with tempfile.TemporaryDirectory() as directory:
            report = sample_api(client, data, Path(directory), batches=1, samples=2, warmups=0, operations=[operation])
            saved = json.loads((Path(directory) / "summary.json").read_text())
        self.assertTrue(report["aborted"])
        self.assertFalse(report["valid"])
        self.assertTrue(saved["aborted"])
        self.assertEqual([x for x in transport.exchanges if x[0] == "PUT"], [])

    def test_real_transport_reuses_connection_and_carries_real_server_cookie(self):
        # urllib's default Connection:close would change the agreed steady latency profile.
        class Response:
            status = 200
            will_close = False

            def __init__(self):
                self.headers = Message()
                self.headers["Set-Cookie"] = "fiestaboard_session=server-cookie; Path=/; HttpOnly; SameSite=Lax"

            def read(self, limit):
                return b'{"status":"ok"}'

            def close(self):
                pass

        class Connection:
            sock = None

            def __init__(self):
                self.requests = []

            def request(self, method, target, body, headers):
                self.sock = object()
                self.requests.append((method, target, headers))

            def getresponse(self):
                return Response()

            def close(self):
                self.sock = None

        connection = Connection()
        client = JsonClient("http://hub.invalid:3000", {}, connection_factory=lambda: connection)
        first = client.request("GET", "/api/auth/status")
        second = client.request("GET", "/api/v1/health")
        self.assertEqual(first.status, 200)
        self.assertFalse(first.connection_reused)
        self.assertTrue(second.connection_reused)
        self.assertEqual({key.lower(): value for key, value in connection.requests[1][2].items()}["cookie"],
                         "fiestaboard_session=server-cookie")
        self.assertNotIn("server-cookie", json.dumps(client.safe_result(first)))

    def test_metadata_redirect_is_not_followed_even_to_same_origin(self):
        # Redirect-following changes the measured path and can leak cookies across origins.
        class Connection:
            sock = None

            def __init__(self):
                self.requests = []

            def request(self, method, target, body, headers):
                self.requests.append(target)

            def getresponse(self):
                response = type("Response", (), {"status": 302, "will_close": False,
                    "read": lambda self, limit: b"{}", "close": lambda self: None})()
                response.headers = Message()
                response.headers["Location"] = "http://other.invalid/api/v1/health"
                return response

        connection = Connection()
        result = JsonClient("http://hub.invalid:3000", {}, connection_factory=lambda: connection).request("GET", "/api/v1/health")
        self.assertEqual(result.status, 302)
        self.assertEqual(connection.requests, ["/api/v1/health"])

    def test_api_cli_rejects_bad_operator_hash_before_login(self):
        # Sampling's entrypoint must enforce the same external byte binding as the seeder.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, context = ownership(), run_context()
            context["ownership_sha256"] = "f" * 64
            for name, value in (("owner.json", marker), ("context.json", context),
                                ("credentials.json", {"username": "perf", "password": "password-secret"})):
                path = root / name
                path.write_text(json.dumps(value))
                path.chmod(0o600)
            transport = MemoryTransport({})
            client = JsonClient(marker["base_url"], {}, transport=transport)
            with patch("runtime_seed.JsonClient", return_value=client), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                code = api_main(["--base-url", marker["base_url"], "--ownership", str(root / "owner.json"),
                                 "--run-context", str(root / "context.json"), "--credentials", str(root / "credentials.json"),
                                 "--manifest", str(root / "manifest.json"), "--out-dir", str(root / "out")])
            self.assertEqual(code, 2)
            self.assertEqual(transport.exchanges, [])

    def test_literal_running_inventory_allows_non_prod_jobs_but_rejects_competing_prod(self):
        # Filtering the evidence before saving it loses load metadata; requiring just one total job falsely blocks harmless work.
        for competing in (False, True):
            with self.subTest(competing=competing):
                context = run_context()
                context["exclusion"]["running_ids"] = ["prod-test", "web23", "native-preview"] + (["prod-other"] if competing else [])
                transport = MemoryTransport({("GET", "/api/auth/status"): HttpResult(
                    200, {"enabled": True, "mode": "enabled", "setup_required": False})})
                client = JsonClient("http://hub.invalid:3000", {}, transport=transport, run_context=context)
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ProtocolError):
                        seed(client, ownership(), Path(directory))
                self.assertEqual([x[:2] for x in transport.exchanges], [] if competing else [("GET", "/api/auth/status")])

    def test_h8_query_auth_failure_suppresses_restoration_mutation(self):
        # A401 must stop the whole authentication scope, including finally-block mutations.
        class ExpiringTransport(SemanticTransport):
            def __call__(self, method, url, payload, headers, timeout):
                if method == "GET" and urlsplit(url).path == "/api/schedules/active/page":
                    self.exchanges.append((method, url, payload))
                    return HttpResult(401, {"detail": "expired"})
                return super().__call__(method, url, payload, headers, timeout)

        data = fixture()
        transport = ExpiringTransport(data)
        with self.assertRaises(ProtocolError):
            verify_semantics(JsonClient(data["base_url"], {}, transport=transport), data)
        enables = [payload["enabled"] for method, url, payload in transport.exchanges if method == "PUT" and urlsplit(url).path == "/api/schedules/enabled"]
        self.assertEqual(enables, [True])
        self.assertTrue(any(transport.enabled.values()))  # Explicit operator recovery remains necessary.

    def test_changed_display_preferences_fail_batch_verification(self):
        # Same content counts with animations disabled are a different browser workload.
        data = fixture()
        transport = fixture_transport(data)
        transport.responses[("GET", "/api/settings/display")].body["board_animations"] = "off"
        with self.assertRaises(ProtocolError):
            verify_manifest(JsonClient(data["base_url"], {}, transport=transport), data)


if __name__ == "__main__":
    unittest.main()
