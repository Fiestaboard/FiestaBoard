"""The plugins a flexible page reads, found without rendering it (issue #1751).

A render fetches only the plugins its page references. A flexible page
references plugins from its text blocks, each block's ``if``, ``{{…}}``
colours in its page and block styles, and its canvas blocks.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from src.canvas.models import Canvas
from src.canvas.refs import canvas_plugin_ids
from src.templates.engine import extract_template_plugin_ids

if TYPE_CHECKING:
    from src.pages.models import Page

__all__ = ["flexible_plugin_ids"]

_COLOR_KEYS = ("color", "background")


def _wrapped(expression: str) -> str:
    """An ``if`` as template text: already ``{{…}}``, or wrapped in it."""
    text = expression.strip()
    return text if text.startswith("{{") else "{{" + text + "}}"


def _style_texts(style: Any) -> Iterable[str]:
    if style is None:
        return
    for key in _COLOR_KEYS:
        value = getattr(style, key, None)
        if isinstance(value, str) and "{{" in value:
            yield value


def _template_texts(page: Page) -> list[str]:
    texts = list(_style_texts(page.style))
    for block in page.blocks or []:
        if block.kind == "text" and block.text:
            texts.append(block.text)
        if block.if_ and block.if_.strip():
            texts.append(_wrapped(block.if_))
        texts.extend(_style_texts(block.style))
    return texts


def _canvases(page: Page) -> list[Canvas]:
    canvases = []
    for block in page.blocks or []:
        body = block.canvas if block.kind == "canvas" else None
        if body is None:
            continue
        try:
            canvases.append(
                Canvas(
                    id="flex",
                    area={"row": 1, "col": 1, "rows": 1, "cols": 1},
                    content=body.content,
                    source=body.source,
                )
            )
        except ValueError:
            continue  # a canvas that cannot be built draws nothing and reads nothing
    return canvases


def flexible_plugin_ids(page: Page) -> set[str] | None:
    """The plugin ids ``page``'s render reads, or ``None`` when that cannot be known statically.

    ``None`` (a ``{{= … }}`` formula anywhere) tells the caller to fetch every
    enabled plugin, which is always safe.
    """
    template_refs = extract_template_plugin_ids(_template_texts(page))
    canvas_refs = canvas_plugin_ids(_canvases(page))
    if template_refs is None or canvas_refs is None:
        return None
    return template_refs | canvas_refs
