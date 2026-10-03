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
    POST /token            authorization_code, refresh_token, device_code grants;
                           the client may authenticate with HTTP Basic
    POST /device/code      start a device authorization
    GET  /device/approve   ?user_code=...  approve it "on another device"
    GET  /me               a protected resource: needs a live bearer token
    POST /revoke-all       forget every token, as if the user revoked the app
    GET  /log              every request seen, with secrets replaced by lengths

The same authorize/token pair also answers under the paths real providers
use, so a manifest or a preset only needs its host swapped:

    /auth/authorize, /auth/token                 Home Assistant (endpoint_base_setting)
    /oauth/authorize, /oauth/token               Hugging Face
    /api/accounts/authorize, /api/accounts/oauth/token
                                                 OpenAI (issues an ``oaiapp_mock_…``
                                                 client when sent ``dynamic_agent_client``)

Other flows:

    GET  /auth                     key_exchange (OpenRouter): redirects to
                                   ``callback_url``, or shows the code without one
    POST /api/v1/auth/keys         JSON {code, code_verifier} -> {"key"}
    POST /api/v2/pins              plex_pin: create a PIN (plex.tv)
    GET  /api/v2/pins/<id>         the PIN, with ``authToken`` once approved
    GET  /plex/auth                the approval page (reads app.plex.tv's ``#?`` fragment)
    GET  /plex/approve?code=...    approve a PIN without a browser
    POST /v1/responses             OpenAI Responses stub: streams text deltas (SSE)
    GET  /v1/models                ChatGPT-style model list (``visibility`` list/hide)
    POST /api/v1/chat/completions, /v1/chat/completions
                                   OpenAI-compatible chat stub (OpenRouter, Hugging Face)

Constant endpoints (Plex, FiestaBot AI presets) reach the mock through
``FIESTABOARD_OAUTH_URL_OVERRIDES`` on the board, for example::

    {"https://openrouter.ai": "http://localhost:9400",
     "https://huggingface.co": "http://localhost:9400",
     "https://router.huggingface.co": "http://localhost:9400",
     "https://auth.openai.com": "http://localhost:9400",
     "https://api.openai.com": "http://localhost:9400",
     "https://plex.tv": "http://localhost:9400",
     "https://app.plex.tv": "http://localhost:9400/plex"}

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
from urllib.parse import parse_qs, unquote_plus, urlencode, urlsplit

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
AUTHORIZE_PATHS = frozenset({"/authorize", "/auth/authorize", "/oauth/authorize", "/api/accounts/authorize"})
TOKEN_PATHS = frozenset({"/token", "/auth/token", "/oauth/token", "/api/accounts/oauth/token"})
#: The client ID OpenAI sends before it has issued one.
DYNAMIC_CLIENT = "dynamic_agent_client"
PLEX_AUTH_PAGE = """<!doctype html><title>Mock Plex sign-in</title>
<p id="msg">Approving...</p>
<script>
const params = new URLSearchParams(location.hash.replace(/^#\\??/, ""));
fetch("/plex/approve?code=" + encodeURIComponent(params.get("code") || "")).then((r) => {
  document.getElementById("msg").textContent = r.ok ? "Approved. You can close this tab." : "Unknown PIN.";
  const forward = params.get("forwardUrl");
  if (r.ok && forward) location.href = forward;
});
</script>
"""
MODELS = [
    {"slug": "mock-gpt", "display_name": "Mock GPT", "visibility": "list"},
    {"slug": "mock-gpt-mini", "display_name": "Mock GPT mini", "visibility": "list"},
    {"slug": "mock-internal", "display_name": "Hidden model", "visibility": "hide"},
]
REPLY = "Hello from the mock provider."
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
        self.keys: set[str] = set()
        self.pins: dict[str, dict] = {}
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

    def live(self, authorization: str) -> bool:
        token = authorization.removeprefix("Bearer ")
        return self.access_tokens.get(token, 0) > time.time() or token in self.keys

    def new_code(self, challenge: str, client_id: str = "", redirect_uri: str = "") -> str:
        code = f"code-{secrets.token_hex(8)}"
        self.codes[code] = {"challenge": challenge, "client_id": client_id, "redirect_uri": redirect_uri}
        return code

    def exchange_key(self, body: dict) -> tuple[int, dict]:
        record = self.codes.pop(str(body.get("code", "")), None)
        if record is None or _challenge(str(body.get("code_verifier", ""))) != record["challenge"]:
            return 400, {"error": {"code": 400, "message": "Invalid code or code_verifier"}}
        key = f"sk-or-mock-{secrets.token_hex(12)}"
        self.keys.add(key)
        return 200, {"key": key, "user_id": "mock-user"}

    def token(self, form: dict[str, str]) -> tuple[int, dict]:
        grant = form.get("grant_type")
        if grant == "authorization_code":
            record = self.codes.pop(form.get("code", ""), None)  # single use
            if record is None:
                return 400, {"error": "invalid_grant", "error_description": "unknown or already-used code"}
            if (
                _challenge(form.get("code_verifier", "")) != record["challenge"]
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


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def _basic_client(authorization: str) -> str:
    """The client ID from an HTTP Basic ``Authorization`` header, or ``""``."""
    if not authorization.startswith("Basic "):
        return ""
    try:
        user = base64.b64decode(authorization[6:]).decode().partition(":")[0]
    except ValueError:
        return ""
    return unquote_plus(user)


def make_handler(provider: Provider, port: int) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep the container log quiet
            pass

        def send_body(self, status: int, content_type: str, data: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status: int, body: object) -> None:
            self.send_body(status, "application/json", json.dumps(body).encode())

        def redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.end_headers()

        def send_events(self, events: list[dict]) -> None:
            data = "".join(f"event: {e.get('type', 'message')}\ndata: {json.dumps(e)}\n\n" for e in events)
            self.send_body(200, "text/event-stream", data.encode())

        def stream_responses(self, body: dict) -> None:
            if not provider.live(self.headers.get("Authorization", "")):
                self.send_json(401, {"error": {"message": "invalid token", "code": "invalid_token"}})
                return
            if body.get("stream") is not True:
                self.send_json(400, {"error": {"message": "stream must be true"}})
                return
            words = REPLY.split(" ")
            deltas = [
                {"type": "response.output_text.delta", "delta": w + (" " if i < len(words) - 1 else "")}
                for i, w in enumerate(words)
            ]
            response = {"id": f"resp_{secrets.token_hex(6)}", "model": body.get("model", "mock-gpt")}
            usage = {"input_tokens": 5, "output_tokens": len(words), "total_tokens": 5 + len(words)}
            self.send_events(
                [
                    {"type": "response.created", "response": response},
                    *deltas,
                    {"type": "response.completed", "response": {**response, "usage": usage}},
                ]
            )

        def chat_completions(self, body: dict) -> None:
            if not provider.live(self.headers.get("Authorization", "")):
                self.send_json(401, {"error": {"message": "invalid key"}})
                return
            if body.get("stream"):
                chunks = [{"choices": [{"delta": {"content": REPLY}, "index": 0}]}]
                data = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                self.send_body(200, "text/event-stream", data.encode())
                return
            self.send_json(
                200,
                {
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": REPLY}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 6},
                },
            )

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            if url.path in AUTHORIZE_PATHS:
                provider.record("authorize", query)
                if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
                    self.send_json(400, {"error": "invalid_request", "error_description": "PKCE S256 required"})
                    return
                if query.get("deny"):
                    answer = {"error": "access_denied", "state": query.get("state", "")}
                else:
                    client_id = query.get("client_id", "")
                    issued = f"oaiapp_mock_{secrets.token_hex(6)}" if client_id == DYNAMIC_CLIENT else ""
                    code = provider.new_code(
                        query["code_challenge"], issued or client_id, query.get("redirect_uri", "")
                    )
                    answer = {"code": code, "state": query.get("state", "")}
                    if issued:
                        answer["client_id"] = issued
                self.redirect(f"{query.get('redirect_uri', '')}?{urlencode(answer)}")
            elif url.path == "/auth":
                provider.record("key_exchange_authorize", query)
                if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
                    self.send_json(400, {"error": {"code": 400, "message": "PKCE S256 required"}})
                    return
                code = provider.new_code(query["code_challenge"])
                callback = query.get("callback_url")
                if not callback:
                    self.send_json(200, {"code": code, "hint": "Paste this code into FiestaBoard."})
                    return
                answer = {"code": code, **({"state": query["state"]} if "state" in query else {})}
                self.redirect(f"{callback}?{urlencode(answer)}")
            elif url.path.startswith("/api/v2/pins/"):
                pin = provider.pins.get(url.path.rsplit("/", 1)[-1])
                if pin is None:
                    self.send_json(404, {"errors": [{"code": 1020, "message": "Not Found"}]})
                else:
                    self.send_json(200, pin)
            elif url.path == "/plex/auth":
                self.send_body(200, "text/html; charset=utf-8", PLEX_AUTH_PAGE.encode())
            elif url.path == "/plex/approve":
                for pin in provider.pins.values():
                    if pin["code"] == query.get("code"):
                        pin["authToken"] = f"plex-mock-{secrets.token_hex(8)}"
                        self.send_json(200, {"approved": True})
                        return
                self.send_json(404, {"error": "unknown code"})
            elif url.path == "/v1/models":
                if not provider.live(self.headers.get("Authorization", "")):
                    self.send_json(401, {"error": {"message": "invalid token"}})
                    return
                self.send_json(200, {"object": "list", "data": MODELS})
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
            if self.headers.get("Content-Type", "").startswith("application/json"):
                try:
                    payload = json.loads(body or "{}")
                except ValueError:
                    payload = {}
                payload = payload if isinstance(payload, dict) else {}
                provider.record(url.path, {k: str(v) for k, v in payload.items() if k in ("model", "stream")})
                if url.path == "/api/v1/auth/keys":
                    self.send_json(*provider.exchange_key(payload))
                elif url.path == "/v1/responses":
                    self.stream_responses(payload)
                elif url.path in ("/api/v1/chat/completions", "/v1/chat/completions"):
                    self.chat_completions(payload)
                else:
                    self.send_json(404, {"error": "not_found"})
                return
            form = {key: values[0] for key, values in parse_qs(body).items()}
            provider.record(url.path, form)
            if url.path in TOKEN_PATHS:
                basic = _basic_client(self.headers.get("Authorization", ""))
                if basic and "client_id" not in form:
                    form["client_id"] = basic
                self.send_json(*provider.token(form))
            elif url.path == "/api/v2/pins":
                pin_id = str(len(provider.pins) + 1000)
                provider.pins[pin_id] = {
                    "id": int(pin_id),
                    "code": secrets.token_hex(12),
                    "expiresIn": 900,
                    "authToken": None,
                    "clientIdentifier": self.headers.get("X-Plex-Client-Identifier", ""),
                }
                self.send_json(201, provider.pins[pin_id])
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
