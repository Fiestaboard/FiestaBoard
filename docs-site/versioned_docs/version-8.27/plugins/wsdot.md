---
sidebar_position: 16
description: "Display Washington State Ferry schedules, vessel names, car spots, and alerts on your split-flap display."
keywords: [FiestaBoard WSDOT, Washington ferries, ferry schedule, ferry wait times, split-flap ferry, Vestaboard ferry]
---

# WSDOT Ferries

Display Washington State Ferry schedules, vessel names, car availability, and service alerts.

<BoardScreenshot src="/img/wsdot-display.png" alt="WSDOT Ferries on split-flap board" />

## Overview

The WSDOT plugin shows:

- Next departure times for your routes
- Vessel names
- Available car spots
- Service alerts

## Setup

### 1. Get an API Key

1. Go to [wsdot.wa.gov/traffic/api](https://wsdot.wa.gov/traffic/api/)
2. Register for a free API access code

### 2. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **WSDOT** on
4. Enter your API access code
5. Select your ferry routes (up to 4)
6. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{wsdot.formatted}` | Formatted ferry info | `SEATTLE-BAINBRIDGE 3:30 PM` |
| `{wsdot.headers}` | Display headers | `WA FERRIES` |
| `{wsdot.route_count}` | Number of routes configured | `2` |
| `{wsdot.has_alerts}` | Whether alerts are active | `false` |

## Next Steps

- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
- [Schedule](/docs/features/schedule) -- Show ferry info during commute hours
