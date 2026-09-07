# Persistence reference

Internal engineering notes on how FiestaBoard writes the files under `data/`.
Not published to fiestaboard.app.

Every long-lived store — `config.json`, `settings.json`, `pages.json`,
`schedules.json`, `collections.json`, `panels.json`, `auth.json`,
`trigger_dismissals.json` — obeys the same three rules. This document exists
because two of them used to be enforced by convention rather than by code, and
because the third rule is deliberately *not* enforced at all.

## 1. Atomic writes

`src/atomic_io.py::write_json_atomic` stages JSON in a sibling temp file
(`<file>.<pid>.<n>.tmp`), fsyncs, then `os.replace`s it onto the target. A
crash mid-write leaves the previous contents fully intact (#1304); the partial
staging file is removed rather than leaked.

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
   (pytest only walks conftests along the rootdir→target ancestry), so
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
