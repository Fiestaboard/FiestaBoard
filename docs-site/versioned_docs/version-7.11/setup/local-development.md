---
sidebar_position: 2
description: "Set up a FiestaBoard development environment with hot-reload for contributing code or building plugins."
keywords: [FiestaBoard development, local setup, dev environment, Python, Node.js, hot reload]
---

# Local Development

This guide is for **contributors and plugin developers** who want to work on FiestaBoard's code. If you just want to host a FiestaBoard server to control your board, see the [Quick Start](/docs/setup/quick-start) instead.

## Development with Docker Compose

The recommended way to develop FiestaBoard:

```bash
# Build and run development environment
docker compose -f docker-compose.dev.yml up --build

# Access Web UI and API at http://localhost:4420 (single container, same as production)
# API base path: http://localhost:4420/api/
```

The development environment uses the **same single-container layout** as production (API + UI + nginx on port 4420), with mounted source volumes for Python API hot-reload. Web UI changes require a container rebuild (`--build`).

## Project Structure

```text
FiestaBoard/
├── plugins/                    # Plugin-based data sources
│   ├── _template/              # Template for new plugins
│   ├── weather/                # Weather plugin
│   ├── stocks/                 # Stocks plugin
│   └── .../                    # Other plugins
├── src/                        # Platform core (API, display service)
│   ├── api_server.py           # FastAPI REST API
│   ├── main.py                 # Display service core
│   ├── config.py               # Configuration management
│   └── plugins/                # Plugin system infrastructure
├── web/                        # Next.js web UI
│   └── src/                    # React components and pages
├── docs-site/                  # Docusaurus documentation
├── tests/                      # Platform test suite
├── Dockerfile                  # Unified Dockerfile (API + Web UI + nginx in one image)
├── docker-compose.yml          # Production compose (single container, port 4420)
└── docker-compose.dev.yml      # Development compose (single container with hot-reload + optional test/Storybook services)
```

## Running Tests

Tests run inside the Docker container during local development:

```bash
# Run Python API tests
docker compose -f docker-compose.dev.yml exec fiestaboard pytest

# Run web UI tests (one-off container)
docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"
```

In CI, tests run directly on the GitHub Actions host for speed (not in Docker).

## Code Style

The project uses:

- **ESLint** for JavaScript/TypeScript
- **Pylint** for Python

## Next Steps

- [Plugin Development](/docs/development/plugin-guide) - Create your own plugins
