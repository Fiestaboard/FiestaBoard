Triage open issues and PRs for the current GitHub repo: spawn fix attempts on unaddressed bugs, then keep the user's PRs green and rebased.

This is a long-running, multi-phase command. Phase 1 (issues) must finish before Phase 2 (PRs) — bugs may produce PRs that Phase 2 then tends. Within each phase, run independent work in parallel.

`gh` must be authed. If `gh auth status` fails, tell the user to run `! gh auth login` and stop.

## Phase 1 — Triage open issues

### 1.1 Fetch and classify

```
gh issue list --state open --limit 100 \
  --json number,title,body,labels,assignees,author,createdAt,updatedAt
```

Classify each issue as **bug** (in-scope) or **skip** using this order:

1. **Label-decisive.** Any of these labels → skip immediately, with reason:
   - `enhancement`, `feature`, `feature-request`, `proposal`, `rfc`
   - `question`, `discussion`, `help wanted` *(only when also `question`)*
   - `wontfix`, `invalid`, `duplicate`, `stale`
   - `good first issue` *(skip — leave for humans)*

2. **Label-decisive in-scope.** Any of these → bug:
   - `bug`, `defect`, `regression`, `crash`, `broken`

3. **No decisive label → quick LLM read.** Look at title + first ~500 chars of body. Treat as **bug** when the text describes broken behavior: error messages, "doesn't work", "expected X got Y", stack traces, "regression after vX.Y". Treat as **skip** when it reads like a feature ask: "add support for", "would be nice", "could we", "we should support".

   Be conservative: when ambiguous, classify as skip and note the reason. The cost of skipping a bug is one round of human triage; the cost of spawning a fixer on an enhancement is a wasted draft PR.

### 1.2 Filter to unaddressed

For each `bug`, skip when any of these is true (capture the reason for the summary):

- An assignee is already set and is not the current user — someone owns it.
- A linked PR exists. Check with:
  ```
  gh issue view <N> --json closedByPullRequestsReferences,timelineItems
  ```
  Also do a cross-search for PRs that reference `#<N>` in title or body:
  ```
  gh pr list --state open --search "#<N> in:title,body" --json number,title,author
  ```
- The issue has a `triaged` / `in-progress` / `working-on-it` label, or any "claimed" convention used by this repo.
- The issue was created less than 24h ago — give humans first crack.

### 1.3 Spawn fix attempts in parallel

For each remaining bug, spawn a **background** Agent with `subagent_type=bug-fixer`. Send them all in a single message so they run concurrently. Each agent gets its own prompt with:

- The issue number, title, full body, and link.
- The branch naming rule: `fix-issue-<N>-<short-slug>`.
- The PR rule: open a **draft** PR titled `fix(<scope>): <summary> (#<N>)` with body `Closes #<N>` and a brief reproduction + fix summary.
- The repo rules: never push to `main`, never force-push, never `--no-verify`, run tests inside Docker per `CLAUDE.md`, use TDD (failing regression test first).

Agent prompt template:

```
You are fixing GitHub issue #<N>: "<title>".

Full report:
<body>

Reproduce the bug, write a failing regression test that captures the
incorrect behavior, then make the smallest change that turns it green.
No drive-by refactors. No new abstractions.

Branch: fix-issue-<N>-<slug>, branched from origin/main.
Tests: run inside the dev container per CLAUDE.md.
When done: open a DRAFT PR against main with title
"fix(<scope>): <summary> (#<N>)" and body containing "Closes #<N>"
plus a short repro + fix summary. Do not mark ready-for-review —
the user will review.

Never push to main, never force-push, never bypass hooks.
```

Track each spawned agent in a list with: issue number, agent id (from the tool result), and current status. Do **not** block waiting for them to finish — they run for minutes to hours. Move to Phase 2 once they are all spawned.

If the issue list is large (>10 unaddressed bugs), ask the user first before fanning out — that many parallel fixers is a big commit.

## Phase 2 — Tend the user's PRs

### 2.1 Identify in-scope PRs

```
ME=$(gh api user --jq .login)
gh pr list --state open --limit 100 \
  --json number,title,author,assignees,isDraft,headRefName,baseRefName,mergeable,mergeStateStatus,statusCheckRollup,updatedAt
```

A PR is in-scope when **any** of:

- `author.login == $ME` (self).
- `author.login == "dependabot[bot]"`.
- `author.login` ends with `[bot]` and is a known agent: `dependabot`, `renovate`, `copilot-swe-agent`, `claude`, `github-actions`, `pre-commit-ci`. Treat unfamiliar bots as in-scope but tag them in the summary so the user knows.
- Any assignee's login matches `$ME`.

Skip drafts authored by other humans — they're not done yet. Self-drafts are in-scope (you may have left them half-finished).

### 2.2 Classify state per PR

For each in-scope PR, look at `statusCheckRollup` and `mergeStateStatus`:

| Situation | Action |
|---|---|
| All checks green, mergeable, up to date | Skip — nothing to do. Note "ready". |
| `mergeStateStatus = BEHIND` (only stale-with-base, checks pass) | **Update branch** — `gh pr update-branch <N>`. If that errors with merge conflicts, fall through to local rebase. |
| Any check failing | **Fix CI** (see 2.3). |
| Both behind AND failing | **Rebase first**, then re-check CI. A stale branch often explains the failure. |
| `mergeStateStatus = DIRTY` (conflicts) | For dependabot PRs: `@dependabot rebase` comment. For self/other-agent: do a local rebase in a worktree and resolve. If conflicts are non-trivial, skip with reason "needs human conflict resolution". |
| `mergeStateStatus = BLOCKED` for review reasons | Skip — needs reviewers, not code changes. Note in summary. |

### 2.3 Fix failing CI

For each PR with failing CI, run this sequence. Do PRs in parallel by giving each its own git worktree so they don't trample each other:

```
git worktree add ../.claude/worktrees/triage-pr-<N> <pr-head-branch>
```

Per PR:

1. **Diagnose first.** Fetch the failing run:
   ```
   gh pr checks <N>
   gh run view <run-id> --log-failed
   ```
   Apply the `why-ci-failed` skill's mental model: skip the wall of red, find the first real error per stage (lint vs unit vs integration vs build), and classify.

2. **Decide whether to fix.**
   - **Dependabot PR:** A failing dependabot upgrade usually means the new version broke something in our code, not the PR itself. Spawn a `bug-fixer` agent to fix our code on the dependabot branch (`dependabot/...`), then push. If the upgrade is genuinely incompatible (major version bump with breaking API changes), leave a comment summarizing the breakage and skip — the user decides whether to pin.
   - **Self PR:** Spawn a `bug-fixer` agent on the branch with the failing-run summary as input.
   - **Other-agent PR:** Same as self — spawn a `bug-fixer`. Note the original author in the summary so the user can decide whether they want our changes layered on.
   - **Flaky test signal** (intermittent, no source change since green): re-run with `gh run rerun <run-id> --failed` instead of spawning a fixer. Note in summary.

3. **Agent prompt template for PR fixes:**
   ```
   You are repairing failing CI on PR #<N>: "<title>".
   Branch: <head-ref> (already checked out at <worktree-path>).
   Failing run: <url>

   First-error-per-stage summary:
   <pasted from gh run view --log-failed>

   Reproduce the failure locally (inside the dev container per CLAUDE.md),
   write a regression test if one is missing, fix, push to the same branch.
   Do not rebase or merge main in this step — the orchestrator handled that.
   Do not mark the PR ready or change its title/body.
   Never force-push, never --no-verify.
   ```

4. **Run agents in parallel via Agent + `run_in_background: true`.** Cap parallelism at 4 — beyond that, Docker test runs start fighting for resources.

### 2.4 Rebase / update-branch path

When only stale-with-base:

1. Prefer `gh pr update-branch <N>` — it does a merge from base, which works for most cases and doesn't rewrite history.
2. If the PR head ref is a branch you own (self or this-agent), and the PR description or repo convention prefers rebased history, do a local rebase in a worktree and `git push --force-with-lease` (never `--force`).
3. For dependabot PRs, post `@dependabot rebase` as a comment instead of touching the branch — dependabot owns its branches.

## Phase 3 — Summary

Print a single table at the end. Keep it to one screen:

```
ISSUES
  spawned:  #123 #145 #160         (3 fix-attempt agents in flight)
  skipped:  #99  enhancement label
            #112 already has PR #134
            #150 created <24h ago

PRS
  fixed:    #200 CI failures patched + pushed
            #205 dependabot upgrade conflict resolved
  rebased:  #210 update-branch
            #212 local rebase + force-with-lease
  ready:    #220 (already green and up to date)
  skipped:  #225 needs human conflict resolution
            #230 BLOCKED on review, not code

IN FLIGHT
  3 issue fixers + 2 PR fixers spawned as background agents.
  Re-run /triage in ~20 min to see results, or check `gh pr list --author @me`.
```

The point of the summary is so the user can scan it and immediately know what's queued vs done vs needs their eyes.

## Safety rules

- Never push to `main`. Never `--force` (use `--force-with-lease` only when rebasing your own branches).
- Never `--no-verify` or `--no-gpg-sign`.
- Never auto-merge a PR.
- Never close issues — only PRs that resolve them close issues, and only when the user merges.
- If anything looks ambiguous (unknown bot author, weird mergeable state, conflicts in core files), skip it and report — the cost of stopping is low.
- Don't spawn more than 10 background agents in a single run without confirming with the user first.

## When to stop early and ask

Stop and ask the user before proceeding when:

- More than 10 issues qualify as unaddressed bugs (likely backlog dump, not real signal).
- A PR's failing CI looks like a real architectural problem rather than a fixable test — a `bug-fixer` agent will spin wheels.
- A dependabot PR is a major version bump with breaking changes — pin or upgrade is a product decision.
