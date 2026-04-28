# FiestaUpdater

A tiny companion sidecar container that performs in-place updates of the main `fiestaboard` container by pulling the newest image and recreating the service via the host Docker socket.

This replaces our prior reliance on Watchtower, which was archived in December 2025.

## How it works

1. The main `fiestaboard` API exposes `POST /system/update`.
2. That handler proxies to `POST http://fiestaupdater:8765/update` over the internal compose network with a shared bearer token.
3. `fiestaupdater` validates the token, runs `docker compose pull fiestaboard && docker compose up -d --no-deps fiestaboard`, and the new image takes over.
4. The user's browser sees the API connection drop, polls `/health`, and reloads when the new version answers.

## Security model

- **No host port published.** The listener is reachable only from other containers on the same compose network (`fiestaboard` is the only intended caller).
- **Bearer token** generated per-install by `entrypoint.sh`, stored in `data/.fiestaupdater-token`, and shared between `fiestaboard` and `fiestaupdater` via env.
- **Hardcoded service allow-list.** The compose service name is read from `FIESTAUPDATER_SERVICE` *and* validated against `^[a-z0-9_-]+$` before being passed to `docker compose`. No user input is ever interpolated into a shell command.
- **Token comparison via SHA-256 hash** to mitigate timing-attack surface.

## Endpoints

| Method | Path        | Auth   | Description                                |
|--------|-------------|--------|--------------------------------------------|
| GET    | `/healthz`  | none   | Returns `{"status":"ok"}`                  |
| GET    | `/version`  | none   | Returns the current image and digest of the managed service |
| POST   | `/update`   | Bearer | Pulls the latest image and recreates the service. Returns 202 immediately. |

## Configuration

| Env var                       | Default                          | Description                              |
|-------------------------------|----------------------------------|------------------------------------------|
| `FIESTAUPDATER_TOKEN`         | *(required)*                     | Shared bearer token. Sidecar refuses to start without one. |
| `FIESTAUPDATER_PORT`          | `8765`                           | Listen port on the compose network.      |
| `FIESTAUPDATER_COMPOSE_FILE`  | `/compose/docker-compose.yml`    | Compose file to act on (mount it in).    |
| `FIESTAUPDATER_SERVICE`       | `fiestaboard`                    | The single service name we will update.  |

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
