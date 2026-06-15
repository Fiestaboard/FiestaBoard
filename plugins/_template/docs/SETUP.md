# My Plugin Name Setup Guide

The My Plugin Name plugin fetches data from [service] and displays it on your board.

## Overview

**What it does:**
- Feature one
- Feature two
- Feature three

**Prerequisites:**
- API key from [service website](https://example.com) (free tier available)

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI:
1. Go to **Integrations**
2. Find **My Plugin Name** and toggle it **On**

<!-- Add a screenshot to `docs/integrations.png`, then replace this comment with:
     ![My Plugin Name in Integrations list](./integrations.png) -->

### 2. Configure My Plugin Name

1. Click the **Configure** button
2. Enter your **API Key**
3. Adjust other settings as needed
4. Click **Save Changes**

<!-- Add a screenshot to `docs/configuration.png`, then replace this comment with:
     ![My Plugin Name configuration dialog](./configuration.png) -->

### 3. Create a Board Template

1. Go to **Pages** in the web UI
2. Click **Create Page** or edit an existing page
3. Add plugin variables using the variable picker or type them directly

Example template:

```jinja
{center}MY PLUGIN
{{my_plugin.value}}
{{my_plugin.status}}
```

### 4. View on Your Board

Once configured, the plugin output displays on your board when the page is active:

<!-- Add a screenshot to `docs/board-display.png`, then replace this comment with:
     ![My Plugin Name on Vestaboard](./board-display.png) -->

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{my_plugin.value}}` | The primary data value | `123` |
| `{{my_plugin.status}}` | Current status text | `OK` |
| `{{my_plugin.formatted}}` | Pre-formatted display string | `Value: 123` |

## Configuration Reference

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `enabled` | boolean | No | false | Enable/disable the plugin |
| `api_key` | string | Yes | — | Your API key from [service] |
| `refresh_seconds` | integer | No | 300 | How often to fetch new data (seconds) |

### Environment Variables

You can also configure the plugin via environment variables:

```bash
MY_PLUGIN_API_KEY=your-api-key-here
```

## Troubleshooting

**Issue: Plugin shows "Not Available"**
- Ensure your API key is correct and active
- Check that the service is reachable from your network
- Verify your account has API access enabled

**Issue: Data not updating**
- Check the refresh interval setting
- Verify the API is not rate-limited
- Check the Docker logs for error messages: `docker compose logs -f`
