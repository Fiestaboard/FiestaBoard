# Pitfalls

Every entry here cost a real PR, a real silent failure, or a real CI debugging session. Read this end-to-end before scaffolding or tuning a loop. The PR numbers refer to the FiestaBoard history — `git log -- .github/workflows/claude-*.yml` will give you the full context.

## Branch naming — never `date +%s`

**Symptom:** branches like `docs-audit/round-3-run-1758049200` with the unix timestamp from a year ago.

**Cause:** the audit prompt asked Claude to pick a unique branch suffix and Claude invented `$(date +%s)` — except the model's "now" was its training cutoff, not the actual run time. PR #967 was the first time this happened.

**Fix:** the workflow sets `BRANCH_SUFFIX: ${{ github.run_id }}` in `env:`, and the prompt instructs Claude to read that env var (`echo "$BRANCH_SUFFIX"`) instead of computing a timestamp. `github.run_id` is unique per run and stable.

```yaml
env:
  BRANCH_SUFFIX: ${{ github.run_id }}
```

```
prompt: |
  ...
  Create a branch named exactly:
      docs-audit/round-<round>-run-$BRANCH_SUFFIX

  where $BRANCH_SUFFIX is the BRANCH_SUFFIX env var. Do NOT use `date +%s`.
  Verify with `echo "$BRANCH_SUFFIX"` first.
```

## Concurrency — `cancel-in-progress: false`

**Symptom:** two PRs touching the same files, opened seconds apart, both saying "round 3 batch 8–16".

**Cause:** PRs #966/#967 — two cron triggers fired in the same window (e.g., the second of a UTC cron pair), both read the same `files_remaining` from the state file, both picked the same batch, both opened a PR.

**Fix:**

```yaml
concurrency:
  group: <name>-audit
  cancel-in-progress: false
```

`cancel-in-progress: false` is critical. A `workflow_dispatch` fired during a scheduled run should *wait its turn*, not abort the scheduled run. With `true` you'd lose the scheduled run mid-way and corrupt the state file.

The feedback-capture workflow also needs serialization — two PRs closed at once would race the JSONL log:

```yaml
concurrency:
  group: <name>-audit-feedback
  cancel-in-progress: false
```

The review workflow is the *opposite* — there you want `cancel-in-progress: true` because only the latest diff matters.

## DST and cron — UTC pairs per intended PT window

GitHub Actions only accepts UTC crons. America/Los_Angeles is UTC-8 (PST) in winter and UTC-7 (PDT) in summer. A single cron line will drift by one hour twice a year.

**Symptom:** the audit fires at 11am instead of noon for half the year.

**Fix:** declare **two crons per intended local window** and gate them with a local-hour check.

```yaml
on:
  schedule:
    - cron: '7 19 * * *'   # 12:07 PDT (summer) — winter cron gated off
    - cron: '7 20 * * *'   # 12:07 PST (winter) — summer cron gated by cooldown
    - cron: '7 23 * * *'   # 16:07 PDT (summer)
    - cron: '7 0 * * *'    # 16:07 PST (winter)
```

The gate step bounces the run if the local PT hour is outside the intended windows:

```bash
hour=$(TZ=America/Los_Angeles date +%H)
minute=$(TZ=America/Los_Angeles date +%M)
in_window=false
if [ "$hour" = "12" ] || { [ "$hour" = "13" ] && [ "$minute" -le 30 ]; }; then
  in_window=true
fi
# ... etc
```

The 30-minute slop on the upper bound absorbs typical GitHub Actions cron delay (often 10–30 min). Without it, a delayed run misses its window.

`workflow_dispatch` always bypasses the gate.

## Cooldown — block paired UTC crons in the same window

**Symptom:** the audit runs twice in 15 minutes (e.g., 12:07 PDT and 13:07 PDT both fire on the same day if both UTC crons are admitted by the gate).

**Cause:** during DST one of the paired UTC crons falls inside the gate window of the *next* window.

**Fix:** add a `last_run_at` check that bounces runs younger than ~3 hours.

```bash
last=$(jq -r '.last_run_at // empty' .github/<name>-state.json)
if [ -n "$last" ]; then
  age_h=$(( ($(date -u +%s) - $(date -u -d "$last" +%s)) / 3600 ))
  if [ "$age_h" -lt 3 ]; then
    echo "Skipping: last run was ${age_h}h ago."
    exit 0
  fi
fi
```

`workflow_dispatch` bypasses this check too.

## Open-draft cap — prevent unbounded stacking

**Symptom:** five docs-audit drafts open, reviewer stops reviewing them, the audit keeps opening new ones for weeks.

**Fix:** cap how many open drafts the audit tolerates before silencing itself:

```bash
draft_count=$(gh pr list --search "head:<name>/" --state open --json number --jq 'length')
if [ "$draft_count" -ge 5 ]; then
  echo "Skipping: ${draft_count} open audit draft(s)."
  exit 0
fi
```

5 is the docs-audit value. Tune per domain: a high-volume domain with patient reviewers can run higher; a low-volume domain wants a smaller cap. The previous version of this check used "any draft open" and the audit silenced itself for weeks at a time — a hard ceiling without a relief valve is too strict.

## Dynamic effort — scale with queue depth

The audit batch size and issue cap should scale **inverse** to open issue count. A drained queue means triage is keeping up; a hot queue means reviewers are drowning.

```bash
open_count=$(gh issue list --label <name> --state open --limit 200 --json number --jq 'length')
if [ "$open_count" -gt 80 ]; then
  mode="conservative"; batch=12; cap=32
elif [ "$open_count" -gt 40 ]; then
  mode="balanced";     batch=24; cap=60
else
  mode="thorough";     batch=32; cap=100
fi
```

The mode threads into the prompt via `${{ steps.effort.outputs.mode }}` interpolation. The prompt's "Aggressiveness" section uses it to decide how confident a finding needs to be before filing.

Don't make this a static knob — the whole point is self-balancing.

## `--allowed-tools` allowlist — read-only by default

**Symptom:** 25 turns burned, $1 spent, no PR, no comment, conclusion=success in the Actions log.

**Cause:** the `anthropics/claude-code-action` agent-mode default toolset is **read-only**. Every `Edit`, `Write`, `git push`, or `gh pr create` is denied. Without `show_full_output: 'true'`, the denial messages are hidden and the run looks like a clean success.

**Fix:** explicit allowlist that matches **every Bash pattern the prompt actually invokes**:

```yaml
claude_args: >-
  --model claude-sonnet-4-6
  --max-turns 250
  --allowed-tools "Read,Glob,Grep,Edit,Write,Bash(ls:*),Bash(cat:*),Bash(find:*),Bash(date:*),Bash(jq:*),Bash(git status:*),Bash(git diff:*),Bash(git log:*),Bash(git show:*),Bash(git branch:*),Bash(git checkout:*),Bash(git switch:*),Bash(git add:*),Bash(git commit:*),Bash(git push:*),Bash(git fetch:*),Bash(git rev-parse:*),Bash(gh pr create:*),Bash(gh pr view:*),Bash(gh pr list:*),Bash(gh issue list:*),Bash(gh issue view:*),Bash(gh issue create:*),Bash(gh issue edit:*),Bash(gh label list:*),Bash(gh label create:*)"
```

Audit and triage workflows need write access. Review workflows are read-only and the allowlist should reflect that — no `Edit`/`Write`, no `git push`, no `gh pr create`.

If you add a new Bash invocation to a prompt, the allowlist must grow too.

## `show_full_output: 'true'` — always

Without this, the action prints `full output hidden for security`. Silent permission denials, hallucinated tool calls, and stuck-in-a-loop conditions all look like green checkmarks.

```yaml
with:
  show_full_output: 'true'
```

If you ever wonder "why did this run cost $X and produce nothing?" — this is the answer 80% of the time.

## `allowed_bots: 'claude'` — for bot-filed issues

**Symptom:** the audit cron files issues with `gh issue create` (so the author is the `claude` bot). The triage workflow sees the new issue, the `if:` condition admits it… and the `anthropics/claude-code-action` rejects the run with "Workflow initiated by non-human actor: claude".

**Fix:**

```yaml
with:
  allowed_bots: 'claude'
```

For the auto-review workflow, both bot identities show up — bot-authored PRs come from `claude` or `github-actions`:

```yaml
with:
  allowed_bots: 'claude,github-actions'
```

This is independent of the workflow's own `if:` gate. The action has its own anti-bot guard layered on top.

## `pull_request_target` vs `pull_request` for feedback capture

**Symptom:** PR #992 closed one second after the feedback workflow merged. The capture workflow never fired. The branch was already created from `main` *before* the capture workflow existed — and `pull_request` resolves workflow definitions from the **PR's head ref**.

**Fix:** use `pull_request_target` so GitHub resolves the workflow from `main`:

```yaml
on:
  pull_request_target:
    types: [closed]
```

Branches cut from `main` before the workflow was added would otherwise be invisible to it forever. With `pull_request_target` the workflow runs against `main`'s definition regardless of head-ref age.

**Safety:** `pull_request_target` grants secrets to the workflow. Two musts:
1. Check out the **base ref** (or no checkout at all), never the PR head.
2. Read PR head content via `gh api .../contents/<path>?ref=<head_sha>` — bytes piped through Claude as *data*, never materialized in a path a later step could execute.

The action's `--allowed-tools` is your last line of defense. Keep it read-only for `pull_request_target` workflows.

## Auto-review workflow checkout — base ref only

**Symptom:** none yet — but CodeQL's `actions/untrusted-checkout` rule flags this pattern. It's called "pwn-request": a malicious PR head edits `.github/workflows/foo.yml` to leak secrets, and if you check out the head with `actions/checkout`, the malicious workflow runs against your secrets.

**Fix:**

```yaml
- uses: actions/checkout@v6
  with:
    ref: ${{ github.event.pull_request.base.ref }}
    fetch-depth: 1
    persist-credentials: false
```

`persist-credentials: false` prevents the workflow's `GITHUB_TOKEN` from leaking into the working tree where the prompt might accidentally surface it.

## OIDC App exchange fails on `pull_request_target` — bypass it

**Symptom:** the auto-review workflow logs `401 Invalid OIDC token` when the action tries to exchange the OIDC token for a `claude[bot]` App token.

**Cause:** the App's trust policy doesn't admit `pull_request_target` subjects.

**Fix:** provide `github_token` to skip the OIDC exchange:

```yaml
with:
  claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
  github_token: ${{ secrets.GITHUB_TOKEN }}
```

The cost: review comments are posted under `github-actions[bot]` instead of `claude[bot]`. The feedback-capture workflow's `allowed_bots` allowlist must include `github-actions` because the review badge is now from that identity.

## State file must commit with `[skip ci]`

**Symptom:** every audit run triggers the audit again because the state-file commit fired `push` on `main`.

**Fix:** include `[skip ci]` in the commit message:

```
chore(<name>-audit): advance sweep state [skip ci]
```

The audit workflow doesn't currently listen on push-to-main, but if the repo ever adds `on.push` to anything, the audit's own commit shouldn't be the trigger.

## Hard rules in the prompt — bound the blast radius

The audit prompt has explicit guardrails so Claude can't go off-roading:

```
## Hard rules
- Never push to `main` except for the single state-file commit above.
- Never force-push, never `--no-verify`, never `--no-gpg-sign`.
- Never modify non-docs source code. Edits are restricted to *.md and the state file.
- Never open more than 1 PR per run.
- Never file more than <CAP> issues per run.
- When dedup says skip, skip — don't refile the same finding.
```

The "Edits are restricted to" rule is the most important. Without it Claude has carte blanche over the repo for the duration of the run. State the *exact* file types editable and the *exact* paths writable.

## RELEASE_PAT for state-file pushes past branch protection

**Symptom:** the state-file commit fails with "GH006: Protected branch update failed for refs/heads/main".

**Cause:** `main` is branch-protected; the default `GITHUB_TOKEN` can't bypass.

**Fix:** use a personal access token stored as `RELEASE_PAT`:

```yaml
- uses: actions/checkout@v6
  with:
    token: ${{ secrets.RELEASE_PAT }}
    fetch-depth: 0
```

The same `RELEASE_PAT` is also needed for `gh pr create` calls that the action makes — pass it as `GH_TOKEN` in `env:`.

## Defensive state-file push at the end

If the Claude step exits early (rate limit, allowlist denial, hallucination), the state file may be staged but not pushed. A defensive final step catches this:

```yaml
- name: Push state-file changes
  if: steps.dedup.outputs.go == 'true'
  run: |
    if git diff --quiet -- .github/<name>-state.json; then
      echo "State file unchanged."
      exit 0
    fi
    git add .github/<name>-state.json
    git commit -m "chore(<name>-audit): advance sweep state [skip ci]"
    git push origin HEAD:main
```

This isn't ideal — Claude exited mid-run, so the round counter may be inconsistent — but it's better than a state file that says "round 3, 50 files remaining" forever.

## Rejection log learning — feed it back in the prompt

The feedback-capture workflow appends rejected PRs to `.github/<name>/rejected-edits.jsonl`. The audit prompt **must** read that file at the top of every run:

```
Read `.github/<name>/rejected-edits.jsonl` before doing anything else.
Each non-empty line is a previous audit PR that a human closed without
merging — i.e. the proposed edit was wrong. The log is your single most
important input.

For each rejection:
1. Never repeat the exact swap (extract -/+ lines from each file's patch).
2. Read every comment — the closer's reasoning is authoritative.
3. Generalize — most rejections expose a class of false positive.
4. Cite when relevant — mention the PR number when you skip a finding.
```

Without this section in the prompt, the audit will re-propose the same wrong edit forever.

## Idempotent rejection capture

`build_rejection.py` must replace a prior line for the same PR rather than append a duplicate. The `workflow_dispatch` re-run path exists specifically for backfilling after a late explanatory comment.

```python
def keep(line: str) -> bool:
    try:
        return json.loads(line).get("pr") != record["pr"]
    except json.JSONDecodeError:
        return True  # preserve hand-edited lines
```

The script also refuses to log merged PRs:

```python
if meta.get("state") == "MERGED":
    raise SystemExit(f"PR #{pr} was merged — refusing to record as rejection.")
```

## Triage worker — triple trigger and bot allowlist

The shared triage worker (`claude-issue-triage.yml`) is gated three ways:
1. Issue opened by trusted author (OWNER / MEMBER / COLLABORATOR)
2. `claude-fix` label applied manually
3. Audit's domain label applied (e.g., `docs-audit`, `tests-audit`)

Without gate 3, audit-filed issues won't trigger triage because the bot author doesn't satisfy gate 1.

Gate 3 must be reflected in two places:
1. The workflow's `if:` condition (`github.event.label.name == 'docs-audit'`)
2. The action's `allowed_bots: 'claude'` (so the run isn't rejected post-gate)

When you add a new loop, **edit the triage workflow** to add the new label to its `if:` condition, and update the model-tier selection step if the new loop should prefer Sonnet (docs-flavored) or Opus (code-flavored).

## Branch prefix → PR style mapping

Inline audit PRs are **ready-for-review** (no `--draft` flag). Triage-worker PRs may be draft or ready depending on flavor:

- Docs-flavored: ready-for-review (PRs go through normal docs review path)
- Code-flavored: draft (human validates the first-pass code fix)

Branch naming carries the flavor:
- `<name>/round-<n>-run-<id>` — audit inline PR (always ready-for-review)
- `<short>/issue-<N>-<slug>` — triage PR (flavor-dependent draft state)

The feedback capture's `if:` condition must match both prefixes if both flavors should feed the rejection log.

## Don't widen permissions speculatively

`permissions: contents: read` at the top of the workflow, then `contents: write` only on the job that needs it. The least-privilege baseline matters because `pull_request_target` workflows have secrets attached.

For the audit job:
```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
  id-token: write
```

For the review job:
```yaml
permissions:
  contents: read
  pull-requests: write   # to post the review
  id-token: write
  actions: read
```

For the feedback capture:
```yaml
permissions:
  contents: write        # to commit the JSONL log
  pull-requests: read
  issues: read
```

## Summary — the five most painful

If you only remember five things:

1. **`BRANCH_SUFFIX: ${{ github.run_id }}`** — never `date +%s`.
2. **`show_full_output: 'true'`** — silent denials look like success without it.
3. **`--allowed-tools`** — the action's default is read-only; every write needs allowlisting.
4. **`pull_request_target`** (with base-ref checkout) for feedback capture and auto-review.
5. **`concurrency: cancel-in-progress: false`** on the audit and feedback workflows.
