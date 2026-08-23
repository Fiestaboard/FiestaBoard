---
sidebar_position: 5
description: "Display Home Assistant smart home data on your Vestaboard. Show door sensors, temperature, lights, and more with the FiestaBoard Home Assistant plugin."
keywords: [FiestaBoard Home Assistant, Vestaboard Home Assistant, Vestaboard Home Assistant integration, Vestaboard smart home, smart home display, IoT display, sensor data, home automation]
---

# Home Assistant Plugin

Display smart home device states from your Home Assistant instance on your board.

<BoardShot plugin="home_assistant" alt="Home Assistant on split-flap board" />

## Overview

The Home Assistant plugin connects to your Home Assistant server and displays entity states on your Vestaboard: door sensors, temperature readings, light status, and any other entity your HA instance tracks.

## Setup

### 1. Generate a Long-Lived Access Token

1. Open your Home Assistant instance
2. Click your profile name in the sidebar
3. Scroll to **Long-Lived Access Tokens**
4. Click **Create Token**
5. Give it a name (e.g., "FiestaBoard")
6. Copy the token immediately. It won't be shown again

### 2. Configure in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle the **Home Assistant** plugin on
4. Enter your Home Assistant URL (e.g., `http://192.168.1.100:8123`)
5. Paste your long-lived access token
6. Click **Save Changes**

## Available Variables

The Home Assistant plugin provides dynamic variables based on your configured entities:

| Variable | Description | Example |
|----------|-------------|---------|
| `{home_assistant.connected}` | Whether HA is connected | `true` |

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

```text
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

- [Plugins Overview](/docs/plugins/overview) - See all available plugins
- [Plugin Configuration](/docs/plugins/configuration) - General plugin management
