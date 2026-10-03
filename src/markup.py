"""Board message markup: one parser, a rich token model, and FiestaUI parity.

A board message is a markup string. Today's grammar (the *legacy* grammar,
always on) has two markers besides plain text:

- **Colour tiles** ``{63}`` … ``{71}`` and ``{red}``, ``{purple}``,
  ``{filled}`` …: one solid tile each.
- **End tags** ``{/}`` and ``{/red}``: formatting artefacts, zero tiles.

Everything else is literal text; the board draws characters it has no flap
for (braces included) as blanks.

``extended_markup=True`` adds the grammar FiestaUI's ``parseLine`` speaks
behind its own ``extendedMarkup`` flag (``src/lib/board-characters.ts`` in
FiestaUI, the reference implementation):

- **Colour span** ``{red:HOT}``, ``{63:HOT}``, ``{#ff8800:HOT}``: the letters
  carry ``color``. A split-flap board draws them plain.
- **Block span** ``{black/white:OPEN}``: ``fg/bg``; the letters carry
  ``color`` and ``background``.
- **Icon** ``{icon:sun}``: one cell, parsed straight to its split-flap
  fallback (a colour tile, a character, or a blank) tagged with ``icon``.
- Spans nest (``{red:HOT {63}}``) and close at the brace that balances
  their own.

The flag is off by default and nothing in the app turns it on yet. With it
off, :func:`parse_line` projects to exactly the codes
:func:`src.text_to_board.text_to_board_array` draws today. With it on, it
matches FiestaUI token for token, except where FiestaUI's *legacy* grammar
disagrees with what the board draws today (``{filled}``, ``{/foo}``); there
the board wins. ``tests/test_markup_parity.py`` lists each such case.

The icon table is FiestaUI's data, vendored as ``markup_icons.json`` by
``scripts/markup_fixtures/generate.sh`` — never a hand-kept list here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from .board_chars import BoardChars
from .text_to_board import COLOR_CODES, COLOR_MARKER_PATTERN

__all__ = [
    "BOARD_ICONS",
    "SPAN_COLOR_CODES",
    "BoardIcon",
    "BoardToken",
    "count_tiles",
    "message_to_grid",
    "parse_line",
    "resolve_code62_glyph",
    "take_tiles",
    "tokens_to_codes",
    "wrap_line",
]


@dataclass(frozen=True)
class BoardIcon:
    """One ``{icon:NAME}`` entry: what an LED draws and what a flap falls back to."""

    label: str
    color: str
    #: A colour-tile code (``"63"``…), one board character, or ``None`` for a blank.
    fallback: str | None


def _load_icons() -> dict[str, BoardIcon]:
    data = json.loads((Path(__file__).with_name("markup_icons.json")).read_text(encoding="utf-8"))
    return {
        name: BoardIcon(label=spec["label"], color=spec["color"], fallback=spec["fallback"])
        for name, spec in data["icons"].items()
    }


BOARD_ICONS: dict[str, BoardIcon] = _load_icons()

#: Colours a span head may name, in FiestaUI's ``ALL_COLOR_CODES`` order.
#: Note ``filled`` is a *tile* (``{filled}``) but not a span colour, as upstream.
SPAN_COLOR_CODES: tuple[str, ...] = (
    "63",
    "64",
    "65",
    "66",
    "67",
    "68",
    "69",
    "70",
    "71",
    "red",
    "orange",
    "yellow",
    "green",
    "blue",
    "violet",
    "purple",
    "white",
    "black",
)
_SPAN_COLORS = frozenset(SPAN_COLOR_CODES)
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


@dataclass(frozen=True)
class BoardToken:
    """One board cell, the Python twin of FiestaUI's ``BoardToken``.

    ``type == "char"`` carries ``value`` (the character as drawn);
    ``type == "color"`` carries ``code`` (the tile marker as written: ``"63"``
    or a lowercase name). ``color`` / ``background`` / ``icon`` are what a
    split-flap board cannot draw and ignores; an LED matrix reads them.
    """

    type: Literal["char", "color"]
    value: str = ""
    code: str = ""
    color: str | None = None
    background: str | None = None
    icon: str | None = None

    def to_dict(self) -> dict:
        """The token in FiestaUI's JSON shape (absent fields omitted)."""
        out: dict = {"type": self.type}
        if self.type == "char":
            out["value"] = self.value
        else:
            out["code"] = self.code
        if self.color is not None:
            out["color"] = self.color
        if self.background is not None:
            out["background"] = self.background
        if self.icon is not None:
            out["icon"] = self.icon
        return out

    @property
    def flap_code(self) -> int:
        """The 0–71 code a split-flap board draws for this cell."""
        if self.type == "color":
            return int(self.code) if self.code.isdigit() else COLOR_CODES[self.code]
        # Uppercasing can widen a character ("ß" -> "SS"); no flap carries that.
        if len(self.value) != 1:
            return BoardChars.SPACE
        code = BoardChars.get_char_code(self.value)
        return BoardChars.SPACE if code is None else code


_BLANK = BoardToken("char", value=" ")


@dataclass(frozen=True)
class _Span:
    color: str
    background: str | None = None


@dataclass(frozen=True)
class _Piece:
    """A token plus the markup it came from, so text can be re-split safely.

    ``token`` is ``None`` for markup that draws nothing (end tags). ``heads``
    are the raw heads of the enclosing spans, outermost first; ``root`` is the
    offset of the top-level atom the piece belongs to, a cut that is always
    safe.
    """

    token: BoardToken | None
    source: str
    heads: tuple[str, ...]
    start: int
    root: int


def _span_color(head: str) -> str | None:
    if head in _SPAN_COLORS:
        return head
    lower = head.lower()
    if lower in _SPAN_COLORS:
        return lower
    return lower if _HEX_COLOR.fullmatch(head) else None


def _span_head(head: str) -> _Span | None:
    if "/" not in head:
        color = _span_color(head)
        return _Span(color) if color else None
    fg, _, bg = head.partition("/")
    color, background = _span_color(fg), _span_color(bg)
    return _Span(color, background) if color and background else None


def _matching_brace(text: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _char_token(value: str, span: _Span | None, icon: str | None = None) -> BoardToken:
    if span is None:
        return BoardToken("char", value=value, icon=icon)
    return BoardToken("char", value=value, color=span.color, background=span.background, icon=icon)


def _icon_token(name: str, span: _Span | None) -> BoardToken:
    fallback = BOARD_ICONS[name].fallback
    if fallback is not None and fallback in _SPAN_COLORS:
        return BoardToken("color", code=fallback, icon=name)
    return _char_token(fallback if fallback is not None else " ", span, icon=name)


def _pieces(
    line: str,
    *,
    extended_markup: bool,
    preserve_case: bool = False,
    max_tokens: int | None = None,
) -> list[_Piece]:
    pieces: list[_Piece] = []
    drawn = 0

    def full() -> bool:
        return max_tokens is not None and drawn >= max_tokens

    def add(token: BoardToken | None, source: str, heads: tuple[str, ...], start: int, root: int | None) -> None:
        nonlocal drawn
        pieces.append(_Piece(token, source, heads, start, start if root is None else root))
        if token is not None:
            drawn += 1

    def walk(text: str, offset: int, span: _Span | None, heads: tuple[str, ...], root: int | None) -> None:
        i = 0
        while i < len(text) and not full():
            if text[i] == "{":
                # The legacy markers come first and keep their exact regex, so
                # every message the board draws today parses the same way.
                match = COLOR_MARKER_PATTERN.match(text, i)
                if match:
                    token = None
                    if match.group(1):
                        token = BoardToken("color", code=match.group(1))
                    elif match.group(2) and COLOR_CODES.get(match.group(2).lower()):
                        token = BoardToken("color", code=match.group(2).lower())
                    add(token, match.group(0), heads, offset + i, root)
                    i = match.end()
                    continue
                after = extended_marker(text, i, offset, span, heads, root) if extended_markup else -1
                if after != -1:
                    i = after
                    continue
            char = text[i]
            add(_char_token(char if preserve_case else char.upper(), span), char, heads, offset + i, root)
            i += 1

    def extended_marker(
        text: str, i: int, offset: int, span: _Span | None, heads: tuple[str, ...], root: int | None
    ) -> int:
        """Parse an icon or span at ``text[i]``; the index after it, or -1 if it is not one."""
        close = text.find("}", i)
        if close == -1:
            return -1
        content = text[i + 1 : close]
        colon = content.find(":")
        if colon <= 0:
            return -1
        head = content[:colon]
        if head.lower() == "icon":
            name = content[colon + 1 :].lower()
            if name not in BOARD_ICONS:
                return -1
            add(_icon_token(name, span), text[i : close + 1], heads, offset + i, root)
            return close + 1
        opened = _span_head(head)
        # The first "}" may close a tile inside the span; the span itself ends
        # at the brace that balances its own "{".
        end = _matching_brace(text, i) if opened else -1
        if end == -1:
            return -1
        inner_start = i + 1 + len(head) + 1
        walk(text[inner_start:end], offset + inner_start, opened, (*heads, head), offset + i if root is None else root)
        return end + 1

    walk(line, 0, None, (), None)
    return pieces


def parse_line(
    line: str,
    max_tokens: int | None = None,
    *,
    extended_markup: bool = False,
    preserve_case: bool = False,
) -> list[BoardToken]:
    """Parse one line into board tokens (FiestaUI ``parseLine``).

    Args:
        line: One line of a message (no ``\\n``).
        max_tokens: Stop after this many tokens (``None`` = no limit).
        extended_markup: Parse colour spans, block spans and icons. Off by
            default: the new markers are then literal text, as the board
            draws them today.
        preserve_case: Keep the letters' case (for LED matrices with
            lowercase glyphs). The board's own charset is uppercase only.
    """
    pieces = _pieces(line, extended_markup=extended_markup, preserve_case=preserve_case, max_tokens=max_tokens)
    return [p.token for p in pieces if p.token is not None]


def resolve_code62_glyph(device_type: str, code62_glyph: str | None = None) -> str:
    """Which glyph a board's code-62 flap carries (FiestaUI ``resolveCode62Glyph``)."""
    if device_type in ("note", "note_array", "panel"):
        return "heart"
    return code62_glyph or "degree"


def message_to_grid(
    message: str,
    rows: int,
    cols: int,
    *,
    device_type: str = "flagship",
    code62_glyph: str | None = None,
    extended_markup: bool = False,
    preserve_case: bool = False,
) -> list[list[BoardToken]]:
    """A ``rows x cols`` grid of tokens (FiestaUI ``messageToGrid``).

    Lines past ``rows`` and cells past ``cols`` are dropped; short rows are
    padded with blanks. Code 62 is drawn as the glyph this board carries
    (display only: both glyphs project to code 62).
    """
    lines = message.split("\n")
    heart = resolve_code62_glyph(device_type, code62_glyph) == "heart"
    grid: list[list[BoardToken]] = []
    for row in range(rows):
        line = lines[row] if row < len(lines) else ""
        tokens = parse_line(line, cols, extended_markup=extended_markup, preserve_case=preserve_case)
        if heart:
            tokens = [replace(t, value="♥") if t.type == "char" and t.value == "°" else t for t in tokens]
        grid.append(tokens + [_BLANK] * (cols - len(tokens)))
    return grid


def tokens_to_codes(tokens: list[BoardToken]) -> list[int]:
    """Project tokens to the 0–71 codes a split-flap board draws."""
    return [t.flap_code for t in tokens]


# --- measuring and splitting extended markup by drawn tiles -------------------


def _tiles(pieces: list[_Piece]) -> int:
    return sum(1 for p in pieces if p.token is not None)


def _serialize(pieces: list[_Piece]) -> str:
    """Markup for *pieces*, closing and reopening spans where they change."""
    out: list[str] = []
    open_heads: tuple[str, ...] = ()
    for piece in pieces:
        common = 0
        while common < min(len(open_heads), len(piece.heads)) and open_heads[common] == piece.heads[common]:
            common += 1
        out.append("}" * (len(open_heads) - common))
        out.extend("{" + head + ":" for head in piece.heads[common:])
        open_heads = piece.heads
        out.append(piece.source)
    out.append("}" * len(open_heads))
    return "".join(out)


def _round_trips(pieces: list[_Piece]) -> bool:
    """Whether :func:`_serialize` re-parses to these pieces' tokens.

    It always does unless a span contains literal braces (``{red:A{foo}B}``)
    and the cut separates them — then no markup can express the half.
    """
    return parse_line(_serialize(pieces), extended_markup=True) == [p.token for p in pieces if p.token is not None]


def _split_index(pieces: list[_Piece], limit: int) -> int | None:
    """Index of the first piece that would take the run past *limit* tiles."""
    tiles = 0
    for index, piece in enumerate(pieces):
        cost = 0 if piece.token is None else 1
        if tiles + cost > limit:
            return index
        tiles += cost
    return None


def count_tiles(text: str) -> int:
    """Tiles *text* draws under the extended grammar (a span counts its cells)."""
    return _tiles(_pieces(text, extended_markup=True))


def take_tiles(text: str, limit: int) -> tuple[str, str]:
    """Split *text* into ``(head, tail)``, ``head`` at most *limit* tiles wide.

    Extended-grammar twin of :func:`src.text_to_board.take_tiles`: tiles,
    icons and end tags are never cut, and a span cut in two is closed in
    ``head`` and reopened (with every enclosing span) in ``tail``. A cut
    between top-level atoms returns the source verbatim.
    """
    if limit <= 0:
        return "", text
    pieces = _pieces(text, extended_markup=True)
    index = _split_index(pieces, limit)
    if index is None:
        return text, ""
    cut = pieces[index]
    if not cut.heads:
        return text[: cut.start], text[cut.start :]
    head, tail = pieces[:index], pieces[index:]
    if _round_trips(head) and _round_trips(tail):
        return _serialize(head), _serialize(tail)
    # Unexpressible cut: keep the whole top-level span for the tail.
    return text[: cut.root], text[cut.root :]


def _is_space(piece: _Piece) -> bool:
    token = piece.token
    return token is not None and token.type == "char" and token.icon is None and piece.source.isspace()


def wrap_line(line: str, cols: int) -> list[str]:
    """Greedy word-wrap one line to *cols* tiles under the extended grammar.

    The rules are :meth:`MessageFormatter._wrap_line`'s — words split on
    whitespace and rejoin with one space, a word wider than the board is
    hard-broken — but measured in drawn tiles, with whitespace *inside* a
    span splitting words too. Every row is re-serialized so a span that
    crosses rows is closed on one and reopened on the next; a space joining
    two words keeps the colours of the space it replaces.
    """
    from .formatters.message_formatter import MessageFormatter

    pieces = _pieces(line, extended_markup=True)
    words: list[tuple[_Piece | None, list[_Piece]]] = []
    word: list[_Piece] = []
    word_sep: _Piece | None = None
    next_sep: _Piece | None = None
    for piece in pieces:
        if _is_space(piece):
            if word:
                words.append((word_sep, word))
                word = []
            if next_sep is None:
                next_sep = piece
            continue
        if not word:
            word_sep, next_sep = next_sep, None
        word.append(piece)
    if word:
        words.append((word_sep, word))
    if not words:
        return [""]

    rows: list[list[_Piece]] = []
    current: list[_Piece] = []
    current_tiles = 0
    for sep, word in words:
        word_tiles = _tiles(word)
        if current and current_tiles + 1 + word_tiles <= cols:
            space = sep.token if sep is not None and sep.token is not None else _BLANK
            joiner = _Piece(replace(space, value=" "), " ", sep.heads if sep else (), -1, -1)
            current = [*current, joiner, *word]
            current_tiles += 1 + word_tiles
            continue
        if current:
            rows.append(current)
            current, current_tiles = [], 0
        while word_tiles > cols:
            index = _split_index(word, cols)
            if not index:  # defensive: never loop forever on a 0-wide board
                break
            rows.append(word[:index])
            word = word[index:]
            word_tiles = _tiles(word)
        if word:
            current, current_tiles = word, word_tiles
    if current:
        rows.append(current)

    if not all(_round_trips(row) for row in rows):
        # Literal braces inside a span that a row boundary would cut: no
        # markup expresses that, so wrap the raw text the legacy way.
        return MessageFormatter(cols=cols)._wrap_line(line)
    return [_serialize(row) for row in rows]
