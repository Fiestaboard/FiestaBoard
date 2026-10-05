"""Character sets: FiestaUI's built-ins, and a plugin's declaration made whole.

A character set says what a board can draw (plan D17). The built-ins
(``vestaboard_v1`` / ``vestaboard_v2`` / ``led_5x7`` / ``led_3x5``) are
FiestaUI's ``CHARACTER_SETS`` exported flattened and vendored verbatim as
``character-sets.json`` in :mod:`src.fiestaui`. A plugin's set may be partial
over ``extends``; :func:`materialize_character_set` ports FiestaUI's
``materializeCharacterSet`` and :func:`validate_character_set` its
``validateCharacterSet`` (``src/lib/character-sets.ts``, 45496c9), messages
included.

Sets are plain dicts in FiestaUI's JSON shape (camelCase keys), because that
is the document an output plugin's manifest declares.

This is core's one materialiser: the LED raster (a plugin set's ``glyphs``)
and the output-plugin manifest (:mod:`src.outputs.output_manifest`, its
conformance suite and board geometry) all make a set whole here.

What a set does to a message is here too, ported exactly from the same
FiestaUI file: :func:`charset_issue` (``charsetIssue``),
:func:`charset_fallback` (``charsetFallback``) and :func:`validate_message`
(``validateMessage``), proven against FiestaUI's golden cases
(``tests/test_charset_fallback_parity.py``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from src.fiestaui import builtin_character_sets
from src.markup import BOARD_ICONS, BoardToken, parse_line

from .fonts import LED_FONTS

__all__ = [
    "BUILTIN_CHARACTER_SETS",
    "CharacterSet",
    "CharacterSetError",
    "CharsetLookup",
    "CharsetValidation",
    "CharsetValidationIssue",
    "ValidationResult",
    "charset_fallback",
    "charset_issue",
    "has_extended_markup",
    "materialize_character_set",
    "resolve_character_set",
    "validate_character_set",
    "validate_message",
]

#: A character set document (FiestaUI ``CharacterSet``).
CharacterSet = dict[str, Any]

#: Built-in id -> flattened set.
BUILTIN_CHARACTER_SETS: Mapping[str, CharacterSet] = builtin_character_sets()


class CharacterSetError(ValueError):
    """A declared character set cannot be made whole, or is not valid."""


_KEYS = frozenset(
    {
        "id",
        "label",
        "version",
        "extends",
        "chars",
        "tiles",
        "icons",
        "mixedCase",
        "colorSpans",
        "blockSpans",
        "code62Glyph",
        "font",
        "glyphs",
    }
)
_FLAGS = ("tiles", "mixedCase", "colorSpans", "blockSpans")
_ID = re.compile(r"[a-z][a-z0-9_]*")
_ROWS = re.compile(r"[#.]+")
_ABSENT = object()


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_positive_int(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return float(value).is_integer() and value >= 1


def validate_character_set(doc: Any) -> ValidationResult:
    """Whether ``doc`` is a well-formed character set (FiestaUI ``validateCharacterSet``).

    A declaration with a string ``extends`` may leave fields out; they are
    inherited, and :func:`materialize_character_set` validates the result.
    Never raises.
    """
    if not isinstance(doc, dict):
        return ValidationResult(False, ["not an object"])
    errors: list[str] = [f"{key}: not a character set field" for key in doc if key not in _KEYS]
    partial = isinstance(doc.get("extends"), str)

    def present(name: str) -> bool:
        # JSON null is a value, not an absence, exactly as `undefined` is not `null`.
        return not (partial and name not in doc)

    def get(name: str) -> Any:
        return doc.get(name, _ABSENT)

    doc_id = get("id")
    if not isinstance(doc_id, str) or not _ID.fullmatch(doc_id):
        errors.append("id: a lowercase identifier (letters, digits, _)")
    label = get("label")
    if present("label") and (not isinstance(label, str) or label == ""):
        errors.append("label: a non-empty string")
    if present("version") and not _is_positive_int(get("version")):
        errors.append("version: a positive integer")
    if "extends" in doc and not isinstance(doc["extends"], str):
        errors.append("extends: a set id")
    chars = get("chars")
    if present("chars") and (not _is_string_list(chars) or any(len(c) != 1 or c == " " for c in chars)):
        errors.append("chars: an array of single printable characters")
    for flag in _FLAGS:
        if present(flag) and not _is_bool(get(flag)):
            errors.append(f"{flag}: a boolean")
    icons = get("icons")
    if present("icons") and (not _is_string_list(icons) or any(i not in BOARD_ICONS for i in icons)):
        errors.append(f"icons: an array of registered icon names ({', '.join(BOARD_ICONS)})")
    if "code62Glyph" in doc and doc["code62Glyph"] not in ("degree", "heart"):
        errors.append('code62Glyph: "degree" or "heart"')
    font = get("font")
    if "font" in doc and not (isinstance(font, str) and font in LED_FONTS):
        errors.append(f"font: one of {', '.join(LED_FONTS)}")
    if "glyphs" in doc:
        errors.extend(_glyph_errors(doc["glyphs"], font, chars, partial))
    return ValidationResult(not errors, errors)


def _glyph_errors(glyphs: Any, font: Any, chars: Any, partial: bool) -> Iterable[str]:
    if not isinstance(glyphs, dict):
        yield "glyphs: an object of char → rows"
        return
    if font is _ABSENT and not partial:
        yield "glyphs: need a font to size against"
    face = LED_FONTS.get(font) if isinstance(font, str) else None
    for char, rows in glyphs.items():
        if len(char) != 1:
            yield f"glyphs.{char}: key must be one character"
        if not _is_string_list(rows) or not rows or any(not _ROWS.fullmatch(r) for r in rows):
            yield f"glyphs.{char}: rows of '#'/'.' characters"
        elif face and (len(rows) != face.glyph_height or any(len(r) != face.glyph_width for r in rows)):
            yield f"glyphs.{char}: {face.glyph_height} rows of {face.glyph_width} '#'/'.' characters"
        if _is_string_list(chars) and char not in chars:
            yield f"glyphs.{char}: not in chars"


def _pick(child: dict, parent: Mapping | None, key: str, default: Any = _ABSENT) -> Any:
    """``child[key] ?? parent?.[key] ?? default``: null counts as absent, as in JS."""
    value = child.get(key)
    if value is None and parent is not None:
        value = parent.get(key)
    return default if value is None else value


def materialize_character_set(declaration: dict, known: Iterable[CharacterSet] = ()) -> CharacterSet:
    """A declared set made whole (FiestaUI ``materializeCharacterSet``).

    - A field the declaration gives replaces the parent's, arrays and
      ``glyphs`` wholesale; a field it omits is inherited from the set it
      ``extends`` (a built-in, or one of ``known``, already materialised).
    - ``version`` is never inherited: the declaration's own, default 1.
    - ``extends`` stays on the result as lineage.

    Raises:
        CharacterSetError: an invalid declaration (a malformed field, or a key that
            is not a set field: a typo is never silently dropped), an unknown
            or circular ``extends``, a set without ``extends`` that is not
            complete, or an invalid result.
    """
    set_id = declaration.get("id")
    # The declaration is checked as given (whole, or partial over `extends`)
    # before anything is inherited.
    declared = validate_character_set(declaration)
    if not declared.ok:
        raise CharacterSetError(f'Character set "{set_id}" is invalid: {"; ".join(declared.errors)}')
    parent: Mapping | None = None
    if "extends" in declaration:
        parent_id = declaration["extends"]
        parent = next((k for k in known if k.get("id") == parent_id), None)
        if parent is None and isinstance(parent_id, str):
            parent = BUILTIN_CHARACTER_SETS.get(parent_id)
        if parent is None:
            shown = parent_id if isinstance(parent_id, str) else json.dumps(parent_id)
            raise CharacterSetError(f'Character set "{set_id}" extends unknown set "{shown}".')
        if parent.get("id") == set_id:
            raise CharacterSetError(f'Character set "{set_id}" extends itself.')

    out: CharacterSet = {
        "id": set_id,
        "label": _pick(declaration, parent, "label", set_id),
        "version": declaration["version"] if declaration.get("version") is not None else 1,
        "chars": _pick(declaration, parent, "chars", []),
        "tiles": _pick(declaration, parent, "tiles", False),
        "icons": _pick(declaration, parent, "icons", []),
        "mixedCase": _pick(declaration, parent, "mixedCase", False),
        "colorSpans": _pick(declaration, parent, "colorSpans", False),
        "blockSpans": _pick(declaration, parent, "blockSpans", False),
    }
    if "extends" in declaration:
        out["extends"] = declaration["extends"]
    for key in ("code62Glyph", "font", "glyphs"):
        value = _pick(declaration, parent, key)
        if value is not _ABSENT:
            out[key] = value
    result = validate_character_set(out)
    if not result.ok:
        raise CharacterSetError(f'Character set "{set_id}" is invalid: {"; ".join(result.errors)}')
    return out


# --- what a set does to a message (plan D17, answer 2) ------------------------


def resolve_character_set(charset: str | CharacterSet) -> CharacterSet:
    """A set given by built-in id, or the (materialised) set itself.

    Raises:
        KeyError: an id that is not a built-in.
    """
    return BUILTIN_CHARACTER_SETS[charset] if isinstance(charset, str) else charset


def has_extended_markup(charset: str | CharacterSet | None) -> bool:
    """Whether a board drawing with *charset* speaks extended markup (plan D19).

    True when the set draws colour spans, block spans or any icon: a board
    that can show ``{red:HOT}`` or ``{icon:sun}`` parses them. False for the
    split-flap sets and for no set at all.
    """
    if not isinstance(charset, (str, Mapping)):
        return False
    s = resolve_character_set(charset)
    return bool(s.get("colorSpans") or s.get("blockSpans") or s.get("icons"))


class CharsetLookup:
    """One set's ``chars`` / ``icons`` as sets, built once per use.

    FiestaUI memoises these per set object; core builds one per projection
    (a render) or per call, so nothing outlives the set it was built from.
    """

    __slots__ = ("chars", "charset", "icons")

    def __init__(self, charset: str | CharacterSet) -> None:
        self.charset = resolve_character_set(charset)
        self.chars = frozenset(self.charset.get("chars") or ())
        self.icons = frozenset(self.charset.get("icons") or ())


def _lookup(charset: str | CharacterSet | CharsetLookup) -> CharsetLookup:
    return charset if isinstance(charset, CharsetLookup) else CharsetLookup(charset)


def charset_issue(charset: str | CharacterSet | CharsetLookup, token: BoardToken) -> str | None:
    """The first reason *charset* cannot draw *token* as written, or ``None``
    (FiestaUI ``charsetIssue``): ``icon``, ``tile``, ``blockSpan``,
    ``colorSpan``, ``case`` or ``char``."""
    look = _lookup(charset)
    s = look.charset
    if token.icon is not None and token.icon not in look.icons:
        return "icon"
    if token.type == "color":
        return None if s.get("tiles") else "tile"
    if token.background is not None and not s.get("blockSpans"):
        return "blockSpan"
    if token.color is not None and not s.get("colorSpans"):
        return "colorSpan"
    if token.icon is not None or token.value == " " or token.value in look.chars:
        return None
    upper = token.value.upper()
    if token.value != upper and upper in look.chars:
        return "char" if s.get("mixedCase") else "case"
    return "char"


def charset_fallback(charset: str | CharacterSet | CharsetLookup, token: BoardToken) -> BoardToken:
    """What *charset* draws for *token* (FiestaUI ``charsetFallback``).

    (a) An icon the set lacks becomes its registry fallback (a two-digit
    fallback is a colour tile, anything else a character, ``None`` a blank),
    keeping the span's ``color`` / ``background``; then (b) a tile is kept
    when the set has tiles, else a blank; (c) an icon the set has is kept;
    (d) a character drops ``color`` unless the set has colour spans and
    ``background`` unless it has block spans, and one the set lacks tries
    its uppercase, then the ``°``/``♥`` swap, then a blank.
    """
    look = _lookup(charset)
    s = look.charset
    t = token
    if t.icon is not None and t.icon not in look.icons:
        fallback = BOARD_ICONS[t.icon].fallback
        if fallback is not None and len(fallback) == 2 and fallback.isdigit():
            t = BoardToken("color", code=fallback, color=t.color, background=t.background)
        else:
            t = BoardToken("char", value=" " if fallback is None else fallback, color=t.color, background=t.background)
    if t.type == "color":
        return t if s.get("tiles") else BoardToken("char", value=" ")
    if t.icon is not None:
        return t
    value = t.value
    if value not in look.chars:
        upper = value.upper()
        if upper in look.chars:
            value = upper
        elif value == "°" and "♥" in look.chars:
            value = "♥"
        elif value == "♥" and "°" in look.chars:
            value = "°"
        elif value != " ":
            value = " "
    return BoardToken(
        "char",
        value=value,
        color=t.color if s.get("colorSpans") else None,
        background=t.background if s.get("blockSpans") else None,
    )


@dataclass(frozen=True)
class CharsetValidationIssue:
    """One cell a set cannot draw as written, and what it draws instead."""

    row: int
    col: int
    token: BoardToken
    reason: str
    fallback: BoardToken

    def to_dict(self) -> dict:
        """FiestaUI's ``CharsetValidationIssue`` JSON shape."""
        return {
            "row": self.row,
            "col": self.col,
            "token": self.token.to_dict(),
            "reason": self.reason,
            "fallback": self.fallback.to_dict(),
        }


@dataclass(frozen=True)
class CharsetValidation:
    ok: bool
    issues: list[CharsetValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "issues": [i.to_dict() for i in self.issues]}


def validate_message(message: str, charset: str | CharacterSet) -> CharsetValidation:
    """Check *message* against *charset*, position by position
    (FiestaUI ``validateMessage``).

    Each line is parsed with extended markup and case preserved — the
    message as written, before any board's projection — so the editor can
    warn about every cell the board will draw differently.
    """
    look = _lookup(charset)
    issues: list[CharsetValidationIssue] = []
    for row, line in enumerate(message.split("\n")):
        for col, token in enumerate(parse_line(line, extended_markup=True, preserve_case=True)):
            reason = charset_issue(look, token)
            if reason:
                issues.append(CharsetValidationIssue(row, col, token, reason, charset_fallback(look, token)))
    return CharsetValidation(not issues, issues)
