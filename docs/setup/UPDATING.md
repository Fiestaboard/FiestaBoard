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

## Auto-update toggle

In Settings → System there's an **Auto-update** switch:

- **On** (default for FiestaPi): a daily background check pulls and applies updates.
- **Off** (default for Docker installs): you'll see a banner when an update is available and decide when to apply it.

The toggle persists in `data/.system-update.json`.

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
