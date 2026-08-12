"""Mock OpenAI-compatible LLM server for AI / MCP integration testing.

Implements just enough of the OpenAI Chat Completions API for FiestaBoard's
``src/ai/generator.py`` to round-trip end-to-end without reaching out to a
real model. Stdlib-only — mirrors ``mock-board/server.py``.

Endpoints
---------

Provider side (mimics OpenAI):
    POST /v1/chat/completions
        Body:  {model, messages, temperature, max_tokens, response_format?}
        Behavior depends on the current scenario (see /mock/scenario):
          * "ok"           — return a valid FiestaBoard page in `choices[0].message.content`
          * "bad_json"     — return malformed JSON content
          * "missing_template" — return a JSON object without the required `template`
          * "auth_error"   — return HTTP 401 with an OpenAI-style error body
          * "server_error" — return HTTP 500 with an OpenAI-style error body
          * "echo_prompt"  — return JSON whose `name` reflects the last user prompt
                              (used to assert the prompt actually reached the LLM)

Mock control:
    GET  /mock/state       — return request history + current scenario
    POST /mock/reset       — clear history; reset scenario to "ok"
    POST /mock/scenario    — body {"scenario": "<name>"}; persist for later requests
    POST /mock/provider    — body {"provider": "<name>"}; emulate that provider's
                             request validation (see PROVIDERS below)
    POST /mock/script      — body {"prose": str?, "ops": [ {...}, ... ]}; the next
                             chat completion returns this content verbatim

Provider personalities
----------------------

By default the mock is ``permissive``: it accepts any well-formed body. That
is what let #1560 ship — the generator hardcoded
``response_format: {"type": "json_object"}``, LM Studio rejects it with a
400, and no test noticed because this server said yes to everything.

``POST /mock/provider`` switches on validation matching a real provider, so a
body that would 400 in production 400s here. The rules mirror
``tests/ai/provider_emulators.py``, which is the canonical source and carries
the citations; ``tests/test_mock_llm_provider_parity.py`` fails if the two
drift apart.

Streaming
---------

``/v1/chat/completions`` honors ``"stream": true`` and replies with an
OpenAI-style SSE stream (``data: {choices:[{delta:{content}}]}`` lines
terminated by ``data: [DONE]``), which is what ``src/ai/chat.py`` consumes.
Combined with ``/mock/script`` this lets a test drive the real chat panel and
choose exactly which tool ops the "model" emits.

Env vars
--------
PORT       — listen port (default 9100)

The defaults match what ``ai.spec.ts`` and the new CI job expect.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock

logger = logging.getLogger(__name__)

VALID_SCENARIOS = (
    "ok",
    "bad_json",
    "missing_template",
    "auth_error",
    "server_error",
    "echo_prompt",
    # Returns whatever POST /mock/script staged, verbatim. Used by the
    # browser apply-loop tests to pick which tool ops the model "emits".
    "script",
)

# Per-provider request validation. Mirrors tests/ai/provider_emulators.py —
# that module is canonical and carries the source citations for each rule.
# "permissive" is the default so existing tests keep their meaning.
#
#   response_formats: allowed response_format.type values; None = not validated
#   requires_auth:    reject when no Authorization: Bearer header is present
#   flat_error:       error envelope is {"error": "..."} not {"error": {...}}
PROVIDERS = {
    "permissive": {"response_formats": None, "requires_auth": False, "flat_error": False},
    "openai": {
        "response_formats": {"text", "json_object", "json_schema"},
        "requires_auth": True,
        "flat_error": False,
    },
    "openrouter": {
        "response_formats": {"text", "json_object", "json_schema"},
        "requires_auth": True,
        "flat_error": False,
    },
    # The #1560 provider: rejects json_object, and reports errors as a flat string.
    "lmstudio": {"response_formats": {"json_schema", "text"}, "requires_auth": False, "flat_error": True},
    "ollama": {"response_formats": {"text", "json_object"}, "requires_auth": False, "flat_error": False},
    "vllm": {
        "response_formats": {"text", "json_object", "json_schema"},
        "requires_auth": False,
        "flat_error": False,
    },
}

# A page payload the FiestaBoard generator will accept for a flagship board.
# 6 rows × ≤22 cols, all required fields present.
_DEFAULT_PAGE = {
    "name": "Mock AI Page",
    "type": "template",
    "device_type": "flagship",
    "template": [
        "MOCK LLM",
        "HELLO WORLD",
        "",
        "",
        "",
        "",
    ],
    "line_metadata": [
        {"alignment": "left", "wrap": False},
        {"alignment": "left", "wrap": False},
        {"alignment": "left", "wrap": False},
        {"alignment": "left", "wrap": False},
        {"alignment": "left", "wrap": False},
        {"alignment": "left", "wrap": False},
    ],
    "duration_seconds": 300,
}


class MockLLMState:
    """Thread-safe shared state across requests."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.scenario = "ok"
            self.provider = "permissive"
            self.script: dict | None = None
            self.history: list[dict] = []
            self.request_count = 0

    def set_scenario(self, scenario: str) -> None:
        with self._lock:
            self.scenario = scenario

    def set_provider(self, provider: str) -> None:
        with self._lock:
            self.provider = provider

    def set_script(self, script: dict) -> None:
        """Stage the content the next chat completion returns, and arm it."""
        with self._lock:
            self.script = script
            self.scenario = "script"

    def record_request(self, body: dict, headers: dict) -> None:
        with self._lock:
            # Trim headers down to what tests typically assert against, so
            # the state endpoint stays readable when curl'd by humans.
            kept = {k.lower(): v for k, v in headers.items() if k.lower() in {
                "authorization",
                "content-type",
                "x-api-key",
                "anthropic-version",
            }}
            self.history.append({
                "model": body.get("model"),
                "messages": body.get("messages"),
                "temperature": body.get("temperature"),
                "max_tokens": body.get("max_tokens"),
                "response_format": body.get("response_format"),
                "headers": kept,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self.request_count += 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "scenario": self.scenario,
                "provider": self.provider,
                "script": self.script,
                "request_count": self.request_count,
                "history": self.history[-10:],
            }


STATE = MockLLMState()


def _make_chat_completion(content: str, *, model: str) -> dict:
    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 17,
            "total_tokens": 59,
        },
    }


def _last_user_prompt(messages: list[dict]) -> str:
    for msg in reversed(messages or []):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
    return ""


def _provider_rejection(provider: str, body: dict, headers: dict) -> tuple[int, dict] | None:
    """Emulate a real provider's request validation.

    Returns ``(status, error_body)`` when the provider would refuse, else None.
    """
    rules = PROVIDERS.get(provider) or PROVIDERS["permissive"]

    def err(status: int, message: str) -> tuple[int, dict]:
        if rules["flat_error"]:
            return status, {"error": message}
        return status, {"error": {"message": message, "type": "invalid_request_error"}}

    lower = {k.lower(): v for k, v in headers.items()}
    if rules["requires_auth"] and not str(lower.get("authorization", "")).startswith("Bearer "):
        return err(401, "Missing bearer credentials.")

    allowed = rules["response_formats"]
    rf = body.get("response_format")
    if allowed and rf is not None:
        if not isinstance(rf, dict) or "type" not in rf:
            return err(400, "'response_format' must be an object with a 'type'")
        if rf["type"] not in allowed:
            expected = " or ".join(f"'{v}'" for v in sorted(allowed))
            return err(400, f"'response_format.type' must be {expected}")
    return None


def _scripted_content(script: dict | None) -> str:
    """Render a staged script into assistant text.

    Each op becomes a ``fiestaboard`` fenced JSON block, which is the tool
    grammar ``src/ai/chat_ops.py`` parses out of the prose.
    """
    script = script or {}
    parts: list[str] = []
    prose = script.get("prose")
    if isinstance(prose, str) and prose:
        parts.append(prose)
    for op in script.get("ops") or []:
        parts.append("```fiestaboard\n" + json.dumps(op) + "\n```")
    return "\n\n".join(parts) if parts else "Nothing staged."


def _content_for_scenario(scenario: str, body: dict) -> tuple[int, dict]:
    """Return (http_status, response_body) for the given scenario."""
    model = body.get("model", "mock-model")

    if scenario == "auth_error":
        return 401, {"error": {"message": "Invalid API key.", "type": "auth_error"}}

    if scenario == "server_error":
        return 500, {"error": {"message": "Upstream exploded.", "type": "server_error"}}

    if scenario == "bad_json":
        return 200, _make_chat_completion("this is not json at all { ] }", model=model)

    if scenario == "missing_template":
        # Valid JSON but missing the required `template` array.
        return 200, _make_chat_completion(
            json.dumps({"name": "No template here", "type": "template"}),
            model=model,
        )

    if scenario == "echo_prompt":
        page = dict(_DEFAULT_PAGE)
        page["name"] = f"Echo: {_last_user_prompt(body.get('messages') or [])[:60]}"
        return 200, _make_chat_completion(json.dumps(page), model=model)

    if scenario == "script":
        return 200, _make_chat_completion(_scripted_content(STATE.script), model=model)

    # "ok" — the default happy path.
    return 200, _make_chat_completion(json.dumps(_DEFAULT_PAGE), model=model)


class Handler(BaseHTTPRequestHandler):
    # Quiet down the default access log so CI output stays readable.
    def log_message(self, format: str, *args) -> None:  # noqa: A002 — stdlib signature
        logger.info("%s - %s", self.address_string(), format % args)

    # ----- helpers ---------------------------------------------------------

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_completion(self, content: str, *, model: str) -> None:
        """Stream `content` as OpenAI-style SSE deltas.

        This is the format ``src/ai/chat.py::_iter_provider_stream`` consumes:
        ``data: {"choices":[{"delta":{"content": "..."}}]}`` lines, then
        ``data: [DONE]``. Chunked deliberately so the fence parser in chat.py
        is exercised across delta boundaries rather than handed one blob —
        that split is where a streaming tool-block parser actually breaks.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        chunk_size = 24
        for i in range(0, len(content), chunk_size):
            frame = {
                "id": f"chatcmpl-{int(time.time() * 1000)}",
                "object": "chat.completion.chunk",
                "model": model,
                "choices": [{"index": 0, "delta": {"content": content[i : i + chunk_size]}}],
            }
            self.wfile.write(f"data: {json.dumps(frame)}\n\n".encode())
            self.wfile.flush()

        final = {
            "id": "chatcmpl-final",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 17, "total_tokens": 59},
        }
        self.wfile.write(f"data: {json.dumps(final)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    # ----- routes ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 — stdlib name
        if self.path == "/mock/state":
            self._send_json(200, STATE.snapshot())
            return
        if self.path in ("/health", "/"):
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": {"message": "Not found"}})

    def do_POST(self) -> None:  # noqa: N802 — stdlib name
        if self.path == "/v1/chat/completions":
            body = self._read_json()
            headers = {k: v for k, v in self.headers.items()}
            STATE.record_request(body, headers)

            # Provider validation runs first: a real server rejects the request
            # before it ever reaches a model, so scenarios must not mask it.
            rejection = _provider_rejection(STATE.provider, body, headers)
            if rejection is not None:
                self._send_json(*rejection)
                return

            status, payload = _content_for_scenario(STATE.scenario, body)
            if status == 200 and body.get("stream"):
                content = payload["choices"][0]["message"]["content"]
                self._send_sse_completion(content, model=body.get("model", "mock-model"))
                return
            self._send_json(status, payload)
            return

        if self.path == "/mock/reset":
            STATE.reset()
            self._send_json(200, {"status": "ok"})
            return

        if self.path == "/mock/scenario":
            body = self._read_json()
            scenario = body.get("scenario")
            if scenario not in VALID_SCENARIOS:
                self._send_json(
                    400,
                    {
                        "error": {
                            "message": (
                                f"Unknown scenario {scenario!r}. "
                                f"Valid: {list(VALID_SCENARIOS)}"
                            )
                        }
                    },
                )
                return
            STATE.set_scenario(scenario)
            self._send_json(200, {"status": "ok", "scenario": scenario})
            return

        if self.path == "/mock/provider":
            body = self._read_json()
            provider = body.get("provider")
            if provider not in PROVIDERS:
                self._send_json(
                    400,
                    {"error": {"message": (f"Unknown provider {provider!r}. Valid: {sorted(PROVIDERS)}")}},
                )
                return
            STATE.set_provider(provider)
            self._send_json(200, {"status": "ok", "provider": provider})
            return

        if self.path == "/mock/script":
            body = self._read_json()
            ops = body.get("ops")
            if ops is not None and not isinstance(ops, list):
                self._send_json(400, {"error": {"message": "'ops' must be an array."}})
                return
            STATE.set_script({"prose": body.get("prose"), "ops": ops or []})
            self._send_json(200, {"status": "ok", "scenario": "script", "ops": len(ops or [])})
            return

        self._send_json(404, {"error": {"message": "Not found"}})


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s mock-llm %(levelname)s %(message)s",
    )
    port = int(os.environ.get("PORT", "9100"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info("Mock LLM listening on 0.0.0.0:%d (scenario=%s)", port, STATE.scenario)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down mock LLM server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
