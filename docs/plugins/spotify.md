---
sidebar_position: 28
description: "Show the song or podcast playing on your Spotify account on your split-flap display, with a progress bar, the device, and what's up next."
keywords: [FiestaBoard Spotify, Spotify now playing, Spotify display, Spotify progress bar, Spotify queue, Vestaboard Spotify, split-flap Spotify]
---

# Spotify

Show what's playing on your Spotify account: the track, artist, progress, device, and what's up next.

<BoardShot plugin="spotify" alt="Spotify now playing on split-flap board" />

## Overview

The Spotify plugin shows:

- The track or podcast episode playing on your account, on any device
- The time (`1:23 / 3:45`) and a progress bar as wide as your board
- The playlist, album, or artist it's playing from, and the device it's playing on
- Shuffle and repeat
- The next tracks in your queue
- The last track you played, when nothing is playing

It only reads your playback. It can't play, pause, or change anything in your account.

## Setup

Spotify limits any one app to a handful of accounts, so you sign in through a free Spotify app of your own. Creating it takes about five minutes, once, and the plugin's settings walk you through it. You need **Spotify Premium**: Spotify requires it for the owner of a developer app.

### 1. Create a Spotify App

1. In FiestaBoard, go to **Integrations**, toggle **Spotify** on, and click **Configure**. The **Account connection** section lists these steps and has the redirect URI to copy
2. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard), log in, and press **Create app**. Give it any name and description, for example `FiestaBoard`
3. Under **Redirect URIs**, paste the redirect URI copied from **Account connection** and press **Add**. Spotify compares it exactly, so copy the one your board shows
4. Under **Which API/SDKs are you planning to use?**, tick **Web API**
5. Agree to the terms and press **Save**
6. Open the app's **Settings** and copy the **Client ID**. You don't need the client secret

To sign in with a different Spotify account than the one that owns the app, add that account under the app's **Settings** > **User Management** first.

### 2. Sign In

1. Paste the **Client ID** into the **Account connection** section
2. Press **Sign in with Spotify**, then **Agree** on Spotify's page
3. The first time, `fiestaboard.app` shows your board's address on the way back. Check it and press **Continue to my board**

See [Connecting Accounts](/docs/features/connecting-accounts) for what happens during sign-in and where FiestaBoard keeps it.

## Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{spotify.headline}}` | `NOW PLAYING`, `PAUSED`, `LAST PLAYED`, `AD BREAK`, or `NOTHING PLAYING` | `NOW PLAYING` |
| `{{spotify.title}}` | Track or episode title | `NEON HARBOR` |
| `{{spotify.artist}}` | Artists, or the show for a podcast | `PAPER LANTERNS` |
| `{{spotify.album}}` | Album, or the publisher for a podcast | `MIDNIGHT FERRY` |
| `{{spotify.title_artist}}` | Title and artist on one line | `LOW TIDE - JUNE ARCADE` |
| `{{spotify.state_tile}}` | Green tile playing, yellow paused, red stopped | `{66}` |
| `{{spotify.time_line}}` | Position and length | `1:23 / 3:45` |
| `{{spotify.progress_bar}}` | Bar as wide as the board | `{66}{66}{66}---` |
| `{{spotify.remaining}}` | Time left | `-2:22` |
| `{{spotify.device_name}}` | Device playing | `KITCHEN SPEAKER` |
| `{{spotify.modes}}` | Shuffle and repeat | `SHUFFLE REPEAT ALL` |
| `{{spotify.context_name}}` | Playlist, album, artist, or podcast it's playing from | `SUNDAY COFFEE` |
| `{{spotify.next_line}}` | Next track and artist | `LOW TIDE - JUNE ARCADE` |
| `{{spotify.last_played_ago}}` | When the last track finished, if nothing is playing | `12M AGO` |

The plugin has more variables, including raw times, volume, and the next five queue entries. See the [setup guide](https://github.com/Fiestaboard/fiestaboard-plugin--spotify/blob/main/docs/SETUP.md#template-variables) for the full list.

A Flagship layout, center-aligned:

```text
{{spotify.state_tile}} {{spotify.headline}}
{{spotify.title}}
{{spotify.artist}}
{{spotify.album}}
{{spotify.time_line}}
{{spotify.progress_bar}}
```

The time and progress bar are as of the last check, every 15 seconds by default.

## Next Steps

- [Spotify plugin setup guide](https://github.com/Fiestaboard/fiestaboard-plugin--spotify/blob/main/docs/SETUP.md) -- Settings reference and troubleshooting
- [Connecting Accounts](/docs/features/connecting-accounts) -- How plugin sign-in works
- [Plugins Overview](/docs/plugins/overview) -- See all available plugins
