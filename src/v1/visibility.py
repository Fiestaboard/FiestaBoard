"""What a consumer sees, and where everything else went.

Measured on ``next`` before this module existed: **231 published operations,
0 routes using ``include_in_schema=False``**. 179 of them have no caller
outside ``web/src``. The published OpenAPI document was the browser's private
RPC surface, and a newcomer was asked to find the front door inside it.

``/v1`` is that front door — 33 operations over five nouns. This module is
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
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.routing import APIRoute
from starlette.responses import HTMLResponse, JSONResponse

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


#: Names in the ``/api/docs`` definition dropdown. The internal one says what
#: it is in the dropdown itself, before anyone reads its front page.
PUBLIC_DOCS_NAME = "FiestaBoard API (v1)"
INTERNAL_DOCS_NAME = "Internal web UI API (unstable, no compatibility promise)"

#: Swagger UI assets, pinned to one exact release (the major FastAPI's own
#: page loads): the bundle and the standalone preset must match, and a floating
#: ``@5`` resolves each URL on its own.
_SWAGGER_DIST = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.34.0"
SWAGGER_JS_URL = f"{_SWAGGER_DIST}/swagger-ui-bundle.js"
SWAGGER_CSS_URL = f"{_SWAGGER_DIST}/swagger-ui.css"
SWAGGER_STANDALONE_PRESET_URL = f"{_SWAGGER_DIST}/swagger-ui-standalone-preset.js"

#: Where Swagger UI is served. Behind nginx that is ``/api/docs``.
DOCS_PATH = "/docs"
DOCS_OAUTH2_REDIRECT_PATH = "/docs/oauth2-redirect"


def offer_internal_schema_in_docs(app: Any) -> None:
    """Let Swagger UI at ``/api/docs`` switch to the internal document (#2367).

    Hiding the internal operations from ``/api/openapi.json`` left ``/api/docs``
    able to show only that document, so ~200 routes that still answer had no
    page anywhere: users upgrading from v8 saw a fraction of the API they knew
    and only a sentence in the description saying where the rest went.

    Swagger UI's ``urls`` option puts a definition dropdown in its top bar.
    The published document stays first and is the default, so a newcomer still
    lands on ``/v1``; the internal one is a deliberate pick, labelled as having
    no promise. Neither document changes, only which ones the page can load.

    ``urls`` is rendered only by ``StandaloneLayout``, whose top bar ships in
    ``swagger-ui-standalone-preset.js``. FastAPI's page loads only the bundle
    and reads the preset from ``SwaggerUIBundle.SwaggerUIStandalonePreset``,
    which the bundle does not define, so this route loads the preset and binds
    it there before Swagger UI starts. The app is built with ``docs_url=None``
    and this replaces FastAPI's two routes (the page and its OAuth2
    redirect) under the same paths and names, so the route table is unchanged.
    """
    app.swagger_ui_parameters = {
        **(app.swagger_ui_parameters or {}),
        "urls.primaryName": PUBLIC_DOCS_NAME,
        "layout": "StandaloneLayout",
    }

    def render(root: str) -> str:
        page = get_swagger_ui_html(
            openapi_url=root + app.openapi_url,
            title=f"{app.title} - Swagger UI",
            oauth2_redirect_url=root + DOCS_OAUTH2_REDIRECT_PATH,
            init_oauth=app.swagger_ui_init_oauth,
            swagger_js_url=SWAGGER_JS_URL,
            swagger_css_url=SWAGGER_CSS_URL,
            swagger_ui_parameters={
                **app.swagger_ui_parameters,
                "urls": [
                    {"url": root + app.openapi_url, "name": PUBLIC_DOCS_NAME},
                    {"url": root + INTERNAL_SCHEMA_PATH, "name": INTERNAL_DOCS_NAME},
                ],
            },
        )
        bundle_tag = f'<script src="{SWAGGER_JS_URL}"></script>'
        html = page.body.decode()
        # The two details of FastAPI's template the layout depends on: where
        # the bundle is loaded, and the presets list reading the preset off
        # SwaggerUIBundle. Without either the page renders blank.
        if bundle_tag not in html or "SwaggerUIBundle.SwaggerUIStandalonePreset" not in html:
            raise RuntimeError("FastAPI's Swagger UI page no longer has the shape the /docs route patches")
        return html.replace(
            bundle_tag,
            f"{bundle_tag}\n"
            f'    <script src="{SWAGGER_STANDALONE_PRESET_URL}"></script>\n'
            "    <script>SwaggerUIBundle.SwaggerUIStandalonePreset = SwaggerUIStandalonePreset;</script>",
            1,
        )

    # Render once now, so a FastAPI upgrade that changes the template fails
    # the app's startup (and CI) rather than serving a blank page.
    render("")

    async def swagger_ui_html(request: Any) -> HTMLResponse:
        return HTMLResponse(render(request.scope.get("root_path", "").rstrip("/")))

    async def swagger_ui_redirect(request: Any) -> HTMLResponse:
        return get_swagger_ui_oauth2_redirect_html()

    app.add_route(DOCS_PATH, swagger_ui_html, name="swagger_ui_html", include_in_schema=False)
    app.add_route(DOCS_OAUTH2_REDIRECT_PATH, swagger_ui_redirect, name="swagger_ui_redirect", include_in_schema=False)
