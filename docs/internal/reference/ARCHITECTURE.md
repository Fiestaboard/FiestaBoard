# Backend architecture

Internal engineering reference for the reworked backend. Not published to
fiestaboard.app.

The 2026-09 audit of the rework counted the cost honestly: request hops from
entry to disk went from 1 to 4, and the number of concepts a contributor has
to hold in their head went from about six to about twenty. Those are real
costs and they are not going away — the single 11k-line module they replaced
was cheap to read and impossible to change safely. What *was* missing is this
document. Everything below is a concept you will meet in the first week.

## The shape of a request

```text
HTTP request
   │
   ▼
src/api_server.py ─── the app object, middleware, lifespan, and the
   │                  eleven deprecated plugin-specific handlers
   ▼
src/<domain>/routes.py ─── APIRouter(tags=["<domain>"]); HTTP concerns only:
   │                       status codes, response_model, HTTPException
   ▼
src/<domain>/service.py ─── the domain's behaviour; raises *domain* errors,
   │                        never fastapi.HTTPException
   ▼
src/<domain>/storage.py ─── a JsonStore over one file under data/
   │
   ▼
data/<domain>.json
```

Four hops, one responsibility each. Three rules keep them honest, and
`tests/test_layering_ratchet.py` enforces all three **for the domains listed
in `tests/layering_manifest.json`, and only those**:

| Rule | id | What it checks |
| --- | --- | --- |
| A service may not import `fastapi` | `service_no_fastapi` | No module in `src/<domain>/` other than `routes.py` / `*_routes.py` / `middleware.py` imports `fastapi` or `starlette` |
| A router may not open a file | `router_no_file_io` | No `open()`, `Path.read_*`/`write_*`, `json.load`/`dump`, `os`/`shutil` filesystem verb, or import of a storage module / `src.atomic_io` / `src.paths` in a transport module |
| A router may not hold domain logic | `router_no_domain_logic` | A **size proxy**: every module-level function in a transport module stays within 15 body statements and cyclomatic complexity 8 |

Enforced today: **`auth`, `backup`, `config_api`, `mqtt`, `network`, `oauth`,
`outputs`, `schedules`, `system`, `transitions`, `triggers`**. Everything else —
including `pages`, `collections`, `panels`, `settings`, `board_api` — is
**unenforced**, and most of it does not currently comply: the 2026-09 audit
counted ~1,600 lines of domain logic living in thirteen routers. A domain
joins the list in the PR that makes it comply, never by loosening a rule
until it passes. The ratchet is a floor that only moves up.

`config_api`, `system` and `transitions` joined by moving ~790 lines out of
their routers: `src/config_api/service.py` is new (the domain had no service
module at all), the transition frame loops and board routing went to
`src/transitions/service.py`, and the update-apply and rollback workflows went
to `src/system/update_service.py`, which also stopped importing `fastapi`.
No rule was loosened and no exception was recorded to admit any of them.

The third rule is a proxy and its docstring says plainly what it does and
does not catch — logic sharded across ten small helpers passes; a dense
one-line comprehension passes. Read it before trusting a green run as proof
of good layering.

`src/plugins/` is a special case: it keeps rule 1 (via
`tests/test_plugins_decoupled.py`, which calls the shared checker) but is not
in the manifest, because its router still fails rule 3.

## The layers, one paragraph each

**`src/api_server.py`** builds the FastAPI app, mounts every router and owns
the lifespan (start the display service, start MQTT, start the update poller).
As of the `/pages/ai` slice it holds **no** handler for a live domain: every
non-deprecated route in the app now belongs to a tagged router under the
conventions ratchet. Nothing else should import it — see *Seams* below.

Two kinds of thing legitimately stay in it. The **background-loop state** —
the `_service_running` flag, the thread handle, `_shutting_down`,
`run_service_background` — is server lifecycle, and `mock.patch` sets the
attribute on the module you name, so relocating a module global would kill
~30 live patch sites for nothing. `src/display_runtime.py` owns the *seam*
instead: a probe reads the flag, `set_loop_controls` registers the writers,
and `src/service_api/routes.py` never sees the state. The other is the
**eleven deprecated plugin-specific routes** (`/baywheels/*`, `/muni/*`,
`/stocks/*`, `/traffic/*`, `/transit/cache/status`) — routes that serve one
plugin each, which CLAUDE.md says must not be in `src/` at all. They have no
consumer, they are `deprecated=True` in the schema, and #1915 tracks removing
them; extracting a router for code we intend to delete would be motion, not
progress. When #1915 lands, `api_server.py` stops serving routes entirely.

**Routers (`src/<domain>/routes.py`)** are the only place HTTP appears.
Every route declares `response_model=`, a typed request body, the error
statuses it can raise, and `201` when it creates something. Those four rules
are enforced per domain by `tests/test_api_conventions_ratchet.py`; see
[API_CONVENTIONS.md](API_CONVENTIONS.md). What a router must *not* do —
persistence, and decision-making — is a separate per-domain ratchet,
`tests/test_layering_ratchet.py`, with its own manifest and its own opt-in
list.

**Services (`src/<domain>/service.py`)** hold the behaviour and are callable
from anywhere — a route, an MCP tool, the display loop, a test. They raise
domain exceptions (`PageNotFound`, `PluginError`) which the router maps to
status codes through one table per domain, and they never import `fastapi` —
`service_no_fastapi` above is what stops that regressing in an enforced
domain.

**Storage (`src/storage/`)** is one kernel: `JsonStore` gives every store an
`RLock`, an atomic write, and ordered `schema_version` migrations. Every
default path resolves through `src.paths.get_data_dir()`, the single seam
that honours `FIESTABOARD_DATA_DIR`. See
[PERSISTENCE.md](PERSISTENCE.md) for the write contract and for why there is
deliberately no cross-process lock.

## The display engine

The engine is a 1 Hz loop that *decides*, and per-board workers that *send*.
This split is the single most consequential change in the rework: before it,
one board's 120-second transition froze the loop, the silence detector and
every other board.

```text
tick thread (1 Hz)                      per-board send workers
──────────────────                      ──────────────────────
resolve what each board should show
   │
fetch only the plugins that are
referenced or drive a trigger
   │
render (skipped when nothing the
template depends on has changed)
   │
diff against what the board shows
   │
enqueue ──────────────────────────────► board 1 worker ── latest-wins queue
   │                                     board 2 worker ── independent
returns in ~0.1 ms
```

Names you will meet:

- **`BoardRuntime`** — per-board state: its client, its worker, its last
  render memo.
- **`OutputDriver`** (`src/outputs/driver.py`) — the Protocol every board
  driver satisfies (every board's driver is an `OutputPluginDriver` around
  its output plugin's instance): the surface the engine and API routes
  actually use.
  Reach for a member of it (or the board's `OutputRuntime`), never a
  client's private attribute; `tests/test_output_driver_protocol.py` holds
  the count of private peeks at zero.
- **`OutputRuntime`** (`src/outputs/runtime.py`) — core-owned send policy for
  one board, created by its `BoardRuntime` and bound to the client. Today it
  holds the per-board **send lock** (re-entrant) and the **cancel token**: a
  new send signals the in-flight run's token *before* waiting on the lock,
  then installs a fresh token, so a running transition is preempted rather
  than waited out and a stale signal never cancels the next run. The engine
  calls `preempt()` at enqueue time for the same reason. It also owns the
  board's **frame cache** (`src/outputs/frames.py`): the device-level dedupe
  cache every client checks before a write (what the board is known to
  show), and the **last-frame store** — the grid last actually sent and
  when, written on every successful write and never cleared by a forced
  re-send. **External-write detection** (#1946) is `observe_read()` over
  that cache: two consecutive read-backs that disagree with an unchanged
  cache mean someone else wrote the board. Sub-unit caches stay in the
  driver: a local note array keeps one per tile so a retry re-posts only
  the tiles that failed. And it **drives transitions**
  (`OutputRuntime.render`; a client's `render()` is a thin delegate). A
  native transition is a `NativeTransition` (`src/outputs/transitions.py`)
  forwarded only to a driver that declares the strategy in
  `native_transitions` — Vestaboard local and local note arrays declare all
  six; RW Cloud, note-array Cloud and virtual boards declare none and get a
  plain write. A `plugin:<id>` transition runs only with the beta flag on
  and a driver whose `animation` capability is not `"none"`: the runtime's
  `TransitionRunner` sends each frame through the driver's plain send under
  the run's cancel token, paced by the driver's declared floor. Every driver
  today is `"stream"` (frame-at-a-time); `"sequence"` (one timed upload)
  is reserved for the first device that needs it. A driver's plain
  `send_characters` is a runtime write too (`OutputRuntime.write()`): called
  from outside a run — a debug blank, an MQTT message, an identify flash —
  it preempts the in-flight transition and takes the lock; called from
  inside one (a transition's frames) it only re-enters the lock.
- **The runtime factory** (`src/outputs/factory.py`) — the only place a
  driver is built. `build_driver()` is for saved boards and is called only
  by `DisplayService` when it builds a board's live runtime; every route,
  executor and integration reaches a saved board through
  `DisplayService.runtime_for(board_id)` (or `display_runtime.live_driver`),
  so the welcome message, the live editor, detect-size, identify and the
  debug probes share the engine's lock, cancel token, frame cache and floor.
  `draft_driver()` is for connection details that are not saved yet (the
  credential probe, identify of an unassigned tile): a throwaway on a
  private runtime. `tests/test_runtime_for_board.py` holds construction
  sites outside the factory at zero. Both doors resolve the board to an
  **output** first.
- **The output registry** (`src/outputs/registry.py`) — every kind of
  device FiestaBoard drives, by output id. Two are first-party: `vestaboard`
  (Local API, RW Cloud, note-array Cloud, local note-array tiles) and
  `fiestapanel` (a TV's in-memory board). Both are **output plugins** in
  their own repositories (`Fiestaboard/fiestaboard-output--vestaboard`,
  `--fiestapanel`: root `__init__.py`, `manifest.json`,
  `output/device-models.json`, `tests/`, README and SETUP), importing core
  only through `src.plugins` (`tests/test_first_party_output_imports.py`).
  The image carries them in the **output seed** at the commits
  `outputs.lock.json` pins, and `src/outputs/first_party.py` loads them from
  there (as `plugins.<id>`, the seed copy's tree digest checked against the
  lock on every load; `FIESTABOARD_DEV_OUTPUT_<ID>` points one at a local
  checkout instead, `docs/internal/development/FIRST_PARTY_OUTPUTS.md`)
  through the output-plugin path the first time the registry is asked for.
  Only an id core drives itself and the lock pins as loadable is
  first-party; an installed plugin with either id is refused before it is
  imported, and the seed never installs them as plugins. They are never
  beta-gated, never replaceable (`plugin=False`), each instance built from the board's legacy flat fields
  by the plugin's `config_from_board` (settings v4 moves them), driven by
  `OutputPluginDriver` in **first-party mode** (inline writes, no budget or
  breaker, unanticipated errors propagate) with `OutputHttp.for_first_party`
  (the `requests` module calls the old clients made), so the wire goldens
  hold byte for byte. `GET /outputs` presents them exactly as before
  (`tests/golden/outputs/first_party_presentation.json`); their settings
  screens and board-settings action dispatch stay core's until P4d. Each
  entry carries a builder
  (only the factory calls it) and the output's **capabilities** —
  `technology` (`split_flap` | `led_matrix` | `screen`), `delivery`
  (`push` | `pull`), `animation` and `native_transitions` — the most the
  output offers in any configuration; a driver narrows them for its own
  connection. A board's output is **stored** since settings v4 (with its
  `output_config`; see `PERSISTENCE.md`), written for existing boards by the
  v3 -> v4 migration with the same rule that resolves a dict naming none:
  an explicit `output` key wins, then `api_mode == "virtual"` is
  `fiestapanel` (legacy virtual note-array panels included), else
  `vestaboard`. An explicit id the registry does not
  know builds no driver (`UnknownOutputError`, recorded as the board's init
  error) — never a Vestaboard in its place. `GET /settings/board` and the
  v1 board summaries expose the derived `output`. Each live runtime knows its
  output (`OutputRuntime.output_id`), and core decides by the registry's
  capabilities: the UI-only output target skips every board whose
  `delivery` is not a literal `"pull"` (an unknown output is hardware —
  fail closed).
- **Output hooks** (`src/outputs/hooks.py`) — what core asks an output
  instead of knowing its device. Per output, on the registry entry:
  `discover(timeout)`, `diagnostics` (the board section of the network
  diagnostics plus its advice) and named custom `actions`. Per board, on the
  driver: `check_connection()` → a `ConnectionCheck` (success, a failure
  class — `auth`, `unreachable`, `timeout`, `server_error`,
  `unexpected_status`, `bad_response`, `blocked` — message,
  troubleshooting), `read_back` (`supported`, `cost`: `cheap` | `network`,
  `suggested_interval_s`; the board-state poll picks the cloud interval for
  a `network` read) and `connection_label` (MQTT `board_api_mode`). The
  Vestaboard answers are its plugin's (`fiestaboard-output--vestaboard`:
  discovery, diagnostics, connection verdicts, the `enable_local_api` action
  with its CodeQL-recognised SSRF block); core's `src/outputs/vestaboard/`
  keeps only the board-settings action dispatcher. `fiestapanel` declares no
  hooks. The legacy
  routes — `/config/board/scan`, `/config/board/test`,
  `/config/board/enable-local-api`, `/debug/network-diagnostics` — stay and
  delegate, response shapes unchanged. The MQTT device `model` is the
  primary board's output name. `tests/test_vestaboard_output_hooks.py`
  ratchets the Vestaboard transport literals left anywhere in `src/` (count
  only goes down; Phase 4 takes it to zero).
- **Output plugins** (`plugin_type: "output"`, contract v1-beta) — a third
  plugin kind: a display device. The loader never constructs one; it keeps
  the class (an `OutputPluginBase` subclass, `src/outputs/plugin_base.py`)
  and the manifest, and registers an output beside the built-ins
  (`src/outputs/plugin_registration.py`; a plugin may not take a built-in's
  id). A board naming the plugin as its `output` gets its own instance,
  `cls(board_id, output_config)`, opened at build and closed when the board's
  runtime is dropped; the `OutputPluginDriver` adapter
  (`src/outputs/plugin_driver.py`) makes it an `OutputDriver`, so the
  runtime's lock, cancel token, floor (by the plugin's `device_key()`),
  dedupe and last-frame store apply unchanged, and an `animation: sequence`
  output receives a frame-driven transition as one `write_sequence` upload.
  The manifest's `output` block (`src/outputs/output_manifest.py`) declares
  `output_api` (outside this core's range → refused at load), FiestaUI
  `device_models` and an optional `character_set` — validated against
  FiestaUI's vendored JSON Schemas (`src/outputs/fiestaui.py`) and built-in
  data (vendored once, for outputs and the LED renderer alike, in
  `src/fiestaui/`; provenance and hashes in its `provenance.json`); a declared set is materialised at load by core's one materialiser,
  `src.led.charsets.materialize_character_set` — plus the transport facts (`delivery`,
  `min_interval_ms`, `read_back`, `native_transitions`) and the
  `settings_schema` of the board's `output_config`, whose `secret` fields are
  masked in the API and restored on save (`src/outputs/output_config.py`).
  Only **third-party** output plugins (registry or git URL, and not in the
  seed) are behind `beta.output_plugins_enabled`; with it off their boards
  stay down. First-party outputs — built-ins, plugins bundled in `plugins/`,
  and the seed's loadable outputs whichever copy runs — are always on: the
  loader decides once (`PluginLoader._register_output_locked` →
  `OutputDefinition.beta_gated`), and `GET /outputs`,
  `GET /outputs/available`, `POST /outputs/{id}/install` and
  `POST /outputs/{id}/boards` all read that one flag. `GET /outputs/available`
  and `POST /outputs/{id}/install` (`src/outputs/install.py`) back the setup
  wizard's first step: installed, then seeded, then registry outputs. The
  published author contract is `docs/development/output-plugins.md` (pull
  viewers: `output-stream-api.md`; landing page: `integrations-overview.md`).
- **The output seed and the `output_api` gate** (plan D8) — a board never
  goes dark because of its plugin. The image carries a read-only seed
  (`/opt/fiestaboard/seed/outputs`, `FIESTABOARD_OUTPUT_SEED_DIR`) of the
  first-party outputs pinned in `outputs.lock.json` (repo, commit,
  `output_api`, tree digest; `loadable: false` = device data only), fetched
  and verified at **build** time by `scripts/seed_outputs.py`
  (`src/outputs/seed.py`) — never at runtime. At boot the registry installs
  from the seed any output a board names that is not installed (offline; a
  plain git checkout, so it updates normally). `output_api` is enforced at
  three points: the update check (`check_plugin_update_available` reads the
  incoming manifest and refuses before anything is pulled; an output plugin
  is never updated blind), install/update (`update_external_plugin` /
  `_install_and_verify`: an output plugin's update that fails verification
  or does not load is reset to its previous commit, and that commit is
  remembered in `config.json`'s `refused_plugin_updates` so the hourly check
  does not offer it again until a newer commit appears —
  `src/plugins/update_refusals.py`), and load (an output
  plugin's precedence is **valid installed copy → seed**: an installed copy
  whose `output_api` is unsupported, that does not import, or that fails its
  install self-check loads the seed copy instead, reported on
  `GET /plugins/errors`). The seed is never put in `plugins/` — built-ins
  always win, so a seeded plugin there could never update. Uninstalling an
  output plugin a board uses is refused (fail closed if the boards cannot be
  read).
- **Third-party output safety** (`src/outputs/breaker.py`, Phase 2.4) —
  applied by `OutputPluginDriver` only; the in-tree drivers are untouched.
  Each plugin write runs on a thread of its own under a **write timeout**
  (30 s default; a manifest's `output.write_timeout_ms` may lower it, never
  raise it): when it runs out core stops waiting, marks the write failed and
  fires the run's cancel token — threads cannot be killed, the same model as
  `SEND_WAIT_TIMEOUT`. A **circuit breaker**, keyed by output and
  `device_key()` like the floor, opens after 3 consecutive failed writes
  (raised, timed out, or reported failed; a partial write does not count)
  and refuses writes for 300 s without calling the plugin, then lets one
  probe through. `OutputPluginDriver.last_write_error` says why, and the
  engine's and the manual-write executors' failure messages carry it.
- **Boards for output plugins** (plan D5, Phase 2.5) —
  `POST /outputs/{output_id}/boards` (`src/outputs/routes.py` →
  `src/outputs/service.py`) creates a board for an installed output plugin as
  one of the device models its manifest declares; Vestaboards keep
  `POST /settings/board/add` and FiestaPanels `POST /panels`. The content
  grid comes from the model (`src/outputs/geometry.py`): `cells` as
  declared, `pixels` from the glyph box of FiestaUI's vendored
  `led-fonts.json` (`(W+spacing)//(glyph+spacing)` per axis; Pixoo 64 at 3x5
  = 10x16), `panel`/`note_array` from the request. A grid below the 3x15
  Note floor (or above the panel ceiling) is **refused** there, before the
  board's geometry is resolved — `clamp_grid` would otherwise inflate a
  32x8 matrix's 1x8 to 3x15. The board is stored with an explicit `output`,
  `output_config` and `device_model`, as a custom `panel` grid;
  `BoardInstance` no longer coerces a plugin board's `panel` to `flagship`
  (a legacy Vestaboard claiming `panel` still falls back, unchanged). Board
  responses (`GET /settings/board`, `/v1/boards`) carry the resolved FiestaUI
  `device_model` and `charset` ids (`src/outputs/board_profile.py`; `null`
  for a FiestaPanel until its per-render-style models are vendored).
- **Pull delivery** (plan D4) — a pulled board's frame is its runtime's
  last-frame store. `GET /panel/{id}/frame` serves
  `OutputRuntime.displayed_frame(rows, cols)` with core's **stale-shape
  refusal** (a frame whose shape no longer matches the board's configured
  grid is served as no frame), and deleting or re-fitting a panel
  **releases** the board's frames (`display_runtime.release_board_frames`)
  before the rebuild. The virtual client keeps no frame state of its own.
- **Rich cells: one parse, projected per output** (plan D15/D17/D19,
  `src/outputs/cells.py`) — the markup string stays canonical (templates,
  APIs, the dedupe cache and render memo key on it). Each board's driver
  carries its **resolved character set** (`board_profile.board_character_set`;
  output plugins only — the built-in drivers carry none). A set is **rich**
  when it has colour spans, block spans or icons (the LED sets); then, and
  only then, the engine renders the board's template with
  `extended_markup=True` (`PageService.preview_page`/`render_page` →
  `TemplateEngine.render_lines`; such a render skips the preview cache) and
  `project_message` parses the content once into the 0–71 flap projection
  plus a `RichCellFrame` (FiestaUI `BoardToken[][]`, every token through the
  set's `charset_fallback`, tiles normalised to numeric codes). A split-flap
  board (a Vestaboard set, a FiestaPanel, no set) gets
  `text_to_board_array` exactly as before, and its render call carries no
  new keywords. An output plugin opts into rich frames by overriding
  `OutputPluginBase.write_cells`; core then sends rich frames there and
  dedupes colour-aware (`FrameCache.matches_frame`, FiestaUI
  `richTokensEqual`), and a frame-driven transition's landing frame carries
  the cells (its intermediate frames stay 0–71). `GET /panel/{id}/frame`
  adds `cells` only for a frame that has them; `POST /templates/render`
  with `board_id` renders for that board and reports `charset` +
  `charset_issues` (`src.led.charsets.validate_message`, FiestaUI
  `validateMessage` parity, proven against `charset-golden.json`). Nothing
  is cached across renders, so a set whose `version` changes is never
  projected stale. Every send path projects the same way
  (`cells.project_for_output` / `extended_markup_kw`): the engine, v1
  `/message` (text, lines, page_id), `render_message` (`/send-message`, MCP),
  MQTT `send_message`, `/templates/render/live`, `/pages/{id}/send`, the
  active-page immediate send and `/displays/{type}/send`. Case: the parse
  keeps case, and the set's fallback uppercases only what a set without
  `mixedCase` cannot draw; the flap projection always uppercases, so
  split-flap output is unchanged. Markup a set lacks stays in the stored
  template; only the projection falls back.
- **The output-plugin author API** (`src/plugins/__init__.py`) — one import
  surface: the contract, `BoardToken` / `cells_from_codes` /
  `characters_to_message`, and `src.led`'s renderer and transitions.
  `OutputPluginBase.http` (`src/outputs/http.py`) is the only way a plugin
  reaches its device: `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` is checked before
  every request (no socket opens for a fenced host), a request without a
  timeout gets `(3.05, 10)`, redirects are never followed, and a request
  after the run's cancel token fired raises `RequestCancelled` (the driver
  binds the write's token with `http.cancel_scope`). `setup=True` marks a
  request that is not the board write (reset, brightness). Core binds what
  it resolved for the board (`bind_board`): `device_model`,
  `character_set` (materialised), `board_geometry`. A plugin that overrides
  `write_transition(before, after, transition, *, cancel)` receives every
  change of its board as before/after rich frames plus
  `resolve_led_transition(choice, device_model)` — the choice is the write's
  strategy when it names an LED transition id, else the model's default;
  `"none"`, no known previous frame or an unchanged frame snap through
  `write_cells`. Plugins implementing only `write_sequence` are driven as
  before.
- **`WriteResult`** (`src/send_outcome.py`; `SendOutcome` is an alias) —
  a write's verdict: `(success, was_sent)`, the throttle verdict, and
  `partial` + `failed_regions` for a write that reached only part of the
  board (a local note array with a failed tile). `POST /v1/boards/{board}/message`
  answers such a write 502 with the regions in a structured detail
  (API_CONVENTIONS.md).
- **The send floor** (`src/outputs/floor.py`) — the minimum spacing between
  writes to one *device* (15 s for Vestaboard's RW and note-array Cloud
  APIs; local boards are unfloored). A driver declares the length
  (`min_send_interval_ms`) and its identity (`device_key()`: host+port, or
  a hash of the cloud credential — never the credential); core keeps one
  process-wide registry keyed by that identity. So a board re-save, which
  rebuilds the client, does not reset the window, and a throwaway client an
  API route builds for the same board (welcome, live render) sees it too.
  A slot is reserved before the write and given back if the write fails —
  except an upstream HTTP 429, which is reported as throttled (with its
  `Retry-After`, else the floor) and keeps the device closed.
- **`BoardSendWorker`** — one thread per board with a **latest-wins** queue:
  a newer frame supersedes a queued older one, and callers waiting on the
  superseded frame are adopted onto the newer one. Never bypass it; a direct
  send races the worker.
- **The dedupe cache** — the engine's own, one level up from the runtime's
  frame cache: the rendered content and page id each board is showing. The tick reads
  it to decide whether to send at all. It is written by the worker *before*
  the in-flight key is retired, and the tick snapshots the in-flight key set
  once per pass, so a job completing mid-pass can never make both guards read
  stale (#1900).
- **The render memo** — `(fingerprint, content, page_id)`. The fingerprint
  covers the referenced plugins' data and the config generation, so an
  unchanged tick skips the render entirely. It re-checks its own content
  against the live dedupe cache before it is trusted, which is why every
  existing cache-invalidation site invalidates the memo for free.
  The fingerprint enters each plugin's payload as a hash computed once on the
  `PluginResult` that `PluginBase` cached, not by re-encoding the
  payload, and the fingerprint itself is memoised per board **size** inside
  the per-tick context cache. Both matter: without them, deciding "nothing
  changed" cost one full `json.dumps` of every referenced payload per board
  per tick. The memo is per-size and never global, because board-aware plugins
  legitimately return different data per geometry.
- **Silence and pause** are per board, resolved through `src/board_guards.py`.
  Every send path asks; both guards degrade to "not blocked" and log rather
  than raising, because a guard that raises turns an unrelated failure into a
  blackout.

## Plugins

Plugins are data sources. `PluginRegistry` loads them, `PluginService`
orchestrates them, and the engine fetches only the ones a rendered template
actually references (plus any that drive a trigger).

Two properties are load-bearing and easy to break:

- **The registry lock is never held across the fetch fan-out.** The registry
  snapshots its enabled-plugin list, releases, and then fetches.
  `tests/test_registry_lock_discipline.py` fails if that inverts — it is a
  deadlock, and no other test would see it.
- **A wedged plugin cannot starve the healthy ones.** Fetches run on one
  shared bounded pool, in-flight dedupe caps each plugin at one worker, and a
  circuit breaker takes a repeatedly-timing-out plugin out of rotation.
  Without the breaker, eight distinct wedged plugins were enough to block
  every plugin's data. The breaker, the in-flight dedupe and the fetch itself
  are all keyed by `(plugin_id, board_key)` — one plugin on one geometry —
  and they must stay that way: keyed by `plugin_id` alone, two boards charged
  two timeouts per tick and one healthy geometry cleared the streak a wedged
  one was accumulating.
- **`CONTEXT_BUILD_TIMEOUT_SECONDS` must stay below the poll interval.**
  `build_template_context` blocks the service thread that also runs the 1 Hz
  silence-boundary detector, so a budget equal to the tick period lets one
  slow plugin consume a whole tick *and* delay silence entry by that long.
- **An already-cached plugin is read on the calling thread**, not dispatched
  to the pool. A fully cached tick therefore never enters `futures_wait` and
  can never pay the fetch budget for a plugin it was not going to talk to.

## Operations: the chat drives the MCP server

`src/ops/` is the named operation set, and `src/mcp_server.py` is the one
place every operation is described and served. The in-app chat does not
have tools of its own: it calls the in-process MCP server through
`src/ai/mcp_bridge.py`, so external MCP clients and FiestaBot use the same
tool names, arguments, descriptions and annotations.

```text
browser drawer ──POST /pages/ai/chat (SSE)──► src/ai/agent.py (server-side loop)
                                              │  model call: src/ai/chat.py stream_model
                                              │  tool catalog + execution: src/ai/mcp_bridge.py
                                              ▼
                                     src/mcp_server.py  list_tools() / call_tool()  ◄── /api/mcp/ (external clients)
                                              ▼
                                     src/ops/executors.py ──► services
```

- `src/ai/agent.py` — one user turn: as many model calls and tool
  executions as it needs, streamed as one SSE stream. A `tool_call` frame is
  emitted *before* a tool runs and a `tool_result` after, which is what the
  web app narrates.
- `src/ai/mcp_bridge.py` — the only chat-side module that imports `mcp`;
  descriptors in, outcomes out. Lazy, so boot never pays the import.
- `src/ai/tool_catalog.py` — the prose the model is taught, generated from
  the MCP tool list; and the validator the fence parser runs.
- `src/ai/transcript.py` — the client replays a structured transcript
  (assistant `tool_calls`, `tool` outcomes); this renders it for the model
  exactly as the loop rendered its own steps.
- `src/ai/chat_tools.py` — the one chat-only tool that is deliberately not
  MCP: `ask_user` (answered in the browser). `trigger_system_update` used to
  live here; it is a real MCP tool now, next to `restart_system` and
  `shutdown_system`.
- `src/ops/executors.py` — still the one implementation per write
  operation; MCP tools call them. `src/ops/teaching.py` generates the
  instruction text from the defining modules so it cannot rot.

The MCP tool **annotations** decide policy, not a list in the chat:
`readOnlyHint` tools run freely mid-turn; `destructiveHint` tools
(`delete_*`, `uninstall_plugin`, `remove_board`, `delete_panel`, the Wi-Fi
disconnect/forget tools and the system actions `trigger_system_update` / `restart_system` /
`shutdown_system`)
end the stream with `done{reason: "awaiting_approval"}` and run only when the
client re-POSTs a `resume` approving them. `ask_user` ends it with
`awaiting_input`. `tests/test_mcp_annotations.py` pins the sets.

Two switches relax that pause (#2021): the install's `approval_mode`
setting on the AI block (`PUT /settings/ai`, `"ask"` | `"auto"`) and the
request's `approval.auto_approve_destructive` flag (the conversation's
"don't ask again"). Either lets a destructive call run without pausing —
its `tool_call` frame then carries `auto_approved: true` — except for the
**system tier**, `SYSTEM_GATED` in `src/ops/registry.py` (`restart_system`,
`shutdown_system`, `trigger_system_update`), which pauses in every mode and
is flagged `system_gated: true` on the wire so the client can hide the
"don't ask again" action. The `update_setting` executor refuses
`approval_mode` outright: the assistant cannot change its own approval
policy.

The previous design — a hand-written chat op grammar, six browser-side ops
(`replace_page`, `apply_patch`, `navigate_to_*`, …) and `POST /ai/operations`
as the execution seam — is retired in favour of this; the endpoint and
`src/ops/grammar.py` remain only until the web client stops calling them.

## Seams: why `src.api_server` imports are counted

Historically, tests patched `src.api_server.<name>` for everything, so an
extracted router had to import `src.api_server` *inside each handler* to keep
those patches steering it. Serving one request then dragged the whole app
module back into the process, and the audit counted those call-time imports
rising 4.2× through Phase 1.

The fix is per domain: move the collaborator to a real module
(`src/board_guards.py`, `src/display_runtime.py`, `src/log_store.py`), have
both the router and `api_server` import it, and repoint the tests. Two rules
follow from that:

1. **A shared accessor cannot be deleted until its last consumer converts.**
   Until then, a fixture stubs *both* paths rather than picking one.
2. **New collaborators get a real module, never parameter-passing.** Extend
   the three above rather than inventing a fourth pattern.

Each converted domain carries a `tests/test_<domain>_decoupled.py` that fails
if the router regains an `api_server` import (the last six share
`tests/test_tail_routers_decoupled.py`).

Not every collaborator has a router to move with. Three had to be given a
home of their own by the last slice: `characters_to_message` went to
`src/board_chars.py` (three callers in three modules asked the app module for
a pure formatting function), the welcome card to `src/board_api/welcome.py`,
and the SSRF URL guard to `src/plugin_support/url_guard.py`. That last one
moved **byte-for-byte on purpose**: CodeQL's `py/full-ssrf` query recognizes
the exact shape of its scheme allowlist, `ipaddress` check and `is_global`
gate, so "tidying" it would delete a security gate rather than a duplication.
`pyproject.toml` gives every file lifted out of `api_server` that module's
ruff ignore set for the same reason.

`src/board_state.py` is the same idea one level up. Four surfaces answer
"what is on the board" — `GET /board/current-message`, the unauthenticated
`GET /panel/{panel_id}/frame` a TV polls every 2s (which has since moved to
the runtime's last-frame store, above), the MCP
`get_board_content` tool and `GET /v1/boards/{board}` — and each used to
carry its own copy of the cache selection, drifting in small ways (only one
could live-read, only one reported a source, only one honoured the virtual
board's shape guard). `read_board_state(board_id, want=...)` is now the
single selection, and it answers two intents: `want="board"` (what the flaps
show — the poll cache first) and `want="sent"` (what FiestaBoard last
displayed or sent, immediately — the panel viewer's question, which never
consults the poll cache). After that: a virtual board's own memory, else what
the client last sent, else empty — with the `source` that says which.
`read_board_state_live` adds the network read `/board/current-message` may
do, off the loop only when it actually happens. Boards resolve through
`DisplayService.runtime_for` (the id's own runtime first, the sentinel-keyed
primary only for the settings primary's id). The routes and the tool keep
only presentation, and nothing outside that module reads
`_polled_characters` or `_last_characters`. `GET /pages/current-display` is
*not* a fifth copy: it answers which page should be showing (intent), not
what the flaps show (state). `tests/test_board_state_contract.py` pins every
value each surface answers, recorded before the consolidation.

## Where the tests draw the lines

| Corpus | Pins |
| --- | --- |
| `tests/golden/engine/` | Exact send sequences for scripted scenarios — value-level, so a duplicate or reordered send fails |
| `tests/golden/responses/` | Response *shapes* per domain |
| `tests/test_<domain>_contract.py` | Response *values* — ids, ordering, error strings. Shape goldens provably missed a secret-masking regression; these exist because of it |
| `tests/golden/storage/` | On-disk bytes per store |
| `tests/golden/api_routes.json` | The route table, so a "pure move" can be proven to move nothing |
| `tests/conventions_manifest.json` | Which domains the four API rules are enforced on |
| `tests/test_data_dir_isolation.py` | That the suite never writes to the real `data/` |

A pure move must leave `api_routes.json` byte-identical. A conversion updates
the contract file deliberately, with a comment naming each change.

## Reading order for a new contributor

1. This file.
2. [API_CONVENTIONS.md](API_CONVENTIONS.md) — the four rules and how they are
   enforced.
3. `src/collections/` — the smallest fully-converted domain; routes, service,
   storage and contract test all fit in one sitting.
4. [PERSISTENCE.md](PERSISTENCE.md) — the write contract.
5. `src/main.py::check_and_send_for_board` — one pass of the engine.
