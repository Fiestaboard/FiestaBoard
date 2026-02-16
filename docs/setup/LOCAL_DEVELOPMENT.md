# Local Development Guide

This guide is for **contributors and plugin developers** who want to work on FiestaBoard's code. If you just want to host a FiestaBoard server to control your board, see the [Quick Start](../../README.md#-quick-start) in the README instead.

## Prerequisites

- Docker and Docker Compose installed
- A `.env` file with your board API key (copy from `env.example`)

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

**Access:**
- Web UI: http://localhost:3000
- API: http://localhost:6969
- API Docs: http://localhost:6969/docs

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
```

## Testing

```bash
# Run API tests
docker-compose exec fiestaboard-api pytest

# Run web tests
docker-compose exec fiestaboard-ui-dev npm test
```

## Testing API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Status
curl http://localhost:8000/status

# Start service
curl -X POST http://localhost:8000/start

# Send message
curl -X POST http://localhost:8000/send-message \
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
docker-compose exec fiestaboard-api bash

# Web container
docker-compose exec fiestaboard-ui-dev sh
```

### Check Container Status

```bash
docker-compose -f docker-compose.dev.yml ps
```

## VS Code / Dev Container

If using VS Code with Dev Containers:

1. The `.devcontainer/devcontainer.json` is configured
2. Open in container: VS Code → "Reopen in Container"
3. Dependencies are installed automatically

## Quick Reference

| Task | Command |
|------|---------|
| Start dev environment | `docker-compose -f docker-compose.dev.yml up` |
| Stop dev environment | `docker-compose -f docker-compose.dev.yml down` |
| Rebuild containers | `docker-compose -f docker-compose.dev.yml up --build` |
| Run API tests | `docker-compose exec fiestaboard-api pytest` |
| View logs | `docker-compose -f docker-compose.dev.yml logs -f` |
| View API docs | http://localhost:8000/docs |
| View Web UI | http://localhost:3000 |

## Troubleshooting

### Port Already in Use

```bash
# Find what's using the port
lsof -i :8000
lsof -i :3000

# Kill the process or stop other Docker containers
docker-compose down
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

- Check `/status` endpoint for service status
- Verify `.env` file has valid API keys
- Check network connectivity to board

### UI Can't Connect to API

- Check API is running: `curl http://localhost:8000/health`
- Check browser console for errors
- Verify both containers are on same Docker network
