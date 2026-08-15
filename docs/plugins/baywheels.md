---
sidebar_position: 14
description: "Display Bay Wheels bike share availability with electric and classic bike counts on your split-flap display."
keywords: [FiestaBoard Bay Wheels, bike share, electric bikes, transit, split-flap bike availability, Vestaboard transit]
---

# Bay Wheels

Display real-time Bay Wheels bike share station availability, including electric and classic bike counts. **No API key required.**

<BoardScreenshot src="/img/baywheels-display.png" alt="Bay Wheels on split-flap board" />

## Overview

The Bay Wheels plugin shows:

- Electric and classic bike counts per station
- Multiple station monitoring (select your favorites)
- Best station summary across all monitored stations

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Bay Wheels** on
4. Use the station picker to select stations near you
5. Click **Save Changes**

:::tip
No API key is needed -- Bay Wheels uses a public data feed.
:::

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{baywheels.total_electric}` | Total e-bikes across stations | `12` |
| `{baywheels.total_classic}` | Total classic bikes across stations | `8` |
| `{baywheels.total_bikes}` | Total bikes across all stations | `20` |
| `{baywheels.station_count}` | Number of monitored stations | `3` |
| `{baywheels.best_station_name}` | Station with most bikes | `MARKET + 2ND` |
| `{baywheels.best_station_electric}` | E-bikes at best station | `5` |

## Next Steps

- [SF Muni Plugin](/docs/plugins/muni) -- Pair with transit arrival times
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
