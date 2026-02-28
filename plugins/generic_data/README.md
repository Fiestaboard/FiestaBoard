# Generic Data Plugin

![Generic Data Display](./docs/generic-data-display.png)

Fetch data from any URL (JSON or XML) and map fields to template variables — no custom plugin needed.

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and setup instructions

## Overview

The Generic Data plugin lets you pull data from any HTTP endpoint and map response fields to template variables using simple dot-notation paths. This is useful for integrating data sources that don't have a dedicated FiestaBoard plugin, such as:

- Public REST APIs (weather stations, transit feeds, IoT sensors)
- Self-hosted services (Home Assistant REST sensors, Node-RED endpoints)
- Static JSON files hosted on a web server
- RSS/Atom feeds served as XML

## Template Variables

Variables are **dynamic** — you define them in the settings using the "Variable Mappings" section. Each mapping creates a template variable.

For example, if you configure a mapping with variable name `temperature` and path `current.temp_f`, you can use it in templates as:

```
{{generic_data.temperature}}
```

### Built-in Variables

```
{{generic_data.raw_response}}   # First 22 characters of the raw response (for debugging)
```

## Quick Start

1. Enable the plugin in the FiestaBoard settings
2. Enter the URL of your data source
3. Add variable mappings:
   - **Variable Name**: The name you'll use in templates (e.g., `temperature`)
   - **Data Path**: Dot-notation path to the value in the response (e.g., `current.temp_f`)
   - **Default**: Fallback value if the path isn't found (optional)
4. Create a page template using your mapped variables

## Path Syntax

The data path uses dot-notation to navigate the response:

| Path | Matches |
|------|---------|
| `name` | Top-level field |
| `current.temp` | Nested field |
| `items[0].name` | First item in an array |
| `data.results[2].value` | Third result's value |
| `[0]` | First element of a root array |

### JSON Example

Given this response:

```json
{
  "current": {
    "temp_f": 72,
    "condition": { "text": "Sunny" }
  },
  "forecast": [
    { "day": "Monday", "high": 75 },
    { "day": "Tuesday", "high": 68 }
  ]
}
```

| Variable | Path | Result |
|----------|------|--------|
| `temperature` | `current.temp_f` | `72` |
| `condition` | `current.condition.text` | `Sunny` |
| `tomorrow_high` | `forecast[1].high` | `68` |

### XML Example

Given this response:

```xml
<weather>
  <current>
    <temp>72</temp>
    <condition>Sunny</condition>
  </current>
  <location>
    <name>San Francisco</name>
  </location>
</weather>
```

The XML is converted to a nested dict structure, so paths work the same way:

| Variable | Path | Result |
|----------|------|--------|
| `temp` | `current.temp` | `72` |
| `city` | `location.name` | `San Francisco` |

## Example Templates

### Weather Station

```
{center}WEATHER STATION
{{generic_data.location}}
TEMP: {{generic_data.temperature}}F
HUMIDITY: {{generic_data.humidity}}%
WIND: {{generic_data.wind_speed}} MPH
```

### IoT Sensor

```
{center}SENSOR READINGS
TEMP: {{generic_data.temp}}
HUMIDITY: {{generic_data.humidity}}
PRESSURE: {{generic_data.pressure}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| url | string | *(required)* | URL to fetch data from |
| format | string | "json" | Response format: `json` or `xml` |
| method | string | "GET" | HTTP method: `GET` or `POST` |
| headers | array | [] | Custom HTTP headers (e.g., for authentication) |
| body | string | | Request body for POST requests |
| mappings | array | *(required)* | Variable mappings (see above) |
| refresh_seconds | integer | 300 | How often to fetch new data (minimum 30s) |

### Authentication

To use APIs that require authentication, add a custom header:

| Header Name | Header Value |
|-------------|-------------|
| `Authorization` | `Bearer your-token-here` |

Or for API key authentication:

| Header Name | Header Value |
|-------------|-------------|
| `X-API-Key` | `your-api-key` |

## Features

- **Any URL**: Fetch data from any HTTP/HTTPS endpoint
- **JSON & XML**: Parse both JSON and XML responses
- **Dot-notation Paths**: Simple path syntax to extract values
- **Array Support**: Access items by index (e.g., `items[0].name`)
- **Default Values**: Fallback values when paths don't match
- **Custom Headers**: Add authentication and custom headers
- **POST Support**: Send request bodies for POST endpoints
- **Size Limit**: Responses limited to 1 MB for safety
- **No Dependencies**: Uses only the `requests` library (already included)

## Author

FiestaBoard Team
