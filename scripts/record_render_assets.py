#!/usr/bin/env python3
"""Record H14 native fixtures through real authenticated TestClient requests.

Run inside the shared Python container after committing the implementation:
python scripts/record_render_assets.py --source-commit <full hub commit SHA>
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Full immutable hub SHA whose source is being recorded.")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("--source-commit must be a full lowercase 40-character Git SHA")
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_render_assets_contract.py",
            "-k",
            "recorded_native_responses",
            "-q",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "RECORD_RENDER_ASSETS": args.source_commit},
    )


if __name__ == "__main__":
    raise SystemExit(main())
