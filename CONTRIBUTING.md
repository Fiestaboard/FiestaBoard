# Contributing to FiestaBoard

Thank you for your interest in contributing to FiestaBoard. This document explains how to propose changes via branches and pull requests, and how we develop and test.

## Table of contents

- [Getting started](#getting-started)
- [Development workflow](#development-workflow)
- [Submitting changes](#submitting-changes)
- [Code and documentation standards](#code-and-documentation-standards)
- [Plugins](#plugins)
- [Security](#security)

---

## Getting started

- **Set up your environment**: See [Local Development](./docs/setup/LOCAL_DEVELOPMENT.md) for Docker-based development. We use Docker for all development and testing—please do not run the API or web UI directly on the host.
- **Explore the project**: The [README](./README.md) describes features, plugins, and quick start. Core code lives in `src/`; each integration is a plugin under `plugins/`.

---

## Development workflow

### 1. Create a new branch

Do your work on a branch instead of `main` or `develop`:

```bash
# Update your local main (or develop)
git fetch origin
git checkout main
git pull origin main

# Create a branch with a descriptive name
git checkout -b feat-add-thing      # for new features
git checkout -b fix-bug-description # for bug fixes
git checkout -b docs-update-readme  # for documentation
```

**Branch naming:** Prefer prefixes like `feat-`, `fix-`, or `docs-` so intent is clear. For new plugins, use e.g. `feat-plugin-name`.

### 2. Make your changes

- Edit code and docs on your branch.
- For API/web changes, use the dev stack so code is mounted and reloads:
  ```bash
  docker-compose -f docker-compose.dev.yml up
  ```
- Run tests before opening a PR (see [Testing](#testing)).

### 3. Run tests locally

All tests run inside Docker:

```bash
# Platform/API tests
docker-compose -f docker-compose.dev.yml up -d
docker-compose exec fiestaboard-api pytest

# Web UI tests
docker-compose exec fiestaboard-ui-dev npm run test:run

# Plugin validation (if you changed plugins)
docker-compose exec fiestaboard-api python scripts/validate_plugins.py --verbose

# Plugin tests (if you changed a specific plugin)
docker-compose exec fiestaboard-api python scripts/run_plugin_tests.py --plugin=my_plugin
```

CI runs on push/PR; make sure the same commands (or their CI equivalents) pass locally.

---

## Submitting changes

### 1. Open a pull request

- **Target branch**: Open your PR against `main` (or `develop` if the project is using that for integration).
- **Description**: Explain what changed and why. Reference any related issues.
- **Scope**: Keep the PR focused—one feature or fix per PR is easier to review.

### 2. Squash your commits

We ask that each PR be **one logical change** and, when merging, that it be **squashed into a single commit**. You can do this in either of these ways:

**Option A – Squash before pushing (recommended)**  
Keep a clean history on your branch by squashing locally before opening (or updating) the PR:

```bash
# If you have 3 commits to squash into one (adjust count as needed)
git rebase -i HEAD~3
# In the editor: leave the first line as "pick", change the rest to "squash" (or "s")
# Save and close; edit the final commit message if needed
git push --force-with-lease origin feat-add-thing
```

**Option B – Let the maintainer squash**  
If the repo is set to “Squash and merge” on GitHub, the maintainer can squash when merging. You can still tidy your branch with Option A if you prefer.

### 3. After your PR is merged

- Delete your branch (or it may be auto-deleted).
- Pull the latest `main` (or `develop`) before starting your next branch.

---

## Code and documentation standards

- **Docker-first**: Do not run `python -m src.api_server` or `npm run dev` on the host. Use `docker-compose` as in [Local Development](./docs/setup/LOCAL_DEVELOPMENT.md).
- **No secrets**: Never commit `.env`, API keys, or real credentials. Use `env.example` and placeholders in docs.
- **Privacy**: Do not use real personal data (addresses, coordinates, phone numbers, etc.) in code, tests, or docs. Use generic examples (e.g. `example@example.com`, well-known public coordinates).
- **Python**: The project uses pylint (see `.pylintrc`) and expects platform tests to pass. New platform code should be covered by tests.
- **Temporary files**: Do not leave temporary markdown or implementation notes in the repo root. Put lasting docs in `docs/` or the right plugin/docs folder.

---

## Plugins

- **Adding a new plugin**: Use a **feature branch** (e.g. `feat-my-plugin`). Follow the [Plugin Development Guide](./docs/development/PLUGIN_DEVELOPMENT.md): copy `plugins/_template`, implement the plugin, add tests (≥80% coverage), and add the plugin to the “Available Plugins” list in the main [README](./README.md).
- **Changing an existing plugin**: Use a branch (e.g. `fix-weather-api` or `feat-plugin-name-feature`). Update the plugin’s own README and docs; update the main README only when adding a *new* plugin.

---

## Security

If you discover a security issue, do **not** open a public issue. See [SECURITY.md](./SECURITY.md) for how to report it.

---

## Questions?

- Open a GitHub Discussion or issue for general questions (use the project’s repository URL once it’s public or shared).
- For bugs or feature ideas, use the issue tracker and try to keep one topic per issue.

Thanks for contributing.
