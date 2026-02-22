# Local Development Guide

This guide is for **contributors and plugin developers** who want to work on FiestaBoard's code. If you just want to host a FiestaBoard server to control your board, see the [Quick Start](../../README.md#-quick-start) in the README instead.

**Dev and CI match production:** Development and CI both use the same single-container layout as production (API + UI on port 4420, API under `/api/*`). Dev adds mounted source and API `--reload`; CI builds the production image and runs E2E against it.

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
- Web UI and API: http://localhost:4420 (single container, same as production)
- API base path: http://localhost:4420/api/
- API Docs: http://localhost:4420/api/docs

### Hot Reload

The development Docker Compose mounts source code as volumes:

- **Python API**: Changes to `src/` and `plugins/` trigger uvicorn auto-reload
- **Next.js Web UI**: Requires image rebuild to see changes (same unified container as production)

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
# Run API tests (inside the FiestaBoard container)
docker-compose -f docker-compose.dev.yml exec fiestaboard pytest

# Run web tests (one-off container with profile test)
docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"
```

## Testing API Endpoints

```bash
# Health check
curl http://localhost:4420/api/health

# Status
curl http://localhost:4420/api/status

# Start service
curl -X POST http://localhost:4420/api/start

# Send message
curl -X POST http://localhost:4420/api/send-message \
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

# FiestaBoard app only
docker-compose -f docker-compose.dev.yml logs -f fiestaboard
```

### Access Container Shell

```bash
# FiestaBoard container (API + UI)
docker-compose -f docker-compose.dev.yml exec fiestaboard sh
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
| Run API tests | `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest` |
| View logs | `docker-compose -f docker-compose.dev.yml logs -f` |
| View API docs | http://localhost:4420/api/docs |
| View Web UI | http://localhost:4420 |

## Troubleshooting

### Port Already in Use

```bash
# Find what's using port 4420 (the single entry point)
lsof -i :4420

# Kill the process or stop other Docker containers
docker-compose down
```

If port 4420 is unavailable, you can remap to any free port by editing the `ports` mapping in `docker-compose.dev.yml`:

```yaml
ports:
  - "9090:3000"   # use a different host port
```

Only the host port (left of the colon) changes. The container-side port stays `3000` because that's where nginx listens internally. See the [Port Configuration](./DOCKER_SETUP.md#port-configuration) section for details.

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

- Check API is running: `curl http://localhost:4420/api/health`
- Check browser console for errors
