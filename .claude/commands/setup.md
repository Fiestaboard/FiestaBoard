One-shot developer setup for FiestaBoard. Goal: a brand-new dev runs `/setup` and ends with Docker installed, every `fiestaboard-plugin--*` repo cloned as a sibling of the FiestaBoard repo, the dev container built and running, and `http://localhost:4420` confirmed reachable.

This skill is macOS- and Linux-agnostic. Detect the platform up front (`uname -s`) and branch installer logic accordingly. Never assume Homebrew or apt are present — probe.

Run as much as possible in parallel (read-only probes, status checks). Treat the whole flow as idempotent: rerunning `/setup` on a half-setup machine should fix what's missing and skip what's done.

## Working directory

Find the FiestaBoard repo root for this session. If the current working directory is the FiestaBoard repo (or a git worktree of it), the **parent of the repo's main worktree** is the clone target — plugin siblings live next to `FiestaBoard/`, e.g. `~/workspace/FiestaBoard/` and `~/workspace/fiestaboard-plugin--muni/`.

Resolve the main worktree with `git worktree list | head -1` (first entry is the primary). The clone target is the parent of that path. Never clone into the worktree itself or into `external_plugins/` — those have a different purpose.

## Phase 1 — Probe the host

Run these in parallel and summarize the results to the user before touching anything:

- `uname -s` — `Darwin` or `Linux`
- `command -v docker` and, if found, `docker --version`
- `docker compose version` (v2 plugin form; the `docker-compose` hyphenated binary is legacy)
- `docker info` — confirms the daemon is actually running, not just installed
- `command -v git` / `git --version`
- `command -v gh` / `gh auth status` — used for plugin discovery; not strictly required if registry-only mode is used
- `command -v brew` (macOS) or `command -v apt-get` / `command -v dnf` (Linux)

Print a short status table (Docker installed? running? git? gh authed? plugin manager available?). Then proceed.

## Phase 2 — Install Docker if missing

**macOS:**
- If Docker Desktop is not installed: prefer `brew install --cask docker`. If Homebrew isn't present, stop and ask the user to either install Homebrew (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`) or download Docker Desktop from https://www.docker.com/products/docker-desktop manually — do not silently curl-pipe an installer.
- After install, Docker Desktop must be launched once by the user to accept the license. Try `open -a Docker` and then poll `docker info` for up to 60 seconds. If it never comes up, surface a clear "open Docker Desktop and rerun /setup" message.

**Linux:**
- Detect the package manager: `apt-get` (Debian/Ubuntu), `dnf`/`yum` (Fedora/RHEL), `pacman` (Arch).
- Prefer the official Docker convenience script when no Docker is present: `curl -fsSL https://get.docker.com | sh`. This is the path Docker itself documents and it installs `docker-ce` + the compose plugin in one shot. Ask the user before running it (it requires sudo).
- After install: `sudo systemctl enable --now docker`, then `sudo usermod -aG docker $USER` so future invocations don't need sudo. Warn the user they must log out / `newgrp docker` for the group change to apply this session — fall back to `sudo docker ...` for the rest of this setup run if needed.
- Verify with `docker info`.

If Docker installation requires user interaction or a re-login, stop cleanly and instruct the user how to resume — do not loop forever.

## Phase 3 — Clone plugin repos as siblings

The canonical list lives in `plugin-registry.json` at the FiestaBoard repo root. Parse it (it's standard JSON with a `plugins` array; each entry has a `repository` URL) to get the full set.

Optionally augment with discovery: if `gh` is installed and authenticated, run `gh repo list Fiestaboard --limit 200 --json name,sshUrl,url` and union in anything whose `name` starts with `fiestaboard-plugin--` that the registry missed. This catches in-flight plugins not yet registered.

For each repo URL, derive `<parent>/<repo-name>` (where `<parent>` is the directory determined in Phase 1, and `<repo-name>` is the last path segment of the URL, e.g. `fiestaboard-plugin--muni`). Then:

- If the directory does **not** exist: `git clone <url> <parent>/<repo-name>`. Run clones in parallel batches of ~5 to keep the network busy without flooding it.
- If the directory **exists** and is a clean git repo: `git -C <path> pull --ff-only`. If fast-forward fails, do **not** force — print "skipped (diverged, has local commits)" and move on.
- If the directory exists but is dirty (`git status --porcelain` non-empty): skip with a clear "skipped (uncommitted changes)" message. Never stash or reset the user's work.
- If the directory exists but isn't a git repo: skip with "skipped (not a git repo)" and warn.

Build a final tally: `N cloned`, `M updated`, `K skipped (with reason)`. Show it.

## Phase 4 — Seed `.env`

If `.env` does not exist in the FiestaBoard repo root, `cp env.example .env`. If it already exists, leave it alone and tell the user to diff against `env.example` themselves if they've been away a while.

## Phase 5 — Build and start the dev container

From the FiestaBoard repo root:

```
docker-compose -f docker-compose.dev.yml up -d --build
```

This is `--build` (not `--no-cache`) — first-time builds need to fetch base images and install Python + Node deps, but cache reuse is fine. If the user wants a forced clean rebuild they can run `/restart`.

Stream the build output so the user can see progress; this can take 5–15 minutes on a fresh machine. Do not background it silently.

## Phase 6 — Validate reachability

After `up -d` returns, poll the running container, not just the port:

- `docker-compose -f docker-compose.dev.yml ps` — confirm the `fiestaboard` service is `Up` and healthy
- `curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:4420/` — poll every 3s for up to 90s; expect a 2xx or 3xx
- Tail the last ~30 log lines if it never comes up: `docker-compose -f docker-compose.dev.yml logs --tail 30 fiestaboard`

When the UI responds, print:

- The URL: `http://localhost:4420`
- Where the plugin siblings live (the parent directory used in Phase 3)
- How to view logs: `docker-compose -f docker-compose.dev.yml logs -f`
- How to stop: `/stop`
- How to do a clean rebuild: `/restart`

## Failure handling

- Any phase that fails should stop the flow cleanly with a one-screen summary of what worked, what didn't, and the exact next command the user needs to run.
- Never run destructive operations (`docker system prune`, `git reset --hard`, `rm -rf` on existing dirs) without explicit user confirmation — this is a setup script, not a recovery script.
- If `sudo` is required and the user is not in a sudoer position, surface that early rather than mid-flow.

## Scope boundaries

- Do **not** install Python or Node on the host. All language deps live inside the container — that's the project's hard rule (see CLAUDE.md).
- Do **not** modify `.env` once it exists.
- Do **not** touch any plugin repo with a dirty working tree.
- Do **not** clone into `external_plugins/` or `plugins/` — sibling layout only.
