---
sidebar_position: 6
description: "Upgrade guide for migrating from FiestaBoard V2 to V3. Covers the new external plugin system, plugin registry, Git-based plugin installs, and API changes."
keywords: [FiestaBoard V3, migration guide, upgrade, breaking changes, external plugins, plugin registry, plugin install]
---

# V3 Migration Guide

FiestaBoard V3 introduces an **external plugin system** that lets you install community plugins from a curated registry or from any public git repository. This guide covers the breaking changes and what you need to do to migrate from V2.

:::note
V3 is backward compatible for all existing plugin configurations, pages, and board settings. When you start FiestaBoard V3 for the first time, it automatically detects any plugins you had configured in V2 and installs them from the registry — no manual steps required. Your API keys, settings, and enabled/disabled states are preserved exactly as you left them.
:::

## What's New in V3

| Feature | Description |
|---------|-------------|
| **Plugin registry** | A curated list of community plugins maintained in `plugin-registry.json`. Install them with a single API call. |
| **Git-based plugin installs** | Install a plugin from any public HTTPS git repository. No need to fork the FiestaBoard repo. |
| **External plugins directory** | External plugins are cloned into `external_plugins/` and persist across container restarts. |
| **Plugin source tracking** | The API now reports where each plugin was loaded from (`builtin` or `external`). |
| **Plugin uninstall** | External plugins can be removed via API. Built-in plugins cannot be uninstalled. |
| **Registry naming convention** | Plugins submitted to the official registry must follow the `fiestaboard-plugin--{name}` repository naming convention. |
| **Plugin extraction plan** | API-dependent plugins (weather, traffic, home_assistant, etc.) will be extracted into standalone repositories over time. |

---

## Breaking Changes

### 1. Plugin list API response includes a `source` field

The `GET /plugins` endpoint now includes a `source` object for each plugin, describing where it was loaded from.

**V2 response (per plugin):**
```json
{
  "id": "weather",
  "name": "Weather",
  "version": "1.0.0",
  "enabled": true,
  "icon": "cloud-sun",
  "category": "weather"
}
```

**V3 response (per plugin):**
```json
{
  "id": "weather",
  "name": "Weather",
  "version": "1.0.0",
  "enabled": true,
  "icon": "cloud-sun",
  "category": "weather",
  "source": {
    "source_type": "builtin",
    "repository_url": "",
    "local_path": "/app/plugins/weather"
  }
}
```

**Impact:** If you parse the plugin list response, the new `source` field is always present. Built-in plugins have `source_type: "builtin"`. External plugins have `source_type: "external"`.

---

### 2. New API endpoints for external plugin management

Four new endpoints manage external plugins. These did not exist in V2:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/plugins/registry` | GET | List curated registry plugins and their install status |
| `/plugins/registry/{id}/install` | POST | Install a plugin from the registry |
| `/plugins/install` | POST | Install a plugin from a git URL |
| `/plugins/{id}/uninstall` | DELETE | Uninstall an external plugin |

**Install from git URL:**

```bash
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/someone/fiestaboard-plugin--my-plugin"}'
```

**Install from registry:**

```bash
curl -X POST http://localhost:4420/api/plugins/registry/my_plugin/install
```

**Uninstall:**

```bash
curl -X DELETE http://localhost:4420/api/plugins/my_plugin/uninstall
```

:::caution
Built-in plugins that ship with FiestaBoard cannot be uninstalled. The uninstall endpoint returns an error for built-in plugins.
:::

---

### 3. Plugin loader scans multiple directories

The plugin loader now scans two directories for plugins:

| Directory | Source | Description |
|-----------|--------|-------------|
| `plugins/` | Built-in | Plugins shipped with FiestaBoard. Always takes precedence. |
| `external_plugins/` | External | Plugins cloned from registry or git URLs. |

If the same plugin ID exists in both directories, the built-in version is used.

**Impact:** If you have custom scripts or tools that interact with the `plugins/` directory, the loader now also discovers plugins in `external_plugins/`. You should not place files in `external_plugins/` manually — it is managed by the install/uninstall API.

---

### 4. Registry naming convention for community plugins

Plugins submitted to the official FiestaBoard plugin registry must follow this repository naming convention:

```text
fiestaboard-plugin--{name}
```

For example: `fiestaboard-plugin--my-weather`, `fiestaboard-plugin--home-sensors`.

The plugin ID is derived from the repository name by removing the `fiestaboard-plugin--` prefix and converting dashes to underscores (e.g., `my_weather`, `home_sensors`).

**Impact:** This requirement only applies to plugins submitted to the registry. Custom plugins installed via git URL can use any repository name.

---

### 5. Docker volume: `external_plugins/` directory

If you use Docker, the `external_plugins/` directory is created inside the container at `/app/external_plugins/`. To persist installed external plugins across container rebuilds, you can optionally mount it as a volume:

```yaml
volumes:
  - ./data:/app/data
  - ./external_plugins:/app/external_plugins  # Optional: persist external plugins
```

If you don't mount this volume, external plugins will need to be reinstalled after container rebuilds (but their configurations are preserved in `data/config.json`).

---

## Upgrading

### From a running V2 instance

V3 upgrades are automatic. On first boot, FiestaBoard detects any plugins you had configured in V2 (weather, muni, stocks, etc.) that are no longer bundled and installs them from the registry before serving any requests.

1. **Pull the latest code or image:**

   ```bash
   # If using docker compose with local build:
   git pull
   docker compose up -d --build

   # If using pre-built images:
   docker compose pull
   docker compose up -d
   ```

2. **First-boot auto-migration**: FiestaBoard scans `data/config.json` for plugin configs that don't have corresponding plugin code on disk. For each one found in the registry, it clones the plugin into `external_plugins/` and restores your stored config — including API keys, settings, and enabled/disabled state. Check the container logs to confirm:

   ```bash
   docker compose logs fiestaboard | grep "V3 migration"
   # V3 migration: auto-installing 'weather' from registry…
   # V3 migration: restored 'weather' (enabled=True)
   # V3 migration complete: auto-installed 2 plugin(s): ['weather', 'muni']
   ```

3. **Verify**: Open `http://localhost:4420` — all your existing pages, plugins, and settings are preserved.

4. **Recommended**: Mount the `external_plugins/` volume so installed plugins survive container rebuilds without re-downloading:

   ```yaml
   volumes:
     - ./data:/app/data
     - ./external_plugins:/app/external_plugins
   ```

   Without this volume, auto-migration re-runs on every container restart (it re-clones the plugins). The process is idempotent and your config is never affected, but it does require a network connection each time.

#### What if the migration fails?

- **No network / GitHub unreachable**: FiestaBoard logs a warning and starts normally. The affected plugins won't be available until the container is restarted with network access.
- **Plugin not in the registry** (e.g. a custom built-in you developed yourself): FiestaBoard logs a warning with the plugin ID. You can re-install it manually via the Integrations page or by running `POST /api/plugins/install` with its git URL.
- **Nothing is ever deleted**: Your `data/config.json` and all plugin configurations are never modified by the migration — it only installs plugin code.

Your existing `.env` file, `data/` directory, and all plugin configurations continue to work unchanged.

### API client updates

If you have scripts or integrations that call the FiestaBoard API:

- The `GET /plugins` response now includes a `source` field on each plugin object. Update any parsing logic to expect this new field.
- The four new endpoints (`/plugins/registry`, `/plugins/registry/{id}/install`, `/plugins/install`, `/plugins/{id}/uninstall`) are additive — they don't affect existing endpoints.

---

## Plugin Development Changes

### Writing external plugins

You can now develop plugins as standalone git repositories instead of adding them to the FiestaBoard repo. See the [Plugin Development Guide](/docs/development/plugin-guide) for full details.

### Plugin extraction plan

Several API-dependent built-in plugins are planned for extraction into standalone repositories under the FiestaBoard organization. During the transition:

- Built-in copies remain in the `plugins/` directory and continue to work.
- Extracted plugins will be added to the registry.
- After a deprecation period, the built-in copies will be removed in a future release.

See `PLUGIN_EXTRACTION_PLAN.md` in the repository root for the full list and timeline.

---

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — See all available plugins and install external ones
- [Plugin Configuration](/docs/plugins/configuration) — Enable and configure plugins
- [Plugin Development Guide](/docs/development/plugin-guide) — Create your own external plugins
