#!/usr/bin/env python3
"""
Renames board screenshots in older external plugin repos from
  docs/black/{plugin-name}-display.png
  docs/white/{plugin-name}-display.png
to the canonical name expected by the docs-site:
  docs/black/board-display.png
  docs/white/board-display.png

Then commits and pushes each repo to main.

Run from anywhere:
  python3 scripts/fix_plugin_screenshot_names.py
"""

import os
import subprocess
import sys

BASE_DIR = os.path.expanduser("~/workspace")

# Repos where docs/black/ and docs/white/ contain {name}-display.png
# Maps repo name → old image stem (the part before -display.png)
PLUGINS_TO_FIX = {
    "air-fog": "air-fog",
    "baywheels": "baywheels",
    "dad-jokes": "dad-jokes",
    "disney-parks-times": "disney-parks-times",
    "generic-data": "generic-data",
    "guest-wifi": "guest-wifi",
    "home-assistant": "home-assistant",
    "last-fm": "last-fm",
    "muni": "muni",
    "nearby-aircraft": "nearby-aircraft",
    "santa-tracker": "santa-tracker",
    "spacecraft-launches": "spacecraft-launches",
    "sports-scores": "sports-scores",
    "star-trek-quotes": "star-trek-quotes",
    "stardate": "stardate",
    "stocks": "stocks",
    "sun-art": "sun-art",
    "surf": "surf",
    "traffic": "traffic",
    "visual-clock": "visual-clock",
    "weather": "weather",
    "white-noise": "white-noise",
    "wsdot": "wsdot",
}


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def fix_repo(name, stem):
    repo_dir = os.path.join(BASE_DIR, f"fiestaboard-plugin--{name}")
    if not os.path.isdir(repo_dir):
        print(f"  ✗ SKIP — directory not found: {repo_dir}")
        return False

    changed = False
    for color_dir in ("black", "white"):
        src = os.path.join(repo_dir, "docs", color_dir, f"{stem}-display.png")
        dst = os.path.join(repo_dir, "docs", color_dir, "board-display.png")

        if os.path.exists(dst):
            print(f"  ✓ {color_dir}/board-display.png already exists — skipping")
            continue

        if not os.path.exists(src):
            print(f"  ✗ WARN — source not found: docs/{color_dir}/{stem}-display.png")
            continue

        r = run(
            ["git", "mv", f"docs/{color_dir}/{stem}-display.png", f"docs/{color_dir}/board-display.png"], cwd=repo_dir
        )
        if r.returncode != 0:
            print(f"  ✗ git mv failed for {color_dir}: {r.stderr.strip()}")
            return False

        print(f"  → renamed docs/{color_dir}/{stem}-display.png → board-display.png")
        changed = True

    if not changed:
        print("  — nothing to do")
        return True

    r = run(
        [
            "git",
            "commit",
            "-m",
            "fix: rename board screenshots to board-display.png\n\n"
            "The docs-site pluginBoardImagePath() now expects\n"
            "docs/black/board-display.png and docs/white/board-display.png.\n"
            "Rename from the legacy {plugin-name}-display.png convention.",
        ],
        cwd=repo_dir,
    )
    if r.returncode != 0:
        print(f"  ✗ git commit failed: {r.stderr.strip()}")
        return False

    r = run(["git", "push", "origin", "main"], cwd=repo_dir)
    if r.returncode != 0:
        print(f"  ✗ git push failed: {r.stderr.strip()}")
        return False

    print("  ✓ pushed")
    return True


def main():
    passed, failed, skipped = [], [], []

    for name, stem in PLUGINS_TO_FIX.items():
        print(f"\n=== {name} ===")
        ok = fix_repo(name, stem)
        if ok is True:
            passed.append(name)
        elif ok is False:
            failed.append(name)
        else:
            skipped.append(name)

    print(f"\n{'=' * 50}")
    print(f"Done. {len(passed)} pushed, {len(failed)} failed, {len(skipped)} skipped.")
    if failed:
        print(f"\nFailed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
