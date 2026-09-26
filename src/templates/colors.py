"""The flap-colour palette — one definition, imported by everyone who needs it.

``engine.py`` and ``expressions.py`` each carried their own copy, with
``expressions`` noting it was "kept in sync with ``COLOR_CODES`` there". It
was not: ``filled`` (code 71) existed only in the expressions copy, so a
formula could emit a marker the engine's word-wrap did not recognize (#1885).

``engine`` imports ``expressions``, so the shared table cannot live in either
of them without a cycle. It lives here instead, with no imports of its own.
"""

from __future__ import annotations

#: Colour token name -> Vestaboard flap code. Aliases map to the same code.
COLOR_CODES: dict[str, int] = {
    "red": 63,
    "orange": 64,
    "yellow": 65,
    "green": 66,
    "blue": 67,
    "violet": 68,
    "purple": 68,  # alias
    "white": 69,
    "black": 70,
    "filled": 71,
}

#: Inclusive numeric flap-code range for ``{NN}`` colour markers, derived
#: from the palette so the two cannot drift. Three engine code paths used to
#: hardcode 63-70 while the tile counter used 63-71, which split word-wrap
#: decisions on the ``filled`` flap.
NUMERIC_COLOR_RANGE: tuple[int, int] = (min(COLOR_CODES.values()), max(COLOR_CODES.values()))


def is_color_code(code: int) -> bool:
    """True when ``{code}`` is a colour marker rather than ordinary text."""
    low, high = NUMERIC_COLOR_RANGE
    return low <= code <= high
