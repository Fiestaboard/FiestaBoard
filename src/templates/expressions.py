"""Inline formula expressions for FiestaBoard templates.

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
      ENDSWITH, PAD, PADLEFT, ZEROPAD, CENTER, TEXT, NUM, FIXED, COLOR.
    * Excel-like error values: ``#REF``, ``#VALUE``, ``#DIV/0``, ``#NAME?``,
      ``#NUM``, ``#SYNTAX`` -- trappable with ``IFERROR``.

This module is intentionally self-contained; the only dependency on the
rest of the template engine is reading variable values from a plain
``dict`` context (the same shape used by ``TemplateEngine``).
"""

from __future__ import annotations

import math
import re
from calendar import monthrange
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any

import regex as _regex

from .colors import COLOR_CODES as _COLOR_CODES
from .colors import is_color_code as _is_color_code

# --------------------------------------------------------------------------- #
# Error model
# --------------------------------------------------------------------------- #


class FormulaError(Exception):
    """Raised internally by the evaluator. ``code`` is the user-visible tag.

    ``pos`` (when set) is the character offset in the source expression
    where the problem was detected. It's surfaced in the rendered tag so
    a user can find it (e.g. ``#SYNTAX:12``) and is also returned by the
    public :func:`validate_expression` helper.
    """

    def __init__(self, code: str, message: str = "", pos: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.pos = pos


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
    "==",
    "!=",
    "<>",
    "<=",
    ">=",
    "&&",
    "||",
    "<",
    ">",
    "=",
    "+",
    "-",
    "*",
    "/",
    "%",
    "&",
    "!",
)


def _tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
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
                raise FormulaError("#SYNTAX", f"Bad number: {text}", pos=start) from exc
            tokens.append(Token(_T_NUMBER, value, start))
            continue

        # String literal: "..." with backslash escapes
        if ch == '"':
            start = i
            i += 1
            buf: list[str] = []
            while i < n and source[i] != '"':
                if source[i] == "\\" and i + 1 < n:
                    nxt = source[i + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(nxt, nxt))
                    i += 2
                else:
                    buf.append(source[i])
                    i += 1
            if i >= n:
                raise FormulaError("#SYNTAX", "Unterminated string literal", pos=start)
            i += 1  # closing quote
            tokens.append(Token(_T_STRING, "".join(buf), start))
            continue

        # Identifier / keyword: letters, digits, underscore, ':' (plugin instance),
        # '.' (dotted paths), and '-' inside plugin instance labels.  We keep
        # dotted paths as a single IDENT.
        #
        # ``-`` is only consumed when sandwiched between two identifier
        # characters (e.g. ``my-cal``).  Free-standing ``-`` -- including
        # ``foo - 1`` and trailing ``foo-`` -- remains a binary/unary minus
        # operator.  This matches how plain ``{{plugin:instance.field}}``
        # substitution treats instance labels with hyphens (issue #969) without
        # breaking arithmetic that doesn't use whitespace.
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n:
                c = source[i]
                if c.isalnum() or c in ("_", ":", "."):
                    i += 1
                    continue
                if c == "-" and i + 1 < n and (source[i + 1].isalnum() or source[i + 1] == "_"):
                    # Lookahead: only treat ``-`` as part of the identifier
                    # when it sits between two identifier characters.
                    i += 1
                    continue
                break
            text = source[start:i]
            # Strip a trailing dot which is almost certainly a typo, leaving
            # it would produce a misleading "Unknown source" error.
            if text.endswith("."):
                raise FormulaError("#SYNTAX", f"Trailing dot in identifier: {text}", pos=start)
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

        raise FormulaError("#SYNTAX", f"Unexpected character {ch!r} at position {i}", pos=i)

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
    args: list[_Node]


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


_CMP_OPS = {"=", "==", "!=", "<>", "<", ">", "<=", ">="}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _accept_op(self, *ops: str) -> str | None:
        tok = self._peek()
        if tok.kind == _T_OP and tok.value in ops:
            self._advance()
            return tok.value
        return None

    def _accept_kw(self, *names: str) -> str | None:
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
                pos=self._peek().pos,
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
                raise FormulaError("#SYNTAX", "Missing closing ')'", pos=close.pos)
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
                args: list[_Node] = []
                if self._peek().kind != _T_RPAREN:
                    args.append(self._parse_or())
                    while self._peek().kind == _T_COMMA:
                        self._advance()
                        args.append(self._parse_or())
                close = self._advance()
                if close.kind != _T_RPAREN:
                    raise FormulaError("#SYNTAX", f"Missing ')' in call to {name}", pos=close.pos)
                return _Call(upper, args)

            # Variable reference
            return _Var(name)

        raise FormulaError(
            "#SYNTAX",
            f"Unexpected token {tok.value!r} at position {tok.pos}",
            pos=tok.pos,
        )


# --------------------------------------------------------------------------- #
# Evaluator
# --------------------------------------------------------------------------- #


_MISSING_SENTINEL = "???"


def _is_error(value: Any) -> bool:
    return isinstance(value, ErrorValue)


def _propagate(*values: Any) -> ErrorValue | None:
    for v in values:
        if _is_error(v):
            return v
    return None


def _to_number(value: Any) -> float:
    """Coerce a value to a number, raising ``#VALUE`` on failure."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
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
    if isinstance(value, int | float):
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
    """Render a value the way the rest of the template engine would.

    Arrays and objects have no sensible board rendering — before they were
    rejected here, ``{{= plugin.games }}`` put a Python repr
    (``[{'team1': 'SF'}]``) on the board. They must go through ``COUNT``,
    ``AT``, ``JOIN`` or ``FOREACH`` instead.
    """
    if isinstance(value, list | dict):
        raise FormulaError(
            "#VALUE",
            "An array cannot be rendered directly — use COUNT, AT, JOIN or FOREACH",
        )
    if isinstance(value, datetime):
        return value.strftime(_DATE_RENDER_FORMAT)
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
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
    if isinstance(value, int | float) and not isinstance(value, bool):
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
    # Two dates compare chronologically, not as text.
    if isinstance(left, datetime) and isinstance(right, datetime):
        a_dt, b_dt = _align_awareness(left, right)
        return (a_dt > b_dt) - (a_dt < b_dt)
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


def _expect_args(name: str, args: list[Any], minimum: int, maximum: int | None = None) -> None:
    if len(args) < minimum:
        raise FormulaError("#VALUE", f"{name}: expected at least {minimum} args, got {len(args)}")
    if maximum is not None and len(args) > maximum:
        raise FormulaError("#VALUE", f"{name}: expected at most {maximum} args, got {len(args)}")


def _fn_if(args: list[Any]) -> Any:
    _expect_args("IF", args, 2, 3)
    cond = args[0]
    err = _propagate(cond)
    if err is not None:
        return err
    return args[1] if _to_bool(cond) else (args[2] if len(args) == 3 else "")


def _fn_ifs(args: list[Any]) -> Any:
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


def _fn_switch(args: list[Any]) -> Any:
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


def _fn_and(args: list[Any]) -> Any:
    if not args:
        return True
    err = _propagate(*args)
    if err is not None:
        return err
    return all(_to_bool(a) for a in args)


def _fn_or(args: list[Any]) -> Any:
    if not args:
        return False
    err = _propagate(*args)
    if err is not None:
        return err
    return any(_to_bool(a) for a in args)


def _fn_not(args: list[Any]) -> Any:
    _expect_args("NOT", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return not _to_bool(args[0])


def _fn_iferror(args: list[Any]) -> Any:
    _expect_args("IFERROR", args, 2, 2)
    return args[1] if _is_error(args[0]) else args[0]


def _fn_iserror(args: list[Any]) -> Any:
    _expect_args("ISERROR", args, 1, 1)
    return _is_error(args[0])


def _fn_isblank(args: list[Any]) -> Any:
    _expect_args("ISBLANK", args, 1, 1)
    v = args[0]
    if _is_error(v):
        return v
    if v is None:
        return True
    if isinstance(v, str):
        return v == "" or v == _MISSING_SENTINEL
    return False


def _fn_default(args: list[Any]) -> Any:
    _expect_args("DEFAULT", args, 2, 2)
    v = args[0]
    if _is_error(v):
        return args[1]
    if v is None or (isinstance(v, str) and (v == "" or v == _MISSING_SENTINEL)):
        return args[1]
    return v


def _fn_coalesce(args: list[Any]) -> Any:
    """Return the first argument that isn't an error / NULL / blank.

    Mirrors SQL's COALESCE and is the n-ary form of DEFAULT. Falls
    through silently on errors so a chain of fallbacks "just works".
    """
    if not args:
        raise FormulaError("#VALUE", "COALESCE: expected at least 1 arg(s), got 0")
    last = args[-1]
    for v in args:
        if _is_error(v):
            continue
        if v is None:
            continue
        if isinstance(v, str) and (v == "" or v == _MISSING_SENTINEL):
            continue
        return v
    # Nothing usable; return the last value as-is so the user sees the
    # final fallback (which may itself be a literal string they chose).
    return last


# Math
def _math_unary(name: str, fn: Callable[[float], float]) -> Callable[[list[Any]], Any]:
    def impl(args: list[Any]) -> Any:
        _expect_args(name, args, 1, 1)
        err = _propagate(args[0])
        if err is not None:
            return err
        return fn(_to_number(args[0]))

    return impl


def _fn_round(args: list[Any]) -> Any:
    _expect_args("ROUND", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    x = _to_number(args[0])
    n = int(_to_number(args[1])) if len(args) == 2 else 0
    return round(x, n)


def _fn_roundup(args: list[Any]) -> Any:
    """Round away from zero to ``n`` decimals (Excel's ROUNDUP)."""
    _expect_args("ROUNDUP", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    x = _to_number(args[0])
    n = int(_to_number(args[1])) if len(args) == 2 else 0
    multiplier = 10**n
    if x >= 0:
        return math.ceil(x * multiplier) / multiplier
    return math.floor(x * multiplier) / multiplier


def _fn_rounddown(args: list[Any]) -> Any:
    """Round toward zero to ``n`` decimals (Excel's ROUNDDOWN)."""
    _expect_args("ROUNDDOWN", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    x = _to_number(args[0])
    n = int(_to_number(args[1])) if len(args) == 2 else 0
    multiplier = 10**n
    if x >= 0:
        return math.floor(x * multiplier) / multiplier
    return math.ceil(x * multiplier) / multiplier


def _fn_power(args: list[Any]) -> Any:
    _expect_args("POWER", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    base = _to_number(args[0])
    exp = _to_number(args[1])
    try:
        result = math.pow(base, exp)
    except (ValueError, OverflowError):
        return ErrorValue("#NUM")
    if math.isnan(result) or math.isinf(result):
        return ErrorValue("#NUM")
    return result


def _fn_sqrt(args: list[Any]) -> Any:
    _expect_args("SQRT", args, 1, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    x = _to_number(args[0])
    if x < 0:
        return ErrorValue("#NUM")
    return math.sqrt(x)


def _fn_min(args: list[Any]) -> Any:
    _expect_args("MIN", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return min(_to_number(a) for a in args)


def _fn_max(args: list[Any]) -> Any:
    _expect_args("MAX", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return max(_to_number(a) for a in args)


def _fn_sum(args: list[Any]) -> Any:
    _expect_args("SUM", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return sum(_to_number(a) for a in args)


def _fn_avg(args: list[Any]) -> Any:
    _expect_args("AVG", args, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    nums = [_to_number(a) for a in args]
    return sum(nums) / len(nums)


def _fn_mod(args: list[Any]) -> Any:
    _expect_args("MOD", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    b = _to_number(args[1])
    if b == 0:
        return ErrorValue("#DIV/0")
    return _to_number(args[0]) % b


def _fn_sign(args: list[Any]) -> Any:
    _expect_args("SIGN", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    v = _to_number(args[0])
    return -1 if v < 0 else (1 if v > 0 else 0)


# Text
def _fn_concat(args: list[Any]) -> Any:
    err = _propagate(*args)
    if err is not None:
        return err
    return "".join(_to_string(a) for a in args)


def _fn_len(args: list[Any]) -> Any:
    _expect_args("LEN", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return len(_to_string(args[0]))


def _fn_left(args: list[Any]) -> Any:
    _expect_args("LEFT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1]))
    if n < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0])[:n]


def _fn_right(args: list[Any]) -> Any:
    _expect_args("RIGHT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1]))
    if n < 0:
        return ErrorValue("#VALUE")
    s = _to_string(args[0])
    return s[-n:] if n > 0 else ""


def _fn_mid(args: list[Any]) -> Any:
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


def _fn_replace(args: list[Any]) -> Any:
    _expect_args("REPLACE", args, 3, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).replace(_to_string(args[1]), _to_string(args[2]))


def _fn_proper(args: list[Any]) -> Any:
    """Title-case (capitalize the first letter of every word).

    Similar to Excel's PROPER but with a friendlier treatment of intra-word
    apostrophes: ``"don't stop"`` becomes ``"Don't Stop"``, not
    ``"Don'T Stop"`` (which is what both Excel and Python's ``str.title()``
    produce). Boards are short -- the prettier rendering wins here.
    """
    _expect_args("PROPER", args, 1, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    s = _to_string(args[0])
    out: list[str] = []
    prev_in_word = False
    for ch in s:
        if ch.isalpha():
            out.append(ch.lower() if prev_in_word else ch.upper())
            prev_in_word = True
        elif ch == "'":
            # Apostrophe stays inside a word so the next letter isn't
            # re-capitalised. Standalone leading quotes are rare enough
            # that we accept the trade-off.
            out.append(ch)
            # prev_in_word unchanged
        else:
            out.append(ch)
            prev_in_word = False
    return "".join(out)


def _fn_find(args: list[Any]) -> Any:
    """Case-sensitive substring search. 1-indexed like Excel; ``#VALUE`` if not found."""
    _expect_args("FIND", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    needle = _to_string(args[0])
    haystack = _to_string(args[1])
    start = int(_to_number(args[2])) - 1 if len(args) == 3 else 0
    if start < 0:
        start = 0
    idx = haystack.find(needle, start)
    if idx < 0:
        return ErrorValue("#VALUE")
    return idx + 1  # 1-indexed


def _fn_search(args: list[Any]) -> Any:
    """Case-insensitive version of FIND. Returns 0 if not found (template-friendly)."""
    _expect_args("SEARCH", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    needle = _to_string(args[0]).lower()
    haystack = _to_string(args[1]).lower()
    start = int(_to_number(args[2])) - 1 if len(args) == 3 else 0
    if start < 0:
        start = 0
    idx = haystack.find(needle, start)
    if idx < 0:
        return 0  # 0 means "not found", easy to test with `> 0`
    return idx + 1


def _fn_rept(args: list[Any]) -> Any:
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


def _fn_contains(args: list[Any]) -> Any:
    _expect_args("CONTAINS", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[1]) in _to_string(args[0])


def _fn_startswith(args: list[Any]) -> Any:
    _expect_args("STARTSWITH", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).startswith(_to_string(args[1]))


def _fn_endswith(args: list[Any]) -> Any:
    _expect_args("ENDSWITH", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _to_string(args[0]).endswith(_to_string(args[1]))


def _fn_pad(args: list[Any]) -> Any:
    _expect_args("PAD", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0]).ljust(width)[:width]


def _fn_padleft(args: list[Any]) -> Any:
    _expect_args("PADLEFT", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    s = _to_string(args[0])
    return s.rjust(width) if len(s) <= width else s[-width:]


def _fn_zeropad(args: list[Any]) -> Any:
    _expect_args("ZEROPAD", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width <= 0:
        return _to_string(args[0])
    s = _to_string(args[0])
    if s.startswith("-"):
        return "-" + s[1:].rjust(width - 1, "0")
    return s.rjust(width, "0")


def _fn_center(args: list[Any]) -> Any:
    _expect_args("CENTER", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    width = int(_to_number(args[1]))
    if width < 0:
        return ErrorValue("#VALUE")
    return _to_string(args[0]).center(width)[:width]


def _fn_text(args: list[Any]) -> Any:
    _expect_args("TEXT", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return _to_string(args[0])


def _fn_num(args: list[Any]) -> Any:
    _expect_args("NUM", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return _to_number(args[0])


def _fn_fixed(args: list[Any]) -> Any:
    _expect_args("FIXED", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    n = int(_to_number(args[1])) if len(args) == 2 else 2
    if n < 0:
        n = 0
    return f"{_to_number(args[0]):.{n}f}"


def _text_unary(name: str, args: list[Any], fn: Callable[[str], str]) -> Any:
    _expect_args(name, args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    return fn(_to_string(args[0]))


def _fn_color(args: list[Any]) -> Any:
    _expect_args("COLOR", args, 1, 1)
    err = _propagate(args[0])
    if err is not None:
        return err
    raw = args[0]
    if isinstance(raw, int | float) and not isinstance(raw, bool):
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
    if not _is_color_code(code):
        return ErrorValue("#VALUE")
    # Single-brace marker matches the format produced by ``_normalize_colors``.
    return f"{{{code}}}"


def _math_floor(x: float) -> float:
    """Round toward negative infinity. Wraps ``math.floor`` to keep the
    return type a ``float`` (matches the rest of the math built-ins)."""
    return float(math.floor(x))


def _math_ceil(x: float) -> float:
    """Round toward positive infinity. Wraps ``math.ceil`` for a ``float``
    return type."""
    return float(math.ceil(x))


# --------------------------------------------------------------------------- #
# Text splitting and regular expressions
#
# Plugins expose composite strings ("72F / Sunny") that a template had no way
# to take apart. SPLIT returns an array, so it composes with the array
# functions below.
#
# The regex trio accepts a user-written pattern, and a template render drives
# hardware on a loop -- a pattern that backtracks catastrophically would stall
# that loop forever.
#
# This used to be defended with a blacklist of dangerous pattern *shapes*.
# That approach is unsound and was repeatedly proved so: refusing a nested
# quantifier (``(a+)+b``) missed the alternation forms (``(a|a)+b``); refusing
# any quantified group missed nesting (``((a)|(a))*$``) and the shapes with no
# group at all (``a*a*a*a*a*a*a*a*a*b``). Each widening also refused more
# legitimate patterns, and none of them could ever be a proof -- the next
# unenumerated shape still hung the board.
#
# So the bound is now on the WORK, not the pattern: ``regex`` (unlike the
# stdlib ``re``) accepts ``timeout=``, and abandons a match that exceeds it.
# Any pattern at all is allowed to compile; one that cannot finish in
# ``_MATCH_TIMEOUT_SECONDS`` yields ``#VALUE`` instead of running forever.
# ``regex`` is a superset of ``re``, so every pattern that worked still does.
# --------------------------------------------------------------------------- #


_MAX_PATTERN_LENGTH = 120

#: Wall-clock a single user regex may spend before it is abandoned. A render
#: may run several (``FOREACH`` evaluates its row expression per item), so this
#: is deliberately far below a render's budget rather than a comfortable slice
#: of it. Nothing legitimate comes close: the patterns a board needs finish in
#: microseconds.
_MATCH_TIMEOUT_SECONDS = 0.1


@lru_cache(maxsize=128)
def _compile_user_pattern(pattern: str) -> _regex.Pattern[str]:
    """Compile a user-supplied regex. Only the length is judged up front."""
    if len(pattern) > _MAX_PATTERN_LENGTH:
        raise FormulaError("#VALUE", f"pattern longer than {_MAX_PATTERN_LENGTH} characters")
    try:
        return _regex.compile(pattern)
    except _regex.error as exc:
        raise FormulaError("#VALUE", f"invalid pattern: {exc}") from exc


def _search_bounded(pattern: _regex.Pattern[str], text: str) -> Any:
    """``pattern.search(text)``, abandoned if it backtracks past the budget."""
    try:
        return pattern.search(text, timeout=_MATCH_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise FormulaError("#VALUE", f"pattern took longer than {_MATCH_TIMEOUT_SECONDS}s to match") from exc


def _sub_bounded(pattern: _regex.Pattern[str], replacement: str, text: str) -> str:
    """``pattern.sub(...)``, abandoned if it backtracks past the budget."""
    try:
        return pattern.sub(replacement, text, timeout=_MATCH_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise FormulaError("#VALUE", f"pattern took longer than {_MATCH_TIMEOUT_SECONDS}s to match") from exc


def _fn_split(args: list[Any]) -> Any:
    """``SPLIT(text[, separator])`` — an array of pieces.

    With no separator, splits on runs of whitespace (the common case for a
    plugin string like ``"72F / Sunny"``).
    """
    _expect_args("SPLIT", args, 1, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    text = _to_string(args[0])
    if len(args) == 1:
        return text.split()
    separator = _to_string(args[1])
    if separator == "":
        return list(text)
    return text.split(separator)


def _fn_regexmatch(args: list[Any]) -> Any:
    _expect_args("REGEXMATCH", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    return _search_bounded(_compile_user_pattern(_to_string(args[1])), _to_string(args[0])) is not None


def _fn_regexextract(args: list[Any]) -> Any:
    """``REGEXEXTRACT(text, pattern[, group])`` — blank when nothing matches."""
    _expect_args("REGEXEXTRACT", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    match = _search_bounded(_compile_user_pattern(_to_string(args[1])), _to_string(args[0]))
    if match is None:
        return ""
    group = int(_to_number(args[2])) if len(args) == 3 else 0
    try:
        return match.group(group) or ""
    except IndexError as exc:
        raise FormulaError("#VALUE", f"REGEXEXTRACT: no capture group {group}") from exc


def _fn_regexreplace(args: list[Any]) -> Any:
    _expect_args("REGEXREPLACE", args, 3, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    pattern = _compile_user_pattern(_to_string(args[1]))
    return _sub_bounded(pattern, _to_string(args[2]).replace("\\", "\\\\"), _to_string(args[0]))


# --------------------------------------------------------------------------- #
# Dates and times
#
# The language had no date support, so "days until launch" or "after 5pm?"
# needed a purpose-built plugin no matter what data was already on the board.
#
# Dates are ``datetime`` values inside an expression and render as
# ``YYYY-MM-DD HH:MM``; ``FORMATDATE`` exists for anything else. "Now" comes
# from the context key ``__now__`` when the caller provides one (the engine
# does, so every formula in one render sees the same instant and tests can
# pin the clock) and otherwise from the app's configured-timezone clock.
# --------------------------------------------------------------------------- #


#: Reserved context key holding the instant this render started. Public so the
#: engine (and tests) can pin the clock without reaching into a private name.
RENDER_CLOCK_KEY = "__now__"

_NOW_KEY = RENDER_CLOCK_KEY

_DATE_RENDER_FORMAT = "%Y-%m-%d %H:%M"

#: ``DATEDIFF``/``DATEADD`` units. Months are handled separately (calendar
#: arithmetic, not a fixed number of seconds).
_DATE_UNIT_SECONDS: dict[str, float] = {
    "seconds": 1.0,
    "minutes": 60.0,
    "hours": 3600.0,
    "days": 86400.0,
    "weeks": 604800.0,
}

_MONTH_ABBR = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_WEEKDAY_ABBR = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _current_datetime(context: dict[str, Any]) -> datetime:
    """The instant to treat as "now".

    Prefers the caller-supplied ``__now__`` so a whole render shares one
    instant. Falls back to the app's time service (configured timezone), and
    to naive local time if that is unavailable — a bare ``NOW()`` must never
    fail just because configuration could not be read.
    """
    injected = context.get(_NOW_KEY)
    if isinstance(injected, datetime):
        return injected
    try:
        from src.time_service import get_time_service

        return get_time_service().get_current_time()
    except Exception:  # pragma: no cover - configuration/import failure
        return datetime.now()


def ensure_render_clock(context: dict[str, Any]) -> dict[str, Any]:
    """Return a context pinned to a single instant for the whole render.

    Without this, every ``NOW()``/``TODAY()`` in a board resolves the clock
    on its own, so two lines of one render can straddle a minute — or a
    midnight — boundary.

    Never mutates the argument: callers hand in the shared plugin context.
    A context that already carries the key is returned unchanged, so an
    outer render that pinned the clock wins and nested renders inherit it.
    """
    if RENDER_CLOCK_KEY in context:
        return context
    return {**context, RENDER_CLOCK_KEY: _current_datetime({})}


def _coerce_date(name: str, value: Any) -> datetime:
    """Coerce a value to a ``datetime`` or raise ``#VALUE``.

    Accepts a ``datetime`` unchanged, a ``date``, and the ISO-8601 strings
    plugins actually expose (``2026-12-25``, ``2026-12-25T08:15:00``, with or
    without a trailing ``Z``).
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                pass
    raise FormulaError("#VALUE", f"{name}: {value!r} is not a date")


def _date_unit(name: str, args: list[Any], index: int, default: str = "days") -> str:
    unit = (_to_string(args[index]).strip().lower() if len(args) > index else default) or default
    if not unit.endswith("s"):
        unit += "s"
    if unit != "months" and unit not in _DATE_UNIT_SECONDS:
        raise FormulaError("#VALUE", f"{name}: unknown unit {unit!r}")
    return unit


def _add_months(moment: datetime, count: int) -> datetime:
    """Shift by calendar months, clamping to the last valid day.

    ``2026-01-31 + 1 month`` is ``2026-02-28``: the alternative (rolling into
    March) surprises everyone who has ever written a monthly countdown.
    """
    total = moment.month - 1 + count
    year = moment.year + total // 12
    month = total % 12 + 1
    day = min(moment.day, monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _fn_date(args: list[Any]) -> Any:
    _expect_args("DATE", args, 1, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return _coerce_date("DATE", args[0])


def _date_part(name: str, extract: Callable[[datetime], int]) -> Callable[[list[Any]], Any]:
    """Build ``YEAR``/``MONTH``/``DAY``/``HOUR``/``MINUTE``/``WEEKDAY``."""

    def _fn(args: list[Any]) -> Any:
        _expect_args(name, args, 1, 1)
        err = _propagate(*args)
        if err is not None:
            return err
        return float(extract(_coerce_date(name, args[0])))

    return _fn


def _fn_datediff(args: list[Any]) -> Any:
    _expect_args("DATEDIFF", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    start = _coerce_date("DATEDIFF", args[0])
    end = _coerce_date("DATEDIFF", args[1])
    unit = _date_unit("DATEDIFF", args, 2)
    if unit == "months":
        months = (end.year - start.year) * 12 + (end.month - start.month)
        if end.day < start.day:
            months -= 1
        return float(months)
    start, end = _align_awareness(start, end)
    delta = (end - start).total_seconds() / _DATE_UNIT_SECONDS[unit]
    # Truncate toward zero: 1.9 days until a deadline is "1 day" left, and a
    # deadline 1.9 days past is "-1".
    return float(int(delta))


def _align_awareness(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    """Make two datetimes safe to subtract.

    Plugin data mixes naive strings (``2026-12-25``) with aware ones
    (``...+00:00``); subtracting across that raises in Python. The naive side
    is assumed to be in the aware side's zone, which is what a user writing
    ``DATEDIFF(TODAY(), DATE(plugin.when))`` means.
    """
    if (a.tzinfo is None) == (b.tzinfo is None):
        return a, b
    if a.tzinfo is None:
        return a.replace(tzinfo=b.tzinfo), b
    return a, b.replace(tzinfo=a.tzinfo)


def _fn_dateadd(args: list[Any]) -> Any:
    _expect_args("DATEADD", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    moment = _coerce_date("DATEADD", args[0])
    amount = _to_number(args[1])
    unit = _date_unit("DATEADD", args, 2)
    if unit == "months":
        return _add_months(moment, int(amount))
    return moment + timedelta(seconds=amount * _DATE_UNIT_SECONDS[unit])


def _fn_formatdate(args: list[Any]) -> Any:
    """``FORMATDATE(date, pattern)`` with board-friendly tokens.

    Deliberately not ``strftime``: ``%`` patterns are a poor fit for a
    spreadsheet-shaped language, and the token set below is what a board
    actually needs. Longest tokens match first so ``MMM`` beats ``MM``.
    """
    _expect_args("FORMATDATE", args, 2, 2)
    err = _propagate(*args)
    if err is not None:
        return err
    moment = _coerce_date("FORMATDATE", args[0])
    pattern = _to_string(args[1])

    hour12 = moment.hour % 12 or 12
    tokens: list[tuple[str, str]] = [
        ("YYYY", f"{moment.year:04d}"),
        ("YY", f"{moment.year % 100:02d}"),
        ("MMM", _MONTH_ABBR[moment.month - 1]),
        ("MM", f"{moment.month:02d}"),
        ("DD", f"{moment.day:02d}"),
        ("ddd", _WEEKDAY_ABBR[moment.weekday()]),
        ("HH", f"{moment.hour:02d}"),
        ("hh", str(hour12)),
        ("mm", f"{moment.minute:02d}"),
        ("ss", f"{moment.second:02d}"),
        ("AP", "AM" if moment.hour < 12 else "PM"),
    ]

    out: list[str] = []
    i = 0
    while i < len(pattern):
        for token, replacement in tokens:
            if pattern.startswith(token, i):
                out.append(replacement)
                i += len(token)
                break
        else:
            out.append(pattern[i])
            i += 1
    return "".join(out)


def _lazy_now(nodes: list[_Node], context: dict[str, Any]) -> Any:
    """``NOW()`` — needs the context, so it is registered as a lazy builtin."""
    if nodes:
        raise FormulaError("#VALUE", "NOW: expected no arguments")
    return _current_datetime(context)


def _lazy_today(nodes: list[_Node], context: dict[str, Any]) -> Any:
    """``TODAY()`` — local midnight of the current day."""
    if nodes:
        raise FormulaError("#VALUE", "TODAY: expected no arguments")
    return _current_datetime(context).replace(hour=0, minute=0, second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Arrays / collections (issue #2050)
#
# Plugins declare arrays in their manifest (``variables.arrays``) and a template
# could only ever index one item at a time, with no way to ask how many items
# existed. Authors hand-unrolled a line per possible item and wrapped each in an
# ``IF`` to hide the ``???`` from indexes that weren't there.
#
# Arrays are real values inside an expression — they can be passed between
# functions — but they cannot be rendered (see ``_to_string``). ``FOREACH``
# turns one into text: newline-joined rows, which ``TemplateEngine.render_lines``
# already spills down the board the same way ``|wrap`` overflow does.
# --------------------------------------------------------------------------- #


#: Reserved context key holding the loop locals (``item``, ``index``).
_LOCALS_KEY = "__locals__"

#: Names that resolve as loop locals rather than plugin sources. Used by
#: ``validate_expression`` so an editor doesn't flag ``item.team1`` as an
#: unknown plugin.
LOOP_LOCAL_NAMES = frozenset({"item", "index"})


def _require_array(name: str, value: Any) -> list[Any]:
    """Coerce ``value`` to a list or raise ``#VALUE``."""
    if isinstance(value, list):
        return value
    raise FormulaError("#VALUE", f"{name}: expected an array, got {type(value).__name__}")


def _item_field(item: Any, field: str | None) -> Any:
    """Read ``field`` from one array item.

    Items are usually dicts (``{"team1": "SF"}``); a plugin may also expose a
    plain list of scalars, in which case the field is omitted and the item
    itself is the value. A missing field is blank rather than an error so the
    hand-unrolled pattern this replaces doesn't need an ``IF`` per line.
    """
    if not field:
        return "" if isinstance(item, dict | list) else item
    if isinstance(item, dict):
        if field in item:
            return item[field]
        return item.get(field.lower(), "")
    return ""


def _child_context(context: dict[str, Any], item: Any, index: int) -> dict[str, Any]:
    """A context with ``item``/``index`` bound for one iteration.

    ``index`` is 1-based (it is shown to users, e.g. ``index & ". " & item.name``)
    and is also injected into dict items as ``item.index``. An item's own
    ``index`` field wins, so a plugin that exposes one keeps its meaning.
    """
    inner = dict(context.get(_LOCALS_KEY) or {})
    inner["item"] = {"index": index, **item} if isinstance(item, dict) else item
    inner["index"] = index
    return {**context, _LOCALS_KEY: inner}


def _sort_key(value: Any) -> tuple[int, float, str]:
    """Order numerically when possible, lexically otherwise.

    Returns a tuple so mixed arrays can't raise: numbers sort before strings.
    """
    if isinstance(value, bool):
        return (0, 1.0 if value else 0.0, "")
    if isinstance(value, int | float):
        return (0, float(value), "")
    text = _to_string(value) if not isinstance(value, list | dict) else ""
    try:
        return (0, float(text.strip()), "")
    except (ValueError, AttributeError):
        return (1, 0.0, text.lower())


def _fn_count(args: list[Any]) -> Any:
    _expect_args("COUNT", args, 1, 1)
    err = _propagate(*args)
    if err is not None:
        return err
    return len(_require_array("COUNT", args[0]))


def _fn_at(args: list[Any]) -> Any:
    _expect_args("AT", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    items = _require_array("AT", args[0])
    index = int(_to_number(args[1]))
    if index < 0 or index >= len(items):
        return ""
    field = _to_string(args[2]) if len(args) == 3 else None
    return _item_field(items[index], field)


def _fn_sort(args: list[Any]) -> Any:
    _expect_args("SORT", args, 1, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    items = _require_array("SORT", args[0])
    field = _to_string(args[1]) if len(args) >= 2 else ""
    descending = len(args) >= 3 and _to_string(args[2]).strip().lower() in ("desc", "descending", "-1")
    return sorted(items, key=lambda it: _sort_key(_item_field(it, field or None)), reverse=descending)


def _fn_slice(args: list[Any]) -> Any:
    _expect_args("SLICE", args, 2, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    items = _require_array("SLICE", args[0])
    start = max(0, int(_to_number(args[1])))
    if len(args) == 3:
        count = int(_to_number(args[2]))
        if count <= 0:
            return []
        return items[start : start + count]
    return items[start:]


def _fn_join(args: list[Any]) -> Any:
    _expect_args("JOIN", args, 1, 3)
    err = _propagate(*args)
    if err is not None:
        return err
    items = _require_array("JOIN", args[0])
    sep = _to_string(args[1]) if len(args) >= 2 else ""
    field = _to_string(args[2]) if len(args) == 3 else None
    return sep.join(_to_string(_item_field(it, field)) for it in items)


def _aggregate(name: str, reducer: Callable[[list[float]], float]) -> Callable[[list[Any]], Any]:
    """Build ``SUMOF``/``AVGOF``/``MINOF``/``MAXOF`` over one field of an array."""

    def _fn(args: list[Any]) -> Any:
        _expect_args(name, args, 1, 2)
        err = _propagate(*args)
        if err is not None:
            return err
        items = _require_array(name, args[0])
        field = _to_string(args[1]) if len(args) == 2 else None
        numbers = [_to_number(_item_field(it, field)) for it in items]
        if not numbers:
            return 0.0
        return reducer(numbers)

    return _fn


def _lazy_foreach(nodes: list[_Node], context: dict[str, Any]) -> Any:
    """``FOREACH(array, rowExpr[, limit])`` — one rendered row per item.

    ``rowExpr`` is evaluated once per item with ``item`` bound, which is why
    this is a lazy builtin: its second argument must not be evaluated in the
    caller's context (there is no ``item`` there).
    """
    if not 2 <= len(nodes) <= 3:
        raise FormulaError("#VALUE", f"FOREACH: expected 2-3 args, got {len(nodes)}")

    array = _eval_node(nodes[0], context)
    if _is_error(array):
        return array
    items = _require_array("FOREACH", array)

    limit: int | None = None
    if len(nodes) == 3:
        limit_value = _eval_node(nodes[2], context)
        if _is_error(limit_value):
            return limit_value
        limit = int(_to_number(limit_value))
        if limit <= 0:
            return ""

    rows: list[str] = []
    for i, item in enumerate(items):
        if limit is not None and i >= limit:
            break
        row = _eval_node(nodes[1], _child_context(context, item, i + 1))
        if _is_error(row):
            return row
        rows.append(_to_string(row))
    return "\n".join(rows)


def _lazy_filter(nodes: list[_Node], context: dict[str, Any]) -> Any:
    """``FILTER(array, condition)`` — the items whose condition is truthy.

    Lazy for the same reason as ``FOREACH``: the condition reads ``item``.
    Returns an array, so it composes (``COUNT(FILTER(...))``).
    """
    if len(nodes) != 2:
        raise FormulaError("#VALUE", f"FILTER: expected 2 args, got {len(nodes)}")

    array = _eval_node(nodes[0], context)
    if _is_error(array):
        return array
    items = _require_array("FILTER", array)

    kept: list[Any] = []
    for i, item in enumerate(items):
        verdict = _eval_node(nodes[1], _child_context(context, item, i + 1))
        if _is_error(verdict):
            return verdict
        if _to_bool(verdict):
            kept.append(item)
    return kept


def _lazy_let(nodes: list[_Node], context: dict[str, Any]) -> Any:
    """``LET(name, value, ..., body)`` — name a subexpression and reuse it.

    Lazy because the bound names only exist while the body runs, and because
    each value expression may refer to names bound before it. Bindings live in
    the same reserved locals map as ``item``, so they disappear with the body
    (``IFERROR(t, ...)`` outside a ``LET`` still sees ``#REF``).
    """
    if len(nodes) < 3 or len(nodes) % 2 == 0:
        raise FormulaError("#VALUE", "LET: expected name/value pairs followed by one body expression")

    scope = dict(context.get(_LOCALS_KEY) or {})
    working = {**context, _LOCALS_KEY: scope}

    for i in range(0, len(nodes) - 1, 2):
        name_node = nodes[i]
        if not isinstance(name_node, _Var) or "." in name_node.path:
            raise FormulaError("#VALUE", "LET: binding names must be bare identifiers")
        value = _eval_node(nodes[i + 1], working)
        if _is_error(value):
            return value
        scope[name_node.path.lower()] = value
        working = {**context, _LOCALS_KEY: scope}

    return _eval_node(nodes[-1], working)


#: Builtins that receive their *unevaluated* argument nodes plus the context,
#: because they bind names (``item``) that only exist while they run.
_LAZY_BUILTINS: dict[str, Callable[[list[_Node], dict[str, Any]], Any]] = {
    "FOREACH": _lazy_foreach,
    "FILTER": _lazy_filter,
    "LET": _lazy_let,
    "NOW": _lazy_now,
    "TODAY": _lazy_today,
}


_BUILTINS: dict[str, Callable[[list[Any]], Any]] = {
    # Dates
    "DATE": _fn_date,
    "YEAR": _date_part("YEAR", lambda d: d.year),
    "MONTH": _date_part("MONTH", lambda d: d.month),
    "DAY": _date_part("DAY", lambda d: d.day),
    "HOUR": _date_part("HOUR", lambda d: d.hour),
    "MINUTE": _date_part("MINUTE", lambda d: d.minute),
    "WEEKDAY": _date_part("WEEKDAY", lambda d: d.isoweekday()),
    "DATEDIFF": _fn_datediff,
    "DATEADD": _fn_dateadd,
    "FORMATDATE": _fn_formatdate,
    # Arrays
    "COUNT": _fn_count,
    "AT": _fn_at,
    "SORT": _fn_sort,
    "SLICE": _fn_slice,
    "JOIN": _fn_join,
    "SUMOF": _aggregate("SUMOF", lambda ns: math.fsum(ns)),
    "AVGOF": _aggregate("AVGOF", lambda ns: math.fsum(ns) / len(ns)),
    "MINOF": _aggregate("MINOF", min),
    "MAXOF": _aggregate("MAXOF", max),
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
    "COALESCE": _fn_coalesce,
    # Math
    "ABS": _math_unary("ABS", abs),
    "FLOOR": _math_unary("FLOOR", _math_floor),
    "CEIL": _math_unary("CEIL", _math_ceil),
    "INT": _math_unary("INT", lambda x: float(int(x))),
    "ROUND": _fn_round,
    "ROUNDUP": _fn_roundup,
    "ROUNDDOWN": _fn_rounddown,
    "POWER": _fn_power,
    "SQRT": _fn_sqrt,
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
    "PROPER": _fn_proper,
    "LEN": _fn_len,
    "LEFT": _fn_left,
    "RIGHT": _fn_right,
    "MID": _fn_mid,
    "FIND": _fn_find,
    "SEARCH": _fn_search,
    "CONCAT": _fn_concat,
    "REPLACE": _fn_replace,
    "REPT": _fn_rept,
    "CONTAINS": _fn_contains,
    "STARTSWITH": _fn_startswith,
    "ENDSWITH": _fn_endswith,
    "PAD": _fn_pad,
    "PADLEFT": _fn_padleft,
    "ZEROPAD": _fn_zeropad,
    "CENTER": _fn_center,
    "SPLIT": _fn_split,
    "REGEXMATCH": _fn_regexmatch,
    "REGEXEXTRACT": _fn_regexextract,
    "REGEXREPLACE": _fn_regexreplace,
    # Conversion / format
    "TEXT": _fn_text,
    "NUM": _fn_num,
    "FIXED": _fn_fixed,
    # Color
    "COLOR": _fn_color,
}


# --- Function metadata for editor autocomplete & help --------------------- #
#
# Each entry: (category, signature, summary). Kept here so the page editor
# can render a function picker without any further introspection. The shape
# is intentionally simple and stable; it is part of the public API surface.

_SIGNATURES: dict[str, tuple[str, str, str]] = {
    # Dates
    "NOW": ("date", "NOW()", "Current date and time, board timezone"),
    "TODAY": ("date", "TODAY()", "Midnight today, board timezone"),
    "DATE": ("date", "DATE(text)", "Parse an ISO date/datetime string"),
    "YEAR": ("date", "YEAR(d)", "Year number"),
    "MONTH": ("date", "MONTH(d)", "Month number, 1-12"),
    "DAY": ("date", "DAY(d)", "Day of month"),
    "HOUR": ("date", "HOUR(d)", "Hour, 0-23"),
    "MINUTE": ("date", "MINUTE(d)", "Minute, 0-59"),
    "WEEKDAY": ("date", "WEEKDAY(d)", "Day of week, Monday=1 to Sunday=7"),
    "DATEDIFF": ("date", "DATEDIFF(start, end[, unit])", "Whole units from start to end (default days)"),
    "DATEADD": ("date", "DATEADD(d, amount[, unit])", "Shift a date; negative amounts go back"),
    "FORMATDATE": ("date", 'FORMATDATE(d, "MMM DD")', "Format with YYYY YY MMM MM DD ddd HH hh mm ss AP"),
    # Arrays
    "COUNT": ("array", "COUNT(array)", "How many items an array holds"),
    "AT": ("array", "AT(array, index[, field])", "Item field by 0-based index; blank if absent"),
    "FOREACH": ("array", "FOREACH(array, rowExpr[, limit])", "One board row per item; rowExpr may use item"),
    "FILTER": ("array", "FILTER(array, condition)", "Items whose condition is true (uses item)"),
    "SORT": ("array", 'SORT(array[, field][, "desc"])', "Array sorted by a field"),
    "SLICE": ("array", "SLICE(array, start[, count])", "A window of an array"),
    "JOIN": ("array", "JOIN(array, sep[, field])", "Join items into one line of text"),
    "SUMOF": ("array", "SUMOF(array[, field])", "Sum a field across items"),
    "AVGOF": ("array", "AVGOF(array[, field])", "Average a field across items"),
    "MINOF": ("array", "MINOF(array[, field])", "Smallest value of a field"),
    "MAXOF": ("array", "MAXOF(array[, field])", "Largest value of a field"),
    # Logic
    "LET": ("logic", "LET(name, value, ..., body)", "Name a value once and reuse it in body"),
    "IF": ("logic", "IF(cond, then[, else])", "Conditional value"),
    "IFS": ("logic", "IFS(c1, v1, c2, v2, ...[, def])", "First matching condition's value"),
    "SWITCH": ("logic", "SWITCH(x, m1, r1, ...[, def])", "Match value against options"),
    "AND": ("logic", "AND(a, b, ...)", "True if all args truthy (short-circuit)"),
    "OR": ("logic", "OR(a, b, ...)", "True if any arg truthy (short-circuit)"),
    "NOT": ("logic", "NOT(x)", "Logical negation"),
    "IFERROR": ("logic", "IFERROR(expr, fallback)", "Replace error result with fallback"),
    "ISERROR": ("logic", "ISERROR(expr)", "True if expr evaluated to an error"),
    "ISBLANK": ("logic", "ISBLANK(expr)", "True if expr is null/empty/missing"),
    "DEFAULT": ("logic", "DEFAULT(expr, fallback)", "Fallback for error/null/blank"),
    "COALESCE": ("logic", "COALESCE(a, b, c, ...)", "First non-error/non-blank value"),
    # Math
    "ABS": ("math", "ABS(x)", "Absolute value"),
    "FLOOR": ("math", "FLOOR(x)", "Round toward -infinity"),
    "CEIL": ("math", "CEIL(x)", "Round toward +infinity"),
    "INT": ("math", "INT(x)", "Truncate toward zero"),
    "ROUND": ("math", "ROUND(x[, n])", "Round to n decimals"),
    "ROUNDUP": ("math", "ROUNDUP(x[, n])", "Round away from zero"),
    "ROUNDDOWN": ("math", "ROUNDDOWN(x[, n])", "Round toward zero"),
    "POWER": ("math", "POWER(base, exp)", "Exponentiation"),
    "SQRT": ("math", "SQRT(x)", "Square root"),
    "MIN": ("math", "MIN(a, b, ...)", "Smallest value"),
    "MAX": ("math", "MAX(a, b, ...)", "Largest value"),
    "SUM": ("math", "SUM(a, b, ...)", "Sum of values"),
    "AVG": ("math", "AVG(a, b, ...)", "Arithmetic mean"),
    "MOD": ("math", "MOD(a, b)", "a modulo b"),
    "SIGN": ("math", "SIGN(x)", "-1, 0, or 1"),
    # Text
    "UPPER": ("text", "UPPER(s)", "Convert to uppercase"),
    "LOWER": ("text", "LOWER(s)", "Convert to lowercase"),
    "TRIM": ("text", "TRIM(s)", "Strip leading/trailing whitespace"),
    "PROPER": ("text", "PROPER(s)", "Title-case each word"),
    "LEN": ("text", "LEN(s)", "Character length"),
    "LEFT": ("text", "LEFT(s, n)", "First n characters"),
    "RIGHT": ("text", "RIGHT(s, n)", "Last n characters"),
    "MID": ("text", "MID(s, start, length)", "Substring (start is 1-indexed)"),
    "FIND": ("text", "FIND(needle, haystack[, start])", "Case-sensitive position (1-indexed); #VALUE if missing"),
    "SEARCH": ("text", "SEARCH(needle, haystack[, start])", "Case-insensitive position; 0 if missing"),
    "CONCAT": ("text", "CONCAT(a, b, ...)", "Join values as text"),
    "REPLACE": ("text", "REPLACE(s, find, repl)", "Replace all occurrences"),
    "REPT": ("text", "REPT(s, n)", "Repeat n times (capped at 1024)"),
    "CONTAINS": ("text", "CONTAINS(s, sub)", "True if s contains sub"),
    "STARTSWITH": ("text", "STARTSWITH(s, prefix)", "True if s starts with prefix"),
    "ENDSWITH": ("text", "ENDSWITH(s, suffix)", "True if s ends with suffix"),
    "PAD": ("text", "PAD(s, width)", "Right-pad to width"),
    "PADLEFT": ("text", "PADLEFT(s, width)", "Left-pad to width"),
    "ZEROPAD": ("text", "ZEROPAD(s, width)", "Left-pad with zeros to width (e.g. 1 -> 01)"),
    "CENTER": ("text", "CENTER(s, width)", "Center within width"),
    "SPLIT": ("text", "SPLIT(text[, sep])", "Split text into an array (default: whitespace)"),
    "REGEXMATCH": ("text", "REGEXMATCH(text, pattern)", "True if the pattern matches"),
    "REGEXEXTRACT": ("text", "REGEXEXTRACT(text, pattern[, group])", "First match or capture group; blank if none"),
    "REGEXREPLACE": ("text", "REGEXREPLACE(text, pattern, repl)", "Replace every match"),
    # Conversion
    "TEXT": ("convert", "TEXT(x)", "Convert to string"),
    "NUM": ("convert", "NUM(x)", "Convert to number"),
    "FIXED": ("convert", "FIXED(x[, n])", "Format with n decimals (default 2)"),
    # Color
    "COLOR": ("color", "COLOR(name_or_code)", 'Single color tile (e.g. "red" or 67)'),
}


# --- Variable lookup against the template context -------------------------- #


def _lookup_variable(path: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted path against the context.

    Returns ``ErrorValue('#REF')`` if any segment is missing. Values come
    back in their native Python type (int/float/bool/str) so that the
    evaluator can do numeric comparisons without re-parsing.

    Home Assistant entity IDs use dot notation (``sensor.outdoor_temp``) but
    dots are path separators in the template language, so users write
    underscores (``sensor_outdoor_temp``).  When the source is
    ``home_assistant``, every possible underscore position in the entity
    segment is tried as a domain separator, as ``engine._get_variable_value``
    does for plain ``{{ }}`` substitution. Only if none matches is the
    segment looked up as-is.
    """
    parts = path.split(".")

    # Loop locals (``item``, ``index``) shadow everything else and are the only
    # single-segment names that resolve. They live under a reserved context key
    # rather than at the top level so a plugin whose id is literally ``item``
    # cannot be mistaken for the loop binding.
    locals_map = context.get(_LOCALS_KEY)
    if isinstance(locals_map, dict) and parts[0].lower() in locals_map:
        return _traverse(locals_map[parts[0].lower()], parts[1:])

    if len(parts) < 2:
        return ErrorValue("#REF")

    source = parts[0].lower()
    if source not in context:
        return ErrorValue("#REF")

    value: Any = context[source]

    # --- Home Assistant entity ID resolution --------------------------------
    # HA entities are keyed by their real ID which contains a dot
    # (e.g. "sensor.outdoor_temp").  The template path uses underscores
    # instead.  Resolve that first segment with smart conversion so that
    # the normal traversal loop below handles the rest of the path.
    start_idx = 1
    # Require at least source.entity_id.field (3 parts) to enter HA resolution.
    if source == "home_assistant" and len(parts) >= 3 and isinstance(value, dict):
        entity_id_part = parts[1]
        entity_data: Any | None = None

        if "_" in entity_id_part:
            # Try each underscore as the domain/name boundary until a match
            # is found (e.g. sensor_outdoor_temp → sensor.outdoor_temp).
            # This must come before the as-is lookup: the HA plugin also
            # returns each entity's state as a flat string under the
            # underscore key, and a path into the entity can't traverse it.
            sub = entity_id_part.split("_")
            for i in range(1, len(sub)):
                candidate = "_".join(sub[:i]) + "." + "_".join(sub[i:])
                if candidate in value:
                    entity_data = value[candidate]
                    break

        if entity_data is None:
            # Fall back to the key as-is (an entity stored without dots).
            entity_data = value.get(entity_id_part)

        if entity_data is None:
            return ErrorValue("#REF")
        value = entity_data
        start_idx = 2  # entity segment already consumed

    return _traverse(value, parts[start_idx:])


def _traverse(value: Any, parts: list[str]) -> Any:
    """Walk ``parts`` into ``value``, returning ``#REF`` on any missing segment.

    Dicts resolve by key (case-insensitively as a fallback); lists resolve by
    zero-based numeric index. Shared by plugin paths and loop locals.
    """
    for part in parts:
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


def _eval_node(node: _Node, context: dict[str, Any]) -> Any:
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
        lazy = _LAZY_BUILTINS.get(node.name)
        if lazy is not None:
            # Receives unevaluated nodes: these functions bind ``item`` for
            # their own arguments, so the caller's context is not enough.
            try:
                return lazy(node.args, context)
            except FormulaError as exc:
                return ErrorValue(exc.code)

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


def evaluate(expression: str, context: dict[str, Any] | None = None) -> str:
    """Parse and evaluate ``expression``, returning a rendered string.

    Parsing or evaluation errors render as their short code (e.g. ``#REF``)
    instead of raising, so a single bad formula never breaks rendering of
    the surrounding template. ``#SYNTAX`` errors include the source-character
    offset where they were detected (``#SYNTAX:12``) when one is available.
    """
    ctx = context or {}
    try:
        tokens = _tokenize(expression)
        tree = _Parser(tokens).parse()
        result = _eval_node(tree, ctx)
    except FormulaError as exc:
        if exc.code == "#SYNTAX" and exc.pos is not None:
            return f"#SYNTAX:{exc.pos}"
        return exc.code
    if _is_error(result):
        return result.code
    try:
        return _to_string(result)
    except FormulaError as exc:
        # An expression whose *result* is an array (``{{= plugin.games }}``).
        return exc.code


def evaluate_value(
    expression: str, context: dict[str, Any] | None = None, bindings: dict[str, Any] | None = None
) -> Any:
    """Parse and evaluate ``expression``, returning its *native* value.

    The data counterpart of :func:`evaluate` for callers that need the value
    itself rather than its board text (pixel canvases: numbers stay numbers,
    a plugin's dict or list stays data). ``bindings`` are extra names visible
    to the expression the way ``FOREACH``'s ``item`` is (names are
    case-insensitive and shadow plugin ids). Any parse or evaluation error
    raises :class:`FormulaError` with its tag (``#REF``, ``#SYNTAX``, ...)
    instead of being rendered.
    """
    ctx = context or {}
    if bindings:
        scope = dict(ctx.get(_LOCALS_KEY) or {})
        scope.update({name.lower(): value for name, value in bindings.items()})
        ctx = {**ctx, _LOCALS_KEY: scope}
    tokens = _tokenize(expression)
    tree = _Parser(tokens).parse()
    result = _eval_node(tree, ctx)
    if _is_error(result):
        raise FormulaError(result.code, f"{expression.strip()} evaluated to {result.code}")
    return result


def value_to_text(value: Any) -> str:
    """A native value as the board text :func:`evaluate` would render (raises ``#VALUE`` for arrays)."""
    return _to_string(value)


@dataclass(frozen=True)
class ExpressionIssue:
    """A single problem found by :func:`validate_expression`.

    Designed to be JSON-serialisable for editor integrations.
    """

    code: str  # e.g. "#SYNTAX", "#NAME?"
    message: str  # Human-readable diagnostic
    pos: int | None  # Character offset within the expression (None if unknown)


def validate_expression(
    expression: str,
    known_sources: set | None = None,
) -> list[ExpressionIssue]:
    """Statically validate a formula body.

    Returns an empty list if the expression looks well-formed. This is a
    *lightweight* check -- it confirms the expression parses, that all
    function names are recognised, that variable references look like a
    known plugin source (when ``known_sources`` is provided), and that
    obvious arity mistakes are flagged. It does not attempt to evaluate.
    """
    issues: list[ExpressionIssue] = []
    try:
        tokens = _tokenize(expression)
        tree = _Parser(tokens).parse()
    except FormulaError as exc:
        issues.append(ExpressionIssue(exc.code, exc.message, exc.pos))
        return issues

    def _walk(node: _Node, bound: set[str]) -> None:
        if isinstance(node, _Call):
            if node.name not in _BUILTINS and node.name not in _LAZY_BUILTINS:
                issues.append(
                    ExpressionIssue(
                        "#NAME?",
                        f"Unknown function: {node.name}",
                        None,
                    )
                )
            else:
                _check_arity(node, issues)
            if node.name == "LET":
                # Names LET binds are not plugin sources. Each value expression
                # sees the names bound before it; the body sees them all.
                names: set[str] = set()
                for i in range(0, max(len(node.args) - 1, 0), 2):
                    if i + 1 < len(node.args):
                        _walk(node.args[i + 1], bound | names)
                    target = node.args[i]
                    if isinstance(target, _Var) and "." not in target.path:
                        names.add(target.path.lower())
                if node.args:
                    _walk(node.args[-1], bound | names)
                return
            for child in node.args:
                _walk(child, bound)
        elif isinstance(node, _Var):
            if known_sources is not None:
                source = node.path.split(".", 1)[0].split(":", 1)[0].lower()
                # ``item``/``index`` are bound by FOREACH/FILTER at render time
                # and LET binds its own names — none are plugin sources, so the
                # editor must not flag them.
                if source in LOOP_LOCAL_NAMES or source in bound:
                    return
                if source not in known_sources:
                    issues.append(
                        ExpressionIssue(
                            "#REF",
                            f"Unknown source: {source}",
                            None,
                        )
                    )
        elif isinstance(node, _Unary):
            _walk(node.operand, bound)
        elif isinstance(node, _Binary):
            _walk(node.left, bound)
            _walk(node.right, bound)

    _walk(tree, set())
    return issues


# Statically known minimum/maximum arities, used by :func:`validate_expression`.
# ``None`` means "unbounded". Functions that don't appear here are assumed to
# accept any number of arguments (we still rely on runtime ``_expect_args``
# checks for the strict variants).
_ARITY: dict[str, tuple[int, int | None]] = {
    "NOW": (0, 0),
    "TODAY": (0, 0),
    "DATE": (1, 1),
    "YEAR": (1, 1),
    "MONTH": (1, 1),
    "DAY": (1, 1),
    "HOUR": (1, 1),
    "MINUTE": (1, 1),
    "WEEKDAY": (1, 1),
    "DATEDIFF": (2, 3),
    "DATEADD": (2, 3),
    "FORMATDATE": (2, 2),
    "LET": (3, None),
    "SPLIT": (1, 2),
    "REGEXMATCH": (2, 2),
    "REGEXEXTRACT": (2, 3),
    "REGEXREPLACE": (3, 3),
    "COUNT": (1, 1),
    "AT": (2, 3),
    "FOREACH": (2, 3),
    "FILTER": (2, 2),
    "SORT": (1, 3),
    "SLICE": (2, 3),
    "JOIN": (1, 3),
    "SUMOF": (1, 2),
    "AVGOF": (1, 2),
    "MINOF": (1, 2),
    "MAXOF": (1, 2),
    "IF": (2, 3),
    "NOT": (1, 1),
    "IFERROR": (2, 2),
    "ISERROR": (1, 1),
    "ISBLANK": (1, 1),
    "DEFAULT": (2, 2),
    "COALESCE": (1, None),
    "ABS": (1, 1),
    "FLOOR": (1, 1),
    "CEIL": (1, 1),
    "INT": (1, 1),
    "ROUND": (1, 2),
    "ROUNDUP": (1, 2),
    "ROUNDDOWN": (1, 2),
    "POWER": (2, 2),
    "SQRT": (1, 1),
    "MOD": (2, 2),
    "SIGN": (1, 1),
    "MIN": (1, None),
    "MAX": (1, None),
    "SUM": (1, None),
    "AVG": (1, None),
    "AND": (0, None),
    "OR": (0, None),
    "UPPER": (1, 1),
    "LOWER": (1, 1),
    "TRIM": (1, 1),
    "PROPER": (1, 1),
    "LEN": (1, 1),
    "LEFT": (2, 2),
    "RIGHT": (2, 2),
    "MID": (3, 3),
    "FIND": (2, 3),
    "SEARCH": (2, 3),
    "REPLACE": (3, 3),
    "REPT": (2, 2),
    "CONTAINS": (2, 2),
    "STARTSWITH": (2, 2),
    "ENDSWITH": (2, 2),
    "PAD": (2, 2),
    "PADLEFT": (2, 2),
    "ZEROPAD": (2, 2),
    "CENTER": (2, 2),
    "TEXT": (1, 1),
    "NUM": (1, 1),
    "FIXED": (1, 2),
    "COLOR": (1, 1),
    "IFS": (2, None),
    "SWITCH": (3, None),
}


def _check_arity(node: _Call, issues: list[ExpressionIssue]) -> None:
    spec = _ARITY.get(node.name)
    if spec is None:
        return
    minimum, maximum = spec
    n = len(node.args)
    if n < minimum:
        issues.append(
            ExpressionIssue(
                "#VALUE",
                f"{node.name}: expected at least {minimum} arg(s), got {n}",
                None,
            )
        )
    elif maximum is not None and n > maximum:
        issues.append(
            ExpressionIssue(
                "#VALUE",
                f"{node.name}: expected at most {maximum} arg(s), got {n}",
                None,
            )
        )


# Match ``{{= ... }}`` blocks. Use ``[^}{]*`` for the body, mirroring
# VAR_PATTERN in engine.py (prevents pathological backtracking and means
# ``{`` / ``}`` cannot appear inside an expression -- documented constraint).
# We deliberately do **not** allow optional whitespace between ``{{`` and ``=``
# (i.e. no ``\s*`` before ``=``): combined with the permissive body class it
# would make the regex polynomial w.r.t. inputs like ``{{   `` with no
# closing brace. Whitespace after ``=`` is fine because it's part of the body
# and we strip it before parsing.
_FORMULA_PATTERN = re.compile(r"\{\{=([^}{]*)\}\}")


def render_expressions(template: str, context: dict[str, Any] | None = None) -> str:
    """Replace every ``{{= ... }}`` formula in ``template`` with its value."""
    if "{{" not in template or "=" not in template:
        return template

    ctx = context or {}

    def _sub(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        if not body:
            return ""
        return evaluate(body, ctx)

    return _FORMULA_PATTERN.sub(_sub, template)


def find_formulas(template: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, body)`` for each formula in ``template``.

    Useful for editor tooling that wants to underline / lint the formula
    bodies in-place.
    """
    return [(m.start(), m.end(), m.group(1).strip()) for m in _FORMULA_PATTERN.finditer(template)]


def list_builtins() -> tuple[str, ...]:
    """Return a stable, sorted tuple of all built-in formula function names."""
    return tuple(sorted(set(_BUILTINS) | set(_LAZY_BUILTINS)))


def function_signatures() -> dict[str, dict[str, str]]:
    """Return ``{ name: {category, signature, summary} }`` for every built-in.

    Editors and docs can use this to render an autocomplete picker without
    importing private symbols. The shape is part of the public API.
    """
    return {
        name: {"category": cat, "signature": sig, "summary": summary}
        for name, (cat, sig, summary) in _SIGNATURES.items()
    }


__all__ = [
    "RENDER_CLOCK_KEY",
    "ErrorValue",
    "ExpressionIssue",
    "FormulaError",
    "ensure_render_clock",
    "evaluate",
    "evaluate_value",
    "find_formulas",
    "function_signatures",
    "list_builtins",
    "render_expressions",
    "validate_expression",
    "value_to_text",
]
