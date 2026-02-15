# Pre-release checklist (e.g. before making the repo public)

Use this before publishing the repo or cutting a release to avoid leaking secrets or personal data.

## 1. Ensure no secrets are committed

- [ ] **`.env`** – Must not be tracked. Run: `git check-ignore -v .env` (should show `.gitignore`).
- [ ] **`config.json`** – Must not exist in repo root; only `config.example.json` is tracked.
- [ ] **`data/`** – Must not be committed except optional seed content. Run: `git ls-files data/` and confirm no `data/config.json`, `data/settings.json`, or any file containing API keys/tokens. If you use `!data/pages.json`, ensure that file contains only non-personal seed/default pages.
- [ ] **API_KEYS.md** – Listed in `.gitignore`; do not commit if it contains real keys.

## 2. Search for accidental leaks

From repo root:

```bash
# Should return no matches (or only test/example placeholders like "test_key", "your_*_here")
git grep -E 'api_key|password|secret|token' -- '*.py' '*.ts' '*.tsx' '*.json' '*.yml' '*.md' | grep -v -E 'example|test_key|your_|placeholder|***|_mask_sensitive|SENSITIVE' || true
```

- [ ] No real API keys, tokens, or passwords in code, docs, or committed config.
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
