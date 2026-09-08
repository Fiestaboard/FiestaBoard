"""Declare in the schema that this API is authenticated.

Measured on ``next``: the published OpenAPI document has **no**
``securitySchemes`` and no top-level ``security``, so a consumer reading it
cannot discover that authentication exists at all — let alone which kind.
That is not an oversight in any one route; it is structural. Authentication
is enforced in ASGI middleware (:mod:`src.auth.middleware`), not in FastAPI
dependencies, and FastAPI can only infer security from dependencies. So it
has to be stated.

Two schemes, because the app really does accept two credentials:

``apiToken``
    ``Authorization: Bearer <token>``. Created at ``POST /auth/mcp-token``
    and accepted on ``/v1/*`` and ``/mcp*``. This is the one a script uses;
    it is what makes FiestaBoard scriptable at all.
``session``
    The browser session cookie from ``POST /auth/login``, which is what the
    web UI holds.

Declared as alternatives at the document root — a request satisfies the
scheme by presenting either — so the document says what the middleware
does rather than an idealised version of it.
"""

from __future__ import annotations

from typing import Any

from fastapi.openapi.utils import get_openapi

from src.auth.service import SESSION_COOKIE_NAME

#: OpenAPI ``securitySchemes`` for the two credentials the app accepts.
SECURITY_SCHEMES: dict[str, dict[str, Any]] = {
    "apiToken": {
        "type": "http",
        "scheme": "bearer",
        "description": (
            "A FiestaBoard API token, sent as `Authorization: Bearer <token>`. Create one with "
            "`POST /auth/mcp-token` or pin one out of band with the `FIESTABOARD_MCP_TOKEN` environment "
            "variable. Accepted on every `/v1` route and on the MCP endpoint. This is the credential to use "
            "from a script: unlike the session cookie it needs no browser login flow.\n\n"
            "When no token is configured and authentication is disabled, the API is open and no credential "
            "is required — the default for a local-only install."
        ),
    },
    "session": {
        "type": "apiKey",
        "in": "cookie",
        "name": SESSION_COOKIE_NAME,
        "description": (
            "The browser session cookie issued by `POST /auth/login`. What the web UI holds. A script should "
            "use `apiToken` instead."
        ),
    },
}

#: Either credential satisfies a request; an empty requirement is not offered,
#: because "no credential" is an install-level setting, not a per-route one.
SECURITY_REQUIREMENT: list[dict[str, list[str]]] = [{"apiToken": []}, {"session": []}]

#: Tag metadata for the consumer surface. The internal domains publish 22
#: bare tag names with no descriptions; this one says what it is.
V1_TAG_METADATA: dict[str, Any] = {
    "name": "v1",
    "description": (
        "The FiestaBoard API. Four nouns — board, page, schedule, plugin — and one way to do each thing.\n\n"
        'Start here: `POST /v1/boards/primary/message` with `{"text": "HELLO"}` puts text on your board. '
        "`primary` works as a board id on every `/v1/boards/...` path, so a single-board install never needs to "
        "look one up.\n\n"
        "Every write reports what actually happened rather than merely acknowledging the request: `sent` is true "
        "only when flaps moved, and a `reason` says why when they did not."
    ),
}


def _tags_used_by(schema: dict[str, Any]) -> set[str]:
    """Every tag named by an operation the document actually contains."""
    used: set[str] = set()
    for operations in schema.get("paths", {}).values():
        for operation in operations.values():
            if isinstance(operation, dict):
                used.update(operation.get("tags", []))
    return used


def build_openapi(
    app,
    *,
    routes=None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """The app's schema, with the security it actually enforces declared.

    ``routes``, ``title`` and ``description`` override the app's own, which is
    what lets the internal document (``src/v1/visibility.py``) reuse this
    builder — the same security declaration, the same tag metadata — while
    saying plainly on its front page that it is not a consumer API.

    The declared tag list is filtered to the tags operations in *this*
    document actually use. Once the internal surface is hidden the app still
    declares twenty-two internal tag descriptions, and publishing headings for
    sections a reader cannot reach is the same noise this whole change is
    removing. Order is preserved, so the consumer surface still leads.
    """
    schema = get_openapi(
        title=title if title is not None else app.title,
        version=app.version,
        description=description if description is not None else app.description,
        routes=app.routes if routes is None else routes,
        # Prepended, not appended: Swagger renders tags in this order and the
        # consumer surface has to be the first thing a newcomer sees.
        tags=[V1_TAG_METADATA, *(app.openapi_tags or [])],
    )
    used = _tags_used_by(schema)
    schema["tags"] = [tag for tag in schema.get("tags", []) if tag["name"] in used]
    schema.setdefault("components", {})["securitySchemes"] = SECURITY_SCHEMES
    schema["security"] = SECURITY_REQUIREMENT
    return schema


def install_security_scheme(app) -> None:
    """Replace ``app.openapi`` with one that declares the security schemes.

    Idempotent: mounting twice (a test app factory, a reload) leaves one
    wrapper, not a stack of them.
    """
    if getattr(app, "_fiestaboard_v1_openapi_installed", False):
        return

    def _openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    app.openapi = _openapi
    app._fiestaboard_v1_openapi_installed = True
