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
from fastapi.testclient import TestClient

from src.api_server import app, cors_settings

# A third-party origin the operator never configured.
EVIL = "https://evil.example"


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


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
