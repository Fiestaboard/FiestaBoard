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

### Plugin-specific platform routes (issue #1915)

Eleven routes in `src/api_server.py` each serve a single plugin, which
`CLAUDE.md` forbids for `src/` code ("Do NOT add plugin-specific code to
`src/`"). They predate the generic per-plugin options mechanism
(`GET /plugins/{id}/options/{options_id}`) that replaced the pickers that used
them.

| Path | Plugin |
|------|--------|
| `GET /baywheels/stations` | lyft_bike_share |
| `GET /baywheels/stations/nearby` | lyft_bike_share |
| `GET /baywheels/stations/search` | lyft_bike_share |
| `GET /muni/stops` | muni |
| `GET /muni/stops/nearby` | muni |
| `GET /muni/stops/search` | muni |
| `GET /transit/cache/status` | muni (shared transit cache) |
| `GET /stocks/search` | stocks |
| `POST /stocks/validate` | stocks |
| `POST /traffic/routes/geocode` | traffic |
| `POST /traffic/routes/validate` | traffic |

All eleven return `Deprecation: true` and a `Sunset` header. They are
deprecated rather than deleted because the muni and stocks routes are published
as "API Endpoints" in the `fiestaboard-plugin--muni` and
`fiestaboard-plugin--stocks` SETUP guides, so a third-party integration this
repo cannot see may depend on them.

**Before removal:** the muni and stocks plugin repos must ship SETUP guides
that no longer advertise these routes. Then, after the sunset date, delete the
handlers, the `src/utils/{baywheels,traffic,stocks,transit_cache}.py` code they
alone reach, the web client wrappers in `web/src/lib/api.ts`, and their cases
in `web/src/__tests__/api-extended.test.ts`, then re-record
`tests/golden/api_routes.json`. Anything a plugin genuinely still needs should
become a plugin `options` provider instead of a platform route.

---

## Deprecation Timeline

| Endpoint | Deprecated Since | Planned Removal |
|----------|-----------------|-----------------|
| `GET /displays/{display_type}/raw` | v1.x | TBD |
| Plugin-specific platform routes (11, see above) | v8.34.x | Sunset 2027-09-01 |

> **Note:** No removal version has been scheduled for `/displays/{display_type}/raw`. The plugin-specific routes carry a `Sunset: Wed, 01 Sep 2027 00:00:00 GMT` header as a placeholder deprecation window; align it to a concrete release before cutting the removal. When a removal window is decided, set a new target version in the table above and update the [API Migration Guide](./API_MIGRATION.md) before cutting the release.

---

## Other Known Debt

*This section will be updated as additional technical debt is identified.*
