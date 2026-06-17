# My Plugin Name Plugin

A brief description of what this plugin does.

<!-- Add a screenshot to `docs/board-display.png`, then replace this comment with:
     ![My Plugin Name Display](./docs/board-display.png) -->

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

Describe in 2–3 sentences what the plugin does and why it is useful. Mention the data source or API it connects to if applicable.

## Template Variables

### Main Data

```jinja
{{my_plugin.value}}       # The primary data value (e.g., "123")
{{my_plugin.status}}      # Current status text (e.g., "OK")
```

### Display

```jinja
{{my_plugin.formatted}}   # Pre-formatted display string (e.g., "Value: 123")
```

## Example Templates

### Simple Display

```jinja
{center}{{my_plugin.value}}
{{my_plugin.status}}
```

### Detailed Display

```jinja
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

```text
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
| `supports_triggers` | boolean | Enable event-based triggers (see [Triggering Pages from a Plugin](../../docs/development/PLUGIN_DEVELOPMENT.md#triggering-pages-from-a-plugin)) |

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
| `check_triggers()` | Return event-based `TriggerResult` list (requires `supports_triggers: true` — see [Triggering Pages from a Plugin](../../docs/development/PLUGIN_DEVELOPMENT.md#triggering-pages-from-a-plugin)) |
| `receive_payload(payload, headers, raw_body)` | Handle a pushed webhook payload (raise `PermissionError` / `ValueError` for 403 / 400) |
| `config` | Property. The current configuration dictionary |
| `manifest` | Property. The raw manifest dictionary |

### Testing

All plugins must have tests with **≥80% code coverage**. Tests are enforced in CI
and will block merges if coverage falls below the threshold.

```bash
# Run tests for a single plugin (with coverage)
python scripts/run_plugin_tests.py --plugin=my_plugin

# Run all plugin tests
python scripts/run_plugin_tests.py
```

#### What to Test

- **Plugin ID** matches the directory name
- **Config validation** — missing required fields, valid config
- **fetch_data()** — success, API errors, edge cases
- **Manifest variables** — all declared variables are returned in data
- **Formatted output** — `formatted_lines` is a list with expected line count
- **Error handling** — graceful degradation on API failures

#### Test File Template

```python
"""Tests for the my_plugin plugin."""
import json, pytest
from pathlib import Path
from plugins.my_plugin import MyPlugin
from src.plugins.base import PluginResult
from src.plugins.manifest import PluginManifest

MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"

@pytest.fixture
def manifest():
    with open(MANIFEST_PATH) as f:
        return PluginManifest.from_dict(json.load(f))

class TestMyPlugin:
    def test_plugin_id(self, manifest):
        assert MyPlugin(manifest).plugin_id == "my_plugin"

    def test_fetch_data_success(self, manifest):
        plugin = MyPlugin(manifest)
        plugin.config = {"api_key": "test_key_123"}
        result = plugin.fetch_data()
        assert result.available is True
        assert isinstance(result.formatted_lines, list)
```

### GitHub Actions CI for Plugins

External plugin repositories should add a CI workflow to enforce tests on every
PR. Create `.github/workflows/ci.yml` in your plugin repository:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install FiestaBoard (test dependency)
        run: |
          git clone --depth 1 https://github.com/Fiestaboard/FiestaBoard.git /tmp/fb
          pip install -r /tmp/fb/requirements.txt
          pip install -r /tmp/fb/requirements-dev.txt

      - name: Run plugin tests with coverage
        run: |
          PYTHONPATH=/tmp/fb:$PYTHONPATH \
          python -m pytest tests/ -v \
            --cov=. --cov-branch \
            --cov-report=term-missing \
            --cov-fail-under=80

      - name: Validate manifest
        run: |
          python -c "
          import json, sys
          m = json.load(open('manifest.json'))
          required = ['id', 'name', 'version']
          missing = [f for f in required if f not in m]
          if missing:
              print(f'Missing required fields: {missing}')
              sys.exit(1)
          print('Manifest valid')
          "
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
    ├── __init__.py
    ├── conftest.py
    └── test_plugin.py
```

Registry plugins must follow the `fiestaboard-plugin--{name}` naming convention.

### Example Plugins

See these plugins for reference implementations:

- `plugins/date_time/` — Plugin with no external dependencies (high coverage, no external deps)
- `plugins/countdown/` — Event countdown with timezone support (comprehensive coverage; check CI for current numbers)
