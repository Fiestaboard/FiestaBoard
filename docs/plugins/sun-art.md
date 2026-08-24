---
sidebar_position: 22
description: "Display a full-screen sun art pattern that changes with the sun's position throughout the day."
keywords: [FiestaBoard sun art, visual display, sunrise sunset, split-flap art, Vestaboard art, sun position]
---

# Sun Art

Display a beautiful full-screen color pattern that changes throughout the day based on the sun's position. **No API key required.**

<BoardShot plugin="sun_art" alt="Sun Art on split-flap board" />

## Overview

The Sun Art plugin creates dynamic visual patterns using the board's color tiles:

- Pattern changes through 12 distinct stages (night, dawn, sunrise, morning, noon, etc.)
- Calculated from your location's actual sun position
- Uses all available color tiles for rich visuals

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Sun Art** on
4. Set your latitude and longitude
5. Click **Save Changes**

:::tip
Sun Art fills the entire board -- use it as a standalone full-screen display or in a schedule rotation.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{sun_art.sun_art}` | Full-screen pattern (use alone) | *(full board)* |
| `{sun_art.sun_stage}` | Current stage name | `SUNSET` |
| `{sun_art.sun_position}` | Sun elevation angle | `45.2` |
| `{sun_art.is_daytime}` | Whether sun is up | `true` |
| `{sun_art.time_to_sunrise}` | Time until sunrise | `06:30` |
| `{sun_art.time_to_sunset}` | Time until sunset | `12:15` |

## Sun Stages

| Stage | Description |
|-------|-------------|
| Night | Deep blue/violet tones |
| Late Night | Subtle pre-dawn hints |
| Dawn | First light on the horizon |
| Early Sunrise | Warm colors emerging |
| Sunrise | Full sunrise palette |
| Morning | Bright warm tones |
| Noon | Peak yellow/white |
| Afternoon | Warm golden hour begins |
| Sunset | Sun setting, orange/red sky |
| Late Sunset | Rich orange/red sky |
| Dusk | Fading purple tones |
| Twilight | Deep blue returning |

## Next Steps

- [Visual Clock Plugin](/docs/plugins/visual-clock) -- Another full-screen display
- [Schedule](/docs/features/schedule) -- Rotate Sun Art with other pages
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
