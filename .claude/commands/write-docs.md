Write new community documentation for FiestaBoard — plugin READMEs, SETUP guides, or development docs.

Use the `docs-writer` agent in **write** mode. Required argument: `<target>` — typically a plugin ID (e.g. `weather`, `countdown`) or a topic slug (e.g. `plugin-development-walkthrough`).

The agent will:
1. Read the existing FiestaBoard plugin READMEs to ground itself in the project's voice (examples-first, no marketing fluff, short paragraphs).
2. Read `plugins/<id>/manifest.json` and `__init__.py` if writing plugin docs, so variables and settings come from code, not invention.
3. Create a feature branch (`docs/<target>`).
4. Draft `plugins/<id>/README.md` in the canonical 10-section order and `plugins/<id>/docs/SETUP.md` in the canonical 7-section order (from `plugins/CLAUDE.md`), or place a topic doc under `docs/development/`, `docs/setup/`, or `docs/reference/` as appropriate.
5. Update the root `README.md` "Available Plugins" list alphabetically if this is a new plugin.
6. Commit one logical artifact per commit with `docs(<scope>):` messages.
7. Open a PR with a voice / format checklist.

It will never use real PII in examples (the plugin `author` field is the only exception), never invent template variables that aren't in the manifest, and never copy screenshots from other plugins.
