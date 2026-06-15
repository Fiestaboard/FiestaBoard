# Architecture

How the four workflow files interlock and why each one exists. Read this once before scaffolding your first loop; you won't need to re-read it for routine tuning.

## The loop, in one picture

```
                ┌──────────────────────────────────────────┐
                │            scheduled cron                │
                │  (twice daily, gated to local PT window) │
                └──────────────────┬───────────────────────┘
                                   │
                  reads state.json │ reads rejected-edits.jsonl
                                   ▼
                  ┌────────────────────────────────┐
                  │     claude-<name>.yml          │
                  │  (the AUDITOR — Claude run)    │
                  └─────┬────────────────┬─────────┘
                        │                │
       trivial fixes    │                │  everything else
                        ▼                ▼
                ┌──────────────┐    ┌─────────────────┐
                │  inline PR   │    │ files an ISSUE  │
                │ ready-for-rev│    │ label: <name>   │
                └──────┬───────┘    └────────┬────────┘
                       │                     │
                       │                     ▼
                       │       ┌────────────────────────────────┐
                       │       │  claude-issue-triage.yml       │
                       │       │  (PER-ISSUE WORKER — Claude)   │
                       │       └──────────────┬─────────────────┘
                       │                      │
                       │                      ▼
                       │              ┌──────────────┐
                       │              │ per-issue PR │
                       │              └──────┬───────┘
                       │                     │
                       └───────┬─────────────┘
                               ▼
              ┌───────────────────────────────────────┐
              │  claude-<name>-review.yml             │
              │  (REVIEWER — Claude posts one review) │
              └───────────────────┬───────────────────┘
                                  │
              if PR is closed     │       if PR is merged → done
              without merging     ▼
              ┌────────────────────────────────────┐
              │  claude-<name>-feedback.yml        │
              │  (captures rejection → JSONL log)  │
              └────────────────────┬───────────────┘
                                   │
                                   ▼
                       rejected-edits.jsonl
                                   │
                                   │ (next cron run reads it)
                                   ▼
                         (back to top — auditor learns)
```

## Why four workflows?

Each one has a different trigger, different permissions, and a different blast radius. Splitting them apart is the safest separation of concerns.

### `claude-<name>.yml` — the auditor

- **Trigger:** scheduled cron (twice-daily) + manual dispatch.
- **What it does:** sweeps the domain in batches, files issues for non-trivial findings, opens one ready-for-review inline PR per run for trivial fixes, advances the sweep state.
- **Permissions:** `contents: write` (to push the state-file commit + open PR), `pull-requests: write`, `issues: write`, `id-token: write`.
- **State:** `.github/<name>-state.json` (sweep progress) + `.github/<name>/rejected-edits.jsonl` (learning input).
- **Failure modes:** allowlist denials silent without `show_full_output`; duplicate PRs from parallel runs without serialized concurrency; DST drift without paired UTC crons.

### `claude-issue-triage.yml` — the per-issue worker

- **Trigger:** `issues: [opened, labeled]`.
- **What it does:** when an issue is opened by a trusted author OR the `claude-fix` label is applied OR an audit-loop label is applied (e.g., `docs-audit`), takes a first-pass fix attempt and opens a focused PR.
- **Permissions:** `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`, `actions: read`.
- **Why shared (not per-loop):** triage is the same job regardless of which audit filed the issue. The only per-loop branch is the label check in the `if:` condition. Multiple audits feed one triage worker.
- **Failure modes:** bot-filed issues blocked unless `allowed_bots: 'claude'`; `@claude` mention double-fires with `claude.yml` unless excluded; wrong model tier (Opus on a markdown edit) wastes budget.

### `claude-<name>-review.yml` — the auto-reviewer

- **Trigger:** `pull_request_target` on paths matching the domain, types `[opened, synchronize, reopened, ready_for_review]`.
- **What it does:** reads the PR diff and posts one Claude review comment. Read-only — never edits, never merges.
- **Permissions:** `contents: read`, `pull-requests: write`, `id-token: write`, `actions: read`.
- **Safety:** checks out the **base ref**, never the PR head. Reads PR head content via `gh api .../contents` (data, not code). `--allowed-tools` is read-only.
- **Failure modes:** OIDC App exchange returns `401` on `pull_request_target` unless `github_token` provided; pwn-request if you check out the head ref.

### `claude-<name>-feedback.yml` — the rejection capture

- **Trigger:** `pull_request_target: [closed]` + manual dispatch (for backfill).
- **What it does:** when a docs-pipeline PR is closed without merging, runs `build_rejection.py` to bundle the diff + every comment into one JSONL line and commits to `main`. The auditor reads this log next run.
- **Permissions:** `contents: write` (for the log commit), `pull-requests: read`, `issues: read`.
- **Why `pull_request_target` (not `pull_request`):** branches were cut from `main` before the workflow existed; `pull_request` resolves the workflow from the PR's head ref and never fires. `pull_request_target` resolves from `main`.
- **Failure modes:** silently appends duplicates (without idempotent `build_rejection.py`); races the log file (without serialized concurrency).

## What lives in `.github/<name>/`

The folder is the loop's persistent memory.

| File | Lifetime | Owner |
| --- | --- | --- |
| `<name>-state.json` (in `.github/`, not `.github/<name>/`) | mutated by the auditor every run | the audit cron |
| `<name>/rejected-edits.jsonl` | append-only learning log | the feedback workflow |
| `<name>/build_rejection.py` | static; tweaked when the schema evolves | maintainer |
| `<name>/README.md` | human-readable docs for the folder | maintainer |

The state file goes in `.github/` (not the loop's subfolder) because it's the audit's progress, not feedback memory. The rejection log and its companion script go in `.github/<name>/` so future loops follow the same convention.

## Why the auditor and triage worker are separated

The audit's job is **finding**. The triage worker's job is **fixing**. Splitting them has several payoffs:

1. **Bounded effort per PR.** A single triage run focuses on one issue. The audit can spread its attention across the full repo without burning the per-PR budget.
2. **Parallelism for free.** Multiple triage workers can run in parallel (one per issue), while the audit is serialized to its single concurrency group.
3. **Different model tiers.** The audit is volume-heavy (Sonnet); triage is depth-heavy for code (Opus). Mixing them in one run forces a bad compromise.
4. **Failure isolation.** A triage worker hitting an allowlist denial doesn't corrupt the audit's state file.
5. **Audit can pre-screen.** The audit applies labels and prefixes so the triage worker enters with context (`label: docs-audit` → use Sonnet) instead of guessing.

## Why the auto-review is a separate workflow

The auto-review fires on **every** PR touching the domain — not just bot-authored ones. It's a quality gate for human contributions too. Making it a separate workflow:

1. Lets it run on `pull_request_target` (which the audit and triage can't, because they write code).
2. Lets the allowed-tools allowlist be read-only.
3. Lets it use `cancel-in-progress: true` (the latest diff supersedes prior reviews).
4. Lets it be disabled independently if the review pass becomes noisy.

## Why the feedback capture is a separate workflow

The feedback workflow fires on **every PR close** matching the audit's branch prefix. Co-locating it with the auditor would tangle `on.schedule` with `on.pull_request_target` and make permissions harder to scope. Separating it:

1. Lets it run on `pull_request_target.closed` exclusively.
2. Lets the `if:` condition gate precisely on `merged == false` AND branch prefix.
3. Lets the `workflow_dispatch` re-run path be a clean separate entry point for backfill after late comments.

## How rejections close the loop

The rejection log is the most important non-obvious mechanism. Without it, the audit re-proposes the same wrong edit forever. The flow:

1. Audit opens a PR proposing some edit.
2. Reviewer (human) closes the PR without merging — sometimes with a comment explaining why.
3. Feedback workflow fires, captures the PR + the explanatory comments, appends one JSONL line.
4. Next audit run reads the log:
   - Extracts every `-/+` swap from the patches → never re-proposes the literal swap.
   - Reads the close comments → generalizes the lesson (e.g., "Vestaboard is the hardware, never rename it").
5. Audit's wrap-up summary cites the PRs whose lessons it applied.

The auditor's prompt explicitly instructs:
- "Treat the close commenter's reasoning as authoritative."
- "Generalize — most rejections expose a class of false positive."
- "Cite when relevant — mention the PR number in your wrap-up summary."

The maintainer can hand-delete a JSONL line if a rejection was wrong (the file is plain text).

## When components are optional

The minimal loop is:
- `claude-<name>.yml` (auditor)
- `.github/<name>-state.json` (sweep state)

The auditor still runs without any of: triage, review, feedback. It just won't fan out to per-issue fix PRs and won't learn from rejections.

You can add components incrementally:
- Just the auditor → sweeps + opens inline PRs.
- Auditor + triage → also fans out to per-issue fix PRs.
- Auditor + triage + review → adds a quality gate on PRs touching the domain.
- Auditor + triage + review + feedback → closes the learning loop. Recommended.

## Comparison: this skill vs. one-off audits

A one-off audit is a `gh workflow run` (or just `Agent` from a Claude Code session). It's faster to set up but:
- No state file → can't sweep large domains in batches.
- No rejection log → repeats wrong findings.
- No dedup → opens duplicate PRs.
- No queue-aware effort scaling → drowns the reviewer.

Use this skill when the domain is large enough that one pass can't cover it, recurring enough that learning matters, and the team wants the audit to throttle itself.

## Comparison: this skill vs. a Linear automation

Linear / Jira automations sit outside the codebase and report findings via API. They can be more flexible (custom dashboards, SLAs, cross-repo) but lose:
- Direct PR fan-out (Linear doesn't open PRs against your repo).
- Bytes-level diff capture for the rejection log.
- Free hosting on GitHub Actions.
- Co-location with the code being audited.

This skill is the right answer when the loop's outputs are PRs and the loop's input is the repo itself.
