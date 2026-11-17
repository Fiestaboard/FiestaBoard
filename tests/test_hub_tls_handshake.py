"""Exercise the shipped nginx configurations with real, verified TLS handshakes.

Only a loopback HTTP echo server substitutes for the hardware-facing API/Vite
processes. The nginx routing, generated TLS snippet, ingress rewrite, certificate
validation, trusted proxy handling, and browser auth helpers are real.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.responses import Response
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from src.auth.browser_routes import _require_portal_origin
from src.auth.device_models import AuthFlowError
from src.auth.routes import _is_secure_request

REPO_ROOT = Path(__file__).resolve().parents[1]
SPA_BODY = b'<!doctype html><script src="/assets/app.js"></script><script>{"basename":"/"}</script>'


def _get(port, path="/", *, context=None, hostname="localhost", headers=None):
    """Always connect to loopback, independently of the name being verified."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.connect()
        if context is not None:
            connection.sock = context.wrap_socket(connection.sock, server_hostname=hostname)
        connection.request("GET", path, headers={"Host": f"localhost:{port}", **(headers or {})})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


class _Backend(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith(("/probe", "/api/mcp")):
            self._respond(SPA_BODY, "text/html")
            return

        result = {}

        async def inspect_request(scope, receive, send):
            request = Request(scope)
            response = Response()
            response.set_cookie("test_session", "test_token", secure=_is_secure_request(request), httponly=True)
            try:
                _require_portal_origin(request)
                origin_status = 200
            except AuthFlowError as error:
                origin_status = error.status
            result.update(
                path=request.url.path,
                scheme=request.url.scheme,
                forwarded_proto=request.headers.get("x-forwarded-proto"),
                cookie=response.headers["set-cookie"],
                origin_status=origin_status,
            )

        # Match Uvicorn's trusted-loopback proxy boundary. Do not manufacture
        # the request scheme from the client-provided header in the test.
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self.path,
            "query_string": b"",
            "headers": [(key.lower().encode(), value.encode()) for key, value in self.headers.items()],
            "client": self.client_address,
            "server": self.server.server_address,
        }
        asyncio.run(ProxyHeadersMiddleware(inspect_request, trusted_hosts="127.0.0.1")(scope, None, None))
        self._respond(json.dumps(result).encode(), "application/json")

    def _respond(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@dataclass
class _Nginx:
    http_port: int
    https_port: int
    certificate: Path

    def trusted_context(self):
        return ssl.create_default_context(cafile=str(self.certificate))


def _unused_ports():
    # Hold both reservations until both numbers are selected, so the OS cannot
    # return the same port twice. Each xdist worker gets its own pair.
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        return first.getsockname()[1], second.getsockname()[1]


@pytest.fixture(scope="module", params=["nginx.conf", "nginx-dev.conf"])
def nginx_tls(request, tmp_path_factory):
    # Deliberately fail rather than skip: CI installs nginx, and silently losing
    # real certificate validation would remove the essential regression guard.
    nginx = shutil.which("nginx")
    assert nginx, "The TLS handshake tests require nginx in the test image / CI runner."
    from src.system.tls import configure_tls

    root = tmp_path_factory.mktemp("hub-tls")
    snippets = root / "etc/nginx/fiestaboard"
    locations = snippets / "location-root"
    locations.mkdir(parents=True)
    static = root / "app/web/build/client"
    static.mkdir(parents=True)
    (static / "index.html").write_bytes(SPA_BODY)
    (root / "var/lib/nginx").mkdir(parents=True)
    (root / "var/log/nginx").mkdir(parents=True)
    (root / "etc/nginx/mime.types").write_text("types { text/html html; application/javascript js; }\n")

    certificate = configure_tls(
        {"FIESTABOARD_TLS_MODE": "self-signed", "FIESTABOARD_TLS_HOSTS": "localhost,127.0.0.1"},
        data_dir=root / "data",
        snippet_dir=snippets,
    )
    assert certificate is not None

    # Consume the production ingress rules verbatim instead of reproducing a
    # simplified substitute that could pass after entrypoint.sh regresses.
    entrypoint = (REPO_ROOT / "entrypoint.sh").read_text()
    ingress_function = entrypoint.split("configure_ingress_path_rewrite() {", 1)[1]
    ingress_snippet = ingress_function.split("<<'NGINX'\n", 1)[1].split("\nNGINX", 1)[0]
    (locations / "base-path-rewrite.conf").write_text(ingress_snippet + "\n")

    backend = ThreadingHTTPServer(("127.0.0.1", 0), _Backend)
    thread = threading.Thread(target=backend.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    process = None
    try:
        http_port, https_port = _unused_ports()
        config = (REPO_ROOT / request.param).read_text()
        for prefix in ("/etc/nginx", "/var/lib/nginx", "/var/log/nginx", "/app"):
            config = config.replace(prefix, str(root / prefix.lstrip("/")))
        config = config.replace("listen 3000;", f"listen 127.0.0.1:{http_port};")
        config = config.replace("listen [::]:3000;", f"listen [::1]:{http_port};")
        config = config.replace("127.0.0.1:8000", f"127.0.0.1:{backend.server_port}")
        config = config.replace("127.0.0.1:3001", f"127.0.0.1:{backend.server_port}")
        tls_snippet = snippets / "tls.conf"
        generated = tls_snippet.read_text()
        generated = generated.replace("listen 3443 ssl;", f"listen 127.0.0.1:{https_port} ssl;")
        generated = generated.replace("listen [::]:3443 ssl;", f"listen [::1]:{https_port} ssl;")
        tls_snippet.write_text(generated)

        version = subprocess.run([nginx, "-v"], capture_output=True, text=True, check=True, timeout=5)
        match = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", version.stderr)
        assert match, version.stderr
        if tuple(map(int, match.groups())) < (1, 25, 1):
            # Debian's nginx predates the standalone http2 directive. Remove
            # only that unrelated directive; retain every TLS/routing setting.
            config = re.sub(r"^\s*http2 on;\s*$", "", config, flags=re.MULTILINE)
        config_file = root / "nginx.conf"
        config_file.write_text(config)
        command = [nginx, "-p", str(root), "-c", str(config_file), "-g", "daemon off; master_process off;"]
        # Single-process mode keeps nginx under the invoking test user's uid,
        # including root in Docker, so pytest's private temp dirs stay private.
        with (root / "nginx-output.log").open("w+") as output:
            checked = subprocess.run([*command, "-t"], capture_output=True, text=True, timeout=5)
            assert checked.returncode == 0, checked.stderr
            process = subprocess.Popen(command, stdout=output, stderr=output)
            deadline = time.monotonic() + 5
            while True:
                if process.poll() is not None:
                    pytest.fail(f"nginx exited during startup: {(root / 'nginx-output.log').read_text()}")
                try:
                    if _get(http_port)[0] == 200:
                        break
                except (OSError, http.client.HTTPException):
                    pass
                if time.monotonic() >= deadline:
                    pytest.fail(f"nginx did not become ready: {(root / 'var/log/nginx/error.log').read_text()}")
                time.sleep(0.02)
            yield _Nginx(http_port, https_port, certificate)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        backend.shutdown()
        backend.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_http_and_verified_https_serve_the_same_spa(nginx_tls):
    http_status, _, http_body = _get(nginx_tls.http_port, "/pages/example")
    https_status, _, https_body = _get(
        nginx_tls.https_port, "/pages/example", context=nginx_tls.trusted_context()
    )
    assert http_status == https_status == 200
    assert http_body == https_body == SPA_BODY


def test_https_rejects_an_untrusted_certificate(nginx_tls):
    with pytest.raises(ssl.SSLCertVerificationError):
        _get(nginx_tls.https_port, context=ssl.create_default_context())


def test_https_rejects_a_trusted_certificate_for_the_wrong_hostname(nginx_tls):
    with pytest.raises(ssl.SSLCertVerificationError, match="[Hh]ostname mismatch"):
        _get(nginx_tls.https_port, context=nginx_tls.trusted_context(), hostname="wrong-host.invalid")


@pytest.mark.parametrize("path,upstream_path", [("/api/probe", "/probe"), ("/api/mcp/probe", "/api/mcp/probe")])
@pytest.mark.parametrize("scheme", ["http", "https"])
def test_proxy_replaces_spoofed_scheme_and_preserves_auth_origin(nginx_tls, monkeypatch, path, upstream_path, scheme):
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    secure = scheme == "https"
    port = nginx_tls.https_port if secure else nginx_tls.http_port
    context = nginx_tls.trusted_context() if secure else None
    status, _, body = _get(
        port,
        path,
        context=context,
        headers={"X-Forwarded-Proto": "http" if secure else "https", "Origin": f"{scheme}://localhost:{port}"},
    )
    assert status == 200
    received = json.loads(body)
    assert received["path"] == upstream_path
    assert received["forwarded_proto"] == received["scheme"] == scheme
    assert ("Secure" in received["cookie"]) is secure
    assert received["origin_status"] == 200


def test_https_browser_origin_rejects_a_different_scheme(nginx_tls, monkeypatch):
    monkeypatch.delenv("FIESTABOARD_CORS_ORIGINS", raising=False)
    status, _, body = _get(
        nginx_tls.https_port,
        "/api/probe",
        context=nginx_tls.trusted_context(),
        headers={"Origin": f"http://localhost:{nginx_tls.https_port}"},
    )
    assert status == 200
    assert json.loads(body)["origin_status"] == 403


def test_http_home_assistant_ingress_rewrite_remains_available(nginx_tls):
    status, _, body = _get(nginx_tls.http_port, headers={"X-Ingress-Path": "/api/hassio_ingress/test_ingress"})
    assert status == 200
    assert b'"/api/hassio_ingress/test_ingress/assets/app.js"' in body
    assert b'"basename":"/api/hassio_ingress/test_ingress/"' in body
