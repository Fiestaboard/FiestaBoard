# FiestaUpdater

A tiny companion sidecar container that performs in-place updates of the main `fiestaboard` container by pulling the newest image and recreating the service via the host Docker socket.

This replaces our prior reliance on Watchtower, which was archived in December 2025.

## How it works

1. The main `fiestaboard` API exposes `POST /system/update`.
2. That handler proxies to `POST http://fiestaupdater:8765/update` over the internal compose network with a shared bearer token. Before proxying, the API also snapshots `data/*.json` to `data/update-backups/pre-update-<timestamp>.json` (newest five retained) so configuration can be rolled back alongside the image.
3. `fiestaupdater` validates the token, captures the running container's image **digest and reference**, runs `docker compose pull fiestaboard && docker compose up -d --no-deps fiestaboard`, and the new image takes over.
4. The sidecar then probes `http://fiestaboard:3000/api/health` for up to 60&nbsp;s (configurable). If the probe never returns 200, the sidecar **automatically rolls back** by retagging the saved digest onto the original image reference and `docker compose up -d --force-recreate`-ing the service so the user is left on a known-good version.
5. The outcome is written to `/var/lib/fiestaupdater/last-update.json` and exposed via `GET /last-update`. The main API surfaces it in `GET /system/update/status` as `last_update_status` (`success`, `rolled_back`, etc.).
6. The user's browser sees the API connection drop, polls `/health`, reloads when the new (or rolled-back) version answers, and shows whatever `last_update_status` reports.

## Endpoints

| Method | Path           | Auth   | Description                                |
|--------|----------------|--------|--------------------------------------------|
| GET    | `/healthz`     | none   | Returns `{"status":"ok"}`                  |
| GET    | `/version`     | none   | Returns the current image and digest of the managed service |
| GET    | `/last-update` | none   | Returns the result of the most recent `/update` attempt (`status`, `previous_digest`, `failed_digest`, `rolled_back_to`, `completed_at`, …). Returns `{"status":"none"}` when no attempt has been made. |
| POST   | `/update`      | Bearer | Pulls the latest image, recreates the service, probes `${FIESTAUPDATER_PROBE_URL}` for up to `${FIESTAUPDATER_PROBE_TIMEOUT_SECS}` seconds, and rolls back on probe failure. Returns 202 immediately. |

## Security model

- **No host port published.** The listener is reachable only from other containers on the same compose network (`fiestaboard` is the only intended caller).
- **Bearer token** generated per-install by `entrypoint.sh`, stored in `data/.fiestaupdater-token`, and shared between `fiestaboard` and `fiestaupdater` via env.
- **Hardcoded service allow-list.** The compose service name is read from `FIESTAUPDATER_SERVICE` *and* validated against `^[a-z0-9_-]+$` before being passed to `docker compose`. No user input is ever interpolated into a shell command.
- **Token comparison via SHA-256 hash** to mitigate timing-attack surface.
- **`GET /last-update` is unauthenticated** because it only reports the outcome of the most recent attempt and contains no credentials. Authenticated routes (`POST /update`, `/restart`, `/shutdown`) still require the bearer token.

## Configuration

| Env var                              | Default                          | Description                              |
|--------------------------------------|----------------------------------|------------------------------------------|
| `FIESTAUPDATER_TOKEN`                | *(required)*                     | Shared bearer token. Sidecar refuses to start without one. |
| `FIESTAUPDATER_PORT`                 | `8765`                           | Listen port on the compose network.      |
| `FIESTAUPDATER_COMPOSE_FILE`         | `/compose/docker-compose.yml`    | Compose file to act on (mount it in).    |
| `FIESTAUPDATER_SERVICE`              | `fiestaboard`                    | The single service name we will update.  |
| `FIESTAUPDATER_PROBE_URL`            | `http://${SERVICE}:3000/api/health` | URL probed after `up -d`. Rollback fires if it never returns 200. |
| `FIESTAUPDATER_PROBE_TIMEOUT_SECS`   | `60`                             | How long to wait for the probe to succeed before rolling back. |
| `FIESTAUPDATER_PROBE_INTERVAL_SECS`  | `2`                              | Pause between probe attempts.            |
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
