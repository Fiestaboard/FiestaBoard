---
sidebar_position: 12
description: "Display surf conditions including wave height, swell period, and quality ratings on your split-flap display."
keywords: [FiestaBoard surf, wave height, surf conditions, swell period, split-flap surf, Vestaboard surf]
---

# Surf Conditions

Display real-time surf conditions including wave height, swell period, wind, and quality ratings. **No API key required.**

<BoardScreenshot src="/img/surf-display.png" alt="Surf Conditions on split-flap board" />

## Overview

The Surf Conditions plugin provides:

- Wave height in feet
- Swell period in seconds
- Wind speed and direction
- Quality rating (Excellent, Good, Fair, Poor) with color coding

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Surf Conditions** on
4. Set the latitude and longitude of your surf spot
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{surf.wave_height}` | Wave height in feet | `4.5` |
| `{surf.swell_period}` | Swell period in seconds | `14` |
| `{surf.quality}` | Quality rating | `GOOD` |
| `{surf.quality_color}` | Color tile for quality | `{66}` |
| `{surf.wind_speed}` | Wind speed in mph | `8` |
| `{surf.wind_direction}` | Wind direction | `NW` |
| `{surf.formatted}` | Pre-formatted message | `4-6 FT 14 SEC GOOD` |

## Next Steps

- [Weather Plugin](/docs/plugins/weather) -- Add weather conditions
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
