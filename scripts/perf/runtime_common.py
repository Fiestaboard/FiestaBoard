"""Standard-library runtime harness primitives; network access is explicit only."""

from __future__ import annotations

import math
import json
import http.cookiejar
import http.client
import socket
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

SOURCE_COMMIT = "83236253aa8103db856b7efa456e088b9c9ec548"
AMD64_MANIFEST = "sha256:62764744c42302386ed746a93c8ca15ee7464b75a436a8cc6acb2e9be675a9e3"


class ProtocolError(ValueError):
    """A fixture, response or observation does not satisfy the declared contract."""


class AuthAbort(ProtocolError):
    """Authentication failed; further requests require explicit operator recovery."""


@dataclass
class HttpResult:
    status: int
    body: object
    headers: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    body_bytes: int = 0
    error: str | None = None
    timed_out: bool = False
    connection_reused: bool | None = None


class JsonClient:
    def __init__(self, base_url, credentials, *, transport=None, timeout=30.0, run_context=None, connection_factory=None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ProtocolError("Use an explicit HTTP(S) origin without credentials")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ProtocolError("The standalone nginx origin must not contain a path/query/fragment")
        if timeout <= 0 or not math.isfinite(timeout):
            raise ProtocolError("Request timeout must be finite and positive")
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self.transport = transport
        self.timeout = timeout
        self.run_context = run_context
        self.connection_factory = connection_factory
        self.secrets = [credentials.get("password", "")]
        self.observer = None
        self.auth_aborted = False
        self.cookies = http.cookiejar.CookieJar()
        self._connection = None

    def request(self, method, path, payload=None):
        if self.auth_aborted:
            raise AuthAbort("No further network requests after authentication failed")
        if not path.startswith("/api/") or path.startswith("//") or urlsplit(path).netloc or urlsplit(path).fragment:
            raise ProtocolError("Request target must be a relative /api/ path")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ProtocolError("Unsupported HTTP method")
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 FiestaBoard-Perf/1.0"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        started = time.monotonic()
        try:
            exchange = self.transport or self._exchange
            result = exchange(method, self.base_url + path, payload, headers, self.timeout)
        except (TimeoutError, socket.timeout):
            self.close()
            result = HttpResult(0, None, elapsed_ms=(time.monotonic() - started) * 1000,
                                error="Request timed out", timed_out=True)
        except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError) as exc:
            self.close()
            # Do not retain exception text: third-party errors can echo credentials/headers.
            timed_out = isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout))
            result = HttpResult(0, None, elapsed_ms=(time.monotonic() - started) * 1000,
                                error="Request timed out" if timed_out else f"Transport failure: {type(exc).__name__}",
                                timed_out=timed_out)
        for name, value in result.headers.items():
            if name.lower() == "set-cookie":
                cookie = SimpleCookie()
                try:
                    cookie.load(value)
                except Exception:
                    continue
                self.secrets.extend(morsel.value for morsel in cookie.values() if morsel.value)
        if result.status == 401:
            self.auth_aborted = True
        if self.observer:
            self.observer(method, path, payload, self.safe_result(result))
        return result

    def _exchange(self, method, url, payload, headers, timeout):
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        self.cookies.add_cookie_header(request)
        parsed = urlsplit(url)
        if self._connection is None:
            if self.connection_factory is not None:
                self._connection = self.connection_factory()
            else:
                factory = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
                self._connection = factory(parsed.hostname, parsed.port, timeout=timeout)
        reused = self._connection.sock is not None
        started = time.monotonic()
        response = None
        try:
            target = parsed.path + ("?" + parsed.query if parsed.query else "")
            self._connection.request(method, target, body=body, headers=dict(request.header_items()))
            response = self._connection.getresponse()
            raw = response.read(4 * 1024 * 1024 + 1)
            elapsed = (time.monotonic() - started) * 1000
            if len(raw) > 4 * 1024 * 1024:
                raise ProtocolError("Response exceeded bounded 4 MiB body")
            self.cookies.extract_cookies(_CookieResponse(response.headers), request)
            try:
                decoded = json.loads(raw)
                error = None
            except (ValueError, UnicodeDecodeError):
                decoded, error = None, "Response was not JSON"
            result = HttpResult(response.status, decoded, dict(response.headers.items()), elapsed, len(raw), error,
                                connection_reused=reused)
            if response.will_close:
                self.close()
            return result
        finally:
            if response is not None:
                response.close()

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def login(self, *, min_valid_seconds=600):
        body = require_ok(self.request("POST", "/api/auth/login", {
            "username": self.credentials["username"], "password": self.credentials["password"], "remember_me": False
        }))
        if body.get("status") != "ok" or body.get("username") != self.credentials["username"]:
            raise ProtocolError("Login did not confirm synthetic account")
        return self.session_info(min_valid_seconds=min_valid_seconds)

    def session_info(self, *, min_valid_seconds=600):
        status = require_ok(self.request("GET", "/api/auth/status"))
        if (status.get("enabled") is not True or status.get("authenticated") is not True
                or status.get("setup_required") is not False or status.get("auth_kind") != "browser"):
            raise ProtocolError("A real authenticated browser cookie is required")
        body = require_ok(self.request("GET", "/api/auth/sessions"))
        sessions = body.get("sessions", [])
        current_id = body.get("current_session_id")
        current = [s for s in sessions if s.get("id") == current_id]
        if len(current) != 1 or current[0].get("kind") != "browser" or len(sessions) >= 200:
            raise ProtocolError("Current browser session missing or session capacity exhausted")
        try:
            expires = datetime.fromisoformat(current[0]["expires_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProtocolError("Session expiry is missing/malformed") from exc
        if expires.tzinfo is None or (expires - datetime.now(timezone.utc)).total_seconds() <= min_valid_seconds:
            raise ProtocolError("Session lifetime is insufficient for declared measurement plus margin")
        return {"current_session_id": current_id, "active_sessions": len(sessions), "expires_at": current[0]["expires_at"]}

    def safe_result(self, result):
        return redact(result.__dict__, self.secrets)


class _CookieResponse:
    def __init__(self, headers):
        self.headers = headers

    def info(self):
        return self.headers


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_credentials(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ProtocolError("Credentials must be a regular private mode-0600 file")
    try:
        credentials = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProtocolError("Cannot read private credentials") from exc
    if (not isinstance(credentials, dict) or set(credentials) != {"username", "password"}
            or not isinstance(credentials["username"], str) or not credentials["username"].strip()
            or not isinstance(credentials["password"], str) or len(credentials["password"]) < 8):
        raise ProtocolError("Private credentials need a synthetic username and password of at least8 characters")
    return credentials


class JsonlWriter:
    """Flush each observation, never truncate/reuse a prior run's partial file."""

    def __init__(self, path, run_id, *, secrets=()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("x", encoding="utf-8")
        self.started = time.monotonic()
        self.run_id = run_id
        self.secrets = secrets

    def write(self, record_type, **fields):
        record = {"schema_version": 1, "run_id": self.run_id, "record_type": record_type, "utc": utc_now(),
                  "monotonic_elapsed_s": time.monotonic() - self.started, **fields}
        self.file.write(json.dumps(redact(record, self.secrets), sort_keys=True, allow_nan=False) + "\n")
        self.file.flush()
        return record

    def close(self):
        self.file.close()


def redact(value, secrets=()):
    """Remove credentials by field name and known values even in free-text errors."""
    private = {"password", "current_password", "new_password", "cookie", "set-cookie", "authorization", "csrf_token"}
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if str(key).lower() in private else redact(item, secrets)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
    return value


def nearest_rank(values, quantile):
    if not values or not 0 < quantile <= 1:
        raise ProtocolError("A quantile needs observations and 0 < q <= 1")
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in values):
        raise ProtocolError("Latency must be finite and nonnegative")
    return sorted(values)[math.ceil(len(values) * quantile) - 1]


def validate_preview(body, page_ids):
    expected = set(page_ids)
    if len(expected) != len(page_ids) or not expected or not isinstance(body, dict):
        raise ProtocolError("Invalid preview ID set or response")
    previews = body.get("previews")
    if body.get("total") != len(expected) or body.get("successful") != len(expected):
        raise ProtocolError("Preview totals do not report all successful items")
    if not isinstance(previews, dict) or set(previews) != expected:
        raise ProtocolError("Preview response IDs differ from requested IDs")
    for pid, item in previews.items():
        if not isinstance(item, dict) or item.get("available") is not True or item.get("page_id") != pid:
            raise ProtocolError("Preview item unavailable or has a different ID")
        if not isinstance(item.get("lines"), list) or not all(isinstance(line, str) for line in item["lines"]):
            raise ProtocolError("Preview lines missing or malformed")


def summarize_requests(records):
    successes = [r for r in records if r.get("semantic_success") is True
                 and isinstance(r.get("http_status"), int) and 200 <= r["http_status"] < 300
                 and not r.get("timed_out")]
    values = [r["elapsed_ms"] for r in successes]
    latency = {"median": nearest_rank(values, 0.5) if values else None,
               "p75": nearest_rank(values, 0.75) if values else None,
               "p95": nearest_rank(values, 0.95) if values else None,
               "max": max(values) if values else None}
    return {"valid": bool(records) and len(successes) == len(records), "observed": len(records),
            "successful": len(successes), "failed": len(records) - len(successes),
            "timeouts": sum(bool(r.get("timed_out")) for r in records), "latency_ms": latency}


def require_ok(result, *, status=200):
    if result.status == 401:
        raise AuthAbort("Authentication failed; run stopped without retry/relogin")
    if result.status != status or result.error or result.timed_out or not isinstance(result.body, dict):
        raise ProtocolError(f"Expected HTTP {status}; observed {result.status}, error={bool(result.error)}")
    return result.body
