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
- [ ] Persist board/native-member issues through the rendering path; avoid describing selected-but-undrawn Canvas as successfully visible.
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
**Interfaces:** editor receives a Page document, preserves opaque fields, and saves through existing revision-aware page APIs. Preview uses backend output for selected real boards; no browser layout reimplementation.

- [ ] RED: creation/routing separates grid and flexible documents; adding/editing/reordering/removing text/canvas/spacer blocks round-trips the document.
- [ ] RED: page/block styles, conditions/priorities, inherited defaults, Canvas source/fallback preservation, dirty/undo behavior and revision conflict.
- [ ] Build the editor from existing FiestaUI primitives and app-coupled controls; stable block IDs and keyboard operation are required.
- [ ] RED then implement multi-board preview with dimensions, resolved styles, issues/dropped blocks and unsupported targets. Never label computed pixels as hardware readback.
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
