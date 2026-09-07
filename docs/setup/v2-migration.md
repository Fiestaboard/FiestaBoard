---
sidebar_position: 5
description: "Upgrade guide for migrating from FiestaBoard V1 to V2. Covers multi-device support, multi-board management, and API changes."
keywords: [FiestaBoard V2, migration guide, upgrade, breaking changes, Vestaboard Note, multi-board]
---

# V2 Migration Guide

FiestaBoard V2 introduces **multi-device support** and **multi-board management**. This guide covers every breaking change and what you need to do to migrate from V1.

:::note
V2 is fully backward compatible for existing single-board Flagship setups. Existing pages default to `device_type: "flagship"` automatically.
:::

:::caution Breaking: Single-container architecture
V2 replaces the previous two-container setup with a single unified container. The web UI port changed from **8080 → 4420** and the API is no longer exposed on its own dedicated port. See the [Docker Architecture Migration](#docker-architecture-migration) section below.
:::

## What's New in V2

| Feature | Description |
|---------|-------------|
| **Vestaboard Note support** | Create pages for the compact Note (15×3) alongside the Flagship (22×6) |
| **Multi-board management** | Add, name, and configure multiple physical boards from the Settings page |
| **Per-board color settings** | Set each board's physical color (black or white) |
| **Device-aware page editor** | The WYSIWYG editor and live preview automatically adapt to the target device's dimensions |
| **Device tabs in Pages** | The Pages section now has **Flagship** and **Note** tabs |
| **Heart character on Note** | Character code 62 renders as ❤ on Note (vs. ° degree on Flagship) |
| **Plus character** | Character code 46 (`+`) is now supported |
| **Device-aware send** | Pages are sent to the board using the correct dimensions for their device type |

---

## Breaking Changes

### 1. Pages now have a `device_type` field

Every page now has a `device_type` of either `"flagship"` or `"note"`.

**Existing pages**: automatically assigned `device_type: "flagship"` — no action required.

**New pages** created via the API must include `device_type` if targeting a Note:

```json
{
  "name": "My Note Page",
  "device_type": "note",
  "template": ["Line 1", "Line 2", "Line 3"]
}
```

If `device_type` is omitted, it defaults to `"flagship"`.

---

### 2. Settings API: `/settings/board` — updated request body

The `PUT /settings/board` endpoint previously accepted only a `board_type` field. In V2, it accepts `boards` (new format) or `devices` (backward-compatible list of device types).

**V1 request body:**

```json
{ "board_type": "vestaboard" }
```

**V2 request body options:**

| Option | Description |
|--------|-------------|
| `boards` | Full board instance objects (new format — see the [full board instance example](#example-full-board-instance)) |
| `devices` | List of device type strings: `["flagship"]`, `["flagship", "note"]` |
| `board_type` | Still accepted for backward compatibility |

**Example — set devices using the compatibility format:**

```json
{ "devices": ["flagship", "note"] }
```

#### Example — configure a full board instance {#example-full-board-instance}

```json
{
  "boards": [{
    "name": "Living Room",
    "device_type": "flagship",
    "board_color": "black",
    "api_mode": "local",
    "host": "192.168.0.11",
    "local_api_key": "your_api_key"
  }]
}
```

**V2 response** now returns the full board settings object instead of just `{ board_type }`.

---

### 3. New board management API endpoints

Two new endpoints manage multiple board instances:

#### `POST /settings/board/add`

Add a new board instance.

```bash
curl -X POST http://localhost:4420/api/settings/board/add \
  -H "Content-Type: application/json" \
  -d '{
    "device_type": "note",
    "name": "Office Note",
    "board_color": "white"
  }'
```

**Request body fields:**

| Field | Type | Description |
|-------|------|-------------|
| `device_type` | string | `"flagship"` or `"note"` (required) |
| `name` | string | Display name for this board |
| `board_color` | string | `"black"` or `"white"` |
| `api_mode` | string | `"local"` or `"cloud"` |
| `host` | string | Board IP address (local mode) |
| `local_api_key` | string | Local API key |
| `cloud_key` | string | Cloud Read/Write key |

#### `DELETE /settings/board/{board_id}`

Remove a board instance by its UUID.

```bash
curl -X DELETE http://localhost:4420/api/settings/board/abc123-...
```

---

### 4. Setup wizard — device and color selection

The setup wizard's **Board Setup** step now includes:

- **Device type** — choose Flagship (22×6) or Note (15×3)
- **Board color** — choose Black or White

If you're already set up, these settings can be changed any time from **Settings → Boards**.

---

## Docker Architecture Migration

This is the biggest infrastructure change in V2. FiestaBoard moved from two separate containers to a single unified container.

### What changed

| | V1 | V2 |
|---|---|---|
| **Architecture** | Two containers | One container |
| **Web UI URL** | `http://localhost:8080` | `http://localhost:4420` |
| **API URL** | `http://localhost:8000` (direct) | `http://localhost:4420` (same port, proxied via nginx) |
| **API Docs** | `http://localhost:8000/docs` | `http://localhost:4420/api/docs` |
| **docker compose services** | `fiestaboard-api` + `fiestaboard-ui` | `fiestaboard` |
| **Dockerfile** | `Dockerfile.api` + `Dockerfile.ui` | `Dockerfile` (unified) |
| **Volumes** | Separate source mounts per service | `./data:/app/data` only |
| **NEXT_PUBLIC_API_URL env var** | Required (pointed UI at API port) | Not needed (handled by nginx) |

### V1 → V2 service diagram

**V1 (two containers)**

```text
Browser → http://localhost:8080 → fiestaboard-ui (Next.js)
                                         ↓ NEXT_PUBLIC_API_URL
Browser → http://localhost:8000 → fiestaboard-api (FastAPI)
```

**V2 (single container)**

```text
Browser → http://localhost:4420 → nginx
                                    ├── /api/* → FastAPI (internal :8000)
                                    └── /*     → Next.js (internal :3001)
```

### Migration steps

1. **Stop V1 containers and remove old volumes:**

   ```bash
   docker compose down
   ```

2. **Pull V2 code:**

   ```bash
   git pull
   ```

3. **Remove `NEXT_PUBLIC_API_URL` from your `.env`** if present — it is no longer used.

4. **Start V2:**

   ```bash
   docker compose up -d --build
   ```

5. **Update any bookmarks or firewall rules** — the web UI is now on port **4420** (not 8080).

6. **Update any direct API clients** that called `http://your-server:8000` to use `http://your-server:4420` instead. All API paths remain the same.

:::tip
Your `data/` directory (pages, schedules, settings) is fully preserved — it is still mounted at `./data:/app/data`.
:::

### Port mapping summary

| Service | V1 Port | V2 Port |
|---------|---------|---------|
| Web UI | 8080 | 4420 |
| API (direct) | 8000 | ~~not exposed~~ (proxied at :4420) |
| API Docs | 8000/docs | 4420/docs |

### Docker image names

V1 published two separate container images. V2 replaces them with a single unified image:

| V1 (deprecated) | V2 |
|---|---|
| `ghcr.io/fiestaboard/fiestaboard-api:latest` | `fiestaboard/fiestaboard:latest` |
| `ghcr.io/fiestaboard/fiestaboard-ui:latest` | _(removed — included in the unified image)_ |

If you were pulling the V1 images, switch to the new image name. The old image names will not receive updates.

### Using pre-built images (optional)

V2 introduces a `docker-compose.hub.yml` for using pre-built images from Docker Hub — no local build required:

```bash
docker compose -f docker-compose.hub.yml up -d
```

---

## Upgrading

### Understanding your data

Before upgrading, it helps to know where your data lives.

:::important Your data is on the host, not inside the container
FiestaBoard stores all configuration, pages, schedules, and settings in a `data/` directory on your **host machine**. This directory is bind-mounted into the container at `/app/data`. As long as you point the new V2 container at the same host path, all your data is preserved automatically.
:::

The `data/` directory contains:

- `config.json` — board connection settings, plugin config, general settings
- `pages.json` — all your saved pages
- `schedules.json` — schedule entries
- `settings.json` — board settings, transition settings, polling intervals

V2 reads this data on first boot and auto-migrates it:

- Existing pages get `device_type: "flagship"` added automatically
- Board connection settings (from `.env` or `config.json`) are migrated to the new multi-board format
- Silence schedule times are converted to UTC
- Legacy feature configs are migrated to plugin format

No manual data conversion is needed.

### From a running V1 instance (docker compose)

1. **Pull the latest code:**

   ```bash
   git pull
   ```

2. **Remove `NEXT_PUBLIC_API_URL` from `.env`** if it exists — it is no longer needed.

3. **Rebuild and restart** (the old two containers are replaced by one):

   ```bash
   docker compose down
   docker compose up -d --build
   ```

4. **Update your bookmarks** — the web UI is now at `http://localhost:4420` (was port 8080).

5. **Open the web UI** at `http://localhost:4420` — your existing pages will appear under the **Flagship** tab, and your board configuration is preserved.

6. **Optional**: Visit **Settings → Boards** to set your board's device type and color, or to add a Note if you have one.

### From Portainer, Synology, Unraid, or standalone Docker

If you deploy containers through a management UI (Portainer, Synology Container Manager, Unraid Docker) or raw `docker run` commands rather than `docker compose`, follow these steps:

1. **Find your data directory on the host.** In your V1 setup, the `fiestaboard-api` container has a bind mount at `/app/data`. Find the corresponding host path:

   - **Portainer**: Go to Containers → `fiestaboard-api` → scroll to Volumes. Note the host path (e.g., `/home/you/fiestaboard/data` or `/volume1/docker/fiestaboard/data`).
   - **CLI**: Run `docker inspect fiestaboard-api --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}'`

2. **Back up the data directory** (recommended):

   ```bash
   cp -r /path/to/your/data /path/to/your/data-backup
   ```

3. **Stop and remove both V1 containers** (`fiestaboard-api` and `fiestaboard-ui`).

4. **Deploy the new unified container** using image `fiestaboard/fiestaboard:latest`:

   - **Volume**: Mount the **same host data path** from step 1 to `/app/data`
   - **Port**: Map host port `4420` to container port `3000`
   - **Environment variables**: Copy the same env vars from your old `fiestaboard-api` container (or use the same `.env` file). Remove `NEXT_PUBLIC_API_URL` if present.
   - **Restart policy**: `unless-stopped` (recommended)

   Example with `docker run`:

   ```bash
   docker run -d \
     --name fiestaboard \
     --restart unless-stopped \
     -p 4420:3000 \
     -v /path/to/your/data:/app/data \
     --env-file /path/to/your/.env \
     fiestaboard/fiestaboard:latest
   ```

5. **Verify**: Open `http://your-server:4420` — your pages and settings should be there.

6. **Clean up**: Once confirmed, remove the old V1 images to free disk space:

   ```bash
   docker image rm ghcr.io/fiestaboard/fiestaboard-api:latest
   docker image rm ghcr.io/fiestaboard/fiestaboard-ui:latest
   ```

7. **Update bookmarks and firewall rules** — web UI is now on port **4420** (was 8080), API is on port **4420** (was 8000).

### From the `.env` file (manual setup)

Your `.env` connection variables (`BOARD_API_MODE`, `BOARD_LOCAL_API_KEY`, `BOARD_HOST`, `BOARD_READ_WRITE_KEY`) continue to work as before. V2 reads them on startup and migrates them into the new multi-board settings format automatically.

---

## Page Dimensions Reference

| Device | Rows | Columns | Total Characters |
|--------|------|---------|------------------|
| **Flagship** | 6 | 22 | 132 |
| **Note** | 3 | 15 | 45 |

---

## Character Code Changes

| Code | V1 Behavior | V2 Behavior |
|------|-------------|-------------|
| 46 | Undefined | `+` (Plus) |
| 62 | `°` on all devices | `°` on Flagship, `❤` on Note |

---

## Next Steps

- [Page Editor](/docs/features/page-editor) — Learn about device-specific pages
- [API Endpoints](/docs/reference/api-endpoints) — Full API reference
- [Character Codes](/docs/reference/character-codes) — Updated character code table
