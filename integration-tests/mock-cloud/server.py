"""Mock Vestaboard Cloud API server for note-array integration testing.

Simulates the Vestaboard Cloud API (``https://cloud.vestaboard.com/``) used by
note-array boards, so the FiestaBoard backend can be tested end-to-end without
a real board or Vestaboard account. Stdlib-only — mirrors ``mock-board/server.py``
and ``mock-llm/server.py``.

The note-array Cloud API (see ``src/board_client.py``) uses:
  * POST ``/`` with header ``X-Vestaboard-Token`` and body ``{"characters": grid}``
    where ``grid`` is a rectangular ``rows×cols`` int array. Success is any 2xx.
  * GET ``/`` with header ``X-Vestaboard-Token`` returning
    ``{"currentMessage": {"layout": "<json-string-grid>", "id": "..."}}`` —
    note that ``layout`` is a JSON *string* encoding the 2-D int array.

Endpoints
---------

Cloud API (mimics cloud.vestaboard.com):
    POST /   - Send a note-array message ({"characters": grid})
    GET  /   - Read the current display state (currentMessage.layout)

Mock control:
    GET  /mock/state   - Return current grid, configured dims, request count, history
    POST /mock/reset   - Reset the grid to all-zeros (configured/default dims)

Env vars
--------
PORT   - listen port (default 9200)
ROWS   - configured array rows (default 6); when ROWS or COLS is set, incoming
         POSTs are validated against the configured dimensions.
COLS   - configured array cols (default 30; 6×30 = a 2×2 note array)

The defaults match the ``fiestaboard-mock-cloud`` compose service and the CI job.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock

logger = logging.getLogger(__name__)

MAX_CHAR_CODE = 71

# Configured at startup from env. When ROWS or COLS is explicitly set, incoming
# POSTs are validated against these dimensions; otherwise any valid grid is
# accepted and stored as-is.
_ROWS = int(os.environ.get("ROWS", "6"))
_COLS = int(os.environ.get("COLS", "30"))
_STRICT_DIMS = bool(os.environ.get("ROWS") or os.environ.get("COLS"))


class MockCloudState:
    """Thread-safe state container for the mock Cloud API."""

    def __init__(self, rows: int, cols: int) -> None:
        self._lock = Lock()
        self._rows = rows
        self._cols = cols
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.current_grid = [[0] * self._cols for _ in range(self._rows)]
            self.history: list[dict] = []
            self.request_count = 0

    def set_grid(self, grid: list[list[int]]) -> None:
        with self._lock:
            self.current_grid = [row[:] for row in grid]
            # Update internal dims to match the stored grid.
            self._rows = len(grid)
            self._cols = len(grid[0]) if grid else self._cols
            self.history.append(
                {
                    "grid_dims": [self._rows, self._cols],
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            self.request_count += 1

    def get_grid(self) -> list[list[int]]:
        with self._lock:
            return [row[:] for row in self.current_grid]

    def get_state(self) -> dict:
        with self._lock:
            return {
                "current_grid": self.current_grid,
                "configured_rows": self._rows,
                "configured_cols": self._cols,
                "request_count": self.request_count,
                "history": self.history[-10:],
            }


STATE = MockCloudState(_ROWS, _COLS)


def _grid_dimensions(grid) -> tuple[int, int] | None:
    """Return (rows, cols) for a rectangular int grid, or None if malformed."""
    if not isinstance(grid, list) or len(grid) == 0:
        return None
    if not isinstance(grid[0], list):
        return None
    cols = len(grid[0])
    for row in grid:
        if not isinstance(row, list) or len(row) != cols:
            return None
    return (len(grid), cols)


class Handler(BaseHTTPRequestHandler):
    """HTTP handler that mimics the Vestaboard Cloud API for note arrays."""

    # ----- helpers ---------------------------------------------------------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _token(self) -> str | None:
        """Return the X-Vestaboard-Token header value, or None if absent/empty."""
        return self.headers.get("X-Vestaboard-Token") or None

    # ----- routes ----------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/":
            if self._token() is None:
                self._send_json(401, {"error": "Missing or invalid X-Vestaboard-Token"})
                return
            grid = STATE.get_grid()
            self._send_json(
                200,
                {
                    "currentMessage": {
                        "layout": json.dumps(grid),
                        "id": "mock-layout-id",
                    },
                },
            )
            return

        if self.path == "/mock/state":
            self._send_json(200, STATE.get_state())
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:
        if self.path == "/":
            if self._token() is None:
                self._send_json(401, {"error": "Missing or invalid X-Vestaboard-Token"})
                return

            body = self._read_json()
            if not isinstance(body, dict) or not isinstance(body.get("characters"), list):
                self._send_json(400, {"error": "Request must include 'characters'"})
                return

            grid = body["characters"]
            dims = _grid_dimensions(grid)
            if dims is None:
                self._send_json(400, {"error": "Request must include 'characters'"})
                return

            rows, cols = dims
            if _STRICT_DIMS and (rows != _ROWS or cols != _COLS):
                self._send_json(
                    400,
                    {
                        "error": (f"Grid dimensions {rows}x{cols} do not match configured array size {_ROWS}x{_COLS}"),
                    },
                )
                return

            for r_idx, row in enumerate(grid):
                for c_idx, code in enumerate(row):
                    if not isinstance(code, int) or isinstance(code, bool) or code < 0 or code > MAX_CHAR_CODE:
                        self._send_json(
                            400,
                            {
                                "error": (
                                    f"Invalid character code {code} at row {r_idx}, "
                                    f"col {c_idx}. Must be 0-{MAX_CHAR_CODE}."
                                ),
                            },
                        )
                        return

            STATE.set_grid(grid)
            self._send_json(200, {"ok": True})
            return

        if self.path == "/mock/reset":
            STATE.reset()
            self._send_json(200, {"ok": True, "message": "Mock reset"})
            return

        self._send_json(404, {"error": "Not found"})

    def log_message(self, fmt: str, *args) -> None:
        """Suppress default request logging to keep CI output readable."""


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s mock-cloud %(levelname)s %(message)s",
    )
    port = int(os.environ.get("PORT", "9200"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info(
        "Mock Cloud API listening on 0.0.0.0:%d (rows=%d, cols=%d, strict_dims=%s)",
        port,
        _ROWS,
        _COLS,
        _STRICT_DIMS,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down mock Cloud API server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
