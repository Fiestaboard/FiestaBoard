#!/usr/bin/env python3
"""Offline bundle inventory and raw-byte gate. Supported for local execution.

Uses only the Python standard library; never starts an application or Docker.
gzip6 is a per-file estimate, not observed HTTP transfer. Source maps are
storage only: nginx refuses to serve them. All chunks count, including lazy
routes and the service worker; this is not an initial-route payload measure.
"""

import argparse
import gzip
import hashlib
import json
import platform
import sys
import zlib
from pathlib import Path

METRICS = {"javascript_bytes", "css_bytes", "font_bytes", "largest_javascript_bytes"}
GROUPS = ("javascript", "css", "font", "source_map", "other")


def measure(client: Path) -> dict:
    """Inventory one completed static client build; refuse incomplete inputs."""
    if client.is_symlink():
        raise ValueError("Client directory must not be a symlink")
    if not client.is_dir():
        raise ValueError("Client directory does not exist")
    groups = {key: {"count": 0, "raw_bytes": 0, "gzip6_bytes": 0} for key in GROUPS}
    files = []
    for path in sorted(client.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink: {path.relative_to(client)}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Refusing nonregular file: {path.relative_to(client)}")
        suffix = path.suffix.lower()
        if suffix in (".js", ".mjs"):
            group = "javascript"
        elif suffix == ".css":
            group = "css"
        elif suffix in (".woff", ".woff2", ".ttf", ".otf"):
            group = "font"
        elif suffix == ".map":
            group = "source_map"
        else:
            group = "other"
        data = path.read_bytes()
        raw_bytes = len(data)
        gzip_bytes = len(gzip.compress(data, compresslevel=6, mtime=0))
        files.append(
            {
                "path": path.relative_to(client).as_posix(),
                "group": group,
                "raw_bytes": raw_bytes,
                "gzip6_bytes": gzip_bytes,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        groups[group]["count"] += 1
        groups[group]["raw_bytes"] += raw_bytes
        groups[group]["gzip6_bytes"] += gzip_bytes
    if not any(item["path"] == "index.html" and item["raw_bytes"] for item in files):
        raise ValueError("Build must contain a nonempty index.html")
    if not groups["javascript"]["raw_bytes"]:
        raise ValueError("Build must contain nonempty JavaScript")
    if not groups["css"]["raw_bytes"]:
        raise ValueError("Build must contain nonempty CSS")
    return {
        "schema_version": 1,
        "scope": "all static client files; not initial route or observed network transfer",
        "environment": {"python": platform.python_version(), "zlib": zlib.ZLIB_RUNTIME_VERSION},
        "metrics": {
            "javascript_bytes": groups["javascript"]["raw_bytes"],
            "css_bytes": groups["css"]["raw_bytes"],
            "font_bytes": groups["font"]["raw_bytes"],
            "largest_javascript_bytes": max(item["raw_bytes"] for item in files if item["group"] == "javascript"),
        },
        "total_disk_bytes": sum(item["raw_bytes"] for item in files),
        "groups": groups,
        "files": files,
    }


def check_budget(report: dict, budget: dict) -> list:
    """Return all exceeded ceilings; malformed budget contracts fail closed."""
    if not isinstance(budget, dict) or type(budget.get("schema_version")) is not int:
        raise ValueError("Budget must have integer schema_version 1")
    if budget["schema_version"] != 1:
        raise ValueError("Unsupported budget schema_version")
    limits = budget.get("limits")
    if not isinstance(limits, dict) or set(limits) != METRICS:
        raise ValueError("Budget limits must define exactly: " + ", ".join(sorted(METRICS)))
    violations = []
    for key in sorted(METRICS):
        limit = limits[key]
        if type(limit) is not int or limit < 0:
            raise ValueError(f"Budget {key} must be a nonnegative integer")
        actual = report["metrics"][key]
        if actual > limit:
            violations.append(f"{key}: {actual} bytes exceeds {limit} bytes")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = measure(args.client)
        budget = json.loads(args.budget.read_text())
        violations = check_budget(report, budget)
        report.update(
            {"limits": budget["limits"], "violations": violations, "budget_status": "fail" if violations else "pass"}
        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    except (ValueError, OSError) as exc:
        print(f"Bundle measurement error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"metrics": report["metrics"], "budget_status": report["budget_status"]}))
    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
