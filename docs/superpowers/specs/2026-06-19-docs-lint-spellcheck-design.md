# Docs Quality Gate: Spell-check, Markdown-lint, Frontmatter-lint & Link-check

**Date:** 2026-06-19
**Status:** Approved (pending spec review)
**Author:** Jeffrey Johnson (with Claude)

## Summary

Port the docs-quality tooling from `Gusto/embedded-react-sdk` to FiestaBoard.
Both projects use Docusaurus, so the approach transfers cleanly. We add four
checks over the repo's markdown, enforced in CI:

1. **Spell check** — `cspell`
2. **Markdown lint** — `markdownlint-cli2`
3. **Frontmatter lint** — custom Node script (docs-site pages only)
4. **Repo-wide broken-link check** — `lychee`

The first three are net-new. A docs-site-only link check already exists
(`build-docs` job + `onBrokenLinks: "throw"`); the lychee addition extends
link validation to *all* markdown, including external URLs.

## Goals

- Catch spelling errors, markdown-style drift, missing frontmatter, and broken
  links in pull requests before they merge.
- Cover **all** repository markdown (not only the published docs site).
- Enforce via **CI only** — no local pre-commit hooks (FiestaBoard has none
  today; adding husky/lint-staged would change every contributor's workflow).
- Land the checks **green**: fix existing violations first, wire CI last.

## Non-goals

- No pre-commit hooks (husky / lint-staged).
- No new docs *content* — this is tooling only.
- No change to the existing docs deploy pipeline (`docs.yml`) or the existing
  `lint-docs` / `build-docs` CI jobs.

## Scope of files

**In scope** for spell-check + markdown-lint:

- `docs/**/*.md` (internal dev guides, ~14 files)
- `docs-site/docs/**/*.{md,mdx}` (published Docusaurus site, ~61 files)
- `plugins/*/README.md` and `plugins/*/docs/**/*.md`
- Root `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  `DOCKERHUB_README.md`

**Excluded** (ignore list):

- `node_modules/**`
- `docs-site/build/**`, `docs-site/.docusaurus/**`
- `docs-site/versioned_docs/**`, `docs-site/versioned_sidebars/**`
  (~40 frozen historical snapshots — cannot be retroactively fixed and would
  dominate the output)
- `docs/superpowers/**` (transient AI specs/plans, including this file)
- `CLAUDE.md` and `.claude/**` (agent instructions, not documentation)
- `CHANGELOG`-style generated files, if any are added later

**Frontmatter lint** is scoped *more narrowly* to `docs-site/docs/**` only.
Plugin READMEs and root-level markdown legitimately have no YAML frontmatter,
so requiring it there would be incorrect.

## Components

### 1. `cspell.json` (repo root)

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/streetsidesoftware/cspell/main/cspell.schema.json",
  "version": "0.2",
  "language": "en",
  "dictionaries": ["en_US", "node", "typescript", "npm", "softwareTerms", "html", "css"],
  "files": [
    "docs/**/*.md",
    "docs-site/docs/**/*.{md,mdx}",
    "plugins/*/README.md",
    "plugins/*/docs/**/*.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "DOCKERHUB_README.md"
  ],
  "ignorePaths": [
    "**/node_modules/**",
    "docs-site/build/**",
    "docs-site/.docusaurus/**",
    "docs-site/versioned_docs/**",
    "docs/superpowers/**",
    "CLAUDE.md",
    ".claude/**"
  ],
  "ignoreRegExpList": [
    "https?://\\S+",
    "```[\\s\\S]*?```",
    "`[^`]*`",
    "<!--[\\s\\S]*?-->",
    "\\w*&[a-z]+;\\w*"
  ],
  "words": [ /* curated allowlist — built during implementation */ ]
}
```

The `words` allowlist is built iteratively: run `cspell`, collect unknown words,
keep the legitimate ones (FiestaBoard, Vestaboard, split-flap, plugin names,
technical terms), fix genuine typos.

### 2. `.markdownlint-cli2.jsonc` (repo root)

Rules tuned to FiestaBoard's existing conventions. Starting point (refined
during implementation to whatever the existing docs actually need):

```jsonc
{
  "config": {
    "default": true,
    "MD003": { "style": "atx" },
    "MD013": false,        // long prose lines are intentional; no hard wrap
    "MD024": false,        // repeated headings (e.g. plugin doc sections) ok
    "MD025": { "front_matter_title": "" },
    "MD033": false,        // inline HTML allowed (MDX + README badges)
    "MD034": false,        // bare URLs appear in some docs
    "MD036": false,
    "MD040": true,         // fenced code blocks must declare a language
    "MD041": false,        // first line need not be H1 (frontmatter precedes)
    "MD046": { "style": "fenced" }
  },
  "globs": [
    "docs/**/*.md",
    "docs-site/docs/**/*.md",
    "docs-site/docs/**/*.mdx",
    "plugins/*/README.md",
    "plugins/*/docs/**/*.md",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "DOCKERHUB_README.md"
  ],
  "ignores": [
    "**/node_modules/**",
    "docs-site/build/**",
    "docs-site/.docusaurus/**",
    "docs-site/versioned_docs/**",
    "docs/superpowers/**",
    "CLAUDE.md",
    ".claude/**"
  ]
}
```

### 3. `scripts/lint-docs-frontmatter.mjs`

Plain Node ESM (no `tsx`/TypeScript dependency). Walks `docs-site/docs/**`,
extracts the leading `---` frontmatter block, and fails if a page is missing a
non-empty `description:`. Reports every violation with its file path and a
non-zero exit on failure. Mirrors Gusto's `lintDocsFrontmatter.ts` but adapted
to FiestaBoard's frontmatter convention (`description` + `keywords` +
`sidebar_position`; the title comes from the in-body H1, not a `title:` field).

### 4. Root `package.json` additions

```jsonc
{
  "devDependencies": {
    "cspell": "^10",
    "markdownlint-cli2": "^0.22"
  },
  "scripts": {
    "docs:lint:spell": "cspell lint --no-progress --no-must-find-files",
    "docs:lint:markdown": "markdownlint-cli2",
    "docs:lint:frontmatter": "node scripts/lint-docs-frontmatter.mjs",
    "docs:lint": "npm run docs:lint:frontmatter && npm run docs:lint:markdown && npm run docs:lint:spell"
  }
}
```

Per CLAUDE.md these are never installed locally during normal development —
they run in CI. A contributor may run them ad hoc via `npx` if they choose.

### 5. `lychee.toml` (repo root) + repo-wide link check

`lychee` validates relative-path links, anchors, and external URLs across all
in-scope markdown. Config tuned to minimize false failures:

- `accept` a sensible set of status codes (200, 206, 429, etc.)
- `max_retries` and a request timeout for transient external failures
- `exclude` placeholder/example hosts (`example.com`, `localhost`, `127.0.0.1`,
  `your-*` placeholders) and any host that proves persistently flaky
- exclude the same paths as the ignore list above

**Flakiness note:** external link checks can fail transiently (rate limits,
downtime). If the per-PR job proves noisy in practice, the fallback is to move
the lychee job to a scheduled (cron) workflow and keep only relative-link
checking on PRs. We start with per-PR and tune the ignore list as needed.

## CI integration

All changes are in `.github/workflows/ci.yml`, following the existing
per-concern pattern (one job, gated by a `dorny/paths-filter` output,
aggregated by `CI Success`).

1. **New `markdown` path filter** in the `detect-changes` job:

   ```yaml
   markdown:
     - '**/*.md'
     - '**/*.mdx'
     - 'cspell.json'
     - '.markdownlint-cli2.jsonc'
     - 'lychee.toml'
     - 'scripts/lint-docs-frontmatter.mjs'
     - 'package.json'
   ```

2. **New `lint-markdown` job** — `needs: detect-changes`, runs when
   `markdown == 'true' || shared == 'true'`:
   - checkout → setup-node 20 (cache root `package-lock.json`)
   - `npm ci` (root)
   - `npm run docs:lint:frontmatter`
   - `npm run docs:lint:markdown`
   - `npm run docs:lint:spell`

3. **New `link-check` job** — `needs: detect-changes`, same gate:
   - checkout
   - `lycheeverse/lychee-action@v2` with the in-scope globs and `lychee.toml`,
     `fail: true`

4. **Wire into `CI Success`**: add `lint-markdown` and `link-check` to the
   `needs:` array *and* to the positional `NAMES` list in the aggregator step.

The existing `lint-docs` (ESLint/Prettier on docs-site) and `build-docs`
(Docusaurus build / docs-site link check) jobs are unchanged.

## Implementation order (land it green)

1. Add `cspell.json`, run, build/curate the word allowlist, fix real typos.
2. Add `.markdownlint-cli2.jsonc`, run `--fix`, hand-fix the rest, tune rules.
3. Add the frontmatter script; confirm/repair `description:` on all docs-site
   pages.
4. Add `lychee.toml`; run lychee locally/in a draft, fix broken links, build
   the exclude list.
5. Add root `package.json` deps + scripts; commit root `package-lock.json`.
6. Add the CI jobs + path filter + `CI Success` wiring **last**, so the gate
   lands already-passing.

## Risks & mitigations

- **Large first-run violation volume** (~75+ files): handled by the
  green-before-CI ordering and iterative allowlist curation.
- **External link flakiness**: tuned lychee config; scheduled-job fallback.
- **Root `npm ci` with a near-empty current lockfile**: regenerate and commit
  `package-lock.json` when adding devDeps.
- **Node deps at root vs. CLAUDE.md "no local installs"**: checks are CI-only;
  configs at root, deps installed only in the CI runner.

## Verification

- All four checks pass locally (via `npx` / `npm run docs:lint` + lychee) before
  CI is wired.
- A trial PR shows `lint-markdown` and `link-check` running and green; both
  appear in the `CI Success` summary.
- Introducing a deliberate typo / broken link in a draft makes the relevant
  job fail (gate proven to work).
