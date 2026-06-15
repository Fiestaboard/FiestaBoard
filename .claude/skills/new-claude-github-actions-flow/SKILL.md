---
name: new-claude-github-actions-flow
description: Scaffold or tune a Claude-powered GitHub Actions feedback loop — the docs-audit pattern (scheduled cron → audit → file issues → open PRs → auto-review → capture rejections to learn from). Use this skill whenever the user wants to create a new automated Claude workflow for a domain (tests, perf, i18n, plugins, security, infra, accessibility, schema migrations, etc.), mirror the docs-audit pattern, set up a recurring audit-and-fix loop, add a scheduled Claude job to GitHub Actions, build a "Claude workflow" or "Claude feedback loop", or tune knobs on an existing claude-*.yml workflow (cron schedule, model tier, batch size, queue thresholds, file globs, draft caps, allowed-tools allowlists, time-window gates). Trigger eagerly on phrases like "set up an automation", "Claude cron", "recurring Claude job", "audit loop", "feedback loop", "scan repeatedly for X", "automate fixing X", "fan out Claude on X", "add a workflow that runs every day", or any request to tune cron / effort / model on an existing `.github/workflows/claude-*.yml` file. Use this skill even when the user does not say "skill" or "scaffold" — if the intent is "make Claude do this on a schedule and open PRs", that is this skill.
---

# new-claude-github-actions-flow

## What this skill does

Scaffolds (or tunes) a Claude-powered, self-improving audit-and-fix loop on GitHub Actions. The canonical example is the FiestaBoard `docs-audit` system: a cron-driven Claude run sweeps a domain (markdown files), opens trivial fixes inline as ready-for-review PRs, files issues for everything else, fans out per-issue triage workers, auto-reviews docs PRs, and captures rejection feedback so the next sweep doesn't repeat mistakes.

This skill lets you create the same shape of loop for **any domain** — tests, performance, i18n, plugin manifests, schema migrations, security findings, broken images, dead links — with the knobs (schedule, model tier, batch size, file globs) tuned for that domain.

## When NOT to use this skill

- The user wants a **one-off** Claude task, not a recurring loop → use a regular slash command or the `Agent` tool.
- The user wants to **manually run** an existing workflow once → just `gh workflow run …`.
- The user wants to **author the prompt logic** for an existing loop's Claude run → edit the prompt directly; you don't need scaffolding.

## The shape of a loop

Every loop produced by this skill has up to four GitHub Actions workflows plus a state file. Components are independently optional, but the recommended default is all four:

| File | Trigger | Purpose |
| --- | --- | --- |
| `.github/workflows/claude-<name>.yml` | `schedule` + `workflow_dispatch` | Main audit cron. Sweeps the domain in batches, opens trivial fixes inline, files issues for the rest. |
| `.github/workflows/claude-issue-triage.yml` (one shared, not per-loop) | `issues: [opened, labeled]` | Per-issue worker. When the audit files an issue with the loop's label, this opens a focused fix PR. |
| `.github/workflows/claude-<name>-review.yml` | `pull_request_target` on paths | Auto-reviews every PR touching the domain, before merge. |
| `.github/workflows/claude-<name>-feedback.yml` | `pull_request_target: [closed]` | Captures closed-without-merge PRs into a JSONL rejection log the next audit reads. |
| `.github/<name>-state.json` | (file, not a workflow) | Sweep progress: round, files_remaining, files_audited, last_run_at. |
| `.github/<name>/build_rejection.py` | (script) | Builds one JSONL line per rejected PR with full diff + every comment. |
| `.github/<name>/rejected-edits.jsonl` | (data) | Append-only learning log the audit prompt reads at the start of every run. |
| `.github/<name>/README.md` | (docs) | Explains the loop's feedback memory for human maintainers. |

The canonical reference instance is `docs-audit`. Read `.github/workflows/claude-docs-audit.yml`, `.github/workflows/docs-audit-feedback.yml`, `.github/workflows/claude-docs-review.yml`, `.github/workflows/claude-issue-triage.yml`, and `.github/docs-audit/` end-to-end before you scaffold a new loop. They are the source of truth for the pattern — these templates copy from them, not the other way around.

## Detecting mode: CREATE vs TUNE

Read the user's message. If they want to **make a new loop**, go to [CREATE flow](#create-flow). If they want to **change knobs on an existing loop** (schedule, model, batch size, etc.), go to [TUNE flow](#tune-flow). If unclear, ask.

Examples of CREATE intent: "set up an audit loop for tests", "I want a Claude cron that scans plugins", "mirror docs-audit but for accessibility", "automate fixing broken images in screenshots".

Examples of TUNE intent: "make the docs-audit run every 4 hours instead of 2", "bump batch size", "switch the docs review to Haiku", "I want the audit to skip files under `web/messages/`", "drop the cap when queue is hot".

## CREATE flow

### Step 1 — Gather variables

Ask the user these questions in order. Suggest a sensible default and let them confirm or override. Use one `AskUserQuestion` batch if you're in Claude Code; otherwise go inline.

**Required:**

1. **Loop name (slug)** — kebab-case, used in filenames, labels, branch prefixes. Example: `tests-audit`, `perf-audit`, `i18n-audit`, `plugin-audit`. Must not collide with an existing `claude-*.yml` workflow.
2. **What is this loop auditing?** — one paragraph describing the domain. The user's words go into the audit prompt verbatim. Examples: "the Python test suite for flaky tests, slow tests, and missing coverage" / "plugin manifests for missing fields, stale screenshots, and category drift".
3. **File globs to sweep** — include + exclude patterns. Default exclude list: `node_modules/`, `.git/`, `**/node_modules/`, `tools/`, `.claude/`. Example for tests: include `tests/**/*.py`, `plugins/*/tests/**/*.py`; exclude `**/__pycache__/`.

**Optional (use the defaults unless the user objects):**

4. **Components** — default all four. Sub-options:
   - Triage worker reuse — if `.github/workflows/claude-issue-triage.yml` already exists, reuse it; just add the new label to its `if:` gate. Don't create a per-loop triage worker.
   - Skip the auto-review if PRs touching this domain don't need a separate Claude review pass.
   - Skip the feedback capture if the loop is read-only (no PRs to learn from).
   - **Issues-only mode** (no inline PRs at all): if the loop only files issues — no bucket-A inline fixes — apply the trims in [Issues-only trims](#issues-only-trims) below. This is a real variant; the docs-audit default opens inline PRs, but `manifest-audit`-style loops where every finding needs a thinking pass don't.
5. **Cadence** — default: twice daily, noon + 4pm PT. Other patterns: daily, weekly, on push to main, weekdays-only.
6. **Model tier** — default for audit: Sonnet 4.6. Default for triage: Opus 4.7 (code) / Sonnet 4.6 (docs). Default for review: Sonnet 4.6.
7. **Effort thresholds** — default mirrors docs-audit: queue ≤ 40 → thorough; 40–80 → balanced; > 80 → conservative. Batch sizes 32/24/12, caps 100/60/32.
8. **Branch prefix** — default `<name>/round-<n>-run-<id>` for inline PRs, `<short-name>/issue-<N>-<slug>` for triage PRs.
9. **Issue labels** — default: domain label + `<name>` + `claude-fix` (for triage handoff).

### Step 2 — Confirm the file plan

List the files you'll create with their exact paths. Show the user before writing anything. Example:

```
Will create:
  .github/workflows/claude-tests-audit.yml          (audit cron)
  .github/workflows/claude-tests-audit-review.yml   (PR auto-review)
  .github/workflows/claude-tests-audit-feedback.yml (rejection capture)
  .github/tests-audit-state.json                    (sweep state)
  .github/tests-audit/README.md                     (folder doc)
  .github/tests-audit/build_rejection.py            (script)
  .github/tests-audit/rejected-edits.jsonl          (empty)

Will modify:
  .github/workflows/claude-issue-triage.yml         (add `tests-audit` to label gate)
```

### Step 3 — Render the templates

Read each template from `references/templates/`. Each template uses `{{TOKEN}}` placeholders documented in `references/variables.md`. Substitute the variables per the user's choices. Write the rendered file to its target path on a feature branch.

Template files to read:
- `references/templates/audit-cron.yml.tmpl` → main audit workflow
- `references/templates/auto-review.yml.tmpl` → PR auto-review (skip if user opted out)
- `references/templates/feedback-capture.yml.tmpl` → rejection capture (skip if opted out)
- `references/templates/state.json.tmpl` → initial sweep state
- `references/templates/build_rejection.py.tmpl` → rejection log builder
- `references/templates/feedback-readme.md.tmpl` → human-readable folder docs

For the **audit prompt body** — the long `prompt:` block in the audit workflow — synthesize it from the user's domain description. Use the docs-audit prompt as the structural template (sweep logic, batch picking, bucket A/B/C definitions, rejection-log learning, hard rules, wrap-up summary) but rewrite the domain-specific paragraphs:
- "You are the FiestaBoard X auditor." — substitute X.
- The categorization section (what counts as bucket A / B / C for this domain).
- Glob patterns for file discovery.
- Hard rules around which files Claude may edit.

If the loop has no triage worker, drop the "After creating each issue, also apply the `claude-fix` label" instruction.

### Step 4 — Read the pitfalls before writing

**Before you write any workflow file, read `references/pitfalls.md` end-to-end.** Every gotcha in there has cost real PRs and real debugging time. The biggest ones:

- `BRANCH_SUFFIX=${{ github.run_id }}` — never `date +%s` (the model invents stale 2025 timestamps).
- `pull_request_target` for feedback capture, NOT `pull_request` — branches don't carry the workflow forward.
- `--allowed-tools` allowlist must match every Bash pattern the prompt invokes — missing patterns silently fail.
- `show_full_output: 'true'` — without it, permission denials look like clean successes.
- `allowed_bots: 'claude'` — required when bot-authored issues should trigger the workflow.
- Auto-review uses `github_token: ${{ secrets.GITHUB_TOKEN }}` to bypass the OIDC App exchange on `pull_request_target`.
- Auto-review checks out the **base ref**, never the PR head (CodeQL `actions/untrusted-checkout`).
- Concurrency group + `cancel-in-progress: false` — without it, parallel runs open duplicate PRs.
- Cron pairs in UTC to absorb DST — one pair per intended PT window.

### Step 5 — Branch, commit, PR

Per `CLAUDE.md`, never push directly to `main`. Cut a feature branch (`feat-<name>-loop`), commit the rendered files with conventional commit messages, push, and open a PR with `gh pr create`. Title: `feat(<name>-audit): scaffold Claude feedback loop`. In the PR body, list every file added and call out any deviation from the docs-audit canonical pattern.

If the canonical docs-audit triage worker already exists, edit `.github/workflows/claude-issue-triage.yml` to extend the `labeled` condition with the new loop's label and bump the model-tier selection if appropriate.

### Step 6 — Tell the user what's next

After the PR opens, tell the user explicitly:
- The first cron tick — when the loop will fire on its own.
- How to manual-dispatch it now: `gh workflow run claude-<name>.yml`.
- Where to find the state file and rejection log.
- The labels to apply to issues that should trigger the triage worker (if any).
- How to disable the loop quickly (delete the schedule, or `gh workflow disable`).

## Issues-only trims

When the loop only files issues — no inline bucket-A PRs, no auto-review, no feedback capture — the audit workflow's surface area shrinks. Apply *every* trim below; leaving any one in place is dead permission or dead instruction that future-you will have to reason about. The state-file commit still happens, so a few write capabilities stay.

**Permissions block (audit job).** Drop `pull-requests: write`. Keep `contents: write` (state-file commit), `issues: write`, `id-token: write`. Result:

```yaml
permissions:
  contents: write
  issues: write
  id-token: write
```

**`--allowed-tools` allowlist.** Drop these (the audit never invokes them):

- `Bash(gh pr create:*)`
- `Bash(gh pr view:*)`
- `Bash(gh pr list:*)` *(or keep only if dedup still wants it — see below)*
- `Bash(gh pr edit:*)`
- `Bash(git branch:*)`, `Bash(git checkout:*)`, `Bash(git switch:*)`, `Bash(git fetch:*)`

**Keep** these — they're still needed for the state-file commit and for issue work:

- `Read`, `Glob`, `Grep`, `Edit`, `Write` (Edit/Write are how Claude rewrites the state JSON)
- `Bash(git add:*)`, `Bash(git commit:*)`, `Bash(git push:*)`, `Bash(git status:*)`, `Bash(git diff:*)`, `Bash(git log:*)`, `Bash(git show:*)`, `Bash(git rev-parse:*)`
- `Bash(gh issue list:*)`, `Bash(gh issue view:*)`, `Bash(gh issue create:*)`, `Bash(gh issue edit:*)`
- `Bash(gh label list:*)`, `Bash(gh label create:*)`
- `Bash(ls:*)`, `Bash(cat:*)`, `Bash(find:*)`, `Bash(date:*)`, `Bash(jq:*)`

**Prompt body.** Strip these sections:

- Bucket A (the trivial-mechanical-fixes case). Every finding is an issue; there's no bucket A.
- "Create a branch named exactly … Branch off `main`. Apply ONLY the bucket-A fixes. Commit. Open a … PR." — gone.
- The draft-cap dedup check (no drafts exist when no PRs are opened). The cooldown check stays.
- "After creating each issue, also apply the `claude-fix` label" — drop unless a triage worker exists.

**Hard rules.** Replace "Edits are restricted to `<editable globs>`" with "Edits are restricted to `<STATE_FILE>` only". The audit must not modify source code outside the state file.

**What stays.**
- The full sweep/state logic (state file, batches, rounds).
- The dedup cooldown check.
- The dynamic-effort step (queue depth → batch/cap).
- The wrap-up summary.
- The defensive state-file push at the end.
- All the pitfall guards: `BRANCH_SUFFIX`, `show_full_output`, `concurrency.cancel-in-progress: false`, `RELEASE_PAT` for checkout, `TZ=…` gate, `[skip ci]` on the state commit.

**`BRANCH_SUFFIX` in issues-only mode.** Even though no PR branches are created, keep the env var. It's cheap, it lets issue bodies reference the run (`round <N>, run $BRANCH_SUFFIX`), and it preserves the pattern so future-you can re-enable bucket A without re-engineering.

## TUNE flow

The audit loop's behaviour is controlled by a handful of knobs. Most live in the workflow YAML; a few live in the prompt block.

### Step 1 — Identify the loop

If the user says "the docs audit", look at `.github/workflows/claude-docs-audit.yml`. If they reference another loop, find it by `ls .github/workflows/claude-*.yml`. If ambiguous, ask.

### Step 2 — Identify the knob

Read `references/variables.md`. Every knob is catalogued there with:
- What it controls
- Where in the workflow file it lives (step name, env var, or interpolation token)
- The trade-offs (lower batch = more PRs per day; higher cap = noisier reviewer queue; etc.)
- Cross-references — some knobs need updates in multiple places.

Common tuning requests and where they land:

| Request | File(s) | Knob |
| --- | --- | --- |
| "Run every 4 hours" | audit workflow | `on.schedule.cron` pairs + the local-time gate |
| "Use Opus instead of Sonnet" | audit workflow | `--model` in `claude_args` |
| "Bump batch / cap" | audit workflow | "Compute dynamic effort" step's branches |
| "Add a file pattern to skip" | audit workflow | Prompt's glob-discovery section |
| "Hold off when N drafts open" | audit workflow | "Dedup against recent runs" step's `draft_count` cap |
| "Allow another Bash command" | audit workflow | `--allowed-tools` allowlist |
| "Auto-review more file types" | review workflow | `on.pull_request_target.paths` |
| "Capture rejections from new branch prefix" | feedback workflow | `if:` startsWith condition |

### Step 3 — Make the change

For straight YAML edits, use `Edit`. For prompt-body changes, edit the multiline `prompt: |` block carefully — the indentation matters; YAML block scalars are sensitive.

If a knob is referenced in multiple places (e.g., model tier appears in both `env:` for visibility and `claude_args:` for execution), update both. `references/variables.md` flags these.

### Step 4 — Test before opening the PR

GitHub Actions cron triggers can't be locally simulated, but `workflow_dispatch` runs as soon as you push. If the user wants to validate, suggest opening the PR, merging, and then dispatching the workflow once to see the effect.

For dry-running: the `prompt:` block can be lifted into a local Claude run with the same inputs to sanity-check the new logic.

### Step 5 — Branch, commit, PR

Same as CREATE step 5. PR title: `chore(<name>-audit): <what you tuned>`. PR body should call out before/after for every knob you changed, and explain why (queue too hot, reviewer fatigue, missed findings, etc.).

## Key references

Read these before making decisions:
- `references/pitfalls.md` — every hard-won lesson, with the PR that taught it.
- `references/variables.md` — full knob catalogue for tuning.
- `references/architecture.md` — how the four workflows interlock and why.
- `references/templates/` — the parameterized YAML and Python templates.
- `.github/workflows/claude-docs-audit.yml` (in the repo) — the canonical instance.

## Hard rules

These apply to every loop you scaffold:

- **Never commit directly to `main`.** Feature branch + PR. This skill is meant to follow `CLAUDE.md`.
- **Never skip `show_full_output: 'true'`.** Without it, silent permission denials masquerade as clean successes.
- **Never use `date +%s` for branch suffixes.** Use `github.run_id` via `BRANCH_SUFFIX` env var.
- **Never use `pull_request` for feedback capture.** Use `pull_request_target` so the workflow is resolved from `main`, not the PR head.
- **Never check out the PR head ref in an auto-review workflow.** Always the base ref. PR content is read via `gh api .../contents` from inside the prompt.
- **Never widen `--allowed-tools` beyond what the prompt actually invokes.** Each pattern is a foot-gun.
- **Never set `cancel-in-progress: true` on the audit workflow.** Parallel runs racing the state file open duplicate PRs.
- **Always copy the dedup + cooldown logic** from docs-audit. Without it, reviewer queues blow up.
- **Always seed the state file** to `schema_version: 1, round: 0, files_remaining: [], files_audited: []`. The first cron run computes the file list.

## Wrap-up

After scaffolding or tuning, give the user:
- A one-line summary of what landed.
- The PR URL.
- The first scheduled trigger time.
- The manual dispatch command.
- A heads-up about anything they should monitor on the first few runs (queue depth, false-positive rate, allowed-tools denial errors in the action log).
