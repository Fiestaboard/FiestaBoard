"""Standard priority tiers for plugin triggers.

``TriggerResult.priority`` is an open integer to preserve flexibility, but
plugins should prefer these published tiers so the relative ordering across
the ecosystem stays predictable.  Higher numbers win when multiple triggers
are active at the same time.

Tiers
-----

* :attr:`TriggerPriority.AMBIENT`  (10) — passive surfacing.  The board
  drifts to this content when nothing else is going on (e.g. "now playing"
  scrobble updates).
* :attr:`TriggerPriority.NOTABLE`  (50) — something worth interrupting the
  current page for (e.g. weather alert, score change).
* :attr:`TriggerPriority.URGENT`   (80) — must surface now (e.g. doorbell,
  garage door left open).
* :attr:`TriggerPriority.CRITICAL` (100) — safety / security override
  (e.g. smoke alarm, severe weather warning).

Existing integer literals continue to work — ``priority=42`` is still valid.
The enum subclasses :class:`int` so values can be passed directly into the
``TriggerResult.priority`` integer field.
"""

from enum import IntEnum


class TriggerPriority(IntEnum):
    """Documented priority tiers for plugin triggers.

    Plugins are encouraged to use these values rather than raw integers so
    that triggers from different plugins compose predictably.  Custom values
    in between tiers (e.g. ``NOTABLE + 5``) are allowed when a plugin needs
    to outrank another plugin's same-tier trigger.
    """

    AMBIENT = 10
    NOTABLE = 50
    URGENT = 80
    CRITICAL = 100


__all__ = ["TriggerPriority"]
