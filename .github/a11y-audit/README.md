# A11y Audit Feedback Loop

Two finders sweep the FiestaBoard web UI for WCAG 2.2 AA / accessibility
issues on a recurring schedule and file labeled issues:

- **`.github/workflows/claude-a11y-audit.yml`** — a weekly static sweep that
  reads `web/src/**/*.tsx` and flags accessibility anti-patterns in the
  source (missing `aria-label`s, non-semantic interactive elements,
  hardcoded labels that should go through `next-intl`, heading-order
  problems, unlabeled form controls, color-only state, focus management).
- **`.github/workflows/claude-a11y-live-axe.yml`** — a weekly live run that
  boots the container and runs `axe-core` (via the existing
  `web/tests/a11y.spec.ts`) against the main routes, then triages the
  violations into the same issues.

Every finding becomes an issue labeled `a11y` + `a11y-audit` + `claude-fix`.
The shared **`claude-issue-triage.yml`** worker picks those up by label and
opens a focused `a11y/issue-*` fix PR. Those PRs are auto-reviewed by
**`claude-a11y-audit-review.yml`**. Sometimes a fix is wrong — when that
happens, the maintainer closes the PR without merging.

**Closing an `a11y/issue-*` PR without merging is the teaching action.**
This folder is the bot's memory of those teaching moments.

## How it works

1. **`claude-a11y-audit-feedback.yml`** triggers on `pull_request.closed`. If
   the PR is unmerged and the head branch starts with `a11y/issue-` (triage
   fix PRs) or `a11y-audit/` (reserved for any future inline-fix PRs), it
   runs `build_rejection.py` to bundle the PR's diff + every comment,
   review, and inline comment into a single JSON object, appends that object
   as one line to `rejected-edits.jsonl`, and commits the change to `main`.
2. **The audit prompt** reads `rejected-edits.jsonl` at the start of every
   run. The bot is instructed to (a) never re-file the same finding it
   already proposed and got rejected, and (b) generalize from the human's
   close comment (e.g. "this element is intentionally decorative" → stop
   flagging that class of element everywhere).
3. **Re-running capture** is idempotent. If the maintainer adds an
   explanatory comment after closing, dispatch
   `claude-a11y-audit-feedback.yml` with the PR number and the existing line
   is replaced.

## Why two finders, one label

The static sweep reads source and catches issues that only exist in the code
(an icon `<button>` with no label, a `<div onClick>` that should be a
`<button>`, an English `aria-label` literal). The live axe run catches issues
that only appear at runtime (computed contrast, ARIA wiring after hydration,
focus order on a real DOM). They overlap deliberately and both file under
`a11y-audit`, so the dedup, triage, review, and rejection-learning machinery
is shared — one queue, one memory.

## File: `rejected-edits.jsonl`

One JSON object per line. Schema:

| Field | Type | Notes |
| --- | --- | --- |
| `pr` | int | PR number. Acts as the primary key — re-capture replaces the prior line. |
| `title` | string | Original PR title. |
| `head_ref` | string | `a11y/issue-<N>-<slug>` (triage fix PR) or `a11y-audit/round-<n>-run-<id>` (reserved). |
| `closed_at` | string | ISO 8601. |
| `author` | string | `github-actions[bot]` / `claude` for the bot, or whoever pushed. |
| `body` | string | PR description as opened by the bot. |
| `files` | array | `[{path, patch}]` — raw unified diff per file. |
| `comments` | array | Issue-style PR comments: `{author, body, created_at}`. |
| `reviews` | array | Review-level comments. |
| `inline_comments` | array | Per-line review comments. |

## File: `build_rejection.py`

Script the feedback workflow runs. Can be invoked locally with `DRY_RUN=1`
to print the record to stdout without modifying the log:

```bash
DRY_RUN=1 python3 .github/a11y-audit/build_rejection.py 1234
```

## Manually clearing a stale rejection

If a rejected fix is later determined to have been correct (the close was
wrong, or the UI changed and the fix now makes sense), hand-delete that line
from `rejected-edits.jsonl` and commit. The file is plain JSONL; any text
editor can do this.
