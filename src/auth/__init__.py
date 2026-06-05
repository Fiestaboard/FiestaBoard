"""Authentication for the FiestaBoard control API.

This package is an *opt-in* layer that lets internet-exposed deployments
require a username + password before any state-changing endpoint is
reachable.

It is gated by the ``FIESTABOARD_AUTH_ENABLED`` environment variable
(``true``/``1``/``yes``). When disabled the middleware is a no-op so
existing local-only installs are unaffected.

Public submodules:
    - :mod:`src.auth.service`: user store, hashing, session tokens.
    - :mod:`src.auth.routes`: FastAPI router exposing ``/auth/*`` endpoints.
    - :mod:`src.auth.middleware`: ASGI middleware that enforces auth.
"""

from .service import (
    SESSION_COOKIE_NAME,
    AlreadySetup,
    AuthError,
    AuthService,
    InvalidCredentials,
    SetupRequired,
    get_auth_service,
    is_auth_enabled,
)

__all__ = [
    "SESSION_COOKIE_NAME",
    "AlreadySetup",
    "AuthError",
    "AuthService",
    "InvalidCredentials",
    "SetupRequired",
    "get_auth_service",
    "is_auth_enabled",
]
