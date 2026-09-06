# REST API Conventions

Status: adopted 2026-09 (issue #1766, umbrella #1849). Applies to every new
endpoint immediately, and to existing endpoints as their domain is extracted
into a router. The 2026-08 audit found three sibling create endpoints with
three response shapes, zero 201s, `response_model` on 19 of 179 endpoints,
~30 failure responses served as HTTP 200, and both string and dict
`HTTPException.detail` payloads — these rules exist so that never regrows.

## Response shapes

- **Bare bodies.** Return the resource (or list) itself — no `{"status":
  "success", "data": ...}` envelopes. `{"status": ...}` wrappers on existing
  endpoints are grandfathered until their domain's conventions pass; new
  endpoints never add one.
- **`response_model` on every endpoint.** The route declares its Pydantic
  response model; no untyped `dict` returns. This is what keeps the TS client
  (`web/src/lib/api/`) honest — `/check-types` compares against these models.
- **Typed request models.** No `request: dict` parameters. Validation errors
  are FastAPI's standard 422.

## Status codes

- Create → **201** with the created resource.
- Delete → **200** with the deleted resource id, or **204** with no body —
  pick per domain and stay consistent within it.
- **Failures are never 200.** A handler must not answer an error with
  `{"success": false}` and HTTP 200. Client errors are 4xx, server errors
  5xx.
- Missing resource → **404**; conflict (duplicate id, env-pinned resource) →
  **409**; feature unavailable / dependency down → **503**.

## Error contract

One shape everywhere: FastAPI's `{"detail": <string>}`. When structured
detail is genuinely needed (validation lists, per-field errors), `detail` is
an object with a `message` string plus named fields — never a bare string in
one endpoint and a dict in its sibling. No stringified tracebacks in any
response (CodeQL also enforces this).

## Routers and services

- Every domain lives in `src/<domain>/routes.py` (`APIRouter`, OpenAPI
  `tags=[<domain>]`) with orchestration in `src/<domain>/service.py`;
  `src/api_server.py` is an app factory that mounts routers.
- Routes never touch another object's `_private` members — that is the
  service's job (see `PluginService.mask_config` / `clear_update_status` for
  the pattern).
- During extraction, moved handlers resolve api_server-patched names at call
  time (the `src/mqtt/commands.py` pattern) so existing test patch targets
  stay live. Follow-up: migrate patch targets to the service modules, then
  retire the call-time seams.

## Deprecation, never deletion

A reachable endpoint that must change shape or move keeps serving its old
contract through a deprecation window:

- Response headers: `Deprecation: true` and
  `Link: </successor/path>; rel="successor-version"`, plus `Sunset: <date>`
  once a removal release is chosen.
- The successor ships first; the deprecated route becomes a shim over the
  same service (see `GET/PUT /config/board`).
- Duplicate endpoints (the audit found 3× cache, 2× install, 3× "what's on
  the board") are collapsed the same way: one canonical route, shims with
  headers on the rest.
- Only provably unreachable code is deleted outright (#1747-class: no route
  decorator, no dynamic registration, no importer).

## Identifiers

- Resource ids are validated against reserved route words so
  `/plugins/{id}` cannot be shadowed by literal segments
  (`updates`, `registry`, `install`, ...). Each router owns its reserved
  list next to its routes.

## Zero-regression mechanics (how a conventions pass lands)

1. Record the domain's **response-shape golden** from current behavior
   (`tests/test_response_shape_goldens.py`, `RECORD_RESPONSE_GOLDEN=1`).
2. Extract the router as a **pure move** — golden diff must be empty.
3. Apply conventions in a separate commit — golden updated deliberately,
   old shapes still served under deprecation headers where any client could
   depend on them.
4. The route-inventory golden (`tests/test_route_inventory.py`) changes only
   with an explanation in the same commit.
