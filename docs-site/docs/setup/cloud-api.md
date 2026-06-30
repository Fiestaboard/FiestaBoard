---
sidebar_position: 5
description: "Configure FiestaBoard Cloud API for remote access to your split-flap display from anywhere over the internet."
keywords: [FiestaBoard cloud API, remote access, Vestaboard API, cloud setup, remote control, display management]
---

# Cloud API Setup

By default, FiestaBoard communicates with your board over the local network (Local API). If your board isn't on the same network as your server, or you want remote access, you can use the Cloud API instead.

## When to Use Cloud API

- Your FiestaBoard server is **not on the same network** as your board
- You want to control your board **remotely** (e.g., from a cloud server)
- Local API is **unavailable** for your board model

## Local vs. Cloud API Comparison

| Feature | Local API | Cloud API |
|---------|-----------|-----------|
| Network requirement | Same network | Internet only |
| Transition animations | Supported | Not available |
| Custom animation speed | Supported | Not available |
| Read current board state | Supported | Not available |
| Rate limiting | None | 1 message per 15 seconds |
| Latency | Low (~ms) | Higher (~100ms+) |

## Setup

### Step 1: Get Your Cloud API Key

1. Go to [your Vestaboard account](https://web.vestaboard.com)
2. Log in to your account
3. Navigate to the API section
4. Enable the **Read/Write API**
5. Copy the key

### Step 2: Configure FiestaBoard

**Via the Web UI (Recommended):**

1. Open **http://localhost:4420**
2. Go to **Settings**
3. Change the API mode to **Cloud API**
4. Paste your Read/Write API key (settings save automatically)

**Via `.env` (alternative):**

```bash
BOARD_API_MODE=cloud
BOARD_READ_WRITE_KEY=your_cloud_api_key_here
```

### Step 3: Restart FiestaBoard

```bash
docker compose restart
```

<ThemedScreenshot src="/img/guides/settings-board-config.png" alt="Settings page with board API key and IP address inputs" />

## Rate Limiting

The Cloud API has a rate limit of **1 message per 15 seconds**. If you see rate limit errors, increase your refresh interval:

- **Via Web UI:** Go to Settings and increase the refresh interval to 30 seconds or higher
- **Via `.env`:** Set `REFRESH_INTERVAL_SECONDS=30` (or higher)

## Troubleshooting

### 401 Unauthorized

- Double-check your Read/Write API key in Settings
- Make sure the key is still active in [your Vestaboard account](https://web.vestaboard.com)
- Verify there are no extra spaces or line breaks in the key

### Rate Limit Errors

- Increase the refresh interval to 30 seconds or higher
- Avoid manually refreshing while automatic updates are running

### Board Not Updating

1. Verify **Cloud** is selected as the API mode in Settings
2. Check that your API key is valid
3. Check the logs: `docker compose logs -f fiestaboard`

## Next Steps

- **[Docker Setup](/docs/setup/docker-setup)** - Understanding the Docker architecture
- **[Environment Variables](/docs/reference/environment-variables)** - All configuration options
