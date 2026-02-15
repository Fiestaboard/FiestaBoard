"""Mock Vestaboard API server for integration testing.

Simulates the Vestaboard Local API (port 7000) so the FiestaBoard
backend can be tested end-to-end without a real board.

Endpoints:
  POST /local-api/message  - Send a message (text or character array)
  GET  /local-api/message   - Read the current display state

The mock also exposes helper endpoints for test assertions:
  GET  /mock/state          - Return full mock state (message history, etc.)
  POST /mock/reset          - Reset the mock to its initial state
"""

import json
import logging
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock

logger = logging.getLogger(__name__)

# Blank board: 6 rows x 22 columns, all zeros
BLANK_BOARD = [[0] * 22 for _ in range(6)]


class MockBoardState:
    """Thread-safe state container for the mock board."""

    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.current_message = [row[:] for row in BLANK_BOARD]
            self.message_history = []
            self.request_count = 0

    def set_message(self, characters, strategy=None):
        with self._lock:
            self.current_message = [row[:] for row in characters]
            self.message_history.append({
                "characters": [row[:] for row in characters],
                "strategy": strategy,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self.request_count += 1

    def get_message(self):
        with self._lock:
            return [row[:] for row in self.current_message]

    def get_state(self):
        with self._lock:
            return {
                "current_message": self.current_message,
                "message_count": len(self.message_history),
                "request_count": self.request_count,
                "history": self.message_history[-10:],  # last 10
            }


# Module-level singleton so the handler can access it
_state = MockBoardState()


class MockBoardHandler(BaseHTTPRequestHandler):
    """HTTP handler that mimics the Vestaboard Local API."""

    def _send_json(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        return json.loads(self.rfile.read(length))

    # --- Vestaboard Local API ---

    def do_GET(self):  # noqa: N802 (HTTP method naming convention)
        if self.path == "/local-api/message":
            self._send_json(200, _state.get_message())
        elif self.path == "/mock/state":
            self._send_json(200, _state.get_state())
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        if self.path == "/local-api/message":
            body = self._read_body()
            if body is None:
                self._send_json(400, {"error": "Empty body"})
                return

            # Handle character array format
            if "characters" in body:
                chars = body["characters"]
                if not isinstance(chars, list) or len(chars) != 6:
                    self._send_json(400, {"error": "characters must be a 6-row array"})
                    return
                for row in chars:
                    if not isinstance(row, list) or len(row) != 22:
                        self._send_json(400, {"error": "Each row must have 22 columns"})
                        return
                _state.set_message(chars, strategy=body.get("strategy"))
                self._send_json(200, {"ok": True})

            # Handle text format
            elif "text" in body:
                # Simple text-to-board: store as character array with char codes
                text = body["text"].upper()
                chars = [row[:] for row in BLANK_BOARD]
                row_idx = 0
                col_idx = 0
                for ch in text:
                    if ch == "\n":
                        row_idx += 1
                        col_idx = 0
                        if row_idx >= 6:
                            break
                        continue
                    if col_idx < 22 and row_idx < 6:
                        # Map ASCII to Vestaboard character codes
                        if ch == " ":
                            chars[row_idx][col_idx] = 0
                        elif "A" <= ch <= "Z":
                            chars[row_idx][col_idx] = ord(ch) - ord("A") + 1
                        elif "0" <= ch <= "9":
                            chars[row_idx][col_idx] = ord(ch) - ord("0") + 27
                        else:
                            chars[row_idx][col_idx] = 0
                        col_idx += 1
                _state.set_message(chars)
                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"error": "Request must include 'characters' or 'text'"})

        elif self.path == "/mock/reset":
            _state.reset()
            self._send_json(200, {"ok": True, "message": "Mock reset"})
        else:
            self._send_json(404, {"error": "Not found"})

    def log_message(self, format, *args):
        """Suppress default request logging."""


def run(port=7000):
    """Start the mock board server.

    Default port is 7000 to match the Vestaboard Local API port
    that the BoardClient hard-codes.
    """
    server = HTTPServer(("0.0.0.0", port), MockBoardHandler)
    logger.info("Mock Vestaboard API listening on port %d", port)
    print(f"Mock Vestaboard API listening on port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7000
    run(port)
