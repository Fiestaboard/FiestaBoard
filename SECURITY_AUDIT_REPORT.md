# Security Audit Report: Merged Pull Requests

**Audit Date:** 2026-02-28
**PRs Reviewed:** 276, 275, 274, 273, 272, 270, 269, 268, 267, 266, 265, 263, 262, 261, 260
**Auditor:** Automated Security Review (Cloud Agent)

---

## Per-PR Analysis

### PR #276: Docs splash page emojis
- **Files changed:** `docs-site/src/components/HomepageFeatures/index.tsx`, `docs-site/src/components/HomepageFeatures/styles.module.css`, `docs-site/src/pages/index.tsx`
- **Summary:** Removes decorative emojis from the documentation site splash page and adjusts emoji font size in CSS.
- **Security issues found:** No security issues found.

---

### PR #275: Remove decorative emojis and em dashes from docs
- **Files changed:** `CONTRIBUTING.md`, `README.md`, multiple files under `docs/`, `plugins/traffic/README.md`, `docs/reference/COLOR_GUIDE.md`
- **Summary:** Cosmetic cleanup replacing em dashes with hyphens/periods and removing decorative emojis from documentation files.
- **Security issues found:** No security issues found.

---

### PR #274: Fix mobile sidebar: auto-expand Documentation dropdown
- **Files changed:** `docs-site/docusaurus.config.ts`, new file `docs-site/src/theme/NavbarItem/DropdownNavbarItem/Mobile/index.tsx`, new file `docs-site/src/theme/NavbarItem/DropdownNavbarItem/Mobile/styles.module.css`
- **Summary:** Swizzles the Docusaurus DropdownNavbarItem Mobile component to start expanded instead of collapsed. Changes the navbar from a `docSidebar` type to a `dropdown` with explicit doc items.
- **Security issues found:** No security issues found.

---

### PR #273: Improve docs and GitHub SEO
- **Files changed:** `.github/FUNDING.yml`, `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `CODE_OF_CONDUCT.md`, `README.md`, `docs-site/docusaurus.config.ts`, `package.json`, `pyproject.toml`
- **Summary:** Adds GitHub community files (issue templates, PR template, code of conduct, FUNDING.yml), SEO metadata (OpenGraph/Twitter images, structured data), and package.json/pyproject.toml metadata.
- **Security issues found:** No security issues found.

---

### PR #272: feat: Stardate as standalone plugin
- **Files changed:** `README.md`, new plugin directory `plugins/stardate/` with `__init__.py`, `manifest.json`, `README.md`, `docs/SETUP.md`, `docs/SCREENSHOT_NEEDED.md`, `tests/conftest.py`, `tests/test_plugin.py`
- **Summary:** Adds a new Stardate plugin that calculates and displays the current TNG-era stardate. Uses `pytz` for timezone handling and `calendar` for leap year detection. No external API calls.
- **Security issues found:** No security issues found.

---

### PR #270: Remove bogus weather symbols from character codes docs
- **Files changed:** `README.md`, `docs-site/docs/reference/character-codes.md`, deleted `docs/reference/CHARACTER_CODES.md`
- **Summary:** Removes inaccurate weather symbol documentation from character codes reference. Consolidates docs to the docs-site version.
- **Security issues found:** No security issues found.

---

### PR #269: Add CODEOWNERS file
- **Files changed:** `.github/CODEOWNERS`
- **Summary:** Adds a single-line CODEOWNERS file assigning two GitHub users as default reviewers.
- **Security issues found:** No security issues found.

---

### PR #268: Tech Debt: Deprecate redundant API endpoints and add migration guide
- **Files changed:** `docs/development/API_MIGRATION.md` (new), `docs/development/TECHNICAL_DEBT.md` (new), `src/api_server.py`
- **Summary:** Adds deprecation headers (`Deprecation: true`, `Link` with successor-version) to legacy API endpoints (`/config/vestaboard`, `/displays/{type}/raw`). Adds migration guide and technical debt documentation.
- **Note (functionality bug, not security):** The route decorators `@app.get("/config/board")` and `@app.put("/config/board")` were removed from the compatibility functions, which means those endpoints are no longer registered as HTTP routes. The functions exist but are unreachable. This is a functionality bug (the deprecation headers will never be served on those paths), not a security vulnerability.
- **Security issues found:** No security issues found.

---

### PR #267: Remove legacy *_ENABLED environment variables
- **Files changed:** `env.example`, `src/config_manager.py`
- **Summary:** Removes the `apply_bool` helper function and all `*_ENABLED` environment variable bindings from the config manager. Plugin enable/disable is now managed exclusively through the UI or `config.json`. Updates `env.example` comments accordingly.
- **Security issues found:** No security issues found.

---

### PR #266: Migrate `src/data_sources/` to `src/utils/`
- **Files changed:** `.github/workflows/ci.yml`, multiple plugin test files, `plugins/muni/__init__.py`, `pyproject.toml`, `src/api_server.py`, all files under `src/data_sources/` renamed to `src/utils/`, `tests/test_logs.py`, `tests/test_transit_cache.py`
- **Summary:** Renames the `src/data_sources/` directory to `src/utils/` and updates all import paths across the codebase (CI, API server, plugin code, and tests).
- **Security issues found:** No security issues found.

---

### PR #265: Rename `feature-settings` component folder to `settings`
- **Files changed:** `web/package-lock.json`, `web/package.json`, `web/src/app/settings/page.tsx`, renamed `web/src/components/feature-settings/` to `web/src/components/settings/`
- **Summary:** Renames the frontend component folder from `feature-settings` to `settings`. Also pins TypeScript to `5.9.3` and updates `package-lock.json`.
- **Security issues found:** No security issues found.

---

### PR #263: feat: per-board schedule with multi-board e2e
- **Files changed:** `integration-tests/mock-board/server.py`, `src/api_server.py`, `web/tests/helpers.ts`, new file `web/tests/multi-board-schedule.spec.ts`
- **Summary:** Extends the mock board server to support multiple ports for multi-board testing. Adds per-board schedule filtering via `board_id` query parameter. Adds E2E tests for multi-board scheduling scenarios.
- **Security issues found:** No security issues found.
- **Notes:** The mock board server binds to `0.0.0.0` which is expected for a test/integration mock. The `board_id` parameter is used for filtering in-memory data (not SQL), so no injection risk exists.

---

### PR #262: Add OCI image metadata labels to Dockerfiles
- **Files changed:** `Dockerfile.api`, `Dockerfile.ui`
- **Summary:** Adds standard OCI image metadata labels (`org.opencontainers.image.*`) to both API and UI Dockerfiles for better container registry discoverability.
- **Security issues found:** No security issues found.

---

### PR #261: Remove registry buildcache images from release workflow
- **Files changed:** `.github/workflows/release.yml`
- **Summary:** Simplifies Docker build caching in the release workflow by removing `type=registry` cache entries and keeping only `type=gha` (GitHub Actions cache).
- **Security issues found:** No security issues found.

---

### PR #260: Docs: default getting started to GHCR image pull, not repo clone + build
- **Files changed:** `README.md`, `docs/deployment/PI_BUILD_GUIDE.md`, `docs/setup/BEGINNERS_GUIDE.md`, `docs/setup/DOCKER_SETUP.md`
- **Summary:** Rewrites getting-started documentation to default to pulling pre-built Docker images from GHCR instead of cloning the repo and building from source. Updates port references (8080 -> 4420, 8000 -> 6969), removes install wizard references, and adds explicit `docker-compose.yml` examples.
- **Security issues found:** No security issues found.
- **Notes:** All API keys in examples use appropriate placeholders (`your_local_api_key_here`, `your_read_write_key_here`). IP addresses used are generic private network addresses (`192.168.0.11`, `192.168.1.100`) serving as examples, not real personal information.

---

## Summary

| PR | Title | Security Issues |
|----|-------|----------------|
| #276 | Docs splash page emojis | None |
| #275 | Remove decorative emojis and em dashes from docs | None |
| #274 | Fix mobile sidebar: auto-expand Documentation dropdown | None |
| #273 | Improve docs and GitHub SEO | None |
| #272 | feat: Stardate as standalone plugin | None |
| #270 | Remove bogus weather symbols from character codes docs | None |
| #269 | Add CODEOWNERS file | None |
| #268 | Tech Debt: Deprecate redundant API endpoints and add migration guide | None |
| #267 | Remove legacy *_ENABLED environment variables | None |
| #266 | Migrate `src/data_sources/` to `src/utils/` | None |
| #265 | Rename `feature-settings` component folder to `settings` | None |
| #263 | feat: per-board schedule with multi-board e2e | None |
| #262 | Add OCI image metadata labels to Dockerfiles | None |
| #261 | Remove registry buildcache images from release workflow | None |
| #260 | Docs: default getting started to GHCR image pull, not repo clone + build | None |

### Overall Assessment

**No security vulnerabilities were found across the 15 reviewed pull requests.**

The PRs in this batch are predominantly:
- Documentation updates and cosmetic cleanup (PRs #276, #275, #274, #273, #270, #260)
- Code refactoring/renaming with no logic changes (PRs #266, #265)
- CI/CD and Docker metadata improvements (PRs #262, #261, #269)
- New plugin with no external dependencies or API calls (PR #272)
- Configuration simplification (PR #267)
- API deprecation with documentation (PR #268)
- Test infrastructure for multi-board support (PR #263)

**One non-security bug was noted:** PR #268 accidentally removed route decorators from two endpoint functions (`get_board_config_compat` and `update_board_config_compat`), making them unreachable. This is a functionality issue, not a security vulnerability.

### Checklist of Security Areas Reviewed

- [x] Hardcoded secrets, API keys, tokens, passwords, or credentials
- [x] Sensitive personal information (real addresses, phone numbers, SSNs, etc.)
- [x] SQL injection vulnerabilities
- [x] Cross-site scripting (XSS) vulnerabilities
- [x] Command injection vulnerabilities
- [x] Path traversal vulnerabilities
- [x] Insecure deserialization
- [x] Improper authentication/authorization
- [x] Exposed sensitive endpoints without auth
- [x] Insecure cryptographic practices
- [x] SSRF (Server-Side Request Forgery) vulnerabilities
- [x] Unsafe file operations
- [x] Docker security issues (running as root, exposed secrets in images)
- [x] CI/CD pipeline security issues (secret leakage, unsafe script injection)
- [x] Dependency vulnerabilities
- [x] CORS misconfigurations
- [x] Unsafe use of eval() or similar dangerous functions
- [x] Information disclosure in error messages
- [x] Insecure direct object references
- [x] Missing input validation/sanitization
