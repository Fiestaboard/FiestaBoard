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

Enforced today: **`auth`, `backup`, `config_api`, `mqtt`, `network`,
`schedules`, `system`, `transitions`, `triggers`**. Everything else —
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
- **`BoardSendWorker`** — one thread per board with a **latest-wins** queue:
  a newer frame supersedes a queued older one, and callers waiting on the
  superseded frame are adopted onto the newer one. Never bypass it; a direct
  send races the worker.
- **The dedupe cache** — what each board is currently showing. The tick reads
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

## Operations: one grammar for chat and MCP

`src/ops/` is the named operation set. Every action a model can take —
whether it arrives as a chat tool call or an MCP tool — resolves to **one**
executor, so the two surfaces cannot drift apart.

```text
chat tool call ──► POST /ai/operations ──┐
                                         ├──► src/ops/registry.execute ──► executor ──► service
MCP tool call ───────────────────────────┘
```

- `src/ops/grammar.py` — the pydantic models and the chat spelling of each op
- `src/ops/registry.py` — canonical name, chat alias, MCP alias, executor
- `src/ops/executors.py` — the one implementation per operation
- `src/ops/teaching.py` — the instruction text, **generated** from the modules
  that define the behaviour (device dimensions, colour palette, template
  filters, formula registry) so it cannot rot

Six operations stay in the browser because they act on the editor rather than
on stored state: `apply_patch`, `suggest_variables`, `navigate_to_page`,
`navigate_to_schedule`, `update_task_list`, `replace_page`. They are marked
`client_side=True` in the registry, and `tests/test_ops_wiring.py` fails if a
server-side op regains a browser-side implementation.

Wiring chat through the layer surfaced three divergences that had been live
in production: `update_schedule` wiped `end_time` on partial updates,
`update_plugin_config` replaced instead of merging, and `update_collection`
destroyed variable-mode rules. In all three the browser was wrong and the
executor was right — nothing had ever called the executor.

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
