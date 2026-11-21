# FiestaBoard — Agent Instructions

`CLAUDE.md` is the full project context (architecture, Docker workflow,
plugin rules, Changesets). Read it before making changes; it applies to every
coding agent, not only Claude Code.

## Before opening a PR

CI no longer runs AI reviews on PRs, so check these yourself before check-in:

- **UI change** (`web/src/**/*.tsx`, `web/messages/**`): review the touched
  components against WCAG 2.2 AA — accessible names on controls and icon
  buttons, `aria-hidden` on decorative icons, keyboard reachability and visible
  focus, labelled form fields, live regions for async status, and translated
  strings for any new user-facing text.
- **Docs change** (`**/*.md`, `plugins/*/docs/**`, excluding `.changeset/`):
  match the canonical doc formats in `CLAUDE.md`, verify every claim against
  the code, use no real PII in examples, keep heading order and link text
  accessible, and keep FiestaBoard (this app) distinct from Vestaboard (the
  hardware).
