---
sidebar_position: 19
description: "Display the current TNG-style stardate on your split-flap display with FiestaBoard."
keywords: [FiestaBoard stardate, Star Trek stardate, TNG stardate, split-flap stardate, Vestaboard stardate]
---

# Stardate

Display the current TNG-era stardate on your board. **No API key required.**

<BoardShot plugin="stardate" alt="Stardate on split-flap board" />

## Overview

The Stardate plugin calculates and displays the current stardate using the TNG-era formula. It updates automatically based on your configured timezone.

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Stardate** on
4. Set your timezone
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{stardate.stardate}` | Current TNG-era stardate | `79145.7` |

## Next Steps

- [Star Trek Quotes Plugin](/docs/plugins/star-trek-quotes) -- Add quotes from the shows
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
