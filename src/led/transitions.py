"""Transitions between two LED layouts: the frames a panel shows on a message change.

A port of FiestaUI's ``src/lib/led-transitions.ts`` (c2c3b72), the reference
implementation (plan D15, rev-7 amendments). A transition is a pure function
of time over two layouts: ``frame_at(0)`` is the old frame and
``frame_at(duration_ms)`` the new one, byte for byte. The golden sequences in
``tests/fixtures/led/led-golden.json`` hold it to FiestaUI's bytes, frame for
frame.

- ``flip``: **the FiestaBoard flip**. Every changing cell shows
  ``scramble_steps`` glyphs drawn from the layout's own character set (a
  plugin device's set, else the face's built-in set), one per ``step_ms``,
  then its target. Cells start up to ``stagger`` steps apart. The scramble is
  seeded from the cell and the change by stable glyph key (``led_flip_seed``), so it is
  the same in the preview and on the device. The second half of a step shows
  the half-turned flap (top of the next glyph over the bottom of the current)
  unless ``half_flap`` is off; a lit block field stays lit under it.
- ``cascade``: one half-flap per changed cell, in reading order.
- ``slide`` / ``wipe`` / ``fade`` / ``dissolve``: per pixel, on the two frames.

A device **frame budget** (``max_frames``) bounds the whole transition, first
frame to final frame inclusive: a flip shortens its stagger, then its
scramble; a continuous kind is quantised to that many evenly spaced samples,
indexed with integer arithmetic. The last frame is always the target.

A device that plays an uploaded sequence (a Divoom Pixoo) gets its upload from
:func:`transition_frames`; which transition a device runs, and with what
budget, is :mod:`src.led.transition_registry`.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from src.markup import BoardToken

from .charsets import BUILTIN_CHARACTER_SETS, CharacterSet
from .fonts import LED_FONTS
from .matrix import (
    LedCell,
    LedDrawOp,
    LedFrame,
    LedLayout,
    draw_glyph,
    glyph_key,
    layout_cells,
    paint_ops,
    rasterize,
)

__all__ = [
    "DEFAULT_LED_FLIP_STAGGER",
    "DEFAULT_LED_FLIP_STEP_MS",
    "DEFAULT_LED_SCRAMBLE_STEPS",
    "DEFAULT_LED_TRANSITION_MS",
    "LED_TRANSITION_KINDS",
    "MIN_CASCADE_SLOT_MS",
    "LedTransition",
    "LedTransitionKind",
    "LedTransitionSpec",
    "led_flip_seed",
    "mulberry32",
    "plan_transition",
    "scramble_pool",
    "transition_frames",
]

LedTransitionKind = Literal["flip", "cascade", "slide", "wipe", "fade", "dissolve"]
LED_TRANSITION_KINDS: tuple[LedTransitionKind, ...] = ("flip", "cascade", "slide", "wipe", "fade", "dissolve")

#: 80 ms: the split-flap renderer's standard cadence.
DEFAULT_LED_FLIP_STEP_MS = 80
DEFAULT_LED_TRANSITION_MS = 480
#: Six scrambled glyphs before the target: long enough to read as a roll.
DEFAULT_LED_SCRAMBLE_STEPS = 6
#: Cells start up to six steps apart, so a change settles as a cascade.
DEFAULT_LED_FLIP_STAGGER = 6
#: A cascade cell is half-flapped for at least this long.
MIN_CASCADE_SLOT_MS = 32

_MIN_STEP_MS = 8
_MAX_STEP_MS = 2000
_MAX_DURATION_MS = 20_000
_MAX_SCRAMBLE_STEPS = 60
_U32 = 0xFFFFFFFF
_SPEC_FIELDS = (
    ("duration_ms", "durationMs"),
    ("step_ms", "stepMs"),
    ("scramble_steps", "scrambleSteps"),
    ("stagger", "stagger"),
    ("half_flap", "halfFlap"),
    ("max_frames", "maxFrames"),
)


@dataclass(frozen=True)
class LedTransitionSpec:
    """A transition as asked for (FiestaUI ``LedTransitionSpec``); unset fields take defaults."""

    kind: LedTransitionKind
    #: Whole-transition length for every kind but ``flip``.
    duration_ms: float | None = None
    #: ``flip``: milliseconds per step.
    step_ms: float | None = None
    #: ``flip``: scrambled glyphs a changing cell shows before its target.
    scramble_steps: int | None = None
    #: ``flip``: the most steps a cell's scramble may be delayed by.
    stagger: int | None = None
    #: ``flip``: show the half-turned flap in the second half of each step.
    half_flap: bool | None = None
    #: A hard frame budget, first frame to final frame inclusive (minimum 2).
    max_frames: int | None = None

    @classmethod
    def from_dict(cls, raw: Mapping) -> LedTransitionSpec:
        """From FiestaUI's JSON shape (camelCase)."""
        return cls(raw["kind"], **{py: raw[js] for py, js in _SPEC_FIELDS if js in raw})

    def to_dict(self) -> dict:
        """To FiestaUI's JSON shape, unset fields omitted."""
        out: dict = {"kind": self.kind}
        out.update({js: getattr(self, py) for py, js in _SPEC_FIELDS if getattr(self, py) is not None})
        return out


@dataclass(frozen=True)
class _Resolved:
    kind: LedTransitionKind
    duration_ms: int
    step_ms: int
    scramble_steps: int
    stagger: int
    half_flap: bool
    max_frames: int | None


def _js_round(x: float) -> int:
    """``Math.round``: halves round up, toward +infinity."""
    return math.floor(x + 0.5)


def _resolve_spec(spec: LedTransitionKind | LedTransitionSpec) -> _Resolved:
    s = LedTransitionSpec(spec) if isinstance(spec, str) else spec

    def clamp(n: float | None, fallback: int, lo: int, hi: int) -> int:
        if n is None or not math.isfinite(n):
            return fallback
        return min(hi, max(lo, _js_round(n)))

    max_frames = None if s.max_frames is None or not math.isfinite(s.max_frames) else max(2, _js_round(s.max_frames))
    return _Resolved(
        kind=s.kind,
        duration_ms=clamp(s.duration_ms, DEFAULT_LED_TRANSITION_MS, 0, _MAX_DURATION_MS),
        step_ms=clamp(s.step_ms, DEFAULT_LED_FLIP_STEP_MS, _MIN_STEP_MS, _MAX_STEP_MS),
        scramble_steps=clamp(s.scramble_steps, DEFAULT_LED_SCRAMBLE_STEPS, 0, _MAX_SCRAMBLE_STEPS),
        stagger=clamp(s.stagger, DEFAULT_LED_FLIP_STAGGER, 0, _MAX_SCRAMBLE_STEPS),
        # A budgeted flip is one frame per step: a half-flap would be a frame
        # the budget does not have.
        half_flap=(True if s.half_flap is None else s.half_flap) if max_frames is None else False,
        max_frames=max_frames,
    )


@dataclass(frozen=True)
class LedTransition:
    """A planned transition (FiestaUI ``LedTransition``)."""

    kind: LedTransitionKind
    #: Total length; 0 when nothing changes.
    duration_ms: float
    #: The exact number of distinct frames, the final one included, when the
    #: transition is a sequence (a flip without half-flaps, or anything under
    #: a budget); ``None`` when it is continuous.
    frame_count: int | None
    from_frame: LedFrame = field(repr=False)
    to_frame: LedFrame = field(repr=False)
    #: The frame ``t`` milliseconds in: ``t <= 0`` is ``from_frame``,
    #: ``t >= duration_ms`` is ``to_frame``.
    frame_at: Callable[[float], LedFrame] = field(repr=False)
    #: Frame ``f`` of a sequenced transition, by integer index; ``None`` when continuous.
    frame_at_index: Callable[[int], LedFrame] | None = field(repr=False)
    #: The layout to treat as current at ``t`` (what a retargeted transition starts from).
    layout_at: Callable[[float], LedLayout] = field(repr=False)


def _settled(kind: LedTransitionKind, to: LedLayout, from_frame: LedFrame, to_frame: LedFrame) -> LedTransition:
    return LedTransition(
        kind,
        0,
        1,
        from_frame,
        to_frame,
        frame_at=lambda _t: to_frame,
        frame_at_index=lambda _f: to_frame,
        layout_at=lambda _t: to,
    )


# --- the FiestaBoard flip ---------------------------------------------------


def _imul(a: int, b: int) -> int:
    return (a * b) & _U32


def _fnv1a32(data: bytes) -> int:
    """FNV-1a, 32-bit: offset basis 0x811c9dc5, prime 0x01000193."""
    h = 0x811C9DC5
    for byte in data:
        h = _imul(h ^ byte, 0x01000193)
    return h


def led_flip_seed(cell_index: int, from_key: str, to_key: str, cols: int, rows: int) -> int:
    """One cell's scramble seed (FiestaUI ``ledFlipSeed``): the same in every process.

    FNV-1a 32-bit over ``u32le(cell_index) || u32le(cols) || u32le(rows) ||
    utf8(from_key) || 0x00 || utf8(to_key) || 0x00``, where the keys are
    stable glyph keys. It seeds :func:`mulberry32`.
    """
    data = (
        struct.pack("<III", cell_index & _U32, cols & _U32, rows & _U32)
        + from_key.encode("utf-8")
        + b"\x00"
        + to_key.encode("utf-8")
        + b"\x00"
    )
    return _fnv1a32(data)


def mulberry32(seed: int) -> Callable[[], float]:
    """mulberry32, bit for bit as FiestaUI runs it: floats in [0, 1)."""
    a = seed & _U32

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _U32
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & _U32) ^ t
        return (t ^ (t >> 14)) / 4294967296

    return rng


def _charset_for_layout(layout: LedLayout) -> CharacterSet:
    """The set a scramble draws from: the layout's own, else its face's built-in set."""
    if layout.options.charset:
        return layout.options.charset
    return BUILTIN_CHARACTER_SETS["led_3x5" if layout.grid.font == "3x5" else "led_5x7"]


def scramble_pool(charset: CharacterSet) -> list[str]:
    """The glyphs a scramble may show on a device (FiestaUI ``ledScramblePool``).

    Every printable character the set has, its colour tiles 63-69 when it has
    tiles, and its icons; never blank. A character the set carries its own
    bitmap for (``glyphs``, a plugin's ``€``) is in the pool whether or not a
    layout has drawn it yet. Deduplicated and **sorted by glyph key in
    code-point order** (Python's ``str`` order, which is also UTF-8 byte
    order), so it depends on the set's contents alone, never on the order a
    manifest lists them in.
    """
    custom = charset.get("glyphs")
    keys = {glyph_key(BoardToken("char", value=char), custom) for char in charset.get("chars", ())}
    if charset.get("tiles"):
        keys.update(glyph_key(BoardToken("color", code=code)) for code in ("63", "64", "65", "66", "67", "68", "69"))
    keys.update(glyph_key(BoardToken("char", value=" ", icon=name)) for name in charset.get("icons", ()))
    keys.discard(" ")
    return sorted(keys)


def _paint_half_flap(frame: bytearray, layout: LedLayout, cell_index: int, current: LedCell, next_glyph: str) -> None:
    """The top half of ``next_glyph`` over the bottom half of the cell, block field kept lit."""
    grid = layout.grid
    face = LED_FONTS[grid.font]
    gw, gh = face.glyph_width, face.glyph_height
    col = cell_index % grid.cols
    row = cell_index // grid.cols
    x = grid.origin_x + col * (gw + face.spacing_x)
    y = grid.origin_y + row * (gh + face.spacing_y)
    ops: list[LedDrawOp] = []
    if current.background:
        ops.append(LedDrawOp("rect", 0, 0, current.background, w=gw, h=gh))
    draw_glyph(ops, next_glyph, 0, 0, face, current.color, layout.options)
    scratch = bytearray(gw * gh * 3)
    paint_ops(scratch, gw, gh, ops)
    width, height = layout.width, layout.height
    x0, x1 = max(0, x), min(width, x + gw)
    if x1 <= x0:
        return
    for dy in range(math.ceil(gh / 2)):
        py = y + dy
        if py < 0 or py >= height:
            continue
        src = (dy * gw + (x0 - x)) * 3
        dst = (py * width + x0) * 3
        frame[dst : dst + (x1 - x0) * 3] = scratch[src : src + (x1 - x0) * 3]


@dataclass(frozen=True)
class _CellScramble:
    index: int
    delay: int
    #: ``scramble_steps`` glyphs, then the target.
    sequence: tuple[str, ...]


def _plan_flip(
    before: LedLayout, after: LedLayout, spec: _Resolved, from_frame: LedFrame, to_frame: LedFrame
) -> LedTransition:
    changing = [i for i, cell in enumerate(after.cells) if before.cells[i].glyph != cell.glyph]
    if not changing:
        return _settled("flip", after, from_frame, to_frame)

    scramble_steps, stagger = spec.scramble_steps, spec.stagger
    step_ms, half_flap, max_frames = spec.step_ms, spec.half_flap, spec.max_frames
    if max_frames is not None:
        # frames = stagger + scramble + 2: shorten the stagger (the cascade)
        # first, then the scramble (the flip itself).
        stagger = min(stagger, max(0, max_frames - 2 - min(scramble_steps, 1)))
        scramble_steps = max(0, min(scramble_steps, max_frames - 2 - stagger))
    frames = stagger + scramble_steps + 2
    duration_ms = (frames - 1) * step_ms
    pool = scramble_pool(_charset_for_layout(after))
    cols, rows = after.grid.cols, after.grid.rows

    plans: list[_CellScramble] = []
    for index in changing:
        source, target = before.cells[index].glyph, after.cells[index].glyph
        rng = mulberry32(led_flip_seed(index, source, target, cols, rows))
        delay = 0 if stagger == 0 else math.floor(rng() * (stagger + 1))
        sequence: list[str] = []
        previous = source
        for _ in range(scramble_steps):
            # An empty pool draws blank, as FiestaUI's `undefined` glyph does.
            glyph = pool[math.floor(rng() * len(pool))] if pool else " "
            # Never the same glyph twice in a row, and never the target early.
            if glyph in (previous, target) and len(pool) > 2:
                glyph = pool[(pool.index(glyph) + 1 + math.floor(rng() * (len(pool) - 1))) % len(pool)]
            sequence.append(glyph)
            previous = glyph
        sequence.append(target)
        plans.append(_CellScramble(index, delay, tuple(sequence)))

    def glyph_at(plan: _CellScramble, f: int) -> str:
        k = f - plan.delay
        if k <= 0:
            return before.cells[plan.index].glyph
        return plan.sequence[min(k - 1, len(plan.sequence) - 1)]

    layouts: dict[int, LedLayout] = {}

    def layout_at_frame(f: int) -> LedLayout:
        if f <= 0:
            return before
        if f >= frames - 1:
            return after
        if f not in layouts:
            cells = list(before.cells)
            for plan in plans:
                cells[plan.index] = replace(after.cells[plan.index], glyph=glyph_at(plan, f))
            layouts[f] = layout_cells(after.grid, cells, after.options)
        return layouts[f]

    rendered: dict[tuple[int, bool], LedFrame] = {}

    def frame_at_index(f: int, half: bool = False) -> LedFrame:
        if f <= 0 and not half:
            return from_frame
        if f >= frames - 1:
            return to_frame
        key = (max(0, f), half)
        if key not in rendered:
            layout = layout_at_frame(max(0, f))
            pixels = bytearray(rasterize(layout).pixels)
            if half:
                for plan in plans:
                    nxt = glyph_at(plan, f + 1)
                    if nxt != layout.cells[plan.index].glyph:
                        _paint_half_flap(pixels, layout, plan.index, layout.cells[plan.index], nxt)
            rendered[key] = LedFrame(layout.width, layout.height, bytes(pixels))
        return rendered[key]

    def frame_of(t: float) -> int:
        return min(frames - 1, math.floor(t / step_ms))

    def frame_at(t: float) -> LedFrame:
        if t <= 0:
            return from_frame
        if t >= duration_ms:
            return to_frame
        f = frame_of(t)
        return frame_at_index(f, half_flap and t - f * step_ms >= step_ms / 2)

    return LedTransition(
        "flip",
        duration_ms,
        None if half_flap else frames,
        from_frame,
        to_frame,
        frame_at=frame_at,
        frame_at_index=None if half_flap else frame_at_index,
        layout_at=lambda t: before if t <= 0 else layout_at_frame(frame_of(t)),
    )


# --- cascade ----------------------------------------------------------------


def _plan_cascade(
    before: LedLayout, after: LedLayout, requested_ms: int, from_frame: LedFrame, to_frame: LedFrame
) -> LedTransition:
    # Only a changed glyph flips; a colour-only change snaps.
    changed = [i for i, cell in enumerate(after.cells) if before.cells[i].glyph != cell.glyph]
    if not changed or requested_ms == 0:
        return _settled("cascade", after, from_frame, to_frame)
    slot = max(MIN_CASCADE_SLOT_MS, requested_ms / len(changed))
    duration_ms = min(_MAX_DURATION_MS, slot * len(changed))

    def layout_at_slot(n: int) -> LedLayout:
        if n <= 0:
            return before
        if n >= len(changed):
            return after
        cells = list(before.cells)
        for j in range(n):
            cells[changed[j]] = after.cells[changed[j]]
        return layout_cells(after.grid, cells, after.options)

    rendered: dict[int, LedFrame] = {}

    def frame_at(t: float) -> LedFrame:
        if t <= 0:
            return from_frame
        if t >= duration_ms:
            return to_frame
        n = min(len(changed) - 1, math.floor(t / slot))
        if n not in rendered:
            layout = layout_at_slot(n)
            pixels = bytearray(rasterize(layout).pixels)
            i = changed[n]
            current = replace(after.cells[i], glyph=layout.cells[i].glyph)
            _paint_half_flap(pixels, layout, i, current, after.cells[i].glyph)
            rendered[n] = LedFrame(layout.width, layout.height, bytes(pixels))
        return rendered[n]

    return LedTransition(
        "cascade",
        duration_ms,
        None,
        from_frame,
        to_frame,
        frame_at=frame_at,
        frame_at_index=None,
        layout_at=lambda t: layout_at_slot(math.floor(t / slot)),
    )


# --- per-pixel kinds --------------------------------------------------------


def _dissolve_threshold(x: int, y: int) -> float:
    """A fixed pseudo-random order for ``dissolve``, in [0, 1). Same on every device."""
    h = (x * 374761393 + y * 668265263) & _U32
    h = _imul(h ^ (h >> 13), 1274126177)
    return (h ^ (h >> 16)) / 4294967296


def _clamp_byte(value: float) -> int:
    """``Uint8ClampedArray`` assignment: clamp, then round half to even."""
    if value <= 0:
        return 0
    if value >= 255:
        return 255
    return round(value)


def _plan_pixels(
    kind: LedTransitionKind,
    before: LedLayout,
    after: LedLayout,
    duration_ms: int,
    from_frame: LedFrame,
    to_frame: LedFrame,
) -> LedTransition:
    same = (from_frame.width, from_frame.height, from_frame.pixels) == (
        to_frame.width,
        to_frame.height,
        to_frame.pixels,
    )
    if duration_ms == 0 or same:
        return _settled(kind, after, from_frame, to_frame)
    width, height = to_frame.width, to_frame.height
    a, b = from_frame.pixels, to_frame.pixels
    row = width * 3

    def frame_at(t: float) -> LedFrame:
        if t <= 0:
            return from_frame
        if t >= duration_ms:
            return to_frame
        p = t / duration_ms
        px = bytearray(len(b))
        if kind == "slide":
            shift = _js_round(p * height)
            for y in range(height):
                src = y + shift
                px[y * row : (y + 1) * row] = (
                    a[src * row : (src + 1) * row]
                    if src < height
                    else b[(src - height) * row : (src - height + 1) * row]
                )
        elif kind == "wipe":
            edge = math.floor(p * width) * 3
            for y in range(height):
                start = y * row
                px[start : start + edge] = b[start : start + edge]
                px[start + edge : start + row] = a[start + edge : start + row]
        elif kind == "fade":
            for i in range(len(px)):
                px[i] = _clamp_byte(a[i] + (b[i] - a[i]) * p)
        else:
            i = 0
            for y in range(height):
                for x in range(width):
                    src = b if _dissolve_threshold(x, y) < p else a
                    px[i : i + 3] = src[i : i + 3]
                    i += 3
        return LedFrame(width, height, bytes(px))

    return LedTransition(
        kind,
        duration_ms,
        None,
        from_frame,
        to_frame,
        frame_at=frame_at,
        frame_at_index=None,
        layout_at=lambda t: before if t < duration_ms / 2 else after,
    )


def _budgeted(transition: LedTransition, max_frames: int | None) -> LedTransition:
    """Quantise a continuous transition to ``max_frames`` evenly spaced samples, the last settled."""
    if max_frames is None or transition.duration_ms == 0:
        return transition
    frames = max_frames
    duration = transition.duration_ms

    def sample_time(f: int) -> float:
        return duration if f >= frames - 1 else (f * duration) / (frames - 1)

    def frame_of(t: float) -> int:
        # Division last, so a t that is exactly frame f's sample time lands on f.
        return 0 if t <= 0 else min(frames - 1, math.floor((t * (frames - 1)) / duration + 1e-6))

    def frame_at_index(f: int) -> LedFrame:
        if f <= 0:
            return transition.from_frame
        if f >= frames - 1:
            return transition.to_frame
        return transition.frame_at(sample_time(f))

    return replace(
        transition,
        frame_count=frames,
        frame_at=lambda t: frame_at_index(frame_of(t)),
        frame_at_index=frame_at_index,
        layout_at=lambda t: transition.layout_at(sample_time(frame_of(t))),
    )


def plan_transition(
    before: LedLayout,
    after: LedLayout,
    spec: LedTransitionKind | LedTransitionSpec,
    from_frame: LedFrame | None = None,
) -> LedTransition:
    """Plan a transition from one layout to another (FiestaUI ``planLedTransition``).

    Layouts of different pixel sizes snap (``duration_ms`` 0); per-cell kinds
    also snap between different grids. ``spec.max_frames`` is the device frame
    budget. ``from_frame`` is what is on the panel now, when that is not the
    raster of ``before`` (a retargeted transition hands over ``frame_at(t)``
    with ``layout_at(t)``); it must match ``before`` in size.
    """
    resolved = _resolve_spec(spec)
    kind = resolved.kind
    from_frame = from_frame if from_frame is not None else rasterize(before)
    to_frame = rasterize(after)
    if (before.width, before.height) != (after.width, after.height):
        return _settled(kind, after, from_frame, to_frame)
    if kind in ("flip", "cascade"):
        a, b = before.grid, after.grid
        if (a.rows, a.cols, a.font) != (b.rows, b.cols, b.font):
            return _settled(kind, after, from_frame, to_frame)
        if kind == "flip":
            return _plan_flip(before, after, resolved, from_frame, to_frame)
        return _budgeted(_plan_cascade(before, after, resolved.duration_ms, from_frame, to_frame), resolved.max_frames)
    return _budgeted(_plan_pixels(kind, before, after, resolved.duration_ms, from_frame, to_frame), resolved.max_frames)


def transition_frames(transition: LedTransition, fps: float = 30) -> list[LedFrame]:
    """The frame sequence a device receives (FiestaUI ``ledTransitionFrames``).

    A sequenced transition (``frame_count`` set) returns exactly its frames by
    integer index and ignores ``fps``; a continuous one is sampled at ``fps``.
    The last frame is always ``to_frame``.
    """
    if transition.frame_count is not None and transition.frame_at_index is not None:
        if transition.frame_count <= 1:
            return [transition.to_frame]
        frames = [transition.frame_at_index(f) for f in range(transition.frame_count - 1)]
        frames.append(transition.to_frame)
        return frames
    frames = []
    step = 1000 / max(1, fps)
    t: float = 0
    while t < transition.duration_ms:
        frames.append(transition.frame_at(t))
        t += step
    frames.append(transition.to_frame)
    return frames
