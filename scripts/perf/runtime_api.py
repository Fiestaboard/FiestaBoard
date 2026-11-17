"""Published-image endpoint calibration; all execution is explicitly requested."""

from dataclasses import dataclass
from pathlib import Path
import json
import uuid
import re
import argparse
import sys
from urllib.parse import urlencode

from runtime_common import JsonlWriter, ProtocolError, require_ok, summarize_requests, validate_preview
from runtime_seed import add_input_arguments, load_inputs, verify_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit authenticated published-image API calibration")
    add_input_arguments(parser)
    parser.add_argument("--batches", type=int, default=3)
    parser.add_argument("--samples", type=int, default=200)
    parser.add_argument("--warmups", type=int, default=20)
    args = parser.parse_args(argv)
    client = None
    try:
        client, _, manifest = load_inputs(args)
        client.login(min_valid_seconds=7800)
        report = sample_api(client, manifest, args.out_dir, args.batches, args.samples, args.warmups)
        return 0 if report["valid"] else 2
    except (OSError, ProtocolError, ValueError, KeyError, TypeError) as exc:
        print(f"API calibration refused: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        if client is not None:
            client.close()


@dataclass
class ApiOperation:
    name: str
    geometry: str
    cache: str
    method: str
    path: str
    payload: object
    validate: object
    cleanup: object = None
    expected_status: int = 200
    abort_on_failure: bool = False
    kind: str = "ordinary"
    transition_index: object = None
    transition_target: object = None


def api_operations(manifest):
    def check(condition, message):
        if not condition:
            raise ProtocolError(message)

    def listing(key, count):
        return lambda body: check(body.get("total") == count and len(body.get(key, [])) == count,
                                  "Timed list count differs from verified fixture")

    operations = [
        ApiOperation("health", "all", "n/a", "GET", "/api/v1/health", None,
                     lambda body: check(body.get("status") == "healthy", "Liveness failed")),
        ApiOperation("status", "all", "n/a", "GET", "/api/v1/status", None,
                     lambda body: check(body.get("running") is True and body.get("initialized") is True,
                                        "Runtime stopped or uninitialized")),
        ApiOperation("boards", "all", "n/a", "GET", "/api/v1/boards", None, listing("boards", 4)),
        ApiOperation("pages", "all", "n/a", "GET", "/api/v1/pages", None, listing("pages", 96)),
        ApiOperation("collections", "all", "n/a", "GET", "/api/v1/collections", None, listing("collections", 12)),
        ApiOperation("schedules_all", "all", "n/a", "GET", "/api/v1/schedules?board_id=*", None, listing("schedules", 32)),
    ]
    pages_by_id = {p["id"]: p for p in manifest["pages"]}
    for geometry, board in manifest["boards"].items():
        bid = board["id"]
        ids = board["page_ids"][4:16]  # Exclude primary active01 and the mutable02–04 ring.
        operations.append(ApiOperation("board_detail", geometry, "n/a", "GET", f"/api/v1/boards/{bid}", None,
                                       lambda body, b=board: check(body.get("id") == b["id"] and
                                           (body.get("rows"), body.get("cols")) == (b["rows"], b["cols"]),
                                           "Board detail identity/geometry differs")))
        operations.append(ApiOperation("schedules", geometry, "n/a", "GET", f"/api/v1/schedules?board_id={bid}", None,
                                       listing("schedules", 8)))
        for forced in (False, True):
            operations.append(ApiOperation("preview_batch_forced" if forced else "preview_batch_prefilled", geometry,
                                           "forced-page-render" if forced else "prefilled-preview", "POST", "/api/pages/preview/batch",
                                           {"page_ids": ids, "force_refresh": forced, "board_id": bid},
                                           lambda body, wanted=ids: validate_preview(body, wanted)))
        template = ["PERF", '{{= SUM(1,2) }} {{= UPPER("a") }}', '{{= DEFAULT(countdown.days,"N/A") }} {{= 4*5 }}']
        target = {"board_id": bid, "device_type": board["device_type"], "template": template}
        if geometry == "array":
            target.update(notes_wide=2, notes_tall=2)
        if geometry == "panel":
            target.update(grid_rows=board["rows"], grid_cols=board["cols"])

        def render_check(body, diagnostics=False, b=board):
            lines = body.get("lines")
            check(isinstance(lines, list) and len(lines) == b["rows"], "Rendered row geometry differs")
            check(all(isinstance(line, str) and len(line) <= b["cols"] for line in lines), "Rendered column geometry differs")
            check(not re.search(r"#(?:REF|VALUE|DIV/0|NAME\?|NUM|SYNTAX)", body.get("rendered", "")), "Unexpected formula error")
            if diagnostics:
                formulas = body.get("diagnostics", {}).get("formulas", [])
                check([f.get("value") for f in formulas] == ["3", "A", "N/A", "20"] and
                      all(f.get("error") is None for f in formulas), "Formula diagnostics differ")

        for name, diagnostics in (("render", False), ("render_diagnostics", True)):
            payload = {**target, "diagnostics": diagnostics, "preview": {"data": "cached", "at": "2026-11-17T12:00:00+00:00",
                        "values": {"date_time.hour": 12}, "missing": ["countdown.days"]}}
            operations.append(ApiOperation(name, geometry, "cached-plugin-data", "POST", "/api/templates/render", payload,
                                           lambda body, d=diagnostics, validate=render_check: validate(body, d)))
        operations.append(ApiOperation("validate", geometry, "n/a", "POST", "/api/templates/validate", target,
                                       lambda body, b=board: check(body.get("valid") is True and not body.get("errors")
                                           and (body.get("rows"), body.get("cols")) == (b["rows"], b["cols"]),
                                           "Template validation/geometry failed")))
        variable = next(c for c in manifest["collections"] if c["geometry"] == geometry and c["mode"] == "variable")
        expected_pid = variable["page_ids"][0]
        operations.append(ApiOperation("collection_dry_run", geometry, "cached-plugin-data", "POST",
            f"/api/collections/{variable['id']}/dry-run", {"at": "2026-11-17T12:00:00+00:00", "data": "cached",
                "values": {"date_time.hour": 12}, "window_seconds": 3600, "step_seconds": 300},
            lambda body, pid=expected_pid: check(body.get("page_id") == pid and body.get("truncated") is False and
                body.get("matched_rule") == 0 and all(r.get("error") is None for r in body.get("rules", [])),
                "Variable dry-run selected wrong page or truncated/errored")))
        query = urlencode({"board_id": bid, "at": "2026-11-17T12:00:00+00:00"})
        def schedule_checked(body, key=geometry, b=board):
            selected = manifest.get("soak_active_refs", {}).get(key, b["page_ids"][0])
            members = next((c["page_ids"] for c in manifest["collections"] if c["id"] == selected), [selected])
            check(body.get("schedule_enabled") is False and body.get("source") == "manual"
                  and body.get("page_id") == selected and body.get("resolved_page_id") in members,
                  "Declared manual/collection schedule-at selection differs")
        operations.append(ApiOperation("schedule_at_manual", geometry, "n/a", "GET", f"/api/schedules/active/page?{query}", None,
            schedule_checked))
        page = pages_by_id[board["page_ids"][1]]
        save_state = {"counter": 0, "last_template": None, "page": page}

        def prepare_save(state=save_state, b=board):
            state["counter"] += 1
            template = [f"PERF {state['counter']:08}", "FIXED", "END"] + [""] * (b["rows"] - 3)
            state["last_template"] = template
            return {"expected_revision": state["page"]["revision"], "template": template}

        def saved(body, state=save_state):
            updated = body.get("page", {})
            check(updated.get("id") == state["page"]["id"] and bool(updated.get("revision")) and
                updated.get("revision") != state["page"]["revision"] and updated.get("template") == state["last_template"]
                and body.get("incompatible_references") == [], "Sparse save did not confirm changed content/new revision")
            state["page"].update(revision=updated["revision"], template=updated["template"])

        operations.append(ApiOperation("save", geometry, "invalidates-page-cache", "PUT", f"/api/v1/pages/{page['id']}",
                                       prepare_save, saved))
        send_state = {"counter": 0}

        def prepare_send(state=send_state, b=board):
            state["counter"] += 1
            return {"lines": [f"SEND {state['counter']:08}"] + [""] * (b["rows"] - 1)}

        def sent(body, b=board):
            frame = body.get("characters", [])
            check(body.get("sent") is True and body.get("board_id") == b["id"] and not body.get("reason") and
                len(frame) == b["rows"] and all(len(row) == b["cols"] for row in frame), "Virtual send did not deliver expected geometry")

        operations.append(ApiOperation("send", geometry, "n/a", "POST", f"/api/v1/boards/{bid}/message", prepare_send, sent,
                                       (f"/api/v1/boards/{bid}/active-page", {"page_id": board["page_ids"][0]})))
    return operations


def sample_api(client, manifest, out_dir, batches=3, samples=200, warmups=20, *, operations=None):
    if batches < 1 or samples < 1 or warmups < 0:
        raise ProtocolError("Sampling requires positive batches/samples and nonnegative warmups")
    verify_manifest(client, manifest)
    if operations is None:
        operations = api_operations(manifest)
    if not operations:
        raise ProtocolError("No measurement strata declared")
    out_dir = Path(out_dir)
    writer = JsonlWriter(out_dir / "requests.jsonl", str(uuid.uuid4()), secrets=client.secrets)
    report = {"valid": True, "aborted": False, "strata": []}
    writer.write("metadata", seed_id=manifest["seed_id"], source_commit=manifest["source_commit"],
                 base_url=client.base_url, batches=batches, samples=samples, warmups=warmups,
                 timeout_seconds=client.timeout, auth="browser-cookie", run_context=client.run_context)
    try:
        for batch in range(1, batches + 1):
            session = client.session_info(min_valid_seconds=7800)
            writer.write("auth_metadata", batch=batch, **session)
            verify_manifest(client, manifest)
            for operation in operations:
                records = []
                warmup_ok = True
                for index in range(warmups + samples):
                    phase = "warmup" if index < warmups else "sample"
                    payload = operation.payload() if callable(operation.payload) else operation.payload
                    result = client.request(operation.method, operation.path, payload)
                    success, error = False, result.error
                    try:
                        body = require_ok(result)
                        if operation.validate(body) is False:
                            raise ProtocolError("Semantic validator refused response")
                        success = True
                    except (ProtocolError, KeyError, TypeError, ValueError):
                        error = error or "HTTP or response-semantic assertion failed"
                    record = writer.write(
                        "request", phase=phase, batch=batch, operation=operation.name, geometry=operation.geometry,
                        cache=operation.cache, auth="browser-cookie", elapsed_ms=result.elapsed_ms,
                        http_status=result.status, bytes=result.body_bytes, semantic_success=success,
                        error=error, timed_out=result.timed_out, timeout_seconds=client.timeout,
                        request={"method": operation.method, "path": operation.path, "body": payload},
                        response=client.safe_result(result),
                    )
                    if phase == "sample":
                        records.append(record)
                    elif not success:
                        warmup_ok = False
                    if result.status == 401:
                        report["aborted"] = True
                        break
                summary = summarize_requests(records)
                summary.update(batch=batch, operation=operation.name, geometry=operation.geometry,
                               cache=operation.cache, auth="browser-cookie", planned_samples=samples,
                               warmups_valid=warmup_ok)
                summary["valid"] = summary["valid"] and len(records) == samples and warmup_ok
                report["strata"].append(summary)
                report["valid"] = report["valid"] and summary["valid"]
                if operation.cleanup and not report["aborted"]:
                    path, payload = operation.cleanup
                    cleanup = client.request("PUT", path, payload)
                    writer.write("cleanup", operation=operation.name, response=client.safe_result(cleanup), path=path)
                    answer = require_ok(cleanup)
                    if answer.get("sent") is not True or answer.get("error"):
                        raise ProtocolError("Failed to restore manual frame after send stratum")
                if report["aborted"]:
                    break
            if report["aborted"]:
                break
        writer.write("summary", **report)
        (out_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        return report
    finally:
        writer.close()


if __name__ == "__main__":
    raise SystemExit(main())
