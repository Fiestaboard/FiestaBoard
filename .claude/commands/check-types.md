Catch drift between Python Pydantic models in `src/*/models.py` and TypeScript interfaces in `web/src/lib/api.ts`.

Use the `ts-sync-validator` agent.

Optional arguments:
- `--scope <feature>` — limit to a single module (e.g., `--scope pages`). Default: every feature module under `src/` that has a `models.py`.
- `--strict` — also flag interfaces with uncertain comparisons (unions, nested generics). Off by default.

The agent (read-only) will:
1. Prefer the live OpenAPI schema from `http://localhost:4420/api/internal/openapi.json` as ground truth — the **internal** document, not `/api/openapi.json`. Since the internal surface was hidden (`src/v1/visibility.py`), `/api/openapi.json` publishes only the 33 consumer operations, so diffing against it would silently skip almost every model the web UI uses. Falls back to AST parsing of `models.py` if the container is down.
2. Parse `web/src/lib/api.ts` for `export interface` blocks.
3. Compare per-model: missing fields, extra fields, type mismatches, optionality mismatches, casing mismatches.
4. Cross-check that every `response_model=<Model>` route in `api_server.py` has a matching TS fetch wrapper.
5. Produce a findings table grouped by feature module with file:line references on both sides.

It will not edit files — fixes are usually 1-line each in `web/src/lib/api.ts`. Re-run after edits to confirm clean.
