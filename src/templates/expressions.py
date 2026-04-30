"""Inline formula expressions for FiestaBoard templates ("FiestaForm").

A small, sandboxed, Excel-like expression language that runs inside
``{{= ... }}`` blocks of a template. Designed to give users one-line
logical/computational power similar to a spreadsheet cell, without
allowing arbitrary Python execution or user-defined functions.

Highlights:
    * Same variable namespace as plain ``{{plugin.field}}`` lookups.
    * Operators: arithmetic ``+ - * / %``, comparison ``= == != <> < > <= >=``,
      logical ``AND OR NOT`` (also ``&& || !``), string concat ``&``.
    * Built-in functions only (no custom functions yet): IF, IFS, SWITCH,
      AND, OR, NOT, IFERROR, ISERROR, ISBLANK, DEFAULT, ABS, ROUND, FLOOR,
      CEIL, MIN, MAX, SUM, AVG, MOD, INT, SIGN, UPPER, LOWER, LEN, LEFT,
      RIGHT, MID, TRIM, CONCAT, REPLACE, REPT, CONTAINS, STARTSWITH,
      ENDSWITH, PAD, PADLEFT, CENTER, TEXT, NUM, FIXED, COLOR.
    * Excel-like error values: ``#REF``, ``#VALUE``, ``#DIV/0``, ``#NAME?``,
      ``#NUM``, ``#SYNTAX`` -- trappable with ``IFERROR``.

This module is intentionally self-contained; the only dependency on the
rest of the template engine is reading variable values from a plain
``dict`` context (the same shape used by ``TemplateEngine``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Color tile names -- duplicated from engine.py to keep this module dependency
# free. Kept in sync with ``COLOR_CODES`` there.
# --------------------------------------------------------------------------- #
_COLOR_CODES: Dict[str, int] = {
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


# --------------------------------------------------------------------------- #
# Error model
# --------------------------------------------------------------------------- #


class FormulaError(Exception):
    """Raised internally by the evaluator. ``code`` is the user-visible tag."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ErrorValue:
    """Sentinel error value produced by formula evaluation.

    Errors propagate through arithmetic / comparison / function calls
    unchanged, so that ``IFERROR`` can trap the original error tag.
    """

    code: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.code


# --------------------------------------------------------------------------- #
# Lexer
# --------------------------------------------------------------------------- #


# Token kinds
_T_NUMBER = "NUMBER"
_T_STRING = "STRING"
_T_IDENT = "IDENT"
_T_LPAREN = "LPAREN"
_T_RPAREN = "RPAREN"
_T_COMMA = "COMMA"
_T_OP = "OP"
_T_EOF = "EOF"


@dataclass
class Token:
    kind: str
    value: Any
    pos: int


# Multi-character operators must be matched before single-character ones.
_OPERATORS = (
    "==", "!=", "<>", "<=", ">=", "&&", "||",
    "<", ">", "=", "+", "-", "*", "/", "%", "&", "!",
)


def _tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        # Whitespace
        if ch.isspace():
            i += 1
            continue

        # Number literal: 42, 3.14, .5
        if ch.isdigit() or (ch == "." and i + 1 < n and source[i + 1].isdigit()):
            start = i
            saw_dot = ch == "."
            i += 1
            while i < n:
                c = source[i]
                if c.isdigit():
                    i += 1
                elif c == "." and not saw_dot:
                    saw_dot = True
                    i += 1
                else:
                    break
            text = source[start:i]
            try:
                value = float(text) if "." in text else int(text)
            except ValueError as exc:  # pragma: no cover - lexer invariant
                raise FormulaError("#SYNTAX", f"Bad number: {text}") from exc
            tokens.append(Token(_T_NUMBER, value, start))
            continue

        # String literal: "..." with backslash escapes
        if ch == '"':
            start = i
            i += 1
            buf: List[str] = []
            while i < n and source[i] != '"':
                if source[i] == "\\" and i + 1 < n:
                    nxt = source[i + 1]
                    buf.append(
                        {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt)
                    )
                    i += 2
                else:
                    buf.append(source[i])
                    i += 1
            if i >= n:
                raise FormulaError("#SYNTAX", "Unterminated string literal")
            i += 1  # closing quote
            tokens.append(Token(_T_STRING, "".join(buf), start))
            continue

        # Identifier / keyword: letters, digits, underscore, ':' (plugin instance)
        # and '.' (dotted paths). We keep dotted paths as a single IDENT.
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (
                source[i].isalnum() or source[i] in ("_", ":", ".")
            ):
                i += 1
            text = source[start:i]
            # Strip a trailing dot which is almost certainly a typo, leaving
            # it would produce a misleading "Unknown source" error.
            if text.endswith("."):
                raise FormulaError("#SYNTAX", f"Trailing dot in identifier: {text}")
            tokens.append(Token(_T_IDENT, text, start))
            continue

        # Punctuation
        if ch == "(":
            tokens.append(Token(_T_LPAREN, ch, i))
            i += 1
            continue
        if ch == ")":
            tokens.append(Token(_T_RPAREN, ch, i))
            i += 1
            continue
        if ch == ",":
            tokens.append(Token(_T_COMMA, ch, i))
            i += 1
            continue

        # Operators (longest match)
        matched = False
        for op in _OPERATORS:
            if source.startswith(op, i):
                tokens.append(Token(_T_OP, op, i))
                i += len(op)
                matched = True
                break
        if matched:
            continue

        raise FormulaError("#SYNTAX", f"Unexpected character {ch!r} at position {i}")

    tokens.append(Token(_T_EOF, None, n))
    return tokens


# --------------------------------------------------------------------------- #
# AST nodes
# --------------------------------------------------------------------------- #


class _Node:
    __slots__ = ()


@dataclass
class _Literal(_Node):
    value: Any


@dataclass
class _Var(_Node):
    path: str  # e.g. "weather.temperature"


@dataclass
class _Unary(_Node):
    op: str
    operand: _Node


@dataclass
class _Binary(_Node):
    op: str
    left: _Node
    right: _Node


@dataclass
class _Call(_Node):
    name: str  # uppercase
    args: List[_Node]


# --------------------------------------------------------------------------- #
# Parser (recursive descent)
#
# Grammar (low -> high precedence):
#   expr        := or_expr
#   or_expr     := and_expr ( ( OR | "||" ) and_expr )*
#   and_expr    := not_expr ( ( AND | "&&" ) not_expr )*
#   not_expr    := ( NOT | "!" )* cmp_expr
#   cmp_expr    := concat_expr ( cmp_op concat_expr )?
#   concat_expr := add_expr ( "&" add_expr )*
#   add_expr    := mul_expr ( ( "+" | "-" ) mul_expr )*
#   mul_expr    := unary  ( ( "*" | "/" | "%" ) unary )*
#   unary       := ( "+" | "-" ) unary | primary
#   primary     := NUMBER | STRING | "(" expr ")" | call | ident
#   call        := IDENT "(" arglist? ")"
#   arglist     := expr ( "," expr )*
#   ident       := IDENT          (constants TRUE/FALSE/NULL handled here)
# --------------------------------------------------------------------------- #


_KEYWORDS_LOGICAL = {"AND", "OR", "NOT"}
_CMP_OPS = {"=", "==", "!=", "<>", "<", ">", "<=", ">="}


class _Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _accept_op(self, *ops: str) -> Optional[str]:
        tok = self._peek()
        if tok.kind == _T_OP and tok.value in ops:
            self._advance()
            return tok.value
        return None

    def _accept_kw(self, *names: str) -> Optional[str]:
        tok = self._peek()
        if tok.kind == _T_IDENT and tok.value.upper() in names:
            self._advance()
            return tok.value.upper()
        return None

    def parse(self) -> _Node:
        node = self._parse_or()
        if self._peek().kind != _T_EOF:
            raise FormulaError(
                "#SYNTAX",
                f"Unexpected token {self._peek().value!r} at position {self._peek().pos}",
            )
        return node

    def _parse_or(self) -> _Node:
        left = self._parse_and()
        while True:
            if self._accept_kw("OR") or self._accept_op("||"):
                right = self._parse_and()
                left = _Binary("OR", left, right)
            else:
                break
        return left

    def _parse_and(self) -> _Node:
        left = self._parse_not()
        while True:
            if self._accept_kw("AND") or self._accept_op("&&"):
                right = self._parse_not()
                left = _Binary("AND", left, right)
            else:
                break
        return left

    def _parse_not(self) -> _Node:
        if self._accept_kw("NOT") or self._accept_op("!"):
            return _Unary("NOT", self._parse_not())
        return self._parse_cmp()

    def _parse_cmp(self) -> _Node:
        left = self._parse_concat()
        tok = self._peek()
        if tok.kind == _T_OP and tok.value in _CMP_OPS:
            op = self._advance().value
            # Normalize comparison operators
            if op == "=":
                op = "=="
            elif op == "<>":
                op = "!="
            right = self._parse_concat()
            left = _Binary(op, left, right)
        return left

    def _parse_concat(self) -> _Node:
        left = self._parse_add()
        while self._accept_op("&"):
            right = self._parse_add()
            left = _Binary("&", left, right)
        return left

    def _parse_add(self) -> _Node:
        left = self._parse_mul()
        while True:
            op = self._accept_op("+", "-")
            if op is None:
                break
            right = self._parse_mul()
            left = _Binary(op, left, right)
        return left

    def _parse_mul(self) -> _Node:
        left = self._parse_unary()
        while True:
            op = self._accept_op("*", "/", "%")
            if op is None:
                break
            right = self._parse_unary()
            left = _Binary(op, left, right)
        return left

    def _parse_unary(self) -> _Node:
        op = self._accept_op("+", "-")
        if op is not None:
            return _Unary(op, self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> _Node:
        tok = self._peek()

        if tok.kind == _T_NUMBER:
            self._advance()
            return _Literal(tok.value)

        if tok.kind == _T_STRING:
            self._advance()
            return _Literal(tok.value)

        if tok.kind == _T_LPAREN:
            self._advance()
            node = self._parse_or()
            close = self._advance()
            if close.kind != _T_RPAREN:
                raise FormulaError("#SYNTAX", "Missing closing ')'")
            return node

        if tok.kind == _T_IDENT:
            name = tok.value
            upper = name.upper()
            self._advance()

            # Constants
            if upper == "TRUE":
                return _Literal(True)
            if upper == "FALSE":
                return _Literal(False)
            if upper == "NULL":
                return _Literal(None)

            # Function call?
            if self._peek().kind == _T_LPAREN:
                self._advance()
                args: List[_Node] = []
                if self._peek().kind != _T_RPAREN:
                    args.append(self._parse_or())
                    while self._peek().kind == _T_COMMA:
                        self._advance()
                        args.append(self._parse_or())
                close = self._advance()
                if close.kind != _T_RPAREN:
                    raise FormulaError(
                        "#SYNTAX", f"Missing ')' in call to {name}"
                    )
                return _Call(upper, args)

            # Variable reference
            return _Var(name)

        raise FormulaError(
            "#SYNTAX",
            f"Unexpected token {tok.value!r} at position {tok.pos}",
        )


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #


_MISSING_SENTINEL = "???"


def _is_error(value: Any) -> bool:
    return isinstance(value, ErrorValue)


def _propagate(*values: Any) -> Optional[ErrorValue]:
    for v in values:
        if _is_error(v):
            return v
    return None


def _to_number(value: Any) -> float:
    """Coerce a value to a number, raising ``#VALUE`` on failure."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return 0.0
        if s == _MISSING_SENTINEL:
            raise FormulaError("#REF", "Missing value used in numeric context")
        try:
            return float(s)
        except ValueError as exc:
            raise FormulaError("#VALUE", f"Cannot convert {value!r} to number") from exc
    raise FormulaError("#VALUE", f"Cannot convert {value!r} to number")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("", "false", "no", "0"):
            return False
        if s == _MISSING_SENTINEL:
            raise FormulaError("#REF", "Missing value used in boolean context")
        return True
    return bool(value)


def _to_string(value: Any) -> str:
    """Render a value the way the rest of the template engine would."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        # Round to 1 decimal to match _get_variable_value behavior.
        rounded = round(value, 1)
        if rounded == int(rounded):
            return str(int(rounded))
        return str(rounded)
    if _is_error(value):
        return value.code
    return str(value)


def _looks_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
            return True
        except ValueError:
            return False
    return False


def _compare(left: Any, right: Any) -> int:
    """Three-way compare with Excel-ish coercion. -1/0/1."""
    # Both numeric-ish -> numeric compare.
    if _looks_numeric(left) and _looks_numeric(right):
        a = _to_number(left)
        b = _to_number(right)
        if a < b:
            return -1
        if a > b:
            return 1
        return 0
    a_s = _to_string(left).lower()
    b_s = _to_string(right).lower()
    if a_s < b_s:
        return -1
    if a_s > b_s:
        return 1
    return 0


# --- Built-in functions ---------------------------------------------------- #


def _expect_args(name: str, args: List[Any], minimum: int, maximum: Optional[int] = None) -> None:
    if len(args) < minimum:
        raise FormulaError("#VALUE", f"{name}: expected at least {minimum} args, got {len(args)}")
    if maximum is not None and len(args) > maximum:
        raise FormulaError("#VALUE", f"{name}: expected at most {maximum} args, got {len(args)}")


def _fn_if(args: List[Any]) -> Any:
    _expect_args("IF", args, 2, 3)
    cond = args[0]
    err = _propagate(cond)
    if err is not None:
        return err
    return args[1] if _to_bool(cond) else (args[2] if len(args) == 3 else "")


def _fn_ifs(args: List[Any]) -> Any:
    if len(args) < 2:
        raise FormulaError("#VALUE", "IFS: expected at least 2 args")
    # Iterate condition/value pairs. A trailing single arg (odd-length args)
    # is treated as a default value, mirroring SWITCH's default semantics so
    # users don't have to write ``IFS(..., TRUE, default)``.
    i = 0
    while i + 1 < len(args):
        cond = args[i]
        err = _propagate(cond)
        if err is not None:
            return err
        if _to_bool(cond):
            return args[i + 1]
        i += 2
    if i < len(args):
        return args[i]  # default
    return ErrorValue("#VALUE")


def _fn_switch(args: List[Any]) -> Any:
    if len(args) < 3:
        raise FormulaError("#VALUE", "SWITCH: expected at least 3 args")
    err = _propagate(args[0])
    if err is not None:
        return err
    needle = args[0]
    i = 1
    while i + 1 < len(args):
        if _compare(needle, args[i]) == 0:
            return args[i + 1]
        i += 2
    if i < len(args):
        return args[i]  # default
    return ""


def _fn_and(args: List[Any]) -> Any:
    if not args:
        return True
    err = _propagate(*args)
    if err is not None:
        return err
    return all(_to_bool(a) for a in args)


def _fn_or(args: List[Any]) -> Any:
    if not args:
        return False
    err = _propagate(*args)
    if err is not None:
        return err
    return any(_to_bool(a) for a in args)


def _fn_not(args: List[Any]) -> Any:
    _expect_args("NOT", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return not _to_bool(args[0])


def _fn_iferror(args: List[Any]) -> Any:
    _expect_args("IFERROR", args, 2, 2)
    return args[1] if _is_error(args[0]) else args[0]


def _fn_iserror(args: List[Any]) -> Any:
    _expect_args("ISERROR", args, 1, 1)
    return _is_error(args[0])


def _fn_isblank(args: List[Any]) -> Any:
    _expect_args("ISBLANK", args, 1, 1)
    v = args[0]
    if _is_error(v):
        return v
    if v is None:
        return True
    if isinstance(v, str):
        return v == "" or v == _MISSING_SENTINEL
    return False


def _fn_default(args: List[Any]) -> Any:
    _expect_args("DEFAULT", args, 2, 2)
    v = args[0]
    if _is_error(v):
        return args[1]
    if v is None or (isinstance(v, str) and (v == "" or v == _MISSING_SENTINEL)):
        return args[1]
    return v


# Math
def _math_unary(name: str, fn: Callable[[float], float]) -> Callable[[List[Any]], Any]:
    def impl(args: List[Any]) -> Any:
        _expect_args(name, args, 1, 1)
        err = _propagate(args[0])
        if err is not None:
            return err
        return fn(_to_number(args[0]))
    return impl


def _fn_round(args: List[Any]) -> Any:
    _expect_args("ROUND", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    x = _to_number(args[0])
    n = int(_to_number(args[1])) if len(args) == 2 else 0
    return round(x, n)


def _fn_min(args: List[Any]) -> Any:
    _expect_args("MIN", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return min(_to_number(a) for a in args)


def _fn_max(args: List[Any]) -> Any:
    _expect_args("MAX", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return max(_to_number(a) for a in args)


def _fn_sum(args: List[Any]) -> Any:
    _expect_args("SUM", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return sum(_to_number(a) for a in args)


def _fn_avg(args: List[Any]) -> Any:
    _expect_args("AVG", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    nums = [_to_number(a) for a in args]
    return sum(nums) / len(nums)


def _fn_mod(args: List[Any]) -> Any:
    _expect_args("MOD", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    b = _to_number(args[1])
    if b == 0:
        return ErrorValue("#DIV/0")
    return _to_number(args[0]) % b


def _fn_sign(args: List[Any]) -> Any:
    _expect_args("SIGN", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    v = _to_number(args[0])
    return -1 if v < 0 else (1 if v > 0 else 0)


# Text
def _fn_concat(args: List[Any]) -> Any:
    err = _propagate(*args)
    if err is not None:
        return err
    return "".join(_to_string(a) for a in args)


def _fn_len(args: List[Any]) -> Any:
    _expect_args("LEN", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return len(_to_string(args[0]))


def _fn_left(args: List[Any]) -> Any:
    _expect_args("LEFT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1]))
    if n < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0])[:n]


def _fn_right(args: List[Any]) -> Any:
    _expect_args("RIGHT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1]))
    if n < 0:
        return ErrorValue("#VALUE")
    s = _to_string(args[0])
    return s[-n:] if n > 0 else ""


def _fn_mid(args: List[Any]) -> Any:
    _expect_args("MID", args, 3, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    s = _to_string(args[0])
    # Excel MID is 1-indexed.
    start = int(_to_number(args[1])) - 1
    if start < 0:
        start = 0
    length = int(_to_number(args[2]))
    if length < 0:
        return ErrorValue("#VALUE")
    return s[start : start + length]


def _fn_replace(args: List[Any]) -> Any:
    _expect_args("REPLACE", args, 3, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).replace(_to_string(args[1]), _to_string(args[2]))


def _fn_rept(args: List[Any]) -> Any:
    _expect_args("REPT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1]))
    if n < 0:
        return ErrorValue("#VALUE")
    # Cap repetitions so a runaway formula can't allocate gigabytes; the board
    # is at most 22 cols wide so 1024 is far more than enough.
    if n > 1024:
        return ErrorValue("#NUM")
    return _to_string(args[0]) * n


def _fn_contains(args: List[Any]) -> Any:
    _expect_args("CONTAINS", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[1]) in _to_string(args[0])


def _fn_startswith(args: List[Any]) -> Any:
    _expect_args("STARTSWITH", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).startswith(_to_string(args[1]))


def _fn_endswith(args: List[Any]) -> Any:
    _expect_args("ENDSWITH", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).endswith(_to_string(args[1]))


def _fn_pad(args: List[Any]) -> Any:
    _expect_args("PAD", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0]).ljust(width)[:width]


def _fn_padleft(args: List[Any]) -> Any:
    _expect_args("PADLEFT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    s = _to_string(args[0])
    return s.rjust(width) if len(s) <= width else s[-width:]


def _fn_center(args: List[Any]) -> Any:
    _expect_args("CENTER", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0]).center(width)[:width]


def _fn_text(args: List[Any]) -> Any:
    _expect_args("TEXT", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return _to_string(args[0])


def _fn_num(args: List[Any]) -> Any:
    _expect_args("NUM", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return _to_number(args[0])


def _fn_fixed(args: List[Any]) -> Any:
    _expect_args("FIXED", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1])) if len(args) == 2 else 2
    if n < 0:
        n = 0
    return f"{_to_number(args[0]):.{n}f}"


def _text_unary(name: str, args: List[Any], fn: Callable[[str], str]) -> Any:
    _expect_args(name, args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return fn(_to_string(args[0]))


def _fn_color(args: List[Any]) -> Any:
    _expect_args("COLOR", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    raw = args[0]
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        code = int(raw)
    else:
        name = _to_string(raw).strip().lower()
        if name.isdigit():
            code = int(name)
        else:
            mapped = _COLOR_CODES.get(name)
            if mapped is None:
                return ErrorValue("#VALUE")
            code = mapped
    if not 63 <= code <= 71:
        return ErrorValue("#VALUE")
    # Single-brace marker matches the format produced by ``_normalize_colors``.
    return f"{{{code}}}"


def _math_floor(x: float) -> float:
    """Round toward negative infinity (matches Python ``math.floor``)."""
    truncated = int(x)
    # ``int()`` truncates toward zero. For negative non-integers we need
    # to step one further toward -infinity.
    if x < 0 and x != truncated:
        return float(truncated - 1)
    return float(truncated)


def _math_ceil(x: float) -> float:
    """Round toward positive infinity (matches Python ``math.ceil``)."""
    truncated = int(x)
    # ``int()`` truncates toward zero. For positive non-integers we need
    # to step one further toward +infinity.
    if x > 0 and x != truncated:
        return float(truncated + 1)
    return float(truncated)


_BUILTINS: Dict[str, Callable[[List[Any]], Any]] = {
    # Logic
    "IF": _fn_if,
    "IFS": _fn_ifs,
    "SWITCH": _fn_switch,
    "AND": _fn_and,
    "OR": _fn_or,
    "NOT": _fn_not,
    "IFERROR": _fn_iferror,
    "ISERROR": _fn_iserror,
    "ISBLANK": _fn_isblank,
    "DEFAULT": _fn_default,
    # Math
    "ABS": _math_unary("ABS", abs),
    "FLOOR": _math_unary("FLOOR", _math_floor),
    "CEIL": _math_unary("CEIL", _math_ceil),
    "INT": _math_unary("INT", lambda x: float(int(x))),
    "ROUND": _fn_round,
    "MIN": _fn_min,
    "MAX": _fn_max,
    "SUM": _fn_sum,
    "AVG": _fn_avg,
    "MOD": _fn_mod,
    "SIGN": _fn_sign,
    # Text
    "UPPER": lambda args: _text_unary("UPPER", args, str.upper),
    "LOWER": lambda args: _text_unary("LOWER", args, str.lower),
    "TRIM": lambda args: _text_unary("TRIM", args, str.strip),
    "LEN": _fn_len,
    "LEFT": _fn_left,
    "RIGHT": _fn_right,
    "MID": _fn_mid,
    "CONCAT": _fn_concat,
    "REPLACE": _fn_replace,
    "REPT": _fn_rept,
    "CONTAINS": _fn_contains,
    "STARTSWITH": _fn_startswith,
    "ENDSWITH": _fn_endswith,
    "PAD": _fn_pad,
    "PADLEFT": _fn_padleft,
    "CENTER": _fn_center,
    # Conversion / format
    "TEXT": _fn_text,
    "NUM": _fn_num,
    "FIXED": _fn_fixed,
    # Color
    "COLOR": _fn_color,
}


# --- Variable lookup against the template context -------------------------- #


def _lookup_variable(path: str, context: Dict[str, Any]) -> Any:
    """Resolve a dotted path against the context.

    Returns ``ErrorValue('#REF')`` if any segment is missing. Values come
    back in their native Python type (int/float/bool/str) so that the
    evaluator can do numeric comparisons without re-parsing.
    """
    parts = path.split(".")
    if len(parts) < 2:
        return ErrorValue("#REF")

    source = parts[0].lower()
    if source not in context:
        return ErrorValue("#REF")

    value: Any = context[source]
    for part in parts[1:]:
        if isinstance(value, dict):
            if part in value:
                value = value[part]
            elif part.lower() in value:
                value = value[part.lower()]
            else:
                return ErrorValue("#REF")
        elif isinstance(value, list):
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < len(value):
                    value = value[idx]
                else:
                    return ErrorValue("#REF")
            else:
                return ErrorValue("#REF")
        else:
            return ErrorValue("#REF")

    if value is None:
        return ErrorValue("#REF")
    return value


# --- Tree walker ----------------------------------------------------------- #


def _eval_node(node: _Node, context: Dict[str, Any]) -> Any:
    if isinstance(node, _Literal):
        return node.value

    if isinstance(node, _Var):
        return _lookup_variable(node.path, context)

    if isinstance(node, _Unary):
        v = _eval_node(node.operand, context)
        if _is_error(v):
            return v
        if node.op == "NOT":
            return not _to_bool(v)
        if node.op == "-":
            return -_to_number(v)
        if node.op == "+":
            return _to_number(v)
        return ErrorValue("#SYNTAX")

    if isinstance(node, _Binary):
        # Short-circuit logical operators so an error in the unused branch
        # doesn't sink the whole expression.
        if node.op == "AND":
            lv = _eval_node(node.left, context)
            if _is_error(lv):
                return lv
            if not _to_bool(lv):
                return False
            rv = _eval_node(node.right, context)
            if _is_error(rv):
                return rv
            return _to_bool(rv)
        if node.op == "OR":
            lv = _eval_node(node.left, context)
            if _is_error(lv):
                return lv
            if _to_bool(lv):
                return True
            rv = _eval_node(node.right, context)
            if _is_error(rv):
                return rv
            return _to_bool(rv)

        left = _eval_node(node.left, context)
        right = _eval_node(node.right, context)
        err = _propagate(left, right)
        if err is not None:
            return err

        op = node.op
        if op == "&":
            return _to_string(left) + _to_string(right)
        if op in ("+", "-", "*", "/", "%"):
            a = _to_number(left)
            b = _to_number(right)
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                if b == 0:
                    return ErrorValue("#DIV/0")
                return a / b
            if op == "%":
                if b == 0:
                    return ErrorValue("#DIV/0")
                return a % b
        if op in ("==", "!=", "<", ">", "<=", ">="):
            cmp = _compare(left, right)
            return {
                "==": cmp == 0,
                "!=": cmp != 0,
                "<": cmp < 0,
                ">": cmp > 0,
                "<=": cmp <= 0,
                ">=": cmp >= 0,
            }[op]
        return ErrorValue("#SYNTAX")

    if isinstance(node, _Call):
        fn = _BUILTINS.get(node.name)
        if fn is None:
            return ErrorValue("#NAME?")
        # Eagerly evaluate arguments. IF/AND/OR's short-circuiting is
        # implemented at the operator level above and via error propagation;
        # because expressions are pure, eager evaluation is safe semantically.
        try:
            args = [_eval_node(a, context) for a in node.args]
            return fn(args)
        except FormulaError as exc:
            return ErrorValue(exc.code)

    return ErrorValue("#SYNTAX")  # pragma: no cover


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def evaluate(expression: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Parse and evaluate ``expression``, returning a rendered string.

    Parsing or evaluation errors render as their short code (e.g. ``#REF``)
    instead of raising, so a single bad formula never breaks rendering of
    the surrounding template.
    """
    ctx = context or {}
    try:
        tokens = _tokenize(expression)
        tree = _Parser(tokens).parse()
        result = _eval_node(tree, ctx)
    except FormulaError as exc:
        return exc.code
    if _is_error(result):
        return result.code
    return _to_string(result)


# Match ``{{= ... }}`` blocks. Use ``[^}{]*`` for the body, mirroring
# VAR_PATTERN in engine.py (prevents pathological backtracking and means
# ``{`` / ``}`` cannot appear inside an expression -- documented constraint).
# We deliberately do **not** allow optional whitespace between ``{{`` and ``=``
# (i.e. no ``\s*`` before ``=``): combined with the permissive body class it
# would make the regex polynomial w.r.t. inputs like ``{{   `` with no
# closing brace. Whitespace after ``=`` is fine because it's part of the body
# and we strip it before parsing.
_FORMULA_PATTERN = re.compile(r"\{\{=([^}{]*)\}\}")


def render_expressions(template: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Replace every ``{{= ... }}`` formula in ``template`` with its value."""
    if "{{" not in template or "=" not in template:
        return template

    ctx = context or {}

    def _sub(match: "re.Match[str]") -> str:
        body = match.group(1).strip()
        if not body:
            return ""
        return evaluate(body, ctx)

    return _FORMULA_PATTERN.sub(_sub, template)


def list_builtins() -> Tuple[str, ...]:
    """Return a stable, sorted tuple of all built-in formula function names."""
    return tuple(sorted(_BUILTINS.keys()))


__all__ = [
    "ErrorValue",
    "FormulaError",
    "evaluate",
    "render_expressions",
    "list_builtins",
]
