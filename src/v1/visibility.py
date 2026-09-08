"""What a consumer sees, and where everything else went.

Measured on ``next`` before this module existed: **231 published operations,
0 routes using ``include_in_schema=False``**. 179 of them have no caller
outside ``web/src``. The published OpenAPI document was the browser's private
RPC surface, and a newcomer was asked to find the front door inside it.

``/v1`` is that front door — 31 operations over four nouns. This module is
what makes it findable, by taking everything else out of the published
document:

* :func:`hide_internal_operations` marks every non-``/v1`` operation
  ``include_in_schema=False``. **This is a documentation change and nothing
  else.** Every hidden route keeps its path, its methods, its handler, its
  status codes and its response bodies; ``include_in_schema`` is read when
  building the OpenAPI document and by nothing in the request path. Proven by
  test rather than asserted here — ``tests/test_internal_schema.py`` calls a
  sample of hidden routes and compares the answers.
* Two legacy operations stay visible, because the published documentation
  already names them and a reader following those docs must still be able to
  find them: ``POST /send-message`` and ``POST /refresh``. Both are flagged
  ``deprecated`` and carry ``Deprecation`` and
  ``Link: rel="successor-version"`` headers naming their v1 equivalents.
* :func:`build_internal_openapi` republishes the full document at
  ``/api/internal/openapi.json``. Hidden must not mean gone: the web team
  still needs a contract, and ``/check-types`` still needs a schema to diff
  Pydantic models against TypeScript.

Consumer-visible total: **33**.

Why a sweep rather than 197 decorator edits
-------------------------------------------
The rule is "``/v1``, plus two named exceptions", and a rule is better spelled
once than restated 197 times where it can drift on the 198th route. A new
internal router is hidden the day it lands with no reviewer having to
remember; a new *consumer* operation is a deliberate ``/v1`` path. The
alternative — a keyword argument on every decorator — is 197 places for the
policy to be wrong and nothing that fails when one of them is.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import routing as fastapi_routing
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from .openapi import build_openapi

#: ``(method, path)`` of the operations that stay in the published document
#: even though they are not ``/v1``. Both are named in
#: ``docs/reference/api-endpoints.md`` and in the front page of ``/api/docs``,
#: so hiding them would break a documented path for a reader following the
#: docs as written. Both advertise their v1 successor on every response.
PUBLIC_LEGACY_OPERATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/send-message"),
        ("POST", "/refresh"),
    }
)

#: Where the full document is served. Behind nginx (which strips ``/api``)
#: that is ``/api/internal/openapi.json``.
INTERNAL_SCHEMA_PATH = "/internal/openapi.json"

INTERNAL_SCHEMA_TITLE = "FiestaBoard Internal API"

INTERNAL_SCHEMA_DESCRIPTION = """\
**Not a consumer API. No compatibility promise. Do not build against this.**

Every operation the app serves, including the ones hidden from
`/api/openapi.json`. It exists for two readers:

* the web UI, which is the only caller of most of these paths and needs a
  contract for `web/src/lib/api/*`;
* `/check-types`, which diffs the Pydantic models behind these paths against
  the TypeScript interfaces in `web/src/lib/api.ts`.

The API a script, an integration or a person with `curl` should use is `/v1`,
published at `/api/openapi.json` and documented at `/api/docs`. Paths in this
document may change or disappear in any release.
"""


class _AlwaysInSchema(fastapi_routing.RouteContext):
    """A route context that reports itself as documented, whatever the route.

    ``get_openapi`` skips a route whose ``include_in_schema`` is false, and
    offers no way to ask it not to. It does, however, accept a sequence of
    ``RouteContext`` objects instead of routes — that is its own public
    signature — and a context resolves its attributes through
    ``__getattr__``. Overriding the one attribute with a property is enough
    to build the full document **without mutating a single route**.

    The alternative, flipping ``include_in_schema`` back on and restoring it
    afterwards, would mean the app briefly serves a different public schema
    than it did a microsecond earlier, and FastAPI >= 0.130 caches an
    effective-route snapshot per included router that a bare attribute write
    does not invalidate — so the flip would not even work. This does.
    """

    @property
    def include_in_schema(self) -> bool:
        return True


def iter_api_routes(routes: Any, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Yield ``(served_path, route)`` for every ``APIRoute`` in the tree.

    FastAPI >= 0.130 wraps ``include_router()`` results in an internal
    ``_IncludedRouter`` node that carries the router's prefix and exposes no
    ``path`` of its own, so the leaf routes below it have *unprefixed* paths.
    Recursing through ``include_context`` and accumulating the prefix is what
    turns ``route.path`` into the path the app actually serves — the same walk
    ``tests/test_route_inventory.py`` does, for the same reason.

    A ``Mount`` (the MCP sub-app) is deliberately not descended into: its
    routes belong to that app and publish no OpenAPI operations here.
    """
    for route in routes:
        include_context = getattr(route, "include_context", None)
        if include_context is not None:
            yield from iter_api_routes(
                include_context.included_router.routes,
                prefix + (include_context.prefix or ""),
            )
            continue
        if isinstance(route, APIRoute):
            yield prefix + route.path, route


def is_consumer_operation(path: str, route: APIRoute) -> bool:
    """True when *route* belongs in the published, consumer-facing document."""
    if path == "/v1" or path.startswith("/v1/"):
        return True
    return any((method, path) in PUBLIC_LEGACY_OPERATIONS for method in route.methods or ())


def hide_internal_operations(app: Any) -> list[APIRoute]:
    """Take every non-consumer operation out of the published document.

    Idempotent, and returns the routes it hid so a caller can count them.

    Must run **after** every router is included and **before** anything builds
    or serves a document: FastAPI caches an effective-route snapshot per
    included router, keyed on a version counter that an attribute write does
    not bump. ``mount_v1`` is the last statement in ``src/api_server.py`` for
    exactly that reason. ``app.openapi_schema`` is cleared here as well, so a
    document built earlier in the process cannot survive as the published one.
    """
    hidden: list[APIRoute] = []
    for path, route in iter_api_routes(app.routes):
        if is_consumer_operation(path, route):
            continue
        route.include_in_schema = False
        hidden.append(route)
    app.openapi_schema = None
    return hidden


def build_internal_openapi(app: Any) -> dict[str, Any]:
    """The full document — every operation, hidden or not.

    Built over :class:`_AlwaysInSchema` views of the app's routes, so it reads
    the live route table and mutates nothing. Not cached: this is a
    development-tooling endpoint whose whole value is being current.
    """
    contexts = [
        _AlwaysInSchema(context.route, context._route_context)
        for context in fastapi_routing.iter_route_contexts(app.routes)
    ]
    return build_openapi(
        app,
        routes=contexts,
        title=INTERNAL_SCHEMA_TITLE,
        description=INTERNAL_SCHEMA_DESCRIPTION,
    )


def mount_internal_schema(app: Any) -> None:
    """Serve the full document at :data:`INTERNAL_SCHEMA_PATH`.

    Registered the same way FastAPI registers ``/openapi.json`` itself — a
    plain Starlette route with ``include_in_schema=False`` — so it is a
    sibling of the document it serves rather than operation 232 inside it.
    """

    async def internal_openapi(request: Any) -> JSONResponse:
        return JSONResponse(build_internal_openapi(app))

    app.add_route(
        INTERNAL_SCHEMA_PATH,
        internal_openapi,
        methods=["GET"],
        name="internal_openapi",
        include_in_schema=False,
    )
