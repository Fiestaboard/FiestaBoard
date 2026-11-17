"""Native renderer contract: vendored values, conditional GET and authentication."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from src import fiestaui

PATH = "/v1/render-assets"
CACHE_CONTROL = "private, no-cache"


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


def _catalog(client):
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    return response


def test_catalog_preserves_vendored_fonts_and_flattened_charsets(client):
    body = _catalog(client).json()
    assert set(body) == {"schema_version", "revision", "source", "fonts", "character_sets"}
    assert body["schema_version"] == 1
    assert body["fonts"] == fiestaui.builtin_led_fonts()
    assert body["character_sets"] == fiestaui.builtin_character_sets()
    record = fiestaui.provenance()
    assert body["source"] == {key: record[key] for key in ("source", "commit", "version")}
    assert body["character_sets"]["vestaboard_v1"]["code62Glyph"] == "degree"
    assert body["character_sets"]["vestaboard_v2"]["code62Glyph"] == "heart"
    assert "font" not in body["character_sets"]["vestaboard_v1"]
    assert "glyphs" not in body["character_sets"]["led_5x7"]
    for name, font in body["fonts"].items():
        assert body["character_sets"][f"led_{name}"]["font"] == name
        for bitmap in [*font["glyphs"].values(), *font["icons"].values()]:
            assert len(bitmap) == font["glyphHeight"]
            assert all(len(row) == font["glyphWidth"] and set(row) <= {"#", "."} for row in bitmap)


def test_revision_identifies_content_and_etag_identifies_exact_bytes(client):
    first = _catalog(client)
    second = _catalog(client)
    body = first.json()
    assets = {key: body[key] for key in ("fonts", "character_sets")}
    canonical = json.dumps(assets, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert body["revision"] == hashlib.sha256(canonical).hexdigest()
    assert first.headers["etag"] == '"' + hashlib.sha256(first.content).hexdigest() + '"'
    assert first.content == second.content
    assert first.headers["etag"] == second.headers["etag"]
    assert first.headers["cache-control"] == CACHE_CONTROL
    assert first.headers["content-type"] == "application/json"


@pytest.mark.parametrize("condition", ["{etag}", "W/{etag}", '"old", {etag}', 'W/"old", W/{etag}', "*"])
def test_matching_condition_returns_empty_304_with_validators(client, condition):
    first = _catalog(client)
    response = client.get(PATH, headers={"If-None-Match": condition.format(etag=first.headers["etag"])})
    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == first.headers["etag"]
    assert response.headers["cache-control"] == CACHE_CONTROL
    assert "content-type" not in response.headers
    assert "content-length" not in response.headers


def test_repeated_conditional_header_fields_are_combined(client):
    first = _catalog(client)
    response = client.get(PATH, headers=[("If-None-Match", '"old"'), ("If-None-Match", first.headers["etag"])])
    assert response.status_code == 304
    assert response.content == b""


@pytest.mark.parametrize("condition", ['"old"', 'W/"old"', '"comma,in,tag"', "unquoted", ""])
def test_nonmatching_condition_returns_full_current_catalog(client, condition):
    first = _catalog(client)
    response = client.get(PATH, headers={"If-None-Match": condition})
    assert response.status_code == 200
    assert response.content == first.content
    assert response.headers["etag"] == first.headers["etag"]


@pytest.mark.parametrize("changed", ["fonts", "character_sets"])
def test_asset_change_invalidates_both_revision_and_etag(client, monkeypatch, changed):
    first = _catalog(client)
    if changed == "fonts":
        fonts = copy.deepcopy(fiestaui.builtin_led_fonts())
        fonts["3x5"]["glyphs"]["A"][0] = "..."
        monkeypatch.setattr(fiestaui, "builtin_led_fonts", lambda: fonts)
    else:
        charsets = copy.deepcopy(fiestaui.builtin_character_sets())
        charsets["led_3x5"]["label"] = "Changed label"
        monkeypatch.setattr(fiestaui, "builtin_character_sets", lambda: charsets)
    response = client.get(PATH, headers={"If-None-Match": first.headers["etag"]})
    assert response.status_code == 200
    assert response.json()["revision"] != first.json()["revision"]
    assert response.headers["etag"] != first.headers["etag"]


def test_openapi_declares_typed_catalog_and_conditional_response(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][PATH]["get"]
    assert operation["summary"] and operation["description"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/RenderAssets")
    for code in ("200", "304"):
        assert {"ETag", "Cache-Control"} <= operation["responses"][code]["headers"].keys()
    assert "content" not in operation["responses"]["304"]
    assert {"401", "403"} <= operation["responses"].keys()
    assert any(p["name"].lower() == "if-none-match" and p["in"] == "header" for p in operation["parameters"])
    model = schema["components"]["schemas"]["RenderAssets"]
    assert set(model["required"]) == {"schema_version", "revision", "source", "fonts", "character_sets"}


@pytest.fixture
def auth(tmp_path, monkeypatch):
    from src.auth import service

    auth = service.AuthService(tmp_path / "auth.json")
    auth.create_initial_user("admin", "contract-password")
    auth.sessions.set_enrollment(True)
    monkeypatch.setattr(service, "_service", auth)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    return auth


@pytest.mark.parametrize("client_id", ["fiestaboard-ios", "fiestaboard-android"])
def test_mobile_control_credentials_can_fetch_and_revalidate(client, auth, client_id):
    from src.auth.device_models import DeviceMetadata
    from src.auth.device_service import DeviceService

    token = (
        DeviceService(auth)
        .login(
            "admin",
            "contract-password",
            DeviceMetadata(client_id=client_id, device_name="Contract phone", app_version="1"),
        )
        .access_token
    )
    client.headers["Authorization"] = "Bearer " + token
    response = _catalog(client)
    assert client.get(PATH, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    assert client.get("/api" + PATH).content == response.content


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token"])
def test_authentication_is_required_before_returning_304(client, auth, authorization):
    headers = {"If-None-Match": "*"}
    if authorization:
        headers["Authorization"] = authorization
    response = client.get(PATH, headers=headers)
    assert response.status_code == 401
    assert "etag" not in response.headers


def test_tv_scope_does_not_gain_access_to_catalog(client, auth):
    from src.auth.device_models import DeviceMetadata
    from src.auth.device_service import DeviceService

    token = (
        DeviceService(auth)
        .login(
            "admin",
            "contract-password",
            DeviceMetadata(client_id="fiestaboard-tvos", device_name="Contract TV", app_version="1"),
        )
        .access_token
    )
    response = client.get(PATH, headers={"Authorization": "Bearer " + token, "If-None-Match": "*"})
    assert response.status_code == 403
    assert "etag" not in response.headers


def test_session_cookie_and_configured_api_token_can_revalidate(client, auth, monkeypatch):
    login = client.post("/auth/login", json={"username": "admin", "password": "contract-password"})
    assert login.status_code == 200
    response = _catalog(client)
    assert client.get(PATH, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    client.cookies.clear()
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "synthetic-render-assets-token")
    client.headers["Authorization"] = "Bearer synthetic-render-assets-token"
    assert _catalog(client).content == response.content
    assert client.get(PATH, headers={"If-None-Match": response.headers["etag"]}).status_code == 304


def test_revoked_phone_cannot_revalidate_cached_catalog(client, auth):
    from src.auth.device_models import DeviceMetadata
    from src.auth.device_service import DeviceService

    issued = DeviceService(auth).login(
        "admin",
        "contract-password",
        DeviceMetadata(client_id="fiestaboard-ios", device_name="Contract phone", app_version="1"),
    )
    client.headers["Authorization"] = "Bearer " + issued.access_token
    response = _catalog(client)
    auth.sessions.revoke_session("admin", issued.session_id)
    denied = client.get(PATH, headers={"If-None-Match": response.headers["etag"]})
    assert denied.status_code == 401
    assert "etag" not in denied.headers


def test_unquoted_or_prefix_validator_does_not_match(client):
    response = _catalog(client)
    etag = response.headers["etag"]
    for condition in (etag.strip('"'), etag[:-2] + '"', '"' + etag.strip('"') + 'extra"'):
        assert client.get(PATH, headers={"If-None-Match": condition}).status_code == 200


def test_recorded_native_responses(client, auth):
    """Native fixtures are actual authenticated HTTP-boundary response bytes."""
    import os
    from pathlib import Path

    from src.auth.device_models import DeviceMetadata
    from src.auth.device_service import DeviceService

    root = Path(__file__).resolve().parent.parent
    directory = root / "tests/fixtures/render-assets-v1"
    service = DeviceService(auth)
    clients = {}
    for name, client_id in (("ios", "fiestaboard-ios"), ("android", "fiestaboard-android"), ("tv", "fiestaboard-tvos")):
        clients[name] = service.login(
            "admin",
            "contract-password",
            DeviceMetadata(client_id=client_id, device_name="Contract client", app_version="1"),
        ).access_token
    first = client.get(PATH, headers={"Authorization": "Bearer " + clients["ios"]})
    assert first.status_code == 200
    etag = first.headers["etag"]
    cases = [
        ("ios-catalog", "ios", {}, 200),
        ("android-catalog", "android", {}, 200),
        ("not-modified", "ios", {"If-None-Match": etag}, 304),
        ("unauthenticated", None, {"If-None-Match": etag}, 401),
        ("tv-forbidden", "tv", {"If-None-Match": etag}, 403),
    ]
    recording = os.getenv("RECORD_RENDER_ASSETS")
    records = []
    bodies = {}
    for name, identity, conditional, status in cases:
        headers = dict(conditional)
        if identity:
            headers["Authorization"] = "Bearer " + clients[identity]
        response = client.get(PATH, headers=headers)
        assert response.status_code == status, response.text
        body_file = name + (".body" if status == 304 else ".json")
        bodies[body_file] = response.content
        records.append(
            {
                "id": name,
                "request": {"method": "GET", "path": PATH, "credential_kind": identity, "headers": conditional},
                "status": status,
                "headers": {
                    key: response.headers[key]
                    for key in ("etag", "cache-control", "content-type")
                    if key in response.headers
                },
                "body": body_file,
                "sha256": hashlib.sha256(response.content).hexdigest(),
            }
        )
    source_files = [
        "src/v1/render_assets.py",
        "src/v1/routes_render_assets.py",
        "src/v1/__init__.py",
        "src/fiestaui/led-fonts.json",
        "src/fiestaui/character-sets.json",
        "src/fiestaui/provenance.json",
        "src/auth/middleware.py",
        "src/auth/scopes.py",
        "scripts/record_render_assets.py",
        "tests/test_render_assets_contract.py",
    ]
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in source_files}
    if recording:
        directory.mkdir(parents=True, exist_ok=True)
        for name, body in bodies.items():
            (directory / name).write_bytes(body)
        (directory / "SOURCE.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "hub_commit": recording,
                    "capture": "FastAPI TestClient with real middleware, synthetic mobile/TV sessions and vendored assets",
                    "recorder": "scripts/record_render_assets.py",
                    "source_files_sha256": hashes,
                    "responses": records,
                },
                indent=2,
            )
            + "\n"
        )
    source = json.loads((directory / "SOURCE.json").read_text())
    assert source["source_files_sha256"] == hashes
    assert source["responses"] == records
    assert len(source["hub_commit"]) == 40 and set(source["hub_commit"]) <= set("0123456789abcdef")
    for name, body in bodies.items():
        assert (directory / name).read_bytes() == body
        for secret in clients.values():
            assert secret.encode() not in body
    assert (directory / "not-modified.body").read_bytes() == b""


@pytest.mark.parametrize("condition", ["{etag},", ", {etag}", '"old", , W/{etag}', ", , {etag}, ,"])
def test_conditional_list_ignores_empty_members(client, condition):
    first = _catalog(client)
    response = client.get(PATH, headers={"If-None-Match": condition.format(etag=first.headers["etag"])})
    assert response.status_code == 304
    assert response.content == b""


def test_empty_repeated_conditional_field_does_not_hide_matching_tag(client):
    first = _catalog(client)
    response = client.get(PATH, headers=[("If-None-Match", ""), ("If-None-Match", first.headers["etag"])])
    assert response.status_code == 304


def test_comma_inside_quoted_etag_is_not_a_separator(client):
    first = _catalog(client)
    etag = first.headers["etag"]
    response = client.get(PATH, headers={"If-None-Match": '"comma,in,tag", , W/' + etag})
    assert response.status_code == 304
    assert client.get(PATH, headers={"If-None-Match": '"comma,in,tag", , "old"'}).status_code == 200


def test_malformed_quoted_list_does_not_match_an_embedded_tag(client):
    first = _catalog(client)
    condition = '"before, ' + first.headers["etag"] + ', after"'
    assert client.get(PATH, headers={"If-None-Match": condition}).status_code == 200
