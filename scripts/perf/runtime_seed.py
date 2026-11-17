"""Explicitly authorized synthetic seed; no network or mutation at import time."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from runtime_common import AMD64_MANIFEST, SOURCE_COMMIT, JsonlWriter, ProtocolError, require_ok, utc_now, validate_preview

ARM64_MANIFEST = "sha256:e0127d1f0eed00e13cd394f098580c2b96579b458731b6dc5d7ee842c7645886"
GEOMETRIES = {"flagship": ("flagship", 6, 22), "note": ("note", 3, 15), "array": ("note_array", 6, 30)}


def page_definitions(boards):
    pages = []
    labels = {"flagship": "F", "note": "N", "array": "A", "panel": "P"}
    for key, board in boards.items():
        for index in range(1, 25):
            kind = "literal" if index <= 8 else "formula" if index <= 16 else "single" if index <= 20 else "composite"
            name = f"PERF {labels[key]} {index:02}"
            page = {"name": name, "type": "template" if index <= 16 else kind, "device_type": board["device_type"],
                    "tags": ["perf", "alpha3", "synthetic", key], "geometry": key, "kind": kind}
            if key == "array":
                page.update(notes_wide=2, notes_tall=2)
            if key == "panel":
                page.update(grid_rows=board["rows"], grid_cols=board["cols"])
            if kind == "literal":
                page["template"] = [name, "FIXED", "END"] + [""] * (board["rows"] - 3)
                if index == 8:
                    page["template"] = [name, "PERF WRAPPING TEXT " * 3] + [""] * (board["rows"] - 2)
                    page["line_metadata"] = [{"alignment": "left", "wrap": i == 1} for i in range(board["rows"])]
            elif kind == "formula":
                page["template"] = [name, '{{= SUM(1,2) }} {{= UPPER("a") }}',
                                    '{{= DEFAULT(countdown.days,"N/A") }} {{= 4*5 }}'] + [""] * (board["rows"] - 3)
            elif kind == "single":
                page["display_type"] = "date_time" if index % 2 else "countdown"
            else:
                page["rows"] = [{"source": "date_time", "row_index": 0, "target_row": 0},
                                {"source": "countdown", "row_index": 0, "target_row": 1},
                                {"source": "date_time", "row_index": 1, "target_row": 2}]
            pages.append(page)
    return pages


def validate_ownership(client, ownership, *, for_setup=True):
    """Require the operator's bound pre-start attestation; this is not live proof."""
    if not isinstance(ownership, dict) or ownership.get("schema_version") != 1:
        raise ProtocolError("Missing ownership attestation")
    if ownership.get("base_url", "").rstrip("/") != client.base_url.rstrip("/"):
        raise ProtocolError("Ownership origin differs from target")
    if ownership.get("source_commit") != SOURCE_COMMIT or ownership.get("image_manifest") not in {
        AMD64_MANIFEST, ARM64_MANIFEST
    }:
        raise ProtocolError("Ownership image/source is not pinned alpha.3")
    if ownership.get("empty_before_start") is not True or ownership.get("prestart_entries") != []:
        raise ProtocolError("Complete data directory must be attested empty before startup")
    for key in ("seed_id", "container_id", "data_dir", "attested_utc"):
        if not isinstance(ownership.get(key), str) or not ownership[key].strip():
            raise ProtocolError("Ownership binding is incomplete")
    if not ownership["data_dir"].startswith("/"):
        raise ProtocolError("Ownership requires an absolute data directory")
    try:
        stamp = datetime.fromisoformat(ownership["attested_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolError("Ownership timestamp is not ISO8601") from exc
    if stamp.tzinfo is None:
        raise ProtocolError("Ownership timestamp needs an offset")
    now = datetime.now(timezone.utc)
    age = (now - stamp).total_seconds()
    if age < 0 or (for_setup and age > 300):
        raise ProtocolError("Pre-start emptiness attestation is stale or in the future")
    context = client.run_context
    if not isinstance(context, dict) or context.get("schema_version") != 1 or not context.get("run_id"):
        raise ProtocolError("An independent current operator run context is required")
    container = context.get("container", {})
    bindings = {"container_id": container.get("id"), "image_manifest": container.get("manifest_digest"),
                "base_url": context.get("target_origin"), "data_dir": context.get("data_dir"),
                "seed_id": context.get("seed_id"), "source_commit": context.get("source_commit")}
    if any(ownership.get(key) != value for key, value in bindings.items()):
        raise ProtocolError("Run context does not match the complete ownership binding")
    for value in (context.get("captured_utc"), context.get("exclusion", {}).get("checked_utc")):
        try:
            captured = datetime.fromisoformat(value.replace("Z", "+00:00"))
            context_age = (now - captured).total_seconds()
        except (AttributeError, TypeError, ValueError) as exc:
            raise ProtocolError("Run context timestamps missing/malformed") from exc
        if context_age < 0 or context_age > 300:
            raise ProtocolError("Independent run context is stale or in the future")
    exclusion = context.get("exclusion", {})
    names = exclusion.get("container_names")
    if len(exclusion.get("running_ids", [])) != 1 or not isinstance(names, list) or not 1 <= len(names) <= 3:
        raise ProtocolError("Run context does not establish serialized PROD exclusion within three containers")
    if "fb-dev-hub" not in names or not container.get("image_id"):
        raise ProtocolError("Run context does not identify the single published-image hub")


def seed(client, ownership, out_dir):
    validate_ownership(client, ownership)
    out_dir = Path(out_dir)
    if (out_dir / "manifest.json").exists():
        raise ProtocolError("Do not seed into an existing run directory")
    writer = JsonlWriter(out_dir / "seed-events.jsonl", ownership["seed_id"], secrets=client.secrets)
    previous_observer = client.observer
    client.observer = lambda method, path, payload, result: writer.write(
        "seed_request", method=method, path=path, request=payload, response=result
    )

    def call(method, path, payload=None, status=200):
        return require_ok(client.request(method, path, payload), status=status)

    try:
        status = call("GET", "/api/auth/status")
        if (status.get("enabled") is not True or status.get("mode") != "enabled"
                or status.get("setup_required") is not True):
            raise ProtocolError("Target must be auth-enabled with no existing account")
        answer = call("POST", "/api/auth/setup", client.credentials, status=201)
        if answer.get("status") != "ok" or answer.get("username") != client.credentials.get("username"):
            raise ProtocolError("Setup did not confirm synthetic account")
        session = client.session_info(min_valid_seconds=7800)
        writer.write("auth_metadata", **session)
        # Protected inventory cannot be read before setup with auth enabled. The
        # pre-start emptiness attestation above is an external prerequisite.
        for group in ("pages", "collections", "schedules", "panels"):
            prefix = "/api/panels" if group == "panels" else f"/api/v1/{group}"
            if group == "schedules":
                prefix += "?board_id=*"
            _list(client, prefix, group, 0)
        initial_boards = call("GET", "/api/settings/board").get("boards", [])
        if len(initial_boards) > 1:
            raise ProtocolError("Unexpected bootstrap board count")
        for board in initial_boards:
            if (board.get("name") != "My Board" or board.get("device_type") != "flagship"
                    or board.get("output") != "vestaboard"):
                raise ProtocolError("Unexpected bootstrap board")
            connection = {**board.get("output_config", {}), **board}
            if any(connection.get(key) for key in ("host", "local_api_key", "cloud_key", "note_array_token", "tiles")):
                raise ProtocolError("Bootstrap board has a configured physical connection")
        general = {"timezone": "UTC", "instance_name": "PERF ALPHA3", "time_format": "24h", "output_target": "both"}
        _compare(general, call("PUT", "/api/config/general", general))
        _compare(general, call("GET", "/api/config/general"))
        call("PUT", "/api/settings/plugins", {"auto_update": False})
        if call("GET", "/api/settings/plugins").get("auto_update") is not False:
            raise ProtocolError("Plugin auto-update was not disabled")
        definitions = [
            {"id": "perf-f", "name": "PERF Flagship", "device_type": "flagship", "api_mode": "virtual",
             "enabled": True, "paused": False, "schedule_enabled": False},
            {"id": "perf-n", "name": "PERF Note", "device_type": "note", "api_mode": "virtual",
             "enabled": True, "paused": False, "schedule_enabled": False},
            {"id": "perf-a", "name": "PERF Array", "device_type": "note_array", "notes_wide": 2, "notes_tall": 2,
             "api_mode": "virtual", "enabled": True, "paused": False, "schedule_enabled": False},
        ]
        response = call("PUT", "/api/settings/board", {"boards": definitions})
        if {b.get("id") for b in response.get("boards", [])} != {"perf-f", "perf-n", "perf-a"}:
            raise ProtocolError("Configured virtual board set differs")
        created_panel = call("POST", "/api/panels", {"name": "PERF Panel", "screen_diagonal_inches": 55,
                                                    "screen_aspect_w": 16, "screen_aspect_h": 9,
                                                    "render_style": "split_flap"}, status=201)
        if (created_panel.get("device_type") != "panel" or created_panel.get("board_missing") is not False
                or not created_panel.get("id") or not created_panel.get("board_id")):
            raise ProtocolError("Created panel is not bound to a virtual panel board")
        boards = {key: {"id": definition["id"], "name": definition["name"], "device_type": device,
                        "rows": rows, "cols": cols, "page_ids": []}
                  for (key, (device, rows, cols)), definition in zip(GEOMETRIES.items(), definitions)}
        boards["panel"] = {"id": created_panel["board_id"], "name": "PERF Panel (Panel)", "device_type": "panel",
                           "rows": created_panel.get("rows"), "cols": created_panel.get("cols"), "page_ids": []}
        panel = boards["panel"]
        if any(not isinstance(panel[axis], int) or panel[axis] < 3 for axis in ("rows", "cols")):
            raise ProtocolError("Panel returned invalid geometry")
        plugin_configs = {"date_time": {"timezone": "UTC"}, "countdown": {
            "event_name": "PERF EVENT", "target_datetime": "2030-01-01T00:00:00+00:00", "timezone": "UTC", "count_up": False
        }}
        plugin_metadata = {}
        for pid, config in plugin_configs.items():
            _compare(config, call("PUT", f"/api/plugins/{pid}/config", {"config": config}).get("config", {}))
            if call("POST", f"/api/plugins/{pid}/enable").get("enabled") is not True:
                raise ProtocolError("Local plugin did not enable")
            info = call("GET", f"/api/plugins/{pid}")
            _compare(config, info.get("config", {}))
            if info.get("version") != "1.3.1" or call("GET", f"/api/plugins/{pid}/data").get("available") is not True:
                raise ProtocolError("Bundled local plugin version/data differs")
            plugin_metadata[pid] = {"version": info["version"], "config": config}
        enabled = {p["id"] for p in call("GET", "/api/plugins").get("plugins", []) if p.get("enabled")}
        if enabled != {"date_time", "countdown"}:
            raise ProtocolError("Unexpected enabled plugin; do not disable unknown plugins automatically")
        manifest = {"schema_version": 1, "fixture": "published-alpha3-96-12-32", "seed_id": ownership["seed_id"],
                    "created_utc": utc_now(), "source_commit": SOURCE_COMMIT, "image_manifest": ownership["image_manifest"],
                    "base_url": client.base_url, "boards": boards, "panel_id": created_panel["id"], "pages": [],
                    "collections": [], "schedules": [], "plugins": plugin_metadata}
        for definition in page_definitions(boards):
            payload = {k: v for k, v in definition.items() if k not in {"geometry", "kind"}}
            page = call("POST", "/api/v1/pages", payload, status=201)
            _compare(payload, page)
            if not page.get("id") or not page.get("revision"):
                raise ProtocolError("Created page lacks generated ID/revision")
            manifest["pages"].append({**definition, "id": page["id"], "revision": page["revision"]})
            boards[definition["geometry"]]["page_ids"].append(page["id"])
        for key, board in boards.items():
            page_id = board["page_ids"][0]
            pinned = call("PUT", f"/api/v1/boards/{board['id']}/active-page", {"page_id": page_id})
            if pinned.get("page_id") != page_id or pinned.get("sent") is not True or pinned.get("error") or pinned.get("warnings"):
                raise ProtocolError("Selection was persisted but virtual frame was not successfully sent")
            detail = call("GET", f"/api/v1/boards/{board['id']}")
            marker = next(p["name"] for p in manifest["pages"] if p["id"] == page_id)
            frame = detail.get("characters")
            if (detail.get("active_page_id") != page_id or detail.get("resolved_page_id") != page_id
                    or not isinstance(frame, list) or len(frame) != board["rows"]
                    or any(not isinstance(row, list) or len(row) != board["cols"] for row in frame)
                    or marker not in (detail.get("text") or "") or detail.get("expected_characters") != frame):
                raise ProtocolError("Virtual board frame/selection does not match the seeded page")
            collection_ids = {}
            for index, mode in enumerate(("time", "random", "variable")):
                members = board["page_ids"][index * 8:(index + 1) * 8]
                payload = {"name": f"PERF {key} {mode}", "page_ids": members, "selection_mode": mode}
                if mode == "variable":
                    payload[mode] = {"rules": [{"expression": "date_time.hour >= 12", "page_id": members[0]}],
                                     "default_page_id": members[1], "poll_seconds": 10}
                else:
                    payload[mode] = {"interval_seconds": 30}
                created = call("POST", "/api/v1/collections", payload, status=201)
                _compare(payload, created)
                if not isinstance(created.get("id"), str) or not created["id"].startswith("collection:"):
                    raise ProtocolError("Collection ID lacks source-defined prefix")
                collection_ids[mode] = created["id"]
                manifest["collections"].append({**payload, "id": created["id"], "revision": created.get("revision"),
                                                "geometry": key, "mode": mode})
            schedule_specs = [
                (0, "06:00", "07:00", {"day_pattern": "weekdays"}),
                (1, "07:00", "08:00", {"day_pattern": "weekends"}),
                (2, "08:00", "09:00", {"day_pattern": "custom", "custom_days": ["monday", "wednesday"]}),
                (3, "23:00", "01:00", {}), (4, "20:00", None, {}),
                (5, "10:00", "11:00", {"recurrence_type": "annual_date", "annual_date": "11-17"}),
                (6, "10:30", "10:45", {"recurrence_type": "one_off_date", "one_off_date": "2026-11-17"}),
                (None, "12:00", "13:00", {}),
            ]
            for index, start, end, extra in schedule_specs:
                payload = {"board_id": board["id"], "page_id": board["page_ids"][index] if index is not None else collection_ids["time"],
                           "start_time": start, "end_time": end, "day_pattern": "all", "recurrence_type": "weekly",
                           "enabled": True, **extra}
                created = call("POST", "/api/v1/schedules", payload, status=201)
                _compare(payload, created)
                if created.get("warnings"):
                    raise ProtocolError("Schedule reports incompatible references")
                manifest["schedules"].append({**payload, "id": created["id"], "revision": created.get("revision")})
            for start in (0, 12):
                ids = board["page_ids"][start:start + 12]
                preview = call("POST", "/api/pages/preview/batch", {"page_ids": ids, "force_refresh": True, "board_id": board["id"]})
                validate_preview(preview, ids)
                if any(len(preview["previews"][pid]["lines"]) != board["rows"] for pid in ids):
                    raise ProtocolError("Preview rows differ from page geometry")
        call("PUT", "/api/settings/wizard", {"state": "completed"})
        manifest["verification"] = verify_manifest(client, manifest)
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
        with (out_dir / "manifest.json").open("x", encoding="utf-8") as output:
            output.write(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
        writer.write("seed_verified", manifest_sha256=manifest["manifest_sha256"], counts={"pages": 96, "collections": 12, "schedules": 32})
        return manifest
    except Exception as exc:
        writer.write("seed_failed", error=f"Seed stopped: {type(exc).__name__}")
        raise
    finally:
        client.observer = previous_observer
        writer.close()


def _list(client, path, key, count):
    body = require_ok(client.request("GET", path))
    items = body.get(key)
    if not isinstance(items, list) or body.get("total") != count or len(items) != count:
        raise ProtocolError(f"Wrong {key} count")
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(ids) != count or any(not isinstance(pid, str) or not pid for pid in ids) or len(set(ids)) != count:
        raise ProtocolError(f"Duplicate or malformed {key} IDs")
    return items


def _compare(expected, actual, ignored=()):
    for key, value in expected.items():
        if key not in ignored and actual.get(key) != value:
            raise ProtocolError(f"Read-back differs in {key}")


def _geometry(item):
    device = item.get("device_type")
    if device == "flagship":
        return device, 6, 22
    if device == "note":
        return device, 3, 15
    if device == "note_array":
        return device, 3 * item.get("notes_tall", 1), 15 * item.get("notes_wide", 1)
    if device == "panel":
        return device, item.get("grid_rows", item.get("rows")), item.get("grid_cols", item.get("cols"))
    raise ProtocolError("Unknown geometry")


def verify_manifest(client, manifest):
    """Verify exact ID sets, authorable read-back and per-board references."""
    if manifest.get("source_commit") != SOURCE_COMMIT or set(manifest.get("boards", {})) != {
        "flagship", "note", "array", "panel"
    }:
        raise ProtocolError("Manifest source/board set differs from fixture")
    boards = manifest["boards"]
    for key, expected in GEOMETRIES.items():
        board = boards[key]
        if (board.get("device_type"), board.get("rows"), board.get("cols")) != expected:
            raise ProtocolError("Manifest geometry differs from fixture")
    panel = boards["panel"]
    if panel.get("device_type") != "panel" or any(
        not isinstance(panel.get(axis), int) or panel[axis] <= 0 for axis in ("rows", "cols")
    ):
        raise ProtocolError("Panel geometry missing")
    if (panel["rows"], panel["cols"]) in {(6, 22), (3, 15), (6, 30)}:
        raise ProtocolError("Panel geometry is not distinct for 24-page filter assertions")
    for group, count in (("pages", 96), ("collections", 12), ("schedules", 32)):
        expected_items = manifest.get(group, [])
        if len(expected_items) != count:
            raise ProtocolError("Manifest counts differ from fixture")
        path = f"/api/v1/{group}" + ("?board_id=*" if group == "schedules" else "")
        items = _list(client, path, group, count)
        actual = {item["id"]: item for item in items}
        if set(actual) != {item["id"] for item in expected_items}:
            raise ProtocolError(f"Read-back {group} IDs differ from manifest")
        for item in expected_items:
            _compare(item, actual[item["id"]], {"geometry", "kind", "mode"})
            detail = require_ok(client.request("GET", f"/api/v1/{group}/{item['id']}"))
            _compare(item, detail, {"geometry", "kind", "mode"})
            if group == "pages":
                board = boards[item["geometry"]]
                if _geometry(actual[item["id"]]) != (board["device_type"], board["rows"], board["cols"]):
                    raise ProtocolError("Page geometry differs from its target board")
    for key, board in boards.items():
        pages = [p for p in manifest["pages"] if p["geometry"] == key]
        if len(pages) != 24 or set(board["page_ids"]) != {p["id"] for p in pages}:
            raise ProtocolError("Per-board page ID set differs")
        kinds = [p["kind"] for p in pages]
        if {kind: kinds.count(kind) for kind in set(kinds)} != {"literal": 8, "formula": 8, "single": 4, "composite": 4}:
            raise ProtocolError("Per-board page composition differs")
        collections = [c for c in manifest["collections"] if c["geometry"] == key]
        if len(collections) != 3 or {c["mode"] for c in collections} != {"time", "random", "variable"}:
            raise ProtocolError("Per-board collection modes differ")
        for collection in collections:
            members = collection["page_ids"]
            if len(members) != 8 or len(set(members)) != 8 or not set(members) <= set(board["page_ids"]):
                raise ProtocolError("Collection members differ from compatible fixture")
        schedules = _list(client, f"/api/v1/schedules?board_id={board['id']}", "schedules", 8)
        expected_schedules = {s["id"] for s in manifest["schedules"] if s["board_id"] == board["id"]}
        refs = set(board["page_ids"]) | {c["id"] for c in collections}
        if {s["id"] for s in schedules} != expected_schedules or any(
            s.get("board_id") != board["id"] or s.get("page_id") not in refs for s in schedules
        ):
            raise ProtocolError("Per-board schedules differ or reference incompatible content")
    configured = require_ok(client.request("GET", "/api/settings/board")).get("boards", [])
    if len(configured) != 4 or {b.get("id") for b in configured} != {b["id"] for b in boards.values()}:
        raise ProtocolError("Configured board IDs differ")
    by_id = {b["id"]: b for b in configured}
    for board in boards.values():
        actual = by_id[board["id"]]
        if (actual.get("output") != "fiestapanel" or actual.get("paused") is not False
                or actual.get("enabled") is not True or actual.get("schedule_enabled") is not False):
            raise ProtocolError("Board must be enabled, unpaused, virtual and in manual baseline mode")
        if _geometry(actual) != (board["device_type"], board["rows"], board["cols"]):
            raise ProtocolError("Configured board geometry differs")
    panels = _list(client, "/api/panels", "panels", 1)
    actual_panel = panels[0]
    if actual_panel.get("id") != manifest.get("panel_id") or actual_panel.get("board_id") != panel["id"]:
        raise ProtocolError("Panel binding differs")
    if actual_panel.get("board_missing") is not False or (actual_panel.get("rows"), actual_panel.get("cols")) != (
        panel["rows"], panel["cols"]
    ):
        raise ProtocolError("Panel geometry missing or changed")
    board_list = _list(client, "/api/v1/boards", "boards", 4)
    if {b["id"] for b in board_list} != set(by_id):
        raise ProtocolError("v1 board IDs differ from configured boards")
    status = require_ok(client.request("GET", "/api/v1/status"))
    if status.get("running") is not True or status.get("initialized") is not True or set(status.get("boards", {})) != set(by_id):
        raise ProtocolError("Published runtime is not running/initialized for the exact board set")
    for board in boards.values():
        bid, page_id = board["id"], board["page_ids"][0]
        state = status["boards"][bid]
        if state.get("configured") is not True or state.get("paused") is not False or state.get("error"):
            raise ProtocolError("Board runtime is unconfigured, paused or failed")
        detail = require_ok(client.request("GET", f"/api/v1/boards/{bid}"))
        frame = detail.get("characters")
        marker = next(p["name"] for p in manifest["pages"] if p["id"] == page_id)
        if (detail.get("source") != "manual" or detail.get("active_page_id") != page_id
                or detail.get("resolved_page_id") != page_id or detail.get("override_started_at") is not None
                or detail.get("override_expires_at") is not None or not isinstance(frame, list)
                or len(frame) != board["rows"] or any(not isinstance(row, list) or len(row) != board["cols"] for row in frame)
                or detail.get("expected_characters") != frame or marker not in (detail.get("text") or "")):
            raise ProtocolError("Manual selected frame changed, or an override is active")
        silence = require_ok(client.request("GET", f"/api/silence-status?board_id={bid}"))
        if silence.get("board_id") != bid or silence.get("enabled") is not False or silence.get("active") is not False or silence.get("held"):
            raise ProtocolError("Silence/held state contaminates manual baseline")
    return {"exact_counts": True, "exact_ids": True, "geometry": True, "read_back": True, "runtime_manual_state": True}
