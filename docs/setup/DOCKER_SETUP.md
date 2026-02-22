# Docker Setup Guide

## Overview

This project uses a **two-container architecture**:

1. **API Service** (`fiestaboard-api`) - FastAPI REST API server
   - Port: `8000` (internal)
   - Controls the FiestaBoard display service
   - Provides REST endpoints for monitoring and control

2. **Web UI** (`fiestaboard-ui`) - Web server with Next.js interface
   - Port: `3000` (internal)
   - Provides a web interface for monitoring and control
   - Proxies API requests to the API service

## Quick Start (Pre-built Images — Recommended)

The fastest way to get running is to use the pre-built images from the **GitHub Container Registry**. No cloning or building required.

```bash
# Create a project folder
mkdir FiestaBoard && cd FiestaBoard

# Download the compose file and environment template
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/docker-compose.ghcr.yml
curl -O https://raw.githubusercontent.com/Fiestaboard/FiestaBoard/main/env.example

# Create and edit your config
cp env.example .env
# Edit .env with your board API key

# Start FiestaBoard
docker compose -f docker-compose.ghcr.yml up -d
```

### Access Services (Pre-built Images)

- **Web UI**: http://localhost:4420
- **API**: http://localhost:6969
- **API Docs**: http://localhost:6969/docs

## Building from Source (Alternative)

If you need to build from source (e.g., for development or customization):

### Build and Run

```bash
# Build and start both services
docker compose up -d --build

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Access Services (Built from Source)

- **Web UI**: http://localhost:8080
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (FastAPI auto-generated docs)

## Development

### Build Individual Services

```bash
# Build API service only
docker build -f Dockerfile.api -t fiestaboard-api .

# Build UI service only
docker build -f Dockerfile.ui -t fiestaboard-ui .
```

### Run Individual Services

```bash
# Run API service
docker run -d \
  --name fiestaboard-api \
  --env-file .env \
  -p 8000:8000 \
  fiestaboard-api

# Run UI service
docker run -d \
  --name fiestaboard-ui \
  -p 8080:80 \
  --link fiestaboard-api:fiestaboard-api \
  fiestaboard-ui
```

## API Endpoints

### Service Control
- `POST /refresh` - Manually refresh the display
- `POST /force-refresh` - Force refresh (ignores cache)
- `POST /dev-mode` - Toggle dev mode (preview vs live)

### Status & Info
- `GET /health` - Health check
- `GET /status` - Service status and configuration
- `GET /config` - Configuration summary

**Note**: The background display service starts automatically when the container starts. There's no need to manually start/stop it.

### Display Control
- `POST /send-message` - Send custom message to board
  ```json
  {
    "text": "Your message here"
  }
  ```

## Testing

### Test API Health
```bash
curl http://localhost:8000/health
```

### Test Service Status
```bash
curl http://localhost:8000/status
```

### Toggle Dev Mode
```bash
curl -X POST http://localhost:8000/dev-mode \
  -H "Content-Type: application/json" \
  -d '{"dev_mode": true}'
```

### Send Custom Message
```bash
curl -X POST http://localhost:8000/send-message \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from API!"}'
```

## Troubleshooting

### Services Won't Start

1. **Check logs:**
   ```bash
   docker-compose logs
   ```

2. **Verify .env file exists:**
   ```bash
   ls -la .env
   ```

3. **Check port conflicts:**
   ```bash
   # Check if ports are in use
   lsof -i :8000
   lsof -i :8080
   ```

### API Not Responding

1. **Check API container is running:**
   ```bash
   docker ps | grep fiestaboard-api
   ```

2. **Check API logs:**
   ```bash
   docker logs fiestaboard-api
   ```

3. **Test API directly:**
   ```bash
   curl http://localhost:8000/health
   ```

### Web UI Can't Connect to API

1. **Check API is accessible:**
   ```bash
   curl http://localhost:8000/health
   ```

2. **Check nginx proxy config:**
   ```bash
   docker exec fiestaboard-ui cat /etc/nginx/conf.d/default.conf
   ```

3. **Check UI logs:**
   ```bash
   docker logs fiestaboard-ui
   ```

## File Structure

```
.
├── Dockerfile.api          # API service Dockerfile
├── Dockerfile.ui          # UI service Dockerfile
├── docker-compose.yml     # Multi-service compose file
├── docker-compose.dev.yml # Development compose file
├── .dockerignore          # Docker ignore patterns
├── src/
│   ├── api_server.py     # FastAPI server
│   └── main.py           # Display service (used by API)
└── web/
    └── src/              # Next.js web application
```

## Environment Variables

Both services use the same `.env` file. Key variables:

- `BOARD_READ_WRITE_KEY` - Board API key (required for cloud mode)
- `WEATHER_API_KEY` - Weather API key (required)
- `WEATHER_PROVIDER` - "weatherapi" or "openweathermap"
- And more... (see `env.example`)

## Production Deployment

For production deployment, use `docker-compose.ghcr.yml` with pre-built images from the GitHub Container Registry. This is the recommended approach — no building required, and images are published with each release. Note that ARM images for Raspberry Pi are built on-demand; see the [Raspberry Pi Guide](../deployment/PI_BUILD_GUIDE.md) for details.


