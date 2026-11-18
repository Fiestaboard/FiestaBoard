#!/usr/bin/env python3
"""Re-baseline the bundle budget on a newer published alpha. Supported for local execution.

Reads a client tree and its provenance written by fetch_published_client.py,
measures it with bundle_budget.measure, writes the new committed sample, and
rewrites bundle-budget.json so every ceiling is 110% of the published value,
rounded up to 1024 bytes. That is the same allowance the first (alpha.3)
baseline used; this script never adds headroom beyond it.

    python3 scripts/perf/rebaseline_bundle.py \
        --fetched /path/to/scratch/alpha10 --version 11.0.0-alpha.10
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_budget import METRICS, measure  # noqa: E402

PERF = Path(__file__).resolve().parent
GROWTH = 1.10
ROUND = 1024
RATIONALE = (
    "Each raw-byte ceiling is 110% of the observed published artifact value, rounded up to 1024 bytes. "
    "This is a reviewable code-growth allowance, not a latency/SLO or statistically calibrated runtime "
    "budget. Gzip estimates do not gate."
)


def ceiling(observed: int) -> int:
    """110% of ``observed`` rounded up to a whole KiB, in exact integer arithmetic."""
    if type(observed) is not int or observed < 0:
        raise ValueError("Observed bytes must be a nonnegative integer")
    return -(-observed * 110 // (100 * ROUND)) * ROUND


def sample_name(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.\d+\.\d+-alpha\.(\d+)", version)
    if not match:
        raise ValueError("Version must look like 11.0.0-alpha.N")
    return f"published-v{match.group(1)}-alpha{match.group(2)}.json"


def rebaseline(fetched: Path, version: str, perf: Path = PERF) -> dict:
    provenance = json.loads((fetched / "provenance.json").read_text())
    if provenance.get("version_env") != version:
        raise ValueError(f"Image VERSION is {provenance.get('version_env')!r}, not {version!r}")
    report = measure(fetched / "client")
    report["provenance"] = provenance
    name = sample_name(version)
    (perf / name).write_text(json.dumps(report, indent=2) + "\n")
    budget = {
        "schema_version": 1,
        "baseline": name,
        "rationale": RATIONALE,
        "limits": {key: ceiling(report["metrics"][key]) for key in sorted(METRICS)},
    }
    (perf / "bundle-budget.json").write_text(json.dumps(budget, indent=2) + "\n")
    return budget


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fetched", type=Path, required=True, help="Output directory of fetch_published_client.py")
    parser.add_argument("--version", required=True, help="The published version, e.g. 11.0.0-alpha.10")
    args = parser.parse_args()
    try:
        budget = rebaseline(args.fetched, args.version)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Re-baseline error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(budget["limits"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
