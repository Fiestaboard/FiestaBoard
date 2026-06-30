---
sidebar_position: 4
description: "Understand FiestaBoard's Docker architecture, container configuration, and docker compose setup for production and development."
keywords: [FiestaBoard Docker, docker compose, container setup, architecture, nginx, FastAPI, Next.js]
---

# Docker Setup

FiestaBoard runs as a single Docker container that bundles the web UI, API, and display service together. This page explains the architecture for users who want to understand what's running under the hood or customize their deployment.

:::tip Most users don't need this page
If you followed the [Quick Start](/docs/setup/quick-start) or [Beginner's Guide](/docs/setup/beginners-guide), everything is already configured correctly. This page is for advanced configuration and troubleshooting.
:::

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
| `docker-compose.hub.yml` | Using pre-built images from Docker Hub |

## Quick Start

```bash
# Standard deployment
docker compose up -d --build

# Development with hot reload
docker compose -f docker-compose.dev.yml up --build

# Using pre-built images (no build needed)
docker compose -f docker-compose.hub.yml up -d
```

## Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Web UI | http://localhost:4420 | Main application interface (from the same machine) |
| Web UI (network) | http://fiestaboard.local:4420 | Access from other devices via mDNS/Bonjour |
| API | http://localhost:4420/api | API access (via nginx proxy) |
| API Docs | http://localhost:4420/api/docs | Interactive FastAPI documentation |

:::tip Accessing from other devices
FiestaBoard registers itself on your local network using mDNS (also called Bonjour), so you can reach it at **http://fiestaboard.local:4420** from any device on the same network — phones, tablets, other computers, etc. This works on most home networks automatically.

If `.local` addresses don't resolve on your network, use the server's IP address directly (e.g. `http://192.168.1.50:4420`).

To change the advertised hostname, set `MDNS_HOSTNAME` in your `.env` file (default: `fiestaboard`, which becomes `fiestaboard.local`).
:::

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
docker compose down
docker compose up -d --build
```

## Environment Variables

All configuration is done through the `.env` file. See the [Environment Variables](/docs/reference/environment-variables) reference for the complete list.

## Next Steps

- [Cloud API Setup](/docs/setup/cloud-api) - Use cloud API instead of local
- [Raspberry Pi Deployment](/docs/deployment/raspberry-pi) - Deploy on a Pi
- [Environment Variables](/docs/reference/environment-variables) - All configuration options
