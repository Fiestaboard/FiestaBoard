# Plugin Template

This is a template for creating FiestaBoard plugins. Copy this directory to create a new plugin.

## Getting Started

1. **Copy this directory** to a new directory with your plugin ID:
   ```bash
   cp -r plugins/_template plugins/my_plugin
   ```

2. **Update `manifest.json`**:
   - Set `id` to match your directory name
   - Update `name`, `description`, `author`
   - Define your `settings_schema` with configuration fields
   - Define `variables` that your plugin exposes
   - Set `max_lengths` for template variable validation

3. **Implement `__init__.py`**:
   - Rename the class to match your plugin
   - Implement `fetch_data()` to retrieve data from your source
   - Implement `validate_config()` for configuration validation

4. **Test your plugin**:
   - Restart the FiestaBoard service
   - Your plugin should appear in the Integrations page

## Plugin Structure

```
plugins/my_plugin/
├── __init__.py      # Plugin implementation (PluginBase subclass)
├── manifest.json    # Plugin metadata and configuration schema
├── README.md        # Plugin documentation (developer-focused)
├── docs/            # User-facing documentation
│   └── SETUP.md     # Setup guide (API keys, configuration, etc.)
└── tests/           # Plugin tests (required)
    ├── __init__.py
    ├── conftest.py  # Test fixtures
    └── test_plugin.py  # Plugin tests
```

## Manifest Reference

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique plugin identifier (must match directory name) |
| `name` | string | Human-readable plugin name |
| `version` | string | Semantic version (e.g., "1.0.0") |

### Recommended Fields

These fields are not enforced by the validator but should be included for a complete plugin:

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Brief description of the plugin |
| `author` | string | Plugin author name |
| `settings_schema` | object | JSON Schema for configuration fields |
| `variables` | object | Template variables exposed by plugin |
| `max_lengths` | object | Maximum character lengths for variables |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `icon` | string | Lucide icon name (default: "puzzle") |
| `category` | string | Category for grouping (default: "utility") |
| `repository` | string | GitHub repository URL |
| `documentation` | string | Path to documentation file |
| `env_vars` | array | Environment variables the plugin can use |
| `color_rules_schema` | object | Schema for dynamic color rules |

### Settings Schema

The `settings_schema` follows [JSON Schema](https://json-schema.org/) format with UI extensions:

```json
{
  "type": "object",
  "properties": {
    "api_key": {
      "type": "string",
      "title": "API Key",
      "description": "Your API key",
      "ui:widget": "password"
    },
    "location": {
      "type": "string",
      "title": "Location",
      "enum": ["us", "eu", "asia"],
      "default": "us"
    },
    "refresh_seconds": {
      "type": "integer",
      "title": "Refresh Interval",
      "default": 300,
      "minimum": 60,
      "maximum": 3600
    }
  },
  "required": ["api_key"]
}
```

#### UI Widgets

- `password` - Masked input for sensitive fields
- `textarea` - Multi-line text input
- `select` - Dropdown (auto for `enum` fields)
- `timezone` - Timezone picker with autocomplete

### Variables Schema

Define template variables your plugin exposes:

```json
{
  "variables": {
    "simple": ["temperature", "humidity", "status"],
    "arrays": {
      "locations": {
        "label_field": "name",
        "item_fields": ["temperature", "humidity", "condition"]
      },
      "stops": {
        "label_field": "stop_name",
        "item_fields": ["stop_code", "arrivals"],
        "sub_arrays": {
          "lines": {
            "key_type": "dynamic",
            "key_field": "line",
            "item_fields": ["next_arrival", "is_delayed"]
          }
        }
      }
    }
  }
}
```

Template usage:
- Simple: `{{my_plugin.temperature}}`
- Array: `{{my_plugin.locations.0.temperature}}`
- Nested: `{{my_plugin.stops.0.lines.N.next_arrival}}`

## PluginBase API

Your plugin class must inherit from `PluginBase`:

```python
from src.plugins.base import PluginBase, PluginResult

class MyPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        """Return plugin ID matching manifest."""
        return "my_plugin"
    
    def fetch_data(self) -> PluginResult:
        """Fetch and return data."""
        # Your implementation here
        return PluginResult(
            available=True,
            data={"key": "value"},
        )
```

### Available Methods

| Method | Description |
|--------|-------------|
| `fetch_data()` | **Required.** Fetch and return plugin data |
| `validate_config(config)` | Validate configuration. Return list of errors |
| `cleanup()` | Called when plugin is disabled. Clean up resources |
| `on_config_change(old, new)` | Called when configuration is updated |
| `config` | Property. The current configuration dictionary |
| `manifest` | Property. The raw manifest dictionary |

### PluginResult

Return this from `fetch_data()`:

```python
@dataclass
class PluginResult:
    available: bool                          # True if data was fetched successfully
    data: Optional[Dict[str, Any]] = None    # Template variables
    error: Optional[str] = None              # Error message if fetch failed
    formatted_lines: Optional[List[str]] = None  # Optional pre-formatted 6-line display
```

## Testing Your Plugin

**All plugins must have tests with >80% code coverage.** Build will fail if coverage is below this threshold.

### Test Directory Structure

```
plugins/my_plugin/tests/
├── __init__.py       # Required (can be empty)
├── conftest.py       # Test fixtures
└── test_plugin.py    # Your tests (must start with test_)
```

### Writing Tests

Use the shared test utilities:

```python
import pytest
from unittest.mock import patch, Mock
from src.plugins.testing import PluginTestCase, create_mock_response

class TestMyPlugin(PluginTestCase):
    """Tests for MyPlugin."""
    
    def test_plugin_id(self):
        """Test plugin ID matches directory name."""
        from plugins.my_plugin import MyPlugin
        manifest = {"id": "my_plugin", "name": "My Plugin", "version": "1.0.0"}
        plugin = MyPlugin(manifest)
        assert plugin.plugin_id == "my_plugin"
    
    def test_fetch_data_success(self):
        """Test successful data fetch."""
        from plugins.my_plugin import MyPlugin
        manifest = {"id": "my_plugin", "name": "My Plugin", "version": "1.0.0"}
        plugin = MyPlugin(manifest)
        plugin.config = {"api_key": "test"}
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.error is None
        assert "expected_field" in result.data
    
    @patch('requests.get')
    def test_fetch_data_api_error(self, mock_get):
        """Test API error handling."""
        mock_get.side_effect = Exception("Network error")
        
        from plugins.my_plugin import MyPlugin
        manifest = {"id": "my_plugin", "name": "My Plugin", "version": "1.0.0"}
        plugin = MyPlugin(manifest)
        plugin.config = {"api_key": "test"}
        result = plugin.fetch_data()
        
        assert result.available is False
        assert result.error is not None
```

### Running Tests

```bash
# Run tests for a single plugin
python scripts/run_plugin_tests.py --plugin=my_plugin

# Run all plugin tests
python scripts/run_plugin_tests.py

# Run with verbose output
python scripts/run_plugin_tests.py --verbose

# Check coverage without failing
python scripts/run_plugin_tests.py --no-coverage
```

### Coverage Requirements

- **Minimum coverage: 80%**
- Coverage is measured per plugin, not globally
- CI will fail if any plugin is below the threshold
- Use `# pragma: no cover` sparingly for untestable code

## Best Practices

1. **Error Handling**: Always catch exceptions in `fetch_data()` and return a meaningful error
2. **Logging**: Use the `logger` for debugging and error messages
3. **Validation**: Implement thorough config validation
4. **Rate Limiting**: Respect API rate limits in your fetch logic
5. **Caching**: Consider caching responses to reduce API calls
6. **Documentation**: 
   - `README.md` - Developer documentation (how plugin works, API reference)
   - `docs/SETUP.md` - User-facing setup guide (API key registration, configuration)
7. **Testing**: Write comprehensive tests with >80% coverage

## Developing as an External Repository

Instead of adding your plugin directly to the FiestaBoard repository, you can develop it as a standalone git repository. This is the recommended approach for:

- Plugins that depend on paid or authenticated third-party APIs
- Plugins you want to release independently of FiestaBoard releases
- Community contributions that you want to maintain yourself

### External Plugin Structure

Your standalone repository should have the same layout as a built-in plugin, but at the repository root:

```
fiestaboard-plugin--my-weather/
├── __init__.py
├── manifest.json
├── README.md
├── docs/
│   └── SETUP.md
└── tests/
    └── test_plugin.py
```

### Naming Convention for Registry Plugins

If you want your plugin to be listed in the curated **plugin registry** (maintained in the FiestaBoard repository), your git repository **must** follow this naming convention:

```
fiestaboard-plugin--{name}
```

Where `{name}` uses lowercase letters and dashes (e.g. `fiestaboard-plugin--my-weather`). The plugin id in `manifest.json` is derived by stripping the prefix and converting dashes to underscores (e.g. `my_weather`).

:::note
This naming convention is only required for the curated registry. When a user installs a plugin via a custom git URL, any repository name is accepted.
:::

### Testing External Plugins Locally

Install your external plugin during development:

```bash
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/yourname/fiestaboard-plugin--my-weather"}'
```

The plugin is cloned into `external_plugins/` and loaded automatically. Changes you push to the repository can be picked up by reinstalling.

### Submitting to the Registry

To have your external plugin included in the curated registry:

1. Ensure the repository name follows the `fiestaboard-plugin--{name}` convention.
2. Open a pull request against the FiestaBoard repository that adds an entry to `plugin-registry.json`:

```json
{
  "id": "my_weather",
  "name": "My Weather Plugin",
  "description": "Custom weather data from my favorite API",
  "repository": "https://github.com/yourname/fiestaboard-plugin--my-weather",
  "author": "Your Name"
}
```

## Example Plugins

See these plugins for reference implementations:

- `plugins/weather/` - Simple plugin with external API
- `plugins/date_time/` - Plugin with no external dependencies
- `plugins/baywheels/` - Array data with multiple items
- `plugins/muni/` - Nested arrays (stops → lines)
- `plugins/home_assistant/` - Dynamic entity-based variables

