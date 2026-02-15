---
sidebar_position: 5
---

# Home Assistant Plugin

Display smart home device states from your Home Assistant instance on your board.

## Overview

The Home Assistant plugin connects to your Home Assistant server and displays entity states — door sensors, temperature readings, light status, and any other entity your HA instance tracks.

## Setup

### 1. Generate a Long-Lived Access Token

1. Open your Home Assistant instance
2. Click your profile name in the sidebar
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**
5. Give it a name (e.g., "FiestaBoard")
6. Copy the token immediately — it won't be shown again

### 2. Configure FiestaBoard

Add to your `.env` file:

```bash
HOME_ASSISTANT_URL=http://192.168.1.100:8123    # Your HA address
HOME_ASSISTANT_TOKEN=your_long_lived_token_here
```

Or configure via the Web UI Integrations page.

### 3. Enable the Plugin

Go to **Integrations** in the Web UI and toggle the Home Assistant plugin on.

## Available Variables

The Home Assistant plugin provides dynamic variables based on your configured entities:

| Variable | Description | Example |
|----------|-------------|---------|
| `{home_assistant.status}` | Formatted entity states | `FRONT DOOR CLOSED` |

## Entity Selection

In the plugin settings, you can select which Home Assistant entities to display using the **Entity Picker**:

1. Go to **Integrations → Home Assistant**
2. Use the entity picker to browse and select entities
3. Choose from sensors, switches, binary sensors, etc.

## Color Coding

The plugin uses colors to indicate state:

| State | Color | Meaning |
|-------|-------|---------|
| Closed / Off / Locked | 🟩 Green | Secure/Normal |
| Open / On / Unlocked | 🟥 Red | Attention needed |

## Example Display

```
┌──────────────────────┐
│   HOME STATUS        │
│  FRONT DOOR   CLOSED │
│  GARAGE       CLOSED │
│  BACK DOOR    OPEN   │
│  TEMP INSIDE    72 F │
│  LIGHTS         ON   │
└──────────────────────┘
```

## Requirements

- Home Assistant instance accessible from FiestaBoard's network
- Long-lived access token with sufficient permissions
- Entities must be accessible via the HA REST API

## Troubleshooting

### Connection Refused

- Verify the Home Assistant URL is correct and reachable
- Check that HA is running and the API is enabled
- If using Docker, ensure network connectivity between containers

### 401 Unauthorized

- Regenerate your long-lived access token
- Verify the token is correctly set in `.env` or the Web UI

### Entities Not Showing

- Check that the entities exist in Home Assistant
- Verify the token has access to those entities

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — See all available plugins
- [Plugin Configuration](/docs/plugins/configuration) — General plugin management
