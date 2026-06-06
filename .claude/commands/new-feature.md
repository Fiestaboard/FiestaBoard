Scaffold a new feature module across Python and TypeScript in one consistent pass.

Use the `endpoint-scaffolder` agent.

Required arguments:
- `--feature <id>` — snake_case module name (e.g., `widgets`, `playlists`)
- `--fields <spec>` — comma-separated `name:type` pairs (e.g., `"name:str,enabled:bool,priority:int"`). Supported types: `str`, `int`, `float`, `bool`, `datetime`, `list[str]`.

Optional arguments:
- `--ops <set>` — subset of `list,get,create,update,delete` (default: all five)
- `--singular <name>` — override the auto-derived singular model name

The agent (edit-capable) will:
1. Read the closest analog module (`src/pages/`, `src/schedules/`, or `src/carousels/`) end-to-end to mirror current patterns.
2. Create `src/<feature>/` with `models.py` (Pydantic v2 — full, Create, Update), `service.py`, `storage.py` (with `CURRENT_SCHEMA_VERSION = 1`), and `__init__.py`.
3. Insert FastAPI routes inline in `src/api_server.py` adjacent to the analog's routes.
4. Add TS interfaces and fetch wrappers to `web/src/lib/api.ts`.
5. Create `tests/test_<feature>.py` with one passing test and todos for the remaining ops.
6. Self-validate with `ruff`, `pytest` on the new module, and `tsc --noEmit` — fix its own snake/camel mistakes before reporting.

It will not commit. The user reviews and commits / opens a PR themselves.

After scaffolding: implement real business logic in `service.py`, build the UI under `web/src/app/<feature>/`, then run `/map-ux web --scope=<feature>` and `/stub-ux-tests` to scaffold regression coverage.
