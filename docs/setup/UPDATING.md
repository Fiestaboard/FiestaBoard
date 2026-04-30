# Updating FiestaBoard

Starting in **5.0**, FiestaBoard can update itself. There's a button in **Settings → System** labelled **Update Now**. Click it, confirm, wait about a minute, done.

This page explains how it works, how to opt in or out, and what to do if it goes sideways.

## How it works

FiestaBoard talks to a small companion container called `fiestaupdater`. The updater has access to your host's Docker socket (FiestaBoard itself does not). When you click **Update Now**, the web UI POSTs to the API, the API calls the updater on the internal Docker network, and the updater runs `docker compose pull && docker compose up -d` against your compose file.

Because the updater is a separate process, FiestaBoard can update *itself* — the running container gets stopped and replaced, and your browser's overlay polls until the new version is back.

## Opting in (Docker / manual installs)

The updater is opt-in for all non-Pi installs. Two things need to be true:

1. The `fiestaupdater` Compose profile is enabled.
2. `FIESTAUPDATER_TOKEN` is set in your `.env`.

The install scripts (`install.sh` / `install.ps1`) ask you about this and configure it for you on a fresh install. To enable it manually after the fact, edit `.env`:

```bash
COMPOSE_PROFILES=fiestaupdater
FIESTAUPDATER_TOKEN=<a long random hex string>
```

Generate a token with: `head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'` (or any 32+ random bytes hex-encoded).

Then restart:

```bash
docker compose up -d
```

The Update Now button will appear once the sidecar is healthy.

## Opting in (FiestaPi)

It's already on. `FIESTABOARD_PROFILE=pi` is baked into the image, which flips the in-app **Auto-update** toggle to default ON, and a unique `FIESTAUPDATER_TOKEN` is generated at first boot. You can disable auto-update in Settings if you'd rather click each time.

## Update check interval

In Settings → System there's a **Check for updates** dropdown that controls
how often FiestaBoard polls for a newer release in the background:

- **Every day** — default for FiestaPi.
- **Every week** — default for Docker / manual installs. A good balance of
  staying current without nagging.
- **Every month** — quietest option that still nudges you periodically.
- **Manual only** — no background checks; use the refresh button on the
  Settings → System card to check on demand.

When a check finds a newer version, you'll see an "Update Available" banner
on Settings → System. Click **Update Now** (or follow the manual steps
below) when you're ready to apply it.

The choice persists in `data/.system-update.json` under
`auto_update_interval`. Older installs that have only the legacy
`auto_update_enabled` boolean continue to work — `true` is treated as the
install's default interval and `false` as `manual`.

## Manual updating (always works)

The Update Now button is convenience; it's not the source of truth. You can always update from the shell:

```bash
cd /path/to/FiestaBoard          # or /opt/fiestaboard on FiestaPi
docker compose pull
docker compose up -d
```

## Security model

- The updater listens on the Compose internal network only (not on a host port).
- Every request to the updater requires a bearer token (`FIESTAUPDATER_TOKEN`) that's compared with constant-time hashing.
- The service name to restart is allow-listed (`^[a-z0-9_-]+$`) — no shell injection via crafted requests.
- The updater can only run `docker compose pull/up -d` against the file you mount in. It can't spawn arbitrary containers or images outside that compose project.

If you'd rather not run with the Docker socket exposed at all, leave the `fiestaupdater` profile off and update manually.

## Troubleshooting

**The Update Now button is missing** — The status panel on the same page tells you whether the updater is reachable and why not. Most common cause: the sidecar profile is disabled.

**Update kicked off but the page never came back** — Open the URL again after a minute. If it's still down: `docker compose logs fiestaboard` (or `docker logs fiestaboard`). Worst case, manual `docker compose up -d` will bring you back up.

**I want to roll back** — Pin the previous tag in `docker-compose.yml` and `docker compose up -d`. Automated rollback is on the roadmap for 5.1.
