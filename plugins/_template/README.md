# My Plugin Name Plugin

A brief description of what this plugin does.

![My Plugin Name Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and setup instructions

## Overview

Describe in 2–3 sentences what the plugin does and why it is useful. Mention the data source or API it connects to if applicable.

## Template Variables

### Main Data

```
{{my_plugin.value}}       # The primary data value (e.g., "123")
{{my_plugin.status}}      # Current status text (e.g., "OK")
```

### Display

```
{{my_plugin.formatted}}   # Pre-formatted display string (e.g., "Value: 123")
```

## Example Templates

### Simple Display

```
{center}{{my_plugin.value}}
{{my_plugin.status}}
```

### Detailed Display

```
{center}MY PLUGIN
{{my_plugin.formatted}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| api_key | string | *(required)* | Your API key for the service |
| refresh_seconds | integer | 300 | How often to fetch new data (seconds) |

## Features

- **Primary Feature**: Describe the main capability
- **Another Feature**: Describe a secondary capability
- **No API Key Required** / **Free API Key**: Note the API key requirement

## Author

Your Name

---

## Plugin Development Reference

> The sections above are the **canonical README format** for all FiestaBoard plugins.
> When copying this template, replace the placeholder content but keep the section
> order. The sections below are development reference material — remove them from
> your plugin's README.

### Plugin Structure

```
plugins/my_plugin/
├── __init__.py      # Plugin implementation (PluginBase subclass)
├── manifest.json    # Plugin metadata, settings, variables, screenshots
├── README.md        # Plugin documentation (this file)
├── docs/            # User-facing documentation and images
│   ├── SETUP.md     # Setup guide (API keys, configuration, etc.)
│   └── board-display.png  # Primary screenshot (required)
└── tests/           # Plugin tests (required, >80% coverage)
    ├── __init__.py
    └── test_plugin.py
```

### Manifest Reference

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique plugin identifier (must match directory name) |
| `name` | string | Human-readable plugin name |
| `version` | string | Semantic version (e.g., "1.0.0") |

#### Recommended Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Brief description of the plugin |
| `author` | string | Plugin author name |
| `settings_schema` | object | JSON Schema for configuration fields |
| `variables` | object | Template variables exposed by plugin |
| `screenshots` | array | Screenshots for galleries and docs (see below) |

#### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `icon` | string | Lucide icon name (default: "puzzle") |
| `category` | string | Category for grouping (default: "utility") |
| `repository` | string | GitHub repository URL |
| `documentation` | string | Path to documentation file |
| `env_vars` | array | Environment variables the plugin can use |
| `color_rules_schema` | object | Schema for dynamic color rules |

#### Screenshots Field

The `screenshots` array makes plugin images discoverable by the docs site, API, and registry:

```json
{
  "screenshots": [
    {
      "src": "docs/board-display.png",
      "alt": "My Plugin displayed on a Vestaboard",
      "caption": "Default template showing the main output",
      "primary": true
    }
  ]
}
```

| Property | Required | Description |
|----------|----------|-------------|
| `src` | yes | Relative path from the plugin directory |
| `alt` | yes | Alt text for accessibility |
| `caption` | no | Human-readable description |
| `primary` | no | Mark exactly one screenshot as the hero image (`true`) |

**Image naming convention:**
- `docs/board-display.png` — Primary hero image (required for published plugins)
- `docs/configuration.png` — Plugin config dialog (optional)
- `docs/integrations.png` — Plugin card on the Integrations page (optional)
- Additional images use descriptive kebab-case names in `docs/`

### PluginBase API

```python
from src.plugins.base import PluginBase, PluginResult

class MyPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "my_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(
            available=True,
            data={"key": "value"},
        )
```

| Method | Description |
|--------|-------------|
| `fetch_data()` | **Required.** Fetch and return plugin data |
| `validate_config(config)` | Validate configuration. Return list of errors |
| `cleanup()` | Called when plugin is disabled. Clean up resources |
| `on_config_change(old, new)` | Called when configuration is updated |
| `config` | Property. The current configuration dictionary |
| `manifest` | Property. The raw manifest dictionary |

### Testing

All plugins must have tests with >80% code coverage.

```bash
# Run tests for a single plugin
python scripts/run_plugin_tests.py --plugin=my_plugin

# Run all plugin tests
python scripts/run_plugin_tests.py
```

### Developing as an External Repository

Your standalone repository should have the same layout as a built-in plugin:

```
fiestaboard-plugin--my-weather/
├── __init__.py
├── manifest.json
├── README.md
├── docs/
│   ├── SETUP.md
│   └── board-display.png
└── tests/
    └── test_plugin.py
```

Registry plugins must follow the `fiestaboard-plugin--{name}` naming convention.

### Example Plugins

See these plugins for reference implementations:

- `plugins/date_time/` — Plugin with no external dependencies
- `plugins/countdown/` — Event countdown with timezone support
