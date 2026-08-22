---
sidebar_position: 18
description: "Display random Star Trek quotes from TNG, Voyager, and DS9 on your split-flap display."
keywords: [FiestaBoard Star Trek, quotes display, TNG quotes, split-flap Star Trek, Vestaboard quotes]
---

# Star Trek Quotes

Display random quotes from Star Trek: The Next Generation, Voyager, and Deep Space Nine. **No API key required.**

<BoardShot plugin="star_trek_quotes" alt="Star Trek Quotes on split-flap board" />

## Overview

The Star Trek Quotes plugin provides:

- Random quotes from TNG, Voyager, and DS9
- Character attribution
- Configurable series weighting
- Color-coded by series

## Setup

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Star Trek Quotes** on
4. (Optional) Adjust the series ratio to prefer certain shows
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{star_trek_quotes.quote}` | The quote text | `MAKE IT SO` |
| `{star_trek_quotes.character}` | Character name | `PICARD` |
| `{star_trek_quotes.series}` | Series code | `TNG` |
| `{star_trek_quotes.series_color}` | Color tile for series | `{63}` |

## Series Ratio

The default ratio is `3:5:9` (TNG:Voyager:DS9). Adjust this in the plugin settings to see more quotes from your preferred series.

## Next Steps

- [Stardate Plugin](/docs/plugins/stardate) -- Display the current stardate
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
