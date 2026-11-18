"""Does a write send a stored secret somewhere new? (phone key re-entry, H21a/H21c).

A phone (``control`` scope) reads every stored secret as ``"***"``. When it
echoes that mask back, the hub restores the stored secret, which is what makes
editing a form without retyping its keys possible. That must not let a phone
point the stored secret at a host it chose: changing *where* a secret is sent
requires typing it again (``400 key_required``).

"Where a secret is sent" is its **endpoint**: the connection fields around it.
For a secret at some path in a settings document, those are the
connection-like scalar fields of every object on the way down to it (its own
object, then each enclosing one), plus any extra top-level keys the caller
names (a display's ``output``). A field is connection-like when

* its name says so (host, URL, server, address, port, protocol, mode, TLS,
  sign-in, ...), or
* its value looks like an address (a URL, an IP address, ``host:port`` or a
  ``.local`` name), before or after the write, whatever the field is called.

Everything else (a tile's row and column, ``enabled``, a topic, a location) is
not, so editing it never asks for the key again. The rule is a heuristic: a
plain dotted name (``sensor.porch``, a Home Assistant entity, looks the same as
``board.example.com``) under a field whose name says nothing about connections
is not treated as an address. A plugin keeps its address in a field named for it.

The rule, given the stored document, the document the write would store and
the values the phone sent: a stored secret that still appears in the result
under a *different* endpoint, and that the phone did not send itself, refuses
the write. Values are compared type-strictly (``1`` is not ``True``).
"""

from __future__ import annotations

import ipaddress
import json
import re
from collections.abc import Iterable
from typing import Any

MASK = "***"

_CONNECTION_KEY = re.compile(
    r"(^|_)(host|hostname|hosts|url|uri|urls|endpoint|endpoints|server|servers|address|addr|ip|port|"
    r"protocol|scheme|mode|ssl|tls|https|insecure|broker|domain|realm|sign_in|signin|auth_type|"
    r"auth_method|subdomain|region|tenant|site|org|organization|workspace|account|cluster|zone|datacenter|"
    r"instance)($|_)",
    re.I,
)
_HOST_PORT = re.compile(r"^[a-z0-9.-]+:\d{1,5}$", re.I)


def is_connection_key(key: Any) -> bool:
    return isinstance(key, str) and bool(_CONNECTION_KEY.search(key))


def looks_like_address(value: Any) -> bool:
    """True for a URL, an IP address (with or without a port), ``host:port``, or a local name.

    A bare dotted name is not enough (``sensor.porch`` is a Home Assistant
    entity, not a host); fields that hold one are caught by their name.
    """
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    if not text or " " in text:
        return False
    if "://" in text or _HOST_PORT.match(text):
        return True
    if text == "localhost" or text.endswith((".local", ".local.")):
        return True
    host = text.strip("[]").split("%", 1)[0]
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if text.startswith("[") and "]:" in text:
        try:
            ipaddress.ip_address(text[1 : text.index("]")])
            return True
        except ValueError:
            return False
    return False


def same_value(a: Any, b: Any) -> bool:
    """Equality that also requires the same type (``1`` never equals ``True`` or ``1.0``)."""
    return type(a) is type(b) and a == b


def leaves(value: Any, path: tuple = ()) -> Iterable[tuple[tuple, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, (*path, index))
    else:
        yield path, value


def at(value: Any, path: tuple) -> Any:
    for step in path:
        if (isinstance(value, dict) and step in value) or (
            isinstance(value, list) and isinstance(step, int) and 0 <= step < len(value)
        ):
            value = value[step]
        else:
            return None
    return value


def stored_secrets(raw: Any, masked: Any) -> list[tuple[tuple, Any]]:
    """``(path, value)`` of every secret *raw* holds: the leaves its masked view reads as ``"***"``."""
    found = []
    for path, shown in leaves(masked):
        if shown != MASK:
            continue
        value = at(raw, path)
        if value in (None, "", MASK) or isinstance(value, (dict, list)):
            continue
        found.append((path, value))
    return found


def _connection_value(value: Any) -> Any:
    return (
        value
        if isinstance(value, (str, int, float, bool)) or value is None
        else json.dumps(value, sort_keys=True, default=str)
    )


def endpoint(doc: Any, path: tuple, secret_keys: frozenset, extra_keys: tuple = ()) -> dict:
    """The connection fields that decide where the secret at *path* in *doc* is sent."""
    found: dict = {}
    node = doc
    for depth, step in enumerate(path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == step or key in secret_keys:
                    continue
                container = isinstance(value, (dict, list))
                if (container and is_connection_key(key)) or (
                    not container
                    and (is_connection_key(key) or looks_like_address(value) or (depth == 0 and key in extra_keys))
                ):
                    found[(depth, key)] = _connection_value(value)
            node = node.get(step)
        elif isinstance(node, list) and isinstance(step, int) and 0 <= step < len(node):
            node = node[step]  # siblings in a list (other tiles, other sources) are not this secret's
        else:
            break
    return found


def _opaque_secret_moves(before: Any, after: Any, masked_before: Any, typed: list, after_leaves: list) -> bool:
    """A settings block withheld whole (``"***"``, an output that is not installed) has no
    known connection fields: any change to it that keeps one of its stored values, untyped,
    counts as moving a secret."""
    for path, shown in leaves(masked_before):
        block = at(before, path) if shown == MASK else None
        if not isinstance(block, (dict, list)) or at(after, path) == block:
            continue
        for _p, stored in leaves(block):
            if stored in (None, "", MASK) or not isinstance(stored, str):
                continue
            if any(same_value(v, stored) for _q, v in after_leaves) and not any(same_value(v, stored) for v in typed):
                return True
    return False


def moves_a_secret(
    before: Any,
    after: Any,
    masked_before: Any,
    sent: Any,
    *,
    extra_keys: tuple = (),
) -> bool:
    """True when *after* keeps a stored secret of *before* under a new endpoint and *sent* lacks it.

    *masked_before* is the API view of *before* (secrets as ``"***"``); *sent*
    is what the caller actually sent (its leaves count as typed values). A
    secret stored in several places (a display's flat and nested halves) may
    stay at any endpoint it already had.
    """
    typed = [value for _path, value in leaves(sent)]
    after_leaves = list(leaves(after))
    if _opaque_secret_moves(before, after, masked_before, typed, after_leaves):
        return True
    secrets = stored_secrets(before, masked_before)
    if not secrets:
        return False
    secret_keys = frozenset(path[-1] for path, _value in secrets if path and isinstance(path[-1], str))
    before_leaves = list(leaves(before))
    for _path, secret in secrets:
        if any(same_value(value, secret) for value in typed):
            continue  # the phone typed it: it knows it
        known = [endpoint(before, p, secret_keys, extra_keys) for p, v in before_leaves if same_value(v, secret)]
        for new_path, value in after_leaves:
            if same_value(value, secret) and endpoint(after, new_path, secret_keys, extra_keys) not in known:
                return True
    return False


__all__ = [
    "MASK",
    "endpoint",
    "is_connection_key",
    "looks_like_address",
    "moves_a_secret",
    "same_value",
    "stored_secrets",
]
