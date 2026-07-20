"""Mock Vestaboard Cloud API server for note-array development & integration testing.

Simulates the Vestaboard Cloud API (``https://cloud.vestaboard.com/``) used by
note-array boards, so the FiestaBoard backend can be tested end-to-end — in CI
*and* by hand in local dev — without a real board or Vestaboard account.
Stdlib-only; mirrors ``mock-board/server.py`` and ``mock-llm/server.py``.

The note-array Cloud API (see ``src/board_client.py``) uses:
  * POST ``/`` with header ``X-Vestaboard-Token`` and body ``{"characters": grid}``
    where ``grid`` is a rectangular ``rows×cols`` int array. Success is any 2xx.
  * GET ``/`` with header ``X-Vestaboard-Token`` returning
    ``{"currentMessage": {"layout": "<json-string-grid>", "id": "..."}}`` —
    ``layout`` is a JSON *string* encoding the 2-D int array.

Endpoints
---------

Cloud API (mimics cloud.vestaboard.com):
    POST /   - Send a note-array message ({"characters": grid})
    GET  /   - Read the current display state (currentMessage.layout)

Manual dev tool:
    GET  /ui            - A live web front-end that renders the current board as
                          split-flap tiles and lets you reset / reconfigure size.

Mock control (used by /ui and tests):
    GET  /mock/state     - Current grid, configured dims, request count, history
    POST /mock/reset     - Reset the grid to all-zeros (configured/default dims)
    POST /mock/configure - Reconfigure the board size at runtime; body is either
                           {"rows": R, "cols": C} or {"notes_wide": W, "notes_tall": H}.

Local dev
---------
``docker-compose.dev.yml`` runs this as ``fiestaboard-mock-cloud`` (host port
19200) and points the app at it via ``VESTABOARD_CLOUD_API_URL``. To use it:
add/select a note-array board in Settings, enter any token, send — then watch it
land at http://localhost:19200/ui.

Env vars
--------
PORT   - listen port (default 9200)
ROWS   - configured array rows (default 6); when ROWS or COLS is set, incoming
         POSTs are validated against the configured dimensions.
COLS   - configured array cols (default 30; 6×30 = a 2×2 note array)
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
# accepted and stored as-is. /mock/configure can change these at runtime.
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

    def reconfigure(self, rows: int, cols: int) -> None:
        """Change the configured board size and reset the grid to it."""
        with self._lock:
            self._rows = rows
            self._cols = cols
            self.current_grid = [[0] * cols for _ in range(rows)]
            self.history = []
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


# Self-contained dev front-end. Static HTML/CSS/JS — all live data is fetched
# from /mock/state, so nothing here needs server-side templating.
_FRONTEND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Mock Vestaboard — Note Array</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; font-family: -apple-system, system-ui, sans-serif;
    background: #0c0d10; color: #e7e9ee;
  }
  h1 { font-size: 16px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #8b909c; font-size: 12px; margin-bottom: 18px; }
  .board-wrap { overflow-x: auto; padding: 14px; background: #000; border-radius: 10px;
    border: 1px solid #23262e; display: inline-block; max-width: 100%; }
  .board { display: grid; gap: 3px; }
  .tile {
    width: 26px; height: 34px; border-radius: 3px; display: flex; align-items: center;
    justify-content: center; font-family: "SF Mono", ui-monospace, monospace;
    font-size: 17px; font-weight: 600; color: #f4f4f6;
    background: linear-gradient(#1c1f25, #141619); box-shadow: inset 0 -2px 3px #0006, inset 0 1px 0 #ffffff10;
    border-top: 1px solid #ffffff0d;
  }
  .tile.color { color: transparent; }
  .meta { margin-top: 16px; font-size: 12px; color: #aeb3bd; line-height: 1.7; }
  .meta b { color: #e7e9ee; font-weight: 600; }
  .controls { margin-top: 18px; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
  button, select, input {
    font: inherit; font-size: 13px; background: #1b1e25; color: #e7e9ee;
    border: 1px solid #2c313b; border-radius: 7px; padding: 7px 12px; cursor: pointer;
  }
  button:hover { background: #242832; }
  input { width: 56px; cursor: text; }
  label { font-size: 12px; color: #aeb3bd; }
  .hint { margin-top: 22px; font-size: 11px; color: #6b7280; max-width: 640px; line-height: 1.6; }
  code { background: #1b1e25; padding: 1px 5px; border-radius: 4px; color: #c8cdd6; }
</style>
</head>
<body>
  <h1>Mock Vestaboard <span style="color:#6b7280">· Note Array</span></h1>
  <div class="sub" id="dims">connecting…</div>
  <div class="board-wrap"><div class="board" id="board"></div></div>
  <div class="meta">
    Messages received: <b id="count">0</b> &nbsp;·&nbsp; Last update: <b id="last">—</b>
  </div>
  <div class="controls">
    <label>Size:</label>
    <select id="preset">
      <option value="6,22">Flagship (22 × 6)</option>
      <option value="3,15">Note (15 × 3)</option>
      <option value="3,30">2 side-by-side (30 × 3)</option>
      <option value="3,60">4 side-by-side (60 × 3)</option>
      <option value="6,15">2 stacked (15 × 6)</option>
      <option value="12,15">4 stacked (15 × 12)</option>
      <option value="6,30" selected>2×2 grid (30 × 6)</option>
      <option value="custom">Custom…</option>
    </select>
    <span id="customWrap" style="display:none">
      <input id="cw" type="number" min="1" max="8" value="2" /> ×
      <input id="ch" type="number" min="1" max="8" value="2" />
      <label>notes (W × H)</label>
    </span>
    <button id="apply">Apply size</button>
    <button id="reset">Reset board</button>
  </div>
  <div class="hint">
    Point a note-array board at this server (the dev app does this automatically via
    <code>VESTABOARD_CLOUD_API_URL</code>), enter any token in Settings, and send — the
    grid below updates live. The Cloud API itself is at <code>POST/GET /</code> with an
    <code>X-Vestaboard-Token</code> header.
  </div>
<script>
// Vestaboard character codes -> display glyph (or a color tile).
const PUNCT = {37:"!",38:"@",39:"#",40:"$",41:"(",42:")",44:"-",46:"+",47:"&",48:"=",
  49:";",50:":",52:"'",53:'"',54:"%",55:",",56:".",59:"/",60:"?",62:"\\u00B0"};
const COLORS = {63:"#d8112a",64:"#e96d24",65:"#f7d000",66:"#1d8a3f",67:"#2456a6",
  68:"#7a3b8f",69:"#f3f3f3",70:"#15171a"};
function glyph(code){
  if (code === 0) return {ch:""};
  if (code >= 1 && code <= 26) return {ch:String.fromCharCode(64+code)};      // A-Z
  if (code >= 27 && code <= 35) return {ch:String(code-26)};                   // 1-9
  if (code === 36) return {ch:"0"};
  if (code in PUNCT) return {ch:PUNCT[code]};
  if (code in COLORS) return {ch:"", color:COLORS[code]};
  return {ch:""};
}
const boardEl = document.getElementById("board");
function render(state){
  const g = state.current_grid || [];
  const rows = g.length, cols = rows ? g[0].length : 0;
  document.getElementById("dims").textContent =
    cols + " \\u00D7 " + rows + " characters  (" + (cols/15|0) + "\\u00D7" + (rows/3|0) + " notes)";
  document.getElementById("count").textContent = state.request_count;
  const h = state.history || [];
  document.getElementById("last").textContent = h.length ? new Date(h[h.length-1].timestamp).toLocaleTimeString() : "\\u2014";
  boardEl.style.gridTemplateColumns = "repeat(" + cols + ", 26px)";
  const cells = [];
  for (const row of g) for (const code of row){
    const gl = glyph(code);
    const cls = gl.color ? "tile color" : "tile";
    const style = gl.color ? ' style="background:'+gl.color+'"' : "";
    cells.push("<div class='"+cls+"'"+style+">"+gl.ch+"</div>");
  }
  boardEl.innerHTML = cells.join("");
}
async function poll(){
  try { const r = await fetch("/mock/state"); render(await r.json()); } catch(e){}
}
document.getElementById("reset").onclick = async () => { await fetch("/mock/reset",{method:"POST"}); poll(); };
document.getElementById("preset").onchange = (e) => {
  document.getElementById("customWrap").style.display = e.target.value === "custom" ? "inline" : "none";
};
document.getElementById("apply").onclick = async () => {
  const v = document.getElementById("preset").value;
  let body;
  if (v === "custom"){
    body = {notes_wide:+document.getElementById("cw").value, notes_tall:+document.getElementById("ch").value};
  } else { const parts = v.split(",").map(Number); body = {rows:parts[0],cols:parts[1]}; }
  await fetch("/mock/configure",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  poll();
};
poll(); setInterval(poll, 1000);
</script>
</body>
</html>"""


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

    def _send_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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

        if self.path in ("/ui", "/ui/"):
            self._send_html(200, _FRONTEND_HTML)
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
                # Distinct from the missing-key error above: the key is present but
                # the value isn't a non-empty rectangular 2-D int grid.
                self._send_json(400, {"error": "'characters' must be a non-empty rectangular 2-D int array"})
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

        if self.path == "/mock/configure":
            self._handle_configure()
            return

        self._send_json(404, {"error": "Not found"})

    def _handle_configure(self) -> None:
        """Reconfigure the board size at runtime (for the /ui dev tool).

        Body is either ``{"rows": R, "cols": C}`` or ``{"notes_wide": W, "notes_tall": H}``
        (a note array is notes_wide×15 cols by notes_tall×3 rows). Resets the grid.
        """
        global _ROWS, _COLS, _STRICT_DIMS
        body = self._read_json()
        if not isinstance(body, dict):
            self._send_json(400, {"error": "Body must be a JSON object"})
            return

        if "notes_wide" in body or "notes_tall" in body:
            try:
                nw = int(body.get("notes_wide", 1))
                nt = int(body.get("notes_tall", 1))
            except (TypeError, ValueError):
                self._send_json(400, {"error": "notes_wide/notes_tall must be integers"})
                return
            if not (1 <= nw <= 8 and 1 <= nt <= 8):
                self._send_json(400, {"error": "notes_wide/notes_tall must be 1-8"})
                return
            rows, cols = nt * 3, nw * 15
        else:
            try:
                rows = int(body["rows"])
                cols = int(body["cols"])
            except (KeyError, TypeError, ValueError):
                self._send_json(400, {"error": "Provide rows+cols or notes_wide+notes_tall"})
                return
            if not (1 <= rows <= 24 and 1 <= cols <= 120):
                self._send_json(400, {"error": "rows must be 1-24, cols 1-120"})
                return

        _ROWS, _COLS, _STRICT_DIMS = rows, cols, True
        STATE.reconfigure(rows, cols)
        self._send_json(200, {"ok": True, "configured_rows": rows, "configured_cols": cols})

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
        "Mock Cloud API on 0.0.0.0:%d (rows=%d, cols=%d, strict_dims=%s) — front-end at /ui",
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
