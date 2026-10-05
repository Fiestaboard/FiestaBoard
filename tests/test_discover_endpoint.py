"""``GET /discover``: how fiestaboard.app/find recognises a board.

The find page runs on https://fiestaboard.app and probes addresses on the
visitor's network. For it to list a board, the route must answer without a
session and must let that one origin read the response, whatever CORS policy
the operator chose. It must not hand out anything ``/health`` does not
already, beyond the install's name when sign-in is off.

The suite-wide autouse fixture disables auth for this file (its name does
not contain "test_auth_"), so the auth tests re-enable it explicitly.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from src import __version__
from src.api_server import CORS_ORIGINS_ENV, app, cors_settings
from src.paths import get_data_dir
from src.service_api.install_id import load_install_id
from src.service_api.routes import FIND_ORIGIN


def _client_with_cors(monkeypatch, origins: str | None) -> TestClient:
    """``app`` with its CORS middleware rebuilt for *origins* (see
    tests/test_cors_policy.py for why the import-time policy is replaced)."""
    if origins is None:
        monkeypatch.delenv(CORS_ORIGINS_ENV, raising=False)
    else:
        monkeypatch.setenv(CORS_ORIGINS_ENV, origins)
    original = list(app.user_middleware)

    def rebuilt(entry):
        if entry.cls is CORSMiddleware:
            return Middleware(CORSMiddleware, **cors_settings())
        return entry

    monkeypatch.setattr(app, "user_middleware", [rebuilt(m) for m in original])
    monkeypatch.setattr(app, "middleware_stack", None)
    return TestClient(app)


@pytest.fixture
def client(monkeypatch):
    yield _client_with_cors(monkeypatch, None)
    app.middleware_stack = None


@pytest.fixture
def restricted_client(monkeypatch):
    """An operator who allow-listed only their own dashboard."""
    yield _client_with_cors(monkeypatch, "http://dashboard.lan")
    app.middleware_stack = None


@pytest.fixture
def auth_enabled(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")


def _named(name: str):
    manager = Mock(get_general=Mock(return_value={"instance_name": name}))
    return patch("src.service_api.routes.get_config_manager", return_value=manager)


def test_identifies_the_server_as_fiestaboard(client):
    with _named("Kitchen"):
        response = client.get("/discover")
    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("product", "version", "name")} == {
        "product": "FiestaBoard",
        "version": __version__,
        "name": "Kitchen",
    }
    assert response.headers["cache-control"] == "no-store"


def test_install_id_is_stable_and_stored_in_the_data_dir(client):
    first = client.get("/discover").json()["id"]
    assert len(first) >= 16
    assert client.get("/discover").json()["id"] == first
    assert (get_data_dir() / ".install_id").read_text().strip() == first


def test_install_id_is_random_per_install(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert load_install_id(a) != load_install_id(b)
    assert load_install_id(a) == load_install_id(a)


def test_install_id_ignores_a_tampered_file(tmp_path):
    (tmp_path / ".install_id").write_text("<script>")
    assert load_install_id(tmp_path) == ""


def test_install_id_is_empty_when_the_data_dir_is_not_writable(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert load_install_id(missing) == ""


def test_unnamed_install_reports_an_empty_name(client):
    with _named("  "):
        assert client.get("/discover").json()["name"] == ""


def test_answers_without_a_session_when_sign_in_is_required(client, auth_enabled):
    response = client.get("/discover")
    assert response.status_code == 200
    assert response.json()["product"] == "FiestaBoard"


def test_hides_the_name_when_sign_in_is_required(client, auth_enabled):
    with _named("Kitchen"):
        assert client.get("/discover").json()["name"] == ""


def test_neighbouring_routes_stay_protected(client, auth_enabled):
    # Guard against the exemption being widened into a prefix by mistake.
    assert client.get("/discover/anything").status_code in (401, 404, 409)
    assert client.get("/status").status_code in (401, 409)


def test_find_page_can_read_it_under_the_default_cors_policy(client):
    response = client.get("/discover", headers={"Origin": FIND_ORIGIN})
    assert response.headers["access-control-allow-origin"] in ("*", FIND_ORIGIN)
    assert "access-control-allow-credentials" not in response.headers


def test_find_page_can_read_it_when_the_operator_restricts_cors(restricted_client):
    response = restricted_client.get("/discover", headers={"Origin": FIND_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FIND_ORIGIN


def test_restricted_cors_still_refuses_other_origins_elsewhere(restricted_client):
    response = restricted_client.get("/health", headers={"Origin": FIND_ORIGIN})
    assert "access-control-allow-origin" not in response.headers


def test_find_origin_is_the_published_page():
    assert FIND_ORIGIN == "https://fiestaboard.app"
