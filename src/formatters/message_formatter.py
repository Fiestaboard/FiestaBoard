"""Message formatting for board display.

The board supports:
- Characters: A-Z, 0-9, and limited punctuation (codes 0-62)
- Color tiles: Red, Orange, Yellow, Green, Blue, Violet, White, Black (codes 63-70)

Color markers like {{red}} or {{66}} create SOLID COLOR TILES, not colored text.
Use them as decorative indicators followed by a space, e.g., "{green} SSID: network"
"""

from src.text_to_board import count_tiles, take_tiles


class MessageFormatter:
    """Formats data for a configurable board character grid.

    Class-level MAX_ROWS/MAX_COLS remain for backward compatibility.
    Instance-level _rows/_cols reflect the target board's actual dimensions.
    """

    MAX_ROWS = 6
    MAX_COLS = 22

    def __init__(self, rows: int = 6, cols: int = 22) -> None:
        """Initialize message formatter.

        Args:
            rows: Number of rows for the target board (default 6 for flagship).
            cols: Number of columns for the target board (default 22 for flagship).
        """
        self._rows = rows
        self._cols = cols

    def split_into_lines(self, text: str, max_lines: int = MAX_ROWS) -> list[str]:
        """
        Split text into lines that each fit the board width.

        Width is measured in *flaps*, not characters: a colour marker such as
        ``{red}`` writes five characters but occupies one tile, and a closing
        tag such as ``{/green}`` occupies none. Measuring characters wrapped
        text that actually fit and wasted the rest of the row (issue #1793).

        A word wider than the board is hard-broken across rows rather than
        left to be truncated at the column limit downstream, and a
        whitespace-only line still yields the (blank) row it asked for.

        Args:
            text: Text to split
            max_lines: Maximum number of lines

        Returns:
            List of lines (each at most self._cols tiles wide)
        """
        result: list[str] = []

        for line in text.split("\n")[:max_lines]:
            if count_tiles(line) <= self._cols:
                result.append(line)
            else:
                result.extend(self._wrap_line(line))

        return result[:max_lines]

    def _wrap_line(self, line: str) -> list[str]:
        """Greedy word-wrap one over-wide line into board-width rows."""
        words = line.split()
        if not words:
            # Whitespace-only line: keep the blank row instead of returning
            # nothing and silently shifting everything below it up.
            return [""]

        wrapped: list[str] = []
        current = ""
        current_tiles = 0

        for word in words:
            word_tiles = count_tiles(word)
            if current and current_tiles + 1 + word_tiles <= self._cols:
                current = f"{current} {word}"
                current_tiles += 1 + word_tiles
                continue
            if current:
                wrapped.append(current)
                current, current_tiles = "", 0
            # A single word wider than the board flows onto further rows
            # instead of vanishing past the column limit.
            while word_tiles > self._cols:
                head, word = take_tiles(word, self._cols)
                if not head:  # defensive: never loop forever on a 0-wide board
                    break
                wrapped.append(head)
                word_tiles = count_tiles(word)
            if word:
                current, current_tiles = word, word_tiles

        if current:
            wrapped.append(current)
        return wrapped
