#!/usr/bin/env python3
"""Collect fixed-bug records for the bug-hunt learner.

Run as: gather_fixed_bugs.py [--since <ISO8601>]

Deterministically gathers, via `gh`, every CLOSED issue labelled `bug` or
`bug-hunt` (optionally only those closed at/after `--since`), follows each
issue's `closedByPullRequestsReferences` to the merged fix PR, and emits a
record pairing the bug (issue title + body + labels) with the fix (PR title +
per-file unified diff). Prints a JSON array to stdout.

In this repo the `bug` label lives on issues, not PRs (PRs get
`python`/`backend`/etc. from the auto-labeler), so the issue is the right
anchor — and it carries the human description of the bug, which the PR diff
alone does not.

The point is to keep all data-gathering out of the model: the weekly learner
(`.github/workflows/claude-bug-hunt-learn.yml`) runs this, then hands the JSON
to Claude, which only does the distillation into `pattern-memory.md`.

Pure helpers (`parse_linked_issues`, `parse_diff`) are unit-tested in
`tests/test_gather_fixed_bugs.py`; the `gh`-backed paths are validated via the
learner workflow.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# `Closes #12`, `fixed #3`, `Resolve #4`, plus a trailing `(#1280)`.
_LINK_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(#(\d+)\)")


def parse_linked_issues(body: str | None) -> list[int]:
    """Return the deduped, sorted issue numbers referenced by a PR body."""
    if not body:
        return []
    nums = {int(n) for n in _LINK_RE.findall(body)}
    nums |= {int(n) for n in _PAREN_RE.findall(body)}
    return sorted(nums)


def parse_diff(diff: str) -> list[dict]:
    """Split a unified diff into per-file `{path, patch}` records."""
    files: list[dict] = []
    current: dict | None = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                current["patch"] = "\n".join(current["patch"])
                files.append(current)
            path = line.split(" b/", 1)[-1] if " b/" in line else line
            current = {"path": path, "patch": [line]}
        elif current is not None:
            current["patch"].append(line)
    if current is not None:
        current["patch"] = "\n".join(current["patch"])
        files.append(current)
    return files


def gh_json(*args: str):
    return json.loads(subprocess.check_output(["gh", *args], text=True))


def gh_text(*args: str) -> str:
    return subprocess.check_output(["gh", *args], text=True)


FIX_LABELS = ("bug", "bug-hunt")


def _repo_name_with_owner() -> str:
    return subprocess.check_output(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        text=True,
    ).strip()


def _closed_issue_numbers(since: str | None) -> list[int]:
    """Deduped closed-issue numbers carrying any FIX_LABELS, newest first."""
    seen: dict[int, None] = {}
    for label in FIX_LABELS:
        search = f"is:issue is:closed label:{label}"
        if since:
            search += f" closed:>={since[:10]}"
        try:
            rows = gh_json(
                "issue", "list",
                "--search", search,
                "--limit", "200",
                "--json", "number",
            )
        except subprocess.CalledProcessError:
            rows = []
        for r in rows:
            seen.setdefault(r["number"], None)
    return list(seen)


def collect(since: str | None) -> list[dict]:
    repo = _repo_name_with_owner()
    records: list[dict] = []
    for num in _closed_issue_numbers(since):
        issue = gh_json(
            "issue", "view", str(num),
            "--json",
            "number,title,body,closedAt,labels,closedByPullRequestsReferences",
        )
        # Pick the closing PR in THIS repo (ignore cross-repo references).
        prs = [
            ref for ref in (issue.get("closedByPullRequestsReferences") or [])
            if f"{ref['repository']['owner']['login']}/{ref['repository']['name']}" == repo
        ]
        if not prs:
            continue
        pr_num = prs[0]["number"]
        try:
            diff = gh_text("pr", "diff", str(pr_num), "--patch")
            pr_title = gh_json("pr", "view", str(pr_num), "--json", "title")["title"]
        except subprocess.CalledProcessError:
            diff, pr_title = "", None
        records.append(
            {
                "issue": issue["number"],
                "issue_title": issue.get("title"),
                "issue_body": issue.get("body") or "",
                "labels": [l["name"] for l in issue.get("labels", [])],
                "closed_at": issue.get("closedAt"),
                "pr": pr_num,
                "pr_title": pr_title,
                "files": parse_diff(diff),
            }
        )
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect merged bug-fix PRs as JSON.")
    ap.add_argument("--since", default=None, help="ISO8601; only PRs merged at/after this")
    args = ap.parse_args()
    since = args.since or None
    if since in ("", "null", "None"):
        since = None
    json.dump(collect(since), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
