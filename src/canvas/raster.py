"""Pure-Python canvas rasteriser (design §1, §3 step 2).

No Pillow or NumPy: output plugins run this too and cannot install
dependencies. Output is straight-alpha RGBA, row-major, 4 bytes per pixel.

**Pixel model.** Pixel ``(i, j)`` is the unit square ``[i, i+1) × [j, j+1)``
of the content space, sampled at its centre ``(i + 0.5, j + 0.5)``. All
rounding is deterministic and platform-independent:

- *Round half up* (``floor(v + 0.5)``) turns rect edges, text origins, the
  line width and gradient channels into integers. A rect covers pixels
  ``[round(x), round(x + w))``; a negative ``w``/``h`` is flipped first.
- Circles and ellipses fill the pixels whose centre satisfies
  ``dx²·ry² + dy²·rx² ≤ rx²·ry²``; a stroke is the pixels inside that and
  not inside the ellipse one pixel smaller (``rx - 1``, ``ry - 1``).
- Lines are Bresenham between the *floored* endpoints, endpoints inclusive,
  always drawn from the lexicographically smaller endpoint so a line looks
  the same whichever way it was written. ``width`` ``n`` stamps an ``n × n``
  square on each point, offset ``-(n - 1) // 2``.
- Polygons fill even-odd: pixel centres between alternate edge crossings of
  the row's centre line (edges half-open in y). A stroke is the closed
  outline of lines between the vertices.
- Text draws LED font bitmaps (:data:`src.led.fonts.LED_FONTS`) top-left
  anchored, advancing ``glyph_width + spacing_x`` per character and
  ``glyph_height + spacing_y`` per ``\\n``; a character the face lacks
  advances blank.
- Gradients are linear along ``(cos a, sin a)`` (y grows down: 0° is
  left→right, 90° top→bottom) across their rect, ``t`` running 0→1 over the
  rect's extent in that direction, each channel ``round(from + (to - from)·t)``.
  A transparent end fades the other end's colour to alpha 0.

Opaque colours overwrite; partial alpha (only from gradients) composites
source-over with round-half-up integer maths. Order: background, shapes in
order, then ``pixels`` rows (``.`` and transparent palette entries leave the
pixel as it is).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from src.led.fonts import LED_FONTS

from .evaluate import ResolvedContent, ResolvedShape
from .models import RGBA

__all__ = ["fit_nearest", "rasterize", "render_content", "upscale"]


def _rhu(value: float) -> int:
    """Round half up."""
    return math.floor(value + 0.5)


class _Surface:
    def __init__(self, width: int, height: int):
        self.w = width
        self.h = height
        self.buf = bytearray(width * height * 4)

    def span(self, y: int, x0: int, x1: int, color: RGBA) -> None:
        """Paint ``[x0, x1)`` on row *y*, clipped."""
        if y < 0 or y >= self.h:
            return
        x0 = max(x0, 0)
        x1 = min(x1, self.w)
        if x1 <= x0:
            return
        if color[3] == 255:
            off = (y * self.w + x0) * 4
            self.buf[off : off + (x1 - x0) * 4] = bytes(color) * (x1 - x0)
        elif color[3] > 0:
            for x in range(x0, x1):
                self._blend((y * self.w + x) * 4, color)

    def plot(self, x: int, y: int, color: RGBA) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            off = (y * self.w + x) * 4
            if color[3] == 255:
                self.buf[off : off + 4] = bytes(color)
            elif color[3] > 0:
                self._blend(off, color)

    def _blend(self, off: int, color: RGBA) -> None:
        sr, sg, sb, sa = color
        dr, dg, db, da = self.buf[off : off + 4]
        keep = da * (255 - sa) / 255
        out_a = sa + keep
        if out_a <= 0:
            return
        self.buf[off : off + 4] = bytes(
            (
                _rhu((sr * sa + dr * keep) / out_a),
                _rhu((sg * sa + dg * keep) / out_a),
                _rhu((sb * sa + db * keep) / out_a),
                _rhu(out_a),
            )
        )


# --- Shapes -------------------------------------------------------------------


def _rect(s: _Surface, v: dict) -> None:
    x, y, w, h = v["x"], v["y"], v["w"], v["h"]
    if w < 0:
        x, w = x + w, -w
    if h < 0:
        y, h = y + h, -h
    x0, x1, y0, y1 = _rhu(x), _rhu(x + w), _rhu(y), _rhu(y + h)
    if x1 <= x0 or y1 <= y0:
        return
    if v.get("fill"):
        for row in range(max(y0, 0), min(y1, s.h)):
            s.span(row, x0, x1, v["fill"])
    stroke = v.get("stroke")
    if stroke:
        s.span(y0, x0, x1, stroke)
        if y1 - 1 != y0:
            s.span(y1 - 1, x0, x1, stroke)
        for row in range(max(y0 + 1, 0), min(y1 - 1, s.h)):
            s.span(row, x0, x0 + 1, stroke)
            if x1 - 1 != x0:
                s.span(row, x1 - 1, x1, stroke)


def _ellipse_span(cx: float, cy: float, rx: float, ry: float, row: int) -> tuple[int, int] | None:
    """Inclusive pixel columns of *row* whose centres are inside the ellipse."""
    if rx <= 0 or ry <= 0:
        return None
    dy = row + 0.5 - cy
    lim = rx * rx * ry * ry
    dy_term = dy * dy * rx * rx
    if dy_term > lim:
        return None

    def inside(i: int) -> bool:
        dx = i + 0.5 - cx
        return dx * dx * ry * ry + dy_term <= lim

    half = rx * math.sqrt(max(0.0, 1 - (dy * dy) / (ry * ry)))
    i0 = math.ceil(cx - half - 0.5)
    i1 = math.floor(cx + half - 0.5)
    # Snap the estimate to the exact predicate so float error cannot move an edge.
    while inside(i0 - 1):
        i0 -= 1
    while i0 <= i1 and not inside(i0):
        i0 += 1
    while inside(i1 + 1):
        i1 += 1
    while i1 >= i0 and not inside(i1):
        i1 -= 1
    return (i0, i1) if i0 <= i1 else None


def _ellipse(s: _Surface, cx: float, cy: float, rx: float, ry: float, fill: RGBA | None, stroke: RGBA | None) -> None:
    rx, ry = abs(rx), abs(ry)
    top = max(0, math.floor(cy - ry) - 1)
    bottom = min(s.h, math.ceil(cy + ry) + 1)
    for row in range(top, bottom):
        outer = _ellipse_span(cx, cy, rx, ry, row)
        if outer is None:
            continue
        if fill:
            s.span(row, outer[0], outer[1] + 1, fill)
        if stroke:
            inner = _ellipse_span(cx, cy, rx - 1, ry - 1, row)
            if inner is None:
                s.span(row, outer[0], outer[1] + 1, stroke)
            else:
                s.span(row, outer[0], inner[0], stroke)
                s.span(row, inner[1] + 1, outer[1] + 1, stroke)


def _line(s: _Surface, x0: float, y0: float, x1: float, y1: float, color: RGBA | None, width: float = 1) -> None:
    if not color:
        return
    a = (math.floor(x0), math.floor(y0))
    b = (math.floor(x1), math.floor(y1))
    if a > b:
        a, b = b, a
    (x, y), (xe, ye) = a, b
    n = max(1, _rhu(width))
    back = (n - 1) // 2
    dx, dy = abs(xe - x), -abs(ye - y)
    step_x = 1 if x < xe else -1
    step_y = 1 if y < ye else -1
    err = dx + dy
    while True:
        if n == 1:
            s.plot(x, y, color)
        else:
            for row in range(y - back, y - back + n):
                s.span(row, x - back, x - back + n, color)
        if x == xe and y == ye:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += step_x
        if e2 <= dx:
            err += dx
            y += step_y


def _polygon(s: _Surface, points: Sequence[tuple[float, float]], fill: RGBA | None, stroke: RGBA | None) -> None:
    edges = list(zip(points, [*points[1:], points[0]], strict=True))
    if fill:
        ys = [p[1] for p in points]
        top = max(0, math.floor(min(ys)))
        bottom = min(s.h, math.ceil(max(ys)) + 1)
        for row in range(top, bottom):
            yc = row + 0.5
            xs = []
            for (ax, ay), (bx, by) in edges:
                if (ay <= yc < by) or (by <= yc < ay):
                    xs.append(ax + (yc - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                s.span(row, math.ceil(xs[k] - 0.5), math.ceil(xs[k + 1] - 0.5), fill)
    if stroke:
        for (ax, ay), (bx, by) in edges:
            _line(s, ax, ay, bx, by, stroke)


def _text(s: _Surface, v: dict) -> None:
    color = v["color"]
    if not color:
        return
    face = LED_FONTS[v["font"]]
    left = x = _rhu(v["x"])
    y = _rhu(v["y"])
    for ch in v["text"]:
        if ch == "\n":
            x = left
            y += face.glyph_height + face.spacing_y
            continue
        rows = face.glyphs.get(ch)
        if rows is not None:
            for dy, bits in enumerate(rows):
                for dx, bit in enumerate(bits):
                    if bit == "#":
                        s.plot(x + dx, y + dy, color)
        x += face.glyph_width + face.spacing_x


def _gradient(s: _Surface, v: dict) -> None:
    start, end = v["from"], v["to"]
    if start is None and end is None:
        return
    if start is None:
        start = (*end[:3], 0)
    if end is None:
        end = (*start[:3], 0)
    gx = 0.0 if v.get("x") is None else v["x"]
    gy = 0.0 if v.get("y") is None else v["y"]
    gw = s.w - gx if v.get("w") is None else v["w"]
    gh = s.h - gy if v.get("h") is None else v["h"]
    if gw < 0:
        gx, gw = gx + gw, -gw
    if gh < 0:
        gy, gh = gy + gh, -gh
    x0, x1, y0, y1 = _rhu(gx), _rhu(gx + gw), _rhu(gy), _rhu(gy + gh)
    if x1 <= x0 or y1 <= y0:
        return
    rad = math.radians(v["angle"])
    c, sn = round(math.cos(rad), 12), round(math.sin(rad), 12)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    half = (abs((x1 - x0) * c) + abs((y1 - y0) * sn)) / 2
    for row in range(max(y0, 0), min(y1, s.h)):
        for col in range(max(x0, 0), min(x1, s.w)):
            t = 0.0 if half == 0 else ((col + 0.5 - cx) * c + (row + 0.5 - cy) * sn + half) / (2 * half)
            t = min(1.0, max(0.0, t))
            s.plot(col, row, tuple(_rhu(a + (b - a) * t) for a, b in zip(start, end, strict=True)))


def _draw(s: _Surface, shape: ResolvedShape) -> None:
    v = shape.values
    kind = shape.type
    if kind == "rect":
        _rect(s, v)
    elif kind == "circle":
        _ellipse(s, v["cx"], v["cy"], v["r"], v["r"], v.get("fill"), v.get("stroke"))
    elif kind == "ellipse":
        _ellipse(s, v["cx"], v["cy"], v["rx"], v["ry"], v.get("fill"), v.get("stroke"))
    elif kind == "line":
        _line(s, v["x1"], v["y1"], v["x2"], v["y2"], v["stroke"], v.get("width", 1))
    elif kind == "polygon":
        _polygon(s, v["points"], v.get("fill"), v.get("stroke"))
    elif kind == "text":
        _text(s, v)
    elif kind == "gradient":
        _gradient(s, v)


# --- Public API ------------------------------------------------------------------


def rasterize(content: ResolvedContent, width: int, height: int) -> bytes:
    """Draw *content* onto a transparent ``width × height`` RGBA surface (its content space)."""
    s = _Surface(width, height)
    if content.background:
        for row in range(height):
            s.span(row, 0, width, content.background)
    for shape in content.shapes:
        _draw(s, shape)
    for j, row_chars in enumerate(content.pixels[:height]):
        for i, ch in enumerate(row_chars[:width]):
            if ch != ".":
                color = content.palette.get(ch)
                if color:
                    s.plot(i, j, color)
    return bytes(s.buf)


def fit_nearest(rgba: bytes, src_w: int, src_h: int, dst_w: int, dst_h: int) -> bytes:
    """Scale *rgba* nearest-neighbour into ``dst_w × dst_h``, aspect kept, centred, transparent letterbox.

    The fitted size is the largest with the source's aspect (floored);
    destination ``(x, y)`` inside it samples source ``(x·src_w // fit_w, y·src_h // fit_h)``.
    """
    if (src_w, src_h) == (dst_w, dst_h):
        return bytes(rgba)
    if dst_w * src_h <= dst_h * src_w:
        fit_w, fit_h = dst_w, max(1, src_h * dst_w // src_w)
    else:
        fit_w, fit_h = max(1, src_w * dst_h // src_h), dst_h
    off_x, off_y = (dst_w - fit_w) // 2, (dst_h - fit_h) // 2
    out = bytearray(dst_w * dst_h * 4)
    columns = [(x * src_w // fit_w) * 4 for x in range(fit_w)]
    src = memoryview(rgba)
    for y in range(fit_h):
        base = (y * src_h // fit_h) * src_w * 4
        row = b"".join(src[base + c : base + c + 4] for c in columns)
        off = ((off_y + y) * dst_w + off_x) * 4
        out[off : off + fit_w * 4] = row
    return bytes(out)


def upscale(rgba: bytes, width: int, height: int, factor: int) -> bytes:
    """Each pixel of *rgba* as a ``factor × factor`` block."""
    if factor == 1:
        return bytes(rgba)
    src = memoryview(rgba)
    rows = []
    for y in range(height):
        base = y * width * 4
        row = b"".join(bytes(src[base + x * 4 : base + x * 4 + 4]) * factor for x in range(width))
        rows.append(row * factor)
    return b"".join(rows)


def render_content(content: ResolvedContent | None, width: int, height: int) -> bytes:
    """*content* drawn at its ``size`` (default ``width × height``), then fitted to ``width × height``."""
    if content is None:
        return bytes(width * height * 4)
    src_w, src_h = content.size or (width, height)
    return fit_nearest(rasterize(content, src_w, src_h), src_w, src_h, width, height)
