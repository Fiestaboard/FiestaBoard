# Local Development Guide

This guide is for **contributors and plugin developers** who want to work on FiestaBoard's code. If you just want to host a FiestaBoard server to control your board, see the [Get Started in 5 Minutes](../../README.md#get-started-in-5-minutes) in the README instead.

**Dev and CI match production:** Development and CI both use the same single-container layout as production (API + UI on port 4420, API under `/api/*`). Dev adds mounted source and API `--reload`; CI builds the production image and runs E2E against it.

## Prerequisites

- Docker and Docker Compose installed
- A `.env` file with your board API key (copy from `env.example`)

> **Important:** Do not run the API (`src/api_server.py`) or the web UI (`npm run dev`) directly on the host. All commands here run **inside** the dev container — no local `pip install` or `npm install` required.

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

If you're working in Claude Code, the project ships matching slash commands: `/start` (up -d), `/stop` (down), and `/restart` (down + `--no-cache` rebuild + up -d).

**Access:**
- Web UI and API: http://localhost:4420 (single container, same as production)
- API base path: http://localhost:4420/api/
- API Docs: http://localhost:4420/api/docs

### Hot Reload

The development Docker Compose mounts source code as volumes (`./src`, `./plugins`, `./web`, `./tests`, `./scripts`, plus `./data`):

- **Python API**: Changes to `src/` and `plugins/` trigger uvicorn `--reload` automatically — no restart needed.
- **React Router / Vite Web UI**: The container serves the production build that was baked into the image, so UI changes need a container rebuild (`docker-compose -f docker-compose.dev.yml up --build` or `/restart`). For interactive component work, Storybook is available as an opt-in service — see [Storybook](#storybook) below.

### Storybook

Storybook is an **opt-in** service for interactive component development. It does not start when you run `docker-compose up` — it only runs when you explicitly request it.

```bash
# Start Storybook (runs npm install on every startup — first launch takes a minute)
docker-compose -f docker-compose.dev.yml up fiestaboard-storybook

# Or use the profile flag to start core services + Storybook together
docker-compose -f docker-compose.dev.yml --profile storybook up
```

Once running, Storybook is available at **http://localhost:6006**.

> **Note:** Storybook runs `npm install --force` on every startup because it shares the `web/` volume with the main container. The first run may take a minute; subsequent starts are faster.

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

# Service status
curl http://localhost:4420/api/status

# Start the display service
curl -X POST http://localhost:4420/api/start

# Send an ad-hoc message
curl -X POST http://localhost:4420/api/send-message \
  -H "Content-Type: application/json" \
  -d '{"text": "Test message"}'
```

For the full schema, open the interactive docs at `http://localhost:4420/api/docs`.

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

The repo ships a `.devcontainer/` with `devcontainer.json`, a build `Dockerfile`, and a `post-create.sh` hook. To use it:

1. Install the **Dev Containers** extension in VS Code.
2. Open the repo folder, then run **Dev Containers: Reopen in Container** from the command palette.
3. Dependencies install automatically via `post-create.sh`. When the build finishes, VS Code is attached to the container with the same toolchain CI uses.

## Quick Reference

| Task | Command |
|------|---------|
| Start dev environment | `docker-compose -f docker-compose.dev.yml up` |
| Stop dev environment | `docker-compose -f docker-compose.dev.yml down` |
| Rebuild containers | `docker-compose -f docker-compose.dev.yml up --build` |
| Run API tests | `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest` |
| Run web tests | `docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"` |
| View logs | `docker-compose -f docker-compose.dev.yml logs -f` |
| View API docs | http://localhost:4420/api/docs |
| View Web UI | http://localhost:4420 |
| Start Storybook (opt-in) | `docker-compose -f docker-compose.dev.yml up fiestaboard-storybook` |
| View Storybook | http://localhost:6006 |

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

Only the host port (left of the colon) changes. The container-side port stays `3000` because that's where nginx listens internally.

### Container Won't Start

```bash
# Check logs for errors
docker-compose -f docker-compose.dev.yml logs

# Rebuild from scratch
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml up --build
```

### API Can't Connect to Board

- Check `http://localhost:4420/api/status` for service status.
- Verify `.env` has valid board credentials (see `env.example`).
- Confirm the container can reach your board's network. The default dev compose seeds `BOARD_API_MODE=local`, `BOARD_HOST=fiestaboard-mock-board`, and `BOARD_LOCAL_API_KEY=mock-dev-key` so a fresh install talks to the bundled mock board instead of stranding the UI on a spinner. Real-board settings in `data/config.json` always win over those seeds.

### UI Can't Connect to API

- Check API is running: `curl http://localhost:4420/api/health`
- Check browser console for errors
