"""Browser request policy must reject requests before their handlers run."""

import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from src.api_server import app, cors_settings


@pytest.fixture
def portal(monkeypatch):
    for name in (
        "FIESTABOARD_CORS_ORIGINS",
        "FIESTABOARD_ALLOWED_HOSTS",
        "FIESTABOARD_EXTERNAL_URL",
        "FIESTABOARD_MCP_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    reached = []

    def client(host="http://localhost:4420"):
        middleware = [
            Middleware(CORSMiddleware, **cors_settings()) if entry.cls is CORSMiddleware else entry
            for entry in app.user_middleware
        ]
        probe = FastAPI(middleware=middleware)

        @probe.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
        async def handle(request: Request, path: str):
            reached.append((request.method, path))
            return {"ok": True}

        return TestClient(probe, base_url=host)

    return client, reached


@pytest.mark.parametrize(
    "path", ["/start", "/backup/export", "/pages/ai/chat", "/system/channel", "/mcp/", "/api/mcp/"]
)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unlisted_browser_cannot_reach_handler(portal, path, method):
    factory, reached = portal
    response = factory().request(method, path, headers={"Origin": "https://unlisted.example"})
    assert response.status_code == 403
    assert not reached
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", [None, "http://unlisted.example"])
def test_unlisted_host_is_rejected_even_without_origin(portal, origin):
    factory, reached = portal
    headers = {"Origin": origin} if origin else {}
    assert factory("http://unlisted.example").get("/backup/export", headers=headers).status_code == 400
    assert not reached


@pytest.mark.parametrize(
    "origin", ["null", "", "https://a.example https://b.example", "http://localhost:4420/path", "http://localhost:0"]
)
def test_invalid_origin_cannot_reach_handler(portal, origin):
    factory, reached = portal
    assert factory().post("/start", headers={"Origin": origin}).status_code == 403
    assert not reached


def test_duplicate_origin_and_host_are_rejected(portal):
    factory, reached = portal
    assert (
        factory()
        .post("/start", headers=[("Origin", "http://localhost:4420"), ("Origin", "https://unlisted.example")])
        .status_code
        == 403
    )
    assert (
        factory().get("/backup/export", headers=[("Host", "localhost:4420"), ("Host", "unlisted.example")]).status_code
        == 400
    )
    assert not reached


@pytest.mark.parametrize(
    "host",
    [
        "http://localhost:4420",
        "http://127.0.0.1:4420",
        "http://[::1]:4420",
        "http://192.0.2.10:4420",
        "http://fiestaboard.local:4420",
    ],
)
@pytest.mark.parametrize("browser", [False, True])
def test_local_anonymous_clients_remain_supported(portal, host, browser):
    factory, reached = portal
    response = factory(host).post("/start", headers={"Origin": host} if browser else {})
    assert response.status_code == 200
    assert reached == [("POST", "start")]


def test_explicit_proxy_and_dashboard_configuration(portal, monkeypatch):
    factory, reached = portal
    monkeypatch.setenv("FIESTABOARD_ALLOWED_HOSTS", "hub.example")
    monkeypatch.setenv("FIESTABOARD_CORS_ORIGINS", "https://dashboard.example,https://ha.example:8123")
    client = factory("http://hub.example")
    assert client.post("/start", headers={"Origin": "https://ha.example:8123"}).status_code == 200
    response = client.options(
        "/start", headers={"Origin": "https://dashboard.example", "Access-Control-Request-Method": "POST"}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://dashboard.example"
    assert reached == [("POST", "start")]


def test_external_address_and_custom_mdns_name(portal, monkeypatch):
    factory, reached = portal
    monkeypatch.setenv("FIESTABOARD_EXTERNAL_URL", "https://hub.example:8443")
    monkeypatch.setenv("MDNS_HOSTNAME", "kitchen")
    assert (
        factory("http://hub.example").post("/start", headers={"Origin": "https://hub.example:8443"}).status_code == 200
    )
    assert factory("http://kitchen.local:4420").get("/status").status_code == 200
    assert len(reached) == 2


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://unlisted.example", "X-Forwarded-Host": "unlisted.example", "X-Forwarded-Proto": "https"},
        {"Origin": "https://unlisted.example", "X-Ingress-Path": "/api/hassio_ingress/fake"},
    ],
)
def test_untrusted_proxy_headers_never_grant_access(portal, headers):
    factory, reached = portal
    assert factory().post("/start", headers=headers).status_code == 403
    assert not reached


def test_discovery_exception_is_narrow(portal):
    factory, reached = portal
    client = factory()
    headers = {"Origin": "https://fiestaboard.app"}
    assert client.get("/discover", headers=headers).status_code == 200
    for method, path in [("POST", "/discover"), ("GET", "/discover/more"), ("GET", "/backup/export")]:
        assert client.request(method, path, headers=headers).status_code == 403
    assert factory("http://unlisted.example").get("/discover", headers=headers).status_code == 400
    assert reached == [("GET", "discover")]


def test_wildcard_configuration_does_not_disable_boundary(portal, monkeypatch):
    factory, reached = portal
    monkeypatch.setenv("FIESTABOARD_CORS_ORIGINS", "*")
    monkeypatch.setenv("FIESTABOARD_ALLOWED_HOSTS", "*")
    assert factory().post("/start", headers={"Origin": "https://unlisted.example"}).status_code == 403
    assert factory("http://unlisted.example").get("/backup/export").status_code == 400
    assert not reached


@pytest.mark.parametrize("path", ["/mcp/", "/api/mcp/", "/backup/export", "/health"])
def test_real_app_rejects_foreign_browser_before_route_dispatch(monkeypatch, path):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    client = TestClient(app, base_url="http://localhost:4420")
    assert client.get(path, headers={"Origin": "https://unlisted.example"}).status_code == 403
    assert client.get(path, headers={"Host": "unlisted.example"}).status_code == 400


def test_configured_mcp_credential_still_required(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")
    monkeypatch.setenv("FIESTABOARD_MCP_TOKEN", "test-only-not-a-real-token")
    client = TestClient(app, base_url="http://localhost:4420")
    response = client.get("/mcp/")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer")


def test_fetch_metadata_blocks_cross_site_requests_without_origin(portal):
    factory, reached = portal
    assert factory().post("/start", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not reached


@pytest.mark.parametrize(
    "host", ["localhost:0", "localhost:", "localhost/", "localhost?", "localhost#", "user@localhost", "localhost:65536"]
)
def test_malformed_host_never_reaches_handler(portal, host):
    factory, reached = portal
    assert factory().post("/start", headers={"Host": host}).status_code == 400
    assert not reached


@pytest.mark.parametrize("path", ["/oauth/callback", "/api/oauth/callback"])
def test_callback_navigation_is_narrow_and_still_checks_host(portal, path):
    factory, reached = portal
    headers = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}
    client = factory()
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path, headers=headers).status_code == 403
    assert client.get(path + "/extra", headers=headers).status_code == 403
    assert client.get(path, headers={**headers, "Host": "unlisted.example"}).status_code == 400
    assert reached == [("GET", path.lstrip("/"))]


@pytest.mark.skipif(shutil.which("nginx") is None, reason="nginx required for proxy integration")
def test_ingress_proxy_preserves_browser_authority(portal, tmp_path):
    factory, reached = portal

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            response = factory().post("/start", headers=dict(self.headers))
            self.send_response(response.status_code)
            self.end_headers()

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    config = Path("infra/ha-ingress-proxy.conf").read_text()
    config = config.replace("listen 80;", f"listen 127.0.0.1:{port};")
    config = config.replace("http://fiestaboard:3000", f"http://127.0.0.1:{upstream.server_port}")
    path = tmp_path / "nginx.conf"
    path.write_text(
        f"pid {tmp_path}/nginx.pid; error_log {tmp_path}/error.log; events {{}} http {{ access_log off; {config} }}"
    )
    process = subprocess.Popen(["nginx", "-c", str(path), "-p", str(tmp_path), "-g", "daemon off;"])
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                assert process.poll() is None
                time.sleep(0.02)
        origin = f"http://localhost:{port}"
        response = httpx.post(
            f"http://127.0.0.1:{port}/api/hassio_ingress/test-token/start",
            headers={"Host": f"localhost:{port}", "Origin": origin},
        )
        assert response.status_code == 200
        assert reached == [("POST", "start")]
    finally:
        process.terminate()
        process.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=5)
