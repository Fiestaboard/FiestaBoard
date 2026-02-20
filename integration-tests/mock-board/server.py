"""Mock Vestaboard API server for integration testing.

Simulates the Vestaboard Local API (port 7000) so the FiestaBoard
backend can be tested end-to-end without a real board.

Supports both Flagship (6x22) and Note (3x15) character arrays.

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

# Valid board dimensions: (rows, cols)
VALID_DIMENSIONS = {
    (6, 22),  # Flagship
    (3, 15),  # Note
}

BLANK_BOARD = [[0] * 22 for _ in range(6)]
BLANK_NOTE = [[0] * 15 for _ in range(3)]

# Character encoding for text-mode requests (matches Vestaboard spec)
CHAR_TO_CODE = {
    " ": 0,
    "!": 37, "@": 38, "#": 39, "$": 40,
    "(": 41, ")": 42, "-": 44, "+": 46,
    "&": 47, "=": 48, ";": 49, ":": 50,
    "'": 52, '"': 53, "%": 54, ",": 55,
    ".": 56, "/": 59, "?": 60,
}

MAX_CHAR_CODE = 71


def _blank_for_dims(rows, cols):
    return [[0] * cols for _ in range(rows)]


class MockBoardState:
    """Thread-safe state container for the mock board."""

    def __init__(self):
        self._lock = Lock()
        self.reset()

    def reset(self):
        with self._lock:
            self.current_message = [row[:] for row in BLANK_BOARD]
            self.current_dimensions = (6, 22)
            self.message_history = []
            self.request_count = 0

    def set_message(self, characters, strategy=None, dimensions=None):
        with self._lock:
            self.current_message = [row[:] for row in characters]
            if dimensions:
                self.current_dimensions = dimensions
            self.message_history.append({
                "characters": [row[:] for row in characters],
                "strategy": strategy,
                "dimensions": list(dimensions) if dimensions else list(self.current_dimensions),
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
                "device_dimensions": list(self.current_dimensions),
                "message_count": len(self.message_history),
                "request_count": self.request_count,
                "history": self.message_history[-10:],
            }


_state = MockBoardState()


def _detect_dimensions(chars):
    """Return (rows, cols) for a character array, or None if invalid."""
    if not isinstance(chars, list) or len(chars) == 0:
        return None
    rows = len(chars)
    cols = len(chars[0]) if isinstance(chars[0], list) else None
    if cols is None:
        return None
    if (rows, cols) not in VALID_DIMENSIONS:
        return None
    for row in chars:
        if not isinstance(row, list) or len(row) != cols:
            return None
    return (rows, cols)


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

            if "characters" in body:
                chars = body["characters"]
                dims = _detect_dimensions(chars)
                if dims is None:
                    self._send_json(400, {
                        "error": (
                            "characters must be a valid board array: "
                            "6x22 (Flagship) or 3x15 (Note)"
                        ),
                    })
                    return

                # Validate character codes are in range 0-71
                for r_idx, row in enumerate(chars):
                    for c_idx, code in enumerate(row):
                        if not isinstance(code, int) or code < 0 or code > MAX_CHAR_CODE:
                            self._send_json(400, {
                                "error": (
                                    f"Invalid character code {code} at row {r_idx}, "
                                    f"col {c_idx}. Must be 0-{MAX_CHAR_CODE}."
                                ),
                            })
                            return

                _state.set_message(chars, strategy=body.get("strategy"), dimensions=dims)
                self._send_json(200, {"ok": True})

            elif "text" in body:
                rows = int(body.get("rows", 6))
                cols = int(body.get("cols", 22))
                if (rows, cols) not in VALID_DIMENSIONS:
                    self._send_json(400, {
                        "error": f"Unsupported dimensions {rows}x{cols}",
                    })
                    return

                text = body["text"].upper()
                chars = _blank_for_dims(rows, cols)
                row_idx = 0
                col_idx = 0
                for ch in text:
                    if ch == "\n":
                        row_idx += 1
                        col_idx = 0
                        if row_idx >= rows:
                            break
                        continue
                    if col_idx < cols and row_idx < rows:
                        if "A" <= ch <= "Z":
                            chars[row_idx][col_idx] = ord(ch) - ord("A") + 1
                        elif "1" <= ch <= "9":
                            chars[row_idx][col_idx] = ord(ch) - ord("1") + 27
                        elif ch == "0":
                            chars[row_idx][col_idx] = 36
                        elif ch in CHAR_TO_CODE:
                            chars[row_idx][col_idx] = CHAR_TO_CODE[ch]
                        else:
                            chars[row_idx][col_idx] = 0
                        col_idx += 1
                _state.set_message(chars, dimensions=(rows, cols))
                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"error": "Request must include 'characters' or 'text'"})

        elif self.path == "/mock/reset":
            _state.reset()
            self._send_json(200, {"ok": True, "message": "Mock reset"})
        else:
            self._send_json(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
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
