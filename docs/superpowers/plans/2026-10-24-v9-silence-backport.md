# Stable Silence Backport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete stable/v9 behavior for #1943 and #1944 as a fully tested local review candidate.

**Architecture:** Introduce the established per-board silence policy and persisted held-intent store, then adapt stable send boundaries and the existing v9 engine to consume them. Wire the installed UI to the additive API contract. No v10 output architecture or dependency upgrades.

**Tech Stack:** Python/FastAPI/Pydantic, React/TypeScript/i18next, pytest, Vitest and Docker.

**Spec:** `docs/internal/reference/V9_SILENCE_BACKPORT_SPEC.md`

## Global Constraints

- Worktree `/tmp/fiestaboard-v9-silence-backport`, branch `fix/v9-silence-backport`, base `256c9d58d2d13a58cc50429574a06982312b22ea`.
- No push, PR, merge, release, deploy, live-board changes, dependency changes, endpoint removal, or #2323 work.
- Preserve v9 board clients, rendering, pause, UI-only and response compatibility.
- `override_silence` is explicit; v1 `force` never bypasses silence or pause.
- Holding defaults false; newest intent per board, 24-hour TTL, persistence, discard only after successful send.
- Docker-only application/dependency/test execution with isolated data and fake hardware.
- Read repository CLAUDE.md. No applicable checkout .agents skills exist; global Jev skill is advisory only when useful.
- Commit locally without agent attribution trailers. Keep exact test logs in this plan's ignored workspace.

## Review Focus

- Invalid intent or unknown target must not overwrite a valid persisted held message (Task 1/2 tests).
- A paused or offline board at silence exit retains intent for later successful delivery (Task 2 tests).
- Omitted primary id, secondary board and UI-only targets must not share state or send to each other (Task 1/2 tests).
- New explicit writes must supersede old intents only after successful delivery (Task 2 tests).
- UI target switching and failed Show now/Discard requests must not show false success or clear the wrong board (Task 3 tests).

---

### Task 1: Persisted held intentions and shared silence policy

**Files:** Create `src/silence_queue.py`; modify `src/board_guards.py`, `src/config.py`, `src/config_manager.py`, `src/settings/models.py`, `src/settings/routes.py`, `src/service_api/models.py`, `src/service_api/routes.py`; create focused store/policy/status/settings tests and update intentional API goldens only.

**Interfaces:** Produces `HeldSend.text/lines/grid/page/display(..., board_id=...)`, `hold(send)`, `peek(board_id)`, `discard(board_id)->bool`, `preview_text(send)` in `src.silence_queue`; use the established #2257 signatures. Produces `resolve_board_id(board_id)`, `silence_window_end(board_id)`, `silence_verdict(board_id, *, override_silence:bool, hold=None, what=None)->SilenceVerdict` with fields `silenced`, `held`, `ends_at_utc`. Store in the existing isolated data directory. GET /silence-status and DELETE /silence-queue use the spec's additive contract.

- [ ] Write behavior tests first: settings accepts/preserves scoped show_queued_on_exit; store survives reload, newest wins, separate ids, TTL expires and discard is scoped; guard refuses/holds/overrides correctly; status/discard target validation.
- [ ] Run each new test group before production edits; save the observed expected failures.
- [ ] Implement only store, policy, setting and status functionality. Inspect v10 as reference but adapt to existing stable configuration and route conventions. Malformed persisted records must not break startup. Keep test reset helpers in test utilities where possible.
- [ ] Verify targeted store/policy/status/silence-setting suites plus adjacent existing silence tests, Ruff, route/schema goldens, and full Python suite once. Expected GREEN, with any baseline failure explicitly established and reported.
- [ ] Commit the task and write task-1-report.md with exact RED/GREEN evidence and public interface notes.

### Task 2: All manual writes and stable engine delivery

**Files:** Modify `src/board_api/{models,routes}.py`, `src/pages/{models,routes}.py`, `src/displays/{models,routes}.py`, `src/templates/{models,routes}.py`, `src/v1/{models,routes_boards}.py`, `src/settings/{models,routes}.py`, `src/ops/executors.py`, `src/mcp_server.py`, `src/mqtt/commands.py`, `src/main.py` as needed. Add behavior tests for active page, live render, send/force/queue, v1 contracts, MCP/MQTT and held engine delivery. Update intentional API goldens/docs only.

**Interfaces:** Consumes Task 1's store, settings and verdict. Produces additive override_silence request fields on relevant write paths, truthful silenced/held/ends_at_utc/sent response fields, HTTP 202 for accepted held messages, unchanged v1 force meaning. Active-page selection persists but immediate hardware writes defer. DELETE /silence-queue and status from Task 1 remain the UI contract. The stable engine peeks outside silence, after pause/UI-only gates, renders typed intents through stable helpers, and discards only on success.

- [ ] Write behavioral RED tests for every affected send surface using existing fake hardware fixtures; include primary and secondary boards, unknown ids, pause with explicit override, v1 force alone during silence, and invalid payload preserving a prior intent.
- [ ] Run before implementation, save expected failures, then adapt each boundary to the common policy. Preserve each existing endpoint's pause/refusal/preview contract; do not route unrelated debug/diagnostic operations through new UX.
- [ ] Write engine RED tests for persistent intent after restart, board isolation, delivery at silence exit, failed/throttled/paused retry, 24-hour expiry, fresh page rendering and successful explicit send supersession. Implement minimal v9 engine integration.
- [ ] Run full focused manual-send/silence/engine/v1/MCP/MQTT suites, the full Python suite, Ruff and API route/wire contract validation. Expected GREEN. Run no live server or board tests.
- [ ] Commit and write task-2-report.md, including the exact final API shape consumed by Task 3.

### Task 3: Stable silence UI, docs and final integration

**Files:** Add/adapt `web/src/components/silence-notice.tsx`, `live-output-silence-strip.tsx`, `web/src/lib/silence-until.ts`; modify Home/active-page display, Compose, Force Set, page-builder, silence settings, API clients, hooks and all 14 message catalogs as needed. Add focused Vitest and isolated integration checks. Update `docs/features/silence-schedule.md` and relevant API reference. No dependency/lockfile or website-repo changes.

**Interfaces:** Consumes Task 2's request/response fields and Task 1's status/discard contract. All actions target the selected board; client invalidation refreshes the same board after success. Show now uses explicit override_silence; failures retain truthful held state.

- [ ] Write and run RED tests for silence notice/end time, selected-page deferral, Show now and Discard, target switching, failed requests, paused warnings, Compose/Force Set/Live confirmations, out-of-sync suppression and settings persistence.
- [ ] Implement the established v10 UX using stable existing components and APIs. Keep translations, accessible names, keyboard flows and mobile layout intact. Do not import v10 preview/display architecture.
- [ ] Run focused UI suites, then the full web suite, typecheck, production build and scoped ESLint/Prettier. Run isolated browser/e2e checks with fake boards if available; never connect to the live installation. Record remaining UI verification limits precisely.
- [ ] Update user/API docs and local test evidence; commit. Write task-3-report.md.
- [ ] Controller performs independent whole-branch review and fixes material findings with RED/GREEN evidence, then verifies final Python/web suites and the final diff. Leave the candidate local for review.
