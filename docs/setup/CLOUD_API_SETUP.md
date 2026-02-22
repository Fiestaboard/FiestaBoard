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

### 2. Configure Your .env File

Add these lines to your `.env` file:

```bash
# Switch to Cloud API mode
BOARD_API_MODE=cloud

# Add your Read/Write API key
BOARD_READ_WRITE_KEY=your_read_write_key_here

# You can leave these empty when using Cloud mode:
# BOARD_LOCAL_API_KEY=
# BOARD_HOST=
```

### 3. Test the Cloud API

Test your key by starting the service and checking the health endpoint:

```bash
# Start the service
docker-compose -f docker-compose.dev.yml up -d

# Check the health endpoint
curl http://localhost:4420/health

# Check the logs for any connection errors
docker-compose -f docker-compose.dev.yml logs -f fiestaboard
```

If successful, the API should connect to your board without errors.

### 4. Restart Your Docker Containers

```bash
docker-compose -f docker-compose.dev.yml restart
```

Or use the Cursor command:
```
/restart
```

## Switching Between Local and Cloud

You can easily switch between Local and Cloud API by changing `BOARD_API_MODE`:

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

## Troubleshooting

### "401 Unauthorized" Error

- Check that your `BOARD_READ_WRITE_KEY` is correct
- Make sure you copied the entire key (no spaces/newlines)
- Verify Read/Write API is enabled in the web dashboard

### "Rate Limited" Errors

The Cloud API limits you to 1 message per 15 seconds. If you see rate limit errors:
- Increase `REFRESH_INTERVAL_SECONDS` in your `.env` (recommended: 300 or higher)
- Disable dev mode when not testing
- Use Force Refresh sparingly

### Messages Not Appearing

- Cloud API doesn't support blank messages
- Rate limiting may drop messages if sent too frequently
- Check the logs viewer in the UI for errors

## Features Not Available in Cloud Mode

- **Transition animations** (column, reverse-column, edges-to-center, etc.)
- **Custom animation speeds**
- **Reading current board state** at initialization

All other features work identically in both modes!

