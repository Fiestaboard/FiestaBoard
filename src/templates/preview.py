"""Preview a template with sample data, missing data, another time or cached data (H6).

The editor's Live · Sample · Missing switch renders a template as if a
variable held another value, a plugin were down, or it were 7:00 AM, without
touching anything real. A :class:`Preview` travels with one render: the
engine builds that render's context (``data``: live, or every plugin's last
result however old), applies it to a request-local copy, and fills
:attr:`Preview.sources` with what the hub's own data is.
"""

from __future__ import annotations

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
