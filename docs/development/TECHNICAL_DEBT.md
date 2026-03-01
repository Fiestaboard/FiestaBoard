# Technical Debt

This document tracks known technical debt in FiestaBoard, including deprecated APIs and planned cleanup work.

---

## Deprecated API Endpoints

### 1. Board Configuration Alias

| Type | Path | Status |
|------|------|--------|
| **Canonical** | `GET /config/board` | Active |
| **Canonical** | `PUT /config/board` | Active |
| **Deprecated** | `GET /config/vestaboard` | Deprecated - returns `Deprecation: true` header |
| **Deprecated** | `PUT /config/vestaboard` | Deprecated - returns `Deprecation: true` header |

The `/config/vestaboard` paths are backward-compatibility aliases kept after the plugin architecture migration. They redirect to `/config/board` and will be removed in a future major release.

**Migration:** Replace calls to `/config/vestaboard` with `/config/board`. See [API Migration Guide](./API_MIGRATION.md).

---

### 2. Display Raw Data

| Type | Path | Status |
|------|------|--------|
| **Canonical** | `GET /plugins/{plugin_id}/data` | Active |
| **Deprecated** | `GET /displays/{display_type}/raw` | Deprecated - returns `Deprecation: true` header |

After the plugin architecture migration, plugin data should be retrieved via `/plugins/{plugin_id}/data`. The old `/displays/{display_type}/raw` endpoint remains for backward compatibility and will be removed in a future major release.

**Migration:** Replace calls to `/displays/{type}/raw` with `/plugins/{plugin_id}/data`. See [API Migration Guide](./API_MIGRATION.md).

---

## Deprecation Timeline

| Endpoint | Deprecated Since | Planned Removal |
|----------|-----------------|-----------------|
| `GET /config/vestaboard` | v1.x | v2.0 |
| `PUT /config/vestaboard` | v1.x | v2.0 |
| `GET /displays/{type}/raw` | v1.x | v2.0 |

---

## Other Known Debt

*This section will be updated as additional technical debt is identified.*

---

## Archived / Legacy Packages (Pre-2.0)

The following Python packages predate the v2.0 migration to Docker and the plugin
architecture. They are retained **only** for backward compatibility and are
scheduled for removal in a future major release. Each package emits a
`DeprecationWarning` on import.

| Package | Replacement | Description |
|---------|-------------|-------------|
| `src/utils/` | `plugins/*` | Feature data-source utilities (weather, stocks, transit, etc.) migrated to the plugin system |
| `src/formatters/` | `src/templates/` | Message formatting logic replaced by the template engine |
| `src/system/` | Docker infrastructure | System management (mDNS, container control) replaced by Docker-based architecture |

### Migration notes

* **Data sources** — use the corresponding plugin under `plugins/` (e.g.
  `plugins/weather/`, `plugins/stocks/`). See [Plugin Development](./PLUGIN_DEVELOPMENT.md).
* **Message formatting** — the template engine in `src/templates/` now handles
  all board rendering.
* **Config migration** — `scripts/migrate_config_to_plugins.py` converts the
  legacy `config.features.*` format to the current `config.plugins.*` format.
