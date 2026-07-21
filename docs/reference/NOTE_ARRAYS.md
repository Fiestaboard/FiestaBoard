# Note Arrays reference

This is the technical reference for Note-array support: the dimensions model,
the built-in presets, custom sizing, the Cloud API transport, and the
auto-detect endpoint. For a user-facing walkthrough, see the
[Note Array setup guide](../setup/NOTE_ARRAYS.md).

The source of truth is `src/devices.py` (geometry) and `src/board_client.py`
(transport). The constants below mirror those modules.

## Dimensions model

A **Note** is the unit of a Note array:

| Constant            | Value | Meaning                              |
|---------------------|-------|--------------------------------------|
| `NOTE_COLS`         | 15    | Characters wide per Note             |
| `NOTE_ROWS`         | 3     | Characters tall per Note             |
| `MAX_NOTES_PER_AXIS`| 8     | Maximum Notes along either axis      |

An array is a grid of `notes_wide × notes_tall` Notes. Its character
dimensions are:

```text
cols = notes_wide × NOTE_COLS   (= notes_wide × 15)
rows = notes_tall × NOTE_ROWS   (= notes_tall × 3)
```

`resolve_dimensions(device_type, notes_wide, notes_tall)` returns the
`(rows, cols)` for any device type — fixed values for `flagship` (rows=6, cols=22) and
`note` (rows=3, cols=15), and the computed grid for `note_array`.

Both axes are capped at `MAX_NOTES_PER_AXIS` (8), so the largest supported
array is 8 × 8 Notes = `120 × 24` characters. The UI clamps **Notes wide** and
**Notes tall** to the range 1–8, and `BoardInstance.__post_init__` clamps the
stored values to the same range.

> **Wording:** the app displays sizes as **width × height** in characters (for
> example `60 × 3` for a 4-wide array). This reference lists Note counts as
> **W × H** as well.

## Presets

Five presets are defined in `NOTE_ARRAY_PRESETS`:

| Preset id  | Label          | Notes (W × H) | Characters (W × H) |
|------------|----------------|---------------|--------------------|
| `2_wide`   | 2 side-by-side | 2 × 1         | 30 × 3             |
| `4_wide`   | 4 side-by-side | 4 × 1         | 60 × 3             |
| `2_tall`   | 2 stacked      | 1 × 2         | 15 × 6             |
| `4_tall`   | 4 stacked      | 1 × 4         | 15 × 12            |
| `2x2_grid` | 2×2 grid       | 2 × 2         | 30 × 6             |

## Custom sizing

Any `notes_wide × notes_tall` from 1 to 8 on each axis is valid, including
sizes outside the presets (for example `3 × 2` Notes → `45 × 6`).

`is_valid_note_array_grid(rows, cols)` validates a raw character grid:

- `rows > 0` and `cols > 0`
- `rows` is a multiple of `NOTE_ROWS` (3) and `cols` is a multiple of
  `NOTE_COLS` (15)
- `rows // NOTE_ROWS ≤ 8` and `cols // NOTE_COLS ≤ 8`

## Cloud API transport

In cloud mode (`api_mode: "cloud"`, the default), note arrays use the
**Vestaboard Cloud API**, which is distinct from the older Read/Write cloud
(`rw.vestaboard.com`) used by single Flagship and Note boards.

| Property    | Value                                                   |
|-------------|---------------------------------------------------------|
| Base URL    | `https://cloud.vestaboard.com/`                         |
| Auth header | `X-Vestaboard-Token: <token>`                           |
| Send        | `POST` with body `{"characters": <grid>}`               |
| Read        | `GET`; returns `{"currentMessage": {"layout": <grid>}}` |

The `<grid>` is a `rows × cols` array of Vestaboard character codes sized to the
array. On read, `layout` may be a JSON-encoded string; FiestaBoard parses it
(`parse_read_message_payload`) and returns the decoded grid.

### Constraints

- **No transitions.** The Cloud API replaces the whole frame at once. Any
  transition `strategy` passed to `send_characters()` is stripped and ignored
  for Note-array boards.
- **Rate limit: ≥ 15 seconds between sends.** `NOTE_ARRAY_MIN_SEND_INTERVAL` is
  `15.0` seconds. `BoardClient` tracks the last send per token and silently
  skips a send that arrives too soon (returning "no change" rather than
  erroring), so the platform's refresh loop stays well-behaved.

## Local transport (per-tile fan-out)

In local mode (`api_mode: "local"` with a non-empty `tiles` list on the board),
FiestaBoard drives each Note over the standard **Local API**
(`http://<host>:<port>/local-api/message`, `X-Vestaboard-Local-Api-Key`) —
one endpoint per Note.

- **Tile model.** Each tile is
  `{"row", "col", "host", "port", "local_api_key", "enabled"}` with 0-indexed
  note coordinates, stored on the board dict (`src/devices.py`,
  `normalize_note_array_tiles` / `BoardInstance.configured_tiles`).
  Out-of-range tiles are preserved across W×H resizes and filtered at point of
  use, so shrinking an array never destroys keys. Per-tile `local_api_key` is
  masked (`"***"`) in API responses and resolved by `(row, col)` on write.
- **Send path.** `NoteArrayLocalClient` (`src/note_array_local_client.py`)
  slices the full frame with `slice_note_array_grid()` into 15 × 3 subgrids
  and fans them out concurrently, one plain local `BoardClient` per tile.
  Success requires every tile to accept its slice; after a partial failure the
  retry re-POSTs only the failed tiles (per-tile skip-unchanged caches).
  Reads stitch per-tile GETs (`stitch_note_array_grid()`) and return a grid
  only when the array is fully assigned and every read succeeds.
- **No cloud constraints.** Transitions are forwarded to every tile (each Note
  animates its slice) and the 15-second cloud throttle does not apply.
- **Identify.** `POST /settings/board/{board_id}/identify` flashes a slot's
  reading-order position (`POSITION n` / `R<row> C<col>`) on one tile
  (`{"target": "tile", "row", "col"}`) or all
  (`{"target": "all"}`), with an optional unsaved credential override
  (SSRF-guarded like `enable-local-api`). Restore is timer-free: the endpoint
  clears the board's client caches and display-loop content dedupe, so the
  next poll cycle rewrites the real frame.

## Auto-detect endpoint

`POST /settings/board/{board_id}/detect-size`

Reads the board's current layout over its own transport
(`board_client_from_board_dict`) and classifies the grid with
`classify_dimensions(rows, cols)`.

**Response** — always includes `device_type`, `rows`, `cols`. For note arrays it
also includes `notes_wide`, `notes_tall`, and `matched_preset`:

```json
{
  "device_type": "note_array",
  "rows": 6,
  "cols": 30,
  "notes_wide": 2,
  "notes_tall": 2,
  "matched_preset": "2×2 grid"
}
```

Error responses:

| Status | Cause                                                |
|--------|------------------------------------------------------|
| `404`  | Unknown board id.                                    |
| `400`  | Board is not configured (missing credentials).       |
| `422`  | Board returned no layout, or an unclassifiable grid. |

### `classify_dimensions` behavior

Given a raw `(rows, cols)`, `classify_dimensions` decides the device type in
this order:

1. **Flagship** — exactly `6 × 22` → `{"device_type": "flagship", ...}`.
2. **Note** — exactly `3 × 15` → `{"device_type": "note", ...}`.
3. **Note array** — passes `is_valid_note_array_grid` → `note_array` with
   `notes_wide = cols // 15`, `notes_tall = rows // 3`, and `matched_preset` set
   to a preset **label** when the geometry matches one of the five presets,
   otherwise `null`.
4. Otherwise it raises `ValueError` (surfaced as the `422` above).

Order matters: the exact Flagship and Note sizes are checked **before** the
note-array branch, so a single Note never classifies as a 1 × 1 array.

> **Note for the UI:** the Settings UI matches the detected `notes_wide` /
> `notes_tall` against the preset table to drive the dropdown — it does not rely
> on the `matched_preset` label string, which is a human-readable hint only.

## Local development — mock Cloud board

Note arrays talk to the Vestaboard **Cloud** API, so there's no local hardware to
point at. A bundled mock stands in — and it has a live web front-end so you can
watch and reconfigure a "board" by hand.

- **Server:** `integration-tests/mock-cloud/server.py` — a stdlib HTTP server that
  faithfully mimics `cloud.vestaboard.com` (token check, dimension + cell-code
  validation, `currentMessage.layout` reads, request history).
- **Wired up automatically:** `docker-compose.dev.yml` runs it as
  `fiestaboard-mock-cloud` and sets `VESTABOARD_CLOUD_API_URL` on the app so
  note-array boards send/read against the mock. (`BoardClient.CLOUD_NOTE_ARRAY_API_URL`
  reads that env var; unset it to use the real Cloud API.)
- **Live front-end:** open **http://localhost:19200/ui** — it renders the current
  grid as split-flap tiles (characters + color codes), shows the message count /
  last update, and lets you **Reset** the board or **reconfigure its size** at
  runtime (the 5 presets, Flagship/Note, or a custom W×H).

Typical loop: `/start` the dev stack → Settings → add a note-array board (any
token) → build/send a page → watch it land at `/ui`. Control endpoints
(`GET /mock/state`, `POST /mock/reset`, `POST /mock/configure`) back the UI and
are handy for scripted/manual testing.

## See also

- [Note Array setup guide](../setup/NOTE_ARRAYS.md) — user-facing configuration.
- `src/devices.py` — geometry constants, presets, `resolve_dimensions`,
  `classify_dimensions`.
- `src/board_client.py` — Cloud API send/read and rate limiting.
- `src/note_array_local_client.py` — local-mode per-tile fan-out client.
- `integration-tests/mock-cloud/server.py` — the mock Cloud board + its `/ui`.
- `integration-tests/mock-board/server.py` — the multi-port Local API mock
  used by the local-array e2e (`web/tests/note-array-local.spec.ts`).
