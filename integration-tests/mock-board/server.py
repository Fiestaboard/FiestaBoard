"""Mock Vestaboard API server for integration testing.

Simulates the Vestaboard Local API so the FiestaBoard backend can be tested
end-to-end without a real board. Supports a single port (default 7000) or
multiple ports for multi-board e2e (e.g. PORTS=7000,7001).

Supports both Flagship (6x22) and Note (3x15) character arrays.

Endpoints (on each port):
  POST /local-api/message  - Send a message (text or character array)
  GET  /local-api/message  - Read the current display state

Mock control endpoints (port can be specified for multi-board):
  GET  /mock/state[?port=7000]   - Return state for port (default: current port). Omit ?port for current.
  POST /mock/reset              - Body optional {"port": 7000}. Omit to reset all ports.
  GET  /mock/boards             - Return list of ports (for e2e discovery).
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock
from urllib.parse import parse_qs, urlparse

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


# Global registry: port -> MockBoardState (set by run() for multi-port)
_states_by_port: dict = {}
_default_port: int = 7000


def _get_state_for_port(port: int):
    """Get MockBoardState for the given port. Used by handler."""
    return _states_by_port.get(port)


class MockBoardHandler(BaseHTTPRequestHandler):
    """HTTP handler that mimics the Vestaboard Local API. Uses port from server_address for state."""

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

    def _current_port(self):
        return self.server.server_address[1]

    def _state(self):
        return _get_state_for_port(self._current_port())

    # --- Vestaboard Local API ---

    def do_GET(self):  # noqa: N802 (HTTP method naming convention)
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/local-api/message":
            state = self._state()
            if state is None:
                self._send_json(503, {"error": "No state for this port"})
                return
            self._send_json(200, state.get_message())

        elif path == "/mock/state":
            # Optional ?port=7000 to get state for a specific port
            port = self._current_port()
            if "port" in query and query["port"]:
                try:
                    port = int(query["port"][0])
                except (ValueError, IndexError):
                    pass
            state = _get_state_for_port(port)
            if state is None:
                self._send_json(404, {"error": f"No mock state for port {port}"})
                return
            out = state.get_state()
            out["port"] = port
            self._send_json(200, out)

        elif path == "/mock/boards":
            self._send_json(200, {"ports": sorted(_states_by_port.keys())})

        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        if self.path == "/local-api/message":
            state = self._state()
            if state is None:
                self._send_json(503, {"error": "No state for this port"})
                return

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

                state.set_message(chars, strategy=body.get("strategy"), dimensions=dims)
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
                state.set_message(chars, dimensions=(rows, cols))
                self._send_json(200, {"ok": True})
            else:
                self._send_json(400, {"error": "Request must include 'characters' or 'text'"})

        elif self.path == "/mock/reset":
            body = self._read_body() or {}
            port = body.get("port") if isinstance(body, dict) else None
            if port is not None:
                try:
                    port = int(port)
                except (TypeError, ValueError):
                    port = None
            if port is not None and port in _states_by_port:
                _states_by_port[port].reset()
                self._send_json(200, {"ok": True, "message": f"Mock reset for port {port}"})
            else:
                for s in _states_by_port.values():
                    s.reset()
                self._send_json(200, {"ok": True, "message": "Mock reset (all ports)"})
        else:
            self._send_json(404, {"error": "Not found"})

    def log_message(self, fmt, *args):
        """Suppress default request logging."""


def run(port=7000, ports=None):
    """Start the mock board server.

    Args:
        port: Single port (used if ports is None). Default 7000.
        ports: List of ports for multi-board (e.g. [7000, 7001]). Overrides port if set.
    """
    global _states_by_port, _default_port

    if ports is None:
        ports = [port]
    else:
        ports = list(ports)
    _default_port = ports[0]
    _states_by_port.clear()
    _states_by_port.update({p: MockBoardState() for p in ports})

    def serve_on(p):
        server = HTTPServer(("0.0.0.0", p), MockBoardHandler)
        logger.info("Mock Vestaboard API listening on port %d", p)
        print(f"Mock Vestaboard API listening on port {p}", flush=True)
        server.serve_forever()

    if len(ports) == 1:
        serve_on(ports[0])
        return

    threads = []
    for p in ports:
        t = threading.Thread(target=serve_on, args=(p,), daemon=True)
        t.start()
        threads.append(t)
    try:
        while True:
            for t in threads:
                t.join(timeout=1)
                if not t.is_alive():
                    break
    except KeyboardInterrupt:
        pass


def _parse_ports():
    """Parse PORTS env (e.g. 7000,7001) or argv --ports 7000 7001."""
    env_ports = os.environ.get("PORTS")
    if env_ports:
        return [int(p.strip()) for p in env_ports.split(",") if p.strip()]
    return None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    ports = _parse_ports()
    if ports:
        run(ports=ports)
    else:
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 7000
        run(port=port)
