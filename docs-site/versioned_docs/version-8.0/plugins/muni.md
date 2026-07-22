---
sidebar_position: 13
description: "Display real-time San Francisco Muni transit arrival predictions on your split-flap display."
keywords: [FiestaBoard Muni, SF transit, bus arrival times, train times, split-flap transit, Vestaboard Muni]
---

# SF Muni

Display real-time San Francisco Muni transit arrival predictions with multi-stop and multi-line support.

<BoardScreenshot src="/img/muni-display.png" alt="SF Muni on split-flap board" />

## Overview

The SF Muni plugin provides:

- Real-time arrival predictions for any Muni stop
- Monitor up to 4 stops simultaneously
- Line filtering and delay detection

## Setup

### 1. Get an API Key

1. Go to [the 511.org Open Data token page](https://511.org/open-data/token)
2. Register for a free API key

### 2. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **SF Muni** on
4. Enter your 511.org API key
5. Use the stop picker to select your stops
6. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{muni.formatted}` | Formatted arrivals display | `N JUDAH 3 MIN` |
| `{muni.stop_name}` | Stop name | `CHURCH + DUBOCE` |
| `{muni.line}` | Transit line | `N JUDAH` |
| `{muni.stop_count}` | Number of monitored stops | `2` |
| `{muni.is_delayed}` | Whether service is delayed | `false` |

## Next Steps

- [Bay Wheels Plugin](/docs/plugins/baywheels) -- Add bike share data
- [Traffic Plugin](/docs/plugins/traffic) -- Add commute times
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
