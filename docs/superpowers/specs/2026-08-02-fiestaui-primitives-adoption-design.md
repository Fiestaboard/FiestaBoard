# FiestaUI Primitive Adoption — Design

**Date:** 2026-08-02
**Status:** Approved
**Scope:** Two repos — `Fiestaboard/FiestaUI` (new primitives) and `Fiestaboard/FiestaBoard` (full migration + enforcement)

## Goal

Eliminate essentially all raw HTML from FiestaBoard's web app code (`web/app/**`, `web/src/**`). Every element the app renders comes from `@fiestaboard/ui` — either an existing component, a new primitive added by this project, or the typed `Box` escape hatch. An ESLint rule makes the state permanent.

## Current state (measured on `fiestaui-upgrade` @ v1.0.1, 2026-08-02)

- 98 files already import `@fiestaboard/ui`; the local `web/src/components/ui/` dir is down to three app-specific components (`sonner`, `time-picker`, `timezone-picker`).
- FiestaUI v1.0.x already exports layout primitives `Flex`, `Stack`, `Grid` (cva variants, enumerated gap scale) plus the `Page*` chrome, used in ~10 routes.
- Remaining raw HTML in app code (excluding tests/stories): ~1,119 `div`, ~297 `span`, ~242 `p`, then a tail: 32 `code`, 20 `a`, 14 `li`, 11 `strong`, 11 `h3`, 10 `ul`, 9 `h2`, 8 `form`, 7 `table` (+ scattered `section`, `img`, `dl`, `ol`, `h4`, `nav`). Spread over ~100 files: 38 `src/components` top-level, 25 `src/components/settings`, 13 `app/routes`, 14 tiptap editor, ~10 misc (wizard, schedule, transitions, plugin-settings).

## Decisions (with rationale)

1. **Full sweep, upstream-first.** Extend FiestaUI with the missing primitives, then migrate everything. Layout-only was rejected: typography is a third of the surface and the user wants ~zero custom HTML.
2. **Normalize while migrating.** Primitives expose a small set of blessed variants; near-miss styles snap to the nearest variant (e.g. `space-y-3` → `Stack gap="3"`, `text-[13px]` → `size="sm"`). Small intentional visual diffs are reviewed per wave. Strict pixel parity was rejected — it would encode today's inconsistencies into the design system.
3. **ESLint ban + allowlist**, error severity, landing with the final wave. Convention-only drifts, especially with agent-written PRs.
4. **Epic + wave PRs via agents**, straight into `main` (no integration branch — waves are independent and individually green).
5. **Semantic primitive set + Box** (rejected: one polymorphic Box for everything — weaker semantics, harder to lint, off-style for this codebase).

## Part 1 — FiestaUI additions

New components in `src/components/ui/`, matching the existing cva-variant house style (enumerated variants so every emitted class is statically visible to the Tailwind v4 scanner). Each ships with a Storybook story and VRT baseline. Released as a **minor**; the Downstream Upgrade pipeline delivers it to FiestaBoard automatically.

| Primitive | Renders | Variants | Replaces |
|---|---|---|---|
| `Text` | `p` or `span` via `as` (default `p`) | `size` xs/sm/base/lg · `tone` default/muted/destructive/success · `weight` normal/medium/semibold | ~540 `p`/`span` |
| `Heading` | `h2`–`h4` via `level` | `size` decoupled from level, default = v1.0.0 unified title typography | ~20 headings (`h1` remains `PageHeader`'s job) |
| `Code` | `code` | inline chip style | 32 uses |
| `TextLink` | `a` | canonical link + focus-ring recipe | 20 uses |
| `List` / `ListItem` | `ul`/`ol` via `as` | `marker` none/disc/decimal · `gap` scale | ~25 uses |
| `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` | table elements | house table style | 7 tables (settings/debug) |
| `Box` | `div`/`section`/`main`/`nav`/`header`/`footer`/`form` via `as` | none — unstyled, `className` pass-through | genuinely custom layout: positioned overlays, portal hosts, canvas wrappers |

`Box` is what keeps "zero raw HTML" honest: anything that fits no styled primitive uses `Box` rather than a lint-disable comment.

Suggested PR slicing upstream: ① `Text`/`Heading`/`Code`/`TextLink` ② `List`/`Table` set ③ `Box` (+ export barrel, stories, VRT).

## Part 2 — FiestaBoard migration

- Layout `div`s → `Flex`/`Stack`/`Grid`; typography → `Text`/`Heading`; tail → `Code`/`TextLink`/`List`/`Table`; remainder → `Box`.
- Semantics preserved: primitives render real `p`/`ul`/`table` elements, so the accessibility tree is unchanged where intended; the a11y (light/dark) and Playwright suites are the regression net.
- Each wave PR includes before/after screenshots of affected screens (normalization diffs are intentional and reviewed).
- Recurring patterns that fit no primitive get logged on the epic; if a pattern recurs, it becomes a FiestaUI variant, not a repeated one-off `className`.

### Enforcement

`react/forbid-elements` (severity **error**) in `web/eslint` config, scoped to `app/**` and `src/**` (tests/stories excluded), banning: `div span p h1 h2 h3 h4 h5 h6 ul ol li section main header footer nav form table thead tbody tr td th a code strong`. Each entry's message names the replacement (e.g. `div → Flex/Stack/Grid/Box`, `strong → Text weight="semibold"`). Allowlist (stays raw, semantic leaves with no primitive counterpart): `svg` and children, `canvas`, `iframe`, `img`, `br`, `em`, `small`, `kbd`, `pre`, `figure`, `dl`, `dt`, `dd`. The three local ui components migrate like everything else. The rule lands **with the final wave** so CI never lies red mid-migration.

## Part 3 — Delivery

GitHub epic in FiestaBoard with sub-issues:

| # | Wave | Files (approx) |
|---|---|---|
| 0 | FiestaUI primitives (3 upstream PRs → minor release → evergreen PR delivers) | — |
| 1 | `app/routes` + app root | 13 |
| 2 | `src/components` top-level, half A | ~19 |
| 3 | `src/components` top-level, half B | ~19 |
| 4 | `src/components/settings` | 25 |
| 5 | tiptap template editor | 14 |
| 6 | wizard/schedule/transitions/plugin-settings/misc + local ui trio + **ESLint rule flip** | ~12 |

One agent per wave, each PR runs full web CI plus screenshot review by the maintainer. Waves 1–6 depend on wave 0 having landed in FiestaBoard via the upgrade PR.

## Error handling / risks

- **Tailwind class scanning:** primitives use enumerated cva variants only — no dynamic class construction — so the `@source` contract with the package keeps working.
- **Visual drift beyond intent:** normalization is bounded to the blessed variant scales; anything that can't snap cleanly is escalated on the epic rather than eyeballed.
- **Downstream pipeline coupling:** wave 0 rides the evergreen upgrade PR (`fiestaui-upgrade`); if its fix-loop mislabels (`upgrade-blocked` false positives from the flaky baseline check — known issue, see below), the bump can be verified and merged manually.
- **Known follow-up (out of scope):** the Downstream Upgrade workflow's baseline validation intermittently fails on main's full-suite vitest flakes and skips fix attempts / mislabels the PR; it should filter known flakes or rerun-failed. Tracked separately in FiestaUI.

## Testing

- FiestaUI: unit/story coverage per primitive + VRT baselines; `npm run lint/typecheck/build/build-storybook` gates.
- FiestaBoard: existing vitest + Playwright + a11y suites per wave; no new test infrastructure required. The ESLint rule is itself the permanent regression test for the "no raw HTML" invariant.
