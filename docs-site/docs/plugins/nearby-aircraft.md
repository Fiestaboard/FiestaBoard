---
sidebar_position: 15
description: "Display real-time nearby aircraft information from OpenSky Network on your split-flap display."
keywords: [FiestaBoard aircraft tracking, nearby planes, OpenSky, flight tracking, split-flap aircraft, Vestaboard aviation]
---

# Nearby Aircraft

Display real-time aircraft information from the OpenSky Network, showing flights near your location.

<BoardScreenshot src="/img/nearby-aircraft-display.png" alt="Nearby Aircraft on split-flap board" />

## Overview

The Nearby Aircraft plugin shows:

- Aircraft call signs and types
- Altitude and ground speed
- Configurable search radius
- Up to 10 aircraft displayed

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Nearby Aircraft** on
4. Set your location coordinates and search radius
5. Click **Save Changes**

:::tip
No API key is required for basic usage. An optional OpenSky Network account increases rate limits -- register free at [the OpenSky Network](https://opensky-network.org/).
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{nearby_aircraft.formatted}` | Formatted aircraft display | `UAL 1532 B738 12K FT` |
| `{nearby_aircraft.headers}` | Column headers | `CALL SIGN TYPE ALT` |
| `{nearby_aircraft.aircraft_count}` | Number detected | `5` |
| `{nearby_aircraft.call_sign}` | First aircraft call sign | `UAL 1532` |
| `{nearby_aircraft.altitude}` | First aircraft altitude | `12000` |

## Next Steps

- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
- [Page Editor](/docs/features/page-editor) -- Design your aircraft display
