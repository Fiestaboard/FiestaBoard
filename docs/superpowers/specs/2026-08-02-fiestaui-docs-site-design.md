# Design: Re-skin the docs site (`docs-site/`) on FiestaUI

**Date:** 2026-08-02
**Branch:** `worktree-fiestaui-docs-site`
**Source of truth:** `~/Desktop/design_handoff_fiestaboard_site/` — `README.md` +
`FiestaboardSite.dc.html` (homepage) + `FiestaboardDocs.dc.html` (docs shell).

## Goal

Re-skin `fiestaboard.app` (Docusaurus 3.9.2) so the marketing homepage and the
docs shell use **`@fiestaboard/ui` (FiestaUI)** — the same components, tokens, and
typography as the FiestaBoard web app. **Structure and copy stay as they are
today; only the visual layer and a few interactive touches change.**

## Reality check (differs from the handoff's stated recipe)

The handoff was written against assumptions that don't hold for the real package;
these three findings drove the architecture:

1. **`@fiestaboard/ui` is not on npmjs** (it publishes to GitHub Packages) and its
   `dist/` is **gitignored** (built, not committed). So a plain
   `npm install @fiestaboard/ui` fails in CI/deploy.
2. **`theme.css` is tokens-only.** FiestaUI components emit Tailwind v4 utility
   class strings that the *consumer* must compile, with a **mandatory `@source`**
   scan of the package. Docusaurus ships no Tailwind. (Handoff's "no Tailwind
   build needed" is false for the real package.)
3. The CSS export is **`@fiestaboard/ui/theme.css`** (not `styles.css`) and dark
   mode is the **`.dark` class** (not `[data-theme]`).

## Architecture

### 1. Dependency: vendored tarball
`@fiestaboard/ui` is built (`npm run build`) and packed (`npm pack`) into
`docs-site/vendor/fiestaboard-ui-1.1.0.tgz`, referenced as
`"@fiestaboard/ui": "file:./vendor/fiestaboard-ui-1.1.0.tgz"`. CI/deploy install
it with **no registry or token**. Peer deps satisfied by docs-site:
`react`/`react-dom` ^19 (present), `lucide-react` bumped to `^1.23.0`,
`tailwindcss` ^4 added.

### 2. Tailwind v4 — precompiled ahead of Docusaurus
FiestaUI ships tokens only; its components emit Tailwind utility class strings we
must compile, with a **mandatory `@source`** scan of the package. We do NOT run
Tailwind inside Docusaurus's webpack PostCSS pipeline: that pipeline silently
drops `@source` scans into `node_modules`, so the DS utilities never generated
(verified — only generic utilities compiled, no `bg-brand-emphasis`). Instead a
prebuild step (`scripts/build-fiestaui-css.mjs`, wired via `prebuild`/`prestart`)
compiles `src/css/fiestaui.src.css` → `src/css/fiestaui.generated.css` with
`@tailwindcss/postcss` given an explicit input path, which resolves `@source`
deterministically. Docusaurus loads the generated plain CSS via `customCss`.

**Preflight** is omitted (only the Tailwind `theme` + `utilities` layers are
imported) so the base reset never clobbers Infima's docs typography. A guard in
the script fails the build if `bg-brand-emphasis` is missing from the output.

### 3. Theme sync — pure CSS, no JavaScript
FiestaUI's dark mode is class-based (`.dark`), Docusaurus signals dark via
`data-theme="dark"`. Rather than sync a `.dark` class in JS (a swizzled `Root`
using a MutationObserver hit a hydration race — the initial sync clobbered the
class, so returning dark-mode users loaded with light tokens), the prebuild
post-processes the generated CSS so FiestaUI's two dark selector forms — the
token block `.dark{…}` and per-utility `…:is(.dark *)` — ALSO match
`[data-theme="dark"]`. Docusaurus's native toggle then drives the DS tokens with
zero JavaScript, no `.dark` class, no hydration race, and no flash.
`prefers-color-scheme` is respected by Docusaurus. Verified: stored `theme=dark`
renders dark tokens on first load with no interaction.

### 4. Infima → FiestaUI token bridge (`src/css/custom.css`)
Re-point the Infima variables at DS tokens (`--background`, `--foreground`,
`--brand`, `--border`, `--radius`, `--font-geist-sans`, …). Per the handoff this
alone re-skins navbar, sidebar, TOC, and every docs page (~80% of the result).
Existing accessibility-oriented orange overrides are replaced by the DS `--brand`
token set.

## Homepage (`src/pages/index.tsx` + `HomepageFeatures`)

Rebuild with FiestaUI components, section order unchanged (hero → 6 feature cards
→ What's New → See It in Action → plugin grid → CTA → footer already lives in
Docusaurus theme config). Uses `Button`, `Badge`, `Alert`, `FiestaLogo`,
`StaticBoardDisplay`, `ScaledBoardDisplay`, `TextLink`, `Code`. All copy, links,
and feature images are reused verbatim from today's homepage.

- **Hero:** two columns; left = eyebrow badge + mono subline + H1 + body + two
  `Button`s (`brand` / `outline`, via `asChild` + Docusaurus `<Link>`); right =
  animated `StaticBoardDisplay`.
- **Split-flap animation:** 3 messages cycling every 7000ms; per-char scramble at
  45ms settling `4 + c*0.8 + r*1.6 + rand(0,7)` frames (ported from the design's
  `flipTo`). **Respect `prefers-reduced-motion`:** skip scramble, cross-fade
  instead. Client-only (`useEffect`); board render wrapped in `<BrowserOnly>`
  because FiestaUI board components touch browser APIs and Docusaurus SSRs.
- **Plugin grid:** 9 cards render **live** `ScaledBoardDisplay` (not screenshots)
  using the sample messages from `FiestaboardSite.dc.html`.
- **Screenshots ("See It in Action"):** swap `/img/light/*` ↔ `/img/dark/*` with
  the resolved theme (replaces today's manual Light/Dark tabs & lightbox).

## Docs shell (swizzles + MDX)

Prefer `--wrap` swizzles (survive upgrades). Most of the docs look comes from the
token bridge (§4); we only add:
- **MDX mapping** (`src/theme/MDXComponents`): admonitions → FiestaUI `Alert`,
  inline code → `Code`, tables → FiestaUI `Table` set, where it improves parity
  without breaking Markdown authoring.
- Sidebar item, TOC, and prev/next accents via the token bridge + minimal CSS to
  match the reference (active pill `--accent`, TOC left-border `--primary`,
  card hover `--ring`).

## Non-goals / YAGNI
- No content, route, or copy restructuring.
- No change to versioned docs, blog, stats, or plugins-directory data.
- No publishing pipeline for `@fiestaboard/ui` (tarball is self-contained); a
  follow-up can switch `file:` → a published version later.

## Verification
- `npm run build` (Docusaurus) succeeds with `onBrokenLinks: throw`.
- `npm run typecheck` and `npm run lint` / `format:check` pass.
- Manual: `npm start`, screenshot homepage + a docs page in light **and** dark,
  compare against the two `.dc.html` references; confirm split-flap animates and
  honors reduced-motion; confirm no Infima-body regression.

## Risks
- **Preflight bleed** into docs body — mitigated by disabling/scoping preflight;
  verify docs typography visually.
- **SSR** of FiestaUI board/WebGL (`ogl`) components — mitigated with
  `<BrowserOnly>`.
- **Tarball staleness** — documented regen step (`npm run build && npm pack` in
  `../FiestaUI`) in `docs-site/vendor/README.md`.
