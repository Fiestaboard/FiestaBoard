"""Which plugins a page's canvases read, for the demand-driven context fetch (issue #1751).

A canvas reads plugin data through ``{{…}}`` expressions in its ``source``
and in any shape field. :func:`canvas_plugin_ids` collects the plugin ids
those expressions name, the way
:func:`src.templates.engine.extract_template_plugin_ids` does for template
lines, so a render fetches the plugins its canvases need. An expression that
is more than a plain dotted path (a formula) makes the set unknowable
statically: ``None``, which callers read as "fetch every enabled plugin" —
always safe.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .models import Canvas

__all__ = ["canvas_plugin_ids"]

_EXPR = re.compile(r"\{\{(.*?)\}\}", re.S)
_PATH = re.compile(r"\s*([A-Za-z_][\w:-]*)(?:\.[\w-]+)+\s*")


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _strings(item)


def canvas_plugin_ids(canvases: Iterable[Canvas] | None) -> set[str] | None:
    """The plugin ids *canvases* reference, or ``None`` when that cannot be known statically.

    Roots that are not plugins (a ``foreach`` item such as ``p.x``) are
    harmless: the registry intersects the set with the enabled plugins.
    """
    refs: set[str] = set()
    for canvas in canvases or ():
        for text in _strings(canvas.model_dump(by_alias=True, exclude_none=True)):
            for match in _EXPR.finditer(text):
                body = match.group(1).strip()
                if body.startswith("="):
                    body = body[1:]
                path = _PATH.fullmatch(body)
                if path is None:
                    return None
                refs.add(path.group(1).lower())
    return refs
