---
sidebar_position: 26
description: "Show the movie, TV episode, or song playing on your Plex Media Server on your split-flap display."
keywords: [FiestaBoard Plex, Plex now playing, Plex Media Server, movie display, TV episode display, Vestaboard Plex, split-flap Plex]
---

# Plex Now Playing

Show what's playing on your Plex Media Server: movies, TV episodes, and music, laid out to fit any board.

<BoardShot plugin="plex" alt="Plex Now Playing on split-flap board" />

## Overview

The Plex plugin shows:

- The movie, TV episode, or track that is playing
- Show name, season and episode, or artist and album
- Playback state: playing, paused, or buffering
- Who is watching, on which device, and how much time is left

It lays the title out to fit your board. A long title wraps onto a second line and the rest of the layout moves down to make room. The same page works on a Note, a Flagship, or a Note Array.

## Setup

### 1. Find Your Plex Token

1. Open [Plex Web](https://app.plex.tv/) and sign in with an account on your server
2. Open any movie or episode in your library
3. Click the **⋯** menu, choose **Get Info**, then **View XML**
4. Copy the value after `X-Plex-Token=` at the end of the new tab's address

Treat the token like a password: it grants access to your Plex account.

### 2. Enable in the Web UI

1. Open **http://localhost:4420**
2. Go to the **Integrations** page
3. Toggle **Plex Now Playing** on
4. Enter your **Plex Server URL** (for example `http://192.168.1.100:32400`) and paste your **Plex Token**
5. Optionally, set **Plex User** to show only one person's streams
6. Click **Save Changes**

If FiestaBoard runs in Docker, use your Plex server's LAN IP address, not `localhost`.

## Display Lines

`line_1`, `line_2`, and `line_3` hold a ready-made layout for the board being rendered. Center them for the classic look:

```text
{{plex.line_1}}
{{plex.line_2}}
{{plex.line_3}}
```

| Playing | Title fits one line | Title needs two lines |
|---------|---------------------|-----------------------|
| Movie | title / *blank* / year | title / title / year |
| TV episode | show / season+episode / episode title | show / show / season+episode |
| Music | track / artist / album | track / track / artist |
| Nothing | *blank* / `Nothing playing` / *blank* | |

A third line that doesn't fit the board ends in `...`. With **Plex yellow accents** on, the year or season/episode line is framed by two yellow tiles on each side.

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{plex.line_1}}` | First display line | `BREAKING BAD` |
| `{{plex.line_2}}` | Second display line | `S05 E14` |
| `{{plex.line_3}}` | Third display line | `OZYMANDIAS` |
| `{{plex.title}}` | Movie, episode, or track title | `OZYMANDIAS` |
| `{{plex.year}}` | Release year | `2013` |
| `{{plex.show}}` | TV show name | `BREAKING BAD` |
| `{{plex.season_episode}}` | Season and episode | `S05 E14` |
| `{{plex.artist}}` | Artist (music) | `DAFT PUNK` |
| `{{plex.album}}` | Album (music) | `DISCOVERY` |
| `{{plex.media_type}}` | `Movie`, `Episode`, `Track`, or `Clip` | `EPISODE` |
| `{{plex.state}}` | `Playing`, `Paused`, `Buffering`, or `Idle`, color-coded | `PLAYING` |
| `{{plex.is_playing}}` | Whether something is playing | `true` |
| `{{plex.user}}` | Plex user watching or listening | `ALEX` |
| `{{plex.player}}` | Device playing the stream | `LIVING ROOM TV` |
| `{{plex.progress_percent}}` | Progress through the item (0-100) | `64` |
| `{{plex.minutes_left}}` | Minutes remaining | `18` |
| `{{plex.stream_count}}` | Number of active streams | `2` |

When several people are streaming, the plugin features whichever stream is playing, ahead of buffering or paused ones. Every stream is also available as `{{plex.sessions.0.title}}`, `{{plex.sessions.1.title}}`, and so on, with the same fields.

## Next Steps

- [Plex plugin setup guide](https://github.com/Fiestaboard/fiestaboard-plugin--plex/blob/main/docs/SETUP.md) -- Settings reference and troubleshooting
- [Page Editor](/docs/features/page-editor) -- Create your now-playing layout
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
