# Docs-Audit Feedback Loop

The docs-audit cron (`.github/workflows/claude-docs-audit.yml`) sweeps every
markdown file in the repo twice a day and opens draft PRs for trivial fixes.
Sometimes those fixes are wrong — e.g. it tried to rename `Vestaboard`
(the physical device this software drives) to `FiestaBoard` (the software).
When that happens, the maintainer closes the PR.

**Closing a docs-audit PR without merging is the teaching action.** This
folder is the bot's memory of those teaching moments.

## How it works

1. **`docs-audit-feedback.yml`** triggers on `pull_request.closed`. If the
   PR is unmerged and the head branch starts with `docs-audit/`, it runs
   `build_rejection.py` to bundle the PR's diff + every comment, review,
   and inline comment into a single JSON object, then appends that object
   as one line to `rejected-edits.jsonl` and commits the change to `main`.
2. **The audit prompt** reads `rejected-edits.jsonl` at the start of every
   run. The bot is instructed to (a) never re-propose the same `removed →
   added` swap anywhere in the repo, and (b) generalize from the human's
   close comment — a Vestaboard rejection becomes a global "never rename
   Vestaboard" rule, not just a per-file blocklist.
3. **Re-running capture** is idempotent. If the maintainer adds an
   explanatory comment after closing, dispatch `docs-audit-feedback.yml`
   with the PR number and the existing line is replaced.

## File: `rejected-edits.jsonl`

One JSON object per line. Schema:

| Field | Type | Notes |
| --- | --- | --- |
| `pr` | int | PR number. Acts as the primary key — re-capture replaces the prior line. |
| `title` | string | Original PR title. |
| `head_ref` | string | `docs-audit/round-<n>-run-<id>`. |
| `closed_at` | string | ISO 8601. |
| `author` | string | `github-actions[bot]` for the cron, or whoever pushed. |
| `body` | string | PR description as opened by the bot. |
| `files` | array | `[{path, patch}]` — raw unified diff per file. |
| `comments` | array | Issue-style PR comments: `{author, body, created_at}`. |
| `reviews` | array | Review-level (cover-letter) comments. |
| `inline_comments` | array | Per-line review comments: `{author, body, path, created_at, diff_hunk}`. |

## File: `build_rejection.py`

Script the workflow runs. Can be invoked locally with `DRY_RUN=1` to print
the record to stdout without modifying the log:

```bash
DRY_RUN=1 python3 .github/docs-audit/build_rejection.py 992
```

## Manually clearing a stale rejection

If a rejected edit is later determined to have been correct (the close
was wrong, or the codebase has changed and the swap now makes sense),
hand-delete that line from `rejected-edits.jsonl` and commit. The file is
plain JSONL; any text editor can do this.
