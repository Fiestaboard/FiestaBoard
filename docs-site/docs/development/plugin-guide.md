---
sidebar_position: 1
description: "End-to-end guide to creating, testing, and submitting a FiestaBoard plugin - from initial idea to merged pull request."
keywords: [FiestaBoard plugin development, create plugin, plugin API, custom plugin, developer guide, Python plugin, PluginBase, manifest.json]
---

# Plugin Development Guide

This guide walks you through creating a FiestaBoard plugin from scratch - from initial idea through development, testing, and submitting a pull request to get it merged into the project.

## What Is a Plugin?

A FiestaBoard plugin is a self-contained Python package that fetches data from an external source (an API, a local service, or computed values) and exposes that data as **template variables**. Users reference those variables in the page editor to build dynamic displays for their split-flap board.

Every plugin has four required components:

| Component | File | Purpose |
|-----------|------|---------|
| **Manifest** | `manifest.json` | Metadata, configuration schema, and declared variables |
| **Implementation** | `__init__.py` | Python class that inherits from `PluginBase` and fetches data |
| **Tests** | `tests/test_plugin.py` | Automated tests with ≥80% code coverage |
| **Documentation** | `README.md` + `docs/SETUP.md` | Developer docs and user-facing setup guide |

### Where Plugins Live

FiestaBoard discovers plugins from three sources:

| Source | Location | Naming Convention |
|--------|----------|-------------------|
| **Built-in** | `plugins/` directory | Directory name must match `manifest.json` `id` field |
| **Registry** | Cloned into `external_plugins/` | Repository must be named `fiestaboard-plugin--{name}` |
| **Custom Git** | Cloned into `external_plugins/` | No naming convention required |

Built-in plugins are auto-discovered at startup. External plugins (registry and custom git) are cloned into the `external_plugins/` directory and also auto-discovered.

:::info Plugin Sources
If you want your plugin included in the curated **plugin registry**, the git repository must follow the `fiestaboard-plugin--{name}` naming convention (e.g. `fiestaboard-plugin--my-weather`). This is **not** required for personal or custom plugins you install via a git URL.
:::

---

## Step 1: Set Up Your Development Environment

Before writing any code, get the dev environment running:

```bash
# Clone the repo (or your fork)
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard

# Create a feature branch
git checkout -b feat-plugin-my-plugin

# Copy the environment template
cp env.example .env
# Edit .env with your board API key (see README for details)

# Start the development stack (hot reload for Python and Next.js)
docker compose -f docker-compose.dev.yml up --build
```

The dev environment gives you:

- **Web UI** at `http://localhost:4420` (hot reloads on frontend changes)
- **API** at `http://localhost:4420` (auto-reloads on Python changes, proxied via nginx)

See [Local Development](/docs/setup/local-development) for full setup details.

---

## Step 2: Scaffold Your Plugin

Copy the built-in template to create your plugin skeleton:

```bash
cp -r plugins/_template plugins/my_plugin
```

This gives you the required directory structure:

```text
plugins/my_plugin/
├── __init__.py          # Plugin class (PluginBase subclass)
├── manifest.json        # Plugin metadata and configuration schema
├── README.md            # Developer-focused documentation
├── docs/
│   └── SETUP.md         # User-facing setup guide (API keys, config)
└── tests/
    ├── __init__.py      # Required (can be empty)
    ├── conftest.py      # Shared test fixtures
    └── test_plugin.py   # Plugin tests (≥80% coverage required)
```

:::warning Important
The plugin directory name **must** match the `id` field in `manifest.json`. If your directory is `plugins/my_plugin/`, then `manifest.json` must have `"id": "my_plugin"`.
:::

---

## Step 3: Define Your Manifest

The `manifest.json` file is the heart of your plugin. It tells FiestaBoard what your plugin is, how it's configured, and what template variables it provides.

### Minimal Example

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "A brief description of what this plugin does",
  "author": "Your Name",
  "icon": "puzzle",
  "category": "utility",
  "settings_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "title": "API Key",
        "description": "Your API key from example.com",
        "ui:widget": "password"
      }
    },
    "required": ["api_key"]
  },
  "variables": {
    "simple": ["value", "status"]
  },
  "max_lengths": {
    "value": 10,
    "status": 15
  }
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier - lowercase letters, digits, and underscores only. Must start with a letter. Must match directory name. |
| `name` | string | Human-readable name shown in the UI (max 50 characters). |
| `version` | string | Semantic version in `X.Y.Z` format (e.g., `"1.0.0"`). |

### Strongly Recommended Fields

These fields are not enforced by the manifest validator but should be included in every plugin:

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Short description (max 200 characters). |
| `author` | string | Plugin author or maintainer. |
| `settings_schema` | object | [JSON Schema](https://json-schema.org/) defining user-configurable settings. |
| `variables` | object | Template variables your plugin exposes (see [Variables](#variables) below). |
| `max_lengths` | object | Maximum character lengths for each variable (used for template validation). |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `icon` | string | `"puzzle"` | [Lucide](https://lucide.dev/icons/) icon name for the UI. |
| `category` | string | `"utility"` | Grouping category. Valid values: `"art"`, `"data"`, `"transit"`, `"weather"`, `"entertainment"`, `"utility"`, `"home"`. |
| `repository` | string | - | GitHub repository URL. |
| `documentation` | string | `"README.md"` | Path to documentation file relative to plugin directory. |
| `env_vars` | array | `[]` | Environment variables the plugin can read (see [Environment Variables](#environment-variables)). |
| `color_rules_schema` | object | `{}` | Schema for dynamic color rules (see [Color Rules](#color-rules)). |

### Settings Schema

The `settings_schema` uses [JSON Schema](https://json-schema.org/) with UI widget extensions. This schema drives the configuration form in the web UI's Integrations page.

```json
{
  "settings_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "title": "API Key",
        "description": "Get your key from example.com",
        "ui:widget": "password"
      },
      "provider": {
        "type": "string",
        "title": "Provider",
        "enum": ["option1", "option2"],
        "default": "option1"
      },
      "locations": {
        "type": "array",
        "title": "Locations",
        "items": {
          "type": "object",
          "properties": {
            "name": { "type": "string", "title": "Name" },
            "value": { "type": "string", "title": "Value" }
          },
          "required": ["name", "value"]
        }
      },
      "refresh_seconds": {
        "type": "integer",
        "title": "Refresh Interval (seconds)",
        "default": 300,
        "minimum": 60,
        "maximum": 3600
      }
    },
    "required": ["api_key"]
  }
}
```

**Available UI widgets:**

| Widget | Usage |
|--------|-------|
| `password` | Masked input for secrets and API keys |
| `textarea` | Multi-line text input |
| `select` | Dropdown (automatically used for `enum` fields) |
| `timezone` | Timezone picker with autocomplete |

### Color Rules {#color-rules}

`color_rules_schema` declares which variables support automatic color coding. When a rule fires, FiestaBoard prepends a color tile before the variable value in the template. No plugin code is required — the template engine handles it automatically.

```json
{
  "color_rules_schema": {
    "status": {
      "type": "threshold",
      "description": "Color based on status value",
      "default_rules": [
        { "condition": "==", "value": "OK",       "color": "green"  },
        { "condition": "==", "value": "WARNING",   "color": "yellow" },
        { "condition": "==", "value": "CRITICAL",  "color": "red"   }
      ]
    },
    "temp_f": {
      "type": "threshold",
      "description": "Color based on temperature",
      "default_rules": [
        { "condition": ">=", "value": 90, "color": "red"    },
        { "condition": ">=", "value": 70, "color": "yellow" },
        { "condition": "<",  "value": 70, "color": "blue"   }
      ]
    }
  }
}
```

Each top-level key is a variable field name. The value is an object with:

| Key | Required | Description |
|-----|----------|-------------|
| `type` | No | Informational label (e.g., `"threshold"`, `"exact"`) — not enforced by the engine |
| `description` | No | Human-readable description shown in the UI |
| `default_rules` | No | Rules applied when the user has not set custom rules |

Each rule object has three fields:

| Field | Description |
|-------|-------------|
| `condition` | Comparison operator: `==`, `!=`, `>`, `<`, `>=`, `<=` |
| `value` | Value to compare against (number or string) |
| `color` | One of: `red`, `orange`, `yellow`, `green`, `blue`, `violet`, `white`, `black` |

Rules are checked in order. The first match wins; the rest are ignored. Numeric operators (`>`, `<`, `>=`, `<=`) coerce both sides to float. `==` and `!=` always do case-insensitive string comparison.

**Using color rules in templates**

Reference the variable as normal — color is applied automatically:

```jinja
{{my_plugin.status}}
{{my_plugin.temp_f}}°F
```

If `status` is `"WARNING"`, the board shows a yellow tile followed by `WARNING`. No special template syntax is needed.

> **Note:** A colored line takes 2 characters of board width (tile + space). FiestaBoard accounts for this in max-length calculations automatically.

**User overrides**

Users can set their own rules per field in the FiestaBoard web UI. Custom rules replace the `default_rules` entirely. The `color_rules_schema` tells the UI which fields are eligible for color customization. Fields without `default_rules` appear in the UI but start with no rules applied.

### Variables {#variables}

The `variables` object declares what template variables your plugin provides. There are three types:

#### Simple Variables

Top-level key-value pairs. Users reference them as `{{my_plugin.temperature}}`.

```json
{
  "variables": {
    "simple": ["temperature", "humidity", "condition"]
  }
}
```

#### Array Variables

Indexed collections. Users reference items as `{{my_plugin.locations.0.temperature}}`.

```json
{
  "variables": {
    "arrays": {
      "locations": {
        "label_field": "name",
        "item_fields": ["name", "temperature", "humidity"]
      }
    }
  }
}
```

- `label_field` - the field used as a human-readable label in the UI.
- `item_fields` - all fields available on each array item.

#### Nested Arrays (Arrays within Arrays)

For data like transit stops that contain multiple lines. Users reference them as `{{my_plugin.stops.0.lines.N.next_arrival}}`.

```json
{
  "variables": {
    "arrays": {
      "stops": {
        "label_field": "stop_name",
        "item_fields": ["stop_name", "stop_code"],
        "sub_arrays": {
          "lines": {
            "key_type": "dynamic",
            "key_field": "line",
            "item_fields": ["line", "next_arrival", "is_delayed"]
          }
        }
      }
    }
  }
}
```

### Max Lengths

Every variable should have a corresponding max-length entry. This helps the page editor validate that content fits the board's 22-character-wide display.

```json
{
  "max_lengths": {
    "temperature": 3,
    "condition": 15,
    "locations.*.name": 10,
    "locations.*.temperature": 3
  }
}
```

The `*` wildcard matches any array index.

### Environment Variables

If your plugin can read configuration from environment variables (as a fallback to UI config), declare them:

```json
{
  "env_vars": [
    {
      "name": "MY_PLUGIN_API_KEY",
      "required": false,
      "description": "API key (can also be set in the web UI)"
    }
  ]
}
```

---

## Step 4: Implement Your Plugin

Your plugin class lives in `__init__.py` and must inherit from `PluginBase`. Here's the minimal contract:

```python
"""My Plugin for FiestaBoard."""

import logging
import os
from typing import Any, Dict, List

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class MyPlugin(PluginBase):
    """Fetches data from My Service."""

    @property
    def plugin_id(self) -> str:
        """Return the plugin ID - must match manifest.json 'id' field."""
        return "my_plugin"

    def fetch_data(self) -> PluginResult:
        """Fetch data and return it as template variables."""
        api_key = self.config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")

        if not api_key:
            return PluginResult(available=False, error="API key not configured")

        try:
            # Your data-fetching logic here
            data = {"value": "123", "status": "OK"}

            return PluginResult(available=True, data=data)

        except Exception as e:
            logger.error("Error fetching data: %s", e, exc_info=True)
            return PluginResult(available=False, error=str(e))

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration. Return a list of error messages (empty if valid)."""
        errors = []
        if not config.get("api_key"):
            errors.append("API key is required")
        return errors
```

### PluginBase API Reference

Your plugin inherits these from `PluginBase`:

| Member | Type | Description |
|--------|------|-------------|
| `plugin_id` | property (abstract) | **Required.** Return your plugin's unique ID. |
| `fetch_data()` | method (abstract) | **Required.** Fetch data and return a `PluginResult`. |
| `validate_config(config)` | method | Validate a config dict. Return list of error strings. Default returns `[]`. |
| `cleanup()` | method | Called when plugin is disabled. Override to release resources. |
| `on_config_change(old, new)` | method | Called when config is updated. Override to reset caches. |
| `get_formatted_display()` | method | Return 6 pre-formatted lines for "single page" mode. Default returns `None`. |
| `config` | property | The current configuration dictionary (set by the platform). |
| `enabled` | property | Whether the plugin is currently enabled. |
| `manifest` | property | The raw manifest dictionary. |
| `refresh_seconds` | property | Effective refresh interval in seconds (from manifest + config). Returns `None` if not defined. |
| `get_data()` | method | Get plugin data with automatic caching based on `refresh_seconds`. This is what the platform calls. |
| `clear_cache()` | method | Clear cached data, forcing a fresh fetch on the next `get_data()` call. |
| `get_variables_schema()` | method | Returns the `variables` section from the manifest. |
| `get_max_lengths()` | method | Returns the `max_lengths` section from the manifest. |
| `get_settings_schema()` | method | Returns the `settings_schema` section from the manifest. |
| `get_env_vars()` | method | Returns environment variable definitions from the manifest. |

### PluginResult

`fetch_data()` must return a `PluginResult`:

```python
@dataclass
class PluginResult:
    available: bool                          # True if data was fetched successfully
    data: Optional[Dict[str, Any]] = None    # Template variables
    error: Optional[str] = None              # Error message if fetch failed
    formatted_lines: Optional[List[str]] = None  # Optional pre-formatted 6-line display
```

- Set `available=True` and populate `data` on success.
- Set `available=False` and populate `error` on failure.
- `formatted_lines` is optional - provide 6 strings (one per board row) if your plugin supports a standalone display mode.

### Accessing Configuration

Use `self.config` (a `Dict[str, Any]`) to read values the user set in the web UI:

```python
def fetch_data(self) -> PluginResult:
    api_key = self.config.get("api_key")
    location = self.config.get("location", "San Francisco")
    refresh = self.config.get("refresh_seconds", 300)
    # ...
```

You can also fall back to environment variables:

```python
api_key = self.config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")
```

### Constructor

`PluginBase.__init__` accepts a `manifest` dictionary (the parsed `manifest.json`). You usually don't need to override `__init__`, but if you do, call `super().__init__(manifest)`:

```python
def __init__(self, manifest: Dict[str, Any]):
    super().__init__(manifest)
    self._cache = None
```

### Real-World Example: Date & Time Plugin

This plugin has no external API - it uses Python's `datetime` library:

```python
"""Date & Time plugin for FiestaBoard."""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class DateTimePlugin(PluginBase):
    """Provides current date/time in the configured timezone."""

    @property
    def plugin_id(self) -> str:
        return "date_time"

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        timezone = config.get("timezone", "America/Los_Angeles")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            errors.append(f"Invalid timezone: {timezone}")
        return errors

    def fetch_data(self) -> PluginResult:
        try:
            tz = ZoneInfo(self.config.get("timezone", "America/Los_Angeles"))
            now = datetime.now(tz)
            return PluginResult(
                available=True,
                data={
                    "date": now.strftime("%Y-%m-%d"),
                    "time": now.strftime("%H:%M"),
                    "day_of_week": now.strftime("%A"),
                    "time_12h": now.strftime("%I:%M %p").lstrip("0"),
                    # ... more variables
                },
            )
        except Exception as e:
            logger.exception("Error fetching datetime data")
            return PluginResult(available=False, error=str(e))
```

---

## Step 5: Write Tests

**All plugins must include tests with ≥80% code coverage.** CI will fail if coverage is below this threshold.

### Test Structure

```text
plugins/my_plugin/tests/
├── __init__.py       # Required (can be empty)
├── conftest.py       # Shared test fixtures
└── test_plugin.py    # Your tests (filenames must start with test_)
```

### conftest.py

Use the template's `conftest.py` or create your own with shared fixtures:

```python
"""Plugin test fixtures."""

import pytest
from src.plugins.testing import create_mock_response


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def mock_api_response():
    """Fixture to create mock API responses."""
    return create_mock_response


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "api_key": "test_api_key_12345",
        "refresh_seconds": 300,
    }
```

### Writing Tests

Test the key behaviors: successful fetches, missing configuration, API errors, edge cases, and config validation.

```python
"""Tests for my_plugin."""

import pytest
from unittest.mock import patch

from plugins.my_plugin import MyPlugin
from src.plugins.base import PluginResult
from src.plugins.testing import PluginTestCase, create_mock_response


class TestMyPlugin(PluginTestCase):
    """Core plugin tests."""

    def _make_plugin(self, config=None):
        """Helper to create a configured plugin instance."""
        manifest = {
            "id": "my_plugin",
            "name": "My Plugin",
            "version": "1.0.0",
        }
        plugin = MyPlugin(manifest)
        if config:
            plugin.config = config
        return plugin

    def test_plugin_id(self):
        """Plugin ID must match the directory name."""
        plugin = self._make_plugin()
        assert plugin.plugin_id == "my_plugin"

    def test_fetch_data_success(self):
        """Successful fetch returns available=True with data."""
        plugin = self._make_plugin({"api_key": "test_key"})

        with patch("requests.get") as mock_get:
            mock_get.return_value = create_mock_response(
                data={"value": "42", "status": "OK"}
            )
            result = plugin.fetch_data()

        assert result.available is True
        assert result.error is None
        assert "value" in result.data

    def test_fetch_data_missing_config(self):
        """Missing API key returns available=False."""
        plugin = self._make_plugin({})
        result = plugin.fetch_data()

        assert result.available is False
        assert result.error is not None

    @patch("requests.get")
    def test_fetch_data_network_error(self, mock_get):
        """Network errors are handled gracefully."""
        mock_get.side_effect = Exception("Connection refused")
        plugin = self._make_plugin({"api_key": "test_key"})
        result = plugin.fetch_data()

        assert result.available is False
        assert "Connection refused" in result.error

    def test_validate_config_valid(self):
        """Valid config passes validation."""
        plugin = self._make_plugin()
        errors = plugin.validate_config({"api_key": "key123"})
        assert len(errors) == 0

    def test_validate_config_missing_required(self):
        """Missing required fields are caught."""
        plugin = self._make_plugin()
        errors = plugin.validate_config({})
        assert len(errors) > 0
        assert any("api_key" in e.lower() for e in errors)

    def test_data_variables_match_manifest(self):
        """Returned data keys match the variables declared in manifest.json."""
        import json
        from pathlib import Path

        manifest_path = Path(__file__).parent.parent / "manifest.json"
        with open(manifest_path) as f:
            manifest = json.load(f)

        declared_vars = manifest["variables"]["simple"]
        plugin = self._make_plugin({"api_key": "test_key"})

        with patch("requests.get") as mock_get:
            mock_get.return_value = create_mock_response(data={"value": "1", "status": "OK"})
            result = plugin.fetch_data()

        if result.available:
            for var in declared_vars:
                assert var in result.data, f"Variable '{var}' declared in manifest but missing from data"


class TestMyPluginEdgeCases:
    """Edge case and error handling tests."""

    def test_empty_api_response(self):
        """Empty API response is handled gracefully."""
        # ...

    def test_timeout_handling(self):
        """Request timeouts produce a clean error."""
        # ...
```

### Running Tests

```bash
# Test a single plugin (with coverage)
docker compose exec fiestaboard python scripts/run_plugin_tests.py --plugin=my_plugin

# Or using pytest directly
docker compose exec fiestaboard pytest plugins/my_plugin/tests/ -v

# Run with coverage report
docker compose exec fiestaboard pytest plugins/my_plugin/tests/ \
  --cov=plugins/my_plugin --cov-report=term-missing

# Run all plugin tests
docker compose exec fiestaboard python scripts/run_plugin_tests.py --verbose

# Dry run (see what would be tested)
docker compose exec fiestaboard python scripts/run_plugin_tests.py --dry-run
```

### Coverage Requirements

| Requirement | Value |
|-------------|-------|
| Minimum coverage | **80%** per plugin |
| CI enforcement | Yes - builds fail below threshold |
| Exclusions | Use `# pragma: no cover` sparingly for legitimately untestable code |

---

## Step 6: Write Documentation

Each plugin needs two documentation files:

### README.md (Developer-Focused)

Explain how the plugin works internally - data sources, API details, architecture decisions. This is for someone reading the code or contributing improvements.

### docs/SETUP.md (User-Focused)

Walk a user through enabling and configuring the plugin. Include:

- How to obtain any required API keys (with links)
- Step-by-step configuration in the web UI
- Available template variables and example usage
- Screenshots of the plugin in action (place images in `docs/`)
- Troubleshooting tips
- API rate limits and plan details

Use the template's `docs/SETUP.md` as a starting point.

---

## Step 7: Validate Your Plugin

Before submitting, run the validation scripts to catch common issues:

```bash
# Validate all plugin manifests (structure, schema, naming)
docker compose exec fiestaboard python scripts/validate_plugins.py --verbose

# Run your plugin's tests with coverage
docker compose exec fiestaboard python scripts/run_plugin_tests.py --plugin=my_plugin

# Verify the plugin loads and appears in the API
curl http://localhost:4420/api/plugins
curl http://localhost:4420/api/plugins/my_plugin
curl http://localhost:4420/api/plugins/my_plugin/data
```

The validator checks:

- `id` matches directory name and follows the naming rules (lowercase, underscores, starts with letter)
- `version` follows semantic versioning (`X.Y.Z`)
- `category` is a valid value
- Required files exist (`__init__.py`, `manifest.json`)
- `settings_schema` and `variables` are well-formed
- No duplicate plugin IDs

---

## Step 8: Test in the Web UI

With the dev stack running, open `http://localhost:4420` and:

1. Go to **Integrations** - your plugin should appear in the list
2. **Enable** the plugin and enter any required configuration
3. **Create a page** using your plugin's template variables (e.g., `{{my_plugin.value}}`)
4. Verify the page renders correctly with live data

---

## Step 9: Submit Your Pull Request

### Pre-Submission Checklist

Before opening a PR, verify every item:

- [ ] Plugin directory name matches `manifest.json` `id`
- [ ] `manifest.json` has all required fields and valid values
- [ ] `__init__.py` implements `PluginBase` with `plugin_id` property and `fetch_data()` method
- [ ] `validate_config()` checks all required settings
- [ ] Error handling is comprehensive - `fetch_data()` never raises uncaught exceptions
- [ ] Tests exist in `tests/` with ≥80% coverage
- [ ] All tests pass: `python scripts/run_plugin_tests.py --plugin=my_plugin`
- [ ] Plugin validation passes: `python scripts/validate_plugins.py --verbose`
- [ ] `README.md` documents how the plugin works
- [ ] `docs/SETUP.md` has user-facing setup instructions
- [ ] No hardcoded secrets, API keys, or real personal data
- [ ] Logging uses appropriate levels (`debug`, `info`, `warning`, `error`)

### Opening the PR

1. **Push** your feature branch:

   ```bash
   git push origin feat-plugin-my-plugin
   ```

2. **Open a PR** against `main` on GitHub.

3. **Title**: Use the format `feat: add my_plugin plugin` (or similar descriptive title).

4. **Description**: Explain what your plugin does, what data source it uses, and mention any required API keys. Reference any related issues.

5. **Scope**: Keep the PR focused on one plugin. Don't bundle unrelated changes.

### What CI Checks

When you open a PR, GitHub Actions automatically:

1. **Validates manifests** - runs `scripts/validate_plugins.py` to check structure and schema
2. **Runs plugin tests** - discovers your `tests/` directory and runs pytest with coverage
3. **Checks coverage** - verifies your plugin meets the 80% coverage threshold
4. **Verifies required files** - confirms `__init__.py` and `manifest.json` exist
5. **Uploads coverage** - reports to Codecov for review

All checks must pass before a maintainer can merge your PR.

### After Merge

Once merged, add your plugin to the **Available Plugins** list in the repository's main `README.md` (if it isn't already part of your PR). Follow the existing format with emoji, plugin name, and link to your plugin's README.

---

## Best Practices

### Error Handling

Always catch exceptions in `fetch_data()` and return a meaningful `PluginResult`:

```python
def fetch_data(self) -> PluginResult:
    try:
        # your logic
        return PluginResult(available=True, data=data)
    except requests.RequestException as e:
        logger.warning("Network error: %s", e)
        return PluginResult(available=False, error="Network unavailable")
    except Exception as e:
        logger.exception("Unexpected error in %s", self.plugin_id)
        return PluginResult(available=False, error=str(e))
```

### Caching

`PluginBase` provides **automatic caching** via `get_data()`. When your manifest defines a `refresh_seconds` field in `settings_schema`, the platform caches the result of `fetch_data()` and reuses it until the interval expires. You do **not** need to implement caching yourself in most cases.

If your plugin needs more control (e.g., different TTLs for different data), you can implement manual caching inside `fetch_data()`:

```python
from datetime import datetime, timedelta

class MyPlugin(PluginBase):
    def __init__(self, manifest):
        super().__init__(manifest)
        self._custom_cache = None
        self._custom_cache_time = None
        self._custom_cache_ttl = timedelta(minutes=5)

    def fetch_data(self) -> PluginResult:
        if self._custom_cache and self._custom_cache_time:
            if datetime.now() - self._custom_cache_time < self._custom_cache_ttl:
                return self._custom_cache

        result = self._fetch_fresh()
        if result.available:
            self._custom_cache = result
            self._custom_cache_time = datetime.now()
        return result
```

:::tip
For most plugins, just add `refresh_seconds` to your `settings_schema` and let `get_data()` handle caching automatically. Manual caching is only needed for advanced scenarios.
:::

### Logging

Use Python's `logging` module with appropriate levels:

```python
logger.debug("Detailed info for debugging")
logger.info("Plugin initialized successfully")
logger.warning("Non-critical issue: %s", detail)
logger.error("Failed to fetch data: %s", error)
logger.exception("Unexpected error with traceback")
```

### Security

- **Never hardcode** API keys, tokens, or credentials.
- **Never log** secrets - even at debug level.
- Use `"ui:widget": "password"` in `settings_schema` for sensitive fields.
- Use generic example data in tests and documentation (e.g., `example@example.com`, well-known public coordinates).

---

## Developing an External Plugin

You can also develop a plugin as a standalone git repository instead of adding it directly to the FiestaBoard repo. This is the recommended approach for plugins that depend on paid or authenticated APIs.

### Repository Structure

Your external plugin repository should have the same structure as a built-in plugin, but at the repository root:

```text
fiestaboard-plugin--my-weather/
├── __init__.py          # Plugin class (PluginBase subclass)
├── manifest.json        # Plugin metadata and configuration schema
├── README.md            # Documentation
├── docs/
│   └── SETUP.md         # User-facing setup guide
└── tests/
    └── test_plugin.py   # Plugin tests
```

### Naming Convention

If you want your plugin listed in the official **plugin registry**, your repository **must** follow this naming convention:

```text
fiestaboard-plugin--{name}
```

Where `{name}` is lowercase and uses dashes for separators (e.g. `fiestaboard-plugin--my-weather`). The plugin id in `manifest.json` is derived by removing the prefix and converting dashes to underscores (e.g. `my_weather`).

:::note
This naming convention is only required for the curated registry. When installing a plugin from a custom git URL, any repository name is accepted.
:::

### Installing Your External Plugin

During development, install your plugin directly from your git repository. Only HTTPS URLs are accepted (SSH and HTTP URLs are rejected for security):

```bash
# Install from your repo (HTTPS only)
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/yourname/fiestaboard-plugin--my-weather"}'
```

The plugin will be cloned into the `external_plugins/` directory and loaded automatically.

### Submitting to the Registry

To get your plugin into the curated registry:

1. Ensure your repository follows the `fiestaboard-plugin--{name}` naming convention.
2. Open a pull request against the FiestaBoard repository that adds your plugin to `plugin-registry.json`.
3. Your entry should include the plugin id, name, description, repository URL, and author.

```json
{
  "id": "my_weather",
  "name": "My Weather Plugin",
  "description": "Custom weather data from my favorite API",
  "repository": "https://github.com/yourname/fiestaboard-plugin--my-weather",
  "author": "Your Name"
}
```

---

## Reference: Plugin API Endpoints

These REST endpoints are available for testing and debugging your plugin:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/plugins` | GET | List all loaded plugins |
| `/plugins/{id}` | GET | Get a specific plugin's details |
| `/plugins/{id}/config` | PUT | Update plugin configuration |
| `/plugins/{id}/enable` | POST | Enable a plugin |
| `/plugins/{id}/disable` | POST | Disable a plugin |
| `/plugins/{id}/data` | GET | Fetch current plugin data |
| `/plugins/{id}/variables` | GET | Get the plugin's variable schema |
| `/plugins/registry` | GET | List curated registry plugins |
| `/plugins/registry/{id}/install` | POST | Install a registry plugin |
| `/plugins/install` | POST | Install a plugin from a git URL |
| `/plugins/{id}/uninstall` | DELETE | Uninstall an external plugin |

---

## Reference: Example Plugins

Study these existing plugins as reference implementations:

| Plugin | Directory | Highlights |
|--------|-----------|------------|
| **Date & Time** | `plugins/date_time/` | Simple plugin, no external API, `simple` variables only |
| **Guest WiFi** | `plugins/guest_wifi/` | Static data, no API key needed |
| **Weather** | `plugins/weather/` | External API with multiple providers |
| **Stocks** | `plugins/stocks/` | Array variables with indexed items |
| **Muni Transit** | `plugins/muni/` | Nested arrays (stops → lines) |
| **Home Assistant** | `plugins/home_assistant/` | Dynamic entity-based variables |
| **Surf** | `plugins/surf/` | Location-based data, caching pattern |

---

## Next Steps

- [Contributing](/docs/development/contributing) - General contribution guidelines
- [Testing Guide](/docs/development/testing) - Running and writing tests
- [Local Development](/docs/setup/local-development) - Development environment setup
