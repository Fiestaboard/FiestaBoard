# API Migration Guide

This guide helps developers migrate from deprecated FiestaBoard API endpoints to their canonical replacements.

---

## Board Configuration: `/config/vestaboard` → `/config/board`

The `/config/vestaboard` endpoints are deprecated. Use `/config/board` instead.

### GET - Retrieve board configuration

**Deprecated (returns `Deprecation: true` header):**
```
GET /config/vestaboard
```

**Canonical:**
```
GET /config/board
```

**Example response (both endpoints return the same shape):**
```json
{
  "config": {
    "api_mode": "local",
    "host": "192.168.1.100",
    "local_api_key": "***"
  },
  "api_modes": ["local", "cloud"]
}
```

### PUT - Update board configuration

**Deprecated (returns `Deprecation: true` header):**
```
PUT /config/vestaboard
```

**Canonical:**
```
PUT /config/board
```

**Example request body:**
```json
{
  "api_mode": "local",
  "local_api_key": "your-key",
  "host": "192.168.1.100"
}
```

---

## Display Raw Data: `/displays/{type}/raw` → `/plugins/{plugin_id}/data`

The `/displays/{display_type}/raw` endpoint is deprecated. Use `/plugins/{plugin_id}/data` instead.

### GET - Retrieve plugin/display data

**Deprecated (returns `Deprecation: true` header):**
```
GET /displays/{display_type}/raw
```

**Canonical:**
```
GET /plugins/{plugin_id}/data
```

The `display_type` and `plugin_id` values are the same identifiers (e.g., `weather`, `datetime`, `stocks`).

**Example - old endpoint:**
```
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

**Example - new endpoint:**
```
GET /plugins/weather/data
```
```json
{
  "plugin_id": "weather",
  "available": true,
  "data": { "temperature": 72, "condition": "Sunny" },
  "formatted": "Sunny, 72°F\nSan Francisco",
  "error": null
}
```

> **Note:** The new endpoint also returns a `formatted` field with the pre-formatted display output.

---

## Detecting Deprecation Headers

Deprecated endpoints include the following HTTP response headers:

```
Deprecation: true
Link: </config/board>; rel="successor-version"
```

You can use these headers to detect and log warnings in your integration code.

---

## See Also

- [Technical Debt](./TECHNICAL_DEBT.md) - full list of deprecated endpoints and removal timeline
- [Plugin Development Guide](./PLUGIN_DEVELOPMENT.md)
