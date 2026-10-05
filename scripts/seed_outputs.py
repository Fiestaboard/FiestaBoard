#!/usr/bin/env python3
"""Build or inspect the output seed (plan D8). Used by the Dockerfile and tests.

    # Image build: fetch every pinned first-party output into the seed.
    python scripts/seed_outputs.py build --lock outputs.lock.json --dest /opt/fiestaboard/seed/outputs

    # Bumping a pin: print the tree digest of a checkout for the lock's
    # tree_sha256 (run it on a clean checkout of the new commit).
    python scripts/seed_outputs.py digest path/to/checkout

    # Validate the lockfile's shape without fetching anything.
    python scripts/seed_outputs.py check --lock outputs.lock.json

``build`` needs the network and runs at image build time only — FiestaBoard
never fetches the seed at runtime. It exits non-zero if any pinned commit
cannot be fetched or its tree does not match the lock, so a bad pin fails
the image build instead of shipping. The logic lives in
:mod:`src.outputs.seed`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.outputs.seed import LockError, build_seed, load_lock, tree_digest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fetch the pinned trees into a seed directory")
    build.add_argument("--lock", type=Path, default=ROOT / "outputs.lock.json")
    build.add_argument("--dest", type=Path, required=True)
    check = sub.add_parser("check", help="validate the lockfile")
    check.add_argument("--lock", type=Path, default=ROOT / "outputs.lock.json")
    digest = sub.add_parser("digest", help="print a tree's digest")
    digest.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            entries = build_seed(args.lock, args.dest)
            for entry in entries.values():
                kind = "plugin" if entry.loadable else "data only"
                print(f"seeded {entry.plugin_id} @ {entry.commit} ({kind})")
        elif args.command == "check":
            entries = load_lock(args.lock)
            print(f"{args.lock}: {len(entries)} pinned output(s) OK")
        else:
            print(tree_digest(args.path))
    except LockError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
