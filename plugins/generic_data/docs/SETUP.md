# Generic Data Plugin — Setup Guide

## Prerequisites

- FiestaBoard running (Docker or local)
- A URL that returns JSON or XML data

## Step 1: Enable the Plugin

1. Open the FiestaBoard web UI
2. Navigate to **Settings → Plugins**
3. Find **Generic Data** and toggle it on

## Step 2: Configure the Data Source

### URL

Enter the full URL to your data source, for example:

```
https://api.example.com/sensor/latest
```

### Format

Choose `json` (default) or `xml` depending on what the URL returns.

### Authentication (optional)

If your endpoint requires authentication, add headers:

| Header Name | Header Value |
|-------------|-------------|
| `Authorization` | `Bearer your-api-token` |

## Step 3: Define Variable Mappings

Add one mapping for each piece of data you want to display.

| Variable Name | Data Path | Default |
|---------------|-----------|---------|
| `temperature` | `readings.temp_f` | `N/A` |
| `humidity` | `readings.humidity` | `N/A` |
| `status` | `device.status` | `unknown` |

### Path syntax

- `field` — top-level field
- `parent.child` — nested field
- `items[0].name` — first item in an array

## Step 4: Create a Page Template

Use your mapped variables in a page template:

```
{center}SENSOR STATUS
TEMP: {{generic_data.temperature}}
HUMIDITY: {{generic_data.humidity}}
STATUS: {{generic_data.status}}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GENERIC_DATA_URL` | Default URL (overridden by UI setting) |

## Troubleshooting

- **"Data URL not configured"**: Make sure you've entered a URL in the settings.
- **"Failed to parse response"**: Verify the URL returns valid JSON or XML and that the format setting matches.
- **"Request timed out"**: The endpoint may be slow or unreachable. The timeout is 30 seconds.
- **"Response too large"**: Responses are limited to 1 MB. Use a more specific API endpoint.
- **Variable shows default value**: Check that your data path matches the actual response structure. Use `{{generic_data.raw_json}}` to see the beginning of the response.
