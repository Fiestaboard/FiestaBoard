# Star Trek Quotes Setup

Display inspiring Star Trek quotes from The Next Generation (TNG), Voyager (VOY), and Deep Space Nine (DS9) on your board.

## Overview

The Star Trek quotes feature displays random quotes from three iconic Star Trek series with a configurable ratio:
- **TNG (The Next Generation)** - Featuring Picard, Data, Worf, and more
- **Voyager** - Featuring Janeway, Seven of Nine, the Doctor, and more
- **DS9 (Deep Space Nine)** - Featuring Sisko, Garak, Odo, Quark, and more

## Configuration

Add these settings to your `.env` file:

```bash
# Star Trek Quotes Configuration
STAR_TREK_QUOTES_ENABLED=true
STAR_TREK_QUOTES_RATIO=3:5:9
```

### Configuration Options

#### `STAR_TREK_QUOTES_ENABLED`

Enable or disable Star Trek quotes.

**Options:**
- `true` - Enable Star Trek quotes
- `false` - Disable Star Trek quotes

**Example:**
```bash
STAR_TREK_QUOTES_ENABLED=true
```

#### `STAR_TREK_QUOTES_RATIO`

Control the ratio between series. Format: `TNG:Voyager:DS9`

**Default:** `3:5:9`

This means:
- TNG quotes appear ~18% of the time (3 out of 17 total weight)
- Voyager quotes appear ~29% of the time (5 out of 17 total weight)
- DS9 quotes appear ~53% of the time (9 out of 17 total weight)

**Examples:**
```bash
# Default (DS9-focused)
STAR_TREK_QUOTES_RATIO=3:5:9

# Equal distribution
STAR_TREK_QUOTES_RATIO=1:1:1

# TNG-focused
STAR_TREK_QUOTES_RATIO=9:3:3

# Voyager-focused
STAR_TREK_QUOTES_RATIO=3:9:3

# DS9 only
STAR_TREK_QUOTES_RATIO=0:0:1

# TNG only
STAR_TREK_QUOTES_RATIO=1:0:0
```

## Display Format

Quotes are displayed in this format:

```
Quote text here, split
across multiple lines
if needed.

- Character Name
  SERIES
```

**Example (TNG):**
```
Make it so.

- Picard
  TNG
```

**Example (DS9):**
```
The truth is usually
just an excuse for a
lack of imagination.

- Garak
  DS9
```

**Example (Voyager):**
```
There is coffee in
that nebula!

- Janeway
  VOY
```

## Quote Collection

The system includes a curated collection of memorable quotes:

- **17 TNG quotes** - From Picard, Data, Worf, and more
- **28 Voyager quotes** - From Janeway, Seven of Nine, the Doctor, and more
- **52 DS9 quotes** - From Sisko, Garak, Odo, Quark, Kira, and more

All quotes are optimized to fit the 6-line display with proper spacing.

### Sample Quotes

**TNG:**
- "Make it so." - Picard
- "There are four lights!" - Picard
- "It is possible to commit no mistakes and still lose." - Picard
- "Today is a good day to die." - Worf
- "Resistance is futile." - Borg

**Voyager:**
- "Do it." - Janeway
- "There's coffee in that nebula!" - Janeway
- "Fear exists for one purpose: to be conquered." - Janeway
- "Survival is insufficient." - Seven of Nine
- "Please state the nature of the medical emergency." - Doctor

**DS9:**
- "It's easy to be a saint in paradise." - Sisko
- "The truth is just an excuse for lack of imagination." - Garak
- "Paranoia is just another word for longevity." - Garak
- "Never begin a negotiation on an empty stomach." - Quark
- "What you leave behind is not as important as how you lived." - Sisko

## Using Star Trek Quotes

To display Star Trek quotes on your board:

1. Enable the feature in your `.env` file
2. Create a page in the web UI using the `{{star_trek.quote}}` template variable
3. Set that page as active

### Template Variables

Available Star Trek template variables:
- `{{star_trek_quotes.quote}}` - The quote text
- `{{star_trek_quotes.character}}` - The character name
- `{{star_trek_quotes.series}}` - Series abbreviation (TNG, VOY, DS9)
- `{{star_trek_quotes.series_color}}` - Color tile based on series

### Example Template

Create a centered quote display:

```
{center}{{star_trek_quotes.quote|wrap}}




{center}- {{star_trek_quotes.character}}
```

**Tip:** The `|wrap` filter automatically word-wraps long quotes across multiple lines, and `{center}` centers each line on the display.

### Display Example

![Star Trek Quotes Display](./star-trek-quotes-display.png)

*Example showing a centered quote with character attribution on the FiestaBoard.*

## Common Configurations

### Equal Distribution
```bash
STAR_TREK_QUOTES_ENABLED=true
STAR_TREK_QUOTES_RATIO=1:1:1
```

### TNG-Focused
```bash
STAR_TREK_QUOTES_ENABLED=true
STAR_TREK_QUOTES_RATIO=9:3:3
```

### Voyager-Focused
```bash
STAR_TREK_QUOTES_ENABLED=true
STAR_TREK_QUOTES_RATIO=3:9:3
```

### DS9-Focused (Default)
```bash
STAR_TREK_QUOTES_ENABLED=true
STAR_TREK_QUOTES_RATIO=3:5:9
```

## Troubleshooting

### Quotes Not Showing

1. **Check if enabled:**
   ```bash
   grep STAR_TREK_QUOTES_ENABLED .env
   # Should show: STAR_TREK_QUOTES_ENABLED=true
   ```

2. **Check logs:**
   ```bash
   docker-compose logs | grep -i "star trek"
   ```

### Wrong Ratio

1. **Verify ratio format:**
   - Format must be `TNG:Voyager:DS9`
   - Example: `3:5:9`

### Quotes Too Long

Quotes are automatically truncated to fit the 6x22 board display. Long quotes are split across multiple lines.

## Adding Custom Quotes

To add your own quotes, edit `src/utils/star_trek_quotes.json`:

```json
{
  "tng": [
    {"quote": "Your custom quote here", "character": "Character Name"}
  ],
  "voyager": [
    {"quote": "Another quote", "character": "Character Name"}
  ],
  "ds9": [
    {"quote": "Yet another quote", "character": "Character Name"}
  ]
}
```

After editing, restart the service:
```bash
docker-compose restart
```

## Restart After Changes

After changing Star Trek quotes settings, restart the service:

```bash
docker-compose restart
docker-compose logs -f
```

## Summary

- **Enable quotes**: `STAR_TREK_QUOTES_ENABLED=true`
- **Control ratio**: `STAR_TREK_QUOTES_RATIO=3:5:9` (TNG:Voyager:DS9)
- **Use in pages**: Include `{{star_trek.quote}}` in your page template

Live long and prosper! 🖖
