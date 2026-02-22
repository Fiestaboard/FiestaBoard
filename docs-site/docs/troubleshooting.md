---
sidebar_position: 8
description: "Fix common FiestaBoard issues including connection errors, Docker problems, plugin failures, and display troubleshooting."
keywords: [FiestaBoard troubleshooting, debug, common issues, error fixes, split-flap display problems]
---

# Troubleshooting

Solutions for common FiestaBoard issues.

## Installation Issues

### Docker is not running

**Symptom**: `Cannot connect to the Docker daemon`

**Solution**:
- Make sure Docker Desktop is open and running
- Look for the Docker whale icon in your system tray (Windows/Mac) or menu bar
- On Linux, check: `sudo systemctl status docker`

### Port already in use

**Symptom**: `Bind for 0.0.0.0:8080 failed: port is already allocated`

**Solution**:
- Another application is using port 8080 or 8000
- Stop the other application, or change the port in `docker-compose.yml`
- Find what's using the port: `lsof -i :8080` (Mac/Linux) or `netstat -ano | findstr 8080` (Windows)

### Build fails on Raspberry Pi

**Symptom**: Build errors related to missing compilers

**Solution**:
Ensure build tools are installed on your Pi:
```bash
sudo apt-get install gcc g++ make
```

## Board Connection Issues

### Board not updating

**Checklist**:
1. Is the display service started? (Click Start in the Web UI)
2. Is your `BOARD_READ_WRITE_KEY` correct in `.env`?
3. Is the board on the same network? (for local API mode)
4. Check the logs: `docker-compose logs -f fiestaboard`

### 401 Unauthorized from board API

**Solution**:
- Verify your API key at [web.vestaboard.com](https://web.vestaboard.com)
- Regenerate the key if needed
- Make sure it's correctly set in `.env` with no extra spaces

### Board updates are slow

**Possible causes**:
- Cloud API mode has a 15-second rate limit. Increase `REFRESH_INTERVAL_SECONDS`
- Network latency. Check your connection to the board
- Too many plugins refreshing. Reduce enabled plugins or increase refresh interval

## Plugin Issues

### Weather shows no data

**Checklist**:
1. Is `WEATHER_API_KEY` set in `.env`?
2. Is `WEATHER_PROVIDER` set correctly? (`weatherapi` or `openweathermap`)
3. Is `WEATHER_LOCATION` a valid location string?
4. Is the Weather plugin enabled in the Integrations page?

### Traffic plugin returns errors

**Common causes**:
- Google Routes API not enabled in Cloud Console
- Billing not set up (required even for free tier)
- Invalid address format - try using coordinates instead

See the [Traffic Plugin](/docs/plugins/traffic) guide for detailed setup.

### Home Assistant connection refused

**Checklist**:
1. Is the `HOME_ASSISTANT_URL` correct and reachable?
2. Is your long-lived access token valid?
3. Can FiestaBoard's Docker container reach your HA instance?

If using Docker, ensure both are on the same Docker network or use the host's IP address.

## Web UI Issues

### Web UI won't load

**Checklist**:
1. Is the container running? `docker-compose ps`
2. Try accessing the health endpoint: `http://localhost:4420/api/health`
3. Check container logs: `docker-compose logs -f fiestaboard`

### Changes not saving

**Possible causes**:
- The `data/` volume mount is not working - check `docker-compose.yml`
- File permissions on the `data/` directory
- Container is not running - check with `docker-compose ps`

## Getting More Help

### Check the Logs

```bash
# All logs
docker-compose logs -f

# FiestaBoard container only
docker-compose logs -f fiestaboard
```

### Interactive API Documentation

Visit `http://localhost:4420/docs` for the Swagger UI where you can test API endpoints directly.

### Open an Issue

If you can't resolve the problem:
1. Go to [GitHub Issues](https://github.com/Fiestaboard/FiestaBoard/issues)
2. Search for existing issues
3. If not found, open a new issue with:
   - Steps to reproduce
   - Expected vs. actual behavior
   - Log output
   - Your environment (OS, Docker version, Pi model, etc.)

## Next Steps

- [Quick Start](/docs/setup/quick-start) - Setup guide
- [Docker Setup](/docs/setup/docker-setup) - Docker architecture
- [API Endpoints](/docs/reference/api-endpoints) - API reference
