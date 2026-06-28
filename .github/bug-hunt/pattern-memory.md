---
last_learned_at: null
---

# Bug-Hunt Pattern Memory

This file is the **positive learning** memory for the bug-hunt loop. The weekly
learner (`.github/workflows/claude-bug-hunt-learn.yml`) mines merged bug-fix PRs
and distills them into the sections below. The daily hunter
(`.github/workflows/claude-bug-hunt.yml`) reads this file at the start of every
run to (a) bias its area selection toward bug-prone modules and (b) seed each
lens subagent with the class-specific checklist of "things that have actually
bitten us."

Maintainers may hand-edit this file. Keep it concise — prune stale or duplicate
patterns. It is the counterpart to `rejected-edits.jsonl` (negative learning):
this file raises recall where bugs really live; the rejection log raises
precision by recording false positives.

> The entry below is a seed example so the hunter has a non-empty memory on day
> one. The learner will replace and extend these as real fixes land.

## Recurring root-cause patterns

Generalized root causes, not one-offs. Each entry: the pattern, where it bit us,
and what to scrutinize.

- **Naive timezone handling.** Scheduling used server-local time instead of the
  configured timezone, so rotations fired at the wrong hour for non-Pacific
  users (issue #1273 → fix #1280). Scrutinize every `datetime.now()` without a
  tz, every naive/aware datetime mix, and every place a user-configured timezone
  string must be honored (schedules, carousels, countdown, page rotation).
  Lens: backend-logic, concurrency-state.

## Bug-prone modules

Areas ranked by how many historical fixes have landed there. The hunter spends
more budget on the top of this list. (Seeded; the learner re-ranks by fix count.)

1. `src/schedules` — timezone/rotation correctness (#1273/#1280).

## Per-lens checklists

Class-specific checks the learner accumulates. Injected into each lens
subagent's prompt.

### backend-logic & edge cases
- Datetime/timezone conversions honor the user-configured TZ, not server local.

### error/exception handling
- _(none yet)_

### concurrency & shared state
- _(none yet)_

### Python↔TS API contract drift
- _(none yet)_

### security & input validation
- _(none yet)_
