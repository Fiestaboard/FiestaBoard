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

The new endpoint also changes failure mode: it returns HTTP **503** when plugin data is unavailable instead of `200 {"available": false}`. Callers that rely on the old success-with-flag behaviour need to handle the 503.

**Migration:** Replace calls to `/displays/{type}/raw` with `/plugins/{plugin_id}/data`. See [API Migration Guide](./API_MIGRATION.md).

---

## Deprecation Timeline

| Endpoint | Deprecated Since | Planned Removal |
|----------|-----------------|-----------------|
| `GET /displays/{type}/raw` | v1.x | TBD |

> **Note:** The v2.0 removal target has passed. As of v7.7.1 the endpoint is still present at `src/api_server.py` because external integrations continue to depend on it. No new target version has been set. If you are a maintainer planning removal, update this table and the [API Migration Guide](./API_MIGRATION.md) before cutting the release.

---

## Dead Code

### Unregistered `/config/vestaboard` compat shims

`src/api_server.py` defines `get_board_config_compat()` and `update_board_config_compat()` to redirect callers from the historical `/config/vestaboard` paths to `/config/board`, but neither function is registered as a FastAPI route — there's no `@app.get("/config/vestaboard")` or `@app.put(...)` binding. The functions are unreachable.

**Cleanup:** Delete both functions. The historical paths already return 404 to clients, so no migration window is needed.

---

## Other Known Debt

*This section will be updated as additional technical debt is identified.*
