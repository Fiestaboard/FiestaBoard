# Board Cloud API Setup

This guide explains how to use the Board Cloud (Read/Write) API as an alternative to the Local API.

## When to Use Cloud API

Use Cloud API when:
- **Local API is not enabled** on your board
- You want to control your board **from outside your local network**
- You're waiting for your Local API key to be generated
- Local API transitions aren't needed

**Trade-offs:**
- Works from anywhere with internet
- Simple setup (just one API key)
- No transition animations
- Slightly slower than Local API
- Rate limited (1 message per 15 seconds)

## Setup Steps

### 1. Get Your Read/Write API Key

1. Go to https://web.vestaboard.com
2. Sign in with your board account
3. Navigate to **Settings** → **API** (or **Developer** section)
4. Enable the **Read/Write API**
5. Copy your Read/Write API key

### 2. Configure via the Web UI (Recommended)

1. Open http://localhost:4420
2. Go to **Settings**
3. Set the API mode to **Cloud API**
4. Paste your Read/Write API key (settings save automatically)

### 3. Test the Connection

After saving, check the service status on the main dashboard. If the connection is successful, you should see a healthy status. If not, check the logs:

```bash
docker-compose logs -f fiestaboard
```

### 4. Restart the Service

If needed, restart the Docker container to apply changes:

```bash
docker-compose restart
```

## Switching Between Local and Cloud

You can switch API modes at any time through the web UI's Settings page, or by updating your `.env` file:

**Local API** (faster, with transitions):
```bash
BOARD_API_MODE=local
BOARD_LOCAL_API_KEY=your_local_key
BOARD_HOST=192.168.0.11
```

**Cloud API** (remote access):
```bash
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=your_read_write_key
```

After changing `.env` values, restart the container:
```bash
docker-compose restart
```

## Troubleshooting

### "401 Unauthorized" Error

- Check that your `BOARD_READ_WRITE_KEY` is correct
- Make sure you copied the entire key (no spaces/newlines)
- Verify Read/Write API is enabled in the web dashboard

### "Rate Limited" Errors

The Cloud API limits you to 1 message per 15 seconds. If you see rate limit errors:
- Increase the refresh interval to 30 seconds or higher (Settings page or `REFRESH_INTERVAL_SECONDS` in `.env`)
- Disable dev mode when not testing
- Use Force Refresh sparingly

### Messages Not Appearing

- Cloud API doesn't support blank messages
- Rate limiting may drop messages if sent too frequently
- Check the logs for errors

## Features Not Available in Cloud Mode

- **Transition animations** (column, reverse-column, edges-to-center, etc.)
- **Custom animation speeds**
- **Reading current board state** at initialization

All other features work identically in both modes!
