# Docker Setup Guide

## Overview

This guide covers the **production** Docker setup. For local development, see [LOCAL_DEVELOPMENT.md](./LOCAL_DEVELOPMENT.md).

This project uses a **two-container architecture**:

1. **API Service** (`fiestaboard-api`) - FastAPI REST API server
   - Port: `8000` (internal), mapped to `8000` in production
   - Controls the FiestaBoard display service
   - Provides REST endpoints for monitoring and control

2. **Web UI** (`fiestaboard-ui`) - Next.js web application
   - Production: served via Nginx on port `8080` (`docker-compose.yml`)
   - Development: Next.js dev server on port `3000` (`docker-compose.dev.yml`)
   - Provides a web interface for monitoring and control
   - Proxies API requests to the API service

## Quick Start

### Build and Run

```bash
# Build and start both services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Access Services

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
- `BOARD_LOCAL_API_KEY` - Board API key (required for local mode)
- `WEATHER_API_KEY` - Weather API key (required)
- `WEATHER_PROVIDER` - "weatherapi" or "openweathermap"
- And more... (see `env.example`)

## Production Deployment

For production deployment, use the standard `docker-compose.yml` file with proper environment variables configured.


