# Generic Data Plugin — Setup Guide

## Overview

The Generic Data plugin fetches data from any URL (JSON or XML) and maps response fields to template variables using dot-notation paths.

**Prerequisites:**
- FiestaBoard running (Docker or local)
- A URL that returns JSON or XML data

## Quick Setup

### 1. Enable the Plugin

1. Open the FiestaBoard web UI
2. Navigate to **Settings → Plugins**
3. Find **Generic Data** and toggle it on

### 2. Configure the Data Source

#### URL

Enter the full URL to your data source, for example:

```
https://api.example.com/sensor/latest
```

You can include **built-in placeholders** in the URL or header values so they update each fetch (FiestaBoard 4.2.0+), for example `https://api.example.com/data?date={{date}}` or `{{date:%Y%m%d}}`. See the FiestaBoard plugin development guide for the full list.

#### Format

Choose `json` (default) or `xml` depending on what the URL returns.

#### Authentication (optional)

If your endpoint requires authentication, add headers:

| Header Name | Header Value |
|-------------|-------------|
| `Authorization` | `Bearer your-api-token` |

### 3. Define Variable Mappings

Add one mapping for each piece of data you want to display.

| Variable Name | Data Path | Default |
|---------------|-----------|---------|
| `temperature` | `readings.temp_f` | `N/A` |
| `humidity` | `readings.humidity` | `N/A` |
| `status` | `device.status` | `unknown` |

#### Path syntax

- `field` — top-level field
- `parent.child` — nested field
- `items[0].name` — first item in an array

### 4. Create a Page Template

Use your mapped variables in a page template:

```
{center}SENSOR STATUS
TEMP: {{generic_data.temperature}}
HUMIDITY: {{generic_data.humidity}}
STATUS: {{generic_data.status}}
```

## Multiple Feeds Setup

If you need data from more than one API, use the **Data Feeds** section instead of the top-level URL.

### Step 1: Add Feeds

Add a feed for each data source. Each feed has:

- **Name**: A label (e.g., "Weather API")
- **URL**: The endpoint URL
- **Format**: `json` or `xml`
- **Headers**: Any authentication headers
- **Mappings**: Variables to extract

### Step 2: Use Unique Variable Names

All variables from all feeds share the same namespace. Make sure each variable name is unique across all feeds.

**Good:**

| Feed | Variable | Path |
|------|----------|------|
| Weather | `temperature` | `current.temp_f` |
| Weather | `condition` | `current.condition.text` |
| Traffic | `commute_time` | `route.duration` |
| Traffic | `traffic_status` | `route.status` |

**Bad** (duplicate names across feeds):

| Feed | Variable | Path |
|------|----------|------|
| Weather | `status` | `current.condition.text` |
| Traffic | `status` | `route.status` |

### Step 3: Create a Template

Use variables from all feeds in a single template:

```
{center}DASHBOARD
TEMP: {{generic_data.temperature}}°F
SKY: {{generic_data.condition}}
DRIVE: {{generic_data.commute_time}}
TRAFFIC: {{generic_data.traffic_status}}
```

## Configuration Reference

| Setting | Description | Default |
|---------|-------------|---------|
| `url` | URL to fetch data from (single-feed mode) | — |
| `format` | Response format: `json` or `xml` | `json` |
| `method` | HTTP method: `GET` or `POST` | `GET` |
| `headers` | Custom HTTP headers | `[]` |
| `body` | Request body for POST requests | — |
| `mappings` | Variable mappings (single-feed mode) | `[]` |
| `feeds` | Multiple data sources (overrides url/mappings) | — |
| `refresh_seconds` | How often to fetch new data (minimum 30s) | `300` |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GENERIC_DATA_URL` | Default URL for single-feed mode (overridden by UI setting) |

## Troubleshooting

- **"No data feeds configured"**: Make sure you've entered a URL or added feeds.
- **"Failed to parse response"**: Verify the URL returns valid JSON or XML and that the format setting matches.
- **"Request timed out"**: The endpoint may be slow or unreachable. The timeout is 30 seconds.
- **"Response too large"**: Responses are limited to 1 MB each. Use a more specific API endpoint.
- **Variable shows default value**: Check that your data path matches the actual response structure.
- **"Duplicate variable name"**: Variable names must be unique across all feeds. Rename one of the conflicting variables.
- **Partial data**: If one feed fails, variables from other feeds will still be available. Check the feed's URL and authentication.
