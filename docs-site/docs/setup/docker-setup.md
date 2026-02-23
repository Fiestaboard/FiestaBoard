---
sidebar_position: 4
description: "Understand FiestaBoard's Docker architecture, container configuration, and docker-compose setup for production and development."
keywords: [FiestaBoard Docker, docker-compose, container setup, architecture, nginx, Flask, React]
---

# Docker Setup

FiestaBoard runs as a single Docker container. This page explains the architecture and how to configure it.

:::info Upgrading from V1?
V1 used two containers (`fiestaboard-api` on port 8000 and `fiestaboard-ui` on port 8080). V2 consolidates everything into one container on port 4420. See the [V2 Migration Guide](/docs/setup/v2-migration#docker-architecture-migration) for full upgrade instructions.
:::

## Architecture

FiestaBoard runs in a single unified container:

| Container | Service | Port | Description |
|-----------|---------|------|-------------|
| `fiestaboard` | Nginx + FastAPI + Next.js | 4420 | Web UI, REST API, display service, plugin system |

```
┌──────────────────────────────────────────────┐
│                   Browser                     │
│              http://localhost:4420             │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│            fiestaboard (Nginx)                │
│              Port 4420                        │
│   ┌────────────┐  ┌───────────────────────┐  │
│   │ Static UI  │  │  Proxy /api → FastAPI │  │
│   └────────────┘  └───────────────────────┘  │
│                                              │
│   ┌──────────────────────────────────────┐   │
│   │         FastAPI Backend              │   │
│   │   ┌────────────┐ ┌──────────────┐   │   │
│   │   │ REST API   │ │Display Service│   │   │
│   │   │            │ │Plugin System  │   │   │
│   │   └────────────┘ └──────────────┘   │   │
│   └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

## Docker Compose Files

| File | Use Case |
|------|----------|
| `docker-compose.yml` | Standard deployment |
| `docker-compose.dev.yml` | Development with hot reload |
| `docker-compose.prod.yml` | Production-optimized |
| `docker-compose.ghcr.yml` | Using pre-built images from GitHub Container Registry |

## Authenticating with GitHub Container Registry

FiestaBoard publishes pre-built Docker images to the [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) (ghcr.io). If you've never pulled an image from ghcr.io before, you'll need to authenticate Docker first.

### 1. Create a Personal Access Token (classic)

GitHub's Container Registry requires a **personal access token (classic)** for authentication. Fine-grained tokens are not supported for ghcr.io.

1. Go to [GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Give it a descriptive name (e.g., `ghcr-pull-fiestaboard`)
4. Select the **`read:packages`** scope (this is all you need to pull images)
5. Click **"Generate token"** and copy it — you won't be able to see it again

### 2. Log in to the Container Registry

Use Docker CLI to authenticate with ghcr.io. Replace `YOUR_GITHUB_USERNAME` and `YOUR_TOKEN` with your values:

```bash
# Save your token to an environment variable
export CR_PAT=YOUR_TOKEN

# Log in to ghcr.io
echo $CR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

You should see `Login Succeeded`. This is a one-time setup — Docker will remember your credentials for future pulls.

:::tip
Never commit your personal access token to version control. Use environment variables or a credential manager to store it securely.
:::

:::info Reference
See [GitHub's official guide to working with the Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) for more details.
:::

## Quick Start

```bash
# Standard deployment
docker-compose up -d --build

# Development with hot reload
docker-compose -f docker-compose.dev.yml up --build

# Using pre-built images (no build needed — requires ghcr.io authentication above)
docker-compose -f docker-compose.ghcr.yml up -d
```

## Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost:4420 | Main application interface |
| API | http://localhost:4420 | API access (via nginx proxy) |
| API Docs | http://localhost:4420/docs | Interactive FastAPI documentation |

## Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Service status and configuration |
| `/config` | GET | Current configuration |
| `/refresh` | POST | Refresh current display |
| `/force-refresh` | POST | Force refresh (bypasses cache) |
| `/dev-mode` | POST | Toggle development mode |
| `/send-message` | POST | Send a message to the board |
| `/plugins` | GET | List all plugins |
| `/plugins/{id}/data` | GET | Get plugin data |

See the [API Endpoints](/docs/reference/api-endpoints) reference for the complete list.

## Data Persistence

FiestaBoard stores its data in a `data/` directory that is mounted as a Docker volume:

```yaml
volumes:
  - ./data:/app/data
```

This includes:
- Page configurations
- Schedule entries
- Plugin settings
- Service configuration

:::tip
Back up the `data/` directory to preserve your configuration when updating FiestaBoard.
:::

## Updating FiestaBoard

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

## Environment Variables

All configuration is done through the `.env` file. See the [Environment Variables](/docs/reference/environment-variables) reference for the complete list.

## Next Steps

- [Cloud API Setup](/docs/setup/cloud-api) - Use cloud API instead of local
- [Raspberry Pi Deployment](/docs/deployment/raspberry-pi) - Deploy on a Pi
- [Environment Variables](/docs/reference/environment-variables) - All configuration options
