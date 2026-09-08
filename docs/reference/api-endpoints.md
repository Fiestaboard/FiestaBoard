---
sidebar_position: 1
description: "The generated FiestaBoard REST API reference: every published operation, its parameters, request body, responses and errors."
keywords: [FiestaBoard API, REST API, API endpoints, API reference, display API, split-flap API]
---

<!--
  GENERATED FILE — DO NOT EDIT BY HAND.

  Produced by scripts/generate_api_reference.py from the published OpenAPI
  document (`app.openapi()`), so it cannot drift from the API it describes.
  Edit the route, the Pydantic model or src/api_server.py::API_DESCRIPTION,
  then regenerate:

      python scripts/generate_api_reference.py

  CI (`Lint Markdown` -> `Check the generated API reference is current`)
  fails when this file differs from what the generator produces.
-->

# API Endpoints

FiestaBoard drives one or more split-flap displays from templated pages.

## Hello world

Put text on the board right now:

```bash
curl -X POST http://fiestaboard.local:4420/api/v1/boards/primary/message \
  -H 'Content-Type: application/json' \
  -d '{"text": "HELLO WORLD"}'
```

`primary` works as a board id on every `/v1/boards/...` path, so a
single-board install never has to look one up — and a multi-board install
puts the id there instead.

## How the pieces fit

Four nouns, and one way to do each thing:

- A **board** is a physical display. `POST /v1/boards/{board}/message` writes
  to it; `GET /v1/boards/{board}` says what is on it and why.

- A **page** is a template: literal text plus `{{plugin_id.variable}}`
  placeholders that **plugins** fill with live data.

- A **schedule** (or a **collection**) decides which page a board shows at a
  given moment. A message write bypasses both for a one-off; `DELETE
  /v1/boards/{board}/message` hands the board back to the schedule.

## Base URL

nginx fronts the API under `/api`, so every path below is reached as
`/api/<path>` — `GET /v1/status` is
`http://fiestaboard.local:4420/api/v1/status`. These docs live at
`/api/docs`, the schema at `/api/openapi.json`.

## What is not here

This document is the API to build against: 33 operations. The app serves
~200 more, but they are the web UI's private RPC channel — undocumented on
purpose, with no compatibility promise, and liable to change in any release.
They are published separately at `/api/internal/openapi.json` for the UI's
own contract checks. Two flat legacy operations, `POST /send-message` and
`POST /refresh`, remain here because earlier documentation named them; both
are deprecated and both name their `/v1` replacement in a `Link` header.

## Authentication

Off by default: a fresh install answers every request. With
`FIESTABOARD_AUTH_ENABLED=true`, a script sends
`Authorization: Bearer <token>` (create one with `POST /auth/mcp-token`),
which is accepted on every `/v1` path and on `/api/mcp`. The web UI instead
carries the session cookie that `POST /auth/login` sets.

## Credentials

Either credential satisfies any request; which one you hold depends on whether
you are a script or the web UI. Both are declared in the OpenAPI document, so a
client generator picks them up.

| Scheme | How it is sent | Notes |
|--------|----------------|-------|
| `apiToken` | `Authorization: Bearer <token>` | A FiestaBoard API token, sent as `Authorization: Bearer <token>`. Create one with `POST /auth/mcp-token` or pin one out of band with the `FIESTABOARD_MCP_TOKEN` environment variable. Accepted on every `/v1` route and on the MCP endpoint. This is the credential to use from a script: unlike the session cookie it needs no browser login flow. When no token is configured and authentication is disabled, the API is open and no credential is required — the default for a local-only install. |
| `session` | `fiestaboard_session` (cookie) | The browser session cookie issued by `POST /auth/login`. What the web UI holds. A script should use `apiToken` instead. |

## Quick start

`POST /v1/boards/{board}/message` is the front door. `primary` works as a board id on
every `/v1/boards/...` path, so a single-board install never has to look one up.

```bash
curl -X POST http://fiestaboard.local:4420/api/v1/boards/primary/message \
  -H "Authorization: Bearer $FIESTABOARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "HELLO WORLD"}'
```

Drop the `Authorization` header on an install that has not turned
authentication on — it is off by default.

## `v1` {#tag-v1}

The FiestaBoard API. Four nouns — board, page, schedule, plugin — and one way to do each thing.

Start here: `POST /v1/boards/primary/message` with `{"text": "HELLO"}` puts text on your board. `primary` works as a board id on every `/v1/boards/...` path, so a single-board install never needs to look one up.

Every write reports what actually happened rather than merely acknowledging the request: `sent` is true only when flaps moved, and a `reason` says why when they did not.

### `GET /v1/boards` {#get-v1-boards}

**List the boards this install drives**

Every configured board, with the id you use in the rest of this API, its grid size, and whether it is currently paused or following its schedule. The board marked `is_primary` is the one the literal path segment `primary` resolves to, so a single-board install never has to look an id up at all.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`BoardListResponse`](#schema-boardlistresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/boards/{board}` {#get-v1-boards-board}

**Read a board and everything it is doing**

One answer to 'what is this board showing, and why'. It merges what the internal API splits across three endpoints: the flaps currently on the board, the page pinned to it by hand, and the page its schedule selects for right now. `source` says which of the two won. `board` may be a board id or the literal `primary`.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`BoardDetail`](#schema-boarddetail) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `PATCH /v1/boards/{board}` {#patch-v1-boards-board}

**Change how a board behaves**

Rename a board, pause or resume it, turn its schedule on or off, or set the page it falls back to when the schedule has a gap. Only the fields you send are applied; omit the rest. Pausing stops every write to the board from every code path — the display loop, schedules, plugin triggers, MQTT and this API alike.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | path | `string` | yes | — |

**Request body** (required) — [`BoardUpdate`](#schema-boardupdate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | Rename the board. (min length 1; max length 100) |
| `paused` | `boolean` \| `null` | no | Pause or resume the board. While paused nothing is written to it from any code path. |
| `schedule_enabled` | `boolean` \| `null` | no | Turn this board's schedule on or off. |
| `default_page_id` | `string` \| `null` | no | Page shown when the schedule has a gap. Send null to clear it. |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`BoardDetail`](#schema-boarddetail) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/boards/{board}/message` {#post-v1-boards-board-message}

**Put something on a board**

The one way to write to a board. Send exactly one of `text` (word-wrapped for you), `lines` (one string per row), `characters` (a raw flap grid), `page_id` (render a saved page) or `fill` (one flap code everywhere; 0 blanks the board).

Add `duration_minutes` to make it temporary — it reverts to your schedule, a chosen page, or a blank board when the time is up. `board` may be a board id or the literal `primary`.

`sent` in the response tells you whether flaps actually moved. It is false, with a `reason`, when the install's output target is UI-only and when the board already showed this exact content. A board that is paused or inside its silence window refuses the write with 409 rather than lying about it.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | path | `string` | yes | — |

**Request body** (required) — [`MessageRequest (v1)`](#schema-src-v1-models-messagerequest)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `string` \| `null` | no | Plain text, word-wrapped to the board. Colour and character markers (`{red}`, `{63}`) work here. |
| `lines` | array of `string` \| `null` | no | One string per board row, laid out without re-wrapping across rows. |
| `characters` | array of array of `integer` \| `null` | no | A raw flap grid, sized exactly to the board. Codes are 0-71. |
| `page_id` | `string` \| `null` | no | Render a saved page (or collection) and send the result. |
| `fill` | `integer` \| `null` | no | Fill the whole board with one flap code (0-71). 0 blanks it. (0–71) |
| `duration_minutes` | `integer` \| `null` | no | Show this for N minutes, then revert. Omit for a message that stays until something else replaces it. (1–480) |
| `revert_mode` | `"schedule"` \| `"page"` \| `"blank"` \| `null` | no | What to show when a timed message expires. Requires duration_minutes. Defaults to "schedule". |
| `revert_page_id` | `string` \| `null` | no | The page to revert to. Required when revert_mode is "page". |
| `transition` | [`TransitionOverride`](#schema-transitionoverride) \| `null` | no | Override the install's transition animation for this one send. |
| `force` | `boolean` | no | Send even when the board already shows this exact content, which is normally skipped. (default `false`) |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`MessageResponse`](#schema-messageresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `409` | [`ErrorResponse`](#schema-errorresponse) | Conflict — duplicate id, or a resource pinned by the environment. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `429` | [`ErrorResponse`](#schema-errorresponse) | Rate-limited — the request arrived inside a minimum interval; see Retry-After. |
| `500` | [`ErrorResponse`](#schema-errorresponse) | The server could not complete the operation. Deliberately raised, not an unhandled error. |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `DELETE /v1/boards/{board}/message` {#delete-v1-boards-board-message}

**Clear a board and let its schedule take over**

Undoes a `POST` to this path. Any timed message is cancelled, the board's content cache is dropped, and the display loop re-renders whatever the schedule or the pinned page says should be there — which is a blank board when nothing is scheduled. `sent` reports whether that re-render reached the board.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`MessageResponse`](#schema-messageresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `500` | [`ErrorResponse`](#schema-errorresponse) | The server could not complete the operation. Deliberately raised, not an unhandled error. |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `PUT /v1/boards/{board}/active-page` {#put-v1-boards-board-active-page}

**Pin a page to a board**

Sets the page (or collection) this board shows until something changes it — the sticky selection a schedule falls back from. The page is rendered and sent immediately. Send `null` to unpin, after which the board follows its schedule again. Pinning a page whose size does not match the board is rejected.

The selection is stored whether or not the send succeeded, so check `sent` — and `error`, which names the render or send failure when it is false.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | path | `string` | yes | — |

**Request body** (required) — [`ActivePageRequest`](#schema-activepagerequest)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `page_id` | `string` \| `null` | yes | Page or collection to pin to this board. Send null to unpin and fall back to the schedule. |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`ActivePageResponse`](#schema-activepageresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `502` | [`ErrorResponse`](#schema-errorresponse) | An upstream the server called on your behalf failed. |

### `GET /v1/pages` {#get-v1-pages}

**List saved pages**

Every page saved on this install. A page is a reusable board layout — literal text, plugin variables, or rows composed from other sources — that a schedule, a collection or `POST /v1/boards/{board}/message` can refer to by id.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PageListResponse`](#schema-pagelistresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/pages` {#post-v1-pages}

**Create a page**

Saves a new page and answers with it, including the generated `id` you refer to it by. `type` picks how it is built: `template` for text with `{{variables}}`, `single` for one plugin's output, `composite` for rows drawn from several sources. `device_type` must match the boards you intend to show it on.

**Request body** (required) — [`PageCreate`](#schema-pagecreate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | min length 1; max length 100 |
| `type` | `"single"` \| `"composite"` \| `"template"` | yes | — |
| `device_type` | `"flagship"` \| `"note"` \| `"note_array"` | no | default `"flagship"` |
| `display_type` | `string` \| `null` | no | — |
| `rows` | array of [`RowConfig`](#schema-rowconfig) \| `null` | no | — |
| `template` | array of `string` \| `null` | no | — |
| `line_metadata` | array of [`LineMetadata`](#schema-linemetadata) \| `null` | no | — |
| `duration_seconds` | `integer` | no | 10–3600; default `300` |
| `transition_strategy` | `string` \| `null` | no | — |
| `transition_interval_ms` | `integer` \| `null` | no | 0–5000 |
| `transition_step_size` | `integer` \| `null` | no | min 1 |
| `demo_plugin_id` | `string` \| `null` | no | — |
| `notes_wide` | `integer` \| `null` | no | 1–8 |
| `notes_tall` | `integer` \| `null` | no | 1–8 |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `201` | [`Page`](#schema-page) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/pages/{page_id}` {#get-v1-pages-page-id}

**Read one page**

The saved page with this id, exactly as stored — its type, its device size, its template or row configuration, and its per-page transition overrides. 404 when no page has this id.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`Page`](#schema-page) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /v1/pages/{page_id}` {#put-v1-pages-page-id}

**Update a page**

Applies the fields you send and leaves the rest alone. The response carries the updated page plus `incompatible_references`: places that still point at this page — a board's schedule, a pinned selection — where your change has made the size no longer fit.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page_id` | path | `string` | yes | — |

**Request body** (required) — [`PageUpdate`](#schema-pageupdate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | min length 1; max length 100 |
| `device_type` | `"flagship"` \| `"note"` \| `"note_array"` \| `null` | no | — |
| `display_type` | `string` \| `null` | no | — |
| `rows` | array of [`RowConfig`](#schema-rowconfig) \| `null` | no | — |
| `template` | array of `string` \| `null` | no | — |
| `line_metadata` | array of [`LineMetadata`](#schema-linemetadata) \| `null` | no | — |
| `duration_seconds` | `integer` \| `null` | no | 10–3600 |
| `transition_strategy` | `string` \| `null` | no | — |
| `transition_interval_ms` | `integer` \| `null` | no | 0–5000 |
| `transition_step_size` | `integer` \| `null` | no | min 1 |
| `notes_wide` | `integer` \| `null` | no | 1–8 |
| `notes_tall` | `integer` \| `null` | no | 1–8 |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PageUpdateResponse`](#schema-pageupdateresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /v1/pages/{page_id}` {#delete-v1-pages-page-id}

**Delete a page**

Removes the page. If it was the last page, or was the one a board was showing, the response says what was put in its place so nothing is left pointing at a page that no longer exists.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `page_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PageDeleteResponse`](#schema-pagedeleteresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/schedules` {#get-v1-schedules}

**List schedule entries**

Every schedule entry, newest rules included. Pass `board_id` to narrow it to one board, or `*` for all boards at once. Each entry says which page shows between which times, on which days; the response also carries the fallback page and whether scheduling is switched on.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board_id` | query | `string` \| `null` | no | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`ScheduleListResponse`](#schema-schedulelistresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/schedules` {#post-v1-schedules}

**Create a schedule entry**

Adds a rule: show `page_id` from `start_time` to `end_time` on the days `day_pattern` selects. Times may also be relative to sunrise or sunset (`start_type`, `start_sun_offset`), and a rule may recur weekly, on a calendar date every year, or once. Omit `board_id` for the default board.

**Request body** (required) — [`ScheduleCreate`](#schema-schedulecreate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` | no | min length 0; default `""` |
| `page_id` | `string` | yes | min length 1 |
| `start_time` | `string` | yes | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` | no | default `"all"` |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` | no | default `true` |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` | no | default `"weekly"` |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `start_sun_offset` | `integer` | no | default `0` |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `end_sun_offset` | `integer` | no | default `0` |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `201` | [`ScheduleWriteResponse`](#schema-schedulewriteresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/schedules/{schedule_id}` {#get-v1-schedules-schedule-id}

**Read one schedule entry**

The schedule entry with this id, plus `resolved_start_time` and `resolved_end_time` — the wall-clock times a sunrise- or sunset-relative rule works out to today.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `schedule_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`ScheduleResponse`](#schema-scheduleresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /v1/schedules/{schedule_id}` {#put-v1-schedules-schedule-id}

**Update a schedule entry**

Applies only the fields you send, so a partial update cannot silently clear the ones you left out. `warnings` reports rules that now overlap or leave a gap without failing the write.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `schedule_id` | path | `string` | yes | — |

**Request body** (required) — [`ScheduleUpdate`](#schema-scheduleupdate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` \| `null` | no | min length 0 |
| `page_id` | `string` \| `null` | no | min length 1 |
| `start_time` | `string` \| `null` | no | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` \| `null` | no | — |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` \| `null` | no | — |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` \| `null` | no | — |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` \| `null` | no | — |
| `start_sun_offset` | `integer` \| `null` | no | — |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` \| `null` | no | — |
| `end_sun_offset` | `integer` \| `null` | no | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`ScheduleWriteResponse`](#schema-schedulewriteresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /v1/schedules/{schedule_id}` {#delete-v1-schedules-schedule-id}

**Delete a schedule entry**

Removes this schedule rule. The page it pointed at is untouched, and the board falls back to its remaining rules — or to its gap page when none of them match.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `schedule_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`ScheduleDeleteResponse`](#schema-scheduledeleteresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/collections` {#get-v1-collections}

**List the saved collections**

Every collection. A collection is a set of pages plus a rule for choosing between them — rotate on a timer, pick at random, or switch on the value of a template expression — and it can be used anywhere a page id can.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`CollectionListResponse`](#schema-collectionlistresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/collections` {#post-v1-collections}

**Create a collection**

Saves a set of pages and how to choose between them. `selection_mode` is `time` (rotate every `time.interval_seconds`), `random`, or `variable` (evaluate `variable.rules` in order and show the first match). The generated id is prefixed `collection:` and is usable wherever a page id is.

**Request body** (required) — [`CollectionCreate`](#schema-collectioncreate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | min length 1; max length 100 |
| `page_ids` | array of `string` | yes | — |
| `selection_mode` | `"time"` \| `"variable"` \| `"random"` | no | default `"time"` |
| `time` | [`TimeModeConfig`](#schema-timemodeconfig) | no | — |
| `variable` | [`VariableModeConfig`](#schema-variablemodeconfig) \| `null` | no | — |
| `random` | [`RandomModeConfig`](#schema-randommodeconfig) \| `null` | no | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `201` | [`Collection`](#schema-collection) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/collections/{collection_id}` {#get-v1-collections-collection-id}

**Read one collection**

The collection with this id: its member page ids in order, its selection mode, and the config block for that mode — the rotation interval, or the expression rules that pick between the members.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `collection_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`Collection`](#schema-collection) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `PUT /v1/collections/{collection_id}` {#put-v1-collections-collection-id}

**Update a collection**

Applies only the fields you send. Every page id in `page_ids` must exist, and a `variable` rule may only point at a page the collection contains.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `collection_id` | path | `string` | yes | — |

**Request body** (required) — [`CollectionUpdate`](#schema-collectionupdate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | min length 1; max length 100 |
| `page_ids` | array of `string` \| `null` | no | — |
| `selection_mode` | `"time"` \| `"variable"` \| `"random"` \| `null` | no | — |
| `time` | [`TimeModeConfig`](#schema-timemodeconfig) \| `null` | no | — |
| `variable` | [`VariableModeConfig`](#schema-variablemodeconfig) \| `null` | no | — |
| `random` | [`RandomModeConfig`](#schema-randommodeconfig) \| `null` | no | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`Collection`](#schema-collection) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `DELETE /v1/collections/{collection_id}` {#delete-v1-collections-collection-id}

**Delete a collection**

Removes the collection. Its member pages are untouched, but anything still referring to the collection id — a schedule rule, a board's pinned selection — will stop resolving.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `collection_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`CollectionDeleteResponse`](#schema-collectiondeleteresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/variables` {#get-v1-variables}

**List every name a template can use**

The whole template vocabulary in one answer: the built-in variables, everything the installed plugins contribute, the colour and symbol names, and the filters you can apply. `max_lengths` gives the longest value each variable can render to, which is what you size a row against.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`VariableCatalog`](#schema-variablecatalog) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/functions` {#get-v1-functions}

**List the functions a template expression can call**

Every function usable inside `{{ }}` — conditionals, arithmetic, text and date helpers — with its signature and a one-line summary. This is the reference for writing a collection's `variable` rules as well as for page templates.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`FormulaFunctionsResponse`](#schema-formulafunctionsresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/render` {#post-v1-render}

**Render a template without saving or sending it**

Runs a template against the current data and gives you back the text, so you can see what a page would look like before you save it. Pass `board` — a board id or `primary` — to lay it out for that board's size, or `device_type` to lay it out for a hardware shape you have not configured a board for; without either, the template is rendered at the default flagship geometry. Nothing is written to any board.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board` | query | `string` \| `null` | no | Board id, or 'primary', whose geometry the template should be laid out for. |
| `device_type` | query | `"flagship"` \| `"note"` \| `"note_array"` \| `null` | no | Board shape to lay the template out for, as an alternative to naming a board. Use this to preview a page whose device type no configured board has. |

**Request body** (required) — [`RenderRequest`](#schema-renderrequest)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template` | `string` \| array of `string` | yes | A template string, or one string per board row. A list is padded to the board's height. |
| `line_metadata` | array of `object` \| `null` | no | Per-line alignment and wrap options, one entry per line. |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`TemplateRenderResponse`](#schema-templaterenderresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |

### `GET /v1/health` {#get-v1-health}

**Check that the instance is up**

Answers 200 whenever the process is serving. `service_running` reports whether the display loop — the thing that actually drives the boards — is running, which is separate from the API being reachable.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`HealthResponse`](#schema-healthresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/status` {#get-v1-status}

**Read the display loop's state, board by board**

What the instance is doing: whether the display loop is running, a summary of the resolved configuration, and per board whether it has a working connection, whether it is paused, which page it is showing, and why it failed to start if it did.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`StatusResponse`](#schema-statusresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/plugins` {#get-v1-plugins}

**List installed plugins**

Every plugin installed on this instance, whether or not it is switched on. A plugin is a data source — weather, transit, a stock ticker — that contributes template variables you can put on a page. `enabled` says whether it runs; `configured` says whether its required settings have been filled in.

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PluginListResponse`](#schema-pluginlistresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/plugins/{plugin_id}` {#get-v1-plugins-plugin-id}

**Read one plugin**

Everything about one plugin: its manifest, the template variables it contributes and their maximum lengths, its settings schema, and its current configuration. Stored secrets come back masked as `***`; sending that value back in a `PATCH` leaves the stored secret untouched.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `plugin_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PluginDetail`](#schema-plugindetail) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `PATCH /v1/plugins/{plugin_id}` {#patch-v1-plugins-plugin-id}

**Enable, disable or configure a plugin**

One call for the three things you can do to a plugin. Send `enabled` to switch it on or off, `config` to replace its settings, or both — the settings are written first so a plugin is never enabled with a configuration you meant to replace. Answers with the plugin's full detail, secrets masked.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `plugin_id` | path | `string` | yes | — |

**Request body** (required) — [`PluginUpdate`](#schema-pluginupdate)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | `boolean` \| `null` | no | Enable or disable the plugin. |
| `config` | `object` \| `null` | no | Replace the plugin's settings. Send "***" for a secret you do not want to change. |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PluginDetail`](#schema-plugindetail) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `GET /v1/plugins/{plugin_id}/data` {#get-v1-plugins-plugin-id-data}

**Read what a plugin is currently reporting**

The plugin's latest fetch, in both forms the internal API served separately: `data` is the raw variable payload a template reads from, and `lines`/`text` are the board-ready rendering of it. `available` is false, with `error` set, when the plugin is disabled, unconfigured, or its source could not be reached — a 200, because that is the answer to the question asked. 404 means no such plugin is installed.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `plugin_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PluginData`](#schema-plugindata) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

### `POST /v1/plugins/{plugin_id}/receive` {#post-v1-plugins-plugin-id-receive}

**Push data into a plugin from outside**

The webhook target. A plugin that declares a `receive` handler accepts a JSON body here and updates what it reports without polling anything — the way to drive a board from a system FiestaBoard cannot reach out to. 405 means this plugin does not accept pushes.

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `plugin_id` | path | `string` | yes | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`PluginReceiveResponse`](#schema-pluginreceiveresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `400` | [`ErrorResponse`](#schema-errorresponse) | Invalid request — the payload references something that does not exist or violates a rule. |
| `403` | [`ErrorResponse`](#schema-errorresponse) | Forbidden. |
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `405` | [`ErrorResponse`](#schema-errorresponse) | The resource exists but does not implement this operation. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

## `service` {#tag-service}

The display loop itself: health, status, start/stop/refresh.

### `POST /refresh` {#post-refresh}

:::warning Deprecated

`POST /refresh` is deprecated and answers with `Deprecation`, `Sunset` and
`Link: rel="successor-version"` headers. Use `DELETE /v1/boards/{board}/message` instead.

:::

**Refresh Display**

Manually trigger a display refresh.

Args:
    board_id: Optional board to refresh (query param, or
        `{"board_id": ...}` in the JSON body). Omitted → legacy
        behavior: refresh every board, primary first (issue #1244).

**Parameters**

| Name | In | Type | Required | Description |
|------|----|------|----------|-------------|
| `board_id` | query | `string` \| `null` | no | — |

**Request body** (optional) — [`RefreshRequest`](#schema-refreshrequest) \| `null`

_No fields._

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`RefreshResponse`](#schema-refreshresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `500` | [`ErrorResponse`](#schema-errorresponse) | The server could not complete the operation. Deliberately raised, not an unhandled error. |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

## `board` {#tag-board}

Write to a board out of band, and read back what is physically on it.

### `POST /send-message` {#post-send-message}

:::warning Deprecated

`POST /send-message` is deprecated and answers with `Deprecation`, `Sunset` and
`Link: rel="successor-version"` headers. Use `POST /v1/boards/{board}/message` instead.

:::

**Send Message**

Send a custom message to a board.

`board_id` (optional) targets one board; omitted → the primary board,
which is what every caller got before this endpoint could address a
second one (issue #1247). Gate for gate this is the same policy the MCP
executor applies — see `src/ops/executors.py`.

The v1 successor takes the board in the path, so it cannot be forgotten,
and reports whether flaps actually moved rather than only that the
request was accepted.

**Request body** (required) — [`MessageRequest (board_api)`](#schema-src-board-api-models-messagerequest)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `string` | yes | — |
| `board_id` | `string` \| `null` | no | — |

**Responses**

| Status | Body | Description |
|--------|------|-------------|
| `200` | [`SendResponse`](#schema-sendresponse) | Successful Response |

**Errors**

| Status | Body | Meaning |
|--------|------|---------|
| `404` | [`ErrorResponse`](#schema-errorresponse) | Resource not found. |
| `409` | [`ErrorResponse`](#schema-errorresponse) | Conflict — duplicate id, or a resource pinned by the environment. |
| `422` | [`HTTPValidationError`](#schema-httpvalidationerror) | Validation Error |
| `429` | [`ErrorResponse`](#schema-errorresponse) | Rate-limited — the request arrived inside a minimum interval; see Retry-After. |
| `500` | [`ErrorResponse`](#schema-errorresponse) | The server could not complete the operation. Deliberately raised, not an unhandled error. |
| `503` | [`ErrorResponse`](#schema-errorresponse) | A required dependency is unavailable. |

## Schemas

Every model the operations above name, expanded once.

### `ActivePageRequest` {#schema-activepagerequest}

`PUT /v1/boards/{board}/active-page`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `page_id` | `string` \| `null` | yes | Page or collection to pin to this board. Send null to unpin and fall back to the schedule. |

### `ActivePageResponse` {#schema-activepageresponse}

The result of pinning a page to a board.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` | yes | — |
| `page_id` | `string` \| `null` | yes | What is now pinned. Null means nothing is. |
| `sent` | `boolean` | yes | Whether the new page reached the board immediately. |
| `error` | `string` \| `null` | no | Why the page did not reach the board, when `sent` is false. The selection is stored either way, so a 200 here is not on its own proof that anything was displayed (#1791). |
| `warnings` | array of `string` | no | Non-fatal problems, e.g. collection members that do not fit this board. |

### `BoardDetail` {#schema-boarddetail}

One board plus what is on it right now.

The merge named in the design: `GET /board/current-message` (what the
flaps show), `GET /settings/active-page` (the sticky manual selection)
and `GET /schedules/active/page` (what the schedule says) answered as
one document, because "what is this board doing" is one question.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | The board's stable id. Usable anywhere `{board}` appears in a v1 path. |
| `name` | `string` | yes | Human-readable board name, as set in Settings. |
| `device_type` | `string` | yes | Board hardware: "flagship", "note", or "note_array". |
| `rows` | `integer` | yes | Grid height in flaps. |
| `cols` | `integer` | yes | Grid width in flaps. |
| `is_primary` | `boolean` | yes | True for the board that the alias "primary" resolves to. |
| `paused` | `boolean` | yes | While true, FiestaBoard writes nothing to this board from any code path. |
| `schedule_enabled` | `boolean` | yes | Whether this board follows its schedule rather than a fixed page. |
| `characters` | array of array of `integer` \| `null` | no | The flap codes currently on the board, or null if nothing has been sent to it yet. |
| `text` | `string` \| `null` | no | `characters` decoded back to text, for reading. Null when `characters` is null. |
| `expected_characters` | array of array of `integer` \| `null` | no | The flap grid FiestaBoard last sent to this board. When it differs from `characters` the board has drifted from what was sent — a flap that did not turn, or something else writing to the board. Null until this instance has sent anything. |
| `read_at` | `string` \| `null` | no | When `characters` was read from the board (ISO 8601). Null for a live read. |
| `active_page_id` | `string` \| `null` | no | The page or collection pinned to this board by hand, if any. |
| `scheduled_page_id` | `string` \| `null` | no | The page the schedule selects for right now. Null when scheduling is off or nothing matches. |
| `resolved_page_id` | `string` \| `null` | no | The page actually being displayed, with any collection resolved to a member page. |
| `resolved_next_check_seconds` | `integer` \| `null` | no | Seconds until `resolved_page_id` may change on its own, when it came from a collection that rotates. Poll again after this long rather than on a guessed timer. Null for a plain page and for a collection that cannot rotate. |
| `source` | `"manual"` \| `"schedule"` \| `"none"` | yes | Where `resolved_page_id` came from. |
| `default_page_id` | `string` \| `null` | no | The page shown when the schedule has a gap. |
| `override_expires_at` | `string` \| `null` | no | When the active timed message expires (ISO 8601), or null if none is running. |

### `BoardListResponse` {#schema-boardlistresponse}

`GET /v1/boards`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `boards` | array of [`BoardSummary`](#schema-boardsummary) | yes | — |
| `total` | `integer` | yes | — |

### `BoardStatus` {#schema-boardstatus}

Per-board runtime state (issue #1244).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `configured` | `boolean` | yes | — |
| `paused` | `boolean` | yes | — |
| `active_page_id` | `string` \| `null` | no | — |
| `error` | `string` \| `null` | no | — |

### `BoardSummary` {#schema-boardsummary}

One board, as a consumer needs to see it.

A deliberate projection, not the stored entry: `GET /settings/board`
serves connection credentials (masked) and per-tile wiring, none of which
a consumer writing to a board has any use for.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | The board's stable id. Usable anywhere `{board}` appears in a v1 path. |
| `name` | `string` | yes | Human-readable board name, as set in Settings. |
| `device_type` | `string` | yes | Board hardware: "flagship", "note", or "note_array". |
| `rows` | `integer` | yes | Grid height in flaps. |
| `cols` | `integer` | yes | Grid width in flaps. |
| `is_primary` | `boolean` | yes | True for the board that the alias "primary" resolves to. |
| `paused` | `boolean` | yes | While true, FiestaBoard writes nothing to this board from any code path. |
| `schedule_enabled` | `boolean` | yes | Whether this board follows its schedule rather than a fixed page. |

### `BoardUpdate` {#schema-boardupdate}

`PATCH /v1/boards/{board}` — every field optional, only what you send is applied.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | Rename the board. (min length 1; max length 100) |
| `paused` | `boolean` \| `null` | no | Pause or resume the board. While paused nothing is written to it from any code path. |
| `schedule_enabled` | `boolean` \| `null` | no | Turn this board's schedule on or off. |
| `default_page_id` | `string` \| `null` | no | Page shown when the schedule has a gap. Send null to clear it. |

### `Collection` {#schema-collection}

A collection – an ordered set of pages plus a selection mode.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | no | — |
| `name` | `string` | yes | min length 1; max length 100 |
| `page_ids` | array of `string` | yes | — |
| `selection_mode` | `"time"` \| `"variable"` \| `"random"` | no | default `"time"` |
| `time` | [`TimeModeConfig`](#schema-timemodeconfig) | no | — |
| `variable` | [`VariableModeConfig`](#schema-variablemodeconfig) \| `null` | no | — |
| `random` | [`RandomModeConfig`](#schema-randommodeconfig) \| `null` | no | — |
| `created_at` | `date-time` | no | — |
| `updated_at` | `date-time` \| `null` | no | — |

### `CollectionCreate` {#schema-collectioncreate}

Request model for creating a new collection.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | min length 1; max length 100 |
| `page_ids` | array of `string` | yes | — |
| `selection_mode` | `"time"` \| `"variable"` \| `"random"` | no | default `"time"` |
| `time` | [`TimeModeConfig`](#schema-timemodeconfig) | no | — |
| `variable` | [`VariableModeConfig`](#schema-variablemodeconfig) \| `null` | no | — |
| `random` | [`RandomModeConfig`](#schema-randommodeconfig) \| `null` | no | — |

### `CollectionDeleteResponse` {#schema-collectiondeleteresponse}

Body of `DELETE /collections/{collection_id}`.

Per `docs/internal/reference/API_CONVENTIONS.md` a delete answers 200
with the deleted resource id (this domain's choice) — not a
`{"status": "success"}` envelope.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | — |

### `CollectionListResponse` {#schema-collectionlistresponse}

Body of `GET /collections`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collections` | array of [`Collection`](#schema-collection) | yes | — |
| `total` | `integer` | yes | — |

### `CollectionUpdate` {#schema-collectionupdate}

Request model for updating an existing collection.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | min length 1; max length 100 |
| `page_ids` | array of `string` \| `null` | no | — |
| `selection_mode` | `"time"` \| `"variable"` \| `"random"` \| `null` | no | — |
| `time` | [`TimeModeConfig`](#schema-timemodeconfig) \| `null` | no | — |
| `variable` | [`VariableModeConfig`](#schema-variablemodeconfig) \| `null` | no | — |
| `random` | [`RandomModeConfig`](#schema-randommodeconfig) \| `null` | no | — |

### `ErrorResponse` {#schema-errorresponse}

The single error body the API serves.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `detail` | `string` | yes | — |

### `FormulaFunctionEntry` {#schema-formulafunctionentry}

One built-in formula function, as the function picker lists it.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `category` | `string` | yes | — |
| `signature` | `string` | yes | — |
| `summary` | `string` | yes | — |

### `FormulaFunctionsResponse` {#schema-formulafunctionsresponse}

`GET /templates/formula-functions`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `functions` | object of [`FormulaFunctionEntry`](#schema-formulafunctionentry) | yes | — |

### `HealthResponse` {#schema-healthresponse}

`GET|HEAD /health` — the liveness probe nginx, Docker and the boot
gate all use.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `string` | yes | — |
| `service_running` | `boolean` | yes | — |
| `version` | `string` | yes | — |

### `HTTPValidationError` {#schema-httpvalidationerror}

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `detail` | array of [`ValidationError`](#schema-validationerror) | no | — |

### `IncompatibleReference` {#schema-incompatiblereference}

A reference left pointing this page at a board it no longer fits.

Produced by a device/size retarget (issue #1250, extended by #1788).
Warn-only: the backend never mutates or removes the reference.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` | yes | — |
| `board_name` | `string` | yes | — |
| `surface` | `"schedule"` \| `"active_page"` \| `"silence"` | yes | — |
| `schedule_id` | `string` \| `null` | no | — |

### `LineMetadata` {#schema-linemetadata}

Per-line formatting metadata for template pages.

Stores alignment and wrap settings that were previously encoded as
inline prefixes (`{center}`, `{wrap}`, etc.) in the template strings.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `alignment` | `"left"` \| `"center"` \| `"right"` | no | default `"left"` |
| `wrap` | `boolean` | no | default `false` |

### `MessageRequest (board_api)` {#schema-src-board-api-models-messagerequest}

Body of `POST /send-message`.

`board_id` closes the gap that made board 2 unreachable over HTTP: the
MCP executor (`src.ops.executors.send_message`) has taken one since
issue #1765, and this endpoint — the one the published docs recommend —
had no spelling for it. Omitted → the primary board, which is exactly
what every existing caller gets today.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `string` | yes | — |
| `board_id` | `string` \| `null` | no | — |

### `MessageRequest (v1)` {#schema-src-v1-models-messagerequest}

`POST /v1/boards/{board}/message` — the front door.

Exactly one of `text`, `lines`, `characters`, `page_id` or
`fill` says _what_ to show. Everything else says how long and how.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `string` \| `null` | no | Plain text, word-wrapped to the board. Colour and character markers (`{red}`, `{63}`) work here. |
| `lines` | array of `string` \| `null` | no | One string per board row, laid out without re-wrapping across rows. |
| `characters` | array of array of `integer` \| `null` | no | A raw flap grid, sized exactly to the board. Codes are 0-71. |
| `page_id` | `string` \| `null` | no | Render a saved page (or collection) and send the result. |
| `fill` | `integer` \| `null` | no | Fill the whole board with one flap code (0-71). 0 blanks it. (0–71) |
| `duration_minutes` | `integer` \| `null` | no | Show this for N minutes, then revert. Omit for a message that stays until something else replaces it. (1–480) |
| `revert_mode` | `"schedule"` \| `"page"` \| `"blank"` \| `null` | no | What to show when a timed message expires. Requires duration_minutes. Defaults to "schedule". |
| `revert_page_id` | `string` \| `null` | no | The page to revert to. Required when revert_mode is "page". |
| `transition` | [`TransitionOverride`](#schema-transitionoverride) \| `null` | no | Override the install's transition animation for this one send. |
| `force` | `boolean` | no | Send even when the board already shows this exact content, which is normally skipped. (default `false`) |

### `MessageResponse` {#schema-messageresponse}

What a v1 board write actually did.

`sent` is the honest answer, not an acknowledgement: it is false when
the install's output target is UI-only, when the board already showed
this exact content, and when a timed message was queued for the display
loop rather than written on the spot. `reason` names which.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sent` | `boolean` | yes | True only when flaps were written to the physical board by this request. |
| `board_id` | `string` | yes | The board this went to, with the 'primary' alias already resolved. |
| `characters` | array of array of `integer` | yes | The flap grid this request produced, sent or not. |
| `text` | `string` | yes | `characters` decoded back to text, for logs and confirmations. |
| `expires_at` | `string` \| `null` | no | When a timed message reverts (ISO 8601). Null for a message with no duration. |
| `reason` | `string` \| `null` | no | Why nothing was written, when sent is false. Null when sent is true. |

### `Page` {#schema-page}

A saved page configuration.

Pages can be one of three types:

- single: Displays a single source type
- composite: Combines specific rows from multiple sources
- template: Custom content with templated variables

Each page targets a specific device type (flagship: 22x6, note: 15x3).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | no | — |
| `name` | `string` | yes | min length 1; max length 100 |
| `type` | `"single"` \| `"composite"` \| `"template"` | yes | — |
| `device_type` | `"flagship"` \| `"note"` \| `"note_array"` | no | default `"flagship"` |
| `display_type` | `string` \| `null` | no | — |
| `rows` | array of [`RowConfig`](#schema-rowconfig) \| `null` | no | — |
| `template` | array of `string` \| `null` | no | — |
| `line_metadata` | array of [`LineMetadata`](#schema-linemetadata) \| `null` | no | — |
| `duration_seconds` | `integer` | no | 10–3600; default `300` |
| `transition_strategy` | `string` \| `null` | no | — |
| `transition_interval_ms` | `integer` \| `null` | no | 0–5000 |
| `transition_step_size` | `integer` \| `null` | no | min 1 |
| `demo_plugin_id` | `string` \| `null` | no | — |
| `notes_wide` | `integer` | no | 1–8; default `1` |
| `notes_tall` | `integer` | no | 1–8; default `1` |
| `created_at` | `date-time` | no | — |
| `updated_at` | `date-time` \| `null` | no | — |

### `PageCreate` {#schema-pagecreate}

Request model for creating a new page.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` | yes | min length 1; max length 100 |
| `type` | `"single"` \| `"composite"` \| `"template"` | yes | — |
| `device_type` | `"flagship"` \| `"note"` \| `"note_array"` | no | default `"flagship"` |
| `display_type` | `string` \| `null` | no | — |
| `rows` | array of [`RowConfig`](#schema-rowconfig) \| `null` | no | — |
| `template` | array of `string` \| `null` | no | — |
| `line_metadata` | array of [`LineMetadata`](#schema-linemetadata) \| `null` | no | — |
| `duration_seconds` | `integer` | no | 10–3600; default `300` |
| `transition_strategy` | `string` \| `null` | no | — |
| `transition_interval_ms` | `integer` \| `null` | no | 0–5000 |
| `transition_step_size` | `integer` \| `null` | no | min 1 |
| `demo_plugin_id` | `string` \| `null` | no | — |
| `notes_wide` | `integer` \| `null` | no | 1–8 |
| `notes_tall` | `integer` \| `null` | no | 1–8 |

### `PageDeleteResponse` {#schema-pagedeleteresponse}

`DELETE /pages/{page_id}` — the deleted id plus what else moved.

Deleting the last page auto-creates a default welcome page, and deleting
the active page re-points the active reference; both are reported here so
the client can follow without re-fetching everything.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | — |
| `message` | `string` | yes | — |
| `default_page_created` | `boolean` | no | default `false` |
| `new_page_id` | `string` \| `null` | no | — |
| `active_page_updated` | `boolean` | no | default `false` |
| `new_active_page_id` | `string` \| `null` | no | — |

### `PageListResponse` {#schema-pagelistresponse}

`GET /pages` — every saved page, plus the count.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pages` | array of [`Page`](#schema-page) | yes | — |
| `total` | `integer` | yes | — |

### `PageUpdate` {#schema-pageupdate}

Request model for updating an existing page.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `string` \| `null` | no | min length 1; max length 100 |
| `device_type` | `"flagship"` \| `"note"` \| `"note_array"` \| `null` | no | — |
| `display_type` | `string` \| `null` | no | — |
| `rows` | array of [`RowConfig`](#schema-rowconfig) \| `null` | no | — |
| `template` | array of `string` \| `null` | no | — |
| `line_metadata` | array of [`LineMetadata`](#schema-linemetadata) \| `null` | no | — |
| `duration_seconds` | `integer` \| `null` | no | 10–3600 |
| `transition_strategy` | `string` \| `null` | no | — |
| `transition_interval_ms` | `integer` \| `null` | no | 0–5000 |
| `transition_step_size` | `integer` \| `null` | no | min 1 |
| `notes_wide` | `integer` \| `null` | no | 1–8 |
| `notes_tall` | `integer` \| `null` | no | 1–8 |

### `PageUpdateResponse` {#schema-pageupdateresponse}

`PUT /pages/{page_id}` — the updated page and its stale references.

Not a bare `Page` because the retarget warning is genuine payload, not
an envelope: the editor shows it to the user after a size change.
`incompatible_references` is always present and empty when the update
did not change the page's size.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `page` | [`Page`](#schema-page) | yes | — |
| `incompatible_references` | array of [`IncompatibleReference`](#schema-incompatiblereference) | no | — |

### `PluginData` {#schema-plugindata}

`GET /v1/plugins/{plugin}/data` — the merge of the raw and formatted reads.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plugin_id` | `string` | yes | — |
| `available` | `boolean` | yes | False when the plugin is disabled, unconfigured, or its fetch failed. |
| `data` | `object` \| `null` | no | The plugin's own variable payload. |
| `lines` | array of `string` | no | The plugin's board-ready lines, as GET /displays/`{type}` served them. |
| `text` | `string` | no | `lines` joined with newlines. (default `""`) |
| `error` | `string` \| `null` | no | Why the data is unavailable, when it is. |

### `PluginDetail` {#schema-plugindetail}

`GET /plugins/{plugin_id}` — derived, masked, and its own model.

`config` is the **stored** configuration with sensitive values masked,
deliberately _without_ the env-var overlay: this response feeds the
settings form, and any value baked in here comes straight back in the next
save, so serving the overlay would freeze env values into `config.json`
(#1864 review). Which keys the environment currently controls is reported
separately in `env_overridden_keys`, values excluded.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | — |
| `name` | `string` | yes | — |
| `version` | `string` | yes | — |
| `description` | `string` | no | default `""` |
| `author` | `string` | no | default `""` |
| `icon` | `string` \| `null` | no | — |
| `category` | `string` \| `null` | no | — |
| `plugin_type` | `string` | no | default `"data"` |
| `enabled` | `boolean` | yes | — |
| `config` | `object` | yes | — |
| `env_overridden_keys` | array of `string` | yes | — |
| `settings_schema` | `object` | yes | — |
| `variables` | `object` | yes | — |
| `max_lengths` | `object` | yes | — |
| `env_vars` | array of `any` | yes | — |
| `documentation` | `string` \| `null` | no | — |
| `has_demo` | `boolean` | yes | — |
| `demo_page_id` | `string` \| `null` | no | — |
| `instance_label` | `string` \| `null` | no | — |
| `base_plugin_id` | `string` \| `null` | no | — |
| `instances` | array of [`PluginInstanceInfo`](#schema-plugininstanceinfo) | yes | — |

### `PluginEntry` {#schema-pluginentry}

One plugin in the merged catalogue.

`GET /plugins` and `GET /displays` are the same registry listing seen
twice — `/displays` is a four-field projection of it. v1 publishes one
catalogue, with the display projection's `available` folded in.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | Plugin id. Usable anywhere `{plugin}` appears in a v1 path. |
| `name` | `string` | yes | — |
| `version` | `string` | yes | — |
| `description` | `string` | no | default `""` |
| `author` | `string` | no | default `""` |
| `category` | `string` \| `null` | no | — |
| `plugin_type` | `string` | no | "data" for a content source, "transition" for an animation. (default `"data"`) |
| `icon` | `string` \| `null` | no | — |
| `enabled` | `boolean` | yes | Whether this plugin runs and contributes template variables. |
| `configured` | `boolean` | yes | Whether its required settings have been filled in. |

### `PluginInstanceInfo` {#schema-plugininstanceinfo}

One named instance of a plugin.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `label` | `string` | yes | — |
| `key` | `string` \| `null` | no | — |
| `enabled` | `boolean` | no | default `false` |
| `has_config` | `boolean` | no | default `false` |

### `PluginListResponse` {#schema-pluginlistresponse}

`GET /v1/plugins`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plugins` | array of [`PluginEntry`](#schema-pluginentry) | yes | — |
| `total` | `integer` | yes | — |
| `enabled_count` | `integer` | yes | — |

### `PluginReceiveResponse` {#schema-pluginreceiveresponse}

`POST /plugins/{plugin_id}/receive`.

The `status` key survives the conventions pass on purpose: this endpoint
is a **webhook target for third-party systems** (CI pipelines, home
automations) that this repo does not control and cannot update in lockstep.
"Deprecation, never deletion" applies to it more literally than to any
browser-facing route. `plugin_id` is added so the ack names what it
acked.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | `string` | no | default `"ok"` |
| `plugin_id` | `string` | yes | — |

### `PluginUpdate` {#schema-pluginupdate}

`PATCH /v1/plugins/{plugin}`.

Collapses `POST /plugins/{plugin_id}/enable`,
`POST /plugins/{plugin_id}/disable` and `PUT /plugins/{plugin_id}/config`
into one call. `config` stays a free-form map on purpose: a typed body would
reject the `"***"` sentinel the API serves in place of a stored secret,
which is what a client round-trips when it edits one field of a form.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | `boolean` \| `null` | no | Enable or disable the plugin. |
| `config` | `object` \| `null` | no | Replace the plugin's settings. Send "***" for a secret you do not want to change. |

### `RandomModeConfig` {#schema-randommodeconfig}

Settings for random page selection.

`interval_seconds` is the page duration — how long each randomly chosen
page is shown before a new one is selected.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `interval_seconds` | `integer` | no | 5–86400; default `30` |

### `RefreshRequest` {#schema-refreshrequest}

Optional body of `POST /refresh`.

`board_id` may also arrive as a query parameter; the query wins when
both are present, which is what the pre-conversion handler did.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` \| `null` | no | — |

### `RefreshResponse` {#schema-refreshresponse}

`POST /refresh` — what the refresh pass did.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | yes | — |
| `board_id` | `string` \| `null` | no | — |
| `sent` | `boolean` | yes | — |

### `RenderRequest` {#schema-renderrequest}

`POST /v1/render` — render a template without saving or sending it.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template` | `string` \| array of `string` | yes | A template string, or one string per board row. A list is padded to the board's height. |
| `line_metadata` | array of `object` \| `null` | no | Per-line alignment and wrap options, one entry per line. |

### `RowConfig` {#schema-rowconfig}

Configuration for a single row in a composite page.

Specifies which row from which source should be placed at which position.
Row limits depend on the device type of the parent page.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | `string` | yes | — |
| `row_index` | `integer` | yes | min 0 |
| `target_row` | `integer` | yes | min 0 |

### `ScheduleCreate` {#schema-schedulecreate}

Request model for creating a new schedule entry.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` | no | min length 0; default `""` |
| `page_id` | `string` | yes | min length 1 |
| `start_time` | `string` | yes | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` | no | default `"all"` |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` | no | default `true` |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` | no | default `"weekly"` |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `start_sun_offset` | `integer` | no | default `0` |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `end_sun_offset` | `integer` | no | default `0` |

### `ScheduleDeleteResponse` {#schema-scheduledeleteresponse}

The id of the schedule that was deleted.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | yes | — |

### `ScheduleListResponse` {#schema-schedulelistresponse}

What `GET /schedules` answers with.

`default_page_id` and `enabled` are per-board, so both are `null` on
the cross-board listing (`board_id=*`) — that listing has no single board
to answer for.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schedules` | array of [`ScheduleResponse`](#schema-scheduleresponse) | yes | — |
| `total` | `integer` | yes | — |
| `default_page_id` | `string` \| `null` | no | — |
| `enabled` | `boolean` \| `null` | no | — |

### `ScheduleResponse` {#schema-scheduleresponse}

A schedule as the API serves it: the stored entry plus today's times.

`resolved_*` equals the stored time for fixed schedules and the computed
sunrise/sunset time for sun-based ones, so a client never has to know the
install's location to render the window.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | no | — |
| `board_id` | `string` | no | min length 0; default `""` |
| `page_id` | `string` | yes | min length 1 |
| `start_time` | `string` | yes | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` | no | default `"all"` |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` | no | default `true` |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` | no | default `"weekly"` |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `start_sun_offset` | `integer` | no | default `0` |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `end_sun_offset` | `integer` | no | default `0` |
| `created_at` | `date-time` | no | — |
| `updated_at` | `date-time` \| `null` | no | — |
| `resolved_start_time` | `string` | yes | — |
| `resolved_end_time` | `string` \| `null` | no | — |

### `ScheduleUpdate` {#schema-scheduleupdate}

Request model for updating an existing schedule entry.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `board_id` | `string` \| `null` | no | min length 0 |
| `page_id` | `string` \| `null` | no | min length 1 |
| `start_time` | `string` \| `null` | no | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` \| `null` | no | — |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` \| `null` | no | — |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` \| `null` | no | — |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` \| `null` | no | — |
| `start_sun_offset` | `integer` \| `null` | no | — |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` \| `null` | no | — |
| `end_sun_offset` | `integer` \| `null` | no | — |

### `ScheduleWriteResponse` {#schema-schedulewriteresponse}

What create and update answer with.

`warnings` carries the non-fatal page&lt;->board size mismatches of issue
\#1245 — a collection may mix page sizes, and the write is allowed as long
as one member fits. The key was previously _omitted_ when there was nothing
to warn about, so a client could not tell "no warnings" from "this server
doesn't report warnings"; it is now always present and empty when clean.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | `string` | no | — |
| `board_id` | `string` | no | min length 0; default `""` |
| `page_id` | `string` | yes | min length 1 |
| `start_time` | `string` | yes | — |
| `end_time` | `string` \| `null` | no | — |
| `day_pattern` | `"all"` \| `"weekdays"` \| `"weekends"` \| `"custom"` | no | default `"all"` |
| `custom_days` | array of `string` \| `null` | no | — |
| `enabled` | `boolean` | no | default `true` |
| `recurrence_type` | `"weekly"` \| `"annual_date"` \| `"one_off_date"` | no | default `"weekly"` |
| `annual_date` | `string` \| `null` | no | — |
| `annual_end_date` | `string` \| `null` | no | — |
| `one_off_date` | `string` \| `null` | no | — |
| `one_off_end_date` | `string` \| `null` | no | — |
| `start_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `start_sun_offset` | `integer` | no | default `0` |
| `end_type` | `"fixed"` \| `"sunrise"` \| `"sunset"` | no | default `"fixed"` |
| `end_sun_offset` | `integer` | no | default `0` |
| `created_at` | `date-time` | no | — |
| `updated_at` | `date-time` \| `null` | no | — |
| `resolved_start_time` | `string` | yes | — |
| `resolved_end_time` | `string` \| `null` | no | — |
| `warnings` | array of `string` | no | — |

### `SendResponse` {#schema-sendresponse}

The outcome of an out-of-band write.

`sent` is False when the content was identical to what the board
already shows — the write was correctly skipped, not refused. Every other
non-delivery (paused board, silence window, send floor, board failure) is
a status code, not a flag.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | yes | — |
| `sent` | `boolean` | yes | — |

### `StatusResponse` {#schema-statusresponse}

`GET /status` — the display loop's state plus a per-board breakdown.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `running` | `boolean` | yes | — |
| `initialized` | `boolean` | yes | — |
| `config_summary` | `object` | yes | — |
| `boards` | object of [`BoardStatus`](#schema-boardstatus) | no | default `{}` |

### `TemplateRenderResponse` {#schema-templaterenderresponse}

`POST /templates/render`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rendered` | `string` | yes | — |
| `lines` | array of `string` | yes | — |
| `line_count` | `integer` | yes | — |

### `TimeModeConfig` {#schema-timemodeconfig}

Settings for time-based rotation (classic carousel).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `interval_seconds` | `integer` | no | 5–86400; default `30` |

### `TransitionOverride` {#schema-transitionoverride}

Per-send transition animation, overriding the install's settings.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `strategy` | `string` \| `null` | no | Transition strategy name, e.g. "instant" or "wipe". |
| `interval_ms` | `integer` \| `null` | no | Milliseconds between animation steps. (0–5000) |
| `step_size` | `integer` \| `null` | no | Flaps advanced per animation step. (min 1) |

### `ValidationError` {#schema-validationerror}

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `loc` | array of `string` \| `integer` | yes | — |
| `msg` | `string` | yes | — |
| `type` | `string` | yes | — |
| `input` | `any` | no | — |
| `ctx` | `object` | no | — |

### `VariableCatalog` {#schema-variablecatalog}

`GET /v1/variables` — every name a template may use, from both sources.

Merges `GET /templates/variables` (the engine's vocabulary plus the
static colour, symbol and filter tables) with `GET
/plugins/variables/all` (what installed plugins contribute). They were
two endpoints answering one question.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `variables` | object of array of `string` | yes | Variable names grouped by their source namespace. |
| `max_lengths` | object of `integer` | yes | Longest value each variable can render to, for layout. |
| `variable_metadata` | `object` | no | Per-variable descriptions and types. |
| `variable_groups` | `object` | no | Display grouping for editors. |
| `colors` | object of `integer` | yes | Colour names to flap codes, e.g. &#123;"red": 63&#125;. |
| `symbols` | array of `string` | yes | Symbol names usable as `{sun}`, `{star}` and so on. |
| `filters` | array of `string` | yes | Filters usable after a variable, e.g. &#123;&#123;x\|pad:5&#125;&#125;. |
| `formatting` | `object` | yes | Layout helpers such as fill_space. |
| `syntax_examples` | object of `string` | yes | Worked examples of the template syntax. |
| `plugin_system_enabled` | `boolean` | yes | False when the plugin subsystem is unavailable on this install. |

### `VariableModeConfig` {#schema-variablemodeconfig}

Settings for variable-driven page selection.

`rules` are evaluated in order; the first one whose expression returns
a truthy non-error value wins. If no rule matches (or all error), the
collection falls back to `default_page_id`.

`poll_seconds` controls how often the active-page loop re-evaluates
the rules.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `rules` | array of [`VariableRule`](#schema-variablerule) | no | — |
| `default_page_id` | `string` | yes | min length 1 |
| `poll_seconds` | `integer` | no | 2–600; default `10` |

### `VariableRule` {#schema-variablerule}

A single (expression, page_id) selection rule.

The `expression` is evaluated by the template expression engine. A
truthy non-error result selects `page_id` as the active page.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `expression` | `string` | yes | min length 1 |
| `page_id` | `string` | yes | min length 1 |

## Where the rest of the API went

This page documents the 33 operations the app publishes. The other
~200 paths the app serves are the web UI's private RPC channel: they still
answer exactly as they always have, but they are undocumented on purpose,
carry no compatibility promise, and may change in any release. They are
published separately at `/api/internal/openapi.json` so the UI keeps a
contract to check itself against.

## Next steps

- [Docker Setup](/docs/setup/docker-setup) — how the API is served and proxied
- [Plugin Configuration](/docs/plugins/configuration) — configuring plugins over the API
- `/api/docs` — the same operations as a Swagger explorer you can send requests from
