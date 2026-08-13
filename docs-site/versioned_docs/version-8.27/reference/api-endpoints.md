---
sidebar_position: 1
description: "Complete FiestaBoard REST API reference with endpoints for pages, schedules, plugins, and display control."
keywords: [FiestaBoard API, REST API, API endpoints, API reference, display API, split-flap API]
---

# API Endpoints

FiestaBoard provides a REST API powered by FastAPI. Interactive API documentation is available at `http://localhost:4420/api/docs` when FiestaBoard is running.

## Base URL

```text
http://localhost:4420
```

When using the default deployment, prefix all paths with `/api` (e.g. `GET http://localhost:4420/api/health`).

## System Endpoints

### Health & Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check, returns service health status |
| `GET` | `/status` | Service status, uptime, and current configuration |
| `GET` | `/config` | Current configuration settings |

### Display Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/refresh` | Refresh the current display |
| `POST` | `/force-refresh` | Force refresh (bypasses preview cache) |
| `POST` | `/send-message` | Send a custom message to the board |

### Service Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/start` | Start the display service |
| `POST` | `/stop` | Stop the display service |

## Page Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/pages` | List all pages |
| `POST` | `/pages` | Create a new page |
| `GET` | `/pages/{id}` | Get a specific page |
| `PUT` | `/pages/{id}` | Update a page |
| `DELETE` | `/pages/{id}` | Delete a page |
| `POST` | `/pages/{id}/preview` | Preview a page (with variables resolved) |

### Page Fields

When creating or updating a page, the following fields are available:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Page name (required) |
| `type` | string | `"template"`, `"single"`, or `"composite"` |
| `device_type` | string | `"flagship"` (22×6) or `"note"` (15×3). Default: `"flagship"` |
| `template` | string[] | Template lines for template-type pages |
| `duration_seconds` | number | How long to display (10–3600s, default 300) |

### Batch Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/pages/preview/batch` | Preview multiple pages at once |
| `POST` | `/displays/raw/batch` | Get raw display data for multiple pages |

## Schedule Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/schedules` | List all schedule entries |
| `POST` | `/schedules` | Create a new schedule entry |
| `GET` | `/schedules/{id}` | Get a specific schedule entry |
| `PUT` | `/schedules/{id}` | Update a schedule entry |
| `DELETE` | `/schedules/{id}` | Delete a schedule entry |

## Plugin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/plugins` | List all plugins with status |
| `GET` | `/plugins/{id}` | Get plugin details |
| `PUT` | `/plugins/{id}/config` | Update plugin configuration |
| `POST` | `/plugins/{id}/enable` | Enable a plugin |
| `POST` | `/plugins/{id}/disable` | Disable a plugin |
| `GET` | `/plugins/{id}/data` | Get current plugin data |
| `GET` | `/plugins/{id}/variables` | Get available template variables |

## Settings Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/settings/all` | Get all settings in a single call |
| `GET` | `/settings/transitions` | Get transition animation settings and the built-in strategy list |
| `PUT` | `/settings/transitions` | Update transition settings. `strategy` accepts a built-in name (`column`, `reverse-column`, `edges-to-center`, `row`, `diagonal`, `random`), `"plugin:<id>"` to drive a [transition plugin](/docs/features/transitions), or `null` for no animation |
| `GET` | `/settings/output` | Get output target settings |
| `PUT` | `/settings/output` | Update output target |
| `GET` | `/settings/board` | Get board configuration |
| `PUT` | `/settings/board` | Update board configuration |

### Board Management

Installs with more than one board follow a **per-board** model: each board
has its own active page, schedule, and send routing, addressed by a
`board_id` query param (or body field) on the relevant endpoints below.
Omitting `board_id` always falls back to the primary board (`boards[0]`),
which keeps single-board installs behaving exactly as before. **Pages** and
**Collections** are not per-board — they're one shared library, and their
pickers filter to the boards they're compatible with (see
[Board Instance Fields](#board-instance-fields) for the size model).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PUT` | `/settings/board` | Update board configuration (devices, connection) |
| `POST` | `/settings/board/add` | Add a new board instance |
| `DELETE` | `/settings/board/{id}` | Remove a board instance |
| `GET` | `/settings/active-page` | Get a board's active page id (`?board_id=`) |
| `PUT` | `/settings/active-page` | Set a board's active page (renders and sends immediately) |
| `POST` | `/pages/{id}/send` | Send a page (`?target=board&board_id=`) |
| `GET` | `/board/current-message` | Read a board's current display (`?board_id=`) |

#### `PUT /settings/board` — request body fields

| Field | Type | Description |
|-------|------|-------------|
| `boards` | object[] | Array of [BoardInstance](#board-instance-fields) objects (V2 format) |
| `devices` | string[] | Device type list e.g. `["flagship", "note"]` (backward-compatible) |
| `board_type` | string | Legacy field — still accepted |

#### `PUT /settings/active-page` — request body fields

| Field | Type | Description |
|-------|------|-------------|
| `page_id` | string \| null | Page (or collection) id to activate, or `null` to clear |
| `board_id` | string | Optional. Omitted → primary board (legacy behavior) |

#### Board Instance Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID (auto-generated on create) |
| `name` | string | Display name for this board |
| `device_type` | string | `"flagship"` (22×6), `"note"` (15×3), or `"note_array"` (variable W×H) |
| `board_color` | string | `"black"` or `"white"` |
| `api_mode` | string | `"local"` or `"cloud"` |
| `host` | string | Board IP address (local mode) |
| `local_api_key` | string | Local API key |
| `cloud_key` | string | Cloud Read/Write key |
| `note_array_token` | string | Cloud API token (note-array boards in cloud mode) |
| `notes_wide` / `notes_tall` | number | Note-array grid dimensions — resolves to `(notes_wide × 15) × (notes_tall × 3)` characters |
| `enabled` | boolean | Whether this board is active |
| `schedule_enabled` | boolean | Whether this board follows its schedule (vs. manual mode) |
| `paused` | boolean | Whether this board's output is paused |

## Transition Plugin Endpoints

These endpoints back the **Transition Lab** and the transition pickers in the UI. They are gated behind the Transition Plugins beta flag (**Settings → Advanced → Beta Features**) and return `404` while it is off. See [Transitions](/docs/features/transitions) for the feature itself.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/transitions/plugins` | List installed transition plugins with their settings schema, runtime caps, and `plugin:<id>` strategy string |
| `POST` | `/transitions/preview` | Run a transition plugin in-process and return its frame sequence — nothing is sent to a board |
| `POST` | `/transitions/test-live` | Run a transition plugin once on the real board |
| `POST` | `/transitions/restore` | Snap a board back to its active page after a live test |

### `POST /transitions/preview` — request body fields

| Field | Type | Description |
|-------|------|-------------|
| `plugin_id` | string | Transition plugin to drive (required) |
| `to_text` | string | Text rendered into the target grid |
| `from_text` | string | Optional. Text rendered into the starting grid. Default: blank |
| `config` | object | Optional. Per-run overrides for the plugin's settings fields |
| `device_type` | string | Optional. `"flagship"` (default), `"note"`, or `"note_array"` |
| `notes_wide` / `notes_tall` | number | Optional. Note-array geometry (1–8 each) |

The response is `{"frames": [{"grid": [[...]], "delay_ms": n}, ...], "total_delay_ms": n, "capped": bool, "plugin_id": "..."}`. `capped` is `true` when the plugin hit its `max_frames` or `max_runtime_seconds` limit and the sequence was truncated.

### `POST /transitions/test-live` — request body fields

| Field | Type | Description |
|-------|------|-------------|
| `plugin_id` | string | Transition plugin to drive (required) |
| `to_page_id` | string | Page the transition lands on (required) |
| `from_page_id` | string | Optional. Page snapped to the board first, so the transition visibly starts from it |
| `config` | object | Optional. Per-run overrides for the plugin's settings fields |
| `board_id` | string | Optional. Omitted → primary board |

Live tests respect silence mode and board pause, returning `409` rather than writing to a quiet or paused board. The board is left showing the target page — call `POST /transitions/restore` (body: optional `board_id`) to return it to its active page, or wait for the normal display loop.

## Example Requests

### Get Service Status

```bash
curl http://localhost:4420/api/status
```

### Send a Message

```bash
curl -X POST http://localhost:4420/api/send-message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello World!"}'
```

### List Plugins

```bash
curl http://localhost:4420/api/plugins
```

### Preview a Page

```bash
curl -X POST http://localhost:4420/api/pages/1/preview
```

## Interactive Documentation

For a complete interactive API explorer with request/response schemas, visit:

```text
http://localhost:4420/api/docs
```

This provides a Swagger UI where you can try out any endpoint directly in your browser.

## Next Steps

- [Docker Setup](/docs/setup/docker-setup) - Understanding the API architecture
- [Plugin Configuration](/docs/plugins/configuration) - Configuring plugins via API
