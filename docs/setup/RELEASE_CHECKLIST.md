# Pre-release security checklist (run before every release)

Use this before publishing the repo or cutting a release to avoid leaking secrets or personal data.

> **How releases actually ship:** Day-to-day version bumps are automated. `.github/workflows/release.yml` runs on pushes to `main` that touch non-documentation source files — it skips commits whose only changes are in `**.md`, `docs/**`, `.github/**`, `images/**`, `.devcontainer/**`, `LICENSE`, or other non-code paths. When it does run, it picks the bump type from the merged PR's `major` / `minor` / `patch` label (defaults to `patch`), commits `chore: bump version to X.Y.Z [skip ci]`, builds and pushes the multi-arch image, and creates the GitHub Release. The FiestaPi `.img.xz` is attached later by `build-fiestapi.yml` (~45–60 min).
>
> **Do not bump versions by hand** in `package.json`, `web/package.json`, or `src/__init__.py`. The checklist below covers the manual gate: making sure no secrets are committed before the first public push.

## 1. Ensure no secrets are committed

- [ ] **`.env`** – Must not be tracked. Run: `git check-ignore -v .env` (should show `.gitignore`).
- [ ] **`data/`** – Must not be committed except optional seed content. Run: `git ls-files data/` and confirm no `data/config.json`, `data/settings.json`, or any file containing API keys/tokens. If you use `!data/pages.json`, ensure that file contains only non-personal seed/default pages.
- [ ] **API_KEYS.md** – Listed in `.gitignore`; do not commit if it contains real keys.

## 2. Search for accidental leaks

Run these two checks from the repo root. They target different file types because the signal to look for differs.

### 2a. Code, config, and workflow files

```bash
# Should return no matches (or only placeholder strings like "test_key", "your_*_here")
git grep -E 'api_key|password|secret|token' -- '*.py' '*.ts' '*.tsx' '*.json' '*.yml' | grep -v -E 'example|test_key|your_|placeholder|_mask_sensitive|SENSITIVE' || true
```

- [ ] No real API keys, tokens, or passwords appear in code, config, or CI/CD files.

### 2b. Documentation files

```bash
# Expect many hits — docs legitimately discuss tokens, API keys, and secrets throughout.
# Look for actual credential values, not just the words.
git grep -E 'api_key|password|secret|token' -- '*.md' | grep -v -E 'your_|your-|<[^>]+>|example|placeholder|`[a-z_]+`|\$\{' || true
```

> **What to look for:** lines containing long hex or base64 strings, keys starting with `sk-`, `Bearer` followed by a real-looking value, or any string that looks like a real credential rather than a placeholder. Hits on words like "your API key" or "token configuration" are expected and can be ignored.

- [ ] No real credential values appear in documentation files.
- [ ] Docs and examples use placeholders like `your_api_key_here`, `your-weather-api-key`, etc.

## 3. Example and documentation content

- [ ] No real addresses, home coordinates, or personal identifiers in examples (use generic values or well-known landmarks).
- [ ] No real phone numbers or emails in examples (except plugin author attribution in `manifest.json` where allowed by project rules).

## 4. CI/CD and GitHub

- [ ] Workflows use `secrets.GITHUB_TOKEN` or repo secrets only; no hardcoded tokens or passwords.
- [ ] Optional: Add a branch protection rule for `main` and require status checks before merge.

## 5. After going public

- [ ] Rotate any keys that might have been used in development or that were ever committed in the past (check `git log -p` for removed secrets).
- [ ] Ensure Docker images are built without embedding `.env` or host secrets; use `env_file` at runtime instead.
