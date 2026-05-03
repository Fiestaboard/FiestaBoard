---
sidebar_position: 2
description: "Technical reference for the FiestaUpdater sidecar — the companion container that powers FiestaBoard's one-click in-app updates."
keywords: [FiestaUpdater, fiestaupdater, in-app update, self-update sidecar, Docker socket, FiestaBoard updater]
---

# FiestaUpdater

`fiestaupdater` is the companion sidecar container that powers FiestaBoard's
[in-app updates](/docs/features/updating). This page is a technical reference for the
sidecar itself — its architecture, configuration, HTTP API, and security model.

:::tip Just want the Update Now button?
If you only want to enable in-app updates, see [In-App Updates](/docs/features/updating)
for the user-facing guide. This page is for understanding what the sidecar does and how
to configure it in custom Docker deployments.
:::

## Why a separate container?

The fiestaboard container can't safely update itself: as soon as
`docker compose up -d` recreates it, the running process (and any HTTP
response in flight) is killed. A side process is needed that:

- Has access to the host's Docker socket
- Survives the recreation of the `fiestaboard` container
- Is not itself recreated as part of the update

`fiestaupdater` is that process. It's a tiny container based on `docker:cli`
with a `socat`-driven HTTP listener and a single shell handler script.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Docker host                        │
│                                                       │
│   ┌──────────────────┐     internal network          │
│   │   fiestaboard    │────────►┌────────────────┐   │
│   │  (port 4420)     │  POST   │  fiestaupdater │   │
│   │                  │  /update│  (port 8765)   │   │
│   └──────────────────┘  Bearer └───────┬────────┘   │
│                                         │            │
│                                         │ docker.sock │
│                                         ▼            │
│                              ┌────────────────────┐  │
│                              │  Docker daemon     │  │
│                              │  pull + up -d      │  │
│                              └────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

Key properties:

- **Internal-network only.** The sidecar's port is not published to the host —
  it's reachable only by other containers on the same Docker Compose network.
- **Bearer-token authenticated.** Both containers share `FIESTAUPDATER_TOKEN`
  via `.env`. Tokens are compared by SHA-256 hash to limit timing-attack surface.
- **Service-name allow-listed.** The compose service the sidecar is willing to
  act on is validated against `^[a-z0-9_-]+$` before being passed to
  `docker compose`, so even a compromised env var can't smuggle in shell metacharacters.

## FiestaPi vs. Docker installs

| Install type | Sidecar status | Auto-update default |
|---|---|---|
| **[FiestaPi](/docs/setup/raspberry-pi)** | Pre-configured, enabled by default | **On** — applies updates daily |
| **Docker / manual** | Off by default; opt in via `COMPOSE_PROFILES` | Off — banner shown, user clicks Update Now |

On FiestaPi the `FIESTAUPDATER_TOKEN` is generated automatically on first boot
by `firstboot.sh`. On Docker installs you generate it yourself (see below).

## Docker Compose configuration

Below is the full `fiestaupdater` service definition used by
`docker-compose.hub.yml`. To enable in-app updates on a custom deployment,
add this service to your compose file (or pull it in via
`COMPOSE_PROFILES=fiestaupdater`):

```yaml
services:
  fiestaupdater:
    image: fiestaboard/fiestaupdater:latest
    container_name: fiestaupdater
    profiles: ["fiestaupdater"]
    restart: unless-stopped
    pull_policy: always
    environment:
      - FIESTAUPDATER_TOKEN=${FIESTAUPDATER_TOKEN}
      - FIESTAUPDATER_SERVICE=fiestaboard
      - FIESTAUPDATER_COMPOSE_FILE=/compose/docker-compose.yml
      - COMPOSE_PROJECT_NAME=fiestaboard
    cap_add:
      - SYS_BOOT  # required for POST /shutdown
    volumes:
      # Talk to the host Docker daemon to pull images and recreate services.
      - /var/run/docker.sock:/var/run/docker.sock
      # Read the same compose file the user deployed with so we update the
      # exact same service definition.
      - ./docker-compose.hub.yml:/compose/docker-compose.yml:ro
      # The compose file references `env_file: .env` for the fiestaboard
      # service. When the sidecar runs `docker compose -f /compose/...`,
      # Compose resolves `.env` relative to the compose file's directory.
      # Without this mount, every pull/up/restart fails with
      # "env file /compose/.env not found".
      - ./.env:/compose/.env:ro
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8765/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 5s
```

:::warning Three required volume mounts
All three volumes are required:

1. `docker.sock` — to run `docker compose` against the host daemon
2. The compose file — so the sidecar updates exactly the service you deployed
3. `.env` — Compose resolves `env_file` relative to the compose file's directory

Without the `.env` mount, every update silently no-ops with
`env file /compose/.env not found`.
:::

### Enabling on an existing Docker install

1. Generate a token and add it (along with `COMPOSE_PROFILES`) to your `.env`:

   ```bash
   echo "COMPOSE_PROFILES=fiestaupdater" >> .env
   echo "FIESTAUPDATER_TOKEN=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> .env
   ```

2. Make sure your compose file contains the `fiestaupdater` service block above.
   (`docker-compose.hub.yml` already does.)

3. Bring the stack up:

   ```bash
   docker compose -f docker-compose.hub.yml up -d
   ```

4. The Update Now button appears in **Settings → System** once the sidecar
   passes its healthcheck.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `FIESTAUPDATER_TOKEN` | yes | — | Shared bearer token. The sidecar refuses to start without it. Must match the value the `fiestaboard` container sees so the API can authenticate. |
| `FIESTAUPDATER_SERVICE` | no | `fiestaboard` | Compose service name to update. Validated against `^[a-z0-9_-]+$`; values that don't match fall back to `fiestaboard`. |
| `FIESTAUPDATER_COMPOSE_FILE` | no | `/compose/docker-compose.yml` | Path inside the sidecar container to the compose file. Mount your compose file here. |
| `FIESTAUPDATER_PORT` | no | `8765` | Port the sidecar listens on (internal network only). |
| `COMPOSE_PROJECT_NAME` | no | derived from compose dir | Must match the project name the main stack uses, so `docker compose` operates on the same containers. Set to `fiestaboard` to match `docker-compose.hub.yml`. |

`COMPOSE_PROFILES=fiestaupdater` is set on the **host** (in your `.env`),
not inside the sidecar container — it tells Docker Compose to include the
sidecar service when bringing the stack up.

## HTTP API

All routes are served on port `8765` on the Docker Compose internal network.
None of them are reachable from the host.

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/healthz` | none | Liveness probe. Returns `{"status":"ok"}`. |
| `GET` | `/version` | none | Returns the running container's image and digest. Used by the UI to detect when an update has actually landed. |
| `POST` | `/update` | bearer | `docker compose pull` + `up -d --no-deps` for the configured service. Returns `202 Accepted` immediately; the update runs in the background. |
| `POST` | `/restart` | bearer | `docker compose restart` for the configured service. Returns `202`. |
| `POST` | `/shutdown` | bearer | Stops the compose stack and powers off the host. Requires the `SYS_BOOT` capability. Returns `202`. |

Authentication is `Authorization: Bearer <FIESTAUPDATER_TOKEN>`. Failed auth
returns `401`. Unknown routes return `404`.

`POST /update` and `POST /restart` return `202` before the work starts because
the action will tear down the `fiestaboard` container that originated the
HTTP request — the connection would otherwise be cut before any response
could be flushed.

## Security

- **No host port.** The sidecar's listener is bound to the compose-internal
  network only. Even on a multi-tenant LAN, no other host can reach `/update`.
- **Bearer-token auth.** A 64-hex-character random token is required for every
  state-changing route. SHA-256 hash comparison reduces timing-attack surface.
- **Service-name allow-list.** The configured service name must match
  `^[a-z0-9_-]+$` before being passed to `docker compose`. No user input is
  ever interpolated into a shell command.
- **Read-only mounts.** The compose file and `.env` are mounted `:ro`.
- **Limited blast radius.** The sidecar can pull images and recreate the one
  service named in `FIESTAUPDATER_SERVICE`. It cannot start arbitrary
  containers or run arbitrary shell commands.

If you're uncomfortable mounting the Docker socket at all, leave the
`fiestaupdater` profile off and [update manually](/docs/features/updating#updating-manually-always-works).

## Troubleshooting

**The Update Now button doesn't appear.** The web UI probes the sidecar at
startup. Check:

```bash
docker compose ps fiestaupdater          # is it running and healthy?
docker logs fiestaupdater                # any errors?
docker exec fiestaboard wget -qO- http://fiestaupdater:8765/healthz
```

The most common cause is `COMPOSE_PROFILES=fiestaupdater` missing from `.env`,
so the sidecar service is never started.

**Update returns 202 but nothing happens.** Check the sidecar logs for
`env file /compose/.env not found` — this means the `.env` volume mount is
missing from your compose file. Add it (see [configuration](#docker-compose-configuration))
and recreate the sidecar.

**Update started but FiestaBoard never came back.** Wait a minute (the Pi can
take 60–90s to recreate the container), then reload
`http://fiestaboard.local:4420`. If still down:

```bash
docker logs fiestaboard
docker compose -f docker-compose.hub.yml up -d
```

**I want to roll back.** Pin the previous image tag (e.g.
`image: fiestaboard/fiestaboard:5.1.1`) in your compose file, then
`docker compose up -d`. Automated rollback is planned for a future release.

## See also

- [In-App Updates](/docs/features/updating) — user-facing guide and Update Now flow
- [FiestaPi Quick Start](/docs/setup/raspberry-pi) — pre-configured Pi image with the sidecar enabled
- [Raspberry Pi Deployment](/docs/deployment/raspberry-pi) — running on an existing Pi with Docker
- [Environment Variables](/docs/reference/environment-variables#fiestaupdater) — full env-var reference
