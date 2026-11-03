"""Bound intermediate template strings before repeated substitutions grow them."""

from collections.abc import Callable
from re import Match, Pattern

MAX_TEMPLATE_TEXT = 65_536


def bounded_sub(pattern: Pattern[str], replacement: Callable[[Match[str]], str], text: str) -> str:
    """Bound expansion while preserving existing oversized literal templates.

    Legacy parsing accepts long literal brace runs. Their existing input size
    is the ceiling when it exceeds the normal expansion budget; substitution
    must not truncate a template that does not grow.
    """
    parts: list[str] = []
    remaining = max(MAX_TEMPLATE_TEXT, len(text))
    position = 0
    for match in pattern.finditer(text):
        literal = text[position : min(match.start(), position + remaining)]
        parts.append(literal)
        remaining -= len(literal)
        if not remaining:
            break
        value = replacement(match)[:remaining]
        parts.append(value)
        remaining -= len(value)
        position = match.end()
        if not remaining:
            break
    if remaining:
        parts.append(text[position : position + remaining])
    return "".join(parts)
