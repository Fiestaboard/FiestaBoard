"""Shared text utilities: alignment/wrap prefix parsing, counted nouns."""

import re

ALIGNMENT_PREFIX_RE = re.compile(r"^\{(left|center|right)\}", re.IGNORECASE)


def extract_alignment_from_line(line: str) -> tuple[str, bool, str]:
    """Extract alignment and wrap prefixes from a template line.

    Parses optional ``{wrap}`` and ``{left}``/``{center}``/``{right}``
    prefixes at the start of *line*.

    Returns:
        (alignment, wrap_enabled, content) where *alignment* is one of
        ``"left"``, ``"center"``, ``"right"``; *wrap_enabled* is ``True``
        when ``{wrap}`` was present; and *content* is the remaining text.
    """
    remaining = line
    wrap_enabled = False

    if remaining.startswith("{wrap}"):
        wrap_enabled = True
        remaining = remaining[6:]

    m = ALIGNMENT_PREFIX_RE.match(remaining)
    if m:
        return (m.group(1).lower(), wrap_enabled, remaining[m.end() :])

    return ("left", wrap_enabled, remaining)


def count_noun(count: int, singular: str, plural: str | None = None) -> str:
    """``"1 row"`` / ``"8 rows"``: *count* with the noun in the right number.

    *plural* defaults to *singular* + ``"s"``; pass it for an irregular one
    (``count_noun(n, "entry", "entries")``).
    """
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"
