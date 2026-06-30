---
sidebar_position: 8
description: "Fix common FiestaBoard issues including connection errors, Docker problems, plugin failures, and display troubleshooting."
keywords: [FiestaBoard troubleshooting, debug, common issues, error fixes, split-flap display problems]
---

# Troubleshooting

Solutions for common FiestaBoard issues, organized by what you're seeing.

## Installation and Startup

### Docker is not running

**What you see:** `Cannot connect to the Docker daemon`

**Fix:** Make sure Docker Desktop is open and running.
- **Mac:** Look for the whale icon in the menu bar at the top of the screen
- **Windows:** Look for the whale icon in the system tray (bottom-right corner)
- **Linux:** Run `sudo systemctl start docker`

### Port already in use

**What you see:** `Bind for 0.0.0.0:4420 failed: port is already allocated`

**Fix:** Something else is already using port 4420. You have two options:

1. **Find and stop it:**
   ```bash
   # Mac/Linux
   lsof -i :4420

   # Windows
   netstat -ano | findstr 4420
   ```

2. **Use a different port** by editing the `ports` line in your `docker-compose.yml` (or `docker-compose.hub.yml`):
   ```yaml
   ports:
     - "9090:3000"   # Change 9090 to any free port
   ```
   Then access FiestaBoard at `http://localhost:9090` instead.

### Container won't start

**What you see:** Container exits immediately or shows errors.

**Fix:** Check the logs for the actual error:
```bash
docker compose logs fiestaboard
```

Common causes:
- Missing `.env` file (run `cp env.example .env` if you cloned the repo)
- Docker doesn't have enough memory allocated (check Docker Desktop settings)
- Corrupted build cache: try `docker compose down && docker compose up -d --build`

### Build takes a long time on Raspberry Pi

**What you see:** Build seems stuck during `npm install` or Python package installation.

**Fix:** This is normal. First builds on a Pi can take 10-20 minutes. To skip building entirely, use the pre-built image from Docker Hub:

```bash
docker compose -f docker-compose.hub.yml up -d
```

## Board Connection

### Board not updating

This is the most common issue. Work through this checklist:

1. **Is the display service running?** Open http://localhost:4420 and check if the dashboard shows **Running**. If it shows **Stopped** or **Disconnected**, check that your Docker container is running (`docker ps`).
2. **Is your API key correct?** Go to **Settings** in the web UI and verify your board API key.
3. **Is the API mode correct?** Make sure you're using the right mode (Local API or Cloud API) for the key you entered.
4. **For Local API:** Is your board on the same WiFi network as the computer running FiestaBoard?
5. **Check the logs** for specific error messages:
   ```bash
   docker compose logs -f fiestaboard
   ```

### 401 Unauthorized from board API

**What you see:** "401 Unauthorized" or "Invalid API key" errors in the logs.

**Fix:**
- Double-check your API key has no extra spaces or line breaks
- For Cloud API: verify the key is still active at [web.vestaboard.com](https://web.vestaboard.com)
- Try regenerating the key and entering the new one in Settings

### Board updates are slow or laggy

**Possible causes:**
- **Cloud API mode** has a 15-second rate limit between messages. This is normal.
- **High refresh interval** - Check Settings to see how often FiestaBoard checks for updates
- **Network issues** - For Local API, check your WiFi connection

**Fix:** If using Cloud API, set the refresh interval to at least 30 seconds in Settings. For Local API, try restarting FiestaBoard:
```bash
docker compose restart
```

## Web UI Issues

### Web UI won't load at http://localhost:4420

**Checklist:**
1. Wait 30-60 seconds after starting - the server needs time to initialize
2. Check if the container is running: `docker ps`
3. Try the health endpoint: `http://localhost:4420/api/health`
4. Check the logs: `docker compose logs -f fiestaboard`

:::tip Accessing from another device?
`localhost` only works on the machine running FiestaBoard. From other devices on the same network, use **http://fiestaboard.local:4420** (mDNS/Bonjour) or your server's IP address (e.g. `http://192.168.1.50:4420`).
:::

### Changes not saving

**Possible causes:**
- The `data/` volume mount isn't working. Check your `docker-compose.yml` has:
  ```yaml
  volumes:
    - ./data:/app/data
  ```
- File permissions on the `data/` directory. Try: `chmod -R 755 data/`
- Container isn't running. Check with `docker ps`

### Page previews look wrong

**Fix:** The preview in the editor should match your board exactly. If it doesn't:
- Make sure you're editing a page for the right device type (Flagship vs Note)
- Check that template variables resolve correctly by looking at the live preview
- Refresh the page in your browser

## Plugin Issues

### Weather shows no data

1. Go to **Integrations** and check that the Weather plugin is enabled
2. Click on the Weather plugin to check your API key is entered
3. Verify you've entered a valid location
4. Check if your API key is still active at [weatherapi.com](https://www.weatherapi.com/) or [openweathermap.org](https://openweathermap.org/)

### Traffic plugin returns errors

Common causes:
- Google Routes API is not enabled in Google Cloud Console
- Billing is not set up (required even for the free tier)
- Invalid address format - try using coordinates instead of street addresses

See the [Traffic Plugin](/docs/plugins/traffic) guide for detailed setup.

### Home Assistant connection refused

1. Is the Home Assistant URL correct and reachable from the computer running FiestaBoard?
2. Is your long-lived access token still valid?
3. If FiestaBoard runs in Docker and Home Assistant runs on the same machine, use your machine's local IP address (e.g., `192.168.1.100:8123`) instead of `localhost`

### A plugin shows stale or outdated data

Plugins refresh their data at the interval set in Settings (see the default in [Environment Variables](/docs/reference/environment-variables)). If data seems stuck:
1. Try a **Force Refresh** from the API: `curl -X POST http://localhost:4420/api/force-refresh`
2. Check plugin logs for errors: `docker compose logs -f fiestaboard | grep plugin_name`
3. Verify the external API hasn't hit rate limits

## Getting More Help

### Check the logs

Logs are the best way to diagnose issues:

```bash
# See all recent logs
docker compose logs --tail=100 fiestaboard

# Follow logs in real time
docker compose logs -f fiestaboard
```

### Interactive API documentation

Visit **http://localhost:4420/api/docs** for the Swagger UI where you can test API endpoints directly and check service status.

### Community support

- **[Discord](https://discord.gg/JvN8y6ahaf)** - Ask questions and get help from other FiestaBoard users
- **[GitHub Issues](https://github.com/Fiestaboard/FiestaBoard/issues)** - Report bugs or request features

When reporting an issue, include:
- What you expected vs. what happened
- Steps to reproduce the problem
- Relevant log output (`docker compose logs fiestaboard`)
- Your environment (OS, Docker version, board model)
