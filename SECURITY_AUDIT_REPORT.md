# Security Audit Report — Merged PRs #310–#325

**Audit Date:** 2026-02-28
**Auditor:** Automated Security Review (Cloud Agent)
**Scope:** PRs 325, 324, 323, 321, 320, 319, 318, 317, 316, 315, 314, 313, 312, 311, 310

---

## PR-by-PR Analysis

### PR #325 — chore: increase test coverage to 80% across platform, plugins, and UI
**Security Issues Found:** Yes (1 issue)

| # | Severity | Type | File | Description |
|---|----------|------|------|-------------|
| 1 | **Low** | Docker Security — Running as root (`chown -R`) | `plugins/home_assistant/__init__.py` (line removal) | The PR removes a dead-code `if not data: return None` guard in `get_formatted_display()`. After removal, if `_cache` is set to an empty dict `{}`, the code proceeds to call `.get("entities", {})` on it, which is safe but changes the previous defensive behavior. This is a **code quality** note rather than a direct vulnerability, but could surface unexpected behavior if cache state is malformed. |

> **Overall:** This PR is predominantly test code. All API keys used in tests are clearly mock/test values (`"test_key"`, `"test_token"`, `"k"`). No real credentials, no injection risks, no unsafe operations. The CI change to use `codecov/codecov-action@v5` with `${{ secrets.CODECOV_TOKEN }}` is properly handled via GitHub Secrets. The `--fail-under=80` coverage gate is a positive security practice.

**Verdict:** No significant security issues found.

---

### PR #324 — Add staggered card fade-in animation to integrations page
**Security Issues Found:** No

> This PR adds UI animation components (BlurText, CountUp, SpotlightCard, ShinyText, FadeContent, DecryptedText, PageFadeWrapper). All are purely client-side React components with no network calls, no `eval()`, no `dangerouslySetInnerHTML`, no external data injection points. The `DecryptedText` component does string character randomization but uses no unsafe APIs.

**Verdict:** No security issues found.

---

### PR #323 — Add Aurora WebGL background to setup wizard
**Security Issues Found:** No

> Adds an `ogl` (WebGL) dependency and Aurora shader component for visual effects. The WebGL shaders are hardcoded GLSL strings with no user input interpolation. The `docker-compose.dev.yml` changes add volume mounts and `WATCHPACK_POLLING=true` for dev hot-reload — standard development practices. The `start-dev.sh` runs `npm install` inside the container, which is expected for dev mode. The `entrypoint.sh` change adds `chown -R appuser:appuser /app/web/.next` for dev mode bind mounts — this runs as root in the entrypoint before dropping to appuser, which is the standard gosu pattern and is acceptable.

**Verdict:** No security issues found.

---

### PR #321 — Fix CI badge showing failing due to concurrency cancellation on main
**Security Issues Found:** No

> Single-line change: `ci-${{ github.event.pull_request.number || github.ref }}` → `ci-${{ github.event.pull_request.number || github.sha }}`. This changes the CI concurrency group key from branch ref to commit SHA for non-PR builds. No security implications — both values are GitHub-provided context variables, not user-controlled inputs susceptible to script injection.

**Verdict:** No security issues found.

---

### PR #320 — Show current time indicator line in schedule calendar
**Security Issues Found:** No

> CSS-only changes to `calendar.css` showing a red time indicator line. No JavaScript, no API changes, no data handling. Version bump in `package-lock.json`.

**Verdict:** No security issues found.

---

### PR #319 — Enable dimming overlay on integration configuration tray
**Security Issues Found:** No

> Single-line change removing `modal={false}` from a Sheet component, restoring default modal behavior with a dimming overlay. No security implications.

**Verdict:** No security issues found.

---

### PR #318 — docs: add screenshot references to plugin SETUP.md files
**Security Issues Found:** No

> Adds markdown image references (`![Description](./image.png)`) to various plugin SETUP.md files. All image paths are relative within plugin `docs/` directories. No external URLs, no script injection vectors.

**Verdict:** No security issues found.

---

### PR #317 — Fix weekly schedule calendar: Saturday midnight rollover wraps to Sunday
**Security Issues Found:** No

> Client-side schedule calendar logic improvements. Adds Saturday-to-Sunday midnight rollover handling. The `schedule-event.tsx` change accesses `resource.originalSchedule.start_time` and `resource.originalSchedule.end_time` to display original time ranges — these are schedule data from the app's own API, not user-controlled HTML injection vectors. Uses `date-fns` `format()` for time formatting, which is safe.

**Verdict:** No security issues found.

---

### PR #316 — Fix 100+ factual errors across all documentation
**Security Issues Found:** No

> Massive documentation-only PR correcting outdated information: API endpoint paths (`/plugins` → `/api/plugins`), button labels, plugin counts, variable names, environment variable names, and instructions. No code logic changes. No credentials or sensitive data exposed. All example values use placeholders (`your_google_key`, `your_ha_token`, etc.).

**Verdict:** No security issues found.

---

### PR #315 — Split midnight-rollover schedule events at day boundary
**Security Issues Found:** No

> Client-side calendar logic to split midnight-spanning schedule events into evening and morning parts. Adds `isMidnightSplit` and `splitPart` metadata to calendar events. The `schedule-calendar-view.tsx` properly constrains drag behavior for split events (disabling drag, constraining resize boundaries). No server-side changes, no API modifications, no injection risks.

**Verdict:** No security issues found.

---

### PR #314 — Sort pages alphabetically at the API layer
**Security Issues Found:** No

> Changes `pages.sort(key=lambda p: p.created_at)` to `pages.sort(key=lambda p: p.name.lower())` in `src/pages/storage.py`. This is a simple sort order change on in-memory data. The `.lower()` call is safe on Python strings. No injection risk, no path traversal, no auth changes.

**Verdict:** No security issues found.

---

### PR #313 — Fix schedule calendar events not rendering when spanning midnight
**Security Issues Found:** No

> Initial implementation of midnight rollover handling in `schedule-calendar.ts` using `date-fns` `addDays()`. Adds new test file `schedule-calendar.test.ts`. Pure client-side date arithmetic logic. No security concerns.

**Verdict:** No security issues found.

---

### PR #312 — Speed up live edit preview and restore board on exit
**Security Issues Found:** No

> Reduces debounce timers from 300ms/500ms to 150ms/200ms for faster live preview. Adds `forceRefresh()` API call on component unmount to restore board display. The `api.forceRefresh()` calls `fetchApi("/force-refresh", { method: "POST" })` — this is an internal API call to the app's own backend with no user-supplied parameters, so no injection risk. The `liveOutputEnabledRef` pattern using `useRef` + `useEffect` cleanup is a standard React pattern.

**Verdict:** No security issues found.

---

### PR #311 — Fix ARM64 build hanging: correct runner label ubuntu-24.04-arm
**Security Issues Found:** No

> Single-line change: `runner: ubuntu-24.04-arm64` → `runner: ubuntu-24.04-arm` in the GitHub Actions workflow. Corrects a runner label. No security implications.

**Verdict:** No security issues found.

---

### PR #310 — Replace QEMU-emulated ARM builds with native ARM runners
**Security Issues Found:** No

> Restructures the release workflow from a single multi-platform build to a matrix strategy with per-platform native runners. Removes QEMU emulation. Adds a `merge` job to create multi-platform manifest. Docker Hub credentials (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`) are properly accessed via `${{ secrets.* }}` — no hardcoded credentials. The `printf 'fiestaboard/fiestaboard@sha256:%s ' *` pattern in the manifest merge step uses digest filenames from the build step, not user input. The workflow structure follows Docker's recommended multi-platform build pattern.

**Verdict:** No security issues found.

---

## Summary of All Findings

### Statistics
- **Total PRs reviewed:** 15
- **PRs with security issues:** 0
- **Total security issues found:** 0

### Detailed Summary

| PR | Title | Issues |
|----|-------|--------|
| #325 | Increase test coverage to 80% | No security issues found |
| #324 | Staggered card fade-in animation | No security issues found |
| #323 | Aurora WebGL background | No security issues found |
| #321 | Fix CI badge concurrency | No security issues found |
| #320 | Current time indicator in calendar | No security issues found |
| #319 | Dimming overlay on config tray | No security issues found |
| #318 | Screenshot references in SETUP.md | No security issues found |
| #317 | Saturday midnight rollover fix | No security issues found |
| #316 | Fix 100+ documentation errors | No security issues found |
| #315 | Split midnight-rollover events | No security issues found |
| #314 | Sort pages alphabetically | No security issues found |
| #313 | Fix midnight-spanning events | No security issues found |
| #312 | Speed up live edit + restore board | No security issues found |
| #311 | Fix ARM64 runner label | No security issues found |
| #310 | Native ARM runners | No security issues found |

### Security Checklist Results

| Check | Result |
|-------|--------|
| Hardcoded secrets/API keys/tokens | ✅ None found — all test values use mock/placeholder keys |
| Sensitive personal information | ✅ None found — coordinates use well-known landmarks (SF: 37.7749, -122.4194) |
| SQL injection | ✅ N/A — no SQL queries in any diff |
| Cross-site scripting (XSS) | ✅ None found — no `dangerouslySetInnerHTML`, no raw HTML injection |
| Command injection | ✅ None found — no `exec()`, `eval()`, or shell command construction with user input |
| Path traversal | ✅ None found |
| Insecure deserialization | ✅ None found |
| Authentication/authorization bypass | ✅ None found — no auth logic changes |
| Exposed sensitive endpoints | ✅ None found |
| Insecure cryptographic practices | ✅ N/A — no crypto operations |
| SSRF vulnerabilities | ✅ None found |
| Unsafe file operations | ✅ None found |
| Docker security issues | ✅ Acceptable — entrypoint uses gosu pattern correctly |
| CI/CD pipeline security | ✅ Secrets properly handled via `${{ secrets.* }}` |
| Dependency vulnerabilities | ✅ No known vulnerable dependencies added |
| CORS misconfigurations | ✅ None found |
| Unsafe eval() usage | ✅ None found |
| Information disclosure in errors | ✅ None found |
| Insecure direct object references | ✅ None found |
| Missing input validation | ✅ None found — validation logic preserved or improved |

### Overall Assessment

**Risk Level: LOW**

All 15 PRs reviewed are clean from a security perspective. The changes consist of:
- Test coverage improvements with properly mocked credentials
- UI animation/visual enhancements (client-side only)
- Documentation corrections
- Calendar/scheduling logic fixes (client-side)
- CI/CD workflow improvements
- Build infrastructure changes

No actionable security vulnerabilities were identified across any of the reviewed pull requests.
