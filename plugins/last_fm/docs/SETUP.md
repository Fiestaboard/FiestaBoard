# Last.fm Now Playing Setup Guide

This guide will help you set up the Last.fm Now Playing plugin for FiestaBoard.

## Prerequisites

- A Last.fm account (free)
- A Last.fm API key (free)
- A scrobbler app for your music player

## Step 1: Create a Last.fm Account

If you don't already have a Last.fm account:

1. Go to [https://www.last.fm/join](https://www.last.fm/join)
2. Create a free account
3. Note your **username** (visible in your profile URL: `last.fm/user/YOUR_USERNAME`)

## Step 2: Get a Free API Key

1. Go to [https://www.last.fm/api/account/create](https://www.last.fm/api/account/create)
2. Fill in the application form:
   - **Application name**: FiestaBoard (or any name you prefer)
   - **Application description**: Personal music display
   - **Callback URL**: Leave blank
   - **Application homepage**: Leave blank or enter your FiestaBoard URL
3. Click "Submit"
4. Copy your **API Key** (you don't need the Shared Secret for this plugin)

## Step 3: Set Up a Scrobbler

A scrobbler is an app that sends your "now playing" info to Last.fm. Choose the setup for your music player:

### For Apple Music (macOS/iOS)

**Recommended: Scrobbles for Last.fm**

1. Download from the [Mac App Store](https://apps.apple.com/app/scrobbles-for-last-fm/id1344679160) or [iOS App Store](https://apps.apple.com/app/scrobbles-for-last-fm/id1344679160)
2. Open the app and sign in with your Last.fm account
3. Grant permission to access your music
4. The app runs in the background and scrobbles automatically

**Alternative: Marvis Pro (iOS)**
- Has built-in Last.fm scrobbling
- Premium app with additional features

### For Spotify

Spotify has built-in Last.fm integration:

1. Go to your Last.fm settings: [https://www.last.fm/settings/applications](https://www.last.fm/settings/applications)
2. Scroll down to "Spotify Scrobbling"
3. Click "Connect" and authorize Spotify
4. Scrobbling happens automatically when you play music on Spotify

### For Other Music Players

- **YouTube Music**: Use Web Scrobbler browser extension
- **Tidal**: Use the Tidal app's built-in scrobbling or a third-party scrobbler
- **Plex/Plexamp**: Enable scrobbling in Plex settings
- **Desktop (any player)**: Try [Web Scrobbler](https://web-scrobbler.com/) browser extension

## Step 4: Configure FiestaBoard

### Option A: Via Web UI

1. Open FiestaBoard web interface
2. Go to **Integrations**
3. Find **Last.fm Now Playing** and click to configure
4. Enter your **Last.fm username**
5. Enter your **API key**
6. Adjust refresh interval if desired (default: 30 seconds)
7. Enable the plugin

### Option B: Via Environment Variables

Add to your `.env` file or Docker environment:

```env
LASTFM_USERNAME=your_username
LASTFM_API_KEY=your_api_key_here
```

Then enable the plugin in the UI.

## Step 5: Verify It's Working

1. Play a song on your music player
2. Check your Last.fm profile to confirm scrobbling is working
3. Wait a few seconds for FiestaBoard to pick up the track
4. Your Vestaboard should display the currently playing song!

## Using in Templates

Once configured, you can use these variables in your templates:

```
{{last_fm.title}}       - Song title
{{last_fm.artist}}      - Artist name
{{last_fm.album}}       - Album name
{{last_fm.is_playing}}  - true if currently playing
{{last_fm.status}}      - "NOW PLAYING" or "LAST PLAYED"
{{last_fm.formatted}}   - "Song Title by Artist"
```

### Example Template

```
{{last_fm.status}}

{{last_fm.title}}
by {{last_fm.artist}}
```

## Troubleshooting

### Nothing appears on the board

1. **Check scrobbling is working**: Visit your Last.fm profile and verify recent tracks appear
2. **Verify credentials**: Double-check your username and API key
3. **Check plugin is enabled**: Go to Integrations and ensure the plugin is toggled on

### Shows "LAST PLAYED" instead of "NOW PLAYING"

This means the scrobbler isn't sending the "now playing" notification. Try:

1. Restart your scrobbler app
2. Check scrobbler settings for "send now playing" option
3. Some scrobblers have a delay - wait a few seconds after starting a song

### API key errors

1. Visit [https://www.last.fm/api/accounts](https://www.last.fm/api/accounts) to view your API keys
2. Create a new key if needed
3. Make sure there are no extra spaces when copying the key

### Rate limiting

The Last.fm API does not publish an exact rate limit, but recommends conservative usage (roughly 1 request per second as a safe guideline). FiestaBoard's default 30-second refresh interval stays well under this limit. If you've set a very low refresh interval, consider increasing it.

## Privacy Note

This plugin only reads your public scrobbling data. It does not:
- Access your Last.fm password
- Modify your Last.fm account
- Share your listening data with anyone

Your API key is stored locally in your FiestaBoard configuration.
