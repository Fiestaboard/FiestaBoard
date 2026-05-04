# FiestaUpdater

A tiny companion sidecar container that performs in-place updates of the main `fiestaboard` container by pulling the newest image and recreating the service via the host Docker socket.

This replaces our prior reliance on Watchtower, which was archived in December 2025.

## How it works

1. The main `fiestaboard` API exposes `POST /system/update`.
2. That handler proxies to `POST http://fiestaupdater:8765/update` over the internal compose network with a shared bearer token. Before proxying, the API also snapshots `data/*.json` to `data/update-backups/pre-update-<timestamp>.json` (newest five retained), tagging each snapshot with the digest + image reference of the container that was running at the time so a future rollback can pair settings with the matching image.
3. `fiestaupdater` validates the token, captures the running container's image **digest and reference**, runs `docker compose pull fiestaboard && docker compose up -d --no-deps fiestaboard`, and the new image takes over.
4. The sidecar persists the previous digest + image reference plus the outcome to `/var/lib/fiestaupdater/last-update.json` and serves it on `GET /last-update`.
5. If the user later wants to revert, they call the main API's `POST /system/update/rollback` (typically via the Settings UI). That endpoint reads the recorded digest+image from a chosen snapshot, restores the snapshot's settings via `BackupService`, and asks the sidecar's `POST /rollback` to retag the digest back onto the original image reference and `docker compose up -d --no-deps --force-recreate` the service.
6. The user's browser sees the API connection drop, polls `/health`, and reloads when the rolled-back version answers.

> Updates are **not** rolled back automatically. The user controls when (and whether) to revert, so a temporarily-flaky probe never undoes a successful upgrade.

## Endpoints

| Method | Path           | Auth   | Description                                |
|--------|----------------|--------|--------------------------------------------|
| GET    | `/healthz`     | none   | Returns `{"status":"ok"}`                  |
| GET    | `/version`     | none   | Returns the current image and digest of the managed service |
| GET    | `/last-update` | none   | Returns the result of the most recent `/update` or `/rollback` attempt (`status`, `action`, `previous_digest`, `completed_at`, …). Returns `{"status":"none"}` when no attempt has been made. |
| POST   | `/update`      | Bearer | Pulls the latest image and recreates the service. Returns 202 immediately. Records the pre-update digest+image so it can be passed back to `/rollback` later. |
| POST   | `/rollback`    | Bearer | Retags the digest given in the JSON body (`{"digest":"sha256:…","image":"repo:tag"}`) onto the supplied image reference and force-recreates the service. The digest must already be present locally — typically because the user is rolling back to the version they were running before the last `/update`. |

## Security model

- **No host port published.** The listener is reachable only from other containers on the same compose network (`fiestaboard` is the only intended caller).
- **Bearer token** generated per-install by `entrypoint.sh`, stored in `data/.fiestaupdater-token`, and shared between `fiestaboard` and `fiestaupdater` via env.
- **Hardcoded service allow-list.** The compose service name is read from `FIESTAUPDATER_SERVICE` *and* validated against `^[a-z0-9_-]+$` before being passed to `docker compose`. No user input is ever interpolated into a shell command.
- **`/rollback` payload validation.** The supplied `digest` is required to match `^sha256:[a-f0-9]{64}$` and the supplied `image` must match a strict Docker-reference allow-list before either is passed to `docker tag`. The body is also size-capped (8&nbsp;KiB).
- **Token comparison via SHA-256 hash** to mitigate timing-attack surface.
- **`GET /last-update` is unauthenticated** because it only reports the outcome of the most recent attempt and contains no credentials. Authenticated routes (`POST /update`, `/rollback`, `/restart`, `/shutdown`) still require the bearer token.

## Configuration

| Env var                              | Default                          | Description                              |
|--------------------------------------|----------------------------------|------------------------------------------|
| `FIESTAUPDATER_TOKEN`                | *(required)*                     | Shared bearer token. Sidecar refuses to start without one. |
| `FIESTAUPDATER_PORT`                 | `8765`                           | Listen port on the compose network.      |
| `FIESTAUPDATER_COMPOSE_FILE`         | `/compose/docker-compose.yml`    | Compose file to act on (mount it in).    |
| `FIESTAUPDATER_SERVICE`              | `fiestaboard`                    | The single service name we will update.  |
| `FIESTAUPDATER_STATE_DIR`            | `/var/lib/fiestaupdater`         | Where `last-update.json` is persisted.   |

## Required mounts

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - ./docker-compose.hub.yml:/compose/docker-compose.yml:ro
```

## Building

The image is multi-arch (`linux/amd64` + `linux/arm64`) and built by `.github/workflows/build-fiestaupdater.yml`. To build locally:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t fiestaboard/fiestaupdater:dev fiestaupdater/
```

## Tests

POSIX/bats tests live in `fiestaupdater/tests/`. Run with:

```bash
bats fiestaupdater/tests/
```
