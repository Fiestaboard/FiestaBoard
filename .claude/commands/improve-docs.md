Improve existing FiestaBoard documentation — tighten voice, fix accuracy, restore canonical structure, add concrete examples.

Use the `docs-writer` agent in **improve** mode. Required argument: `<path>` — a single file or a glob (e.g. `plugins/countdown/README.md`, `plugins/*/docs/SETUP.md`, `docs/development/`).

The agent will:
1. Read the existing files end-to-end and the relevant canonical reference (`plugins/CLAUDE.md` for plugin docs).
2. Read the related `manifest.json` and source code to confirm what the docs claim actually matches reality.
3. Create a feature branch (`docs/improve-<area>`).
4. Group issues into categories — structure (wrong section order, missing sections), voice (marketing fluff, abstract placeholders, long paragraphs), accuracy (variables in docs that don't exist in code), privacy (real PII leaks), and examples (placeholder values where concrete realistic ones belong).
5. Commit one logical improvement per commit. A section reorder is one commit; a voice rewrite is another.
6. Preserve the original author's intent and tone where it's good — this is not a from-scratch rewrite.
7. Open a PR listing improvements addressed.

If the docs are largely fine and only need light edits, the agent will say so rather than padding the PR with cosmetic changes.
