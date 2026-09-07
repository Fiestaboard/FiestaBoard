---
sidebar_position: 21
description: "Display guest WiFi network name and password on your split-flap display for visitors."
keywords: [FiestaBoard WiFi, guest WiFi display, WiFi credentials, split-flap WiFi, Vestaboard WiFi]
---

# Guest WiFi

Display your guest WiFi network name and password on the board for visitors. **No API key required.**

<BoardShot plugin="guest_wifi" alt="Guest WiFi on split-flap board" />

## Overview

The Guest WiFi plugin provides a simple way to share WiFi credentials:

- Network name (SSID)
- Password
- No external services needed -- just enter your credentials

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Guest WiFi** on
4. Enter your network name and password
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{guest_wifi.ssid}` | Network name | `MYNETWORK-GUEST` |
| `{guest_wifi.password}` | WiFi password | `WELCOME2024` |

## Example Page Layout

```text
┌──────────────────────┐
│                      │
│  WIFI NETWORK        │
│  MYNETWORK-GUEST     │
│  PASSWORD            │
│  WELCOME2024         │
│                      │
└──────────────────────┘
```

## Next Steps

- [Page Editor](/docs/features/page-editor) -- Design your WiFi display layout
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
