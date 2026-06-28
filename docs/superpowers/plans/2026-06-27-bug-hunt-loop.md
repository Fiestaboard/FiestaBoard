# Bug-Hunt Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily, self-improving GitHub Actions loop that hunts for real functional bugs via a multi-lens subagent fan-out with adversarial verification, files high-trust issues, hands them to the shared triage worker for a human-reviewed draft fix, and learns from both merged fixes (positive) and rejected fixes (negative).

**Architecture:** Third sibling of `docs-audit` / `a11y-audit`, built from the `new-claude-github-actions-flow` skill templates with two departures: (1) the hunter runs lens + skeptic subagents inside one `claude-code-action` run (issues-only output), and (2) a separate weekly learner cron mines merged bug-fix PRs into a `pattern-memory.md`. Option 1 now; the §7 issue schema is designed so a Phase-2 repro-execution job bolts on later.

**Tech Stack:** GitHub Actions, `anthropics/claude-code-action@v1`, Claude (Sonnet 4.6 for hunt/learn/review, Opus 4.7 for triage fixes), Python 3 (`gather_fixed_bugs.py`, `build_rejection.py`), `gh` CLI, `jq`.

## Global Constraints

- Loop slug: `bug-hunt`. Domain label: `bug-hunt`. Reuse existing `bug` + `claude-fix` labels.
- Hunter branch prefix (fix PRs from triage): `bug-hunt/issue-<N>-<slug>`.
- Hunter is **issues-only**: permissions `contents: write`, `issues: write`, `id-token: write` — NO `pull-requests: write`. `Edit`/`Write` restricted by hard rule to `.github/bug-hunt-state.json` only.
- Subagent fan-out requires `Task` in the hunter's `--allowed-tools`.
- Every Claude step: `show_full_output: 'true'`. Hunter env: `BRANCH_SUFFIX: ${{ github.run_id }}` (never `date +%s`).
- Commits to `main` from workflows use `RELEASE_PAT` and carry `[skip ci]`.
- Concurrency: `cancel-in-progress: false` on hunt/learn/feedback; `true` on review.
- Models are knobs but defaults: hunt/learn/review = `claude-sonnet-4-6`; triage fix = `claude-opus-4-7` (existing default).
- Source of truth for boilerplate: `.claude/skills/new-claude-github-actions-flow/references/templates/`. Canonical live instances to mirror: `.github/workflows/claude-a11y-audit.yml` (issues-capable audit), `.github/workflows/claude-docs-audit.yml`, `.github/workflows/claude-a11y-audit-review.yml`, `.github/workflows/docs-audit-feedback.yml`.
- Privacy rules from `CLAUDE.md`: no real PII/keys/coords in any example.

---

### Task 1: Scaffold `.github/bug-hunt/` data + memory skeletons + state file

**Files:**
- Create: `.github/bug-hunt-state.json`
- Create: `.github/bug-hunt/pattern-memory.md`
- Create: `.github/bug-hunt/rejected-edits.jsonl` (empty)
- Create: `.github/bug-hunt/README.md`

**Interfaces:**
- Produces: the state schema (`schema_version:1, round:0, round_started_at:null, last_run_at:null, areas_remaining:[], areas_audited:[]`) consumed by Task 4; `pattern-memory.md` consumed by Tasks 4 & 5; `rejected-edits.jsonl` consumed by Task 4 & written by Task 7.

- [ ] **Step 1: Write `.github/bug-hunt-state.json`** — copy `state.json.tmpl` but rename `files_*` → `areas_*`:
```json
{
  "schema_version": 1,
  "round": 0,
  "round_started_at": null,
  "last_run_at": null,
  "last_learned_at": null,
  "areas_remaining": [],
  "areas_audited": []
}
```

- [ ] **Step 2: Write `.github/bug-hunt/pattern-memory.md`** — seeded skeleton with frontmatter `last_learned_at: null`, the three sections (Recurring root-cause patterns, Bug-prone modules, Per-lens checklists), and one seeded example entry (the #1273→#1280 timezone pattern) so the hunter has a non-empty memory on day one.

- [ ] **Step 3: Create empty `.github/bug-hunt/rejected-edits.jsonl`** (zero bytes).

- [ ] **Step 4: Write `.github/bug-hunt/README.md`** — adapt `feedback-readme.md.tmpl`, plus a section documenting the SECOND memory (`pattern-memory.md`) and the learner workflow. Explain both memories and how to hand-edit them.

- [ ] **Step 5: Commit**
```bash
git add .github/bug-hunt-state.json .github/bug-hunt/
git commit -m "feat(bug-hunt): scaffold sweep state + dual-memory skeletons"
```

---

### Task 2: `gather_fixed_bugs.py` + pytest (TDD)

**Files:**
- Create: `.github/bug-hunt/gather_fixed_bugs.py`
- Create: `.github/bug-hunt/tests/test_gather_fixed_bugs.py`

**Interfaces:**
- Produces: `parse_linked_issues(body: str) -> list[int]` (parses `Closes #N`, `Fixes #N`, `Resolves #N`, and trailing `(#N)`), and a `main()` that prints JSON `[{pr, title, closed_at, linked_issues, files:[{path,patch}]}]` for merged PRs labelled `bug` since an optional `--since` ISO timestamp. Consumed by Task 5's learner workflow.

- [ ] **Step 1: Write the failing test** for `parse_linked_issues`:
```python
from pathlib import Path
import importlib.util
spec = importlib.util.spec_from_file_location(
    "gfb", Path(__file__).parent.parent / "gather_fixed_bugs.py")
gfb = importlib.util.module_from_spec(spec); spec.loader.exec_module(gfb)

def test_parse_closes_fixes_resolves_and_paren():
    body = "Closes #1273\nalso Fixes #99 and resolves #100\ntitle (#1280)"
    assert sorted(gfb.parse_linked_issues(body)) == [99, 100, 1273, 1280]

def test_parse_dedupes_and_ignores_non_refs():
    assert gfb.parse_linked_issues("no refs here #notanumber") == []
    assert gfb.parse_linked_issues("Closes #5 Closes #5") == [5]
```

- [ ] **Step 2: Run it, verify failure**
Run: `python3 -m pytest .github/bug-hunt/tests/test_gather_fixed_bugs.py -v`
Expected: FAIL (module/function missing).

- [ ] **Step 3: Implement `gather_fixed_bugs.py`** — `parse_linked_issues` via regex `(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)` (case-insensitive) plus `\(#(\d+)\)`, deduped. `main()` uses `gh pr list --state merged --search "label:bug" --json number,title,closedAt,body` (+ `--search` date filter when `--since` given), then `gh pr diff <n> --patch` per PR, parsing the unified diff into `{path,patch}` (reuse the `parse_diff` logic from `build_rejection.py.tmpl`). Supports `DRY_RUN`/stdout JSON. No network in the unit test (only `parse_linked_issues` is tested).

- [ ] **Step 4: Run tests, verify pass**
Run: `python3 -m pytest .github/bug-hunt/tests/test_gather_fixed_bugs.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**
```bash
git add .github/bug-hunt/gather_fixed_bugs.py .github/bug-hunt/tests/
git commit -m "feat(bug-hunt): add deterministic merged-bug-fix collector + tests"
```

---

### Task 3: `build_rejection.py` (negative-learning log builder)

**Files:**
- Create: `.github/bug-hunt/build_rejection.py`

**Interfaces:**
- Produces: `build_rejection.py <pr_number>` that writes one idempotent JSONL line to `.github/bug-hunt/rejected-edits.jsonl`; refuses merged PRs; replaces a prior line for the same PR. Consumed by Task 7's feedback workflow.

- [ ] **Step 1: Copy `build_rejection.py.tmpl`** to `.github/bug-hunt/build_rejection.py`, substituting `{{REJECTION_LOG}}` → `.github/bug-hunt/rejected-edits.jsonl`, `{{NAME}}` → `bug-hunt`.

- [ ] **Step 2: Smoke-check it imports**
Run: `python3 -c "import ast; ast.parse(open('.github/bug-hunt/build_rejection.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**
```bash
git add .github/bug-hunt/build_rejection.py
git commit -m "feat(bug-hunt): add rejection-log builder (negative learning)"
```

---

### Task 4: The hunter — `.github/workflows/claude-bug-hunt.yml`

**Files:**
- Create: `.github/workflows/claude-bug-hunt.yml`

**Interfaces:**
- Consumes: state file (Task 1), both memories (Tasks 1/5/7).
- Produces: GitHub issues labelled `bug,bug-hunt,claude-fix` with the §7 schema body; advances the state file.

Base on `audit-cron.yml.tmpl` + `claude-a11y-audit.yml`, then apply **issues-only trims** and the **multi-lens prompt**. Key specifics:

- [ ] **Step 1: Workflow skeleton & triggers** — `on.schedule` one daily PT window via paired UTC crons (e.g. `7 19 * * *` and `7 20 * * *`) + `workflow_dispatch` with a boolean input `dry_run` (default `false`). `concurrency.group: bug-hunt`, `cancel-in-progress: false`. Top-level `permissions: contents: read`.

- [ ] **Step 2: Gate + dedup + effort steps** — copy the gate (local PT hour, `TZ=America/Los_Angeles`, ~30-min slop), the cooldown (`last_run_at` < 20h bounces; `workflow_dispatch` bypasses), and the dynamic-effort step but keyed on **open `bug-hunt` issue count**: drained (≤ `EFFORT_BALANCED_THRESHOLD`=15) → 2 areas + thorough; warm (≤ 30) → 1–2 areas + balanced; hot (> 30) → 1 area + conservative + silence-filing ceiling at 40. Outputs `mode`, `areas`, `cap`.

- [ ] **Step 3: Job permissions (issues-only trim)** —
```yaml
permissions:
  contents: write
  issues: write
  id-token: write
```

- [ ] **Step 4: Claude step env + args** — `GH_TOKEN: ${{ secrets.RELEASE_PAT }}`, `BRANCH_SUFFIX: ${{ github.run_id }}`, effort outputs. `claude_args`:
```
--model claude-sonnet-4-6
--max-turns 250
--allowed-tools "Task,Read,Glob,Grep,Edit,Write,Bash(ls:*),Bash(cat:*),Bash(find:*),Bash(grep:*),Bash(rg:*),Bash(date:*),Bash(jq:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git rev-parse:*),Bash(gh issue list:*),Bash(gh issue view:*),Bash(gh issue create:*),Bash(gh issue edit:*),Bash(gh label list:*),Bash(gh label create:*)"
```
`with: show_full_output: 'true'`, `claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}`. (No `pull-requests` tools, no `git branch/checkout` — issues-only.)

- [ ] **Step 5: The hunter prompt** — bespoke. Sections, in order:
  1. **Intro:** "You are the FiestaBoard bug hunter. You run daily and hunt for real functional bugs before users hit them. You do NOT edit source — you file issues only."
  2. **Effort block** (mode/areas/cap from effort outputs).
  3. **Learning from past rejections** — read `.github/bug-hunt/rejected-edits.jsonl` first (copy the template's rejection section; never re-file a refuted bug; generalize).
  4. **Pattern memory** — read `.github/bug-hunt/pattern-memory.md`; use bug-prone-module ranking to bias area pick and feed each lens its checklist.
  5. **Sweep state** — schema with `areas_*`; the enumerated area list (§3 of spec); if `areas_remaining` empty, refill from the enumerated list, bump round.
  6. **Fan out** — "Dispatch one subagent per lens via the Task tool, in parallel. Each lens is READ-ONLY. Lenses: backend-logic, error-handling, concurrency-state, contract-drift (src/*/models.py ↔ web/src/lib/api.ts), security-input. Give each lens the area(s), the rejection lessons, and its pattern-memory checklist. Each returns candidates {area,lens,severity,trace,proposed_repro}."
  7. **Dedup** — `gh issue list --label bug-hunt --state open --search "<phrase>"`.
  8. **Adversarial verify** — "For each candidate, dispatch 2–3 independent skeptic subagents whose job is to REFUTE it: trace the real code paths, default to refuted under uncertainty, and draft a failing repro (pytest for backend). File only if a majority cannot refute."
  9. **Output / issue schema** — the §7 body verbatim; labels `bug,bug-hunt,claude-fix`; create labels idempotently (`gh label create bug-hunt --color B60205 --description "Filed by the bug-hunt cron" || true`); apply `claude-fix`.
  10. **State commit** — move audited areas, set `last_run_at`, write back, commit `chore(bug-hunt): advance sweep state [skip ci]`.
  11. **Hard rules** — only direct-to-main commit is the state file; edits restricted to `.github/bug-hunt-state.json`; never touch source; never exceed `cap` issues; honor dedup; if `dry_run` input is true, PRINT intended issues and do NOT call `gh issue create` or commit state.
  12. **Wrap-up** summary.

- [ ] **Step 6: Defensive state push step** — copy template's final `Push state-file changes` step (guarded by `dry_run == false`).

- [ ] **Step 7: Validate YAML**
Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/claude-bug-hunt.yml')); print('ok')"`
Expected: `ok`. (Plus `actionlint` if available — see Task 9.)

- [ ] **Step 8: Commit**
```bash
git add .github/workflows/claude-bug-hunt.yml
git commit -m "feat(bug-hunt): add daily multi-lens hunter workflow (issues-only)"
```

---

### Task 5: The learner — `.github/workflows/claude-bug-hunt-learn.yml`

**Files:**
- Create: `.github/workflows/claude-bug-hunt-learn.yml`

**Interfaces:**
- Consumes: `gather_fixed_bugs.py` (Task 2), `pattern-memory.md` (Task 1).
- Produces: rewritten `pattern-memory.md`, committed `[skip ci]`.

- [ ] **Step 1: Triggers & concurrency** — `on.schedule` weekly (e.g. `0 18 * * 1` Mon + DST pair `0 19 * * 1`) + `workflow_dispatch`. `concurrency.group: bug-hunt-learn`, `cancel-in-progress: false`. `permissions: contents: read` top-level.

- [ ] **Step 2: Checkout with RELEASE_PAT** (`fetch-depth: 0`), set up Python via `./.github/actions/setup-python-deps`, configure git identity.

- [ ] **Step 3: Gather step** — `python3 .github/bug-hunt/gather_fixed_bugs.py --since "$(jq -r '.last_learned_at // empty' .github/bug-hunt-state.json)" > /tmp/fixed-bugs.json` (env `GH_TOKEN: RELEASE_PAT`). Echo the count.

- [ ] **Step 4: Job permissions** — `contents: write`, `issues: read`, `pull-requests: read`, `id-token: write`.

- [ ] **Step 5: Claude step** — model `claude-sonnet-4-6`, `--max-turns 60`, `show_full_output: 'true'`, allowlist `Read,Glob,Grep,Edit,Write,Bash(cat:*),Bash(jq:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git status:*),Bash(git diff:*)`. Prompt: "Read `/tmp/fixed-bugs.json` and `.github/bug-hunt/pattern-memory.md`. For each fixed bug, distill the GENERALIZED root-cause (not the one-off), update/extend the three sections, re-rank bug-prone modules by fix count, and set frontmatter `last_learned_at` to now (ISO8601 UTC). Keep it concise — prune stale/duplicate patterns. Write the file back. Also set `last_learned_at` in `.github/bug-hunt-state.json`. Commit `chore(bug-hunt): refresh pattern memory [skip ci]` and push."

- [ ] **Step 6: Defensive push step** for `pattern-memory.md` + state (mirror Task 4 Step 6).

- [ ] **Step 7: Validate YAML + commit**
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/claude-bug-hunt-learn.yml')); print('ok')"
git add .github/workflows/claude-bug-hunt-learn.yml
git commit -m "feat(bug-hunt): add weekly learner that mines fixes into pattern memory"
```

---

### Task 6: Auto-review — `.github/workflows/claude-bug-hunt-review.yml`

**Files:**
- Create: `.github/workflows/claude-bug-hunt-review.yml`

**Interfaces:**
- Consumes: nothing internal; reviews PRs whose head branch is `bug-hunt/issue-*`.

- [ ] **Step 1:** Base on `auto-review.yml.tmpl` + `claude-a11y-audit-review.yml`. `on.pull_request_target: types [opened, synchronize, reopened, ready_for_review]`, `paths: ['src/**','plugins/**','web/src/**']`.

- [ ] **Step 2: Job gate** — `if:` requires `github.event.pull_request.draft == false || true` (review drafts too, since fixes open as draft — set the condition to fire on draft bug-hunt PRs) AND `startsWith(github.event.pull_request.head.ref, 'bug-hunt/issue-')`. Note: because triage opens these as DRAFT, do NOT exclude drafts here (unlike the a11y/docs reviewers). Comment this explicitly.

- [ ] **Step 3:** Base-ref checkout (`ref: ${{ github.event.pull_request.base.ref }}`, `persist-credentials: false`, `fetch-depth: 1`). Claude step with `github_token: ${{ secrets.GITHUB_TOKEN }}`, `allowed_bots: 'claude,github-actions'`, read-only allowlist (`Read,Glob,Grep,Bash(cat:*),Bash(find:*),Bash(grep:*),Bash(rg:*),Bash(jq:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(gh pr diff:*),Bash(gh pr view:*),Bash(gh pr review:*),Bash(gh api:*)`), model `claude-sonnet-4-6`, `--max-turns 40`. Prompt: review the fix's correctness, that the repro test genuinely fails-then-passes and covers the bug, no scope creep, follows CLAUDE.md; post ONE `gh pr review --comment`. `concurrency.group: claude-bug-hunt-review-${{ github.event.pull_request.number }}`, `cancel-in-progress: true`.

- [ ] **Step 4: Validate YAML + commit**
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/claude-bug-hunt-review.yml')); print('ok')"
git add .github/workflows/claude-bug-hunt-review.yml
git commit -m "feat(bug-hunt): add auto-review for bug-hunt fix PRs"
```

---

### Task 7: Feedback capture — `.github/workflows/claude-bug-hunt-feedback.yml`

**Files:**
- Create: `.github/workflows/claude-bug-hunt-feedback.yml`

**Interfaces:**
- Consumes: `build_rejection.py` (Task 3). Produces appended `rejected-edits.jsonl`.

- [ ] **Step 1:** Copy `feedback-capture.yml.tmpl`, substitute `{{NAME}}`→`bug-hunt`, `{{REJECTION_LOG}}`→`.github/bug-hunt/rejected-edits.jsonl`, `{{FEEDBACK_DIR}}`→`.github/bug-hunt/`, `{{CONCURRENCY_GROUP_FEEDBACK}}`→`bug-hunt-feedback`. The `if:` startsWith uses ONLY `bug-hunt/issue-` (single source — there are no bucket-A audit branches in issues-only mode).

- [ ] **Step 2: Validate YAML + commit**
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/claude-bug-hunt-feedback.yml')); print('ok')"
git add .github/workflows/claude-bug-hunt-feedback.yml
git commit -m "feat(bug-hunt): add rejection-capture feedback workflow"
```

---

### Task 8: Extend the shared triage worker

**Files:**
- Modify: `.github/workflows/claude-issue-triage.yml`

**Interfaces:**
- Consumes: issues labelled `bug-hunt`. Produces: `bug-hunt/issue-<N>-<slug>` draft fix PRs.

- [ ] **Step 1: Add `bug-hunt` to the label gate** (the `github.event.action == 'labeled'` block, alongside `claude-fix`/`docs-audit`/`a11y-audit`).

- [ ] **Step 2: Add a bug-hunt arm to the prompt's step 4** — before the "everything else" fallback: "For bug-hunt issues (labels include `bug-hunt`): branch `bug-hunt/issue-${{ github.event.issue.number }}-<short-slug>`, title prefix `fix:`. The issue body contains a fenced ```python repro``` block — add it as a real failing test FIRST (TDD), confirm it fails, implement the smallest fix, confirm it passes and the suite stays green, then open as a **draft** (`gh pr create --draft`). `Closes #N`."

- [ ] **Step 3: Update the header comment** (the numbered trigger list) to add the bug-hunt cron as trigger #5.

- [ ] **Step 4: Validate YAML + commit**
```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/claude-issue-triage.yml')); print('ok')"
git add .github/workflows/claude-issue-triage.yml
git commit -m "feat(bug-hunt): route bug-hunt issues through triage as draft fix PRs"
```

---

### Task 9: Final validation + PR

**Files:** none (validation only).

- [ ] **Step 1: Lint all new workflows** — if `actionlint` is available run it on the four new files + the modified triage file; otherwise rely on the per-task `yaml.safe_load` checks. Record any findings and fix.

- [ ] **Step 2: Run the Python test**
Run: `python3 -m pytest .github/bug-hunt/tests/ -v`
Expected: PASS.

- [ ] **Step 3: Grep guardrail audit** — confirm: `BRANCH_SUFFIX: ${{ github.run_id }}` present in hunter; `show_full_output: 'true'` in all four; `cancel-in-progress: false` on hunt/learn/feedback and `true` on review; `Task` in hunter allowlist; no `pull-requests: write` on the hunter job; `[skip ci]` on every workflow commit message; `RELEASE_PAT` used for checkout/commit on hunt/learn/feedback.

- [ ] **Step 4: Open the PR** against `main` (title `feat(bug-hunt): scaffold proactive bug-hunting feedback loop`), body listing every file added/modified, calling out deviations from the docs-audit canonical pattern (multi-lens subagents, second learner cron, issues-only hunter), and noting Phase 2 is deferred. Include the manual dispatch + first-cron-tick info.

---

## Self-Review

**Spec coverage:** §3 components → Tasks 1–8 (state/memory T1, scripts T2/T3, hunter T4, learner T5, review T6, feedback T7, triage T8). §4 hunt cycle → T4 Step 5. §5 memories → T1+T5+T7. §6 learner → T5. §7 schema → T4 Step 5.9 (and reserved labels noted). §8 handoff → T6/T7/T8. §9 safety → T4 trims + T9 Step 3 audit. §10 Phase 2 → reserved, not built (correct). §11 testing → T2 (unit), T4 `dry_run` (Step 5.11), T9. §12 prereqs → Global Constraints. No gaps.

**Placeholder scan:** `<N>`, `<slug>`, `<phrase>` are runtime template values, not plan placeholders. The hunter/learner prompts are specified by section content rather than verbatim 300-line transcripts — acceptable because the implementer (this session) holds full template context and the canonical live workflows are cited as the base. No "TBD/handle edge cases" hand-waves.

**Type consistency:** state keys `areas_remaining`/`areas_audited`/`last_run_at`/`last_learned_at` consistent across T1/T4/T5. Branch prefix `bug-hunt/issue-` consistent across T6/T7/T8. Label set `bug,bug-hunt,claude-fix` consistent T4/T8. `parse_linked_issues` signature consistent T2↔T5.
