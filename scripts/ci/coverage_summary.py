#!/usr/bin/env python3
"""Emit a Markdown coverage summary table for GitHub Actions step summaries.

Parses either lcov.info (web) or Cobertura XML (Python) and writes a
Markdown table to stdout. Designed to be piped into $GITHUB_STEP_SUMMARY.

This replaces inline `python3 - <<'PY'` heredocs in workflow YAML, which
are brittle (indentation, $ expansion, set -e propagation) and have
broken CI runs in the past.

Usage:
    python3 scripts/ci/coverage_summary.py --lcov web/coverage/lcov.info --title "UI Tests"
    python3 scripts/ci/coverage_summary.py --cobertura coverage-plugins.xml --title "Plugin Tests"

Exits 0 on success, 1 if the input file is missing or cannot be parsed.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_lcov(path: Path) -> tuple[float, float]:
    lf = lh = brf = brh = 0
    for line in path.read_text().splitlines():
        if line.startswith("LF:"):
            lf += int(line[3:])
        elif line.startswith("LH:"):
            lh += int(line[3:])
        elif line.startswith("BRF:"):
            brf += int(line[4:])
        elif line.startswith("BRH:"):
            brh += int(line[4:])
    line_pct = (lh / lf * 100) if lf else 0.0
    branch_pct = (brh / brf * 100) if brf else 0.0
    return line_pct, branch_pct


def parse_cobertura(path: Path) -> tuple[float, float]:
    root = ET.parse(path).getroot()
    line_pct = float(root.attrib.get("line-rate", "0")) * 100
    branch_pct = float(root.attrib.get("branch-rate", "0")) * 100
    return line_pct, branch_pct


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lcov", type=Path, help="Path to an lcov.info file")
    group.add_argument("--cobertura", type=Path, help="Path to a Cobertura XML file")
    parser.add_argument("--title", required=True, help="Section title for the summary")
    args = parser.parse_args()

    path: Path = args.lcov or args.cobertura
    if not path.is_file():
        print(f"coverage_summary: {path} not found", file=sys.stderr)
        return 1

    try:
        if args.lcov:
            line_pct, branch_pct = parse_lcov(path)
        else:
            line_pct, branch_pct = parse_cobertura(path)
    except Exception as exc:
        print(f"coverage_summary: failed to parse {path}: {exc}", file=sys.stderr)
        return 1

    print(f"## {args.title}")
    print()
    print("| Metric | Value |")
    print("|---|---|")
    print(f"| Line coverage | {line_pct:.1f}% |")
    print(f"| Branch coverage | {branch_pct:.1f}% |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
