# Local Development Guide

This guide explains how to develop the FiestaBoard Display Service locally using Docker.

> **Using Cursor IDE?** FiestaBoard includes Cursor commands that automate many of these steps. See the [Cursor IDE shortcuts](#cursor-ide-shortcuts) section below or the [CONTRIBUTING guide](../../CONTRIBUTING.md#cursor-ide-optional) for details.

## Prerequisites

- Docker and Docker Compose installed
- A `.env` file with your API keys (copy from `env.example`)
- A `config.json` file (copy from `config.example.json` if it doesn't exist)

## Initial Setup

```bash
# 1. Clone the repository
git clone https://github.com/Fiestaboard/FiestaBoard.git
cd FiestaBoard

# 2. Create environment and config files
cp env.example .env
cp config.example.json config.json

# 3. Edit .env and add your API keys
#    At minimum you need: BOARD_READ_WRITE_KEY and WEATHER_API_KEY

# 4. Create data directory (if it doesn't exist)
mkdir -p data
```

## Development Workflow

### Starting Development Environment

```bash
# Start all services in development mode
docker-compose -f docker-compose.dev.yml up

# Or run in background
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f
```

**Access (development mode):**
- Web UI: http://localhost:3000
- API: http://localhost:6969
- API Docs: http://localhost:6969/docs
- Storybook: http://localhost:6006

> **Note:** Production mode uses different ports — see [DOCKER_SETUP.md](./DOCKER_SETUP.md) for production details.

### Hot Reload

The development Docker Compose mounts source code as volumes, so code changes are reflected automatically:

- **Python API**: Changes to `src/` trigger auto-reload
- **Next.js Web UI**: Changes to `web/` trigger fast refresh

### Stopping Services

```bash
docker-compose -f docker-compose.dev.yml down
```

### Rebuilding After Dependency Changes

```bash
# If you update requirements.txt or package.json
docker-compose -f docker-compose.dev.yml up --build

# For a full clean rebuild (no cache)
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml build --no-cache
docker-compose -f docker-compose.dev.yml up -d
```

## Testing

All tests run inside Docker containers. Make sure the dev containers are running first.

```bash
# Run API/platform tests
docker-compose -f docker-compose.dev.yml exec fiestaboard-api pytest

# Run web UI tests (one-shot)
docker-compose -f docker-compose.dev.yml exec fiestaboard-ui-dev npm run test:run

# Run plugin validation
docker-compose -f docker-compose.dev.yml exec fiestaboard-api python scripts/validate_plugins.py --verbose

# Run a specific plugin's tests
docker-compose -f docker-compose.dev.yml exec fiestaboard-api python scripts/run_plugin_tests.py --plugin=my_plugin
```

## Testing API Endpoints

```bash
# Health check
curl http://localhost:6969/health

# Status
curl http://localhost:6969/status

# Send message
curl -X POST http://localhost:6969/send-message \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message"}'
```

## Environment Variables

All services use the same `.env` file:

```bash
# Create .env from template
cp env.example .env
# Edit .env with your API keys
```

## Debugging

### View Logs

```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# API only
docker-compose -f docker-compose.dev.yml logs -f fiestaboard-api

# Web UI only
docker-compose -f docker-compose.dev.yml logs -f fiestaboard-ui-dev
```

### Access Container Shell

```bash
# API container
docker-compose -f docker-compose.dev.yml exec fiestaboard-api bash

# Web container
docker-compose -f docker-compose.dev.yml exec fiestaboard-ui-dev sh
```

### Check Container Status

```bash
docker-compose -f docker-compose.dev.yml ps
```

## Cursor IDE Shortcuts

If you use [Cursor](https://cursor.com/) as your editor, the project includes pre-built Cursor commands (in `.cursor/commands/`) that automate common tasks:

| Cursor Command | What It Does | Equivalent Manual Command |
|---------------|-------------|--------------------------|
| `/setup` | Check prerequisites, create `.env` and `config.json` | See [Initial Setup](#initial-setup) above |
| `/start` | Start dev containers (background) | `docker-compose -f docker-compose.dev.yml up -d` |
| `/stop` | Stop dev containers | `docker-compose -f docker-compose.dev.yml down` |
| `/restart` | Full rebuild (no cache) and restart | `down` → `build --no-cache` → `up -d` |
| `/redeploy-quick` | Quick rebuild (with cache) and restart | `down` → `build` → `up -d` |
| `/build` | Rebuild images without restarting | `docker-compose -f docker-compose.dev.yml build` |
| `/test-api` | Run API tests in Docker | `docker-compose -f docker-compose.dev.yml exec fiestaboard-api pytest` |
| `/test-web` | Run web tests in Docker | `docker-compose -f docker-compose.dev.yml exec fiestaboard-ui-dev npm test` |
| `/logs` | Stream container logs | `docker-compose -f docker-compose.dev.yml logs -f` |
| `/status` | Show container status | `docker-compose -f docker-compose.dev.yml ps` |

These commands are **optional** — everything can be done with the manual `docker-compose` commands shown in this guide.

## Quick Reference

| Task | Command |
|------|---------|
| Start dev environment | `docker-compose -f docker-compose.dev.yml up` |
| Stop dev environment | `docker-compose -f docker-compose.dev.yml down` |
| Rebuild containers | `docker-compose -f docker-compose.dev.yml up --build` |
| Run API tests | `docker-compose -f docker-compose.dev.yml exec fiestaboard-api pytest` |
| Run web tests | `docker-compose -f docker-compose.dev.yml exec fiestaboard-ui-dev npm run test:run` |
| View logs | `docker-compose -f docker-compose.dev.yml logs -f` |
| View API docs | http://localhost:6969/docs |
| View Web UI | http://localhost:3000 |

## Troubleshooting

### Port Already in Use

```bash
# Find what's using the port
lsof -i :6969
lsof -i :3000

# Kill the process or stop other Docker containers
docker-compose -f docker-compose.dev.yml down
```

### Container Won't Start

```bash
# Check logs for errors
docker-compose -f docker-compose.dev.yml logs

# Rebuild from scratch
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up --build
```

### API Can't Connect to Board

- Check `/status` endpoint for service status: `curl http://localhost:6969/status`
- Verify `.env` file has valid API keys
- Check network connectivity to board

### UI Can't Connect to API

- Check API is running: `curl http://localhost:6969/health`
- Check browser console for errors
- Verify both containers are on same Docker network
