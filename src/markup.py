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
- **Icon** ``{icon:sun}`` (or an alias, ``{icon:storm}``): one cell, parsed
  straight to its split-flap fallback (a colour tile, a character, or a
  blank) tagged with ``icon`` and the enclosing span's colours.
  ``{icon:heart}`` is the typed ``♥`` (code 62), not an icon.
- Spans nest (``{red:HOT {63}}``) and close at the brace that balances
  their own, at most :data:`MAX_SPAN_DEPTH` (8) deep: an opener that would
  open a ninth level is literal text, while tiles and icons inside it still
  parse. ``filled`` / ``71`` is a tile only, never a span colour.

Tile tokens keep the spelling they were parsed from (``"63"`` or ``"red"``);
normalising to a numeric code is the caller's job (:attr:`BoardToken.flap_code`).

The parser's flag is off by default, as FiestaUI's ``parseLine`` is: a bare
call is an explicit parse of the base grammar. The app's renderers turn it
on for every board since the split-flap flip
(:data:`src.text_to_board.SPLIT_FLAP_EXTENDED_MARKUP`). With it off,
:func:`parse_line` projects to exactly the codes the legacy
:func:`src.text_to_board.text_to_board_array` drew. In both modes it
matches FiestaUI (d4e3074, PR #335) token for token; see
``tests/test_markup_parity.py``.

The icon registry is FiestaUI's data, vendored as ``markup_icons.json`` by
``scripts/markup_fixtures/generate.sh``, never a hand-kept list here.
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
    "BOARD_ICON_ALIASES",
    "MAX_SPAN_DEPTH",
    "SPAN_COLOR_CODES",
    "BoardIcon",
    "BoardToken",
    "count_tiles",
    "message_to_grid",
    "parse_line",
    "resolve_code62_glyph",
    "resolve_icon_name",
    "rich_tokens_equal",
    "split_rows",
    "take_tiles",
    "tokens_equal",
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


_ICON_REGISTRY = json.loads((Path(__file__).with_name("markup_icons.json")).read_text(encoding="utf-8"))

#: Icon name -> spec, from FiestaUI's published registry.
BOARD_ICONS: dict[str, BoardIcon] = {
    name: BoardIcon(label=spec["label"], color=spec["color"], fallback=spec["fallback"])
    for name, spec in _ICON_REGISTRY["icons"].items()
}
#: Other names an icon answers to (``{icon:storm}`` is ``bolt``). A token
#: carries the canonical name.
BOARD_ICON_ALIASES: dict[str, str] = dict(_ICON_REGISTRY.get("aliases", {}))


#: Plugin ids the template grammar claims (plan D19): ``{{red:HOT}}`` is a
#: span and ``{{icon:sun}}`` an icon, so a plugin with one of these ids could
#: not have its variables addressed. Tile names and codes, colour names, ``icon``.
RESERVED_PLUGIN_IDS: frozenset[str] = frozenset(
    {"red", "orange", "yellow", "green", "blue", "violet", "purple", "white", "black", "filled", "icon"}
    | {str(code) for code in range(63, 72)}
)


def neutralize_data(value: str) -> str:
    """Make a substituted variable value *data*, not markup (plan D19, rule 1).

    A value keeps exactly the base grammar: tile tokens ``{63}``-``{71}``,
    tile names ``{red}``...``{black}`` and ``{filled}``, and base end tags
    ``{/}`` / ``{/<colour name>}`` (art plugins inject tiles through data).
    Every other brace becomes ``(`` or ``)``, so data can never open a span,
    a block or an icon, nor hit a template shortcut. Applied on every output.
    """
    out: list[str] = []
    pos = 0
    while pos < len(value):
        match = COLOR_MARKER_PATTERN.match(value, pos) if value[pos] == "{" else None
        if match:
            out.append(match.group(0))
            pos = match.end()
            continue
        char = value[pos]
        out.append("(" if char == "{" else ")" if char == "}" else char)
        pos += 1
    return "".join(out)


def resolve_icon_name(name: str) -> str | None:
    """The icon a lowercase name or alias means, or ``None``."""
    if name in BOARD_ICONS:
        return name
    return BOARD_ICON_ALIASES.get(name)


#: Colours a span or block head may name (besides ``#rrggbb``), in FiestaUI's
#: ``ALL_COLOR_CODES`` order. ``filled`` / ``71`` is a *tile* (``{filled}``,
#: ``{71}``), not a colour a letter can be drawn in, so a head naming it is
#: literal text, as upstream (FiestaUI 5364439).
SPAN_COLOR_CODES: tuple[str, ...] = (
    "63",
    "64",
    "65",
    "66",
    "67",
    "68",
    "69",
    "70",
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
_TILE_CODES = frozenset(str(code) for code in range(63, 72))
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

# A character keeps its identity in a token: a typed heart stays a heart, so a
# renderer that can draw one (an LED) does. "❤" (U+2764) is normalised to "♥"
# (U+2665) so a heart is one character downstream. Only the flap projection
# collapses it: "♥" and "°" are both code 62, and :func:`message_to_grid` draws
# whichever glyph the board's flap carries. FiestaUI ``typedCharToBoard`` (5364439).
_TYPED_HEARTS = {"❤": "♥"}


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


#: How deep spans may nest (FiestaUI ``MAX_SPAN_DEPTH``, spec §4.1). A span
#: opened at the top level is depth 1; an opener that would open depth 9 is
#: literal text in the depth-8 span (its ``{``, head and ``:`` are characters,
#: and so is its ``}`` when the walk reaches it). Tiles, icons and end tags
#: parse at every depth. The cap bounds the parser's recursion, so a hostile
#: run of openers cannot exhaust the stack. Change it in FiestaUI too.
MAX_SPAN_DEPTH = 8

# The longest span head (``#rrggbb/#rrggbb``) and icon name a marker can
# have; anything longer is never one, so it is not copied out to find that
# out (FiestaUI ``SPAN_HEAD_MAX`` / ``ICON_NAME_MAX``). Tiles and end tags
# keep their exact legacy regex, which is already bounded.
_SPAN_HEAD_MAX = 16
_ICON_NAME_MAX = 16

_BRACE = re.compile(r"[{}]")


def _brace_map(line: str) -> tuple[dict[int, int], dict[int, int]]:
    """Where every ``{`` in *line* leads, found in one pass (FiestaUI ``braceMap``).

    ``close[i]`` is the first ``}`` after the ``{`` at ``i`` (absent when
    there is none) and ``match[i]`` the ``}`` that balances it, counting every
    brace in between (absent when unbalanced). Computed once per parse so no
    opener ever scans forward on its own: a run of openers stays linear.
    """
    close: dict[int, int] = {}
    match: dict[int, int] = {}
    waiting: list[int] = []
    stack: list[int] = []
    for found in _BRACE.finditer(line):
        at = found.start()
        if line[at] == "{":
            waiting.append(at)
            stack.append(at)
            continue
        for opener in waiting:
            close[opener] = at
        waiting.clear()
        if stack:
            match[stack.pop()] = at
    return close, match


def _char_token(value: str, span: _Span | None, icon: str | None = None) -> BoardToken:
    if span is None:
        return BoardToken("char", value=value, icon=icon)
    return BoardToken("char", value=value, color=span.color, background=span.background, icon=icon)


def _icon_token(name: str, span: _Span | None) -> BoardToken:
    """An icon's split-flap fallback, tagged with the icon and the span's colours."""
    fallback = BOARD_ICONS[name].fallback
    if fallback is not None and fallback in _TILE_CODES:
        token = BoardToken("color", code=fallback, icon=name)
    else:
        token = BoardToken("char", value=fallback if fallback is not None else " ", icon=name)
    if span is None:
        return token
    return replace(token, color=span.color, background=span.background)


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

    # A line with no brace has no markers; skip the brace map for it.
    close_of, match_of = _brace_map(line) if "{" in line else ({}, {})

    def walk(start: int, end: int, span: _Span | None, heads: tuple[str, ...], root: int | None, depth: int) -> None:
        """Parse ``line[start:end)`` inside *span*, at span nesting *depth*.

        Spans recurse into their own body, at most :data:`MAX_SPAN_DEPTH`
        levels; everything else is one forward pass over the line itself,
        never a copy of it.
        """
        i = start
        while i < end and not full():
            if line[i] == "{":
                # The legacy markers come first and keep their exact regex, so
                # every message the board draws today parses the same way.
                match = COLOR_MARKER_PATTERN.match(line, i, end)
                if match:
                    token = None
                    if match.group(1):
                        token = BoardToken("color", code=match.group(1))
                    elif match.group(2) and COLOR_CODES.get(match.group(2).lower()):
                        token = BoardToken("color", code=match.group(2).lower())
                    add(token, match.group(0), heads, i, root)
                    i = match.end()
                    continue
                after = extended_marker(i, end, span, heads, root, depth) if extended_markup else -1
                if after != -1:
                    i = after
                    continue
            char = line[i]
            value = _TYPED_HEARTS.get(char) or (char if preserve_case else char.upper())
            add(_char_token(value, span), char, heads, i, root)
            i += 1

    def extended_marker(
        i: int, end: int, span: _Span | None, heads: tuple[str, ...], root: int | None, depth: int
    ) -> int:
        """Parse an icon or span at ``line[i]``; the index after it, or -1 if it is not one."""
        close = close_of.get(i, -1)
        if close == -1 or close >= end:
            return -1
        # A valid head is at most _SPAN_HEAD_MAX long, so the colon is only
        # looked for that far: a later one makes the marker literal anyway.
        colon = line.find(":", i + 1, min(close, i + 2 + _SPAN_HEAD_MAX))
        if colon <= i + 1:
            return -1
        head = line[i + 1 : colon]
        if head.lower() == "icon":
            if close - colon - 1 > _ICON_NAME_MAX:
                return -1
            raw = line[colon + 1 : close].lower()
            # `{icon:heart}` is not an icon but the typed ♥ (code 62).
            if raw == "heart":
                add(_char_token("♥", span), line[i : close + 1], heads, i, root)
                return close + 1
            name = resolve_icon_name(raw)
            if name is None:
                return -1
            add(_icon_token(name, span), line[i : close + 1], heads, i, root)
            return close + 1
        # Past the depth cap an opener is literal text: it falls through with
        # its head, its colon and, when the walk reaches it, its closing
        # brace. Tiles and icons inside it still parse.
        if depth >= MAX_SPAN_DEPTH:
            return -1
        opened = _span_head(head)
        # The first "}" may close a tile inside the span; the span itself ends
        # at the brace that balances its own "{" (always inside *end*: every
        # brace between a span's own pair is balanced).
        span_end = match_of.get(i, -1) if opened else -1
        if span_end == -1:
            return -1
        walk(colon + 1, span_end, opened, (*heads, head), i if root is None else root, depth + 1)
        return span_end + 1

    walk(0, len(line), None, (), None, 0)
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
    padded with blanks. Code 62 is drawn as the glyph this board's flap
    carries, in both directions: a ``°`` draws as ``♥`` on a heart board and a
    typed ``♥`` as ``°`` on a degree board (display only: both are code 62).
    """
    lines = message.split("\n")
    glyph = resolve_code62_glyph(device_type, code62_glyph)
    grid: list[list[BoardToken]] = []
    for row in range(rows):
        line = lines[row] if row < len(lines) else ""
        tokens = parse_line(line, cols, extended_markup=extended_markup, preserve_case=preserve_case)
        tokens = [_apply_code62_glyph(t, glyph) for t in tokens]
        grid.append(tokens + [_BLANK] * (cols - len(tokens)))
    return grid


def _apply_code62_glyph(token: BoardToken, glyph: str) -> BoardToken:
    """Draw code 62 as the board's flap (FiestaUI ``applyCode62Glyph``)."""
    if token.type != "char":
        return token
    if glyph == "heart" and token.value == "°":
        return replace(token, value="♥")
    if glyph == "degree" and token.value == "♥":
        return replace(token, value="°")
    return token


def tokens_to_codes(tokens: list[BoardToken]) -> list[int]:
    """Project tokens to the 0–71 codes a split-flap board draws."""
    return [t.flap_code for t in tokens]


def tokens_equal(a: BoardToken, b: BoardToken) -> bool:
    """Whether a split-flap tile would change (FiestaUI ``tokensEqual``).

    Compares only what a flap draws: ``type`` and ``value`` / ``code``, as
    spelled (``"63"`` and ``"red"`` differ). Colour and icon are ignored.
    """
    if a.type != b.type:
        return False
    return a.value == b.value if a.type == "char" else a.code == b.code


def rich_tokens_equal(a: BoardToken, b: BoardToken) -> bool:
    """Colour-aware equality for renderers that draw colour (FiestaUI ``richTokensEqual``).

    :func:`tokens_equal` plus ``color``, ``background`` and ``icon``. An LED
    dedupe needs this: a span recoloured from red to blue is the same flap
    but a different frame.
    """
    return tokens_equal(a, b) and a.color == b.color and a.background == b.background and a.icon == b.icon


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


def _split_index(pieces: list[_Piece], limit: int, start: int = 0) -> int | None:
    """Index of the first piece from *start* that would take the run past *limit* tiles."""
    tiles = 0
    for index in range(start, len(pieces)):
        cost = 0 if pieces[index].token is None else 1
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


def split_rows(text: str) -> list[str]:
    """Split multi-row *text* at each ``\\n`` under the extended grammar.

    The row-break twin of :func:`take_tiles`: a span (or block) that crosses
    a newline — a row-emitting formula such as ``FOREACH`` inside
    ``{{red:...}}`` — is closed at the end of one row and reopened, with
    every enclosing span, at the start of the next. Text with no span
    crossing a newline is split exactly as ``text.split("\\n")``; so is a
    break between a span's literal braces, which no markup can re-express.
    """
    pieces = _pieces(text, extended_markup=True)
    if not any(p.source == "\n" and p.heads for p in pieces):
        return text.split("\n")
    rows: list[list[_Piece]] = [[]]
    for piece in pieces:
        if piece.source == "\n":
            rows.append([])
        else:
            rows[-1].append(piece)
    if not all(_round_trips(row) for row in rows):
        return text.split("\n")
    return [_serialize(row) for row in rows]


def _is_space(piece: _Piece) -> bool:
    token = piece.token
    return token is not None and token.type == "char" and token.icon is None and piece.source.isspace()


def wrap_line(line: str, cols: int, *, first_cols: int | None = None) -> list[str]:
    """Greedy word-wrap one line to *cols* tiles under the extended grammar.

    The rules are :meth:`MessageFormatter._wrap_line`'s — words split on
    whitespace and rejoin with one space, a word wider than the board is
    hard-broken — but measured in drawn tiles, with whitespace *inside* a
    span splitting words too. Every row is re-serialized so a span that
    crosses rows is closed on one and reopened on the next; a space joining
    two words keeps the colours of the space it replaces.

    ``first_cols`` narrows the first row only (a template's ``|wrap`` value
    shares its first row with the text around it); later rows get *cols*.
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

    first = cols if first_cols is None else first_cols
    rows: list[list[_Piece]] = []

    def width() -> int:
        return cols if rows else first

    current: list[_Piece] = []
    current_tiles = 0
    for sep, word in words:
        word_tiles = _tiles(word)
        if current and current_tiles + 1 + word_tiles <= width():
            space = sep.token if sep is not None and sep.token is not None else _BLANK
            joiner = _Piece(replace(space, value=" "), " ", sep.heads if sep else (), -1, -1)
            current = [*current, joiner, *word]
            current_tiles += 1 + word_tiles
            continue
        if current:
            rows.append(current)
            current, current_tiles = [], 0
        # Hard-break a word wider than the board, walking it once: each row
        # starts where the last one ended, never at a re-sliced copy.
        cut = 0
        while word_tiles > width():
            index = _split_index(word, width(), cut)
            if not index or index == cut:  # defensive: never loop forever on a 0-wide board
                break
            row = word[cut:index]
            rows.append(row)
            word_tiles -= _tiles(row)
            cut = index
        word = word[cut:]
        if word:
            current, current_tiles = word, word_tiles
    if current:
        rows.append(current)

    if not all(_round_trips(row) for row in rows):
        # Literal braces inside a span that a row boundary would cut: no
        # markup expresses that, so wrap the raw text the legacy way.
        return MessageFormatter(cols=min(cols, first))._wrap_line(line)
    return [_serialize(row) for row in rows]
