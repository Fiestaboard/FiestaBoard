Audit one or all FiestaBoard plugins for canonical-format compliance.

Use the `plugin-doctor` agent in **audit** mode.

- With an `<id>` argument: audit only that plugin.
- Without an argument: audit every plugin under `plugins/` (excluding `_template/`).

The agent will check README/SETUP section orders, manifest schema, category enum, screenshots presence, `docs/board-display.png`, test coverage (≥80% gate), and run `scripts/validate_plugins.py`. It will end with a per-plugin punch list. It is read-only — it does not modify plugin files.
