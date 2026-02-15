---
sidebar_position: 1
---

# Plugin Development Guide

Create your own FiestaBoard plugins to display custom data on your split-flap display.

## Plugin Structure

Each plugin is a self-contained directory in `plugins/`:

```
plugins/
└── my_plugin/
    ├── __init__.py          # Plugin entry point
    ├── plugin.py            # Main plugin class
    ├── README.md            # Developer documentation
    └── docs/
        └── SETUP.md         # User setup guide
```

## Creating a New Plugin

1. **Copy the template**

```bash
cp -r plugins/_template plugins/my_plugin
```

2. **Implement the plugin class**

```python
# plugins/my_plugin/plugin.py
from src.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    """My custom plugin."""
    
    name = "my_plugin"
    display_name = "My Plugin"
    description = "Displays my custom data"
    
    def get_data(self) -> dict:
        """Fetch and return data for display."""
        return {
            "title": "My Data",
            "value": "Hello World!"
        }
    
    def format_for_display(self, data: dict) -> str:
        """Format data for the split-flap display."""
        return f"{data['title']}: {data['value']}"
```

3. **Register the plugin**

Add your plugin to `plugins/__init__.py`:

```python
from plugins.my_plugin.plugin import MyPlugin
```

4. **Add documentation**

Create `README.md` and `docs/SETUP.md` for your plugin.

## Plugin API

### BasePlugin Methods

| Method | Description |
|--------|-------------|
| `get_data()` | Fetch data from your source |
| `format_for_display(data)` | Format data for the display |
| `get_config()` | Return plugin configuration |
| `validate_config()` | Validate required settings |

### Configuration

Plugins can define configuration options:

```python
class MyPlugin(BasePlugin):
    config_schema = {
        "api_key": {
            "type": "string",
            "required": True,
            "env_var": "MY_PLUGIN_API_KEY"
        },
        "refresh_interval": {
            "type": "integer",
            "default": 300
        }
    }
```

## Testing Your Plugin

```bash
# Run plugin tests
pytest plugins/my_plugin/tests/

# Test in development
docker-compose -f docker-compose.dev.yml up --build
```

## Contributing Plugins

1. Fork the repository
2. Create your plugin
3. Add tests and documentation
4. Submit a pull request

We welcome community plugins! Check out existing plugins for examples.
