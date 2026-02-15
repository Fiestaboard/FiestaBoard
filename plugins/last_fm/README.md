# Last.fm Now Playing Plugin

Display what's currently playing on your Vestaboard via Last.fm scrobbling.

![Last.fm Now Playing Display](./docs/last-fm-display.png)

**→ [Setup Guide](./docs/SETUP.md)** - API key registration and configuration

## Overview

This plugin fetches the currently playing or most recently played track from a user's Last.fm profile. It works with any music source that scrobbles to Last.fm, including:

- Apple Music (via scrobbler apps)
- Spotify (native Last.fm integration)
- YouTube Music
- Tidal
- And many more

## How It Works

```
Music App → Scrobbler → Last.fm → FiestaBoard → Vestaboard
```

1. You listen to music on your preferred app
2. A scrobbler sends the track info to Last.fm
3. FiestaBoard polls the Last.fm API for your recent tracks
4. The `@attr.nowplaying` flag indicates if you're actively listening
5. Track info is displayed on your Vestaboard

## Configuration

### Settings

| Setting | Type | Required | Default | Description |
|---------|------|----------|---------|-------------|
| `username` | string | Yes | - | Your Last.fm username |
| `api_key` | string | Yes | - | Your Last.fm API key |
| `refresh_seconds` | integer | No | 30 | How often to check for updates (min: 10) |
| `show_album` | boolean | No | false | Include album name in output |
| `enabled` | boolean | No | false | Enable the plugin |

### Environment Variables

You can also configure via environment variables:

- `LASTFM_USERNAME` - Last.fm username
- `LASTFM_API_KEY` - Last.fm API key

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{last_fm.title}}` | Song title | "Bohemian Rhapsody" |
| `{{last_fm.artist}}` | Artist name | "Queen" |
| `{{last_fm.album}}` | Album name | "A Night at the Opera" |
| `{{last_fm.is_playing}}` | Currently playing? | true/false |
| `{{last_fm.status}}` | Status text | "NOW PLAYING" or "LAST PLAYED" |
| `{{last_fm.formatted}}` | Formatted string | "Bohemian Rhapsody by Queen" |
| `{{last_fm.artwork_url}}` | Album artwork URL | https://... |
| `{{last_fm.track_url}}` | Last.fm track URL | https://... |

## Example Templates

### Simple Now Playing

```
{{last_fm.status}}

{{last_fm.title}}
{{last_fm.artist}}
```

### With Album

```
NOW PLAYING
{{last_fm.title}}
by {{last_fm.artist}}
{{last_fm.album}}
```

## API Details

This plugin uses the Last.fm `user.getRecentTracks` endpoint:

- **Endpoint**: `http://ws.audioscrobbler.com/2.0/`
- **Method**: `user.getRecentTracks`
- **Rate Limits**: Last.fm recommends conservative usage; FiestaBoard's default refresh interval stays well within limits
- **Cost**: FREE

The `@attr.nowplaying` attribute in the response indicates if a track is currently being played, providing true real-time status.

## Troubleshooting

### "User not found" error

- Verify your username is correct (case-sensitive)
- Check your Last.fm profile is public

### "Invalid API key" error

- Regenerate your API key at https://www.last.fm/api/account/create
- Ensure no extra spaces in the key

### Tracks not showing as "now playing"

- Ensure your scrobbler is running and connected
- Some scrobblers have a delay before reporting
- Check that scrobbling is working on your Last.fm profile

## Development

### Running Tests

```bash
python scripts/run_plugin_tests.py --plugin=last_fm
```

### API Response Example

```json
{
  "recenttracks": {
    "track": [
      {
        "name": "Bohemian Rhapsody",
        "artist": {"#text": "Queen"},
        "album": {"#text": "A Night at the Opera"},
        "image": [{"#text": "https://..."}],
        "url": "https://www.last.fm/music/Queen/_/Bohemian+Rhapsody",
        "@attr": {"nowplaying": "true"}
      }
    ]
  }
}
```
