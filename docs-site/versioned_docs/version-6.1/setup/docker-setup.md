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

FiestaBoard stores all runtime state on disk so that configuration, pages, and schedules survive container restarts and image upgrades.

### What is persisted

Two host directories are bind-mounted into the container:

| Host path | Container path | Contents |
|-----------|---------------|----------|
| `./data/` | `/app/data/` | All application state (see table below) |
| `./external_plugins/` | `/app/external_plugins/` | Marketplace plugins installed via the Integrations page |

Files inside `data/`:

| File | Description |
|------|-------------|
| `config.json` | Board connection settings, API keys, plugin configuration |
| `settings.json` | Display preferences, transitions, schedule, MQTT, active page |
| `pages.json` | All board pages you have created |
| `schedules.json` | Time-based scheduling rules |
| `carousels.json` | Carousel display settings |
| `logs/` | Application, API, and nginx log files |
| `*.backup` | Pre-migration backups created automatically before schema upgrades |

This is configured in every Docker Compose file:

```yaml
volumes:
  - ./data:/app/data
  - ./external_plugins:/app/external_plugins
```

### Running with plain `docker run`

If you start the container directly without Docker Compose, pass the volume flags explicitly — otherwise data is lost when the container is removed:

```bash
docker run -d \
  --name fiestaboard \
  -p 4420:3000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/external_plugins:/app/external_plugins" \
  fiestaboard/fiestaboard:latest
```

:::warning Data loss without volume mounts
If you run `docker run` without `-v` flags, Docker creates an anonymous volume for `/app/data` (from the `VOLUME` directive in the image). The data still persists between restarts of the **same container**, but is permanently lost when you run `docker rm`. Always use explicit bind-mounts or named volumes for anything you want to keep.
:::

### Backup and restore

```bash
# Backup (from the directory containing your docker compose file)
tar -czf fiestaboard-backup-$(date +%Y%m%d).tar.gz data/ external_plugins/

# Restore
tar -xzf fiestaboard-backup-20240101.tar.gz
docker compose up -d
```

All configuration, pages, schedules, and installed plugins are captured in a single archive.

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
