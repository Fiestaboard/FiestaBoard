# Flexible editor usability implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task.

**Goal:** Resolve the rendered Astra review defects without changing legacy documents or the shared design system.

**Architecture:** Give the flexible route explicit scroll ownership, retain one document state and preview, and make pending edits and diagnostics actionable. Preserve the existing semantic JSON, Canvas and exact-grid contracts.

**Tech Stack:** React, FiestaUI 8.15, TanStack Query, Vitest, Playwright.

**Spec:** The dedicated rendered review of PR #2395 at `1a94b34b`, with desktop clipping as the leading defect. Jeffrey delegated bounded product decisions to independent Astra review.

## Global constraints

- Work only on `codex/flexible-pages-mvp`, targeting `next`; no merge, deployment or live data.
- No dependency installs, shared UI changes, legacy editor redesign or companion publication.
- Preserve opaque document fields, invalid drafts, revisions and rollback compatibility.
- Use existing cached isolated containers; distinguish mocked API interactions from actual integration and hardware.

## Design choices

A scroll-only patch would restore access but leave the edit/preview loop disconnected. A broad editor rewrite would risk unrelated behavior. Use a bounded workspace change: a user-scrollable flexible body, persistent save/status actions, adjacent desktop preview and reachable mobile preview, with repair links and compact block actions. Astra challenges this approach before implementation and re-reviews rendered results.

## Review focus

- Invalid drafts across tabs, reorder, remove, undo and external document refresh.
- Numeric intermediate values, blur, save while focused and undo/redo.
- Warning links after reorder and unknown paths; focus must stay visible below sticky actions.
- Desktop wheel/PageDown and mobile viewport/zoom with large content.
- Save failures, repeated save and no-ID drafts; no false persisted state.

## Tasks

- [x] Add a composed-shell browser regression using ordinary wheel scrolling and prove failure. Add scroll ownership and verify lower content is reachable.
- [x] Add regression tests for hidden JSON recovery, numeric replacement and truthful new-page status. Prove failures, then implement bounded fixes.
- [x] Add actionable issue-link and preview-reachability regressions. Implement connected preview/actions, explicit warning labels, and safe focus movement.
- [x] Verify relevant unit/browser checks, frontend aggregate, lint/types/format/build and repository checks. Re-review desktop/mobile light/dark with Astra; fix findings and preserve before/after screenshots.
- Delivery gate: commit/push to existing PR, verify exact-head CI terminal results, prepare supported screenshot attachments and report remaining integration/hardware gaps. Record publication and CI results in the PR rather than creating another documentation-only head after every run.

## Rendered review decisions

Two independent Astra passes reviewed task flow and visual design, then reconciled the findings. The bounded beta direction is approved in the observed desktop/mobile light/dark states. Follow-up failures were reproduced before fixing offscreen save errors, mobile action persistence, short-phone repair focus, and duration validation.

The mobile height override lives in the app-owned section shell and is enabled only for flexible editing below the existing bounded-layout breakpoint. It uses the shared header-height variable. The workspace owns scrolling; save errors remain inside persistent actions, and repair/preview links measure the toolbar to reveal their targets below it.

Browser fixtures use actual production components with synthetic API responses and sanitized data. Separate review captures include offline engine frames at representative resolutions. Neither proves authenticated transport or physical hardware delivery. Native mobile keyboards, broader locale/font scaling, and full screen-reader testing remain acceptance follow-ups. Remembering the last edited block and guided style presets are optional polish outside this repair.

## Local verification

- Frontend aggregate: 269 files passed, 3,136 tests passed and 7 skipped.
- Eleven committed Chromium checks passed, including keyboard save, accessibility, representative pixel dimensions, ordinary desktop scrolling, persistent errors/actions and short-phone JSON focus.
- Seventeen separate sanitized review scenarios passed, including light/dark, cancellation, in-flight save, retry, legacy editor and engine snapshot previews.
- Web lint, typecheck, formatting and production build passed. Documentation checks passed.
- An intermediate full-page screenshot altered scrolling between pointer-down and pointer-up in one review fixture. Event tracing proved the ordinary interaction and composed page shell both worked. A viewport-only capture corrected the harness; no product workaround was added.
