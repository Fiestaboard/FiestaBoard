#!/usr/bin/env python3
"""Capture why a docs-audit PR was closed without merging.

Run as: build_rejection.py <pr_number>

Reads the PR's metadata, full diff, every comment / review / inline comment
via `gh`, then writes one JSONL line into
`.github/docs-audit/rejected-edits.jsonl`. The next docs-audit cron run
loads that file and uses it to avoid repeating the same wrong edit and to
generalize from the closer's explanation.

Idempotent: a re-run for the same PR replaces that PR's existing line
rather than appending a duplicate. This lets the GitHub Action be
triggered manually (workflow_dispatch) after a user has added a later
explanatory comment without polluting the log.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

LOG_PATH = Path(".github/docs-audit/rejected-edits.jsonl")


def gh_json(*args: str):
    out = subprocess.check_output(["gh", *args], text=True)
    return json.loads(out)


def gh_text(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


def parse_diff(diff: str) -> list[dict]:
    """Split a unified diff into per-file `{path, patch}` records."""
    files: list[dict] = []
    current: dict | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                current["patch"] = "\n".join(current["patch"])
                files.append(current)
            # `diff --git a/path b/path` — take everything after ` b/`.
            path = line.split(" b/", 1)[-1] if " b/" in line else line
            current = {"path": path, "patch": [line]}
        elif current is not None:
            current["patch"].append(line)
    if current is not None:
        current["patch"] = "\n".join(current["patch"])
        files.append(current)
    return files


def build_record(pr: str) -> dict:
    meta = gh_json(
        "pr", "view", pr,
        "--json", "number,title,headRefName,closedAt,author,body,state",
    )
    if meta.get("state") == "MERGED":
        raise SystemExit(f"PR #{pr} was merged — refusing to record as rejection.")

    diff = gh_text("pr", "diff", pr)
    files = parse_diff(diff)

    repo = subprocess.check_output(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        text=True,
    ).strip()

    issue_comments = gh_json(
        "api", f"repos/{repo}/issues/{pr}/comments",
        "--jq", "[.[] | {author: .user.login, body: .body, created_at: .created_at}]",
    )
    reviews = gh_json(
        "api", f"repos/{repo}/pulls/{pr}/reviews",
        "--jq",
        '[.[] | select((.body // "") != "") | '
        '{author: .user.login, body: .body, state: .state, submitted_at: .submitted_at}]',
    )
    inline = gh_json(
        "api", f"repos/{repo}/pulls/{pr}/comments",
        "--jq",
        "[.[] | {author: .user.login, body: .body, path: .path, "
        "created_at: .created_at, diff_hunk: .diff_hunk}]",
    )

    return {
        "pr": meta["number"],
        "title": meta["title"],
        "head_ref": meta["headRefName"],
        "closed_at": meta["closedAt"],
        "author": (meta.get("author") or {}).get("login"),
        "body": meta.get("body") or "",
        "comments": issue_comments,
        "reviews": reviews,
        "inline_comments": inline,
        "files": files,
    }


def write_log(record: dict, path: Path = LOG_PATH) -> None:
    """Replace any prior line for this PR; append the new one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.exists():
        existing = [ln for ln in path.read_text().splitlines() if ln.strip()]

    def keep(line: str) -> bool:
        try:
            return json.loads(line).get("pr") != record["pr"]
        except json.JSONDecodeError:
            # Preserve hand-edited / malformed lines rather than silently dropping.
            return True

    kept = [ln for ln in existing if keep(ln)]
    kept.append(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    path.write_text("\n".join(kept) + "\n")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: build_rejection.py <pr_number>")
    pr = sys.argv[1]
    record = build_record(pr)
    if os.environ.get("DRY_RUN") == "1":
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return
    write_log(record)
    print(f"Captured PR #{record['pr']} into {LOG_PATH}")


if __name__ == "__main__":
    main()
