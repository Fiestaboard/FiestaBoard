# Docker Setup Guide

## Overview

This project uses a **single-container architecture** for simplicity and portability:

- **FiestaBoard** (`fiestaboard`) - Unified container running API + Web UI
  - Port: `4420` (single port for everything)
  - Nginx reverse proxy routes requests to the appropriate backend
  - API (FastAPI) runs internally on port 8000
  - Web UI (Next.js) runs internally on port 3001

## Port Configuration

FiestaBoard defaults to port **4420** on the host. Inside the container, an nginx reverse proxy on port 3000 handles routing to the backend services:

```
Host (port 4420) ──> Nginx (port 3000 inside container)
                       ├── /api/*  ──> FastAPI (port 8000)
                       └── /*      ──> Next.js (port 3001)
```

The internal ports (3000, 8000, 3001) are never exposed to the host directly.

### Using a Custom Port

To change the host port, edit the left side of the `ports` mapping in your docker-compose file:

```yaml
ports:
  - "8080:3000"   # access FiestaBoard at localhost:8080
```

Or with `docker run`:

```bash
docker run -d -p 8080:3000 fiestaboard
```

The container-side port (right of the colon) must stay `3000` -- that's where nginx listens inside the container. Only the host-side port (left of the colon) changes.

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

- **Web UI**: http://localhost:4420
- **API Docs**: http://localhost:4420/docs (FastAPI auto-generated docs)

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
  -p 4420:3000 \
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
curl http://localhost:4420/health
```

### Test Service Status
```bash
curl http://localhost:4420/status
```

### Toggle Dev Mode
```bash
curl -X POST http://localhost:4420/dev-mode \
  -H "Content-Type: application/json" \
  -d '{"dev_mode": true}'
```

### Send Custom Message
```bash
curl -X POST http://localhost:4420/send-message \
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
   lsof -i :4420
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
   curl http://localhost:4420/health
   ```

### Web UI Can't Connect to API

1. **Check the service is running:**
   ```bash
   curl http://localhost:4420/health
   ```

2. **Check container logs:**
   ```bash
   docker logs fiestaboard
   ```

## File Structure

```
.
├── Dockerfile              # Unified Dockerfile (API + Web UI + nginx)
├── docker-compose.yml      # Production compose file (single container)
├── docker-compose.dev.yml  # Development compose file (single container with hot-reload)
├── .dockerignore           # Docker ignore patterns
├── nginx.conf              # Nginx reverse proxy config
├── src/
│   ├── api_server.py       # FastAPI server
│   └── main.py             # Display service (used by API)
└── web/
    └── src/                # Next.js web application
```

## Environment Variables

The service uses the `.env` file created from `env.example`. No manual editing is required -- the install wizard and web UI handle all configuration, including board connection, plugins, and API keys.

For advanced users who want to override settings via `.env`, here are the key variables:

- `BOARD_API_MODE` - `local` (default) or `cloud`
- `BOARD_LOCAL_API_KEY` / `BOARD_HOST` - Board connection (local mode)
- `BOARD_READ_WRITE_KEY` - Board API key (cloud mode)
- `TIMEZONE` - Your local timezone (e.g., `America/Los_Angeles`)

See the [Environment Variables Reference](https://fiestaboard.app/docs/reference/environment-variables) for the full list of options.

## Authenticating with GitHub Container Registry

FiestaBoard publishes pre-built Docker images to the [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) (ghcr.io). If you've never pulled an image from ghcr.io before, you may need to authenticate Docker first.

### Step 1: Create a Personal Access Token (classic)

GitHub's Container Registry requires a **personal access token (classic)** for authentication. Fine-grained tokens are not supported for ghcr.io.

1. Go to [GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Give it a descriptive name (e.g., `ghcr-pull-fiestaboard`)
4. Select the **`read:packages`** scope (this is all you need to pull images)
5. Click **"Generate token"** and copy it — you won't be able to see it again

### Step 2: Log in to the Container Registry

Use Docker CLI to authenticate with ghcr.io. Replace `YOUR_GITHUB_USERNAME` and `YOUR_TOKEN` with your values:

```bash
# Save your token to an environment variable
export CR_PAT=YOUR_TOKEN

# Log in to ghcr.io
echo $CR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

You should see `Login Succeeded`. This is a one-time setup — Docker will remember your credentials for future pulls.

### Step 3: Pull and Run FiestaBoard

Once authenticated, you can use the pre-built images:

```bash
docker-compose -f docker-compose.ghcr.yml up -d
```

> **Reference:** [GitHub's official guide to working with the Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

## Production Deployment

For production deployment, use the pre-built image from the GitHub Container Registry (`ghcr.io/fiestaboard/fiestaboard:latest`) with proper environment variables configured. Images are published with each release. Note that ARM images for Raspberry Pi are built on-demand; see the [Raspberry Pi Guide](../deployment/PI_BUILD_GUIDE.md) for details.


