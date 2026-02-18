# Spotify Now Playing Plugin

Display what's currently playing on Spotify on your Vestaboard via the Spotify Web API.

**→ [Setup Guide](./docs/SETUP.md)** - Spotify app registration and configuration

## Overview

This plugin fetches the currently playing track directly from a user's Spotify account using the Spotify Web API. Unlike the Last.fm plugin (which works through scrobbling), this plugin connects directly to Spotify for real-time "now playing" status.

## How It Works

```
Spotify → Spotify Web API → FiestaBoard → Vestaboard
```

1. You listen to music on Spotify (any device)
2. FiestaBoard polls the Spotify Web API for your currently playing track
3. Track info (title, artist, album, artwork) is displayed on your Vestaboard
4. Playback state (playing/paused) is reflected in real-time

## Configuration

### Settings

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `client_id` | string | Yes | - | Spotify application Client ID |
| `client_secret` | string | Yes | - | Spotify application Client Secret |
| `refresh_token` | string | Yes | - | OAuth refresh token (see Setup Guide) |
| `refresh_seconds` | integer | No | 30 | How often to check for updates (min: 10) |
| `show_album` | boolean | No | false | Include album name in output |
| `enabled` | boolean | No | false | Enable the plugin |

### Environment Variables

You can also configure via environment variables:

- `SPOTIFY_CLIENT_ID` - Spotify application Client ID
- `SPOTIFY_CLIENT_SECRET` - Spotify application Client Secret
- `SPOTIFY_REFRESH_TOKEN` - OAuth refresh token

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{spotify.title}}` | Song title | "Halo" |
| `{{spotify.artist}}` | Artist name | "Beyonce" |
| `{{spotify.album}}` | Album name | "I Am... Sasha Fierce" |
| `{{spotify.is_playing}}` | Currently playing? | true/false |
| `{{spotify.status}}` | Status text | "NOW PLAYING" or "PAUSED" |
| `{{spotify.formatted}}` | Formatted string | "Halo by Beyonce" |
| `{{spotify.artwork_url}}` | Album artwork URL | https://... |
| `{{spotify.track_url}}` | Spotify track URL | https://open.spotify.com/... |

## Example Templates

### Simple Now Playing

```
{{spotify.status}}

{{spotify.title}}
{{spotify.artist}}
```

### With Album

```
SPOTIFY
{{spotify.album}}

{{spotify.title}}
{{spotify.artist}}
```

## API Details

This plugin uses the Spotify Web API:

- **Token endpoint**: `https://accounts.spotify.com/api/token`
- **Now Playing endpoint**: `https://api.spotify.com/v1/me/player/currently-playing`
- **Auth**: OAuth 2.0 with refresh token flow
- **Required scope**: `user-read-currently-playing`
- **Rate Limits**: Varies; the default 30-second refresh interval stays well under limits
- **Cost**: FREE (requires a Spotify account)

## Troubleshooting

### "Authentication failed" error

- Verify your Client ID and Client Secret are correct
- Re-generate your refresh token (see Setup Guide)
- Ensure your Spotify app is still active in the Developer Dashboard

### "Access forbidden" error

- Check that `user-read-currently-playing` scope was granted during authorization
- Re-authorize and generate a new refresh token

### Shows "PAUSED" instead of "NOW PLAYING"

- Spotify playback is paused — this is expected behavior
- Resume playback on your Spotify app

### Nothing appears on the board

- Make sure Spotify is actively playing on at least one device
- Check that the plugin is enabled in FiestaBoard settings
- Verify credentials are entered correctly

## Development

### Running Tests

```bash
python scripts/run_plugin_tests.py --plugin=spotify
```

### API Response Example

```json
{
  "is_playing": true,
  "currently_playing_type": "track",
  "item": {
    "name": "Halo",
    "artists": [{"name": "Beyonce"}],
    "album": {
      "name": "I Am... Sasha Fierce",
      "images": [{"url": "https://i.scdn.co/image/..."}]
    },
    "external_urls": {
      "spotify": "https://open.spotify.com/track/..."
    }
  }
}
```
