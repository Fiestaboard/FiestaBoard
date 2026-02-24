# FiestaBoard Plugin Development Guide

This guide explains how to create plugins for FiestaBoard. Plugins are self-contained data source integrations that expose variables for use in templates.

## Overview

FiestaBoard uses a plugin architecture inspired by Home Assistant's HACS. Each plugin:

- Lives in its own directory under `plugins/`
- Has a `manifest.json` describing its metadata and configuration
- Implements the `PluginBase` class to fetch data
- Exposes template variables for use in board displays

## Quick Start

1. Copy the template plugin:
   ```bash
   cp -r plugins/_template plugins/my_plugin
   ```

2. Update `manifest.json` with your plugin's details

3. Implement your data fetching logic in `__init__.py`

4. Test your plugin:
   ```bash
   docker-compose up -d
   ```
   Your plugin should appear in the Integrations page.

## Plugin Structure

```
plugins/
├── _template/           # Template (ignored by loader)
│   ├── __init__.py
│   ├── manifest.json
│   ├── README.md
│   ├── docs/            # User-facing documentation
│   │   └── SETUP.md     # Setup guide
│   └── tests/           # Test directory
│       ├── __init__.py
│       ├── conftest.py
│       └── test_plugin.py
├── weather/             # Example plugin
│   ├── __init__.py
│   ├── manifest.json
│   ├── README.md
│   ├── docs/
│   │   └── SETUP.md
│   └── tests/           # Plugin tests
└── my_plugin/           # Your plugin
    ├── __init__.py      # Required: Plugin implementation
    ├── manifest.json    # Required: Plugin metadata
    ├── README.md        # Required: Developer documentation
    ├── docs/            # Required: User documentation
    │   └── SETUP.md     # Setup guide (API keys, configuration)
    └── tests/           # Required: Plugin tests
        ├── __init__.py
        ├── conftest.py
        └── test_plugin.py
```

### Documentation Requirements

Each plugin has two types of documentation:

1. **README.md** (Developer-focused)
   - How the plugin works internally
   - API reference and implementation details
   - Contributing guidelines

2. **docs/SETUP.md** (User-focused)
   - How to get API keys
   - Configuration instructions
   - Examples and screenshots
   - Troubleshooting tips

## manifest.json

The manifest file describes your plugin's metadata, configuration schema, and exposed variables.

### Basic Structure

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "A description of what this plugin does",
  "author": "Your Name",
  "icon": "puzzle",
  "category": "utility",
  "settings_schema": { ... },
  "variables": { ... },
  "max_lengths": { ... }
}
```

### Required Fields

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (must match directory name) |
| `name` | Human-readable name |
| `version` | Semantic version (e.g., "1.0.0") |
| `description` | Brief description |
| `author` | Author name |
| `settings_schema` | JSON Schema for configuration |
| `variables` | Template variables exposed |
| `max_lengths` | Max character lengths for variables |

### Optional Fields

| Field | Description |
|-------|-------------|
| `icon` | Lucide icon name (default: "puzzle") |
| `category` | Category for grouping ("weather", "transit", "home", etc.) |
| `repository` | GitHub repository URL |
| `documentation` | Path to documentation file |
| `env_vars` | Environment variables the plugin uses |
| `color_rules_schema` | Schema for dynamic color rules |

### Settings Schema

Use JSON Schema to define configuration fields:

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
        "title": "Refresh Interval",
        "default": 300,
        "minimum": 60
      }
    },
    "required": ["api_key"]
  }
}
```

#### UI Widgets

- `password` - Masked input for secrets
- `textarea` - Multi-line text
- `select` - Dropdown (automatic for `enum` fields)
- `array-input` - Array of items

### Variables Schema

Define what template variables your plugin exposes:

```json
{
  "variables": {
    "simple": ["temperature", "humidity", "status"],
    "arrays": {
      "locations": {
        "label_field": "name",
        "item_fields": ["temperature", "humidity", "condition"]
      }
    },
    "nested": {
      "stops": {
        "label_field": "stop_name",
        "item_fields": ["stop_code", "arrivals"],
        "nested_arrays": {
          "lines": {
            "label_field": "line",
            "item_fields": ["next_arrival", "is_delayed"]
          }
        }
      }
    },
    "dynamic": false
  }
}
```

#### Variable Types

1. **Simple Variables** - Top-level values
   ```
   {{my_plugin.temperature}}
   {{my_plugin.status}}
   ```

2. **Array Variables** - Indexed access to array items
   ```
   {{my_plugin.locations.0.temperature}}
   {{my_plugin.locations.1.name}}
   ```

3. **Nested Variables** - Arrays within arrays
   ```
   {{my_plugin.stops.0.lines.N.next_arrival}}
   {{my_plugin.stops.1.lines.KT.is_delayed}}
   ```

4. **Dynamic Variables** - Entity-based (like Home Assistant)
   ```
   {{home_assistant.sensor_temperature.state}}
   {{home_assistant.light_living_room.brightness}}
   ```

### Max Lengths

Define maximum character lengths for variables (used for template validation):

```json
{
  "max_lengths": {
    "temperature": 3,
    "status": 15,
    "formatted": 22,
    "locations.*.temperature": 3,
    "locations.*.name": 10
  }
}
```

The `*` wildcard matches any array index.

## Plugin Implementation

Your plugin must inherit from `PluginBase`:

```python
from src.plugins.base import PluginBase, PluginResult

class MyPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "my_plugin"
    
    def fetch_data(self) -> PluginResult:
        # Your implementation
        pass
```

### PluginBase Methods

| Method | Required | Description |
|--------|----------|-------------|
| `plugin_id` | Yes | Property returning plugin ID |
| `fetch_data()` | Yes | Fetch and return data |
| `validate_config(config)` | No | Validate configuration |
| `cleanup()` | No | Clean up when disabled |

### Helper Methods

| Method | Description |
|--------|-------------|
| `get_config(key, default=None)` | Get configuration value |
| `get_manifest()` | Get plugin manifest |
| `is_enabled` | Property: plugin enabled state |

### PluginResult

Return this from `fetch_data()`:

```python
@dataclass
class PluginResult:
    available: bool              # True if data fetched successfully
    data: Optional[Dict] = None  # Template variables
    formatted: Optional[str] = None  # Pre-formatted display
    error: Optional[str] = None  # Error message
```

### Example Implementation

```python
import logging
import requests
from typing import Any, Dict, List

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class WeatherPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "weather"
    
    def fetch_data(self) -> PluginResult:
        api_key = self.get_config("api_key")
        location = self.get_config("location", "San Francisco")
        
        if not api_key:
            return PluginResult(
                available=False,
                error="API key not configured"
            )
        
        try:
            response = requests.get(
                "https://api.weatherapi.com/v1/current.json",
                params={"key": api_key, "q": location}
            )
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            
            return PluginResult(
                available=True,
                data={
                    "temperature": int(current.get("temp_f", 0)),
                    "condition": current.get("condition", {}).get("text", ""),
                    "humidity": current.get("humidity", 0),
                    "location": location,
                },
                formatted=self._format_display(current, location)
            )
            
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors = []
        if not config.get("api_key"):
            errors.append("API key is required")
        return errors
    
    def _format_display(self, current: dict, location: str) -> str:
        temp = current.get("temp_f", "N/A")
        cond = current.get("condition", {}).get("text", "Unknown")
        return f"{location}\\n{temp}°F {cond}"
```

## Testing Your Plugin

**All plugins must include tests with a minimum of 80% code coverage.** CI will fail if coverage is below this threshold.

### Test Directory Structure

Every plugin must have a `tests/` directory:

```
plugins/my_plugin/tests/
├── __init__.py       # Required (can be empty)
├── conftest.py       # Test fixtures
└── test_plugin.py    # Test cases (must start with test_)
```

### Writing Tests

Use the shared test utilities from `src.plugins.testing`:

```python
"""Tests for my_plugin."""

import pytest
from unittest.mock import patch, Mock

from src.plugins.testing import PluginTestCase, create_mock_response
from plugins.my_plugin import MyPlugin


class TestMyPlugin(PluginTestCase):
    """Test suite for MyPlugin."""
    
    def test_plugin_id(self):
        """Test plugin ID matches directory name."""
        plugin = MyPlugin()
        assert plugin.plugin_id == "my_plugin"
    
    def test_fetch_data_success(self):
        """Test successful data fetch."""
        plugin = MyPlugin()
        config = {"api_key": "test_key", "location": "SF"}
        
        with patch('requests.get') as mock_get:
            mock_get.return_value = create_mock_response(
                data={"temperature": 72, "condition": "Sunny"}
            )
            
            result = plugin.fetch_data(config)
            
            assert result.available is True
            assert result.error is None
            assert result.data["temperature"] == 72
    
    def test_fetch_data_missing_config(self):
        """Test error handling for missing config."""
        plugin = MyPlugin()
        result = plugin.fetch_data({})
        
        assert result.available is False
        assert result.error is not None
    
    @patch('requests.get')
    def test_fetch_data_network_error(self, mock_get):
        """Test handling of network errors."""
        mock_get.side_effect = Exception("Network error")
        
        plugin = MyPlugin()
        result = plugin.fetch_data({"api_key": "test"})
        
        assert result.available is False
        assert "error" in result.error.lower()
    
    def test_validate_config_valid(self):
        """Test config validation with valid config."""
        plugin = MyPlugin()
        errors = plugin.validate_config({"api_key": "key123"})
        assert len(errors) == 0
    
    def test_validate_config_missing_required(self):
        """Test config validation detects missing fields."""
        plugin = MyPlugin()
        errors = plugin.validate_config({})
        assert len(errors) > 0
        assert any("api_key" in e.lower() for e in errors)


class TestMyPluginEdgeCases:
    """Edge case tests."""
    
    def test_empty_response_handling(self):
        """Test handling of empty API response."""
        plugin = MyPlugin()
        with patch('requests.get') as mock_get:
            mock_get.return_value = create_mock_response(data={})
            result = plugin.fetch_data({"api_key": "test"})
            # Should handle gracefully
            assert result is not None
    
    def test_timeout_handling(self):
        """Test handling of request timeout."""
        from requests.exceptions import Timeout
        
        plugin = MyPlugin()
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Timeout()
            result = plugin.fetch_data({"api_key": "test"})
            assert result.available is False
```

### conftest.py Template

Create a `conftest.py` with shared fixtures:

```python
"""Plugin test fixtures and configuration."""

import pytest
from unittest.mock import patch, MagicMock

from src.plugins.testing import PluginTestCase, create_mock_response


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
        "location": "San Francisco, CA",
        "refresh_seconds": 300
    }
```

### Running Plugin Tests

#### Run Tests for a Single Plugin

```bash
# Using the plugin test runner
python scripts/run_plugin_tests.py --plugin=my_plugin

# Using pytest directly
pytest plugins/my_plugin/tests/ -v
```

#### Run All Plugin Tests

```bash
# Using the plugin test runner (enforces 80% coverage)
python scripts/run_plugin_tests.py

# With verbose output
python scripts/run_plugin_tests.py --verbose

# Without coverage enforcement (for development)
python scripts/run_plugin_tests.py --no-coverage

# Dry run (show what would be tested)
python scripts/run_plugin_tests.py --dry-run
```

#### Run with Coverage Report

```bash
# Generate coverage report
pytest plugins/my_plugin/tests/ --cov=plugins/my_plugin --cov-report=term-missing

# With HTML report
pytest plugins/my_plugin/tests/ --cov=plugins/my_plugin --cov-report=html
```

### Coverage Requirements

| Requirement | Value |
|-------------|-------|
| Minimum coverage | **80%** |
| Coverage scope | Per-plugin (not global) |
| CI enforcement | Yes - builds fail below threshold |

#### Excluding Code from Coverage

Use `# pragma: no cover` sparingly for legitimately untestable code:

```python
def fetch_data(self) -> PluginResult:
    if not self.api_key:  # pragma: no cover
        # This is only hit in production with misconfiguration
        return PluginResult(available=False, error="API key missing")
```

### CI/CD Integration

When you submit a PR with a new plugin:

1. **Discovery**: CI automatically discovers plugins with `tests/` directories
2. **Test Execution**: Tests run with pytest and coverage
3. **Coverage Check**: Build fails if any plugin is below 80% coverage
4. **Report**: Coverage report uploaded to Codecov

### Testing Best Practices

1. **Test the Happy Path**: Ensure successful data fetch works
2. **Test Error Conditions**: API errors, network failures, invalid responses
3. **Test Configuration**: Valid and invalid config validation
4. **Test Edge Cases**: Empty responses, extreme values, missing fields
5. **Mock External APIs**: Never make real API calls in tests
6. **Test Variable Output**: Verify returned data matches manifest variables
7. **Use Descriptive Names**: `test_fetch_data_network_timeout` not `test_fetch_1`

### Local Development

1. Set any required environment variables for your plugin:
   ```bash
   export MY_PLUGIN_API_KEY=your_key
   ```

2. Run the service:
   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```

3. Check the plugin loaded:
   ```bash
   curl http://localhost:4420/api/plugins
   ```

4. Test data fetching:
   ```bash
   curl http://localhost:4420/api/plugins/my_plugin/data
   ```

### Plugin API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/plugins` | GET | List all plugins |
| `/plugins/{id}` | GET | Get plugin details |
| `/plugins/{id}/config` | PUT | Update configuration |
| `/plugins/{id}/enable` | POST | Enable plugin |
| `/plugins/{id}/disable` | POST | Disable plugin |
| `/plugins/{id}/data` | GET | Fetch plugin data |
| `/plugins/{id}/variables` | GET | Get variable schema |

## Best Practices

### Error Handling

Always handle errors gracefully:

```python
def fetch_data(self) -> PluginResult:
    try:
        # Your logic
        return PluginResult(available=True, data=data)
    except requests.RequestException as e:
        logger.warning(f"Network error: {e}")
        return PluginResult(available=False, error="Network unavailable")
    except Exception as e:
        logger.exception("Unexpected error")
        return PluginResult(available=False, error=str(e))
```

### Caching

Cache responses to reduce API calls:

```python
from datetime import datetime, timedelta

class MyPlugin(PluginBase):
    def __init__(self):
        super().__init__()
        self._cache = None
        self._cache_time = None
        self._cache_duration = timedelta(minutes=5)
    
    def fetch_data(self) -> PluginResult:
        # Return cache if valid
        if self._cache and self._cache_time:
            if datetime.now() - self._cache_time < self._cache_duration:
                return self._cache
        
        # Fetch fresh data
        result = self._fetch_fresh_data()
        
        # Update cache
        if result.available:
            self._cache = result
            self._cache_time = datetime.now()
        
        return result
```

### Logging

Use appropriate log levels:

```python
logger.debug("Detailed info for debugging")
logger.info("Plugin initialized successfully")
logger.warning("Non-critical issue occurred")
logger.error("Failed to fetch data")
logger.exception("Unexpected error with traceback")
```

### Configuration

Prefer UI configuration over environment variables:

```python
def fetch_data(self) -> PluginResult:
    # Check config first, then fall back to env var
    api_key = self.get_config("api_key") or os.getenv("MY_PLUGIN_API_KEY")
```

## Contributing Plugins

To contribute a plugin to the FiestaBoard repository:

1. Create a new directory under `plugins/`
2. Implement your plugin following this guide
3. **Add tests with >80% coverage** in `tests/` directory
4. Add comprehensive documentation in `README.md`
5. Submit a pull request

### PR Checklist

Before submitting your PR, ensure:

- [ ] Plugin ID matches directory name
- [ ] `manifest.json` is complete and valid
- [ ] `__init__.py` implements `PluginBase` correctly
- [ ] Tests exist in `tests/` directory
- [ ] Test coverage is >80%
- [ ] All tests pass locally
- [ ] `README.md` documents setup and usage
- [ ] No hardcoded secrets or API keys
- [ ] Appropriate error handling
- [ ] Logging uses appropriate levels

### Review Criteria

Your plugin will be reviewed for:

| Criteria | Description |
|----------|-------------|
| **Code Quality** | Clean code, error handling, follows patterns |
| **Test Coverage** | Minimum 80% coverage, meaningful tests |
| **Documentation** | Clear README with setup instructions |
| **Security** | No hardcoded secrets, input validation |
| **Performance** | Appropriate caching, rate limiting |
| **Compatibility** | Works with plugin system, valid manifest |

### Running CI Locally

Before submitting, run the full CI check locally:

```bash
# Run plugin tests with coverage enforcement
python scripts/run_plugin_tests.py --plugin=your_plugin

# Run all tests
pytest tests/ plugins/ -v

# Check linting
pylint plugins/your_plugin/
```

