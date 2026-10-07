# Persistence reference

Internal engineering notes on how FiestaBoard writes the files under `data/`.
Not published to fiestaboard.app.

Every long-lived store — `config.json`, `settings.json`, `pages.json`,
`schedules.json`, `collections.json`, `panels.json`, `auth.json`,
`trigger_dismissals.json`, `.system-update.json`, `ai_conversations.json` (the
FiestaBot chat history, capped at 200 conversations, #2022) — obeys the same
three rules. This document exists
because two of them used to be enforced by convention rather than by code, and
because the third rule is deliberately *not* enforced at all.

## 1. Atomic writes

`src/atomic_io.py::write_json_atomic` stages JSON in a sibling temp file
(`<file>.<pid>.<n>.tmp`), fsyncs, then `os.replace`s it onto the target. A
crash mid-write leaves the previous contents fully intact (#1304); the partial
staging file is removed rather than leaked.

`if_changed=True` reads the target first and skips the write when the bytes
would be identical, returning whether it wrote. `ConfigManager` and
`JsonStore` both use it, so a restart that merges in no new defaults, and a
PUT that stores the value already stored, cost zero fsyncs instead of one
each. It is opt-in because a caller that writes to signal liveness must keep
writing. A read that fails for any reason answers "changed", so the failure
mode is a needless write and never a skipped one.

`config_generation` is deliberately NOT conditional on the write happening.
It means "what this process reads has moved", not "the disk moved".

Every store's default path resolves through `src.paths.get_data_dir()`, the one
seam that honours `FIESTABOARD_DATA_DIR`. `tests/test_data_dir_isolation.py` is
the guard: it constructs each store with defaults and asserts the resulting
path landed under the isolated temp dir.

## 2. Schema versions, never heuristics

Every store records an integer `schema_version` and runs ordered
`(target_version, fn)` migrations keyed on it. `CLAUDE.md` ("Page Schema
Versioning") is the contract; `src/storage/json_store.py` is the kernel that
runs it.

`config.json` was the last holdout. Its two structural migrations —
legacy `features.*` → `plugins.*`, and the `PLUGIN_ID_RENAMES` pass — were
guarded by *heuristics*: "is there a `plugins.weather` entry yet?". A heuristic
cannot distinguish "not migrated yet" from "migrated, then deliberately changed
by the user", and that produced a real bug: a plugin the user uninstalled was
silently re-created from its surviving `features.*` block on every boot,
forever.

Both now run from `src/config_manager.py::MIGRATIONS`, gated on
`CURRENT_SCHEMA_VERSION`, with a `config.json.v{N}_backup` written before the
first migration and a per-migration log line naming how many entries were
affected.

**Two config migrations are deliberately still deferred**, and cannot join the
list:

| Migration | Why it cannot run at load time |
|---|---|
| `migrate_silence_schedule_to_utc` | Needs `get_time_service()`, whose construction resolves `Config.GENERAL_TIMEZONE` and so re-enters `ConfigManager` |
| `migrate_silence_schedule_to_per_board` | Needs the configured board ids from the settings service, which reaches back into `ConfigManager` — a documented deadlock |

Both run once per process from `src.config` and keep structural guards. If
either collaborator is ever decoupled from `ConfigManager`, they should move
into `MIGRATIONS` and the guards should go.

### Rolling back past a settings migration (the downgrade bridge)

A store stamped newer than the running build is refused (`SchemaTooNewError`)
rather than read as the wrong format. For `settings.json` that refusal would
make "roll back one release" mean "the board goes dark", so
`SettingsService._run_migrations` first tries to step back: if
`settings.json.v{CURRENT}_backup` exists — the snapshot the newer build took of
*this* build's file before migrating it — the too-new file is copied to
`settings.json.v{found}_aside-<UTC timestamp>`, the backup is atomically
replaced over `settings.json`, and the backup is **deleted**. Deleting it
matters: a newer build writes its pre-migration backup only when none exists,
so a leftover would make the next upgrade-then-rollback restore this one's
stale snapshot. The swap writes `settings_restore_notice.json`, which
`GET /settings/restore-notice` serves and the web app shows as a banner naming
the aside file until `DELETE /settings/restore-notice` dismisses it. With no
usable backup the refusal stands, and its message says what to do.

This only works one release back: a build that predates the bridge still
refuses the newer file, so a settings migration ships at least one release
after the bridge (output-plugins plan D8). `tests/test_settings_downgrade_bridge.py`
pins it, and `tests/fixtures/upgrade/` (booted by `tests/test_upgrade_fixtures.py`)
holds real-shaped data directories from past releases that must keep booting to
the same wire.

### Settings v4: every board stores its output

Schema v4 (output-plugins plan D8) is the first settings migration to cross
the bridge. Each `board.boards[]` entry gains `output` and `output_config`:

| Board (v3) | `output` | `output_config` |
|---|---|---|
| has an explicit `output` | kept | kept; flat fields dropped (they never meant anything to a plugin) |
| `api_mode == "virtual"` | `fiestapanel` | `{}` (a panel renders to memory) |
| anything else | `vestaboard` | its `api_mode`, `host`, `port`, `local_api_key`, `cloud_key`, `note_array_token`, `tiles`, moved out of the top level |

`device_type`, geometry (`notes_*`, `grid_*`), name and display fields stay
top-level: they describe the content's shape, which pages and previews key
on. The migration is `_migrate_v3_to_v4` →
`src/settings/board_shape.py::migrate_board_to_v4`, idempotent per board,
logging the count; `settings.json.v3_backup` is the usual pre-migration
snapshot, and it is exactly what the bridge restores on a rollback.

The flat shape is still the public one until the Vestaboard settings screen
moves onto the plugin renderer. `board_view` projects a stored board back to
it for every response and reader (settings, `/config/board`, MCP, the
diagnostics hook, the first-party actions), with `output` and a masked
`output_config` added. Writes accept the flat shape, the v4 shape, or both (an
echoed GET): `merge_board_write` resolves them against the stored board, and
when the halves disagree the one that differs from what is stored — the one
the client edited — wins. A Vestaboard's `"***"` echoes are restored in both
halves by its plugin's rules (`restore_config`, through
`src/outputs/config_hooks.py`: tiles matched by host:port, then by position;
they carry no id), and its `output_config` is stored as the plugin normalizes
it (`normalize_config`). Core keeps the flat view's field names — its own
storage history and public shape — and takes their defaults from the plugin
(`legacy_flat_fields`).

**Rollback.** One step back, to the bridge release, boots from
`settings.json.v3_backup` and shows the restore banner; changes made on v4 stay
in the set-aside file. Further back, the older build refuses the v4 file: put
`settings.json.v3_backup` in place of `settings.json` by hand first.
`tests/test_settings_v4_output_migration.py` and the bridge module pin all of
this, including a real upgrade rolled back onto a simulated bridge build.

### Settings v5: HTTPS (Beta) is gone

Schema v5 removes the HTTPS (Beta) feature. `_migrate_v4_to_v5` drops
`beta.https_enabled` whatever its value and keeps every other beta flag; it is
idempotent and logs how many files it changed (0 or 1), with a warning when the
flag was on. An install that had it on serves plain HTTP on its usual port
(`http://<host>:4420`) after the upgrade: the entrypoint no longer swaps nginx
configs, and the image ships no `nginx.https.conf`. At startup
`src/system/legacy_https.py::remove_legacy_https_certs` deletes the two files
the old entrypoint generated, `data/certs/fiestaboard.crt` and
`fiestaboard.key`, and removes `data/certs/` only if that leaves it empty. It
deletes them only when the cert is the self-signed one FiestaBoard made
(`O = FiestaBoard` as both issuer and subject). A pair the user dropped in
under the same names, which the old beta API allowed, is kept.

**Rollback.** One step back, to a v4 build, restores
`settings.json.v4_backup` (flag included), but HTTPS comes back only on the
**second** boot. The v4 entrypoint reads `beta.https_enabled` before the API
starts, while `settings.json` is still the v5 file without the flag, so the
first boot serves plain HTTP with no certificate. The bridge then restores the
v4 settings, and the next restart generates a new certificate and switches
nginx over. `tests/test_settings_v5_https_removed.py`, the
`v10_beta_schema4_https_on` upgrade fixture and the bridge module pin the
settings half of this; the two-boot timing is the v4 entrypoint's and is not
tested here.

### Settings v6: each display owns its transition

Schema v6 (`_migrate_v5_to_v6`) removes the install-wide `transitions` block
and the `beta` block:

- Every board without a `transition` of its own gets the old block's
  `strategy`. A null strategy becomes `"none"` on a split-flap board (a
  Vestaboard or FiestaPanel, where null meant no transition); an output
  plugin's board stays unset, because unset there means its device model's
  default, which is what it ran. Every board without a speed of its own gets
  the old `step_interval_ms` / `step_size` as `transition_step_interval_ms` /
  `transition_step_size` (the speed was always install-wide, even for a
  board with its own style); an interval above 5000 ms
  (`MAX_TRANSITION_STEP_INTERVAL_MS`) is clamped. When there is no board to
  copy onto (no `board` section, an empty `boards` list, or a devices-era
  section) the transition is parked under `pending_board_transition`; the
  board loader applies it to the boards it builds (after the first-boot
  seed fills a fresh board's connection) and saves, and the save never
  writes the key. The migration never reads config.json and cannot abort,
  so the beta flags and the transition survive an unreadable config.json.
- `beta.transition_plugins_enabled` and `beta.output_plugins_enabled` move to
  `plugins`, and `beta` is deleted.

It is idempotent (a re-run finds no block, and every split-flap board
already has a transition) and logs its count: boards changed plus one per
block removed. Stored speeds above the cap are clamped on load too
(logged), and a board write is validated only on the fields it changes, so
old data never blocks a write. It never reads the environment: every save wrote the
`transitions` block, so a file without one is hand-made. The legacy
`BOARD_TRANSITION_*` env values now only seed a new split-flap display
(`default_board_transition`). The runtime reads only the board
(`SettingsService.get_transition_settings(board_id)`); a page's own
transition wins field by field (`page_transition`). `GET/PUT
/settings/transitions` is a deprecated alias for the first board's, and
`GET/PUT /settings/beta` for the two plugin flags, until v11 (both send a
`Deprecation` header and a `Link` to their successor). A page strategy the
board's driver cannot run (`driver_runs_strategy`, the rule its write path
applies) falls through to the board's own transition and speed.

**Rollback.** One step back, to a v5 build, restores
`settings.json.v5_backup` with its `transitions` and `beta` blocks; changes
made to a display's transition after the upgrade are in the set-aside file.
`tests/test_settings_v6_per_display_transitions.py`, the
`v10_beta_schema5_install_transition` upgrade fixture (and its wire golden)
and `test_a_v6_upgrade_rolled_back_to_the_v5_build_runs_the_same_transition`
pin this.

### Settings v7: display plugins need no opt-in

Schema v7 (`_migrate_v6_to_v7`) drops `plugins.output_plugins_enabled`, the
"Third-party displays (beta)" switch, whatever its value. Every installed
display (output) plugin can drive a board: bundled with the image, from the
marketplace or from a git URL. Every other plugin setting is kept. The
migration is idempotent (a re-run finds no key) and counts 1 when it removed
the key; it logs a line when the stored value was off, since display plugins
that were held back can now drive their boards.

What an output plugin runs behind is unchanged: the write timeout and
breaker (`src/outputs/breaker.py`), the network allowlist
(`FIESTABOARD_OUTPUTS_ALLOW_HOSTS`, `src/outputs/http.py`), and the
`output_api` gate and install self-check. The Vestaboard and FiestaPanel keep
their own rules (`docs/internal/development/FIRST_PARTY_OUTPUTS.md`).

On the wire the field stays until v11, deprecated: `GET /settings/plugins`
(and the deprecated `/settings/beta` alias) report `output_plugins_enabled:
true`, and a `PUT` of it is accepted and ignored. `GET /outputs` and
`GET /outputs/available` keep `beta_gated` (always `false`) and `available`
(always `true`), also deprecated. Nothing answers 409 for a display plugin
any more.

**Rollback.** One step back, to a v6 build, restores
`settings.json.v6_backup` with the stored opt-in; on the v6 build a board
driven by a display plugin the image does not carry stays down again while
that opt-in is off.
`tests/test_settings_v7_display_plugins_open.py`, the
`v10_beta_schema6_display_opt_in_off` upgrade fixture and
`test_a_v7_upgrade_rolled_back_to_the_v6_build_gets_its_opt_in_back` pin this.

## 3. A failed write is never swallowed

A store write that fails must surface. Silent partial success — the change
holds in memory, the API answers 200, and the next restart quietly undoes it —
is the failure mode this rule exists to prevent.

Closed so far: `src/settings/service.py::_save_to_file` re-raises; the backup
service aborts before overwriting when it loses its rollback copy; the SSRF
check stopped downgrading its 400 to a 200; and
`src/triggers/service.py::_save_dismissals` re-raises (it used to log and
continue, so a dismissal the user made was reported as successful while being
non-durable).

There is exactly one documented exception, and it carries a `best_effort=True`
argument at the call site so it cannot be adopted by accident: the startup
prune in `TriggerService._load_dismissals`, which rewrites the store without
already-lapsed entries. It records no user decision, the in-memory state is
already correct, and its caller is `__init__` — taking the app down on boot
over a cosmetic rewrite would be strictly worse.

Any new best-effort write needs the same treatment: an explicit argument, a
comment saying which user decision is *not* being recorded, and a test pinning
the choice.

## 4. No cross-process locking — and why that is the right call

Locking in the stores is **in-process only**: `threading.RLock` in
`JsonStore`, and `ConfigManager._file_lock`. There is no `fcntl.flock`
anywhere in `src/`. That is deliberate.

Measured against this tree (Phase 2 audit), every deployment runs exactly one
Python process against a data directory:

| Avenue | Evidence |
|---|---|
| Production container | `supervisord.conf` runs one `uvicorn` with no `--workers`; no gunicorn anywhere. Two programs in production: `api` + `nginx` |
| MQTT / MCP / display loop | Threads inside the API process (`src/mqtt/client.py` `loop_start()` + a daemon thread; `app.mount("/mcp", ...)`), not processes |
| Volume topology | Only the `fiestaboard` service binds `./data` in every compose file. The FiestaUpdater sidecar deliberately mounts only `docker.sock` and the compose file. Every variant binds host port 4420, so two instances collide on the port first |
| The updater | `docker compose up -d --no-deps` with no `order: start-first`; the recreate is stop-old → start-new. The pre-update backup is written in-process by the *old* container before the swap |
| Pi image | `fiestaboard.service` is a oneshot running `docker compose up -d` on the same single-container compose file |
| CLI scripts | No script under `scripts/` resolves the data dir or calls `write_json_atomic` / `ConfigManager()`; the seeding scripts go through HTTP so the server does the writing |
| Tests | `tests/conftest.py::pytest_configure` gives every xdist worker its own `mkdtemp`, ratcheted by `test_data_dir_is_unique_per_xdist_worker` |

`JsonStore.mutate()` already states the resulting assumption honestly: *"Use
the process-wide singleton store for a given file, and single-process
deployment, for this to hold."*

Adding `flock` would mean adding a lock whose contended path no supported
deployment can reach — untestable in production terms, and therefore
untrustworthy. **An unjustified lock is worse than a documented absence.**

### What would change the answer

Single-process is a *convention*, not an invariant. Nothing in the image
enforces it. These are the three ways a second writer could appear; if any of
them becomes real, revisit this section before writing any code:

1. **`supervisord.conf` has an extension point.** `[include] files =
   /app/conf.d/*.conf`, and the Dockerfile creates `/app/conf.d`. Nothing in
   this repo writes it, but any downstream wrapper can drop a `[program:x]`
   there and get a second process against the same `/app/data`. The Home
   Assistant add-on (a separate repo) wraps this image and supplies `/app/data`
   from HA's `addon_config` volume — it is the most likely place this is
   already happening, and it has not been inspected.
2. **A second hand-rolled container.** `docs/setup/docker-setup.md` publishes a
   plain `docker run -v "$(pwd)/data:/app/data"` recipe. A user on
   Portainer/Unraid/Synology can create a second container with a different
   name and port pointed at the same host directory. Nothing prevents it —
   there is no lockfile or pidfile in `data/`.
3. **`pytest <explicit-plugin-path>` inside the running dev container.**
   `pytest` with a path under `plugins/` never loads `tests/conftest.py`
   (pytest only collects `conftest.py` files along the ancestry from the
   rootdir down to the target), so
   `FIESTABOARD_DATA_DIR` is unset and `get_data_dir()` falls back to the live
   `/app/data`. `scripts/run_plugin_tests.py` passes explicit test dirs and
   hits the same hole. It is benign *today* only because those tests happen to
   import nothing that constructs a `ConfigManager` or a `JsonStore` — one
   plugin test that touches settings turns it into a live two-writer race. This
   is the cheapest of the three to close and does not need locking to fix.

If cross-process writing ever becomes supported, the place to add the lock is
`write_json_atomic` — `flock` the *target* file (not the staging file) around
the read-modify-write, which means the lock has to be held by the store, not by
the writer, and `JsonStore.mutate()` becomes the natural owner.
