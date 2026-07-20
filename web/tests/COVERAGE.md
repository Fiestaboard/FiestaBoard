# Test Coverage

This document describes the full test suite for the FiestaBoard web layer,
covering both Playwright E2E tests and Vitest unit tests.

---

## E2E Tests (Playwright)

Tests exercise the full stack:

```
Playwright browser → Next.js UI → FastAPI backend → Mock Vestaboard API
```

### Playwright Spec Files (30 files)

| File                               | Area                      | What's Covered                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------- | ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ai.spec.ts`                       | AI providers + generation | `/settings/ai` round-trip + api_key masking, `/settings/ai/test` against a mock OpenAI server (happy path + draft override + auth error), `/pages/ai/context` debug payload, `/pages/ai/generate` happy path / disabled / bad JSON / missing template / upstream auth error, Settings → Integrations tab renders AI Settings. Gated behind `RUN_AI_TESTS=1`; runs in the `ai-mcp-e2e-tests` CI job against `integration-tests/mock-llm/server.py`. |
| `api.spec.ts`                      | Backend API               | Core endpoint contracts: version, config, settings CRUD, pages CRUD, schedules CRUD, plugins, template validation, displays, debug                                                                                                                                                                                                                                                                                                                 |
| `api-extended.spec.ts`             | Backend API               | Deeper API coverage: full config, board config test, page preview/send/batch, schedule active/validate/default/enable, plugin config/variables, settings transitions/active-page/board, template render, service start/stop                                                                                                                                                                                                                        |
| `auth.spec.ts`                     | Authentication            | First-run setup form, sign-in form (valid + invalid creds), remember-me cookie behavior, logout, protected-route 401 / 409 setup-required, `/profile` redirect, `redirect=` query param. Gated behind `RUN_AUTH_TESTS=1` because it requires a container booted with `FIESTABOARD_AUTH_ENABLED=true`. Runs in its own CI job (`auth-e2e-tests`); the main e2e job runs with auth disabled.                                                         |
| `mcp.spec.ts`                      | MCP HTTP                  | Smoke that `/api/mcp/` is mounted, MCP Streamable-HTTP initialize handshake, `tools/list` returns the expected FiestaBoard tool catalog, `tools/call list_pages` returns valid JSON, unknown-tool error path. Catches "MCP broke at the HTTP boundary" regressions that `tests/test_mcp_server.py` can't see. Gated behind `RUN_AI_TESTS=1`.                                                                                                       |
| `board-discovery-offline.spec.ts`  | Board discovery & offline | Board scan/discovery endpoint, connection test (online/offline/missing creds), per-board schedule active page resolution, per-board schedule enable/disable independence, Note template rendering dimensions, offline board send handling, multi-board state independence                                                                                                                                                                          |
| `calendar-alignment.spec.ts`       | Schedule UI               | Time gutter label alignment with hour grid, desktop + mobile viewports                                                                                                                                                                                                                                                                                                                                                                             |
| `dashboard.spec.ts`                | Dashboard                 | Board display visible, active page name, manual mode badge                                                                                                                                                                                                                                                                                                                                                                                         |
| `error-handling.spec.ts`           | Error handling            | 404 for missing page/schedule, invalid POST/template data, API error states, invalid routes, graceful degradation                                                                                                                                                                                                                                                                                                                                  |
| `generate-screenshots.spec.ts`     | Docs                      | Screenshot generation for documentation (skipped in CI)                                                                                                                                                                                                                                                                                                                                                                                            |
| `home-assistant-controls.spec.ts`  | HA integration            | HA REST API round-trips: schedule switch, active page select, refresh display/blank board buttons, send message, refresh interval, sensor state reads, transition style select                                                                                                                                                                                                                                                                     |
| `home-assistant-discovery.spec.ts` | HA integration            | FiestaBoard entities discoverable in Home Assistant via MQTT                                                                                                                                                                                                                                                                                                                                                                                       |
| `integration.spec.ts`              | Core flows                | Setup wizard, navigation, page creation, schedule creation                                                                                                                                                                                                                                                                                                                                                                                         |
| `integrations.spec.ts`             | Plugin UI                 | Installed + Marketplace tabs, plugin cards, "Add from Git" dialog (open/URL entry/cancel/disabled state validation)                                                                                                                                                                                                                                                                                                                                |
| `localization.spec.ts`             | i18n                      | Default English, switching to Spanish/French/German/Japanese, locale persistence across navigation + reload, mobile menu                                                                                                                                                                                                                                                                                                                           |
| `mock-board.spec.ts`               | Mock server               | Accepts valid 6×22 and 3×15 arrays, rejects codes >71, validates dimensions                                                                                                                                                                                                                                                                                                                                                                        |
| `multi-board.spec.ts`              | Multi-board               | Board card display, board CRUD (add/rename/type/color/toggle/delete), wizard board type/color picker, cross-feature config                                                                                                                                                                                                                                                                                                                         |
| `multi-board-schedule.spec.ts`     | Multi-board scheduling    | Single-board schedule page, two-board board selector, schedule mode toggle, per-board CRUD, filtering by board_id                                                                                                                                                                                                                                                                                                                                  |
| `multi-board-output.spec.ts`       | Multi-board output        | Two boards with real mock connections (ports 7000/7001): manual send + scheduled send land on the right board's hardware, cross-board leak checks, per-board pause isolation, per-board schedule list consistency, board-deletion consistency, board-selector UI clarity (name shown, view fully swaps, per-board toggle). Known gaps as fixme: board 2 driving (epic #1241), client reinit on board mutations                                     |
| `multi-board-mixed.spec.ts`        | Mixed-device fleet        | Flagship (6×22) + Note (3×15) boards side by side: one refresh delivers correctly-sized content to each device's hardware (dimension + token asserts, no cross-device leakage), and the board selector switches cleanly between device types on /schedule                                                                                                                                                                                          |
| `note-array-output.spec.ts`        | Note-array output         | Note arrays at the Cloud-API hardware layer: solo array installs (scheduled + manual send), every geometry class (all five presets, 1×1, 8-wide/8-tall/8×8 extremes, a non-preset size) validated against a size-strict mock, flagship+array mixed fleet driven in one refresh, array pause isolation                                                                                                                                              |
| `page-device-switch.spec.ts`       | Page creator              | Board-size switching in the editor: a page started from the Flagship tab can be switched to Note (3×15) before saving and persists device_type=note; existing pages offer no switcher (size locked once saved)                                                                                                                                                                                                                                     |
| `navigation.spec.ts`               | Navigation                | Mobile hamburger menu, sidebar links, theme toggle, version display, sidebar gradient                                                                                                                                                                                                                                                                                                                                                              |
| `note-pages.spec.ts`               | Note pages                | Note (3×15) API CRUD, UI creation, 3-line editor, preview dimensions, pages list tabs, send to board with encoding verification                                                                                                                                                                                                                                                                                                                    |
| `note-multiboard-extended.spec.ts` | Note & multi-board        | Device type mismatch (Flagship↔Note), Note 3×15 grid enforcement, one board offline handling, per-board schedule isolation, multi-board UI switching, Note display rendering                                                                                                                                                                                                                                                                       |
| `page-builder.spec.ts`             | Page builder              | Create/edit pages through the visual page builder UI                                                                                                                                                                                                                                                                                                                                                                                               |
| `pages-crud.spec.ts`               | Page management           | Create, edit, delete pages via UI                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `plugin-detail.spec.ts`            | Plugin detail             | `/integrations/[pluginId]` route: navigation from Marketplace, plugin name/category visible, Install/Installed button, Back to Marketplace link, README section present, unknown plugin error state, GitHub link                                                                                                                                                                                                                                   |
| `plugin-management.spec.ts`        | Plugin management         | Plugin listing by category, enable/disable via API+UI, config sheet open, API key password field, status badge                                                                                                                                                                                                                                                                                                                                     |
| `schedule-crud.spec.ts`            | Schedules                 | Create with page/time/day selection, delete via UI                                                                                                                                                                                                                                                                                                                                                                                                 |
| `schedule-management.spec.ts`      | Schedules                 | Toggle, form interactions, validation, calendar/list view modes, day patterns                                                                                                                                                                                                                                                                                                                                                                      |
| `settings.spec.ts`                 | Settings                  | Settings page loads with all sections (General, Boards, Advanced/Debug/Wizard), navigate to integrations                                                                                                                                                                                                                                                                                                                                           |
| `settings-full.spec.ts`            | Settings                  | Timezone picker, refresh interval, output target, board type, service control, silence schedule, wizard rerun, debug tools, system info                                                                                                                                                                                                                                                                                                            |
| `visual-regression.spec.ts`        | Visual regression         | Screenshot comparison tests for Dashboard (default/dark/light), Page Editor (empty/content/template vars), Schedule Calendar (empty/entries), Settings (general/board config), Plugin Integrations (installed/marketplace), Pages List (empty/with pages), Navigation Sidebar                                                                                                                                                                      |

> Note: `generate-screenshots.spec.ts` is excluded from CI runs via playwright config.

---

### App Routes Covered by E2E Tests

| Route                      | Spec File(s)                                                                                                      |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `/` (Dashboard)            | `dashboard.spec.ts`, `integration.spec.ts`, `visual-regression.spec.ts`                                           |
| `/pages`                   | `pages-crud.spec.ts`, `integration.spec.ts`, `visual-regression.spec.ts`                                          |
| `/pages/new`               | `pages-crud.spec.ts`, `page-builder.spec.ts`, `visual-regression.spec.ts`                                         |
| `/pages/edit/[id]`         | `pages-crud.spec.ts`, `page-builder.spec.ts`                                                                      |
| `/carousels`               | `api.spec.ts` (API only)                                                                                          |
| `/schedule`                | `schedule-crud.spec.ts`, `schedule-management.spec.ts`, `calendar-alignment.spec.ts`, `visual-regression.spec.ts` |
| `/integrations`            | `integrations.spec.ts`, `plugin-management.spec.ts`, `visual-regression.spec.ts`                                  |
| `/integrations/[pluginId]` | `plugin-detail.spec.ts`                                                                                           |
| `/settings`                | `settings.spec.ts`, `settings-full.spec.ts`, `visual-regression.spec.ts`                                          |
| `/debug`                   | `settings-full.spec.ts` (debug tools section)                                                                     |
| `/login`                   | `auth.spec.ts` (setup + sign-in forms)                                                                            |
| `/profile`                 | `auth.spec.ts` (redirects to `/settings`)                                                                         |

---

## Unit Tests (Vitest)

Unit tests run in Node with jsdom + MSW mocks for API calls.

### Vitest Test Files

| File                                      | What's Covered                                                                                                                  |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `api.test.ts`                             | `lib/api.ts` function contracts (rotation, page, settings API calls)                                                            |
| `api-extended.test.ts`                    | Extended `lib/api.ts` coverage: plugin API, schedule API, carousel API                                                          |
| `active-page-display.test.tsx`            | `ActivePageDisplay` component states (loading, active page, no page)                                                            |
| `board-colors-extended.test.ts`           | `lib/board-colors.ts` — extended color mapping edge cases                                                                       |
| `board-display-colors.test.tsx`           | Board display component color rendering                                                                                         |
| `board-display-transition.test.tsx`       | Board display component transition logic                                                                                        |
| `carousel-integration.test.tsx`           | Carousel integration component                                                                                                  |
| `carousels.test.ts`                       | `lib/carousels` utility functions                                                                                               |
| `components.test.tsx`                     | Miscellaneous UI components                                                                                                     |
| `config-display.test.tsx`                 | `ConfigDisplay` component: renders items, On/Off badges, toggle behavior, loading state                                         |
| `general-settings.test.tsx`               | `GeneralSettings` component                                                                                                     |
| `general-settings-extended.test.tsx`      | `GeneralSettings` extended coverage                                                                                             |
| `github.test.ts`                          | `lib/github.ts` — GitHub raw/README helpers (`fetchPluginReadme`, `rewriteMarkdownImageUrls`, `rewriteMarkdownRepoLinks`, etc.) |
| `home-page-banner.test.tsx`               | Home page banner component                                                                                                      |
| `hooks.test.ts`                           | Custom React hooks (useStatus, useConfig, useActivePage, usePages)                                                              |
| `hooks-extended.test.ts`                  | Custom React hooks extended coverage                                                                                            |
| `i18n-config.test.ts`                     | i18n configuration                                                                                                              |
| `language-selector.test.tsx`              | `LanguageSelector` component                                                                                                    |
| `live-output.test.tsx`                    | Live output display component                                                                                                   |
| `mqtt-settings.test.tsx`                  | MQTT settings component                                                                                                         |
| `navigation-sidebar.test.tsx`             | `NavigationSidebar` active state, mobile menu, links                                                                            |
| `new-components.test.tsx`                 | Additional UI components                                                                                                        |
| `output-target-selector.test.tsx`         | `OutputTargetSelector` component                                                                                                |
| `page-grid-selector.test.tsx`             | `PageGridSelector` component                                                                                                    |
| `page-picker-dialog.test.tsx`             | `PagePickerDialog`: renders pages, selected state, onSelect callback, None option, empty state, carousels tab, accessibility    |
| `preview-cache.test.ts`                   | `lib/preview-cache.ts`                                                                                                          |
| `schedule-calendar.test.ts`               | `lib/schedule-calendar.ts`                                                                                                      |
| `schedule-calendar-extended.test.ts`      | `lib/schedule-calendar.ts` extended                                                                                             |
| `schedule-components.test.tsx`            | Schedule form components                                                                                                        |
| `schedule-entry-form-validation.test.tsx` | Schedule entry form validation                                                                                                  |
| `service-controls.test.tsx`               | `ServiceControls` + `ServiceStatus`: loading state, running/stopped badge, green dot indicator                                  |
| `setup-detection.test.ts`                 | `lib/setup-detection.ts`                                                                                                        |
| `silence-mode-status.test.tsx`            | `SilenceModeStatus` component                                                                                                   |
| `silence-mode-status-branches.test.tsx`   | `SilenceModeStatus` branch coverage                                                                                             |
| `system-update.test.tsx`                  | `SystemUpdate` component                                                                                                        |
| `theme-toggle.test.tsx`                   | Theme toggle component                                                                                                          |
| `time-picker.test.tsx`                    | `TimePicker` UI component                                                                                                       |
| `timezone-picker.test.tsx`                | Timezone picker component                                                                                                       |
| `timezone-utils.test.ts`                  | Timezone utility functions                                                                                                      |
| `tiptap-length-calculator.test.ts`        | TipTap editor character length calculation                                                                                      |
| `tiptap-serialization.test.ts`            | TipTap editor serialization                                                                                                     |
| `tiptap-template-editor-enter.test.ts`    | TipTap editor Enter key behavior                                                                                                |
| `transition-settings.test.tsx`            | Transition settings component                                                                                                   |
| `variable-picker-content.test.tsx`        | Variable picker in TipTap toolbar                                                                                               |

---

## Running the Tests

### E2E Tests (Playwright)

```bash
# Start Docker services
docker-compose -f docker-compose.dev.yml up -d

# Run all E2E tests
cd web && MOCK_BOARD_HOST=fiestaboard-mock-board npm run test:integration

# Run a specific spec file
cd web && npx playwright test tests/integrations.spec.ts

# Run with headed browser for debugging
cd web && npx playwright test --headed
```

### Unit Tests (Vitest)

```bash
# Run unit tests (inside Docker)
docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"

# Run with coverage
cd web && npm run test:coverage
```

### Visual Regression Tests

Visual regression tests use Playwright `toHaveScreenshot()` to compare
screenshots against committed baseline images using a **0.3% pixel threshold**
to allow for minor anti-aliasing differences.

> **Note:** Visual regression tests run on CI as a dedicated step in the
> `e2e-tests` job, opted in via the `RUN_VISUAL_REGRESSION` env var. The
> step uses `continue-on-error: true` so missing or mismatched baselines do
> not block PR merges. Generated snapshots are uploaded as the
> `visual-regression-snapshots` artifact (30-day retention) and any diff
> output as `visual-regression-results` (7-day retention).

**Baseline workflow:**

1. First CI run generates baselines and uploads them as the
   `visual-regression-snapshots` artifact (the step "fails" but is
   non-blocking)
2. Download the artifact, extract under
   `web/tests/visual-regression.spec.ts-snapshots/`, and commit
3. Subsequent CI runs compare against the committed baselines
4. Update baselines after intentional UI changes by re-running locally
   with `--update-snapshots` and committing the result, or by deleting
   stale snapshots and letting CI regenerate them

```bash
# Run visual regression tests locally against the dev container
cd web && npx playwright test visual-regression

# Update baselines after intentional UI changes
cd web && npx playwright test --update-snapshots visual-regression

# Run with headed browser for debugging
cd web && npx playwright test --headed visual-regression
```

**Reducing false positives:**

- Schedule calendar tests freeze `Date.now()` via Playwright's `page.clock.setFixedTime()`
- WYSIWYG editor tests hide the blinking cursor and selection highlights
- Settings tests mask version numbers and system info
- Dashboard tests mask uptime counters and timestamps
- Calendar today-highlighting is neutralised via injected CSS

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Playwright  │────▶│  Next.js UI      │────▶│   FastAPI    │────▶│  Mock Board  │
│  (browser)   │     │  (host:4420)     │     │  (internal)  │     │ (host:17000) │
└─────────────┘     └──────────────────┘     └──────────────┘     └──────────────┘
```

The mock board server simulates the Vestaboard Local API so no real hardware
is needed for any test in this suite.
