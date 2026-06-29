# API Migration Guide

This guide helps developers migrate from deprecated FiestaBoard API endpoints to their canonical replacements.

---

## Display Raw Data: `/displays/{type}/raw` → `/plugins/{plugin_id}/data`

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

> **Note:** The new endpoint also returns `formatted_lines` — an array of up to six pre-formatted display lines from the plugin's `PluginResult.formatted_lines`. This is `null` when the plugin does not pre-format its output.

The new endpoint returns **HTTP 503** whenever plugin data is unavailable (not configured, auth failure, network error). The error detail message comes from `PluginResult.error`, falling back to `"Plugin data not available"`.

The old endpoint behaves differently depending on whether an error message is set. It returns 503 only when data is unavailable **and** `PluginResult.error` is present; when data is unavailable but no error message is set — for example, a plugin that is simply unconfigured — it returns `200 {"available": false}`.

> **Note:** Don't assume the old endpoint never returns 503. An integrator migrating to the new endpoint should handle 503 in both cases; the change is that the new endpoint returns 503 for *every* unavailable result, not just the ones carrying an error message.

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
