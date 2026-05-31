"""HTML renderer for FiestaBoard previews.

Produces a self-contained ``<!DOCTYPE html>`` document that visually mimics
a Vestaboard / FiestaBoard physical display. Used by the MCP server to
include an MCP-UI ``EmbeddedResource`` alongside page tool responses, so
MCP-UI-aware clients (Claude Desktop, etc.) can render a board preview
inline next to the JSON result.

The renderer is intentionally simple: it parses the rendered template
text (post template-engine output) into character + colour tokens, then
emits one ``<div class="tile">`` per cell. A small CSS keyframe plays a
one-shot flap-in animation on first paint so the preview feels alive
without requiring any interactivity.

The HTML is fully static — no external assets, no API calls. It is safe
to embed in a sandboxed iframe.
"""

from __future__ import annotations

import html

# ---------------------------------------------------------------------------
# Constants — mirrored from web/src/lib/board-colors.ts and
# web/src/components/board-display.tsx so the preview matches the web UI.
# ---------------------------------------------------------------------------

DEVICE_DIMS: dict[str, tuple[int, int]] = {
    # device_type -> (rows, cols)
    "flagship": (6, 22),
    "note": (3, 15),
}

# 8-colour board palette (codes 63-71). 71 ("filled") renders as black, same
# as the web UI.
COLOR_CODE_MAP: dict[str, str] = {
    "63": "#eb4034",  # red
    "64": "#f5a623",  # orange
    "65": "#f8e71c",  # yellow
    "66": "#7ed321",  # green
    "67": "#4a90d9",  # blue
    "68": "#9b59b6",  # violet
    "69": "#ffffff",  # white
    "70": "#1a1a1a",  # black
    "71": "#1a1a1a",  # filled
}

NAMED_COLORS: dict[str, str] = {
    "red": COLOR_CODE_MAP["63"],
    "orange": COLOR_CODE_MAP["64"],
    "yellow": COLOR_CODE_MAP["65"],
    "green": COLOR_CODE_MAP["66"],
    "blue": COLOR_CODE_MAP["67"],
    "violet": COLOR_CODE_MAP["68"],
    "purple": COLOR_CODE_MAP["68"],
    "white": COLOR_CODE_MAP["69"],
    "black": COLOR_CODE_MAP["70"],
}

ALL_COLOR_CODES: dict[str, str] = {**COLOR_CODE_MAP, **NAMED_COLORS}


# ---------------------------------------------------------------------------
# Token parsing — mirrors parseLine() in board-display.tsx
# ---------------------------------------------------------------------------

class _CharToken:
    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value


class _ColorToken:
    __slots__ = ("hex",)

    def __init__(self, hex_value: str) -> None:
        self.hex = hex_value


def _parse_line(line: str) -> list[object]:
    """Parse a rendered line into a flat list of character/colour tokens.

    Matches the web UI's ``parseLine`` semantics: ``{63}`` / ``{red}`` style
    single-bracket tokens become colour tiles, ``{/...}`` end tags are
    dropped, anything else becomes an uppercase character tile.
    """
    tokens: list[object] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "{":
            close = line.find("}", i)
            if close != -1:
                content = line[i + 1 : close]
                if content.startswith("/"):
                    i = close + 1
                    continue
                hex_value = ALL_COLOR_CODES.get(content) or ALL_COLOR_CODES.get(content.lower())
                if hex_value is not None:
                    tokens.append(_ColorToken(hex_value))
                    i = close + 1
                    continue
        tokens.append(_CharToken(line[i].upper()))
        i += 1
    return tokens


def _grid(formatted: str, rows: int, cols: int, device_type: str) -> list[list[object]]:
    """Convert a rendered string into a fixed (rows x cols) token grid.

    Lines shorter than ``cols`` are right-padded with blank character
    tokens; extra lines beyond ``rows`` are ignored. Matches
    ``messageToGrid`` in the web UI, including the Note-device degree
    sign -> heart substitution.
    """
    is_note = device_type == "note"
    lines = formatted.split("\n") if formatted else []
    grid: list[list[object]] = []
    for r in range(rows):
        line = lines[r] if r < len(lines) else ""
        parsed = _parse_line(line)
        row: list[object] = []
        for c in range(cols):
            if c < len(parsed):
                tok = parsed[c]
                if is_note and isinstance(tok, _CharToken) and tok.value == "°":
                    row.append(_CharToken("♥"))
                else:
                    row.append(tok)
            else:
                row.append(_CharToken(" "))
        grid.append(row)
    return grid


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------

_STYLE = """
:root {
  color-scheme: dark;
  --board-bg: #0c0c0c;
  --board-frame: #1a1a1a;
  --tile-bg: #1a1a1a;
  --tile-text: #f5f0e6;
  --tile-split: rgba(0, 0, 0, 0.35);
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--board-bg);
  color: var(--tile-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  min-height: 100vh;
}
.wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px;
}
.label {
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.55;
}
.label strong { opacity: 0.9; font-weight: 600; }
.board {
  background: var(--board-frame);
  padding: 14px;
  border-radius: 12px;
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.04),
    0 12px 40px rgba(0, 0, 0, 0.55);
}
.row { display: flex; gap: 3px; justify-content: center; }
.row + .row { margin-top: 3px; }
.tile {
  width: 24px;
  height: 34px;
  border-radius: 3px;
  background: var(--tile-bg);
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: flap-in 360ms cubic-bezier(0.2, 0.7, 0.2, 1) both;
  animation-delay: calc((var(--r, 0) * 18ms) + (var(--c, 0) * 9ms));
}
.tile.note { width: 32px; height: 44px; }
.tile .char {
  font-family: "SF Mono", "Menlo", "Consolas", monospace;
  font-weight: 600;
  font-size: 16px;
  line-height: 1;
  color: var(--tile-text);
  user-select: none;
}
.tile.note .char { font-size: 22px; }
.tile .char.heart { color: #eb4034; }
.tile .swatch {
  position: absolute;
  inset: 5px 2px 6px;
  border-radius: 2px;
}
.tile::after {
  content: "";
  position: absolute;
  left: 0; right: 0;
  top: 50%;
  height: 1px;
  background: var(--tile-split);
  pointer-events: none;
}
@keyframes flap-in {
  0%   { transform: rotateX(-90deg); opacity: 0; }
  60%  { transform: rotateX(20deg);  opacity: 1; }
  100% { transform: rotateX(0deg);   opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .tile { animation: none; }
}
"""


def _tile_html(token: object, row: int, col: int, is_note: bool) -> str:
    """Emit the HTML for a single tile."""
    note_cls = " note" if is_note else ""
    style = f'style="--r:{row};--c:{col};"'
    if isinstance(token, _ColorToken):
        return (
            f'<div class="tile{note_cls}" {style}>'
            f'<div class="swatch" style="background:{token.hex};"></div>'
            f"</div>"
        )
    # Character token
    ch = token.value if isinstance(token, _CharToken) else " "
    if ch == " ":
        return f'<div class="tile{note_cls}" {style}></div>'
    is_heart = ch == "♥"
    char_cls = " heart" if is_heart else ""
    return (
        f'<div class="tile{note_cls}" {style}>'
        f'<span class="char{char_cls}">{html.escape(ch)}</span>'
        f"</div>"
    )


def render_board_html(
    formatted: str,
    *,
    device_type: str = "flagship",
    page_name: str | None = None,
) -> str:
    """Render a board preview as a self-contained HTML document.

    Args:
        formatted: The rendered template text (output of TemplateEngine.render
            or PageService.preview_page().formatted). May include ``{63}`` /
            ``{red}`` colour tokens and ``\\n``-separated lines.
        device_type: ``"flagship"`` (22x6) or ``"note"`` (15x3).
        page_name: Optional label rendered above the board.

    Returns:
        A standalone HTML document string (``<!DOCTYPE html>...``).
    """
    rows, cols = DEVICE_DIMS.get(device_type, DEVICE_DIMS["flagship"])
    is_note = device_type == "note"
    grid = _grid(formatted or "", rows, cols, device_type)

    row_html_parts: list[str] = []
    for r, row in enumerate(grid):
        tiles = "".join(_tile_html(tok, r, c, is_note) for c, tok in enumerate(row))
        row_html_parts.append(f'<div class="row">{tiles}</div>')
    board_html = "".join(row_html_parts)

    label_html = ""
    if page_name:
        safe_name = html.escape(page_name)
        label_html = (
            f'<div class="label"><strong>{safe_name}</strong> '
            f"&middot; {device_type} {cols}&times;{rows}</div>"
        )

    title = html.escape(page_name or "FiestaBoard Preview")
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        f"<style>{_STYLE}</style>"
        "</head><body>"
        '<div class="wrapper">'
        f"{label_html}"
        f'<div class="board" role="img" aria-label="{title}">{board_html}</div>'
        "</div>"
        "</body></html>"
    )


def render_page_preview_html(page: object) -> str:
    """Render an HTML preview for a Page model.

    Uses ``PageService.preview_page`` (which is cached) when available so
    template variables resolve against live plugin data. Falls back to
    rendering the raw template lines verbatim if the preview service is
    unavailable or the page has no template (e.g. composite pages — they
    are previewed as their stored content).

    Args:
        page: A ``src.pages.models.Page`` instance.

    Returns:
        A standalone HTML document string.
    """
    device_type = getattr(page, "device_type", "flagship") or "flagship"
    page_id = getattr(page, "id", None)
    page_name = getattr(page, "name", None)

    formatted: str = ""
    if page_id:
        try:
            from .pages.service import get_page_service

            svc = get_page_service()
            result = svc.preview_page(page_id)
            if result is not None and getattr(result, "formatted", None):
                formatted = result.formatted
        except Exception:
            # Fall through to template fallback below.
            formatted = ""

    if not formatted:
        template = getattr(page, "template", None)
        if template:
            formatted = "\n".join(template)

    return render_board_html(formatted, device_type=device_type, page_name=page_name)
