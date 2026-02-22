---
sidebar_position: 4
description: "Understand FiestaBoard's Docker architecture, container configuration, and docker-compose setup for production and development."
keywords: [FiestaBoard Docker, docker-compose, container setup, architecture, nginx, Flask, React]
---

# Docker Setup

FiestaBoard runs as a multi-container Docker application. This page explains the architecture and how to configure it.

## Architecture

FiestaBoard consists of two Docker containers:

| Container | Service | Port | Description |
|-----------|---------|------|-------------|
| `fiestaboard-api` | FastAPI Backend | 8000 | REST API, display service, plugin system |
| `fiestaboard-ui` | Nginx + Next.js | 8080 | Web UI, serves static assets, proxies API |

```
┌──────────────────────────────────────────────┐
│                   Browser                     │
│              http://localhost:8080             │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│           fiestaboard-ui (Nginx)              │
│              Port 8080                        │
│   ┌────────────┐  ┌───────────────────────┐  │
│   │ Static UI  │  │  Proxy /api → :8000   │  │
│   └────────────┘  └───────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│          fiestaboard-api (FastAPI)             │
│              Port 8000                        │
│   ┌────────────┐  ┌───────────────────────┐  │
│   │ REST API   │  │  Display Service      │  │
│   │            │  │  Plugin System         │  │
│   └────────────┘  └───────────────────────┘  │
└──────────────────────────────────────────────┘
```

## Docker Compose Files

| File | Use Case |
|------|----------|
| `docker-compose.yml` | Standard deployment |
| `docker-compose.dev.yml` | Development with hot reload |
| `docker-compose.prod.yml` | Production-optimized |
| `docker-compose.ghcr.yml` | Using pre-built images from GitHub Container Registry |

## Quick Start

```bash
# Standard deployment
docker-compose up -d --build

# Development with hot reload
docker-compose -f docker-compose.dev.yml up --build

# Using pre-built images (no build needed)
docker-compose -f docker-compose.ghcr.yml up -d
```

## Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost:8080 | Main application interface |
| API | http://localhost:8000 | Direct API access |
| API Docs | http://localhost:8000/docs | Interactive FastAPI documentation |

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
