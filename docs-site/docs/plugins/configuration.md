---
sidebar_position: 2
description: "Enable and configure FiestaBoard plugins through the web UI or environment variables for your split-flap display."
keywords: [FiestaBoard plugin configuration, enable plugins, plugin settings, environment variables, plugin setup]
---

# Plugin Configuration

Learn how to enable, configure, and manage FiestaBoard plugins.

## Enabling Plugins

### Via the Web UI (Recommended)

1. Open `http://localhost:3000`
2. Go to the **Integrations** page
3. Toggle plugins **on** or **off**
4. Click on a plugin to configure its settings

### Via the API

```bash
# Enable a plugin
curl -X POST http://localhost:3000/plugins/weather/enable

# Disable a plugin
curl -X POST http://localhost:3000/plugins/weather/disable

# Get plugin configuration
curl http://localhost:3000/plugins/weather/config

# Update plugin configuration
curl -X PUT http://localhost:3000/plugins/weather/config \
  -H "Content-Type: application/json" \
  -d '{"location": "San Francisco, CA"}'
```

## Configuration Methods

Plugins can be configured in two ways:

### 1. Web UI Settings

Each plugin has a settings form accessible from the Integrations page. Settings configured through the UI are stored in FiestaBoard's data directory and persist across restarts.

### 2. Environment Variables

Most plugins support configuration via environment variables in your `.env` file. This is useful for:

- Initial setup before the web UI is available
- Docker deployment where you want all config in one place
- Sensitive values like API keys

:::info Priority
Web UI settings take priority over environment variables. If a setting is configured in both places, the Web UI value is used.
:::

## Using Plugin Variables in Pages

Once a plugin is enabled, its template variables become available in the page editor:

1. Open the **Page Editor**
2. Click the **Variable Picker**
3. Select a plugin to see its available variables
4. Click a variable to insert it

### Variable Format

Variables use the format `{plugin_name.variable_name}`:

```
Temperature: {weather.temperature}
Conditions:  {weather.conditions}
```

### Array Variables

Some plugins provide array variables that expand into multiple lines:

```
{stocks.prices}    → Displays all stock rows
{muni.arrivals}    → Displays all transit arrivals
```

## Plugin Data API

You can query plugin data directly:

```bash
# Get all available variables from a plugin
curl http://localhost:3000/plugins/weather/variables

# Get raw plugin data
curl http://localhost:3000/plugins/weather/data

# List all plugins and their status
curl http://localhost:3000/plugins
```

## Next Steps

- [Plugins Overview](/docs/plugins/overview) - See all available plugins
- [Page Editor](/docs/features/page-editor) - Use plugin data in your pages
- [Plugin Development Guide](/docs/development/plugin-guide) - Create custom plugins
