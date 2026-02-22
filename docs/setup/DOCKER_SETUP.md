# Docker Setup Guide

## Overview

This project uses a **single-container architecture** for simplicity and portability:

- **FiestaBoard** (`fiestaboard`) - Unified container running API + Web UI
  - Port: `3000` (single port for everything)
  - Nginx reverse proxy routes requests to the appropriate backend
  - API (FastAPI) runs internally on port 8000
  - Web UI (Next.js) runs internally on port 3001

## Quick Start

### Build and Run

```bash
# Build and start the service
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Access

- **Web UI**: http://localhost:3000
- **API Docs**: http://localhost:3000/docs (FastAPI auto-generated docs)

## Development

### Build the Image

```bash
# Build the unified image
docker build -t fiestaboard .
```

### Run the Container

```bash
# Run FiestaBoard
docker run -d \
  --name fiestaboard \
  --env-file .env \
  -p 3000:3000 \
  -v ./data:/app/data \
  fiestaboard
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

### Test Health
```bash
curl http://localhost:3000/health
```

### Test Service Status
```bash
curl http://localhost:3000/status
```

### Toggle Dev Mode
```bash
curl -X POST http://localhost:3000/dev-mode \
  -H "Content-Type: application/json" \
  -d '{"dev_mode": true}'
```

### Send Custom Message
```bash
curl -X POST http://localhost:3000/send-message \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from API!"}'
```

## Troubleshooting

### Service Won't Start

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
   # Check if port is in use
   lsof -i :3000
   ```

### API Not Responding

1. **Check container is running:**
   ```bash
   docker ps | grep fiestaboard
   ```

2. **Check logs:**
   ```bash
   docker logs fiestaboard
   ```

3. **Test API directly:**
   ```bash
   curl http://localhost:3000/health
   ```

### Web UI Can't Connect to API

1. **Check the service is running:**
   ```bash
   curl http://localhost:3000/health
   ```

2. **Check container logs:**
   ```bash
   docker logs fiestaboard
   ```

## File Structure

```
.
├── Dockerfile              # Unified Dockerfile (API + Web UI)
├── Dockerfile.api          # API-only Dockerfile (for development)
├── Dockerfile.ui           # UI-only Dockerfile (for development)
├── docker-compose.yml      # Production compose file
├── docker-compose.dev.yml  # Development compose file
├── .dockerignore           # Docker ignore patterns
├── nginx.conf              # Nginx reverse proxy config
├── src/
│   ├── api_server.py       # FastAPI server
│   └── main.py             # Display service (used by API)
└── web/
    └── src/                # Next.js web application
```

## Environment Variables

The service uses the `.env` file. Key variables:

- `BOARD_READ_WRITE_KEY` - Board API key (required for cloud mode)
- `WEATHER_API_KEY` - Weather API key (required)
- `WEATHER_PROVIDER` - "weatherapi" or "openweathermap"
- And more... (see `env.example`)

## Production Deployment

For production deployment, use the standard `docker-compose.yml` file with proper environment variables configured.


