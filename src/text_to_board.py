"""Convert formatted text strings to board character arrays.

This module handles conversion of text (with color markers) into the 6x22
character code arrays that the board requires.
"""

import logging
import re

from .board_chars import BoardChars

logger = logging.getLogger(__name__)

# Color name to code mapping
COLOR_CODES = {
    "red": 63,
    "orange": 64,
    "yellow": 65,
    "green": 66,
    "blue": 67,
    "violet": 68,
    "purple": 68,
    "white": 69,
    "black": 70,
    "filled": 71,
}

# Parse color markers: {63}, {red}, {/red}, {/} - each produces a single colored tile
# Note: Single brackets are used after template normalization to avoid conflicting with {{variable}} syntax
COLOR_MARKER_PATTERN = re.compile(
    r"\{(?:"
    r"(6[3-9]|7[01])|"  # Numeric codes 63-71
    r"(red|orange|yellow|green|blue|violet|purple|white|black|filled)|"  # Named colors
    r"(/(?:red|orange|yellow|green|blue|violet|purple|white|black|filled)?)"  # End tags {/} or {/red}
    r")\}",
    re.IGNORECASE,
)


def count_tiles(text: str) -> int:
    """Count how many flaps *text* occupies.

    A colour marker (``{66}``, ``{green}``) is one tile regardless of how many
    characters it takes to write. Closing tags (``{/green}``, ``{/}``) are
    formatting artefacts and occupy none — matching :func:`text_to_board_array`,
    which skips them without advancing ``col_idx``.
    """
    tiles = 0
    pos = 0
    while pos < len(text):
        match = COLOR_MARKER_PATTERN.match(text, pos)
        if match:
            if not match.group(3):  # group(3) is the closing-tag alternative
                tiles += 1
            pos = match.end()
            continue
        tiles += 1
        pos += 1
    return tiles


def take_tiles(text: str, limit: int) -> tuple[str, str]:
    """Split *text* into ``(head, tail)``, ``head`` at most *limit* tiles wide.

    The split never lands inside a colour marker: a marker is taken whole or
    left for the tail. Trailing closing tags cost no tiles, so they ride along
    with ``head``.
    """
    if limit <= 0:
        return "", text
    tiles = 0
    pos = 0
    while pos < len(text):
        match = COLOR_MARKER_PATTERN.match(text, pos)
        cost = 1
        end = pos + 1
        if match:
            cost = 0 if match.group(3) else 1
            end = match.end()
        if tiles + cost > limit:
            break
        tiles += cost
        pos = end
    return text[:pos], text[pos:]


# Backslash escapes understood by ``unescape_message_newlines``. Only "\n"
# and "\\" mean anything; every other sequence is passed through untouched.
MESSAGE_ESCAPE_PATTERN = re.compile(r"\\(.)", re.DOTALL)


def unescape_message_newlines(text: str) -> str:
    r"""Interpret backslash escapes in a *single-line* message payload.

    Home Assistant's ``text`` entity cannot type a real newline, so the
    literal two-character sequence ``\n`` is how an MQTT plain-string
    payload asks for a line break (issue #1793).

    That substitution is destructive for text that legitimately contains a
    backslash, so ``\\`` is the escape hatch: it collapses to one literal
    backslash and the next character is left alone, making ``C:\\new``
    render as ``C:\new``. Any other backslash sequence (``C:\temp``) is
    passed through verbatim.

    This is deliberately *not* applied to the HTTP ``/send-message`` body or
    to JSON MQTT payloads — both can carry a real newline already, so they
    keep their exact pre-#1793 rendering.
    """

    def _replace(match: re.Match[str]) -> str:
        escaped = match.group(1)
        if escaped == "n":
            return "\n"
        if escaped == "\\":
            return "\\"
        return match.group(0)

    return MESSAGE_ESCAPE_PATTERN.sub(_replace, text)


def wrap_message_text(text: str, rows: int = 6, cols: int = 22, unescape_newlines: bool = False) -> str:
    r"""Prepare free-form user text for :func:`text_to_board_array` (issue #1793).

    - Word-wraps to ``cols`` *tiles* (not characters — a colour marker like
      ``{red}`` is one flap) so text longer than the board width flows onto
      the next row instead of being silently truncated. Explicit newlines are
      respected; wrapping fills within them.
    - Truncates to ``rows`` lines, logging a warning when content is dropped.
    - With ``unescape_newlines``, first turns the literal two-character
      sequence ``\n`` into a real line break. Off by default because it
      corrupts text that legitimately contains a backslash; see
      :func:`unescape_message_newlines`.

    :func:`text_to_board_array` itself keeps its contract of truncating each
    line at the column limit — wrapping happens here, upstream.

    Args:
        text: Raw user message.
        rows: Target board rows (default 6 for flagship, 3 for note).
        cols: Target board columns (default 22 for flagship, 15 for note).
        unescape_newlines: Treat ``\n`` as a line break (single-line clients).

    Returns:
        Newline-separated text that fits within rows x cols.
    """
    from src.formatters.message_formatter import MessageFormatter

    if unescape_newlines:
        text = unescape_message_newlines(text)

    # Ask for one row more than fits so overflow is detectable rather than
    # silently swallowed.
    lines = MessageFormatter(rows=rows, cols=cols).split_into_lines(text, max_lines=rows + 1)
    if len(lines) > rows:
        logger.warning(
            "Message too long for a %dx%d board: dropping everything past row %d",
            rows,
            cols,
            rows,
        )
        lines = lines[:rows]
    return "\n".join(lines)


def text_to_board_array(text: str, use_color_tiles: bool = True, rows: int = 6, cols: int = 22) -> list[list[int]]:
    """
    Convert formatted text to board character array.

    Color markers like {red} or {67} produce ONE solid color tile at that position.
    They do NOT color subsequent text - the board doesn't support colored text.

    Example: "Temp: {green} 62°F" produces:
    - "TEMP: " as regular text
    - One green tile
    - Space
    - "62°F" as regular text

    Args:
        text: Formatted text string (newline-separated)
        use_color_tiles: If True (default), render color markers as solid color tiles.
                        If False, strip color markers entirely.
        rows: Number of rows (default 6 for flagship, 3 for note)
        cols: Number of columns (default 22 for flagship, 15 for note)

    Returns:
        rows x cols array of character codes (0-71)
    """
    # Initialize empty board (all spaces)
    board = [[BoardChars.SPACE] * cols for _ in range(rows)]

    # Split into lines (max rows)
    lines = text.split("\n")[:rows]

    # Process each line
    for row_idx, line in enumerate(lines):
        col_idx = 0
        pos = 0

        while pos < len(line) and col_idx < cols:
            # Check for color marker at current position
            match = COLOR_MARKER_PATTERN.match(line, pos)

            if match:
                # Color marker found
                numeric_code = match.group(1)
                named_color = match.group(2)
                end_tag = match.group(3)

                if end_tag:
                    # End tags are ignored (just skip them)
                    pass
                elif use_color_tiles:
                    # Color marker produces ONE colored tile
                    if numeric_code:
                        board[row_idx][col_idx] = int(numeric_code)
                        col_idx += 1
                    elif named_color:
                        color_code = COLOR_CODES.get(named_color.lower())
                        if color_code:
                            board[row_idx][col_idx] = color_code
                            col_idx += 1
                # If not use_color_tiles, we just skip the marker entirely

                # Move past the marker
                pos = match.end()
                continue

            # Regular character
            char = line[pos].upper()

            # Convert character to code
            char_code = BoardChars.get_char_code(char)
            if char_code is not None:
                board[row_idx][col_idx] = char_code
            else:
                # Unknown character - use space
                board[row_idx][col_idx] = BoardChars.SPACE

            col_idx += 1
            pos += 1

    return board


def format_board_array_preview(board: list[list[int]]) -> str:
    """
    Create a human-readable preview of a board array.

    Args:
        board: 6x22 character array

    Returns:
        String representation with characters and color indicators
    """
    lines = []

    # Character code to character mapping (reverse lookup)
    # Based on official board character codes
    code_to_char = {
        0: " ",  # Blank/space
    }

    # Letters A-Z (codes 1-26)
    for i in range(26):
        code_to_char[i + 1] = chr(ord("A") + i)

    # Numbers: 1-9 are codes 27-35, 0 is code 36
    for i in range(1, 10):
        code_to_char[i + 26] = str(i)  # 1→27, 2→28, ..., 9→35
    code_to_char[36] = "0"

    # Punctuation (official codes)
    special_chars = {
        37: "!",  # Exclamation
        38: "@",  # At
        39: "#",  # Pound
        40: "$",  # Dollar
        41: "(",  # Left paren
        42: ")",  # Right paren
        44: "-",  # Dash/hyphen
        46: "+",  # Plus
        47: "&",  # Ampersand
        48: "=",  # Equals
        49: ";",  # Semicolon
        50: ":",  # Colon
        52: "'",  # Single quote
        53: '"',  # Double quote
        54: "%",  # Percent
        55: ",",  # Comma
        56: ".",  # Period
        59: "/",  # Slash
        60: "?",  # Question
        62: "°",  # Degree
    }
    code_to_char.update(special_chars)

    # Color tiles
    color_names = {
        63: "[RED]",
        64: "[ORG]",
        65: "[YEL]",
        66: "[GRN]",
        67: "[BLU]",
        68: "[VIO]",
        69: "[WHT]",
        70: "[BLK]",
        71: "[FIL]",
    }

    for row in board:
        line_chars = []
        for code in row:
            if code in color_names:
                line_chars.append(color_names[code])
            else:
                line_chars.append(code_to_char.get(code, "?"))
        lines.append("".join(line_chars))

    return "\n".join(lines)


def validate_board_array(board: list[list[int]], rows: int = 6, cols: int = 22) -> bool:
    """
    Validate that a board array is properly formatted.

    Args:
        board: Character array
        rows: Expected number of rows (default 6)
        cols: Expected number of columns (default 22)

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(board, list) or len(board) != rows:
        logger.error(
            f"Invalid board: expected {rows} rows, got {len(board) if isinstance(board, list) else 'not a list'}"
        )
        return False

    for i, row in enumerate(board):
        if not isinstance(row, list) or len(row) != cols:
            logger.error(
                f"Invalid row {i}: expected {cols} columns, got {len(row) if isinstance(row, list) else 'not a list'}"
            )
            return False

        for j, code in enumerate(row):
            if not isinstance(code, int) or code < 0 or code > 71:
                logger.error(f"Invalid character code at row {i}, col {j}: {code}")
                return False

    return True
