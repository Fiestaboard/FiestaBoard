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
docker-compose -f docker-compose.dev.yml up --build

# Access Web UI at http://localhost:3000
# Access API at http://localhost:8000 (direct, separate container in dev mode)
```

The development environment uses **two separate containers** (`fiestaboard-api-dev` on port 8000 and `fiestaboard-ui-dev` on port 3000) with **hot reload** for both Python and Next.js code. This is different from the production single-container setup.

## Project Structure

```
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
├── Dockerfile                  # Unified Dockerfile (production: API + Web UI in one image)
├── Dockerfile.api              # API-only Dockerfile (used by docker-compose.dev.yml)
├── Dockerfile.ui-dev           # Web UI dev Dockerfile (hot reload, used by docker-compose.dev.yml)
├── docker-compose.yml          # Production compose (single container, port 3000)
└── docker-compose.dev.yml      # Development compose (two containers, hot reload)
```

## Running Tests

```bash
# Run web UI tests
npm run test:web

# Run Python tests
pytest tests/
```

## Code Style

The project uses:
- **ESLint** for JavaScript/TypeScript
- **Pylint** for Python

```bash
# Lint web code
npm run lint:web
```

## Next Steps

- [Plugin Development](/docs/development/plugin-guide) - Create your own plugins
