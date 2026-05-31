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
)

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
            self.history: list[dict] = []
            self.request_count = 0

    def set_scenario(self, scenario: str) -> None:
        with self._lock:
            self.scenario = scenario

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
            status, payload = _content_for_scenario(STATE.scenario, body)
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
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
