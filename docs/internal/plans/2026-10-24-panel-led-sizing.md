# Independent LED panel sizing implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the core implementation. Independent web and content-copy tasks may run through superpowers:dispatching-parallel-agents with exclusive file ownership. Follow test-first verification.

**Goal:** Give TV LED panels a pixel-authoritative surface and character-based authoring, independent of split-flap physical sizing.

**Architecture:** One server geometry resolver determines the effective model, pixel dimensions, font, and character grid. New screen-layout LED panels fit an aspect-matched surface within the existing 256-pixel renderer envelope; old panels retain their authored grids until an explicit conversion. Content conversion creates board-specific copies rather than rewriting shared originals.

**Tech stack:** Python/FastAPI/Pydantic, React/TypeScript, existing FiestaUI LED renderer; Swift/Kotlin clients consume the existing model contract.

**Spec:** `docs/internal/reference/PANEL_PIXEL_GEOMETRY_2026_10.md`, with the user's subsequent approval of distinct LED and split-flap sizing. This plan resolves the previously open direction in favor of pixel authority and square LEDs.

## Decisions and constraints

- `matrix_layout`: `legacy` or `screen`. Missing stored values mean `legacy`; newly created panels select `screen`. Render style stays independent.
- `matrix_font`: `5x7` (Large) or `3x5` (Small), default `5x7`; only screen layout offers text-size changes. Legacy always uses its historical 5x7 face.
- Screen layout uses an aspect-matched integer pixel surface whose longest edge is approximately 192 pixels, never above 256. Reduce the requested aspect to a bounded rational ratio, choose an integer multiplier, then derive cells using FiestaUI glyph metrics. Standard 16:9 is 192×108, 5x7 gives 32×13, 3x5 gives 48×18; portrait 9:16 is 108×192. Reject impossible/extreme shapes before mutating state rather than inflating/clamping the authored grid.
- Inches, calibration, pitch, and presentation mode never change an LED screen-layout page's geometry. Split-flap retains existing autofit behavior.
- Legacy LED models derive their surface from the stored grid, removing the 192×96 minimum. Legacy surfaces exceeding supported raster capacity are surfaced as unsupported; bounded screen layout is the upgrade path, not silently clamped content.
- No generic renderer-capacity increase or physical-LED geometry change is required for the new mode. Larger renderer support remains a separately versioned capability project.
- Existing `null` presentation stays viewer-local. Selecting screen layout in the web editor sets explicit `fill_tv` unless the user chooses another mode. Aspect matching makes uniform contain fill the matching screen; background LEDs are not counted as content.
- Original pages/collections remain unchanged during requested conversion. Copies preserve template text and canvas cell areas; no independent proportional canvas scaling. Only the target board's references move. Copying is explicit in the update request and UI. Failure rolls back reference changes; originals remain recoverable.
- No live deployment or mutation of the user's FiestaPi is part of local implementation verification.

## Review focus

- Existing LED panels must not resize on upgrade, ordinary settings save, or restart.
- Rich cells and canvas layers from a stale frame must not render against a different grid.
- A shared collection, scheduled page, default page, or silence page must not change on other boards during conversion.
- Font/aspect changes must update the runtime profile, authoring charset, model, page picker, and draft preview together.
- Small/large and portrait/ultrawide surfaces must fit renderer bounds and plugin minimum character dimensions without silent clamping.

## Task 1: Canonical geometry and API

Files: create `src/panels/geometry.py`; modify panel models/service/storage/routes/reconcile, `src/outputs/board_profile.py`, `src/fiestaui/__init__.py`; test `tests/test_panel_led_geometry.py` and existing panel suites.

Interfaces: `resolve_panel_geometry(panel, board=None)` returns a dataclass with `rows`, `cols`, `width`, `height`, `font`, `model`; `POST /panels/geometry` resolves a draft without saving, returning `rows`, `cols`, `device_model_spec` and geometry key. Panel responses carry `matrix_layout` and `matrix_font`; public config and frame carry a consistent geometry key for stale-frame protection.

- [x] Write tests for 16:9/portrait/ultrawide, both fonts, inches/calibration independence, legacy preservation, invalid aspect, and create/update/restart parity; observe failure.
- [x] Implement resolver and wire it into model/profile/runtime paths and routes. Validate prospective settings before saving; roll back settings when board update fails.
- [x] Run focused backend tests and record results.

## Task 2: Safe board-specific content copies

Files: create `src/panels/content_resize.py`, tests `tests/test_panel_content_resize.py`; integrate route in Task 1.

Interface: `panel_content_resize(board, target, enabled)` context manager yields a summary of copied pages and collection mappings. `target` is `DeviceDimensions`; when disabled it does nothing. On exceptional exit, restore changed references and remove only newly created copies where safe; originals are never modified. `copy_content: bool = false` is an operation-only update field, never persisted in Panel.

- [x] Test direct/shared collection/scheduled/default/silence references, exact canvas preservation, deduplication, disabled mode, and reference-update failure before implementing.
- [x] Implement copying and board-scoped rewiring using existing storage/service contracts. Explicitly handle temporary overrides or refuse conversion while one is active, before mutation.
- [x] Verify with focused tests; expose actionable failures to the editor.

## Task 3: Web settings and preview

Files: panel API types/client, panel settings, draft preview, viewer/frame hooks and tests; locale copy.

- [x] Test screen layout/text size controls, draft API dimensions, old-server fallback, geometry mismatch blanking, and explicit content-copy choice before implementing.
- [x] Use server draft geometry instead of handwritten 192/96 and glyph-pitch math. Display columns × rows and preview the exact proposed pixel surface. Never pass old frame cells/layers as if they belong to a new grid.
- [x] Show separate sizing controls for split-flap and LED. Existing legacy panels offer explicit screen-layout conversion; save sends `matrix_layout`, `matrix_font`, and `copy_content` only as intended.
- [x] Run focused frontend tests, type checking, and relevant browser tests where available.

## Task 4: Contract verification and documentation

- [x] Verify bounded new models against pinned FiestaUI and native raster algorithms; add shared synthetic fixtures covering edge markers, final-column text, and all-edge canvas bleed.
- [x] Run broader panel, canvas, board-profile, output-delivery, persistence, and frontend regression tests. Use Jev only if a mixed failure batch or consequential unresolved choice triggers it.
- [x] Document modes, conversion/copy behavior, and retained legacy behavior. Obtain fresh whole-change code review; fix important findings with regression tests.
- [x] Commit the reviewed work in this isolated checkout and report evidence and material limitations. Do not deploy to the live Pi.


## Implementation notes and acceptance limits

- Added pending/committed conversion journals and startup recovery; recovery checks for later conflicting panel or reference edits before restoring anything.
- Fresh review found and verified fixes for same-grid pixel changes retaining runtime caches, and recovery overwriting subsequent panel edits. Failed conversion also retains its last displayed frame.
- Combined display-role and geometry changes are refused with a request to save them separately, keeping other panels outside the conversion transaction.
- API preview has a declared response model; missing old fields remain backward compatible. New synthetic fixtures live outside vendored FiestaUI files so their provenance remains intact.
- Web: 245 test files, 2,917 tests passed, 7 skipped; typecheck and changed-file ESLint passed. Thirteen distinct isolated-browser panel tests passed, including pixel delivery, conversion controls, polling and physical split-flap scale. Screenshots were inspected.
- Native: actual Swift and Kotlin core probes passed all six surface/text fixtures. Swift also passed decoded RGBA canvas coverage. The inspected Kotlin checkout ignores canvas layers, an existing feature gap documented in the research note; no native repository was modified.
- Installed-device acceptance and viewing-distance readability remain release validation, not completed claims. No live FiestaPi changes or deployment occurred.

## Final verification

- Full backend command: `FIESTABOARD_OUTPUT_SEED_DIR=/private/tmp/fiestaboard-panel-sizing-seed /tmp/fiestaboard-plugin-venv/bin/python -m pytest -n 4 -q`. Final run: **14,222 passed, 2 skipped, 1 failed** (156.91s). The sole failure was the unchanged timing-sensitive `TestSlowIsNotWedged::test_a_plugin_that_answers_after_the_budget_is_never_quarantined`; it passed in the preceding full run. Re-running all eight tests in `tests/test_plugin_fetch_breaker.py` alone passed. No product code or test was changed for that timing failure. The full parallel run is therefore not reported as unconditionally green.
- The preceding full run found two intentional contract changes needing fixture updates: the added preview route and an MCP test that needed explicit legacy mode for its arbitrary stored grid. Those test files passed all 32 tests after correction; the final full run passed both.
- Python changed-file Ruff and formatting checks, web typecheck/changed-file ESLint, and `git diff --check` passed.
- Branch retained locally; no merge, push, deployment, or live content conversion.
