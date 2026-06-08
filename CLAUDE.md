# FiestaBoard — Claude Code Context

## Single-Container Architecture

This project uses a **unified single container** for all environments (production, development, and CI). The container runs the Python API, the React Router v7 + Vite web UI, and nginx reverse proxy together. All traffic goes through port 4420 on the host, mapped to nginx on port 3000 inside the container.

### Architecture Overview

- **Single Dockerfile** (`Dockerfile`): Multi-stage build producing one image with API + UI + nginx
- **Production** (`docker-compose.yml`): Single container, no volume mounts
- **Development** (`docker-compose.dev.yml`): Same container with volume mounts for Python hot-reload, uses `start-dev.sh` (uvicorn `--reload`)
- **CI** (`.github/workflows/ci.yml`): Tests run directly on the GitHub Actions host (not in Docker) for speed; Docker image build is verified separately

### Core Rules

1. **NEVER run the API server (`src/api_server.py` or `python -m src.api_server`) directly on the host machine**
   - Always use Docker containers via `docker-compose` commands

2. **NEVER run the web UI (`npm run dev` in `web/` directory) directly on the host machine**
   - Always use Docker containers via `docker-compose` commands

3. **NEVER install Python dependencies locally or suggest running `pip install`**
   - All Python dependencies are managed within Docker containers

4. **NEVER install Node.js dependencies locally or suggest running `npm install` in the web/ directory**
   - All Node.js dependencies are managed within Docker containers

### Development Workflow

- **Starting the dev container**: Use `/start` command or `docker-compose -f docker-compose.dev.yml up`
- **Stopping**: Use `/stop` command or `docker-compose -f docker-compose.dev.yml down`
- **Restarting**: Use `/restart` command (stops, rebuilds with --no-cache, restarts)
- **Building**: `docker-compose -f docker-compose.dev.yml build` to rebuild images without restarting
- **Running tests**: `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest` (API) or `docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"` (web)
- **Debugging**: Use `docker-compose logs -f` or `docker-compose exec` for interactive debugging
- **Checking status**: Use `docker-compose ps` to see container status
- **Code changes**: Edit code on host machine; Python changes auto-reload via volume mounts. UI changes require a container rebuild.
- **Installing dependencies**:
  - For Python: Update `requirements.txt` and rebuild the container
  - For Node.js: Update `web/package.json` and rebuild the container

### Testing Guidelines

- **Local development**: Tests run inside the Docker container
  - Use `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest` for Python tests
  - Use `docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"` for web tests
- **CI**: Tests run directly on the GitHub Actions host for speed (Python and Node.js installed natively)
- Re-testing after changes should also be done in the container

### Exceptions

The only code that may run locally:
- Utility scripts explicitly marked for local execution

### Available Commands

- `/start` - Start the dev container
- `/stop` - Stop the dev container
- `/restart` - Stop, rebuild with --no-cache, and restart the container
- `/qa-a11y` - Audit the running web UI for WCAG 2.2 AA accessibility issues
- `/qa-a11y-docs` - Audit markdown docs for accessibility issues
- `/fix-a11y` - Fix accessibility findings on a feature branch and open a PR

### When Suggesting Commands

Always suggest Docker-based commands:
- ✅ Use `/start`, `/stop`, `/restart` to control the container
- ✅ `docker-compose -f docker-compose.dev.yml up`
- ✅ `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest`
- ✅ `docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"`
- ❌ `python src/api_server.py`
- ❌ `cd web && npm run dev`
- ❌ `pip install -r requirements.txt`

## Plugin Architecture

This project uses a **plugin-based architecture** for data source integrations. Each plugin is self-contained with its own code, configuration, tests, and documentation.

### Plugin vs Platform Code

- **Plugins** (`plugins/`): Self-contained data source integrations (weather, transit, stocks, etc.)
- **Platform** (`src/`): Core FiestaBoard infrastructure (API server, template engine, board client)

### Key Plugin Concepts

- Plugins live in `plugins/<plugin_id>/` directories
- Each plugin has a `manifest.json` defining metadata, settings schema, and variables
- Plugins implement the `PluginBase` class from `src/plugins/base.py`
- Plugin IDs must be unique and match the directory name
- All plugins require tests with >80% coverage

## Documentation Requirements

### Plugin Documentation

When creating or modifying a plugin:
- **NEW plugins MUST be added** to the main `README.md` "Available Plugins" list (alphabetically)
- **Modifying existing plugins** does NOT require updating main README.md
- Plugin documentation goes in the plugin's own directory:
  - `plugins/PLUGIN_NAME/README.md` - Developer documentation (canonical format, see below)
  - `plugins/PLUGIN_NAME/docs/SETUP.md` - User-facing setup guide (canonical format, see below)
  - `plugins/PLUGIN_NAME/docs/board-display.png` - Primary screenshot (required for published plugins)
  - `plugins/PLUGIN_NAME/manifest.json` - Configuration schema, env vars, and screenshots

### Plugin Documentation Formats

**README.md** must follow this section order:
1. `# {Plugin Name} Plugin` — title
2. One-sentence description
3. `![{Name} Display](./docs/board-display.png)` — hero image (always `board-display.png`)
4. `**→ [Setup Guide](./docs/SETUP.md)**` — setup link
5. `## Overview` — 2-3 sentence description
6. `## Template Variables` — grouped to match manifest `variables.groups`
7. `## Example Templates` — code blocks with template content
8. `## Configuration` — table mirroring `settings_schema`
9. `## Features` — bullet list of capabilities
10. `## Author` — author name

**docs/SETUP.md** must follow this section order:
1. `# {Plugin Name} Setup Guide` — title
2. One-sentence description
3. `## Overview` — What it does + Prerequisites
4. `## Quick Setup` — numbered steps (Enable, Configure, Template, View)
5. `## Template Variables` — variable table
6. `## Configuration Reference` — full settings table + env vars
7. `## Troubleshooting` — common issues

### Plugin Image Conventions

All plugin images live in `plugins/PLUGIN_NAME/docs/` with standardized names:
- `board-display.png` — **Required.** Primary hero image showing board output
- `configuration.png` — Optional. Config dialog screenshot
- `integrations.png` — Optional. Plugin card on Integrations page
- Additional images use descriptive kebab-case names (e.g., `color-rules.png`)

All images referenced in the manifest `screenshots` array must exist in `plugins/PLUGIN_NAME/docs/`.

### User-Facing Setup Guides

For user-facing setup instructions (API key registration, configuration):
- Create `plugins/PLUGIN_NAME/docs/SETUP.md` inside the plugin directory
- Include screenshots in the plugin's `docs/` directory
- Use relative path format: `![Description](./screenshot.png)`

### Platform Documentation

When modifying platform/core functionality:
- Update `README.md` for significant platform changes
- Update `docs/development/PLUGIN_DEVELOPMENT.md` for plugin system changes
- Document new platform features in appropriate `docs/` subdirectory

### Environment Variables

- **For plugins**: Document in `manifest.json` under `env_vars` array
- **For platform**: Document in `env.example` with clear descriptions

### Information Security and Privacy

**CRITICAL: Never use real personal information in code, documentation, or examples.**

**Exception: Plugin authorship information is allowed:**
- ✅ **Plugin author name and email** in `manifest.json` `author` field is permitted
- ✅ Plugin creators may use their real name and contact email for attribution

When creating examples, documentation, or test data:
- ❌ **NEVER use real addresses, coordinates, or locations** (home, work, etc.)
- ❌ **NEVER use real API keys, tokens, or credentials** (even if expired)
- ❌ **NEVER use real phone numbers, emails, or personal identifiers** (except plugin author attribution)
- ❌ **NEVER use real names or personal data** in examples (except plugin author attribution)

**Always use:**
- ✅ **Random/fake coordinates**: Use well-known public landmarks (e.g., `40.7128, -74.0060` for NYC) or clearly fake values
- ✅ **Generic example values**: `example@example.com`, `555-0100`, `123 Main St, Anytown, ST 12345`
- ✅ **Test API keys**: Clearly marked as `test_` or `example_` prefixed
- ✅ **Placeholder data**: `your-api-key-here`, `your-username`, etc.

**For coordinates specifically:**
- Use well-known public landmarks (NYC: `40.7128, -74.0060`, London: `51.5074, -0.1278`)
- Or use clearly fake round numbers (e.g., `40.0000, -74.0000`)
- Never use coordinates that could identify a personal residence

**Before committing:**
1. Review all examples and documentation for personal information
2. Replace any real addresses, coordinates, or personal data with generic examples
3. Verify no API keys or credentials are hardcoded (even in comments)

## Development Artifacts

### No Temporary Markdown Files

**NEVER leave temporary markdown files in the repository root after completing a feature or task.**

Examples of files that should NOT be committed or left behind:
- ❌ Implementation notes (e.g., `FEATURE_IMPLEMENTATION.md`, `BAYWHEELS_UI_UPDATE.md`)
- ❌ Testing notes (e.g., `MANUAL_TESTING_*.md`, `TESTING_*.md`)
- ❌ Review summaries (e.g., `REVIEW_SUMMARY.md`, `IMPLEMENTATION_SUMMARY.md`)
- ❌ Edge case documentation (e.g., `EDGE_CASES.md`, `STATE_TRACKING.md`)
- ❌ Performance test notes (e.g., `PERFORMANCE_TEST.md`)
- ❌ Fix documentation (e.g., `DOCKER_PUBLISHING_FIX.md`)

### Proper Documentation Locations

Instead, put documentation in the appropriate place:

**For permanent documentation:**
- **Plugin developer docs**: `plugins/PLUGIN_NAME/README.md` - How the plugin works
- **Plugin setup guides**: `plugins/PLUGIN_NAME/docs/SETUP.md` - User-facing setup instructions
- **Plugin development**: `docs/development/PLUGIN_DEVELOPMENT.md` - How to create plugins
- **Deployment**: `docs/deployment/*.md` - Deployment and infrastructure docs
- **Reference**: `docs/reference/*.md` - Technical reference material
- **Setup**: `docs/setup/*.md` - Development environment setup
- **Architecture**: Add to `README.md` or create `docs/reference/ARCHITECTURE.md`
- **Web UI features**: `web/src/components/README.md` or component-specific docs in `web/`

**For temporary notes during development:**
- Keep notes in your local environment (not in git)
- Use comments in code for implementation details
- Use PR descriptions for change summaries
- Delete any temporary `.md` files before committing

### Cleanup Rule

Before completing any feature or task:
1. Review the repository root for any `*.md` files that aren't `README.md`
2. Move any valuable information to the proper location in `docs/`
3. Delete all temporary implementation/testing markdown files
4. Ensure all critical information is preserved in proper documentation

## Plugin Development Rules

### Creating a New Plugin

**IMPORTANT: All plugin development MUST be done in a feature branch, never directly on `main`.**

When creating a new plugin:
1. **Create a feature branch**: `git checkout -b feat-plugin-name` (e.g., `feat-lastfm`, `feat-weather`)
2. Copy the template: `cp -r plugins/_template plugins/my_plugin`
3. Update `manifest.json` with unique ID matching directory name
4. Add `screenshots` array to `manifest.json` with at least one `primary: true` entry
5. Implement `PluginBase` class in `__init__.py`
6. Create tests in `tests/` directory with >80% coverage
7. Write `README.md` following the canonical section order (see Plugin Documentation Formats)
8. Write `docs/SETUP.md` following the canonical section order
9. Add `docs/board-display.png` screenshot (required for published plugins)
10. **Add plugin to project README.md** under "Available Plugins" section (alphabetically ordered)
11. Push branch and create a pull request for review

### Required Plugin Files

Every plugin MUST have:
- `__init__.py` - Plugin implementation (PluginBase subclass)
- `manifest.json` - Plugin metadata, settings schema, variables, screenshots
- `README.md` - Plugin documentation (canonical format with `./docs/board-display.png` hero image)
- `tests/` - Test directory with test files
- `docs/SETUP.md` - User-facing setup guide (canonical format)
- `docs/board-display.png` - Primary screenshot (required for published plugins)

### Plugin Documentation Checklist

When a new plugin is complete, verify:
- [ ] `README.md` follows canonical section order with hero image `./docs/board-display.png`
- [ ] `docs/SETUP.md` follows canonical section order
- [ ] `docs/board-display.png` exists (primary screenshot)
- [ ] `manifest.json` includes `screenshots` array with `primary: true` entry
- [ ] Plugin is added to main `README.md` "Available Plugins" list (alphabetically)
- [ ] Tests pass with >80% coverage

### Plugin Manifest Requirements

The `manifest.json` MUST include:
- `id` - Unique identifier matching directory name (lowercase, underscores)
- `name` - Human-readable display name
- `version` - Semantic version (X.Y.Z)
- `settings_schema` - JSON Schema for configuration
- `variables` - Template variables exposed by plugin

Optional but recommended:
- `icon` - Lucide icon name for UI display
- `category` - Category for grouping (MUST use an existing category - see below)
- `description` - Brief description
- `author` - Plugin author/maintainer
- `screenshots` - Array of screenshot entries with `src`, `alt`, and `primary` flag

### Plugin Categories

**IMPORTANT: Always use an existing category. Do NOT create new categories.**

Before assigning a category, check existing plugins to see what categories are in use:
```bash
grep -r '"category"' plugins/*/manifest.json | grep -v _template
```

**Current valid categories:**
- `art` - Display art and visual displays (sun art, visual clock)
- `data` - Data feeds (stocks, sports scores, aircraft tracking)
- `entertainment` - Fun/media content (music, quotes)
- `home` - Home automation (Home Assistant)
- `transit` - Transportation (Muni, traffic, bike sharing)
- `utility` - General utilities (date/time, WiFi credentials)
- `weather` - Weather-related (weather, air quality, surf)

When in doubt, use `utility` as the default category.

### Plugin Testing Requirements

- All plugins MUST have tests in `tests/` directory
- Minimum coverage requirement: **80%**
- CI will fail if coverage is below threshold
- Run tests with: `python scripts/run_plugin_tests.py --plugin=my_plugin`
- **No dead code**: Remove unreachable code paths identified by coverage reports
  - If coverage shows unreachable lines (e.g., `elif` branches that can never execute), remove them
  - Dead code reduces code clarity and can confuse future maintainers
  - Use coverage reports to identify and eliminate dead code before completing a plugin

### Plugin Validation

CI automatically validates:
- All plugin IDs are unique (no duplicates allowed)
- Plugin ID matches directory name
- Manifest has required fields
- Manifest JSON is valid

### When Modifying Plugins

**IMPORTANT: Plugin modifications should also be done in feature branches, not directly on `main`.**

- ✅ Create a feature branch: `git checkout -b fix-plugin-name` or `feat-plugin-name-feature`
- ✅ Edit plugin files in `plugins/PLUGIN_NAME/`
- ✅ Update plugin's own `README.md`
- ✅ Update plugin's `manifest.json` for config changes
- ✅ Add/update tests in plugin's `tests/` directory
- ✅ Push branch and create pull request for review
- ❌ Do NOT add plugin-specific code to `src/` (platform code)
- ❌ Do NOT document individual plugins in main `README.md` (unless it's a new plugin)
- ❌ Do NOT commit directly to `main` branch

## Page Schema Versioning

> Applies to: `src/pages/**/*.py`

`pages.json` uses a `schema_version` integer for ordered migrations.
When changing the stored format of pages (adding/removing/renaming fields,
changing how data is encoded), you MUST use this system instead of ad-hoc
detection.

### How It Works

- `src/pages/storage.py` has `CURRENT_SCHEMA_VERSION` and a `MIGRATIONS` list
- Each migration is a `(target_version, function)` tuple
- On startup `_load()` reads `schema_version` (default 0), runs pending
  migrations in order, bumps the version, and resaves once

### Adding a New Migration

1. Write a migration function in `storage.py`:

```python
def _migrate_v1_to_v2(pages_data: List[dict]) -> int:
    """Migration 1 -> 2: describe what changes."""
    migrated = 0
    for page_data in pages_data:
        # mutate page_data in place
        migrated += 1
    return migrated
```

2. Append to `MIGRATIONS`:

```python
MIGRATIONS: List[Tuple[int, Callable[[List[dict]], int]]] = [
    (1, _migrate_v0_to_v1),
    (2, _migrate_v1_to_v2),  # NEW
]
```

3. Bump `CURRENT_SCHEMA_VERSION`:

```python
CURRENT_SCHEMA_VERSION = 2  # was 1
```

### Rules

- NEVER use heuristic detection (key presence, string length, etc.) to
  decide if a page needs migrating — use schema_version
- NEVER modify the stored format without adding a migration
- Migrations MUST be idempotent and safe to re-run
- Migrations operate on raw dicts (before Pydantic validation)
- Always log how many pages were affected
- A backup is created automatically before the first migration runs
