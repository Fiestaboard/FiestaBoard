# Test Coverage

This document describes the test suite for the FiestaBoard web layer, covering
both Playwright E2E tests and Vitest unit tests.

> **Counts refreshed 2026-09-03** — 74 Playwright spec files (48 top-level,
> 26 under `regression/`), 134 Vitest files. Counts drift; the invariants
> below are enforced by `tests/test_e2e_spec_reachability.py`, which fails CI
> if any spec is unreachable by every workflow.

---

## E2E Tests (Playwright)

Tests exercise the full stack against the unified container:

```
Playwright browser → nginx → React Router v7 + Vite UI
                           → FastAPI backend → mock Vestaboard Local/Cloud API
```

### Which CI job runs which specs

This is the part that matters most: a spec no job runs reads as coverage while
asserting nothing. Every one of these jobs runs on **`pull_request` and
`merge_group`**, so the merge queue gates on the merged result, not just the PR
head.

| Job                                                     | Specs                                              | Why it's separate                                                                                |
| ------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `e2e-tests` (ci.yml)                                    | whole suite except the opt-in specs below           | 4 workers, 4 isolated backends                                                                     |
| `ai-mcp-e2e-tests` (ci.yml)                             | `ai.spec.ts`, `mcp.spec.ts` — `RUN_AI_TESTS=1`      | Needs the `mock-llm` sidecar; `ai.spec.ts` writes global `/settings/ai` state                      |
| `auth-e2e-tests` (ci.yml)                               | `auth.spec.ts` — `RUN_AUTH_TESTS=1`                 | Needs a container booted with `FIESTABOARD_AUTH_ENABLED=true`                                      |
| `ingress-e2e-tests` (ci.yml)                            | `ingress.spec.ts` — `RUN_INGRESS_TESTS=1`           | Needs the HA Ingress nginx simulator in front of a production bundle                               |
| `integration-tests` (integration-tests.yml)             | `integration.spec.ts` on PRs, whole suite in the queue | Smoke subset early, full suite as the last gate                                                 |
| _not run in CI_                                         | `generate-screenshots.spec.ts`, `draw-mode-demo.spec.ts` | Authoring tools that produce docs assets, not tests — allowlisted in the reachability guard |

The opt-in `RUN_*` flags live in `web/playwright.config.ts`. Adding a new flag
without a job that sets it fails `tests/test_e2e_spec_reachability.py`.

### Core flows and API

| File                        | Area                | What's covered                                                                                          |
| --------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------- |
| `integration.spec.ts`       | Core flows          | Infrastructure health, setup wizard, navigation, page and schedule management                            |
| `api.spec.ts`               | Backend API         | Version/config, settings, pages, schedules, plugins, templates, displays, debug                          |
| `api-extended.spec.ts`      | Backend API         | Deeper config/pages/schedules/plugins/settings/templates coverage                                        |
| `navigation.spec.ts`        | Navigation          | Mobile hamburger menu, sidebar links, theme toggle, version display                                      |
| `dashboard.spec.ts`         | Dashboard           | Board display, active page name, manual-mode badge                                                       |
| `a11y.spec.ts`              | Accessibility       | axe-core scans of the main routes                                                                        |
| `localization.spec.ts`      | i18n                | Locale switching, persistence across navigation and reload, mobile menu                                  |
| `error-handling.spec.ts`    | Error handling      | 404s, invalid POST/template data, API error states, graceful degradation                                 |
| `error-recovery.spec.ts`    | Error recovery      | Board unreachable, config reset, invalid data, network simulation                                        |
| `mobile-critical-flows.spec.ts` | Mobile          | Navigation, dashboard, pages, integrations, schedule at phone viewports                                  |

### Pages, schedules and the editor

| File                          | Area           | What's covered                                                                             |
| ----------------------------- | -------------- | -------------------------------------------------------------------------------------------- |
| `pages-crud.spec.ts`          | Pages          | Create, edit, delete via the UI                                                               |
| `page-builder.spec.ts`        | Page builder   | Visual builder create/edit, Sync from Board                                                   |
| `page-device-switch.spec.ts`  | Page creator   | Flagship → Note switching before save; size locked once saved                                 |
| `draw-mode.spec.ts`           | Page builder   | Pencil draw mode strokes and template round-trip                                              |
| `transition-pickers.spec.ts`  | Transitions    | Transition picker UI on pages and settings                                                    |
| `schedule-crud.spec.ts`       | Schedules      | Create with page/time/day selection, delete                                                   |
| `schedule-management.spec.ts` | Schedules      | Toggle, form interactions, validation, calendar/list views, day patterns                      |
| `schedule-midnight.spec.ts`   | Schedules      | Midnight-rollover boundary behavior                                                           |
| `calendar-alignment.spec.ts`  | Schedule UI    | Time-gutter alignment with the hour grid, desktop and mobile                                  |

### Boards, devices and output

| File                               | Area                   | What's covered                                                                                                                                                                     |
| ---------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `multi-board.spec.ts`              | Multi-board            | Board card display, board CRUD, wizard board type/color picker, cross-feature config                                                                                                   |
| `multi-board-schedule.spec.ts`     | Multi-board scheduling | Board selector, schedule mode toggle, per-board CRUD, filtering by `board_id`                                                                                                          |
| `multi-board-output.spec.ts`       | Multi-board output     | Two boards on real mock connections (ports 7000/7001): manual and scheduled sends land on the right hardware, cross-board leak checks, per-board pause and schedule-mode isolation      |
| `multi-board-mixed.spec.ts`        | Mixed-device fleet     | Flagship (6×22) + Note (3×15) in one refresh, correctly sized per device, no cross-device leakage                                                                                       |
| `board-switch-ux.spec.ts`          | Board selector         | Switching boards fully swaps the view                                                                                                                                                  |
| `board-send-path.spec.ts`          | Send path              | End-to-end send path from UI action to board hardware                                                                                                                                  |
| `board-discovery-offline.spec.ts`  | Discovery & offline    | Board scan, connection test online/offline/missing creds, per-board active-page resolution, offline send handling                                                                       |
| `mock-board.spec.ts`               | Mock server            | Character-code validation, text-mode encoding, mock state                                                                                                                              |
| `code62-glyph.spec.ts`             | Character code 62      | Per-board heart/degree glyph setting, including the setup wizard                                                                                                                       |
| `note-pages.spec.ts`               | Note pages             | Note (3×15) API CRUD, UI creation, 3-line editor, preview dimensions, send with encoding verification, heart/degree handling                                                            |
| `note-multiboard-extended.spec.ts` | Note & multi-board     | Device-type mismatch, 3×15 grid enforcement, one board offline, per-board schedule isolation                                                                                            |
| `note-array-output.spec.ts`        | Note-array output      | Cloud-API hardware layer: solo array installs, every geometry class, mixed fleet in one refresh, array pause isolation                                                                  |
| `note-array-local.spec.ts`         | Note-array output      | Local-API per-tile fan-out for arrays                                                                                                                                                  |
| `note-array-add-ux.spec.ts`        | Note arrays            | Adding a Note Array board through the UI                                                                                                                                               |
| `panel.spec.ts`                    | FiestaPanel            | The public read-only `/panel/{id}` viewer surface                                                                                                                                      |

### Plugins and integrations

| File                            | Area                | What's covered                                                                                        |
| ------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------- |
| `integrations.spec.ts`          | Plugin UI           | Installed + Marketplace tabs, plugin cards, Add-from-Git dialog, Check for Updates                       |
| `plugin-management.spec.ts`     | Plugin management   | Listing by category, enable/disable via API + UI, config sheet, API-key field, status badge               |
| `plugin-detail.spec.ts`         | Plugin detail       | `/integrations/[pluginId]` navigation, metadata, install button, README, unknown-plugin error state       |
| `plugin-board-previews.spec.ts` | Plugin previews     | Manifest `teaser`/`previews` rendering as live split-flap boards                                         |
| `home-assistant-controls.spec.ts` | HA integration    | HA REST round-trips: schedule switch, active page, refresh/blank, send message, sensors, transition style  |
| `home-assistant-discovery.spec.ts` | HA integration   | FiestaBoard entities discoverable in Home Assistant via MQTT                                             |

### Settings, auth, AI and infrastructure

| File                   | Area          | What's covered                                                                                                                       |
| ---------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `settings.spec.ts`     | Settings      | Settings page loads with all sections; navigation to integrations                                                                       |
| `settings-full.spec.ts`| Settings      | Timezone picker, refresh interval, output target, board type, service control, silence schedule, wizard rerun, debug tools, system info  |
| `auth.spec.ts`         | Auth          | First-run setup, sign-in valid/invalid, remember-me cookie, logout, 401/409 protected routes, `redirect=` param. `RUN_AUTH_TESTS=1`      |
| `ai.spec.ts`           | AI            | `/settings/ai` round-trip + key masking, `/settings/ai/test`, `/pages/ai/context`, `/pages/ai/generate` happy and error paths. `RUN_AI_TESTS=1` |
| `mcp.spec.ts`          | MCP HTTP      | `/api/mcp/` mount smoke, Streamable-HTTP initialize handshake, `tools/list` catalog, `tools/call list_pages`, prompts, resources, unknown-tool error. `RUN_AI_TESTS=1` |
| `ingress.spec.ts`      | HA Ingress    | The production bundle behind the HA Ingress path-rewrite proxy. `RUN_INGRESS_TESTS=1`                                                    |

### `regression/` — UX-tree gap suite

26 specs generated from `.claude/ux-tree.json` and then filled in with real
assertions. They are named for the UX node they cover
(`regression: pages.edit`, `regression: settings.hardware`, …) and run in the
main `e2e-tests` job alongside everything else:

`board-preview-fit`, `collections`, `dashboard`, `debug`,
`integrations-installed`, `integrations-marketplace-detail`,
`integrations-plugin-config`, `login`, `multi-board-e2e`, `note-arrays`,
`offline`, `pages-edit`, `pages-import-dialog`, `pages-list`, `pages-new`,
`picks`, `schedule-calendar`, `schedule-delete-confirm`, `schedule-form`,
`schedule-list`, `schedule-toolbar`, `settings-advanced`,
`settings-behavior-integrations`, `settings-general-account`,
`settings-hardware-network`, `settings-system`.

A handful of individual cases are still `test.fixme` where the UI affordance
does not exist yet (for example a Factory Reset card in `settings-system`).
Grep for `test.fixme` for the current list — that grep is the source of truth,
not this document.

### Authoring tools (not tests)

| File                           | What it does                                                     |
| ------------------------------ | ------------------------------------------------------------------ |
| `generate-screenshots.spec.ts` | Regenerates documentation screenshots on demand                    |
| `draw-mode-demo.spec.ts`       | Records the draw-mode demo asset; excluded even in local runs      |

---

## Unit Tests (Vitest)

Unit tests run in Node with jsdom + MSW mocks for API calls. There are 134
files under `web/src/__tests__/`. An exhaustive table here rotted within a
release and is not worth maintaining by hand — list them with:

```bash
ls web/src/__tests__
```

They cover `lib/` contracts (`api.ts`, `board-colors.ts`, `schedule-calendar.ts`,
`github.ts`, `preview-cache.ts`, `setup-detection.ts`, timezone and TipTap
helpers) and component behavior (board display, settings sections, schedule
forms, navigation sidebar, pickers, theme and locale switching).

---

## Running the Tests

### E2E Tests (Playwright)

```bash
# Start the dev container
docker compose -f docker-compose.dev.yml up -d

# Run the suite against it
cd web && npx playwright test

# Run a single spec
cd web && npx playwright test tests/integrations.spec.ts

# Run an opt-in spec (needs the matching sidecar — see the CI job table)
cd web && RUN_AI_TESTS=1 npx playwright test tests/mcp.spec.ts
```

### Unit Tests (Vitest)

```bash
docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"
```

---

## Architecture

```
┌────────────┐    ┌───────────────────────────────┐    ┌──────────────────┐
│ Playwright │───▶│ FiestaBoard container         │───▶│ mock Vestaboard  │
│ (browser)  │    │ nginx → RRv7/Vite UI + FastAPI│    │ Local/Cloud API  │
└────────────┘    └───────────────────────────────┘    └──────────────────┘
```

The mock servers (`integration-tests/mock-board`, `integration-tests/mock-cloud`,
`integration-tests/mock-llm`) simulate the Vestaboard Local API, the Vestaboard
Cloud API, and an OpenAI-compatible LLM, so no real hardware or API key is
needed for any test in this suite.
