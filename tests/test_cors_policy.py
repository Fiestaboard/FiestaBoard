"""Tests for the API's CORS policy.

The API is normally same-origin with the UI (nginx serves both), so CORS
exists only for third-party callers. Two invariants matter:

* A credentialed cross-origin grant must never be handed to an arbitrary
  origin — that turns any web page the operator visits into a client of
  their LAN board (Fiestaboard/FiestaBoard#1744).
* ``Access-Control-Allow-Origin: *`` must never be paired with
  ``Access-Control-Allow-Credentials: true``; browsers reject the
  combination outright, so it is a footgun even where it is not a hole.
"""

from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from src.api_server import CORS_ORIGINS_ENV, app, cors_settings

# A third-party origin the operator never configured.
EVIL = "https://evil.example"


@pytest.fixture
def client(monkeypatch):
    """``app`` with its CORS middleware rebuilt from a scrubbed environment.

    ``src.api_server`` calls ``load_dotenv()`` and evaluates
    ``cors_settings()`` at *import* time, so the policy baked into ``app``
    reflects whatever ``FIESTABOARD_CORS_ORIGINS`` the developer's ``.env``
    (or the CI runner's environment) happened to hold. A plain
    ``monkeypatch.delenv`` is too late to undo that. Swap in a middleware
    entry built from the clean environment and drop the cached stack so the
    next request rebuilds it, so the assertions below describe the shipped
    *default* policy rather than the ambient operator config.

    The real ``app`` — real routes, real middleware ordering — is still what
    gets exercised; only the one env-derived argument is normalised.
    """
    monkeypatch.delenv(CORS_ORIGINS_ENV, raising=False)

    original = list(app.user_middleware)
    assert any(m.cls is CORSMiddleware for m in original), (
        "app no longer installs CORSMiddleware — these tests would be vacuous"
    )

    def with_default_cors(entry):
        if entry.cls is CORSMiddleware:
            return Middleware(CORSMiddleware, **cors_settings())
        return entry

    app.user_middleware = [with_default_cors(m) for m in original]
    app.middleware_stack = None  # force a rebuild on the next request
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.user_middleware = original
        app.middleware_stack = None


def _headers(response):
    return (
        response.headers.get("access-control-allow-origin"),
        response.headers.get("access-control-allow-credentials"),
    )


# --- Emitted headers on the real app --------------------------------------


def test_arbitrary_origin_is_not_granted_credentialed_access(client):
    """An unconfigured origin must not get an origin echo + credentials."""
    r = client.get("/health", headers={"Origin": EVIL})
    allow_origin, allow_credentials = _headers(r)
    assert not (allow_origin == EVIL and allow_credentials == "true"), (
        f"reflected {EVIL} with credentials — any site could drive this board"
    )


def test_wildcard_origin_is_never_paired_with_credentials(client):
    """``*`` + credentials is invalid per the CORS spec."""
    r = client.get("/health", headers={"Origin": EVIL})
    allow_origin, allow_credentials = _headers(r)
    assert not (allow_origin == "*" and allow_credentials == "true")


def test_preflight_from_arbitrary_origin_is_not_credentialed(client):
    """The preflight for an unconfigured origin must not promise credentials."""
    r = client.options(
        "/health",
        headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"},
    )
    assert r.headers.get("access-control-allow-credentials") != "true"


def test_anonymous_cross_origin_reads_still_allowed_by_default(client):
    """Backward compatibility: the default stays open to anonymous callers."""
    r = client.get("/health", headers={"Origin": EVIL})
    assert r.headers.get("access-control-allow-origin") == "*"


# --- cors_settings() ------------------------------------------------------


def test_default_config_does_not_allow_credentials(monkeypatch):
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    settings = cors_settings()
    assert settings["allow_origins"] == ["*"]
    assert settings["allow_credentials"] is False


def test_explicit_allowlist_enables_credentials(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_CORS_ORIGINS", "https://board.example, https://other.example/")
    settings = cors_settings()
    assert settings["allow_origins"] == ["https://board.example", "https://other.example"]
    assert settings["allow_credentials"] is True


def test_wildcard_in_allowlist_drops_credentials(monkeypatch):
    """An operator writing ``*`` must not resurrect the invalid pairing."""
    monkeypatch.setenv("FIESTABOARD_CORS_ORIGINS", "*")
    settings = cors_settings()
    assert settings["allow_credentials"] is False
