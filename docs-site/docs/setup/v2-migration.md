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
V2 replaces the previous two-container setup with a single unified container. The web UI port changed from **8080 → 3000** and the API is no longer exposed on its own dedicated port. See the [Docker Architecture Migration](#docker-architecture-migration) section below.
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
| `boards` | Full board instance objects (new format — see below) |
| `devices` | List of device type strings: `["flagship"]`, `["flagship", "note"]` |
| `board_type` | Still accepted for backward compatibility |

**Example — set devices using the compatibility format:**
```json
{ "devices": ["flagship", "note"] }
```

**Example — configure a full board instance:**
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
curl -X POST http://localhost:3000/settings/board/add \
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
curl -X DELETE http://localhost:3000/settings/board/abc123-...
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
| **Web UI URL** | http://localhost:**8080** | http://localhost:**3000** |
| **API URL** | http://localhost:**8000** (direct) | http://localhost:3000 (same port, proxied via nginx) |
| **API Docs** | http://localhost:8000/docs | http://localhost:3000/docs |
| **docker-compose services** | `fiestaboard-api` + `fiestaboard-ui` | `fiestaboard` |
| **Dockerfile** | `Dockerfile.api` + `Dockerfile.ui` | `Dockerfile` (unified) |
| **Volumes** | Separate source mounts per service | `./data:/app/data` only |
| **NEXT_PUBLIC_API_URL env var** | Required (pointed UI at API port) | Not needed (handled by nginx) |

### V1 → V2 service diagram

**V1 (two containers)**

```
Browser → http://localhost:8080 → fiestaboard-ui (Next.js)
                                         ↓ NEXT_PUBLIC_API_URL
Browser → http://localhost:8000 → fiestaboard-api (FastAPI)
```

**V2 (single container)**

```
Browser → http://localhost:3000 → nginx
                                    ├── /api/* → FastAPI (internal :8000)
                                    └── /*     → Next.js (internal :3001)
```

### Migration steps

1. **Stop V1 containers and remove old volumes:**

   ```bash
   docker-compose down
   ```

2. **Pull V2 code:**

   ```bash
   git pull
   ```

3. **Remove `NEXT_PUBLIC_API_URL` from your `.env`** if present — it is no longer used.

4. **Start V2:**

   ```bash
   docker-compose up -d --build
   ```

5. **Update any bookmarks or firewall rules** — the web UI is now on port **3000** (not 8080).

6. **Update any direct API clients** that called `http://your-server:8000` to use `http://your-server:3000` instead. All API paths remain the same.

:::tip
Your `data/` directory (pages, schedules, settings) is fully preserved — it is still mounted at `./data:/app/data`.
:::

### Port mapping summary

| Service | V1 Port | V2 Port |
|---------|---------|---------|
| Web UI | 8080 | 3000 |
| API (direct) | 8000 | ~~not exposed~~ (proxied at :3000) |
| API Docs | 8000/docs | 3000/docs |

### Using pre-built images (optional)

V2 introduces a `docker-compose.ghcr.yml` for using pre-built images from GitHub Container Registry — no local build required:

```bash
docker-compose -f docker-compose.ghcr.yml up -d
```

---

## Upgrading

### From a running V1 instance

1. **Pull the latest code:**
   ```bash
   git pull
   ```

2. **Remove `NEXT_PUBLIC_API_URL` from `.env`** if it exists — it is no longer needed.

3. **Rebuild and restart** (the old two containers are replaced by one):
   ```bash
   docker-compose down
   docker-compose up -d --build
   ```

4. **Update your bookmarks** — the web UI is now at **http://localhost:3000** (was port 8080).

5. **Open the web UI** at http://localhost:3000 — your existing pages will appear under the **Flagship** tab, and your board configuration is preserved.

6. **Optional**: Visit **Settings → Boards** to set your board's device type and color, or to add a Note if you have one.

:::tip
The `data/` directory is mounted as a Docker volume, so your pages, schedules, and settings survive the upgrade.
:::

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
