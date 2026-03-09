---
sidebar_position: 1
description: "Complete FiestaBoard REST API reference with endpoints for pages, schedules, plugins, and display control."
keywords: [FiestaBoard API, REST API, API endpoints, API reference, display API, split-flap API]
---

# API Endpoints

FiestaBoard provides a REST API powered by FastAPI. Interactive API documentation is available at `http://localhost:4420/api/docs` when FiestaBoard is running.

## Base URL

```
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
| `GET` | `/settings/transitions` | Get transition animation settings |
| `PUT` | `/settings/transitions` | Update transition settings |
| `GET` | `/settings/output` | Get output target settings |
| `PUT` | `/settings/output` | Update output target |
| `GET` | `/settings/board` | Get board configuration |
| `PUT` | `/settings/board` | Update board configuration |

### Board Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `PUT` | `/settings/board` | Update board configuration (devices, connection) |
| `POST` | `/settings/board/add` | Add a new board instance |
| `DELETE` | `/settings/board/{id}` | Remove a board instance |

#### `PUT /settings/board` — request body fields

| Field | Type | Description |
|-------|------|-------------|
| `boards` | object[] | Array of [BoardInstance](#board-instance-fields) objects (V2 format) |
| `devices` | string[] | Device type list e.g. `["flagship", "note"]` (backward-compatible) |
| `board_type` | string | Legacy field — still accepted |

#### Board Instance Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID (auto-generated on create) |
| `name` | string | Display name for this board |
| `device_type` | string | `"flagship"` (22×6) or `"note"` (15×3) |
| `board_color` | string | `"black"` or `"white"` |
| `api_mode` | string | `"local"` or `"cloud"` |
| `host` | string | Board IP address (local mode) |
| `local_api_key` | string | Local API key |
| `cloud_key` | string | Cloud Read/Write key |
| `enabled` | boolean | Whether this board is active |

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

```
http://localhost:4420/api/docs
```

This provides a Swagger UI where you can try out any endpoint directly in your browser.

## Next Steps

- [Docker Setup](/docs/setup/docker-setup) - Understanding the API architecture
- [Plugin Configuration](/docs/plugins/configuration) - Configuring plugins via API
