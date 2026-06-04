Open a GitHub pull request for the current branch against `main`.

Never run from `main` — abort and ask the user to switch to a feature branch first.

Steps (run the read-only commands in parallel where possible):

1. Inspect state:
   - `git branch --show-current` — confirm it isn't `main`.
   - `git status` (never `-uall`) — note untracked/uncommitted changes.
   - `git diff main...HEAD` and `git log main..HEAD --oneline` — review every commit that will land, not just the latest.
   - `git rev-parse --abbrev-ref --symbolic-full-name @{u} 2>/dev/null` — check whether the branch already tracks a remote.

2. If there are uncommitted changes, stop and ask the user whether to commit them first (do not auto-stage with `git add -A` or `git add .` — add specific paths only). Never commit files that look like secrets (`.env`, credentials, tokens).

3. Draft the PR title and body:
   - **Title** under 70 chars, conventional-commit style matching this repo (`feat(plugin-x): …`, `fix(a11y): …`, `chore: …`, `docs: …`, `build(deps): …`). Scope = plugin id when the change is plugin-local.
   - **Body** uses this template (HEREDOC, not `-b "..."`):

     ```
     ## Summary
     - <1–3 bullets on the why, not a file list>

     ## Changes
     - <key user-visible or behavior changes>

     ## Test plan
     - [ ] <commands run, e.g. `docker-compose -f docker-compose.dev.yml exec fiestaboard pytest`>
     - [ ] <manual checks, screenshots, /qa-a11y, etc.>

     🤖 Generated with [Claude Code](https://claude.com/claude-code)
     ```

   - For plugin changes, include the plugin-doc checklist items that apply (README hero image, SETUP.md, `board-display.png`, main README "Available Plugins" entry for new plugins).
   - For a11y fixes, cite WCAG criteria per finding.

4. Push and open:
   - If no upstream: `git push -u origin <branch>`. Otherwise `git push`.
   - `gh pr create --base main --title "…" --body "$(cat <<'EOF' … EOF)"`.
   - Never `--no-verify`, never force-push, never push to `main`.

5. Print the PR URL on the last line so it's easy to click.

If `gh` isn't authed (`gh auth status` fails), tell the user to run `! gh auth login` in the prompt and stop.
