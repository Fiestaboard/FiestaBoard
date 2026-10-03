"""Domain errors for the OAuth module.

No status codes live here: ``src/oauth/routes.py`` owns the one table that
maps these onto HTTP (``docs/internal/reference/API_CONVENTIONS.md``,
"Services raise domain errors; routers map them to status codes").
"""

from __future__ import annotations


class OAuthError(Exception):
    """Base class for every failure the OAuth module raises."""


class ConnectionNotFound(OAuthError):
    """No installed plugin declares an OAuth connection under this id."""


class ConnectionNotConfigured(OAuthError):
    """The plugin has no client ID yet, so no flow can start."""


class FlowNotSupported(OAuthError):
    """The plugin's manifest does not declare the requested flow."""


class InvalidBoardUrl(OAuthError):
    """The address the relay should return to is missing or not a plain web address."""


class InvalidState(OAuthError):
    """The ``state`` on a callback is unsigned, tampered, expired or reused.

    ``reason`` is a short machine-readable slug safe to put in a redirect URL.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ProviderError(OAuthError):
    """The provider could not be reached or answered something unusable."""


class TokenEndpointError(OAuthError):
    """The provider's token endpoint answered with an OAuth error object.

    ``error`` is the RFC 6749 §5.2 code (``invalid_grant``,
    ``authorization_pending``, ...). The description is the provider's own
    text and is only ever logged or shown to the board's owner.
    """

    def __init__(self, error: str, description: str = "") -> None:
        super().__init__(f"{error}: {description}" if description else error)
        self.error = error
        self.description = description
