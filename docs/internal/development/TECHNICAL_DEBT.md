# Technical Debt

This document tracks known technical debt in FiestaBoard, including deprecated APIs and planned cleanup work.

---

## Deprecated API Endpoints

### Display Raw Data

| Type | Path | Status |
|------|------|--------|
| **Canonical** | `GET /plugins/{plugin_id}/data` | Active |
| **Deprecated** | `GET /displays/{display_type}/raw` | Returns `Deprecation: true` header |

After the plugin architecture migration, plugin data should be retrieved via `/plugins/{plugin_id}/data`. The old `/displays/{display_type}/raw` endpoint remains for backward compatibility and will be removed in a future major release.

The new endpoint also changes failure mode. It returns HTTP **503** whenever plugin data is unavailable. The old endpoint returns 503 only when an error message is present, and otherwise returns `200 {"available": false}` (for example, when a plugin is merely unconfigured). Callers that rely on the old success-with-flag behaviour need to handle the 503 in every unavailable case.

**Migration:** Replace calls to `/displays/{display_type}/raw` with `/plugins/{plugin_id}/data`. See [API Migration Guide](./API_MIGRATION.md).

---

## Deprecation Timeline

| Endpoint | Deprecated Since | Planned Removal |
|----------|-----------------|-----------------|
| `GET /displays/{display_type}/raw` | v1.x | `Sunset: Tue, 01 Dec 2026 00:00:00 GMT` (#1941) |

> **Note:** The route sends the shared `Sunset` date on every response (it is in `SUPERSEDED_BY_V1`, `src/api_deprecation.py`) and is deleted with the rest of that cohort in #1941, not before. The `Link` header names `/api/v1/plugins/{plugin_id}/data` as the successor; `/plugins/{plugin_id}/data` is itself in the same cohort.

---

## Other Known Debt

*This section will be updated as additional technical debt is identified.*
