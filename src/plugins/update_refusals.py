"""Releases of an output plugin that were refused, remembered by commit.

An output plugin's update that fails verification or does not load is rolled
back to the commit it replaced (plan D8, gate 2). Some failures only show up
when the release is applied — a bad import, a self-check — so the update
check, which reads only the incoming manifest, would offer the same release
again an hour later, and the auto-apply would pull and roll it back again,
forever.

So the refused commit is remembered, per plugin, in the plugin bookkeeping
FiestaBoard already persists in ``config.json`` (beside the
``removed_plugins`` tombstones and ``plugin_migrations``): the update check
does not offer that commit again, and says why. It is forgotten as soon as
the remote moves to any other commit — a newer release is always offered.

One commit per plugin: only the remote head is ever offered, so the latest
refusal is the only one that can matter.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefusedUpdate:
    """A release that was refused: its commit and why."""

    sha: str
    reason: str


def _config():
    from src.config_manager import get_config_manager

    return get_config_manager()


def refused_update(plugin_id: str) -> RefusedUpdate | None:
    """The release of *plugin_id* that was refused, or ``None``.

    Reads fail open (``None``): a store that cannot be read means the release
    is offered, which is what happened before this memory existed.
    """
    try:
        entry = _config().get_refused_plugin_update(plugin_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not read refused updates for %s: %s", plugin_id, exc)
        return None
    if entry is None:
        return None
    return RefusedUpdate(sha=entry["sha"], reason=entry.get("reason", ""))


def remember_refused_update(plugin_id: str, sha: str | None, reason: str) -> None:
    """Remember that *sha* of *plugin_id* was refused (no-op without a SHA)."""
    if not sha:
        return
    try:
        _config().set_refused_plugin_update(plugin_id, sha, reason)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not remember the refused update %s of %s: %s", sha, plugin_id, exc)


def forget_refused_update(plugin_id: str) -> None:
    """Forget *plugin_id*'s refused release (a newer one appeared)."""
    try:
        _config().clear_refused_plugin_update(plugin_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not clear the refused update of %s: %s", plugin_id, exc)
