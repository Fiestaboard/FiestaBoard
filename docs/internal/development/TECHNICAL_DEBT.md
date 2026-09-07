# Technical Debt

This document tracks known technical debt in FiestaBoard, including deprecated APIs and planned cleanup work.

---

## Deprecated API Endpoints

### Display Raw Data

| Type | Path | Status |
|------|------|--------|
| **Canonical** | `GET /plugins/{plugin_id}/data` | Active |
| **Retired** | `GET /displays/{display_type}/raw` | Answers `410 Gone` (issue #1911) |

After the plugin architecture migration, plugin data should be retrieved via `/plugins/{plugin_id}/data`. The old `/displays/{display_type}/raw` endpoint has been **retired**: it no longer serves data and answers `410 Gone`, carrying `Deprecation: true`, a `Sunset` date, and a `Link: rel="successor-version"` header pointing at `/plugins/{plugin_id}/data`.

The successor endpoint changes failure mode. It returns HTTP **503** whenever plugin data is unavailable. The old endpoint returned 503 only when an error message was present, and otherwise returned `200 {"available": false}` (for example, when a plugin was merely unconfigured). Callers that relied on the old success-with-flag behaviour need to handle the 503 in every unavailable case.

The old endpoint also answered **503** for an unknown `display_type`, conflating "does not exist" with "temporarily down". The successor does not carry that over: it answers **404** for an unknown plugin, **400** for a disabled one, and reserves **503** for a genuinely unavailable source.

**Migration:** Replace calls to `/displays/{display_type}/raw` with `/plugins/{plugin_id}/data`. See [API Migration Guide](./API_MIGRATION.md).

---

## Deprecation Timeline

| Endpoint | Deprecated Since | Removed |
|----------|-----------------|---------|
| `GET /displays/{display_type}/raw` | v1.x | Retired — answers `410 Gone` (issue #1911) |

> **Note:** The route is retained only as a `410 Gone` tombstone so external integrations that never migrated get a self-describing signal (successor `Link` + `Sunset`) rather than a bare 404. It can be deleted outright in a later major release once traffic has drained.

---

## Other Known Debt

*This section will be updated as additional technical debt is identified.*
