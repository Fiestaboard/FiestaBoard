# Vite 8 Migration (finish issue #1381) — Design

**Date:** 2026-07-25
**Status:** Approved (user), executing

## Summary

Issue #1381 tracks migrating the web UI to react-router 8 + vite 8 after
Dependabot's #1366 majors were backed out for breaking the `/schedule` route.
React Router 8 has since landed on `main` via PR #1422 (`react-router@8.3.0`
and all `@react-router/*@8.3.0`, with a committed `web/package-lock.json`).
This work finishes the issue: bump vite to 8 and `@vitejs/plugin-react` to 6,
raise the web CI jobs from Node 20 to Node 22, drop the Dependabot major-bump
ignores, and — critically — verify against the running app that the
`/schedule` reload loop from #1366 does not reproduce.

## Decisions (from brainstorming)

- **CI Node version:** bump web jobs from `'20'` to `'22'` (react-router 8
  requires Node ≥ 22.22; smallest compliant change, LTS until 2027). Not 26,
  despite the Dockerfile shipping Node 26.
- **Docs jobs stay on Node 20:** `lint-docs`, `build-docs` (`ci.yml`) and
  `docs.yml` build the Docusaurus site, not the RR8 web app.
- **Verification uses the repo's existing suites** — no bespoke one-off
  checks. Web lint (eslint + `prettier --check`), web unit tests, the full
  Playwright E2E suite, and the production Docker image build must all pass
  locally before pushing, mirroring what CI runs.
- **Isolation:** all work happens in the `feat-vite8-migration` worktree with
  its own prod image on port 4499, never against the shared dev container on
  4420.

## Changes

### 1. Dependency bumps (`web/package.json` + lockfile)

- `vite`: `^7.3.6` → `^8.x` (latest 8)
- `@vitejs/plugin-react`: `^5.2.0` → `^6.x` (consumed only transitively —
  it is deliberately absent from `vite.config.ts` because RR handles Fast
  Refresh; Storybook's `@storybook/react-vite` is the consumer)
- Regenerate `web/package-lock.json` inside a Node 22+ container using
  `npm install --legacy-peer-deps` (known peer-conflict quirk in this repo).
- Pre-check: confirm `@storybook/react-vite@10.4.6` and `@react-router/dev@8`
  accept vite 8 as a peer (the current lockfile already shows
  `vite ^7.0.0 || ^8.0.0` ranges).

### 2. CI Node bumps (`.github/workflows/`)

`node-version: '20'` → `'22'` with a short comment referencing #1381, on:

- `ci.yml`: `lint-web`, `test-ui` (both setup-node steps under it, which
  cover the UI test and a11y steps)
- `integration-tests.yml`: the web E2E job
- `release.yml`: the version-sync (`prep`) job

### 3. Dependabot (`.github/dependabot.yml`)

Delete the four `ignore` entries (`react-router`, `@react-router/*`, `vite`,
`@vitejs/plugin-react`) and their explanatory comment so future majors flow
through Dependabot again.

## Verification plan

The #1366 failure mode was a live-browser reload loop on `/schedule`
(suspected vite 8 chunk-manifest change × the lazy `react-big-calendar`
import in `app/routes/schedule.tsx`, possibly interacting with the VitePWA
`navigateFallback`). Verification therefore runs against the real app, plus
every existing repo validation:

1. **Build** the branch's production Docker image; run it on port 4499.
2. **Manual drive (Playwright):** load `/schedule`, confirm the Schedule
   heading renders with no re-navigation loop; switch to calendar view to
   force the lazy `@/components/schedule` chunk import; check the browser
   console for chunk-load errors.
3. **Existing web validations, run in-container as CI does:**
   - `npm run lint` and `npx prettier --check` (lint-web equivalent)
   - web unit tests (`npm test`)
   - full Playwright E2E suite against :4499, with special attention to the
     schedule specs that failed in #1366 (known flakes per repo memory:
     rerun-failed clears them; consistent failures are real)
4. **Python side:** untouched by this change; CI runs it on the PR. No local
   Python suite run is required unless the Docker build surfaces an issue.

## Error handling / rollback

If the `/schedule` loop (or any consistent E2E failure) reproduces under
vite 8 and the fix is not tractable within this effort: ship only the CI
Node-22 bump, keep the Dependabot ignores, and report the diagnosis on
issue #1381. No partial dep bump lands.

## Out of scope

- Storybook major bumps or any other dependency updates
- Docs-site Node versions or tooling
- Any behavioral change to the schedule feature itself
