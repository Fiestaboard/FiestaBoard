# E2E / Integration Test Coverage

This document describes every use case covered by the FiestaBoard end-to-end
integration tests. Tests exercise the **full stack**:

```
Playwright browser → Next.js UI → FastAPI backend → Mock Vestaboard API
```

## Test Files

| File | Area | Description |
|------|------|-------------|
| `integration.spec.ts` | Core flows | Infrastructure, setup wizard, navigation, pages, schedules |
| `settings.spec.ts` | Settings | Settings page, output target, debug tools |
| `api.spec.ts` | Backend API | Direct API endpoint tests for config, pages, schedules, settings, templates |
| `pages-crud.spec.ts` | Page management | Create, edit, and delete pages via the UI |
| `schedule-crud.spec.ts` | Schedule management | Create, validate, and delete schedules via the UI |
| `integrations.spec.ts` | Integrations | Plugin listing and plugin enable/disable |

---

## Coverage Matrix

### Infrastructure & Health (`integration.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 1 | Mock board server responds with correct board dimensions | `mock board server is running and responsive` |
| 2 | API health endpoint returns OK status | `API health check responds OK` |

### Setup Wizard (`integration.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 3 | Wizard appears on first run | `completes the wizard using Local API mode` |
| 4 | User can select Local API connection mode | `completes the wizard using Local API mode` |
| 5 | User can fill in board host and API key | `completes the wizard using Local API mode` |
| 6 | Test Connection succeeds against mock board | `completes the wizard using Local API mode` |
| 7 | User can skip data sources step | `completes the wizard using Local API mode` |
| 8 | Wizard completion redirects to Dashboard | `completes the wizard using Local API mode` |

### Navigation (`integration.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 9 | Navigate to Dashboard | `navigates between main sections` |
| 10 | Navigate to Pages | `navigates between main sections` |
| 11 | Navigate to Schedule | `navigates between main sections` |
| 12 | Navigate to Settings | `navigates between main sections` |
| 13 | Navigate back to Dashboard from Settings | `navigates between main sections` |

### Page Management – UI (`integration.spec.ts`, `pages-crud.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 14 | Create a new template page with name and content | `creates a new template page` |
| 15 | Saved page appears in page list | `newly created page appears in the page list` |
| 16 | Delete a page from the page list | `can delete a page` |

### Schedule Management – UI (`integration.spec.ts`, `schedule-crud.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 17 | Open Add Schedule dialog | `creates a schedule entry` |
| 18 | Select a page, start time, and end time | `creates a schedule entry` |
| 19 | Submit schedule entry | `creates a schedule entry` |
| 20 | Schedule page remains visible after creation | `creates a schedule entry` |
| 21 | Create a schedule and see it listed | `can create a schedule and see it listed` |
| 22 | Delete a schedule entry | `can delete a schedule` |

### Settings – UI (`settings.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 23 | Settings page loads with all sections | `loads settings page with all sections visible` |
| 24 | Navigate to Integrations from Settings | `can navigate to integrations from settings` |
| 26 | Run Setup Wizard button is available | `loads settings page with all sections visible` |

### Integrations – UI (`integrations.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 27 | Integrations page loads with plugin list | `loads the integrations page with plugin list` |
| 28 | Plugin cards display name and description | `loads the integrations page with plugin list` |

### API – Backend Direct (`api.spec.ts`)

| # | Use Case | Test |
|---|----------|------|
| 29 | `GET /version` returns package and build versions | `returns version information` |
| 30 | `GET /config` returns configuration summary | `returns configuration summary` |
| 31 | `GET /settings/all` returns all settings groups | `returns all settings` |
| 32 | `PUT /settings/output` changes output target | `can update output target` |
| 33 | `PUT /settings/polling` changes polling interval | `can update polling interval` |
| 34 | `PUT /settings/polling` rejects invalid interval | `rejects invalid polling interval` |
| 35 | `GET /pages` lists pages | `can list pages` |
| 36 | `POST /pages` + `DELETE /pages/:id` round-trip | `can create and delete a page` |
| 37 | `GET /schedules` lists schedules | `can list schedules` |
| 38 | `POST /schedules` + `DELETE /schedules/:id` round-trip | `can create and delete a schedule` |
| 39 | `GET /plugins` lists available plugins | `can list plugins` |
| 40 | `GET /templates/variables` returns variable catalog | `returns template variables` |
| 41 | `POST /templates/validate` validates correct template | `validates a correct template` |
| 42 | `GET /displays` lists display sources | `can list displays` |
| 43 | `POST /debug/test-connection` tests board connection | `can test board connection` |
| 46 | `GET /debug/system-info` returns system information | `returns system information` |

---

## Running the Tests

### Local development (Docker + host Playwright)

This is the recommended local workflow. Docker provides all backend services;
Playwright runs on the host and connects to them.

**One-time setup** (install Playwright's Chromium browser):

```bash
cd web && npx playwright install chromium
```

**Every run:**

```bash
# 1. Start Docker services (mock board published on host **17000** / **17001**, container ports 7000 / 7001)
docker-compose -f docker-compose.dev.yml up -d

# 2. Run tests from the web/ directory
#    MOCK_BOARD_HOST tells the API container where to find the mock board
cd web && MOCK_BOARD_HOST=fiestaboard-mock-board npm run test:integration
```

`MOCK_BOARD_HOST` is the hostname the API container uses to reach the mock
board. In Docker, containers talk to each other by service name
(`fiestaboard-mock-board`). In CI, everything runs on `localhost` (the default).

Playwright's `reuseExistingServer: true` means it will use the already-running
Docker services (FiestaBoard on **4420**; mock board on host **17000** and **17001**, still **7000**/**7001** inside the compose network)
without trying to start new processes.

**Run a specific test file:**

```bash
cd web && npx playwright test tests/api.spec.ts
```

**Run with headed browser for debugging:**

```bash
cd web && npx playwright test --headed
```

### CI (merge queue)

Tests run automatically via `.github/workflows/integration-tests.yml` when a PR
enters the merge queue. No action needed.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐     ┌──────────────┐
│  Playwright  │────▶│  Next.js UI      │────▶│   FastAPI    │────▶│  Mock Board  │
│  (browser)   │     │  (internal:3000) │     │  (internal:  │     │ (host:17000) │
│              │     │  (host:4420)     │     │   8000)      │     │              │
└─────────────┘     └──────────────────┘     └──────────────┘     └──────────────┘
                                                                     ▲
                    API-only tests hit the FastAPI server directly ───┘
```

All three servers are started automatically by Playwright's `webServer`
configuration. The mock board server simulates the Vestaboard Local API
so no real hardware is needed.
