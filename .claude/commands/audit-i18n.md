Audit the FiestaBoard web UI for i18n issues — hardcoded strings, missing a11y keys, and locale drift.

Use the `i18n-auditor` agent.

Optional arguments:
- `--scope <path>` — limit TSX scanning to a subtree (e.g., `--scope web/src/app/schedules`). Default: all of `web/src/`.
- `--locale <code>` — limit locale drift comparison to a single non-English locale. Default: all 13 (de, es, fr, it, ja, ko, nl, pl, pt, ru, sv, tr, zh).
- `--max <N>` — cap each category at N findings (default: 25).

The agent (read-only) will scan three categories against `web/messages/en.json` as source of truth:

- **Category A — Hardcoded English in TSX**: JSX text (2+ words), `placeholder` / `title` / `alt` attributes, `toast.*` messages, user-facing `throw new Error(...)`. Suppresses comments, `console.*`, `data-testid`, single short tokens.
- **Category B — `aria-label` without `t()`**: Always shown in full — these block WCAG 2.2 AA.
- **Category C — Locale drift**: Per non-English locale: missing keys, extra (stale) keys, identical-to-English values (suppressed for proper nouns / brand / symbols).

Findings are ranked by route weight (`app/*/page.tsx` first) and trimmed to `--max`. Hand results to `docs-writer` or `a11y-engineer` for fixes — the agent does not edit.
