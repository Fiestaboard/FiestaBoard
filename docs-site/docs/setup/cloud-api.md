---
sidebar_position: 5
description: "Configure FiestaBoard Cloud API for remote access to your split-flap display from anywhere over the internet."
keywords: [FiestaBoard cloud API, remote access, Vestaboard API, cloud setup, remote control, display management]
---

# Cloud API Setup

By default, FiestaBoard communicates with your board over the local network. If your board isn't on the same network, or you want remote access, you can use the Cloud API instead.

## When to Use Cloud API

- Your FiestaBoard server is **not on the same network** as your board
- You want to control your board **remotely**
- Local API is **unavailable** for your board model

## Setup

### Step 1: Get Your Cloud API Key

1. Go to [web.vestaboard.com](https://web.vestaboard.com)
2. Log in to your account
3. Navigate to the API section
4. Find your **Read/Write API** key
5. Copy the key

### Step 2: Configure FiestaBoard

Update your `.env` file:

```bash
# Set API mode to cloud
BOARD_API_MODE=cloud

# Your Read/Write API key
BOARD_READ_WRITE_KEY=your_cloud_api_key_here
```

### Step 3: Restart FiestaBoard

```bash
docker-compose down
docker-compose up -d
```

## Local vs. Cloud API Comparison

| Feature | Local API | Cloud API |
|---------|-----------|-----------|
| Network requirement | Same network | Internet only |
| Transition animations | ✅ Supported | ❌ Not available |
| Custom animation speed | ✅ Supported | ❌ Not available |
| Read current board state | ✅ Supported | ❌ Not available |
| Rate limiting | None | 1 message per 15 seconds |
| Latency | Low (~ms) | Higher (~100ms+) |

## Rate Limiting

The Cloud API has a rate limit of **1 message per 15 seconds**. If you're seeing rate limit errors, increase your refresh interval:

```bash
# In .env — set to at least 15 seconds for cloud mode
REFRESH_INTERVAL_SECONDS=30
```

## Troubleshooting

### 401 Unauthorized

- Double-check your `BOARD_READ_WRITE_KEY` in `.env`
- Make sure you're using the correct API key from web.vestaboard.com

### Rate Limit Errors

- Increase `REFRESH_INTERVAL_SECONDS` to 30 or higher
- Avoid manually refreshing while automatic updates are running

### Board Not Updating

1. Verify `BOARD_API_MODE=cloud` is set in `.env`
2. Check that your API key is valid
3. Check the logs: `docker-compose logs -f api`

## Next Steps

- [Docker Setup](/docs/setup/docker-setup) — Understanding the Docker architecture
- [Environment Variables](/docs/reference/environment-variables) — All configuration options
