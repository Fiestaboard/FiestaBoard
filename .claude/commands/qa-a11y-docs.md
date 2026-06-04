Audit FiestaBoard markdown docs for accessibility issues.

Use the `a11y-docs-auditor` agent. Optional argument: a `<path-glob>` (e.g. `plugins/date_time`, `docs/`). With no argument, the agent sweeps the root `README.md`, every `docs/**/*.md`, and every `plugins/*/README.md` + `plugins/*/docs/*.md` (excluding `plugins/_template/`).

The agent (read-only) will:
1. Discover the target file set with `find`.
2. Flag empty / uninformative image alt text (`![]`, `![image]`, `![screenshot]`).
3. Check heading hierarchy — exactly one H1, no skipped levels.
4. Flag uninformative link text ("click here", bare URLs).
5. Flag color- or direction-only prose cues ("the red button", "see above").
6. Flag fenced code blocks missing a language identifier.

It will not edit docs — it produces an inline markdown findings table with `File:line` references. Hand the output to `/fix-a11y` to ship the fixes.
