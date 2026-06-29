# CI Auto-Fix & Drift Repair

Two Claude-powered workflows that keep **automation-authored PRs**
(`bug-hunt/*`, `docs/*`, `a11y/*`, `claude/*`) from sitting in a red or stale
state. Both use the Sonnet model and push under the repo-installed GitHub App
token so CI re-runs without the "Approve workflows" gate.

| Workflow | Trigger | What it does |
| --- | --- | --- |
| [`claude-ci-autofix.yml`](../workflows/claude-ci-autofix.yml) | `workflow_run` — CI completed with `failure` on a PR | Reads the failing logs, attempts a fix, pushes it back to the PR branch. |
| [`claude-pr-rebase.yml`](../workflows/claude-pr-rebase.yml) | `schedule` (every 3h) + `workflow_dispatch` | Finds bot PRs behind `main` or conflicting, merges `main` in (Claude only for conflicts). |

## How the auto-fixer stays out of an infinite loop

A fix push re-runs CI, which can re-trigger the fixer. Three guards bound it:

1. **Staleness** — if a newer commit superseded the failing SHA, the run
   bails (a newer CI run will fire for that commit).
2. **Attempt cap (3)** — "attempts so far" is the count of consecutive
   `[ci-autofix]` commits at the branch tip. Each fix push adds exactly one
   such commit, so the counter needs no external state and **resets
   automatically** when a non-`[ci-autofix]` commit lands (a human push or a
   drift-repair merge). After 3 attempts the run stops, labels the PR
   `autofix-exhausted`, flips the sticky comment to "gave up", and
   @-mentions the maintainer.
3. **No-push = no loop** — if Claude can't fix it and pushes nothing, CI
   never re-runs, so the workflow can't re-fire on that SHA.

> The `[ci-autofix]` tag in the commit subject is load-bearing. The prompt
> requires it; without it the attempt counter breaks.

## The sticky comment

Each PR gets one status comment (marker `<!-- claude-ci-autofix:state -->`).
The bootstrap step posts it immediately ("🔧 on it, attempt N/3") with an
unchecked checklist; Claude edits the *same* comment in place, ticking items
and adding an honest summary of what it changed and verified.

## How drift repair stays cheap

The cron sweep tries a plain `git merge origin/main` first. Clean merges
push directly with **no Claude run**. Only genuine conflicts spin up Claude,
which resolves *trivial* conflicts and otherwise aborts + labels the PR
`needs-human-rebase` (skipped on future sweeps) so it never thrashes.

## Labels

| Label | Meaning |
| --- | --- |
| `autofix-exhausted` | The auto-fixer tried 3 times and gave up; needs a human. Push a new commit to reset its budget. |
| `needs-human-rebase` | Drift repair found non-trivial conflicts; sweeps skip it until a human resolves them. |

## Operating notes

- **Manual dispatch (drift repair):** `gh workflow run claude-pr-rebase.yml`
- **The auto-fixer can't be dispatched** — `workflow_run` only fires from the
  workflow file on `main`, so it goes live only after this lands. Validate it
  with a deliberately-broken automation PR after merge.
- **Disable quickly:** `gh workflow disable "Claude: CI Auto-Fix"` /
  `gh workflow disable "Claude: PR Drift Repair"`.
- **First runs to watch:** check the Actions log for `--allowed-tools` denial
  messages (they appear because `show_full_output: 'true'`), runaway attempt
  counts, and false-confidence fixes that don't actually turn CI green.
- **Scope:** both workflows act only on same-repo automation branches, never
  on forks or human PRs.
