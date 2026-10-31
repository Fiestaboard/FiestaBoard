# Flexible Pages MVP Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. Track every completed task and verification in the plan-specific ledger. A fresh independent whole-branch review is required before readiness.

**Goal:** Finish the flexible-page backend and an opt-in web block editor while preserving legacy exact-grid pages, Canvas documents, and playback.

**Architecture:** Resume the parked flexible page family. Core dispatches legacy grid rendering or flexible stack layout using shared glyph and Canvas primitives. Device adaptation, playback, and source documents remain distinct; previews show the actual target result and compromises.

**Tech Stack:** Existing Python/FastAPI/Pydantic renderer; React/TypeScript/React Query; existing FiestaUI primitives and Canvas editor. No new packages.

**Spec:** `docs/internal/superpowers/specs/2026-10-28-flexible-pages-design.md`, narrowed and corrected by the compatibility decisions below.

## Global constraints and scope

- The owner authorized end-to-end implementation and feature-branch publication targeting `next` on 2026-10-31. Continue within this scope without repeated task approvals.
- One evolving core branch `codex/flexible-pages-mvp` and draft PR against `next`. Do not push shared `main`/`next`, merge a PR, deploy, or touch live displays.
- Start with verified main `b0c5ec597065de449905e57c52427628bba53edc` and next `5aabc252ab23ec76da4756b94bfca5af4542d301`; reconcile only on this isolated branch. Preserve main's paused beta-publication workflow.
- Parked input is `a4260f343cf4a7ccfb86b89b4ba15e03dbd6cd76`. Preserve its original branch and all unrelated unpublished work.
- No dependency installs or security configuration changes. Run repository code/tests in Docker, using cached dependencies; report unavailable exact environments explicitly. Never reuse live data or credential mounts.
- Existing single/composite/template pages and editor remain supported. No automatic conversion, ID rewrites, or schedule changes.
- MVP: text/canvas/spacer stack blocks, styles, conditions, priorities, import/export, safe reader routing, per-board preview, useful issues, accessible editing, backend correctness and bounded work.
- Optional later: positioned regions, new font families, animation, shared assets, automatic conversion, firmware-native text optimization. Do not imply these exist.
- Core app composites stay in FiestaBoard; generic primitives/font assets belong in FiestaUI only if genuinely required. Existing components should suffice for this MVP.
- Known iOS and TC002 adapter compatibility dependencies require explicit integration evidence; do not fake `device_type`, silently truncate physical frames, or publish unrelated denied commits to satisfy them.

## Review focus

1. Mixed legacy/flexible clients: unsupported documents must not break all page listing or be rewritten by the grid editor (Tasks 2 and 6).
2. Actual adapter output: preserve legacy TC002 mapping and avoid double monochrome conversion; frame support is not implied by width/height (Tasks 3 and 5).
3. Conditional-only/time-only bindings and unavailable Canvas sources: one compilation clock, complete dependencies, honest issues (Task 4).
4. Long legal expanded data and custom glyph dimensions: bounded work and no adjacent-content corruption (Task 4).
5. Native partial failures/selection and editing conflicts: no competing rotation, lost document data, or silently overwritten revision (Tasks 5–7).

## Task 1: Integrate parked history and establish reproducible fixtures

**Files:** merge conflicts in `src/main.py`, `src/pages/routes.py`; existing `tests/layout`, `tests/golden/layout`, `tests/test_native_playlist.py`; this plan and ledger.
**Interfaces:** preserve both native playlist symbols from main and flexible board-render helpers from the parked branch. No new public interface in this task.

- [ ] Record exact ancestry and isolated merge decisions. Import conflicts retain both sides' needed imports; preserve paused beta publishing.
- [ ] Locate cached Python/output seed and web dependencies; record versions and baseline limitations. No installation.
- [ ] Run baseline checks on the reconciled input; distinguish environment failures from source failures.
- [ ] Establish sanitized 32x8, legacy 52x17, physical 52x16, 64x64, 6x22 and mono regression fixtures. Existing snapshots remain recorded/synthetic, never live invented values.
- [ ] Commit the integrated input separately from subsequent fixes; create the evolving draft PR only from reviewed authorized history.

## Task 2: Reader, document, storage and import safety

**Files:** `src/pages/models.py`, `src/pages/storage.py`, `src/pages/share.py`, `src/pages/routes.py`, `src/v1/routes_pages.py`, `web/src/lib/api/pages.ts`, `web/src/lib/api/shared.ts`; corresponding flexible storage/v1/model and document-preservation tests.
**Interfaces:** retain `Page.document_protocol`, `page-revision-v1`, legacy share envelope 1, flexible share envelope 2 and schema 7 as distinct contracts. Preserve opaque fields when replacing block/style/layout values.

- [ ] RED: mixed kinds, unsupported editor routing, unknown nested-field round trips, revision conflict, cross-install target IDs, failed migration backup and rollback fixtures.
- [ ] Reproduce each intended failure with the actual serializer/router/client model before fixes.
- [ ] Implement the smallest reader/import/migration changes preserving old documents. Track iOS typed-reader dependency separately rather than inventing a fake grid.
- [ ] GREEN: focused suites plus affected document/API suites. Commit with observed RED→GREEN evidence.

## Task 3: Deterministic colors, glyphs and frame delivery

**Files:** `src/layout/style.py`, `src/layout/pixels.py`, `src/layout/target.py`, `src/led/page_frame.py`, `src/outputs/display_profile.py`, `src/outputs/plugin_driver.py`, `src/pages/fit.py`; layout/style/pixel tests and `tests/test_led_page_frame.py`.
**Interfaces:** preserve `layout_flexible_page`, full-frame layers and legacy Canvas alpha/luminance semantics. Output capability and physical-surface changes must be explicit and separately tested before being advertised.

- [ ] RED: exact dim RGB, opaque black over a colored page, colored mono full-frame final composition, custom glyph metrics, and unsupported frame receiver.
- [ ] Fix style/cell-to-frame behavior without changing legacy Canvas rules. Resolve each capability seam with a documented contract before updating fit decisions.
- [ ] Keep legacy TC002 virtual mapping intact; a physical-frame adapter path must be evidenced before enabling flexible pages for that model.
- [ ] GREEN: final adapted-frame assertions, existing LED/Canvas/grid fixtures and supported-face tests. Commit.

## Task 4: Clock/dependencies, bounded expansion and render diagnostics

**Files:** `src/layout/refs.py`, `src/layout/expand.py`, `src/layout/measure.py`, `src/layout/engine.py`, `src/layout/fonts.py`, `src/canvas/evaluate.py`, `src/pages/service.py`, `src/main.py`; flexible dedupe/render and Canvas evaluation tests.
**Interfaces:** reuse the expression-aware dependency scanner and existing render-clock mechanism; return issues via the existing layout result, with visible text distinguished from alternate cell projection.

- [ ] RED: raw conditions with two plugin roots; `HOUR(NOW())` boundary invalidation; same-frame clock pinning; missing Canvas source/fallback diagnostics.
- [ ] RED: long plugin text and nested repetition; attempted-but-skipped Canvas repetitions; resolved polygon/text limits; custom glyph rows inconsistent with requested face.
- [ ] Implement bounded work/early termination and complete dependency discovery. Preserve normal outputs and existing fallback semantics.
- [ ] Persist board/native-member issues through the rendering path; avoid describing selected-but-not drawn Canvas as successfully visible.
- [ ] GREEN: focused layout/Canvas/fingerprint suites and aggregate backend checks. Commit.

## Task 5: Native collections and ordinary-render equivalence

**Files:** `src/main.py`, `src/pages/board_render.py`, `src/pages/service.py`, `src/outputs/native_playlist.py`; `tests/test_native_playlist.py`, flexible call-site/transition/preview tests.
**Interfaces:** use `_board_kw`, `_face_kw`, `_delivery_geometry`, `_project_page`/`_page_layers` equivalents for native members; retain immutable layer-aware `NativePlaylistEntry` semantics.

- [ ] RED: flexible native member without page geometry; alternate-face grid member; mixed eligible/ineligible member set; unavailable versus intentional blank; retained per-member issues.
- [ ] Choose one explicit admission policy before mutation. Preserve foreign slots, dwell, selection, silence and current fallback contracts.
- [ ] Expose effective native transition behavior without dropping authored preferences. No host-rotation fallback after partial native synchronization.
- [ ] GREEN: native/ordinary same-target same-snapshot frames, full native suite and affected scheduling tests. Commit.

## Task 6: Complete opt-in block editor and actual-board preview

**Files:** create focused app components under `web/src/components/flexible-page-editor/`; wire `page-editor-shell.tsx`, pages creation/list routes, API types and locale strings; reuse existing Canvas editor and template controls; add component/integration tests beside existing web tests.
**Interfaces:** editor receives a Page document, preserves opaque fields, and saves through existing revision-aware page APIs. Preview uses backend output for selected real boards; no browser layout duplicate implementation.

- [ ] RED: creation/routing separates grid and flexible documents; adding/editing/reordering/removing text/canvas/spacer blocks round-trips the document.
- [ ] RED: page/block styles, conditions/priorities, inherited defaults, Canvas source/fallback preservation, dirty/undo behavior and revision conflict.
- [ ] Build the editor from existing FiestaUI primitives and app-coupled controls; stable block IDs and keyboard operation are required.
- [ ] RED then implement multi-board preview with dimensions, resolved styles, issues/dropped blocks and unsupported targets. Never label computed pixels as hardware read back.
- [ ] GREEN: real-component tests, typecheck, lint, build, keyboard/a11y checks and browser flows where the isolated environment permits. Commit.

## Task 7: Documentation, compatibility acceptance and publication

**Files:** published feature/API docs, internal architecture/readiness notes, focused cross-device/API/browser fixtures, evolving PR description.
**Interfaces:** document actual capabilities and omissions; examples use fake/test data or expressions, never private settings.

- [ ] Verify exact-grid pages, bindings, schedules, Canvas rendering and all supported clients against the accepted compatibility matrix.
- [ ] Run aggregate Python/web checks and relevant integration/browser checks. Record every failure by name and disposition; do not call an unavailable check passed.
- [ ] Obtain fresh independent whole-branch review; address important findings with RED→GREEN tests and relevant aggregate reruns.
- [ ] Publish only the feature branch and maintain one draft PR against `next`. Inspect CI through terminal results and fix recoverable failures.
- [ ] Update readiness gates. Hardware/deployment remains explicitly unverified unless separately authorized. Do not merge, deploy, install dependencies, move shared refs or alter live displays.

## Definition of done

Backend and frontend are complete only when Tasks 1–7 have evidence, the editor saves/reopens correctly, legacy compatibility is preserved, supported final adapters agree with previews, required tests and CI are green, and independent review has no unresolved important issue. Unsupported adapters/clients and unavailable hardware validation are explicit release gates, not hidden exceptions.

## Implementation checkpoint: 2026-10-31

The isolated core branch and draft PR are `codex/flexible-pages-mvp` and
[PR 2395](https://github.com/Fiestaboard/FiestaBoard/pull/2395), targeting `next`.
Shared branches, live content, and the separate UI redesign remain untouched.

Implemented and covered by focused regressions:

- Board-aware native rendering, mixed collection admission, and clearing selection
  when the selected member becomes ineligible.
- Exact dim RGB, opaque black and explicit transparency, mono frame delivery,
  and custom glyph size fallback with a layout warning.
- Shared render clock and complete condition dependencies; bounded Canvas work,
  expression evaluation, substitutions, padding, and numeric precision.
- Failed migration backup refusal and legacy oversized literal preservation.
- The web block editor, explicit routing by document family, revision conflict
  preservation, stable IDs, undo/redo, Canvas drafts, and server preview.
- Target restriction editing that retains unknown fields and unavailable board
  IDs; warnings after target changes and refusal of excluded preview targets.

Executed locally in offline containers: 14,997 backend tests passed with two
skipped; 3,120 frontend tests passed with seven skipped. Subsequent independent
review corrections passed 482 layout/frame tests and 61 preview/API tests.
The target editor passed eight focused tests. These aggregate runs preceded the
last review corrections; required remote CI remains the final combined gate.
Full Python checks, web lint/types/format/build, and documentation checks passed
before the additional browser fixture. The isolated Chromium fixture then passed
keyboard edit/save, horizontal overflow, and accessibility checks at widths of
375 and 1280 pixels, using a fake save API and no backend or live device.

The web environment uses an existing compiled `@fiestaboard/ui` 8.15.0 package
mounted read-only. Its source and feature lock files have matching package URL
and integrity; the extracted artifact was not independently verified against a
cached tarball. Other cached dependency versions are recorded in the execution
ledger; exact lockfile verification belongs to CI. No packages were installed.

Open acceptance gates remain explicit:

- Output dimensions do not prove receipt of full-frame layers. Unsupported
  output writers must be refused rather than silently losing the frame.
- TC002 currently maps a legacy 52 by 17 virtual surface onto 52 by 16 physical
  pixels. A separate adapter change must preserve the legacy transform and
  supply an explicit physical-frame path before physical preview parity is claimed.
- The separate iOS reader requires `device_type` and cannot decode a mixed page
  list containing flexible documents. Its reader and editor routing must be
  updated before this server format is enabled for that client.
- Pixel-visible text and the alternate cell projection need distinct reporting;
  per-board/native-member layout diagnostics need persistent delivery context.
- Full browser/backend integration, final combined CI, and final readiness review
  are incomplete. Hardware delivery has not been exercised or authorized.

This checkpoint is not a completion or release approval.

## Delivery and integration checkpoint

The integration failure at head `d1f5b5473` was reproduced in an isolated
mock-board stack: the new creation button made the old `/New/` selector
ambiguous, and the schedule test depended on a page from another test. The
selector is now exact and the schedule test creates its own page. All seven
smoke tests passed locally, including a new real-backend flexible
create/save/reopen/edit flow that verifies a companion legacy grid is unchanged.
Only the three disposable test containers and their internal network were
removed afterward; existing services were preserved.

Flexible sends now refuse excluded targets and ordinary output writers that
would discard their full-frame layer. Native synchronization checks its own
rich-frame path. Independent review exposed two additional silence paths:
held pages must revalidate targets and writer support on replay, and an
unsupported silence page must use the existing indicator fallback. Three
regressions failed for those behaviors before the fixes; all 57 focused
delivery/silence/queue tests then passed. Review confirmed both findings closed.
The guard proves layer transport, not physical pixel mapping by the adapter.

Preview metadata now distinguishes `cell_projection` from `visible_cells` and
reports the computed surface. The editor labels computed pixel dimensions and
explains that the character fallback is a separate layout. This does not claim
to provide a transcript of only the text visible in the pixel frame.

Remote Quick Checks and the CI aggregate passed for `d1f5b5473`, but the heavy
platform, UI, accessibility, E2E and image-build jobs were skipped because the
PR is a draft. Its integration job failed as described above; replacement CI
is required after publishing these fixes. Do not describe skipped jobs as
executed coverage.

Remaining cross-repository dependencies are unchanged: the iOS `Page` model
requires `device_type` and its local repository has no remote; TC002 still
maps a virtual 52 by 17 surface to 52 by 16. No files in either repository were
changed. Persistent runtime diagnostics and final acceptance remain open.

The combined post-fix checks passed: 15,013 backend tests (two skipped),
3,122 frontend tests (seven skipped), full Python lint/format, frontend
lint/types/format, and documentation checks. The response-golden diff adds
only the intentional flexible preview metadata. A further regression proved
that cell surface metadata must use the resolved display grid; all 49 focused
geometry/render/response checks passed after that correction.

## Runtime diagnostics implementation boundary

Retain the latest engine layout computation per board, with page/member IDs,
revisions, bounded warnings, surface metadata, computation time and whether all
members were processed. Cover ordinary, native, silence and held-page renders.
Expose this as `last_layout_computation` in the board API. It is historical
computation evidence, explicitly not delivery acknowledgement, installed native
playlist state or device selection. Direct API previews/sends do not update
this engine-scoped record. No frames, rendered text or plugin contexts are kept.
Cap members, total issues, path segments and string lengths, reporting omissions.
This smaller reviewed boundary avoids false accepted-state claims across direct
writes, partial native synchronization and asynchronous output callbacks.

Implemented and reviewed this boundary: 284 affected checks and the aggregate
backend suite passed (15,020 tests, two skipped). Inline overrides replace the
historical record with their own identity; native rendering serializes once per
pass and records incomplete computations on early failure. Regression tests
failed for missing history, missing API exposure, primary aliases, stale inline
history and repeated serialization before their fixes. A cap mutation also
proved the member-bound assertion fails. Python style, frontend lint/types/format
and regenerated API documentation checks passed. The record contains eligible
members rendered in that pass; completion does not mean playlist installation.

## Physical-frame admission and adapter dependency

Layer transport alone cannot establish physical fidelity: the TC002 adapter
maps a legacy 52 by 17 model to 52 by 16 by removing a row or centering again.
Implement a generic explicit declaration instead of a model-specific exception:

1. Output API 2 adds optional `physical_frames`, version 1, with per-model
   width/height and ordinary/native modes. API 1 and legacy content stay valid.
   Older cores reject API 2 explicitly. Missing declarations refuse flexible
   pixel delivery; flexible character panels keep the ordinary grid path.
2. Flexible layout alone uses the declared physical surface. Preserve legacy
   model geometry and the alternate character projection grid.
3. Use an immutable physical-frame marker through layer projection and native
   snapshots. Its exact RGB bytes are separate from any monochrome preview
   encoding. Adapters must bypass legacy composition/transforms for this marker;
   layer dimensions alone never establish that a frame is physical.
4. Fit, preview, direct/engine/silence/held delivery and native admission share
   declaration checks. Computed previews use physical dimensions.
5. Verify malformed/version/mode rejection, default refusal, marker retention,
   32 by 8, 52 by 16 and 64 by 64 frames, mono colors and unchanged legacy paths.

Companion adapters must opt in with final payload tests: TC001 ordinary/native,
Pixoo ordinary, and TC002 ordinary/native with squeezing bypassed only for tagged
frames. Prepare isolated patches and evidence; publication outside the core
feature branch requires an identified approved destination. No live install is
part of this work. The iOS mixed-reader patch is independently prepared and
build-verified; its original dirty checkout has no remote.


Physical-frame implementation checkpoint: explicit declarations, tagged RGB,
physical preview dimensions, transition recognition, declaration revisions and
picker admission are implemented. The adapter copies remain isolated outside
this repository. TC002 reproduced row-loss before its marker bypass, then passed
50 affected render/native tests. The exact iOS patch passes 145 package tests
and an isolated unsigned simulator build. Companion publication destinations and
hardware acceptance remain release gates; neither has been performed.


Final compatibility evidence: isolated TC001, Pixoo and TC002 suites pass
140, 309 and 132 tests respectively. The prepared patches apply cleanly to
the preserved original commits. The iOS reader handles mixed libraries and
opaque unsupported projection fields while retaining strict legacy template
geometry; 145 package tests and the unsigned simulator app build pass. No
companion patch has been installed or published. Physical-frame transitions use
still replacement when the adapter cannot mix coordinate spaces safely.

The shared preview marker survives HTTP single, batch, unsaved, send and board
state serialization, and absent markers are omitted for legacy Canvas JSON.
The shared component changes geometry only for a valid marked physical layer;
old cached flexible pixel previews are refreshed. Five Chromium checks pass,
including keyboard save at 375 and 1280 pixels, and real canvas previews at
32 by 8, 52 by 16 and 64 by 64 with no horizontal overflow or accessibility
violations after the entrance animation settles. Frontend aggregate: 3,128
passed, seven skipped; production build, lint, types and formatting pass.
