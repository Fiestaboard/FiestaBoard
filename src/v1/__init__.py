"""The consumer-facing FiestaBoard API.

`/v1` is the surface a script, an integration or a person with `curl` is
meant to use. The rest of the HTTP surface is the web UI's private RPC
channel — 179 of the 199 published operations have no caller outside
`web/src`, and the two the published docs recommend have no caller at all.
This package is the answer to "how do I put text on my board" being a
sixteen-way choice with no ranking.

Thirty-one operations over four nouns — board, page, schedule, plugin — every
one of them an adapter over a handler, service or executor that already
exists. It adds exactly one concept: `{board}` accepts the literal `primary`,
so a single-board owner never learns that boards have ids, and a multi-board
owner can finally address board 2 over HTTP at all.

Mounting
--------
`src.api_server` calls :func:`mount_v1`, which includes the router *and*
declares the API's security scheme. The declaration has to happen here rather
than on the routes because authentication is enforced in ASGI middleware
(:mod:`src.auth.middleware`), which FastAPI cannot see — without this the
published schema tells every consumer the API is unauthenticated.
"""

from __future__ import annotations

from . import routes_boards, routes_content, routes_meta, routes_plugins
from .openapi import install_security_scheme
from .router import router
from .visibility import build_internal_openapi, hide_internal_operations, mount_internal_schema


def mount_v1(app) -> None:
    """Attach the v1 surface to *app* and hide everything that is not it.

    Order matters, and each step depends on the one before it:

    1. include the ``/v1`` routes, so there is a consumer surface at all;
    2. declare the security schemes, so the document says the API is
       authenticated;
    3. mount ``/internal/openapi.json``, so the full document has somewhere
       to live *before* anything is taken out of the published one;
    4. hide every non-``/v1`` operation. Last, because it sweeps the whole
       route table — every router this module's caller included, plus the
       internal-schema route added in step 3.
    """
    app.include_router(router)
    install_security_scheme(app)
    mount_internal_schema(app)
    hide_internal_operations(app)


__all__ = [
    "build_internal_openapi",
    "hide_internal_operations",
    "install_security_scheme",
    "mount_v1",
    "router",
]
