# Display Plugin Experience Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Preserve existing onboarding changes in this checkout.

**Goal:** Let a newcomer find and set up any available output plugin, and record the complete experience for review.

**Architecture:** One catalog API merges installed, bundled and registry outputs with optional discovery metadata and an explicit registry-load status. A shared catalog browser powers onboarding, Add a display and marketplace filtering; plugin-owned settings/actions remain the setup contract.

**Tech Stack:** Python/FastAPI, React/TypeScript, FiestaUI, pytest, Vitest, Playwright and FFmpeg.

**Spec:** The design below implements the user's approved direction to build plugin support end to end.

## Design and constraints

- All output plugins remain discoverable, without a separate marketplace detour in setup. Keep built-in flows intact.
- Use optional `display` metadata (`category`, `manufacturer`, `models`, `keywords`) in registry entries and plugin manifests. Categories are open labels, not rendering technologies. Older plugins fall back to Other displays and remain searchable by name/description/id.
- Prefer installed/bundled implementations while enriching discovery with registry metadata. Installed model labels remain searchable offline.
- Preserve the array-shaped `/outputs/available` API; add `/outputs/catalog` with outputs and registry status. A missing, malformed or unreadable registry is distinct from an empty valid one.
- Search and category filters are shared across the three entry points. Show at most 12 choices per page, with explicit navigation and a persistent selection summary. Filtering cannot silently change a selected output.
- Installing a selected plugin stays in the setup flow, with retry and back navigation. No new rendering technology is added.
- Show connection verification separately from saving. A passing `test_connection` verifies only the tested configuration; edits, model changes and failed tests invalidate it. Plugins without testing can still save with truthful feedback.
- Support existing Git install as an optional advanced path in the chooser, without leaving onboarding.
- Capture real browser interactions against a production frontend, using clearly identified simulated devices/catalog fixtures. Copy MP4s to Desktop; do not claim real hardware verification.
- Internal plans stay under `docs/internal/plans` to avoid publishing them in the documentation site. Do not commit unrelated pre-existing changes.

## Approaches

The approved recommendation is a shared searchable catalog with metadata-driven categories. Separate fixed category wizard branches would require core edits for every category. Keeping the current flat list would expose plugins but not make a large marketplace navigable.

## Review focus

- Missing/malformed registry must preserve local choices and disclose an incomplete catalog.
- Old plugins and a new category must be reachable without frontend changes.
- Search, pagination and filtering must not lose the current selection.
- Editing settings or a failed test must not retain a verified connection claim.
- Returning from setup and adding a second display must not duplicate installs or delete existing boards.

### Task 1: Catalog contract

**Files:** `src/plugins/sources.py`, `src/outputs/{install,models,routes}.py`, new `src/outputs/catalog_metadata.py`, `tests/test_outputs_install.py`.

**Interfaces:** `list_output_catalog() -> dict` returns `outputs` and `registry_status`; each output optionally carries normalized `display` metadata. `load_registry(..., strict=False)` preserves legacy behavior by default.

- [x] Write API tests for metadata, local precedence, new categories, malformed metadata and registry failure/empty distinction; run red.
- [x] Implement normalization and the additive catalog route; run output install/manifest/source tests green.

### Task 2: Shared discovery

**Files:** API output types; new `web/src/components/displays/display-catalog.tsx`; wizard chooser, add dialog and marketplace; frontend catalogs and relevant tests.

**Interfaces:** `useDisplayCatalog()` supplies catalog query; shared browser controls search/category/pagination while callers render selectable or marketplace cards.

- [x] Write tests for manufacturer/model search, an unknown category, pagination, selected-item persistence, registry retry, and direct marketplace selection in Add display; run red.
- [x] Implement shared browsing and optional Git install; run affected frontend tests and typecheck green.

### Task 3: Plugin setup feedback

**Files:** `step-output-plugin.tsx`, `plugin-board-settings.tsx`, wizard tests and translation catalogs.

- [x] Write tests for no-test save, successful test, editing after success and a failed retest; run red.
- [x] Add truthful connection status and invalidate verification with settings/model changes; retain existing install retries and server-side validation.
- [x] Document author metadata and setup behavior; run full frontend suite, relevant Python suites, lint/typecheck/build, and a final independent review.

### Task 4: Record and deliver

- [x] Record onboarding with a large catalog and plugin setup, recovery, and adding another plugin display. Use production UI and labeled simulated devices.
- [x] Inspect video frames and decode exported MP4s; copy to Desktop and compare file hashes.

## Validation log

Implementation and validation results are appended here as tasks complete.

### Implementation verification

- Backend catalog tests were observed failing before implementation; registry outage,
  malformed entries, metadata precedence, and seeded model names now pass.
- Shared catalog tests cover manufacturer/model search, categories supplied by plugins,
  pagination, retained selections, and incomplete-catalog recovery.
- Independent reviewer found malformed registry-entry handling, missing draft model
  facts, and missing configurable geometry. All three were reproduced with failing
  tests and fixed. Generic setup now renders panel/Note-array dimensions, applies
  detected sizes, and omits geometry for fixed-size models.
- Production browser exercise identified inherited automatic mutation retries.
  A failing test demonstrated two creation requests; generic board creation now
  disables automatic retry, with the same test passing.
- Full frontend suite: **218 files, 2,536 passed, 7 skipped**.
- Full Python suite: **13,528 passed, 2 skipped**. Earlier runs exposed the required
  route inventory/error declaration updates, a first-party response compatibility
  mismatch, and environment/timing issues. The final complete run is green using the
  canonical `/private/tmp` seed path.
- TypeScript, production build, changed-file ESLint, Ruff, formatting, docs front matter,
  docs contract and markdown checks passed. No commits or deployment were made.
- Existing locales receive English fallback copy for the new strings; translated copy
  remains a follow-up. New categories remain discovery labels, not new renderer support.

### Video delivery

Four continuous browser recordings plus a combined 1:54 walkthrough were exported
as H.264 MP4s (1600 × 1000, 25 fps, no audio). The production frontend was exercised
with labeled simulated catalog, installation, and hardware responses. Screenshots
and decoded video frames were inspected; every MP4 decoded without errors.

Delivered to `/Users/jeffre/Desktop/FiestaBoard-Plugin-Experience` and retained in
`/Users/jeffre/Library/Developer/FiestaBoard-Plugin-Experience`. Every Desktop file
matches its source by SHA-256. The temporary demo server and browser were closed.
