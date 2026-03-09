---
sidebar_position: 17
description: "Display what's currently playing via Last.fm scrobbling on your split-flap display."
keywords: [FiestaBoard Last.fm, now playing, music display, Spotify scrobbling, split-flap music, Vestaboard music]
---

# Last.fm Now Playing

Display what you're currently listening to via Last.fm scrobbling. Works with Spotify, Apple Music, and any scrobbling source.

<BoardScreenshot src="/img/last-fm-display.png" alt="Last.fm Now Playing on split-flap board" />

## Overview

The Last.fm plugin shows:

- Currently playing track title
- Artist name
- Album name (optional)
- Playing status

## Setup

### 1. Set Up Last.fm Scrobbling

1. Create an account at [last.fm](https://www.last.fm/)
2. Set up scrobbling from your music app (Spotify, Apple Music, etc.)

### 2. Get an API Key

1. Go to [last.fm/api/account/create](https://www.last.fm/api/account/create)
2. Create an API application (name it anything)
3. Copy your API key

### 3. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Last.fm** on
4. Enter your API key and Last.fm username
5. Click **Save Changes**

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{last_fm.title}` | Track title | `BOHEMIAN RHAPSODY` |
| `{last_fm.artist}` | Artist name | `QUEEN` |
| `{last_fm.album}` | Album name | `A NIGHT AT THE OPERA` |
| `{last_fm.is_playing}` | Whether playing | `true` |
| `{last_fm.formatted}` | Formatted display | `BOHEMIAN RHAPSODY - QUEEN` |
| `{last_fm.status}` | Status text | `NOW PLAYING` |

## Next Steps

- [Page Editor](/docs/features/page-editor) -- Create your music display layout
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
