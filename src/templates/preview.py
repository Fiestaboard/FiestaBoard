"""Preview a template with sample data, missing data, another time or cached data (H6).

The editor's Live · Sample · Missing switch renders a template as if a
variable held another value, a plugin were down, or it were 7:00 AM, without
touching anything real. A :class:`Preview` travels with one render: the
engine builds that render's context (``data``: live, or every plugin's last
result however old), applies it to a request-local copy, and fills
:attr:`Preview.sources` with what the hub's own data is.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class Preview:
    """One render's sample data. ``values`` and ``missing`` use the
    template's variable paths; precedence is the hub's data, then ``missing``
    removes, then ``values`` sets. ``at`` is the render's clock."""

    values: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    at: datetime | None = None
    data: Literal["live", "cached"] = "live"
    #: Filled by the render: ``{plugin_id: {state, updated_at}}`` for the
    #: hub's own data (``fresh``, ``stale``, ``live`` or ``none``).
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def apply(self, context: dict[str, Any], roots: set[str] | None = None) -> dict[str, Any]:
        """A request-local copy of *context* with this preview applied.

        Never mutates *context*: its values are the plugin cache's own
        objects, so each plugin this preview touches is deep-copied first. A
        sample written into the cache would show on the next real render.
        With *roots*, only the paths under those plugin ids are applied (H8
        re-applies them over data it recomputed at another instant).
        """
        from src.templates.expressions import RENDER_CLOCK_KEY

        def wanted(path: str) -> bool:
            return roots is None or _split(path)[0] in roots

        result = dict(context)
        for root in {_split(path)[0] for path in (*self.values, *self.missing) if wanted(path)}:
            if root in result:
                result[root] = copy.deepcopy(result[root])
        for path in self.missing:
            if wanted(path):
                _remove(result, _split(path))
        for path, value in self.values.items():
            if wanted(path):
                _assign(result, _split(path), copy.deepcopy(value), path)
        if self.at is not None:
            result[RENDER_CLOCK_KEY] = self.at
        return result

    def roots(self) -> set[str]:
        """The plugin ids this preview samples or marks missing."""
        return {_split(path)[0] for path in (*self.values, *self.missing)}


class PreviewError(ValueError):
    """A sample value the hub's data cannot take (e.g. an item past a list's end)."""


def _split(path: str) -> list[str]:
    """``plugin[:instance].field.0.sub`` as segments; the root lowercased, as
    the template engine looks it up."""
    parts = path.split(".")
    return [parts[0].lower(), *parts[1:]]


def _child(node: Any, part: str) -> Any:
    """*part* of *node* the way the template engine resolves it, or ``None``."""
    if isinstance(node, dict):
        if part in node:
            return node[part]
        return node.get(part.lower())
    if isinstance(node, list) and part.isdigit() and int(part) < len(node):
        return node[int(part)]
    return None


def _key(node: dict, part: str) -> str:
    """The existing key *part* resolves to in *node*, else *part* itself."""
    return part if part in node or part.lower() not in node else part.lower()


def _remove(context: dict[str, Any], parts: list[str]) -> None:
    if len(parts) == 1:
        context.pop(parts[0], None)
        return
    node = context.get(parts[0])
    for part in parts[1:-1]:
        node = _child(node, part)
    last = parts[-1]
    if isinstance(node, dict):
        node.pop(_key(node, last), None)
    elif isinstance(node, list) and last.isdigit() and int(last) < len(node):
        node[int(last)] = None  # an item cannot be removed without moving the rest


def _assign(context: dict[str, Any], parts: list[str], value: Any, path: str) -> None:
    if len(parts) == 1:
        context[parts[0]] = value
        return
    node = context.get(parts[0])
    if not isinstance(node, dict | list):
        node = context[parts[0]] = {}
    for part in parts[1:-1]:
        child = _child(node, part)
        if not isinstance(child, dict | list):
            if not isinstance(node, dict):
                raise PreviewError(f"values[{path!r}]: there is no item {part}")
            child = node[_key(node, part)] = {}
        node = child
    last = parts[-1]
    if isinstance(node, dict):
        node[_key(node, last)] = value
    elif last.isdigit() and int(last) < len(node):
        node[int(last)] = value
    else:
        raise PreviewError(f"values[{path!r}]: there is no item {last}")


def hub_instant(at: datetime) -> datetime:
    """*at* in the hub's configured timezone (a naive time is already there)."""
    from src.time_service import get_time_service

    now = get_time_service().get_current_time()
    if now.tzinfo is None:
        return at.replace(tzinfo=None) if at.tzinfo is None else at.astimezone().replace(tzinfo=None)
    return at.replace(tzinfo=now.tzinfo) if at.tzinfo is None else at.astimezone(now.tzinfo)


def context_at(context: dict[str, Any], at: datetime, preview: Preview | None = None) -> dict[str, Any]:
    """*context* as it would be at the instant *at* (H8).

    The formula clock is pinned to *at*, and every enabled plugin in
    *context* whose data is a pure function of the clock (``date_time``:
    :meth:`~src.plugins.base.PluginBase.data_at`) is recomputed at *at*, so
    ``date_time.hour >= 17`` answers for that hour, not the real one. Other
    plugins keep the hub's current data (the hub keeps no history and cannot
    forecast). *preview*'s sample and missing paths are applied again over
    what was recomputed, so a sampled value still wins. Never mutates
    *context*.
    """
    from src.plugins.registry import get_plugin_registry
    from src.templates.expressions import RENDER_CLOCK_KEY

    result = dict(context)
    shifted = get_plugin_registry().data_at(result, at)
    result.update(shifted)
    if preview is not None and shifted:
        result = preview.apply(result, roots=set(shifted) & preview.roots())
    result[RENDER_CLOCK_KEY] = at
    return result
