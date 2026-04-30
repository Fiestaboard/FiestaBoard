---
sidebar_position: 10
description: "FiestaBoard 5.0 introduces one-click in-app updates. Learn how Update Now works, how to opt in on Docker installs, and how auto-update works on FiestaPi."
keywords: [FiestaBoard update, in-app update, self-update, Update Now, fiestaupdater, FiestaPi update]
---

# In-App Updates

Starting in FiestaBoard **5.0**, you can update FiestaBoard directly from the web UI — no terminal required.

## The Update Now button

When a new version is available, a banner appears in **Settings → System**. Click **Update Now**, confirm, and FiestaBoard handles the rest:

1. The `fiestaupdater` sidecar pulls the new Docker image in the background
2. FiestaBoard restarts with the new image
3. A full-screen overlay polls the API every 2 seconds
4. When the new version is detected, the page reloads automatically

The whole process takes about a minute on a fast connection, a bit longer on a Raspberry Pi.

## Auto-update

In **Settings → System**, there's an **Auto-update** toggle:

| Install type | Default | What it does |
|---|---|---|
| **FiestaPi** | **On** | Checks for updates daily and applies them automatically |
| **Docker / manual** | Off | Shows a banner when updates are available; you decide when to apply |

You can flip the toggle any time.

## How it works (technical)

FiestaBoard uses a small companion container called `fiestaupdater`. It sits on the same Docker Compose internal network as FiestaBoard and has access to the Docker socket — FiestaBoard itself does not.

When you click Update Now, the web UI POSTs to the FiestaBoard API, which calls the updater over the internal network. The updater runs `docker compose pull && docker compose up -d` against your compose file. Because it's a separate process, FiestaBoard can update itself without getting cut off mid-response.

**See also:** [FiestaUpdater reference](/docs/deployment/fiestaupdater) for the full sidecar architecture, environment variables, and HTTP API.

## Opting in on Docker installs

The updater is opt-in for Docker and manual installs (it's already on for FiestaPi).

**Via the install script (easiest):** Run `./scripts/install.sh` (or `install.ps1` on Windows) — it asks about this and configures everything.

**Manually:** Edit your `.env` file:

```bash
COMPOSE_PROFILES=fiestaupdater
FIESTAUPDATER_TOKEN=<64-hex-char random string>
```

Generate a token:
```bash
head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
```

Then restart:
```bash
docker compose up -d
```

The Update Now button will appear in Settings → System once the sidecar is healthy.

## Security

- The updater is only reachable on the Docker Compose internal network — it's never published on a host port
- All requests require a bearer token (`FIESTAUPDATER_TOKEN`), unique to your install
- The sidecar can only restart the service listed in `FIESTAUPDATER_SERVICE` — no arbitrary container access

If you prefer not to use the Docker socket at all, leave the `fiestaupdater` profile off and update manually instead.

## Updating manually (always works)

The Update Now button is a convenience shortcut. You can always update from the terminal:

```bash
# For Docker Hub installs — cd to the SAME folder you originally ran
# `docker compose up -d` from. That's where your ./data folder lives.
cd ~/fiestaboard
docker compose -f docker-compose.hub.yml pull
docker compose -f docker-compose.hub.yml up -d

# For FiestaPi (SSH in first)
ssh fiesta@fiestapi.local
cd /opt/fiestaboard
docker compose pull && docker compose up -d
```

:::caution Always `cd` first on Docker installs
The compose file uses a relative bind mount (`./data:/app/data`), so persistence depends on your current shell directory. If you run `docker compose pull && up -d` from a different folder than your original install, FiestaBoard will come up with empty settings — your data isn't deleted, but Docker is mounting a different (empty) folder. See [Troubleshooting → Settings or board credentials are gone after an update](/docs/troubleshooting#settings-or-board-credentials-are-gone-after-an-update) if this has happened.
:::

## Troubleshooting

**The Update Now button isn't showing** — Check the status panel just below the button area in Settings → System. It will say whether the updater sidecar is reachable. Most common cause: `COMPOSE_PROFILES=fiestaupdater` isn't set in `.env`, or the sidecar container isn't running.

**Update started but the page never came back** — Open `http://fiestaboard.local:4420` (or `localhost:4420`) again after a minute. If it's still down, check logs: `docker logs fiestaboard`. As a last resort, `docker compose up -d` will bring you back online.

**I want to roll back** — Pin the previous image tag in `docker-compose.yml`, then `docker compose up -d`. Automated rollback is planned for a future release.
