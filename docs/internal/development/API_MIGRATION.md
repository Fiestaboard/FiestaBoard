# API Migration Guide

This guide helps developers migrate from deprecated FiestaBoard API endpoints to their canonical replacements.

---

## Display Raw Data: `/displays/{display_type}/raw` → `/plugins/{plugin_id}/data`

The `/displays/{display_type}/raw` endpoint is deprecated. Use `/plugins/{plugin_id}/data` instead.

### GET - Retrieve plugin/display data

**Deprecated (returns `Deprecation: true` header):**

```http
GET /displays/{display_type}/raw
```

**Canonical:**

```http
GET /plugins/{plugin_id}/data
```

The `display_type` and `plugin_id` values are the same identifiers (e.g., `weather`, `date_time`, `stocks`).

**Example — old endpoint:**

```http
GET /displays/weather/raw
```

```json
{
  "display_type": "weather",
  "data": { "temperature": 72, "condition": "Sunny" },
  "available": true,
  "error": null
}
```

**Example — new endpoint:**

```http
GET /plugins/weather/data
```

```json
{
  "plugin_id": "weather",
  "available": true,
  "data": { "temperature": 72, "condition": "Sunny" },
  "formatted_lines": ["Sunny, 72F", "San Francisco", "", "", "", ""],
  "error": null
}
```

> **Note:** The new endpoint also returns `formatted_lines` — an array of pre-formatted display lines from the plugin's `PluginResult.formatted_lines`. The array length matches the board height (6 lines on a Flagship, 3 on a Note), so don't hardcode six. This is `null` when the plugin does not pre-format its output. See [Pre-formatted content in PLUGIN_DEVELOPMENT.md](./PLUGIN_DEVELOPMENT.md#pre-formatted-content-formatted_lines-vs-get_formatted_display) for details.

The new endpoint returns **HTTP 503** whenever plugin data is unavailable (not configured, auth failure, network error). The error detail message comes from `PluginResult.error`, falling back to `"Plugin data not available"`.

The old endpoint behaves differently depending on whether an error message is set. It returns 503 only when data is unavailable **and** `PluginResult.error` is present; when data is unavailable but no error message is set — for example, a plugin that is simply unconfigured — it returns `200 {"available": false}`.

> **Note:** Don't assume the old endpoint never returns 503. An integrator migrating to the new endpoint should handle 503 in both cases; the change is that the new endpoint returns 503 for *every* unavailable result, not just the ones carrying an error message.

### Status codes

The new endpoint returns four status codes. The old `/displays/{display_type}/raw` endpoint only ever produced **200** and **503**, so add handling for **404** and **400** when you migrate.

| Status | Meaning | `detail` message |
| --- | --- | --- |
| `200` | Success — data available. | — |
| `404` | Plugin not found. The `plugin_id` is unknown. | `Plugin not found: {plugin_id}` |
| `400` | Plugin found but disabled. Enable it on the Integrations page first. | `Plugin not enabled: {plugin_id}` |
| `503` | Plugin data unavailable (not configured, auth failure, network error), or the plugin system is not available. | `PluginResult.error`, falling back to `Plugin data not available` |

**Example — plugin not found (404):**

```http
GET /plugins/does_not_exist/data
```

```json
{
  "detail": "Plugin not found: does_not_exist"
}
```

**Example — plugin disabled (400):**

```http
GET /plugins/weather/data
```

```json
{
  "detail": "Plugin not enabled: weather"
}
```

---

## Detecting Deprecation Headers

Deprecated endpoints include the following HTTP response headers:

```http
Deprecation: true
Link: </plugins/{plugin_id}/data>; rel="successor-version"
```

The `Link` header value points at the canonical successor for that specific request — e.g. a call to `/displays/weather/raw` returns `Link: </plugins/weather/data>; rel="successor-version"`. Use these headers to detect deprecated calls in your integration code.

---

## See Also

- [Technical Debt](./TECHNICAL_DEBT.md) — full list of deprecated endpoints and removal timeline
- [Plugin Development Guide](./PLUGIN_DEVELOPMENT.md)
