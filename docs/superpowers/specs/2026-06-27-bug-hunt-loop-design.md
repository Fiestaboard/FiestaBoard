# Bug-Hunt Loop — Design Spec

**Date:** 2026-06-27
**Status:** Approved design, pre-implementation
**Author:** Jeffrey Johnson (with Claude)

A Claude-powered, self-improving GitHub Actions loop that proactively hunts for
real functional bugs in the FiestaBoard codebase — finding them before users do —
files high-trust issues, hands them to the existing triage worker for a
human-reviewed draft fix, and gets smarter over time from both the bugs we fix
and the false positives we reject.

It is the third sibling of the existing `docs-audit` and `a11y-audit` loops,
built with the `new-claude-github-actions-flow` skill pattern, with two
deliberate departures: a **multi-lens subagent fan-out with adversarial
verification**, and a **second positive-learning cron** that mines merged
bug-fixes into a pattern memory.

---

## 1. Goals & non-goals

### Goals
- Proactively surface real, functional bugs (logic, edge cases, error handling,
  concurrency/state, Python↔TS contract drift, security/input-validation)
  across the ~40k LOC Python + ~64k LOC TS/TSX codebase.
- **High precision**: only file a bug after independent adversarial verification.
  A trustworthy queue is the success metric; a noisy one kills the loop.
- **Learn in both directions**: raise recall where bugs really live (positive
  learning from merged fixes) and raise precision by never repeating a rejected
  false positive (negative learning).
- Reuse the proven loop plumbing and the shared triage worker. No bug fix lands
  without a human merging a draft PR.

### Non-goals
- Not a style/lint/perf/i18n/a11y auditor — those are covered by existing
  read-only finders (`render-perf-auditor`, `i18n-auditor`, `ts-sync-validator`,
  the a11y loop, etc.). The hunter targets **functional defects** only.
- The hunter never edits source code. It files issues only.
- Phase 1 does not *execute* repro tests in CI (that is Phase 2). Phase 1
  verification is reasoning-based, and the repro test is written into the issue.

---

## 2. Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Hunt scope | **Broad / multi-lens** — 5 specialized lens agents |
| 2 | Learning | **Both signals** — positive pattern memory + negative rejection log |
| 3 | Precision | **Adversarial verify** — independent skeptics refute each candidate; repro test where feasible |
| 4 | Fix handoff | **Issue → draft fix PR** via the shared triage worker; hunter never edits code |
| 5 | Cadence | Hunter **once daily**; learner **weekly** |
| 6 | Orchestration | **Option 1, phased to Option 2** — single-job hunter with subagent fan-out, reasoning-verified, issues-only now; designed so a real repro-execution job bolts on as Phase 2 |

---

## 3. Architecture

`bug-hunt` is the loop slug. Domain label `bug-hunt`; reuses existing `bug` and
`claude-fix` labels.

### Component inventory

| File | Trigger | Role |
|------|---------|------|
| `.github/workflows/claude-bug-hunt.yml` | daily cron + dispatch | **Hunter.** One job, fans out lens + skeptic subagents, files issues only. |
| `.github/workflows/claude-bug-hunt-learn.yml` | weekly cron + dispatch | **Learner.** Mines merged bug-fix PRs → updates pattern memory. |
| `.github/workflows/claude-bug-hunt-review.yml` | `pull_request_target` | Auto-reviews the loop's fix PRs (gated to `bug-hunt/issue-*` head branches). |
| `.github/workflows/claude-bug-hunt-feedback.yml` | `pull_request_target: closed` | Captures rejected fix PRs → rejection log. |
| `.github/bug-hunt-state.json` | data | Sweep progress over **subsystems** (areas), not single files. |
| `.github/bug-hunt/pattern-memory.md` | data | Positive learning: recurring root causes + bug-prone modules + per-lens checklists. |
| `.github/bug-hunt/rejected-edits.jsonl` | data | Negative learning: false positives we closed. |
| `.github/bug-hunt/gather_fixed_bugs.py` | script | Deterministically pulls merged bug-fix PRs + diffs for the learner. |
| `.github/bug-hunt/build_rejection.py` | script | Rejection-log builder (from skill template). |
| `.github/bug-hunt/README.md` | docs | Explains both memories. |
| `.github/bug-hunt/tests/test_gather_fixed_bugs.py` | test | Light pytest for the collector. |
| `.github/workflows/claude-issue-triage.yml` | **modified** | Add `bug-hunt` to the gate + a bug-hunt fix arm. |

### Why "subsystems," not files
Multi-lens bugs (a caller/callee mismatch, a contract drift, a race) span files.
The sweep unit is a curated **area** — an enumerated list of ~12–16 subsystems
defined in the hunter prompt. The state file tracks `areas_remaining` /
`areas_audited` and advances one round at a time, same shape as `docs-audit` but
coarser-grained.

Initial area list (tune during build):
`src/schedules`, `src/pages`, `src/collections` + `src/carousels`,
`src/board_client*` + rendering (`board_chars`, `board_html_renderer`,
`text_to_board`, `text_utils`), `src/plugins` loader/base + `plugins/*`,
`src/api_server.py` routes, `src/auth` + `src/security`, `src/mqtt`,
`src/triggers`, `src/displays`, `src/settings` + `config_manager`, `src/ai`,
`src/backup` + `src/system` + `src/network`, `web/src/routes`, `web/src/lib`
(API client + contract), `web/src/components` (state-heavy).

---

## 4. The daily hunt cycle (inside one `claude-code-action` run)

```
read state.json + pattern-memory.md + rejected-edits.jsonl
        │
        ▼
pick this run's area batch (1–2 areas, queue-aware)
        │
        ▼
FAN OUT — lens subagents (Task tool), in parallel, each read-only:
   ├─ backend-logic & edge cases        (src/**, plugins/**)
   ├─ error/exception handling
   ├─ concurrency & shared state
   ├─ Python↔TS API contract drift      (src/*/models.py ↔ web/src/lib/api.ts)
   └─ security & input validation
        │  each returns candidate bugs {area, lens, severity, trace, proposed repro}
        │  each lens prompt is seeded with the relevant pattern-memory checklist
        ▼
DEDUP candidates against open `bug-hunt` issues
   (gh issue list --label bug-hunt --state open --search "<key phrase>")
        ▼
VERIFY — for each candidate, N independent skeptic subagents try to REFUTE it
   (trace real code paths; default to "refuted" when uncertain;
    draft a failing repro — pytest for backend)
        │  keep only survivors (majority cannot refute)
        ▼
FILE issues (labels: bug, bug-hunt, claude-fix) with the structured body schema
   (see §7)
        ▼
advance state.json (move area→audited, set last_run_at) → commit [skip ci]
```

### Models
Lenses + skeptics + orchestrator: Sonnet 4.6. (All model tiers are knobs.)

### Compute envelope
Per run: ~5 lens subagents + up to ~2–3 skeptics per surviving candidate, over
1–2 areas. Bounded by `--max-turns` + `timeout-minutes` (30–45 min). Primary
cost levers: lens count, areas/run, skeptic count — all tunable.

---

## 5. The two memories

### Memory 1 — `pattern-memory.md` (positive learning)
Human-readable markdown the learner maintains and the hunter reads. Three living
sections:
- **Recurring root-cause patterns** — generalized, not one-offs. e.g.
  *"Naive timezone handling: schedules used server-local time instead of the
  configured TZ (#1273 → #1280). Scrutinize every `datetime.now()` and tz
  conversion."*
- **Bug-prone modules** — areas ranked by historical fix count; tells the sweep
  where to spend budget.
- **Per-lens checklists** — class-specific "things that have actually bitten us,"
  injected into each lens subagent's prompt.

Carries a `last_learned_at` marker (frontmatter) so the learner's window is
incremental.

### Memory 2 — `rejected-edits.jsonl` (negative learning)
The skill's standard mechanism. When a `bug-hunt/issue-*` fix PR is closed
**unmerged**, the feedback workflow bundles its diff + every comment into one
JSONL line. The hunter reads it each run: never re-file a refuted bug, and
generalize the false-positive class (*"looked like a race, but guarded by lock
Y — stop flagging this shape"*).

**The two memories pull in opposite directions on purpose:** pattern-memory
raises recall where bugs really live; rejected-edits raises precision by killing
repeat false positives.

---

## 6. The weekly learner — `claude-bug-hunt-learn.yml`

```
gather_fixed_bugs.py  (deterministic, no model)
   gh pr list --state merged --search "label:bug" since last_learned_at
   → for each: linked issue (Closes #N / (#N)) + fix diff + files touched → JSON
        │
        ▼
Claude (Sonnet) reads that JSON + current pattern-memory.md
   → distills/updates root-cause patterns, re-ranks bug-prone modules,
     extends per-lens checklists
        │
        ▼
rewrite pattern-memory.md → commit [skip ci]  (advance last_learned_at)
```

Data-gathering is a deterministic script so the model only does distillation.
`last_learned_at` bounds the window — incremental, not a full re-scan each week.

---

## 7. Issue body schema (also the Phase 2 hook)

Every filed issue carries a machine-parseable header and exactly one fenced
repro block, so Phase 2's executor can parse it with no rework:

```
## Bug-hunt finding

- **area:** src/schedules
- **lens:** concurrency
- **severity:** high
- **run:** round <N>, run <BRANCH_SUFFIX>

### What's wrong
<2–5 sentences>

### Why it's real (trace)
<code-path trace the skeptics could not refute, with file:line refs>

### Repro
```python
# runnable pytest that fails against current code
def test_...():
    ...
```

### Suggested direction
<2–5 sentences; not a full patch>
```

Labels: `bug`, `bug-hunt`, `claude-fix`. Reserved for Phase 2:
`repro-confirmed`, `repro-failed`.

---

## 8. Handoff / review / feedback

### Triage (modify existing `claude-issue-triage.yml`)
- Add `bug-hunt` to the `labeled` gate (alongside `claude-fix`, `docs-audit`,
  `a11y-audit`).
- Add a **bug-hunt arm** to the prompt: branch `bug-hunt/issue-<N>-<slug>`,
  **draft** PR, title `fix: …`. The worker lifts the issue's repro block into a
  real failing test, implements the smallest fix, makes it pass with the suite
  green, `Closes #N`.
- Model tier already defaults to **Opus** for non-docs issues — no tier change
  needed.

### Review — `claude-bug-hunt-review.yml`
- `pull_request_target` on code paths, but the **job `if:` is gated to head
  branch `bug-hunt/issue-*`** so it reviews only the loop's own fix PRs, not
  every code PR in the repo.
- Read-only, base-ref checkout, `persist-credentials: false`,
  `github_token: ${{ secrets.GITHUB_TOKEN }}` to bypass the OIDC App exchange,
  `allowed_bots: 'claude,github-actions'`, `cancel-in-progress: true`.
- Reviews the fix's correctness and that the repro test genuinely covers the bug.

### Feedback — `claude-bug-hunt-feedback.yml`
- `pull_request_target: closed` + `workflow_dispatch` (backfill).
- Gated on `merged == false` AND `startsWith(head.ref, 'bug-hunt/issue-')`.
- Runs `build_rejection.py`, commits the JSONL line `[skip ci]`,
  `cancel-in-progress: false`.

### Full data flow
```
        weekly                           daily
   ┌──────────────┐              ┌──────────────────┐
   │   LEARNER    │─writes──▶ pattern-memory.md ──read─▶│   HUNTER    │
   └──────────────┘                                     │ (fan-out +  │
          ▲                    rejected-edits.jsonl ─read─▶│  verify)   │
          │ reads                      ▲                 └──────┬──────┘
   merged bug-fix PRs                  │ writes                 │ files
          ▲                     ┌──────────────┐         bug + bug-hunt + claude-fix
          │                     │  FEEDBACK    │                │
   merge ─┘                     └──────────────┘                ▼
          ▲                            ▲                  ┌──────────┐
          │                     close unmerged            │  ISSUE   │
   ┌──────────────┐                    │                  └────┬─────┘
   │ human merges │◀─review─┐          │                       │ claude-fix label
   │   fix PR     │         │          │                       ▼
   └──────────────┘   ┌─────────────┐  │                ┌──────────────┐
                      │   REVIEW    │  └────────────────│ TRIAGE WORKER│
                      └─────────────┘   draft fix PR ◀──│ (Opus, draft)│
                                        bug-hunt/issue-*└──────────────┘
```

---

## 9. Safety & error handling (applied from the skill's pitfalls)

- **Concurrency:** `cancel-in-progress: false` on hunt, learn, feedback;
  `true` on review.
- **`show_full_output: 'true'`** on every Claude step.
- **`BRANCH_SUFFIX: ${{ github.run_id }}`** kept even though issues-only (issue
  bodies cite the run; never `date +%s`).
- **`RELEASE_PAT`** for state + memory commits past branch protection, and as
  `GH_TOKEN` for `gh issue create`. **`[skip ci]`** on all commit types.
  **Defensive state push** as the final hunter step if Claude exits early.
- **Time-gate** on local PT hour + **cooldown** (`last_run_at`, ~20h for a daily
  cadence). `workflow_dispatch` bypasses both.
- **`allowed_bots: 'claude,github-actions'`** on review/feedback;
  `allowed_bots: 'claude'` already on triage.

### Issues-only trims on the hunter
- Permissions: `contents: write` (state/memory), `issues: write`,
  `id-token: write` — **no `pull-requests: write`**.
- Allowlist drops all `gh pr …` / branch tools and **adds `Task`** for subagent
  fan-out. `Edit`/`Write` stay but a **hard rule restricts them to
  `.github/bug-hunt-state.json` only** — the hunter never touches source.
- Lens subagents are read-only (`Read,Glob,Grep,Bash(cat/find/grep/rg)`); only
  the orchestrator writes state and calls `gh issue create`.

### Precision governance
- A candidate is filed only if a **majority of independent skeptics cannot
  refute it**; skeptics default to "refuted" under uncertainty.
- **Queue-aware effort:** drained → 2 areas + all 5 lenses + thorough;
  hot (open `bug-hunt` issues over a ceiling) → 1 area + security/crash lenses +
  high-confidence bar. A hard **open-issue ceiling silences filing** when the
  queue is saturated (the issues-only analog of the draft cap).
- Lenses target real defects, not style; low-severity nitpicks are dropped by
  design.

---

## 10. Phase 2 (reserved, not built now)

`claude-bug-hunt-verify.yml`: on the `bug-hunt` label, checkout →
`./.github/actions/setup-python-deps` → parse the issue's repro block → run it
via pytest. Label `repro-confirmed` (+ failing output comment) or `repro-failed`
(likely false positive). This both hardens precision and hands the triage worker
a ready failing test. The §7 schema and the two label names are reserved now so
Phase 2 needs no rework.

---

## 11. Testing the loop itself

- **Hunter:** a `dry_run` dispatch input that prints intended issues instead of
  filing them — eyeball candidate quality on one known area before enabling the
  cron.
- **Learner acceptance test:** point `gather_fixed_bugs.py` at the known
  #1273→#1280 timezone fix; confirm `pattern-memory.md` gains a sensible
  timezone root-cause entry.
- **Scripts:** `build_rejection.py` exercisable with `DRY_RUN=1` against a real
  closed PR; `gather_fixed_bugs.py` gets a pytest under `.github/bug-hunt/tests/`
  confirming it parses `Closes #N` / `(#N)` and emits the expected JSON.
- **First live run:** watch the Actions log (`show_full_output`) for denials on
  the new `Task` tool and subagent inheritance; confirm two back-to-back
  dispatches don't double-file (cooldown + serialized concurrency).

---

## 12. Prerequisites & rollout

- **Secrets:** `RELEASE_PAT`, `CLAUDE_CODE_OAUTH_TOKEN` — already used by the two
  existing loops, so present.
- **Rollout order:**
  1. Land scripts + state + memory skeletons + the triage gate change.
  2. Land the hunter with `dry_run` default-safe; dispatch once, inspect.
  3. Enable the daily cron; watch false-positive rate for a week.
  4. Land the learner; run once; verify pattern-memory updates.
  5. Land review + feedback.
  6. Once trusted, build Phase 2 (repro execution).

---

## 13. Open questions / risks

- **`Task` subagent path is unexercised in this repo's workflows.** First run
  must confirm `claude-code-action` admits the `Task` tool and that subagents
  inherit read tools. Fallback if not: sequential multi-lens in one context
  (no fan-out), or Option 3 (matrix of jobs).
- **Frontend repro tests** are hard to execute in Phase 2 (Python pytest is
  clean; TS logic bugs lean on reasoning + Playwright). Phase 2 execution
  initially targets backend bugs only.
- **Cost.** Daily multi-lens + adversarial verify is the heaviest of the three
  loops. The queue-aware effort scaler and the lens/area/skeptic knobs are the
  controls; start conservative.
- **Area list churn.** As the codebase evolves the enumerated area list needs
  occasional maintenance; acceptable, and visible in the prompt.
