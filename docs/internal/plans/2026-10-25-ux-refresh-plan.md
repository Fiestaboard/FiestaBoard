# FiestaBoard UX Refresh Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development. Work only within the assigned scope; no additional subagents.

**Goal:** Address all nine recorded UX issues with consistent, responsive app layouts.

**Architecture:** App-owned composites using existing FiestaUI primitives and existing APIs. Shared display compatibility and route shells preserve saved data and navigation behavior.

**Tech Stack:** React, TypeScript, React Router, TanStack Query, FiestaUI 8.14.0, Vitest, Docker.

**Spec:** `docs/internal/plans/2026-10-25-ux-refresh-design.md`

## Global Constraints

- Work on `codex/ux-refresh-v10` in the current checkout; preserve the prior user's stash.
- Docker-only dependencies/tests/runtime. Test container `fiestaboard-ux-web-test`, workdir `/app`; root initializes dependencies. Run `docker exec fiestaboard-ux-web-test npm run test:run -- <files>`.
- No edits to sibling repos, deployment, live-device writes, or schema migrations.
- Existing primitives from @fiestaboard/ui; app-owned composites may configure layout through supported props/classes.
- Root owns locale integration. Workers supply exact locale key/value additions in their report; avoid concurrent edits to shared locale files. Existing strings may be reused.
- Workers own their listed files/tests only. Root integrates route-file conflicts and docs. No git commits by workers while others edit the shared checkout.
- Behavioral changes get focused regression tests with observed red/green evidence. Pure spacing does not need implementation-mirroring tests. Root runs aggregate checks.

## Review Focus

- Editor mode switching must not lose rich-text/canvas draft state or bypass save/navigation guards (Task 4).
- Route board A differs from global board B: silence reads and updates A (Task 3).
- Missing/malformed source must not become FiestaBoard or Community by guesswork (Task 1).
- Orphan page shapes and plugin/LED displays remain reachable and accurately previewed (Task 2).
- Popover and selectors support keyboard/reduced motion, mobile scrolling and focus return (Tasks 1, 3, 4).

### Task 1: Marketplaces and transition controls

**Files:** display-catalog.tsx, display-marketplace.tsx, display-transition.tsx, integrations._index.tsx, new app-owned marketplace/provenance/transition-preview composites/helpers, corresponding tests.
**Interfaces:** existing BoardInstance, RegistryEntry.repository, PluginInfo.source.repository_url; preserve DisplayTransition props and display-catalog onboarding callers. Do not edit displays.$boardId.tsx (Task 3).

- [ ] Add focused tests for Git disclosure, known/unknown provenance and selector/preview behavior without device sends.
- [ ] Run tests and confirm intended failure.
- [ ] Compose compact catalog controls, secondary Git dialogs, bounded integration browsing, provenance badges, compact selector with truthful native/LED preview and unavailable plugin messaging.
- [ ] Verify marketplace/install/update, legacy transition values, cloud/device limits, speed semantics and keyboard/reduced-motion behavior.
- [ ] Report files, locale additions, exact test evidence and limitations for independent review.

### Task 2: Pages and Collections libraries

**Files:** pages._index.tsx, collections.tsx, new collections route/components/helpers, page-grid-selector.tsx only as needed for shared previews, active-page-display.tsx collection link, focused tests. Root owns app/routes.ts integration.
**Interfaces:** existing pagesCompatibleWithBoard and model-aware preview helpers; preserve CollectionForm and interval utility exports used by tests. New routes /collections, /collections/new, /collections/:collectionId.

- [ ] Add tests for actual-display/LED filtering, All/orphan reachability, tile/list persistence, collection route save and custom durations.
- [ ] Observe failures for missing behavior.
- [ ] Consolidate Pages controls; use configured display compatibility rather than fixed device-type tabs.
- [ ] Implement Collections tile/list and bounded model-aware card stacks based on the video motif; list avoids previews.
- [ ] Implement full-page collection creation/editing with shared SectionShell conventions and accessible reorder controls; retain rules/validation/errors/deletion behavior.
- [ ] Verify targeted tests and report route registrations, locale additions, evidence and limitations.

### Task 3: Settings, display page organization, account popup

**Files:** settings.tsx, displays.$boardId.tsx, profile.tsx, sidebar-settings-menu.tsx, settings/animation-settings.tsx, settings/silence-schedule.tsx, related grouping components and tests. Do not edit display-transition.tsx (Task 1).
**Interfaces:** preserve DisplayTransition props, SilenceSchedule supports explicit boardId with backward-compatible currentBoard fallback. Global preview settings retain their API scope.

- [ ] Add tests for route-board silence scope, account destination/popover keyboard behavior and preview-speed persistence.
- [ ] Observe intended failures.
- [ ] Create coherent compact General groups, clarify app-preview settings and improve radio semantics; relocate silence with explicit boardId and maintain legacy discoverability.
- [ ] Organize display details using Overview/Settings/Playback or equivalent clear tabs, exposing preview and per-display controls without one long form. Preserve panel controls/loading/not-found behavior.
- [ ] Rebuild account popover with identity/account, theme, settings/about, version/update and sign-out; keep mobile inline behavior.
- [ ] Verify targeted tests; report locale additions and independent review evidence.

### Task 4: Focused page editor

**Files:** page-builder.tsx, page-editor-shell.tsx if needed, canvas editor focus handling if needed, editor tests.
**Interfaces:** preserve template/canvas state and existing save/live/retarget API. Canvas marker activation changes mode and then focuses selected canvas.

- [ ] Test Text/Canvases switching preserves unsaved content and save payload; marker activation reaches canvas and unsupported-target notices remain visible.
- [ ] Observe intended failures.
- [ ] Introduce focused editing modes with persistent shared actions/preview; reduce nested scroll and accommodate phone/desktop widths.
- [ ] Verify existing canvas/live/retarget/navigation tests plus new mode tests.
- [ ] Report locale additions, exact evidence and limitations.

### Task 5: Integration and review

**Files:** app/routes.ts, locale files, documentation; task-owned files only for reviewed fixes.

- [ ] Integrate locale keys and route registrations without losing existing keys.
- [ ] Independent task reviews, then focused fix loops.
- [ ] Run typecheck, lint for changed files, relevant tests and broader web suite once stable.
- [ ] Inspect responsive screens and keyboard paths in isolated preview; fix observed issues.
- [ ] Astra whole-change review, resolve material findings, report verified results and any remaining limitations.

## Implementation and review result

Tasks 1–5 are implemented on `codex/ux-refresh-v10`, based on `2ced809c8` (v10.0.0). The user's final workflow preference was “Implement, then review the result.” GPT-6.1 Sol workers handled implementation and localization; Astra reviewed the design and final integration.

The implementation includes compact display and integration catalogs, Community provenance, replayable transition previews, display detail tabs, configured-display page filtering, Collections tile/list views and full detail routes, focused Text/Canvases editing, grouped settings, and the account popover. The Collections stack follows the CardStack motif in the sibling media project's `studio/src/videos/h4-collections/helpkit.tsx`. All new copy was integrated into English and 13 other supported locales.

Independent review fixes cover preview cache identity when switching displays, uninterrupted LED Replay, AI navigation to moved settings, and visible AI page updates with dirty-draft preservation. Astra's scoped re-review found no outstanding material issue. Subsequent phone-width visual QA identified a transition grid sizing issue; the two-file CSS fix passed 10 focused tests, lint and a fresh build, then was visually confirmed at 390×844 in Safari.

Validation on the integrated implementation: Docker web suite 3,014 passed / 7 skipped across 255 files; Collections Chromium regression 11 passed; TypeScript, production build, changed-file ESLint and `git diff --check` passed. Manual Safari checks covered desktop and phone layouts, dark/light appearance, collection detail, focused editing, catalogs, settings/account controls and transition Replay. Native transition previews illustrate ordering; third-party transition plugins explicitly report when no browser preview is available.

Review runtime: `http://localhost:4820`, isolated sample data and localhost-only output destinations. Existing running instances were not deployed over. Prior checkout changes remain in stash `pre-main-v10-switch-2026-10-25`. Changes are uncommitted because this session's filesystem policy denied writing `.git/index.lock`.

## User review revision

The user rejected the desktop editor's side-by-side template and preview. Restored a single vertical column at every breakpoint: active Text/Canvases surface first, shared preview underneath. Kept the focused mode switching and mobile preview toggle. Pages received a smaller visual correction: filter/count grouped separately from view/actions, quieter Import, brighter card names, thinner borders and loading placeholders matching the actual cards. Build, scoped lint and editor/library regression checks passed; Safari confirmed the full-width template and preview below it.

## Per-display scheduling follow-up

The user requested that scheduling settings live entirely on each display, with no global-defaults UI. Removed the Scheduling tab from Settings and moved silence hours, schedule re-enable behavior and update intervals into each display's Playback tab. Settings schema 8 copies existing scheduling values onto existing boards; newly added boards receive independent defaults. Runtime refresh timing and state reads use those board fields, and changes take effect without restarting. Legacy links and AI navigation resolve the relevant display. Virtual displays hide physical board state-read controls; Vestaboard displays show the applicable local or cloud control.

Astra reviewed migration, compatibility and runtime isolation. Fresh affected backend suites passed 1,471 tests. The full backend run's remaining 19 failures were each reproduced against original HEAD in the same test image (seed pins, catalog fixtures and updater mocks/dependencies); none is attributable to this change. Web validation passed 3,027 tests with 7 skipped, plus 49 focused settings tests after the final visibility adjustment. TypeScript, lint and production build passed. Safari and API checks confirmed independent 45/90-second intervals and distinct re-enable behavior on two virtual displays, and the removed Settings tab.

## Canvas QA fixtures

Added four virtual displays in the isolated localhost:4820 environment: landscape, portrait, square and a dense 3×5-font display. Eight sample pages and four rotating collections cover text flow, transparent overlap, full bleed, clipping, pixel scaling, eight canvases, expression-driven shapes and a missing-plugin source with fallback artwork. Each sample produced its expected canvas layers; the missing-source sample intentionally reports a reference issue while rendering its fallback. Safari verified canvas selection, pixel painting and saving without changing another canvas, plus library stack previews. The repeatable seed script and fixture manifest are kept in the ignored task scratch directory; they do not change real display data.

The user's intermittent canvas-loading report exposed two classes of defect. Canvas-only preview responses and failed requests could drop a queued edit; completion now drains the pending preview using the latest canvas and board state. Shape-only and source-backed canvases also misleadingly opened a blank Draw pad; they now start on their appropriate tool, with a pixel-layer explanation when Draw is chosen. Stable editor identities and retained visited editors preserve unfinished JSON and tool state across tab/canvas switches and renames, while deletion retires the removed editor's state. Regression tests reproduced the failures before fixes. Astra's scoped review found no material issue; Safari confirmed the shape editor opens correctly at phone width.

The user also requested a balanced Appearance and accessibility section. Theme and reduced motion now share a compact row; Graphics and previews owns board/site animation controls alongside Flip speed and its demonstration. The columns stack on mobile. Safari verified desktop and 390×844 layouts, and all new copy is translated in 14 locales.

Final combined web verification after these fixes: 3,046 passed / 7 skipped across 256 files; TypeScript, production build, scoped lint, locale formatting and `git diff --check` passed. The isolated preview was rebuilt and restarted with these changes.

## Display-plugin updates before setup

The user identified that a Pixoo owner stuck before saving a board still needs discovery/connection fixes. Removed the saved-board usage gate from installed output-plugin update checks. Installed display plugins are eligible whether used or unused; disabled data-plugin behavior, the global auto-update preference, compatibility holds and rollback remain unchanged. Regression cases failed before the fix; 294 affected plugin/update tests passed afterward, with lint and formatting clean. Port troubleshooting documentation distinguishes the current port-80 discovery probe from explicit endpoint support and older installed plugin code.

## Consolidated enhancement PR

The user requested one PR containing the UX refresh, follow-up fixes, per-board scheduling, display-plugin update eligibility and beta-publication pause, then selected stable `10.1.1` as its release target. PR #2368 is expanded instead of opening a second PR. The existing version-sync tool prepares all four version files at `10.1.0`; the PR uses `enhancement` plus `patch`, without `minor` or `major`, so the standard post-merge release workflow produces `10.1.1`. Automatic beta publication remains disabled. This prepares the release; creating the PR does not publish it or update deployed installations.
