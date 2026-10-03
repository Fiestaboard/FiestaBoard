#!/usr/bin/env python3
"""A stand-in OAuth provider for testing plugin sign-in end to end.

Lets you exercise a plugin's ``oauth`` block against a running FiestaBoard
without an account, an app registration, or a secret at any real provider.
It behaves like a strict provider: it requires PKCE (S256), issues
authorization codes that work once, checks the code verifier, redirect URI and
client ID at the token endpoint, issues short-lived access tokens so refresh is
exercised within seconds, and rotates refresh tokens.

Run it inside the dev container, where the board can reach it on localhost::

    docker compose -f docker-compose.dev.yml exec -d fiestaboard \\
        python scripts/mock_oauth_provider.py

Then point a throwaway plugin's manifest at it (plain http is accepted for
loopback hosts only)::

    "oauth": {
      "provider_name": "Mock Provider",
      "flows": ["relay"],
      "authorization_url": "http://localhost:9400/authorize",
      "device_authorization_url": "http://localhost:9400/device/code",
      "token_url": "http://localhost:9400/token",
      "scopes": ["read-profile"]
    }

The relay flow sends your *browser* to ``/authorize``, so port 9400 must also
be published to the host; docs/development/plugin-oauth.md has the compose
override and the full walkthrough. With the port published, approve a device
code with ``curl "http://localhost:9400/device/approve?user_code=<CODE>"``.

Endpoints:

    GET  /authorize        consent is automatic; add ``&deny=1`` to decline
    POST /token            authorization_code, refresh_token, device_code grants
    POST /device/code      start a device authorization
    GET  /device/approve   ?user_code=...  approve it "on another device"
    GET  /me               a protected resource: needs a live bearer token
    POST /revoke-all       forget every token, as if the user revoked the app
    GET  /log              every request seen, with secrets replaced by lengths

Options: ``--port`` (default 9400), ``--access-ttl`` seconds (default 20).

This is a test tool. It keeps everything in memory, has no TLS, and must never
be exposed beyond a development machine.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
#: Form fields safe to show in /log; everything else is logged as a length.
LOGGABLE = frozenset({"grant_type", "client_id", "redirect_uri", "response_type", "code_challenge_method", "scope"})


class Provider:
    """Everything the provider remembers. One instance per process."""

    def __init__(self, access_ttl: int) -> None:
        self.access_ttl = access_ttl
        self.codes: dict[str, dict[str, str]] = {}
        self.refresh_tokens: dict[str, str] = {}
        self.access_tokens: dict[str, float] = {}
        self.devices: dict[str, dict] = {}
        self.log: list[dict] = []

    def record(self, name: str, fields: dict[str, str]) -> None:
        self.log.append({name: {k: (v if k in LOGGABLE else f"<{len(v)} chars>") for k, v in fields.items()}})

    def issue(self, client_id: str) -> dict:
        access, refresh = f"at-{secrets.token_hex(8)}", f"rt-{secrets.token_hex(8)}"
        self.access_tokens[access] = time.time() + self.access_ttl
        self.refresh_tokens[refresh] = client_id
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.access_ttl,
            "refresh_token": refresh,
            "scope": "read-profile",
        }

    def token(self, form: dict[str, str]) -> tuple[int, dict]:
        grant = form.get("grant_type")
        if grant == "authorization_code":
            record = self.codes.pop(form.get("code", ""), None)  # single use
            if record is None:
                return 400, {"error": "invalid_grant", "error_description": "unknown or already-used code"}
            verifier = form.get("code_verifier", "").encode()
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=").decode()
            if (
                challenge != record["challenge"]
                or form.get("client_id") != record["client_id"]
                or form.get("redirect_uri") != record["redirect_uri"]
            ):
                return 400, {"error": "invalid_grant", "error_description": "PKCE, client or redirect mismatch"}
            return 200, self.issue(record["client_id"])
        if grant == "refresh_token":
            client_id = self.refresh_tokens.pop(form.get("refresh_token", ""), None)  # rotating
            if client_id is None or client_id != form.get("client_id"):
                return 400, {"error": "invalid_grant"}
            return 200, self.issue(client_id)
        if grant == DEVICE_GRANT:
            device = self.devices.get(form.get("device_code", ""))
            if device is None:
                return 400, {"error": "expired_token"}
            if not device["approved"]:
                return 400, {"error": "authorization_pending"}
            del self.devices[form["device_code"]]
            return 200, self.issue(device["client_id"])
        return 400, {"error": "unsupported_grant_type"}


def make_handler(provider: Provider, port: int) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the container log quiet
            pass

        def send_json(self, status: int, body: object) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            if url.path == "/authorize":
                provider.record("authorize", query)
                if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
                    self.send_json(400, {"error": "invalid_request", "error_description": "PKCE S256 required"})
                    return
                if query.get("deny"):
                    answer = {"error": "access_denied", "state": query.get("state", "")}
                else:
                    code = f"code-{secrets.token_hex(8)}"
                    provider.codes[code] = {
                        "challenge": query["code_challenge"],
                        "client_id": query.get("client_id", ""),
                        "redirect_uri": query.get("redirect_uri", ""),
                    }
                    answer = {"code": code, "state": query.get("state", "")}
                self.send_response(302)
                self.send_header("Location", f"{query.get('redirect_uri', '')}?{urlencode(answer)}")
                self.end_headers()
            elif url.path == "/device/approve":
                for device in provider.devices.values():
                    if device["user_code"] == query.get("user_code"):
                        device["approved"] = True
                        self.send_json(200, {"approved": True})
                        return
                self.send_json(404, {"error": "unknown user_code"})
            elif url.path == "/me":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                if provider.access_tokens.get(token, 0) > time.time():
                    self.send_json(200, {"user": "example-user"})
                else:
                    self.send_json(401, {"error": "invalid_token"})
            elif url.path == "/log":
                self.send_json(200, provider.log)
            else:
                self.send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            url = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            form = {key: values[0] for key, values in parse_qs(body).items()}
            provider.record(url.path, form)
            if url.path == "/token":
                self.send_json(*provider.token(form))
            elif url.path == "/device/code":
                device_code = f"dc-{secrets.token_hex(8)}"
                user_code = f"{secrets.token_hex(2)}-{secrets.token_hex(2)}".upper()
                provider.devices[device_code] = {
                    "user_code": user_code,
                    "approved": False,
                    "client_id": form.get("client_id", ""),
                }
                base = f"http://localhost:{port}/device"
                self.send_json(
                    200,
                    {
                        "device_code": device_code,
                        "user_code": user_code,
                        "verification_uri": base,
                        "verification_uri_complete": f"{base}/approve?user_code={user_code}",
                        "expires_in": 300,
                        "interval": 2,
                    },
                )
            elif url.path == "/revoke-all":
                provider.access_tokens.clear()
                provider.refresh_tokens.clear()
                self.send_json(200, {"revoked": True})
            else:
                self.send_json(404, {"error": "not_found"})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock OAuth provider for testing plugin sign-in.")
    parser.add_argument("--port", type=int, default=9400)
    parser.add_argument("--access-ttl", type=int, default=20, help="Access token lifetime in seconds.")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(Provider(args.access_ttl), args.port))
    print(f"Mock OAuth provider listening on :{args.port} (access tokens live {args.access_ttl}s)")
    server.serve_forever()


if __name__ == "__main__":
    main()
