# Bug-Hunt Feedback Loop

The bug-hunt cron (`.github/workflows/claude-bug-hunt.yml`) sweeps the codebase
daily, hunting for real functional bugs with a multi-lens subagent fan-out and
adversarial verification, then files high-trust issues (`bug`, `bug-hunt`,
`claude-fix`). The shared triage worker turns each into a **draft** fix PR. A
human reviews and merges. No bug fix lands without sign-off.

This folder is the loop's **two memories** — one positive, one negative.

## Positive memory: `pattern-memory.md`

What the loop has *learned about where bugs live*. Maintained weekly by
`.github/workflows/claude-bug-hunt-learn.yml`, which:

1. Runs `gather_fixed_bugs.py` to deterministically collect merged PRs labelled
   `bug` since the last run (with their linked issues and diffs).
2. Feeds that to Claude, which distills generalized root-cause patterns,
   re-ranks the bug-prone modules, and extends the per-lens checklists.
3. Rewrites `pattern-memory.md` and advances `last_learned_at`.

The hunter reads it each run to bias area selection and to seed each lens with
the checklist of "things that have actually bitten us." **This raises recall.**

## Negative memory: `rejected-edits.jsonl`

What the loop has *learned not to file*. When a `bug-hunt/issue-*` fix PR is
closed **without merging**, that's the maintainer saying "this bug report was
wrong." `.github/workflows/claude-bug-hunt-feedback.yml` triggers on
`pull_request_target: closed`, runs `build_rejection.py` to bundle the PR's diff
+ every comment/review into one JSONL line, and commits it here.

The hunter reads it each run to (a) never re-propose the same wrong finding and
(b) generalize the false-positive class. **This raises precision.**

> Closing a bug-hunt fix PR without merging is the teaching action. Add a comment
> explaining *why* it was wrong — the hunter treats the closer's reasoning as
> authoritative.

### `rejected-edits.jsonl` schema

One JSON object per line. Primary key is `pr` (re-capture replaces the prior
line). Fields: `pr`, `title`, `head_ref`, `closed_at`, `author`, `body`,
`files: [{path, patch}]`, `comments`, `reviews`, `inline_comments`. See
`build_rejection.py` for details; run it locally with `DRY_RUN=1` to preview:

```bash
DRY_RUN=1 python3 .github/bug-hunt/build_rejection.py <pr_number>
```

## Manually clearing a stale entry

Both files are plain text. If a rejection was actually correct, or a learned
pattern is stale, hand-delete the relevant line/section and commit. The next run
picks up the change.

## Scripts

- `gather_fixed_bugs.py` — deterministic collector of merged bug-fix PRs for the
  learner. `--since <ISO8601>` bounds the window. Prints JSON to stdout.
- `build_rejection.py` — idempotent rejection-log builder for the feedback
  workflow. Refuses to record merged PRs.
- `tests/` — pytest for the collector's issue-link parsing.

## Sweep state

Sweep progress lives in `.github/bug-hunt-state.json` (not this folder, by
convention — it's the hunter's progress, not feedback memory): `round`,
`areas_remaining`, `areas_audited`, `last_run_at`, `last_learned_at`.
