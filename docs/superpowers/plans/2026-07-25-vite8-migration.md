# Vite 8 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish issue #1381 — bump the web UI to vite 8 + @vitejs/plugin-react 6, raise web CI jobs to Node 22, drop the Dependabot major ignores, and prove the #1366 `/schedule` reload loop does not reproduce.

**Architecture:** Pure dependency/config migration — no product code changes expected. All npm work happens inside Docker containers (CLAUDE.md forbids local installs). Verification reuses the repo's existing suites exactly as CI runs them, against a branch-built production image on port 4499, isolated from the shared dev container on 4420.

**Tech Stack:** vite 8.1.5, @vitejs/plugin-react 6.0.4, react-router 8.3.0 (already on main), Node 22 containers, Playwright E2E via `mcr.microsoft.com/playwright` container.

## Global Constraints

- Branch: `feat-vite8-migration` in worktree `/Users/jeffre/workspace/FiestaBoard/.claude/worktrees/feat-vite8-migration`
- NEVER run npm/node on the host — every npm command runs in a Docker container
- All lockfile/install operations use `--legacy-peer-deps` (pre-existing eslint-10 vs eslint-plugin-jsx-a11y peer conflict)
- Never touch the shared dev container or port 4420; this branch's stack uses port 4499 and compose-free `docker run` with a dedicated network `fiesta-vite8-net`
- CI Node bump target is `'22'` (not 24/26); docs jobs (`lint-docs`, `build-docs`, `docs.yml`) stay on `'20'`
- `@vitejs/plugin-react` must stay OUT of `web/vite.config.ts` (RR8 owns Fast Refresh; Storybook is the only consumer)
- Rollback rule: if `/schedule` consistently fails under vite 8 and the fix is not tractable, ship only the CI Node bump and keep the Dependabot ignores

---

### Task 1: Bump deps and regenerate the lockfile

**Files:**
- Modify: `web/package.json` (devDependencies `vite`, `@vitejs/plugin-react`)
- Modify: `web/package-lock.json` (regenerated, not hand-edited)

**Interfaces:**
- Produces: a lockfile that resolves `vite@8.1.5` and `@vitejs/plugin-react@6.0.4`, consumed by every later task's `npm ci`.

- [ ] **Step 1: Edit `web/package.json`** — change `"vite": "^7.3.6"` → `"vite": "^8.1.5"` and `"@vitejs/plugin-react": "^5.2.0"` → `"@vitejs/plugin-react": "^6.0.4"`.

- [ ] **Step 2: Regenerate the lockfile in a Node 22 container** (lockfile-only, so no `node_modules` lands on the host mount):

```bash
docker run --rm -v "$PWD/web":/app -w /app node:22 \
  npm install --legacy-peer-deps --no-audit --package-lock-only
```

- [ ] **Step 3: Verify resolution** — expect `8.1.5` and `6.0.4`:

```bash
grep -A2 '"node_modules/vite"' web/package-lock.json | head -3
grep -A2 '"node_modules/@vitejs/plugin-react"' web/package-lock.json | head -3
```

Also confirm no second vite major snuck in: `grep -c '"vite": "^7' web/package-lock.json` should be 0 for top-level resolution (transitive peer *ranges* like `^7.0.0 || ^8.0.0` are fine).

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "chore(deps): bump vite to 8.1.5 and @vitejs/plugin-react to 6.0.4 (#1381)"
```

---

### Task 2: Run every CI web validation in a Node 22 container

**Files:**
- Possibly modify: `web/vite.config.ts` (only if vite 8 breaks config API); any file eslint/tsc/vitest flags

**Interfaces:**
- Consumes: Task 1's lockfile.
- Produces: a named volume `vite8_node_modules` with installed deps, reused by Task 4's Playwright run if helpful.

- [ ] **Step 1: Install deps in a persistent container volume** (mirrors CI's `npm ci --legacy-peer-deps --no-audit`; the named volume keeps `node_modules` off the host):

```bash
docker run --rm -v "$PWD/web":/app -v vite8_node_modules:/app/node_modules -w /app node:22 \
  npm ci --legacy-peer-deps --no-audit
```

- [ ] **Step 2: ESLint** (CI `lint-web`): same container pattern, `npm run lint`. Expected: exit 0.

- [ ] **Step 3: Prettier check** (CI `lint-web`): `npm run format:check`. Expected: exit 0. Do NOT reformat unrelated files if it fails — only files this branch touched may be fixed; pre-existing drift gets reported, not fixed.

- [ ] **Step 4: Typecheck** (repo validation): `npm run typecheck` (`react-router typegen && tsc --noEmit`). Expected: exit 0.

- [ ] **Step 5: Unit tests with coverage** (CI `test-ui`): `npm run test:coverage`. Expected: all pass. Note vitest bundles its own vite internally; failures here are more likely env/jsdom than vite 8.

- [ ] **Step 6: Storybook production build** (CI `a11y-tests` build step — this is what actually exercises `@vitejs/plugin-react@6` via `@storybook/react-vite`): `npm run build-storybook`. Expected: build completes.

- [ ] **Step 7: Fix-and-rerun loop** — if any step fails, use superpowers:systematic-debugging: read the actual error, check the vite 8 / plugin-react 6 changelogs (context7) before patching, apply the minimal fix, rerun the failed step. Commit each real fix with its own message.

- [ ] **Step 8: Commit** any config fixes (skip if none): `git add -A && git commit -m "fix(web): vite 8 config compatibility"`.

---

### Task 3: Build the production image and prove `/schedule` works

**Files:**
- None expected (Dockerfile unchanged); this task is pure verification.

**Interfaces:**
- Produces: image `fiestaboard:vite8-e2e`, network `fiesta-vite8-net`, running app container `fiestaboard-vite8` on `127.0.0.1:4499` — consumed by Task 4.

- [ ] **Step 1: Build the runtime image** (exercises `react-router build` under vite 8 inside the Dockerfile UI stage):

```bash
docker build --target runtime -t fiestaboard:vite8-e2e .
```

Expected: build succeeds; watch the UI build stage output for vite 8's build summary.

- [ ] **Step 2: Start mocks + app on a dedicated network** (pencil-e2e recipe — no host-port collisions with other sessions except 4499):

```bash
docker network create fiesta-vite8-net
docker run -d --name fiestaboard-mock-board --network fiesta-vite8-net \
  --network-alias fiestaboard-mock-board \
  -v "$PWD/integration-tests/mock-board":/srv -w /srv python:3.12-slim \
  python server.py
docker run -d --name fiestaboard-mock-cloud --network fiesta-vite8-net \
  --network-alias fiestaboard-mock-cloud \
  -e PORT=9200 -e ROWS=6 -e COLS=30 \
  -v "$PWD/integration-tests/mock-cloud":/srv -w /srv python:3.12-slim \
  python server.py
docker run -d --name fiestaboard-vite8 --network fiesta-vite8-net \
  -p 127.0.0.1:4499:3000 \
  -e BOARD_API_MODE=local -e BOARD_HOST=fiestaboard-mock-board \
  -e BOARD_LOCAL_API_KEY=test_key -e PRODUCTION=false \
  -e FIESTABOARD_AUTH_ENABLED=false \
  fiestaboard:vite8-e2e
```

(Check `integration-tests/mock-board/server.py` for its port/env conventions first; CI runs it bare with defaults. Adjust `BOARD_PORT`-style env on the app container if the server defaults differ.)

- [ ] **Step 3: Health check**: `curl -fsS http://127.0.0.1:4499/api/health` → HTTP 200 within ~30s of start.

- [ ] **Step 4: Drive `/schedule` in a real browser** (Playwright MCP tools against `http://127.0.0.1:4499/schedule`):
  - The `Schedule` heading must render; the page must NOT re-navigate in a loop (the #1366 signature was repeating `commit → domcontentloaded → load`).
  - Toggle to calendar view — this forces the lazy `import("@/components/schedule")` chunk (react-big-calendar). The calendar grid must render.
  - Read the browser console: zero chunk-load / dynamic-import errors.
  - Reload the page once more (PWA `navigateFallback` check — stale index.html serving old hashed chunks was a suspect).

- [ ] **Step 5: If the loop reproduces** — apply superpowers:systematic-debugging: capture the failing chunk URL from the network log, compare against `build/client/assets` chunk names in the image, inspect the VitePWA precache manifest, and consult vite 8 + RR8 release notes before changing anything. If no tractable fix, invoke the rollback rule from Global Constraints.

---

### Task 4: Full existing Playwright E2E suite against the branch image

**Files:**
- None expected; verification only.

**Interfaces:**
- Consumes: Task 3's running stack (`fiestaboard-vite8` on `fiesta-vite8-net`).

- [ ] **Step 1: Check the pinned Playwright version**: `grep '"@playwright/test"' web/package.json` and use the matching `mcr.microsoft.com/playwright:v<version>-noble` image.

- [ ] **Step 2: Run the suite exactly as CI's main e2e matrix does** — `CI=true` activates the CI ignore list (screenshots, ai/mcp, auth specs — those need dedicated containers CI provides separately), `--workers=1` keeps one backend consistent:

```bash
docker run --rm --network fiesta-vite8-net \
  -v "$PWD/web":/work -w /work \
  -e CI=true -e BASE_URL=http://fiestaboard-vite8:3000 \
  mcr.microsoft.com/playwright:v<version>-noble \
  bash -c "npm ci --legacy-peer-deps --no-audit && npx playwright test --workers=1"
```

Expected: pass, modulo known flakes (multi-board delete, pages-edit, schedule-form select — per repo memory).

- [ ] **Step 3: Rerun any failures once**: `npx playwright test --last-failed --workers=1`. A failure that survives the rerun is real — debug it (systematic-debugging), fix, rerun. Schedule-spec failures get top priority; they are this migration's acceptance gate.

- [ ] **Step 4: Tear down**: stop/rm `fiestaboard-vite8`, `fiestaboard-mock-board`, `fiestaboard-mock-cloud`; `docker network rm fiesta-vite8-net`. Keep the image for reruns.

---

### Task 5: CI Node 22 bumps + Dependabot un-ignore

**Files:**
- Modify: `.github/workflows/ci.yml` (`lint-web` ~line 314, `test-ui` ~line 382, `a11y-tests` ~line 441 — the three web `node-version: '20'` entries; leave `lint-docs` ~353 and `build-docs` ~1007 alone)
- Modify: `.github/workflows/integration-tests.yml` (~line 72)
- Modify: `.github/workflows/release.yml` (~line 71, version-sync `prep` job)
- Modify: `.github/dependabot.yml` (delete the 4-entry `ignore` block + its comment)

**Interfaces:**
- Consumes: nothing; independent of Tasks 1–4 but lands in the same PR.

- [ ] **Step 1: Bump the five web `node-version` entries** from `'20'`/`"20"` to `'22'`/`"22"`, each with this comment above it:

```yaml
        # react-router 8 requires Node >= 22.22 (issue #1381); the Docker
        # image runs Node 26. Docs-site jobs intentionally stay on Node 20.
        node-version: '22'
```

- [ ] **Step 2: Remove the Dependabot ignores** — in `.github/dependabot.yml`, delete the `ignore:` key and all four entries (`react-router`, `@react-router/*`, `vite`, `@vitejs/plugin-react`) plus the two comment lines referencing #1381.

- [ ] **Step 3: Sanity-check YAML**: `python3 -c "import yaml,glob; [yaml.safe_load(open(f)) for f in ['.github/dependabot.yml','.github/workflows/ci.yml','.github/workflows/integration-tests.yml','.github/workflows/release.yml']]"` → no exception. Verify with `grep -n "node-version" .github/workflows/*.yml` that exactly the intended lines changed.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/integration-tests.yml \
  .github/workflows/release.yml .github/dependabot.yml
git commit -m "ci: bump web jobs to Node 22, re-enable RR/vite major bumps (#1381)"
```

---

### Task 6: PR and CI green

**Files:**
- None; process task.

- [ ] **Step 1: Push** `git push -u origin feat-vite8-migration`.

- [ ] **Step 2: Open the PR** against `main` with `gh pr create`, body summarizing: vite 8.1.5 + plugin-react 6.0.4 bump, local verification results (unit/lint/typecheck/storybook/E2E incl. `/schedule` proof), CI Node 22 bump, Dependabot un-ignore. Include `Closes #1381` and the standard Claude Code footer.

- [ ] **Step 3: Watch CI** (`gh pr checks --watch`). Debug any failure via its logs; known-flake E2E failures get one rerun before deeper investigation. Merge-queue markdown lint failures unrelated to this diff are pre-existing main issues (repo memory) — report, don't chase.

- [ ] **Step 4: After CI is green**, update the repo memory file `rr8-vite8-migration-blocked.md` to reflect that #1381's migration has landed (or is in review), so future sessions don't treat the majors as blocked.
