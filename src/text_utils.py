"""Shared text utilities for alignment/wrap prefix parsing."""

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
