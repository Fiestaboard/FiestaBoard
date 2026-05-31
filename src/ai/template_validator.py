"""Server-side repair pass for AI-generated template lines.

The AI is prompted to use template syntax like ``{{filled:X}}`` where ``X``
is either a single repeated character (``.``, ``-``) or a bare color name
(``red``, ``green``). Models nevertheless make a handful of recurring
mistakes that silently mis-render:

- ``{{filled:green.}}`` — trailing punctuation on a color name. The
  engine falls through to the text-pattern branch and repeats the
  literal string ``green.`` across the row.
- ``{{filled:}}`` — empty argument. Renders nothing useful.
- ``{{filled.X}}`` / ``{{filled X}}`` — wrong separator. The block isn't
  recognised as a fill at all; it falls through to the variable resolver
  and renders ``???``.

This module repairs the unambiguous cases in-place and returns a list of
human-readable warnings describing what was changed. Warnings are
surfaced to the caller (``/pages/ai/generate`` response, or an SSE
``warning`` event on the chat stream) so the user — and, on the next
turn, the model — can see what happened.

We are deliberately conservative: we only auto-fix when the intent is
unambiguous (e.g. ``{{filled:green.}}`` → ``{{filled:green}}``). Anything
ambiguous is left untouched and only flagged.
"""

from __future__ import annotations

import re

# Known color names accepted by both the template engine and BoardChars.
# Keep in sync with ``src.templates.engine.COLOR_CODES`` and
# ``src.board_chars.BoardChars.get_color_code``.
_COLOR_NAMES = frozenset(
    {
        "red",
        "orange",
        "yellow",
        "green",
        "blue",
        "violet",
        "purple",
        "white",
        "black",
    }
)

# ``{{filled:ARG}}`` or ``{{fill_space_repeat:ARG}}``. We capture the
# keyword and the argument separately so we can preserve which form the
# model used in the repaired output.
_FILLED_RE = re.compile(
    r"\{\{\s*(filled|fill_space_repeat)\s*:\s*([^}]*?)\s*\}\}",
    re.IGNORECASE,
)

# Wrong-separator forms: ``{{filled.X}}`` or ``{{filled X}}``. The
# argument here is whatever comes between the separator and the closing
# braces. We only match when there is no colon at all in the block, so
# we don't shadow the legitimate ``{{filled:X}}`` form.
_FILLED_WRONG_SEP_RE = re.compile(
    r"\{\{\s*(filled|fill_space_repeat)\s*([.\s])\s*([^}:]*?)\s*\}\}",
    re.IGNORECASE,
)

# Characters that count as "stray trailing punctuation" we will strip
# from a color-name argument. Whitespace is included so that
# ``{{filled:green }}`` is also normalised.
_STRAY_TRAILING_CHARS = ".,;:!?\"' \t"

# Bare color tile with trailing punctuation: ``{{green.}}``, ``{{red,}}``.
# Captures (color_candidate, trailing_chars). We require at least one
# trailing char so we don't accidentally match clean blocks.
_BARE_COLOR_PUNCT_RE = re.compile(
    r"\{\{\s*([a-zA-Z]+)([.,;:!?\"' \t]+)\s*\}\}",
    re.IGNORECASE,
)


def _looks_like_color_with_trailing_punct(arg: str) -> tuple[bool, str, str]:
    """If ``arg`` is a color name plus stray trailing punctuation, split it.

    Returns ``(matched, color_name, stripped_suffix)``. ``matched`` is
    True only when stripping the trailing run of punctuation/whitespace
    yields a recognised color name AND there was at least one such
    character to strip.
    """
    if not arg:
        return False, "", ""
    stripped = arg.rstrip(_STRAY_TRAILING_CHARS)
    if stripped == arg:
        return False, "", ""
    if stripped.lower() in _COLOR_NAMES:
        return True, stripped, arg[len(stripped):]
    return False, "", ""


def repair_template_lines(
    lines: list[str],
) -> tuple[list[str], list[str]]:
    """Repair common AI mistakes in ``{{filled:...}}`` syntax.

    Args:
        lines: Raw template lines as returned by the model.

    Returns:
        A tuple ``(repaired_lines, warnings)``. ``repaired_lines`` is
        always the same length as ``lines``; ``warnings`` is a list of
        human-readable strings, one per repair or notable issue. Both
        are empty/identity when nothing needed fixing.
    """
    repaired: list[str] = []
    warnings: list[str] = []

    for idx, line in enumerate(lines):
        new_line, line_warnings = _repair_line(line, idx)
        repaired.append(new_line)
        warnings.extend(line_warnings)

    return repaired, warnings


def _repair_line(line: str, idx: int) -> tuple[str, list[str]]:
    """Apply all known repairs to a single line."""
    warnings: list[str] = []
    line_no = idx + 1

    # ---- 1. ``{{filled.X}}`` / ``{{filled X}}`` → ``{{filled:X}}`` ----
    def _fix_wrong_sep(match: re.Match[str]) -> str:
        keyword = match.group(1)
        sep = match.group(2)
        arg = match.group(3)
        if not arg:
            warnings.append(
                f"Line {line_no}: `{{{{{keyword}{sep}}}}}` is missing an "
                "argument; expected `{{" + keyword + ":X}}` where X is a "
                "character (e.g. `.`) or a color name (e.g. `blue`)."
            )
            # Leave it alone so the user notices.
            return match.group(0)
        warnings.append(
            f"Line {line_no}: rewrote `{{{{{keyword}{sep}{arg}}}}}` to "
            f"`{{{{{keyword}:{arg}}}}}` — fills require a colon "
            "separator."
        )
        return "{{" + keyword + ":" + arg + "}}"

    line = _FILLED_WRONG_SEP_RE.sub(_fix_wrong_sep, line)

    # ---- 2. ``{{filled:green.}}`` etc. — trailing punctuation on a
    # color name. Also handles empty arg and stray surrounding
    # whitespace inside the braces.
    def _fix_arg(match: re.Match[str]) -> str:
        keyword = match.group(1)
        arg = match.group(2)
        canonical = "{{" + keyword + ":" + arg + "}}"

        if arg == "":
            warnings.append(
                f"Line {line_no}: `{{{{{keyword}:}}}}` has no argument; "
                "expected a character or color name (e.g. "
                f"`{{{{{keyword}:.}}}}` or `{{{{{keyword}:blue}}}}`)."
            )
            return match.group(0)

        matched, color, suffix = _looks_like_color_with_trailing_punct(arg)
        if matched:
            warnings.append(
                f"Line {line_no}: stripped trailing {suffix!r} from "
                f"`{{{{{keyword}:{arg}}}}}` — color fills must use only "
                "the bare color name (e.g. "
                f"`{{{{{keyword}:{color.lower()}}}}}`). A trailing "
                "character makes the color lookup fail and the literal "
                "text would be repeated across the row."
            )
            return "{{" + keyword + ":" + color + "}}"

        # Single-character pattern (e.g. `.`, `-`) or a deliberate
        # multi-char text pattern is valid. If the model wrapped the
        # block in stray whitespace, normalise to the canonical form
        # so downstream regex-based passes (and rendering) work.
        if match.group(0) != canonical:
            warnings.append(
                f"Line {line_no}: normalised whitespace in "
                f"`{match.group(0)}` to `{canonical}`."
            )
            return canonical
        return match.group(0)

    line = _FILLED_RE.sub(_fix_arg, line)

    # ---- 3. ``{{green.}}`` etc. — bare color tile with trailing punctuation.
    # The engine looks up the block content directly as a color name, so any
    # trailing character causes a silent render failure.
    def _fix_bare_color(match: re.Match[str]) -> str:
        candidate = match.group(1)
        trailing = match.group(2)
        if candidate.lower() in _COLOR_NAMES:
            warnings.append(
                f"Line {line_no}: stripped trailing {trailing!r} from "
                f"`{{{{{candidate}{trailing}}}}}` — bare color tiles must be "
                f"`{{{{{candidate}}}}}` with no extra characters."
            )
            return "{{" + candidate + "}}"
        return match.group(0)  # not a color name — leave unchanged

    line = _BARE_COLOR_PUNCT_RE.sub(_fix_bare_color, line)

    return line, warnings


__all__ = ["repair_template_lines"]
