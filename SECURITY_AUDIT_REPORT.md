# Security Audit Report — Merged Pull Requests

**Audit Date:** 2026-02-28
**PRs Reviewed:** 309, 308, 307, 306, 305, 304, 303, 302, 301, 300, 299, 297, 296, 295, 294
**Auditor:** Automated Security Audit (Cloud Agent)

---

## Per-PR Analysis

### PR #309 — Fix release workflow race condition on concurrent merges to main
**Files:** `.github/workflows/release.yml`
**Security Issues Found:** No

Added concurrency group to prevent parallel release runs, git push retry loop (3 attempts), and a `git fetch/checkout -B` to sync with latest main before version bump. No secrets exposed, no injection vectors.

---

### PR #308 — Use brand palette for calendar event colors with dark/light mode support
**Files:** `web/src/lib/schedule-calendar.ts`, `web/src/styles/calendar.css`
**Security Issues Found:** No

Replaces dynamic HSL color generation with CSS custom properties. Pure UI/styling change with no security implications.

---

### PR #307 — Replace schedule entry modal with Sheet tray component
**Files:** `web/src/app/schedule/page.tsx`, `.github/workflows/ci.yml`
**Security Issues Found:** No

Swaps a custom modal for a Radix `Sheet` component (slide-out tray). Also increases E2E health-check timeout from 30 to 60 seconds. No security implications.

---

### PR #306 — Fix nav sidebar active state on sub-routes
**Files:** `web/src/components/navigation-sidebar.tsx`, `web/src/__tests__/navigation-sidebar.test.tsx`, `Dockerfile`, `nginx.conf`, `supervisord.conf`, `supervisord-dev.conf`, `web/package-lock.json`, `plugins/santa_tracker/manifest.json`
**Security Issues Found:** No

- Navigation active-state logic changed to support sub-routes (prefix matching).
- Dockerfile reorders steps to fix ownership issues (non-root user creation moved after file copy).
- `nginx.conf` adds `client_body_temp_path` and `proxy_temp_path` for the non-root appuser — improves container security by avoiding permission errors.
- Supervisord logs moved from `/tmp` and `/dev/stdout` to `/app/data/logs/` — no security concern, standard log management.
- Typo fix in santa_tracker manifest URL (case correction in GitHub org name).

---

### PR #305 — docs: comprehensive visual documentation overhaul with 45+ screenshots
**Files:** Multiple docs-site markdown/TypeScript files, new Playwright E2E test for screenshot generation
**Security Issues Found:** No

Adds comprehensive documentation pages for all plugins and a Playwright-based screenshot automation suite. Test data uses generic/fictional content (e.g., "SAN FRANCISCO", template variable placeholders). No hardcoded secrets, real personal information, or API keys.

---

### PR #304 — Remove Docker sock restart/upgrade, redesign update alert as inline banner
**Files:** `src/api_server.py`, `src/system/docker_manager.py` (deleted), `web/src/app/settings/page.tsx`, `web/src/components/settings/system-update.tsx`, `web/src/lib/api.ts`, tests
**Security Issues Found:** Yes — 1 finding (positive security improvement)

| # | Severity | Type | Description |
|---|----------|------|-------------|
| 1 | **Info (Positive)** | Attack Surface Reduction | **Removed dangerous Docker socket endpoints.** The `/system/restart` and `/system/upgrade` POST endpoints were deleted along with the entire `docker_manager.py` module. These endpoints allowed restarting containers and pulling new images via the Docker socket — a significant privilege escalation vector if the API is accessible on the network. Their removal is a **security improvement**. |

The update check is now a read-only info banner with an external link to the release page. No more write operations against the Docker daemon from the API.

---

### PR #303 — Replace ARM runner with Docker Buildx + QEMU for multi-platform builds
**Files:** `.github/workflows/release.yml`
**Security Issues Found:** No

CI/CD pipeline change only: replaces native ARM runner with QEMU-based cross-compilation. No secrets handling changes.

---

### PR #302 — Fix entrypoint failing with "operation not permitted" when container runs as non-root
**Files:** `entrypoint.sh`
**Security Issues Found:** No

Adds an early-exit check: if the container is already running as a non-root user (`id -u != 0`), the entrypoint skips all privilege-related operations and directly executes the CMD. This is a **security-positive** change that respects non-root container configurations (Docker rootless, `--user`, Kubernetes securityContext).

---

### PR #301 — Use native ARM runner for arm64 Docker build
**Files:** `.github/workflows/release.yml`
**Security Issues Found:** No

CI/CD change only: replaces QEMU emulation with a native `ubuntu-latest-arm` runner for arm64 builds. No security impact.

---

### PR #300 — Fix Docker socket permission denied on container restart
**Files:** `Dockerfile`, `entrypoint.sh` (new)
**Security Issues Found:** Yes — 1 finding

| # | Severity | Type | File | Description |
|---|----------|------|------|-------------|
| 1 | **Low** | Docker Security — Container Runs as Root | `Dockerfile` (lines ~111-113), `entrypoint.sh` | The container's `ENTRYPOINT` now runs as **root** to fix Docker socket permissions, then drops to `appuser` via `gosu`. Previously, the Dockerfile used `USER appuser` directly. While `gosu` privilege-dropping is a well-established pattern, running the entrypoint as root increases the attack surface if the entrypoint script has vulnerabilities. **Mitigated by:** PR #302 adds an early exit for non-root invocation, and PR #304 later removes the Docker socket dependency entirely. |

**Note:** The `gosu` binary is added as a dependency. gosu is the recommended tool for this pattern (preferred over `su` or `sudo` in containers).

---

### PR #299 — Remove white glow from pixel art feature icons
**Files:** Binary image files only (`docs-site/static/img/features/*.png`)
**Security Issues Found:** No

Image asset changes only.

---

### PR #297 — Live vestaboard output
**Files:** `src/api_server.py`, `web/src/components/page-builder.tsx`, `web/src/lib/api.ts`, `tests/test_live_output.py`, `web/src/__tests__/live-output.test.tsx`, `web/src/__tests__/mocks/handlers.ts`
**Security Issues Found:** Yes — 2 findings

| # | Severity | Type | File & Line | Description |
|---|----------|------|-------------|-------------|
| 1 | **Medium** | Exposed Sensitive Endpoint Without Auth | `src/api_server.py`, `POST /templates/render/live` | New endpoint that **renders a template AND sends it directly to the physical board**. Like all other endpoints in this API, it has **no authentication or authorization**. This endpoint is particularly sensitive because it uses `force=True` when calling `client.send_characters()`, **bypassing deduplication/throttle safeguards**. Any network-adjacent attacker can send arbitrary content to the board without limits. While the lack of auth is consistent with the rest of the API (which is designed for LAN use), the `force=True` flag and the ability to write to the board make this endpoint higher-risk than read-only endpoints. |
| 2 | **Low** | Missing Server-Side Rate Limiting | `src/api_server.py`, `POST /templates/render/live` | The live output endpoint has no server-side rate limiting. The only throttle is a client-side 5-minute inactivity timeout in the React component. A malicious client can bypass this and spam the endpoint, causing excessive writes to the physical board. |

**Positive notes:**
- The `board_id` parameter is validated against the configured boards list (cannot target arbitrary boards).
- Template rendering goes through the existing template engine (no new injection vectors).
- Client-side has a 5-minute auto-timeout that disables live mode on inactivity.

---

### PR #296 — Replace homepage emoji icons with branded pixel art
**Files:** `docs-site/src/components/HomepageFeatures/index.tsx`, `docs-site/src/components/HomepageFeatures/styles.module.css`, binary image files
**Security Issues Found:** No

Replaces emoji strings with `<img>` tags referencing local PNG files. Image sources are static paths (e.g., `/img/features/plugin-architecture.png`), not user-controlled. No XSS or injection risk.

---

### PR #295 — User onboarding documentation
**Files:** `DOCKERHUB_README.md`, `README.md`, `docs/setup/BEGINNERS_GUIDE.md`, `docs/setup/CLOUD_API_SETUP.md`
**Security Issues Found:** No

Documentation rewrite for onboarding. No code changes, no secrets. Discord invite link (`discord.gg/wc9dDfte`) is intentionally public. Placeholder API key references use descriptive strings like `your-read-write-key-here`.

---

### PR #294 — Parallelize multi-arch Docker image builds in release workflow
**Files:** `.github/workflows/release.yml`
**Security Issues Found:** No

CI/CD pipeline refactoring: splits single build into parallel per-platform builds with digest-based manifest assembly. Docker Hub credentials are properly referenced via `${{ secrets.DOCKERHUB_USERNAME }}` and `${{ secrets.DOCKERHUB_TOKEN }}`. No secret leakage.

---

## Summary of All Findings

| PR | Severity | Type | Description |
|----|----------|------|-------------|
| **#297** | **Medium** | Exposed Sensitive Endpoint Without Auth | `POST /templates/render/live` sends content to the physical board with `force=True`, has no authentication, and is accessible to anyone on the network. |
| **#297** | **Low** | Missing Server-Side Rate Limiting | `/templates/render/live` has no server-side rate limit; only client-side 5-minute inactivity timeout. |
| **#300** | **Low** | Docker Security — Root Entrypoint | Container entrypoint runs as root before dropping privileges via gosu. Mitigated by PR #302 (non-root bypass) and PR #304 (Docker socket removal). |
| **#304** | **Info (Positive)** | Attack Surface Reduction | Removed Docker socket-based `/system/restart` and `/system/upgrade` endpoints — significant security improvement. |

### Pre-Existing Issues (Not Introduced by These PRs)

| Severity | Type | Location | Description |
|----------|------|----------|-------------|
| **Medium** | CORS Misconfiguration | `src/api_server.py` line 268 | `allow_origins=["*"]` allows any origin to make API requests. Comment says "In production, restrict this to your UI domain" but no mechanism enforces this. |
| **Medium** | No API Authentication | `src/api_server.py` (all endpoints) | The entire API has no authentication mechanism. All endpoints (including board writes, configuration changes, and debug tools) are accessible to anyone who can reach the server. This is by design for LAN-only deployments but poses risk if the server is exposed to the internet. |

### Statistics

- **Total PRs reviewed:** 15
- **PRs with new security findings:** 2 (PR #297, PR #300)
- **PRs with security improvements:** 2 (PR #302, PR #304)
- **PRs with no security issues:** 11
- **Critical findings:** 0
- **High findings:** 0
- **Medium findings:** 1 (new), 2 (pre-existing)
- **Low findings:** 2
- **Info findings:** 1 (positive)
