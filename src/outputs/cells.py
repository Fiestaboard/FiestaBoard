"""Rich cells: a board message parsed once, projected per output (plan D15/D17).

The **markup string** stays canonical upstream: templates, pages, the v1 and
MQTT message APIs, the engine's content dedupe and its render memo all key
on it. What a board is *sent* is projected from it per output, by the
board's resolved character set:

- **Split-flap** (a Vestaboard set, a FiestaPanel, no set at all): the 0–71
  grid from :func:`src.text_to_board.text_to_board_array`, which since the
  split-flap flip (plan Task 12, :data:`~src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`)
  parses extended markup and draws its degradation: a span's letters, an
  icon's fallback tile. No rich cells: the board cannot draw more.
- **A rich set** (one with colour spans, block spans or icons — the LED
  sets): the message is parsed ONCE with extended markup and case kept.
  From that one parse come both the 0–71 flap projection (what transitions,
  the last-frame store's ``characters`` and every int-grid consumer read)
  and the :data:`RichCellFrame`: each token passed through the set's
  :func:`~src.led.charsets.charset_fallback`, with colour tiles normalised
  to their numeric code (``{red}`` → ``"63"``, plan D17 answer 6).

A :data:`RichCellFrame` is FiestaUI's ``BoardToken[][]``: per cell a
character (one code point), a colour tile (numeric code) or an icon (its
canonical name), plus ``color`` / ``background``. Its JSON shape is
:func:`cells_to_json`.

**Layers.** A projected frame is a :class:`RichCells`: still a plain list of
rows (every plugin written before canvases keeps working), with a
``.layers`` attribute — the page's pixel canvases rasterised for the board
(``src.canvas.CanvasLayer``s, ``(x, y, w, h, rgba)``; empty on most frames).
An LED output plugin draws them with
``layout_message(frame, spec, options, layers=getattr(frame, "layers", ()))``.
Frame equality (:func:`cells_equal`, so the dedupe) includes them. Only a
pixel-matrix board's render produces any, and only a rich output gets cells,
so a split-flap output never sees a layer.

Nothing is cached across renders: a set's lookups are built once per
projection, so a set whose content changes (a new ``version``) can never
be served a stale projection.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, NamedTuple

from src.board_chars import characters_to_message
from src.led.charsets import CharacterSet, CharsetLookup, charset_fallback, has_extended_markup
from src.markup import BoardToken, parse_line, rich_tokens_equal
from src.text_to_board import COLOR_CODES, SPLIT_FLAP_EXTENDED_MARKUP, text_to_board_array

__all__ = [
    "ProjectedFrame",
    "RichCellFrame",
    "RichCells",
    "cells_equal",
    "cells_from_codes",
    "cells_to_json",
    "charset_extended_markup",
    "extended_markup_kw",
    "frame_layers",
    "output_character_set",
    "output_extended_markup",
    "project_for_output",
    "project_message",
]

#: One rich frame: rows of FiestaUI ``BoardToken``s, board-shaped. A
#: projected frame is a :class:`RichCells` (this, plus ``.layers``).
RichCellFrame = list[list[BoardToken]]


class RichCells(list):
    """A rich frame (rows of ``BoardToken``s) that also carries its bitmap ``layers``.

    A ``list`` subclass so it is a :data:`RichCellFrame` wherever one is
    expected: indexing, iteration, ``==`` against a plain list (cells only)
    and :func:`cells_to_json` are unchanged. ``layers`` is a tuple of
    ``src.canvas.CanvasLayer`` (``x``, ``y``, ``w``, ``h``, ``rgba``), drawn
    over the cells in order; ``()`` when the frame has none. Use
    :func:`cells_equal` to compare frames including their layers.
    """

    __slots__ = ("layers",)

    def __init__(self, rows=(), layers=()) -> None:
        super().__init__(rows)
        self.layers: tuple = tuple(layers)

    def __repr__(self) -> str:
        return f"RichCells({list.__repr__(self)}, layers={len(self.layers)})"

    def __copy__(self) -> RichCells:
        return RichCells(self, self.layers)

    def __reduce__(self):
        return (RichCells, (list(self), self.layers))


def frame_layers(cells: object) -> tuple:
    """The bitmap layers a rich frame carries (``()`` for a plain list or ``None``)."""
    return tuple(getattr(cells, "layers", ()) or ())


_BLANK = BoardToken("char", value=" ")


class ProjectedFrame(NamedTuple):
    """One message, projected for one output."""

    #: The 0–71 grid (the split-flap projection every output has).
    characters: list[list[int]]
    #: The rich cells, for an output whose set is rich; else ``None``.
    cells: RichCellFrame | None


def output_character_set(client: Any) -> CharacterSet | None:
    """The resolved character set a board's driver draws with, when it says.

    Output-plugin drivers carry the set their board resolved to; the
    built-in drivers (and test doubles) carry none, which reads as split-flap.
    """
    charset = getattr(client, "character_set", None)
    return charset if isinstance(charset, Mapping) else None


def charset_extended_markup(charset: str | CharacterSet | None) -> bool:
    """Whether a board drawing with *charset* speaks extended markup (plan
    D19, Task 12): a rich set always does; a split-flap set (or none) does
    while :data:`~src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP` is on.

    Not the same question as :func:`~src.led.charsets.has_extended_markup`,
    which asks whether the set is *rich* (so the board gets rich cells)."""
    return SPLIT_FLAP_EXTENDED_MARKUP or has_extended_markup(charset)


def output_extended_markup(client: Any) -> bool:
    """Whether the board behind *client* speaks extended markup
    (:func:`charset_extended_markup` of its resolved set)."""
    return charset_extended_markup(output_character_set(client))


def extended_markup_kw(client: Any) -> dict[str, Any]:
    """The page/template render keywords for the board behind *client*.

    A rich set gets ``{"extended_markup": True}``. Any other board gets no
    keyword: the renderers' default *is* the split-flap mode
    (:data:`~src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`), so a split-flap
    board's render call keeps the shape it always had."""
    return {"extended_markup": True} if has_extended_markup(output_character_set(client)) else {}


def project_for_output(
    client: Any,
    message: str,
    rows: int,
    cols: int,
    *,
    flap: Callable[..., list[list[int]]] | None = None,
    layers: Sequence[Any] = (),
) -> tuple[list[list[int]], dict[str, Any]]:
    """*message* projected for the board behind *client*: the 0–71 grid and
    the send keywords that carry its rich cells (``{"cells": ...}``, or
    nothing for a split-flap board).

    A split-flap board's grid comes from *flap* — the caller's own
    ``text_to_board_array`` (a module-level name tests patch), by default
    :func:`~src.text_to_board.text_to_board_array`, whose default is the
    split-flap mode (:data:`~src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`),
    so the call shape a patched seam sees is the one it always was.

    *layers* (a pixel-matrix render's canvases) ride on the rich cells; a
    split-flap board gets none.
    """
    charset = output_character_set(client)
    if not has_extended_markup(charset):
        return (flap or text_to_board_array)(message, rows=rows, cols=cols), {}
    frame = project_message(message, rows, cols, charset, layers=layers)
    return frame.characters, {"cells": frame.cells}


def _numeric_tile(token: BoardToken) -> BoardToken:
    if token.type == "color" and not token.code.isdigit():
        return replace(token, code=str(COLOR_CODES[token.code]))
    return token


def project_message(
    message: str, rows: int, cols: int, charset: CharacterSet | None, *, layers: Sequence[Any] = ()
) -> ProjectedFrame:
    """*message* as a ``rows`` x ``cols`` board drawn with *charset*.

    A set that is not rich (or none) gets the split-flap grid (parsed with
    :func:`charset_extended_markup`) and no cells. A rich set gets one
    extended-markup parse, projected twice (see module docstring), and its
    cells carry *layers* (:class:`RichCells`).
    """
    if not has_extended_markup(charset):
        grid = text_to_board_array(message, rows=rows, cols=cols, extended_markup=charset_extended_markup(charset))
        return ProjectedFrame(grid, None)
    look = CharsetLookup(charset)
    lines = message.split("\n")
    characters: list[list[int]] = []
    cells = RichCells(layers=layers)
    for row in range(rows):
        line = lines[row] if row < len(lines) else ""
        tokens = parse_line(line, cols, extended_markup=True, preserve_case=True)
        tokens = tokens + [_BLANK] * (cols - len(tokens))
        characters.append([t.flap_code for t in tokens])
        cells.append([_numeric_tile(charset_fallback(look, t)) for t in tokens])
    return ProjectedFrame(characters, cells)


def cells_equal(a: RichCellFrame | None, b: RichCellFrame | None) -> bool:
    """Colour-aware frame equality (FiestaUI ``richTokensEqual`` per cell),
    bitmap layers included (:func:`frame_layers`).

    Two missing frames are equal; a missing and a present one are not.
    """
    if a is None or b is None:
        return a is b
    if len(a) != len(b) or frame_layers(a) != frame_layers(b):
        return False
    for row_a, row_b in zip(a, b, strict=True):
        if len(row_a) != len(row_b) or not all(rich_tokens_equal(x, y) for x, y in zip(row_a, row_b, strict=True)):
            return False
    return True


def cells_to_json(cells: RichCellFrame) -> list[list[dict]]:
    """FiestaUI's ``BoardToken[][]`` JSON shape (absent fields omitted)."""
    return [[t.to_dict() for t in row] for row in cells]


def _code_cell(code: int) -> BoardToken:
    if 63 <= code <= 71:
        return BoardToken("color", code=str(code))
    text = characters_to_message([[code]]) if 0 <= code <= 62 else " "
    return BoardToken("char", value=text if len(text) == 1 else " ")


def cells_from_codes(characters: list[list[int]]) -> RichCellFrame:
    """A 0–71 grid as rich cells: a code 63–71 is that colour tile, any
    other its character (an unknown code is a blank). What a frame that
    only ever was codes (a blank board, a read-back) looks like as cells."""
    return [[_code_cell(int(code)) for code in row] for row in characters]
