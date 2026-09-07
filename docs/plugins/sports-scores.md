---
sidebar_position: 6
description: "Display live NFL, NBA, NHL, and soccer scores on your Vestaboard with FiestaBoard's sports plugin."
keywords: [FiestaBoard sports scores, Vestaboard sports scores, Vestaboard NFL, Vestaboard NBA, NFL scores, NBA scores, NHL scores, soccer scores, split-flap sports, live scores]
---

# Sports Scores Plugin

Display recent sports scores from NFL, Soccer, NHL, and NBA on your board.

<BoardShot plugin="sports_scores" alt="Sports scores on split-flap board" />

## Overview

The Sports Scores plugin fetches recent match results and displays formatted scores. It supports multiple leagues and updates automatically.

## Setup

The Sports Scores plugin works **without an API key** using free data from TheSportsDB. For enhanced data, you can optionally provide an API key.

### Basic Setup (No API Key)

1. Go to **Integrations** in the Web UI
2. Toggle the Sports Scores plugin on
3. Configure your preferred leagues

### Enhanced Setup (Optional API Key)

1. Sign up at [TheSportsDB](https://www.thesportsdb.com/)
2. Get a free API key
3. In the Web UI, go to **Integrations** > **Sports Scores** and enter the key

## Supported Leagues

| League | Sport |
|--------|-------|
| NFL | American Football |
| NBA | Basketball |
| NHL | Hockey |
| Soccer | Various soccer leagues |

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{sports_scores.formatted}` | Formatted recent scores | `NFL CHIEFS 27 BILLS 24` |

## Example Display

```text
┌──────────────────────┐
│  SPORTS SCORES       │
│  NFL  CHIEFS 27      │
│       BILLS  24      │
│  NBA  LAKERS 112     │
│       CELTS  108     │
│                      │
└──────────────────────┘
```

## Next Steps

- [Plugins Overview](/docs/plugins/overview) - See all available plugins
- [Plugin Configuration](/docs/plugins/configuration) - General plugin management
