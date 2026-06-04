Scaffold a new FiestaBoard plugin from `plugins/_template/`.

Use the `plugin-doctor` agent in **scaffold** mode. Required argument: the plugin `<id>` (lowercase, underscores, must match the new directory name).

The agent will:
1. Verify a feature branch exists (`feat-plugin-<id>`).
2. Copy `_template/` to `plugins/<id>/`.
3. Fill `manifest.json` (id, name, version 0.1.0, category from existing enum, screenshots array).
4. Write canonical README.md and `docs/SETUP.md`.
5. Stub `__init__.py`, tests, and `docs/board-display.png` placeholder.
6. Add the plugin alphabetically to the root README "Available Plugins".
7. Run `scripts/validate_plugins.py --plugin=<id>` and report.

If no `<id>` is provided, ask before scaffolding.
