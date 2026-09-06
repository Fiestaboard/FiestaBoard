"""Trigger service — manages event-based plugin triggers.

Plugins that set ``supports_triggers: true`` in their manifest can
implement ``check_triggers()`` to return :class:`TriggerResult` objects.
The :class:`TriggerService` periodically evaluates these, maintains a
set of *active* triggers, and exposes the highest-priority one so the
display loop can override the normal schedule/manual page.
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.atomic_io import write_json_atomic
from src.plugins.base import PluginBase, TriggerResult
from src.time_service import get_time_service

logger = logging.getLogger(__name__)

# Version of the on-disk dismissal store (see ``TriggerService`` below).
DISMISSALS_SCHEMA_VERSION = 1


def _default_dismissals_file() -> Path:
    """Default location of the dismissal store (repo-root ``data/``).

    A module-level seam so tests that exercise the trigger-service
    *singleton* can point it at a temp directory. See the adapter note in
    ``TriggerService.__init__`` for the A-track storage-kernel merge.
    """
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data" / "trigger_dismissals.json"


def _now() -> datetime:
    """The trigger clock: aware UTC from the app's TimeService (#1850).

    All trigger timing — activation stamps, expiry math, suppression
    horizons — goes through the TimeService rather than module-level
    ``datetime.now()``, so triggers follow the app's clock discipline and
    a fake TimeService is the only seam tests need. Aware UTC throughout:
    every stored/compared instant carries tzinfo, so naive-vs-aware mixing
    cannot occur internally and persisted ISO stamps are unambiguous.
    """
    return get_time_service().get_current_utc()


@dataclass
class ActiveTrigger:
    """A trigger that has fired and is currently active.

    Attributes:
        trigger_id: Stable identifier (used for dedup / dismiss).
        plugin_id: Which plugin produced this trigger.
        message: Simple text message (may be None if formatted_lines set).
        formatted_lines: Pre-formatted board lines (may be None).
        data: Raw data dict for template rendering.
        priority: Higher = more important.
        duration_seconds: How long to keep showing the trigger.
        activated_at: When the trigger was activated.
    """

    trigger_id: str
    plugin_id: str
    message: str | None
    formatted_lines: list[str] | None
    data: dict[str, Any] | None
    priority: int
    duration_seconds: int
    activated_at: datetime = field(default_factory=_now)

    def is_expired(self) -> bool:
        """Return True when the trigger has exceeded its duration."""
        age = (_now() - self.activated_at).total_seconds()
        return age >= self.duration_seconds

    def remaining_seconds(self) -> float:
        """Return the number of seconds left before expiry."""
        age = (_now() - self.activated_at).total_seconds()
        return max(0.0, self.duration_seconds - age)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API responses."""
        return {
            "trigger_id": self.trigger_id,
            "plugin_id": self.plugin_id,
            "message": self.message,
            "formatted_lines": self.formatted_lines,
            "data": self.data,
            "priority": self.priority,
            "duration_seconds": self.duration_seconds,
            "activated_at": self.activated_at.isoformat(),
            "remaining_seconds": round(self.remaining_seconds(), 1),
        }


class TriggerService:
    """Manages the lifecycle of plugin-originated triggers.

    * ``activate_trigger`` — record a fired trigger.
    * ``get_active_trigger`` — return the highest-priority non-expired
      trigger (or ``None``).
    * ``dismiss_trigger`` — manually dismiss a trigger by id; with
      ``suppress=True`` the suppression is persisted across restarts.
    * ``clear_expired`` — remove triggers past their duration.
    * ``check_plugin_triggers`` — evaluate a single plugin and activate
      any fired triggers.
    """

    def __init__(self, dismissals_file: Path | None = None) -> None:
        self._active_triggers: dict[str, ActiveTrigger] = {}
        # Triggers the user has explicitly dismissed (typically via a manual
        # "Change Page" action). Each entry maps a trigger_id to the time at
        # which the suppression expires, after which the trigger is allowed
        # to re-fire. Without this, a plugin re-emitting the trigger every
        # display loop tick would silently overwrite the user's choice
        # (see issue #856 — manual page change blocked by active trigger).
        self._suppressed_until: dict[str, datetime] = {}

        # Suppressed dismissals persist across restarts (#1850): before this,
        # a reboot brought every dismissed trigger straight back — the one
        # real restart loss in the trigger platform. The store is a minimal
        # schema-versioned JSON file written atomically (src.atomic_io).
        #
        # NOTE for the A-track storage-kernel merge: the file location is
        # resolved the way this branch's stores do (repo-root ``data/``,
        # mirroring pages/settings storage). When the kernel lands
        # (src/storage/json_store.py + src/paths.py), swap this block for
        # ``get_data_dir() / "trigger_dismissals.json"`` behind a JsonStore —
        # the payload is already schema-versioned, so that swap is a trivial
        # adapter change, not a migration.
        if dismissals_file is None:
            dismissals_file = _default_dismissals_file()
        self._dismissals_file = Path(dismissals_file)
        self._dismissals_lock = threading.Lock()
        # When each persisted suppression was created (metadata only; the
        # behavioral horizon lives in ``_suppressed_until``).
        self._dismissed_at: dict[str, datetime] = {}
        self._load_dismissals()
        logger.info("TriggerService initialized")

    # -- dismissal persistence ---------------------------------------------

    @staticmethod
    def _parse_instant(raw: object) -> datetime | None:
        """Parse a persisted ISO instant; naive values are taken as UTC."""
        if not isinstance(raw, str):
            return None
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    def _load_dismissals(self) -> None:
        """Restore persisted suppressions, pruning any that already lapsed.

        A corrupt or unreadable store degrades to the pre-#1850 behavior
        (empty suppressions) rather than blocking service startup.
        """
        try:
            if not self._dismissals_file.exists():
                return
            data = json.loads(self._dismissals_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Could not load trigger dismissals from %s: %s", self._dismissals_file, e)
            return
        if not isinstance(data, dict) or data.get("schema_version") != DISMISSALS_SCHEMA_VERSION:
            logger.warning(
                "Trigger dismissal store %s has unsupported schema_version %r - ignoring it",
                self._dismissals_file,
                data.get("schema_version") if isinstance(data, dict) else None,
            )
            return
        now = _now()
        entries = data.get("dismissals")
        pruned = 0
        for trigger_id, entry in (entries or {}).items():
            if not isinstance(entry, dict):
                pruned += 1
                continue
            until = self._parse_instant(entry.get("suppressed_until"))
            if until is None or until <= now:
                pruned += 1
                continue
            self._suppressed_until[trigger_id] = until
            dismissed_at = self._parse_instant(entry.get("dismissed_at"))
            if dismissed_at is not None:
                self._dismissed_at[trigger_id] = dismissed_at
        if self._suppressed_until:
            logger.info(
                "Restored %d persisted trigger dismissal(s): %s",
                len(self._suppressed_until),
                ", ".join(sorted(self._suppressed_until)),
            )
        if pruned:
            # Keep the on-disk store pruned too (best-effort; the next
            # write-through rewrites it from memory anyway).
            self._save_dismissals()

    def _save_dismissals(self) -> None:
        """Write-through of the in-memory suppressions (pruned of lapsed entries).

        Only suppressed dismissals are durable: an unsuppressed dismissal
        leaves no state behind today, and persisting one would change that
        contract. A failed write logs and degrades to in-memory behavior —
        dismissing a trigger must never raise into the caller.
        """
        now = _now()
        dismissals = {
            trigger_id: {
                "suppressed_until": until.isoformat(),
                "dismissed_at": (self._dismissed_at.get(trigger_id) or now).isoformat(),
            }
            for trigger_id, until in sorted(self._suppressed_until.items())
            if until > now
        }
        payload = {"schema_version": DISMISSALS_SCHEMA_VERSION, "dismissals": dismissals}
        try:
            with self._dismissals_lock:
                if not dismissals and not self._dismissals_file.exists():
                    return  # nothing durable and nothing on disk to clear
                write_json_atomic(self._dismissals_file, payload)
        except Exception as e:
            logger.error("Could not persist trigger dismissals to %s: %s", self._dismissals_file, e)

    # -- public API --------------------------------------------------------

    def activate_trigger(self, plugin_id: str, trigger: TriggerResult) -> None:
        """Record a fired trigger (replaces any existing trigger with same id).

        Triggers that were recently dismissed by the user are suppressed: a
        plugin can keep returning the same TriggerResult every loop tick, but
        it won't show on the board until the suppression entry expires (or
        a new trigger fires with a different ``trigger_id``).
        """
        suppressed_until = self._suppressed_until.get(trigger.trigger_id)
        if suppressed_until is not None:
            if _now() < suppressed_until:
                logger.debug(
                    "Trigger %s is user-suppressed until %s — not activating",
                    trigger.trigger_id,
                    suppressed_until.isoformat(),
                )
                return
            # Suppression has lapsed; drop the entry and fall through.
            del self._suppressed_until[trigger.trigger_id]
            self._dismissed_at.pop(trigger.trigger_id, None)

        active = ActiveTrigger(
            trigger_id=trigger.trigger_id,
            plugin_id=plugin_id,
            message=trigger.message,
            formatted_lines=trigger.formatted_lines,
            data=trigger.data,
            priority=trigger.priority,
            duration_seconds=trigger.duration_seconds,
            activated_at=_now(),
        )
        self._active_triggers[trigger.trigger_id] = active
        logger.info(
            "Trigger activated: %s (plugin=%s, priority=%d, duration=%ds)",
            trigger.trigger_id,
            plugin_id,
            trigger.priority,
            trigger.duration_seconds,
        )

    def get_active_trigger(self) -> ActiveTrigger | None:
        """Return the highest-priority non-expired trigger, or None.

        Automatically clears expired triggers before selecting.
        """
        self.clear_expired()
        if not self._active_triggers:
            return None
        return max(self._active_triggers.values(), key=lambda t: t.priority)

    def list_active_triggers(self) -> list[ActiveTrigger]:
        """Return all active (non-expired) triggers sorted by priority desc."""
        self.clear_expired()
        return sorted(
            self._active_triggers.values(),
            key=lambda t: t.priority,
            reverse=True,
        )

    def dismiss_trigger(self, trigger_id: str, suppress: bool = False) -> bool:
        """Dismiss (remove) a trigger by its id.

        Args:
            trigger_id: The trigger to dismiss.
            suppress: When True, also blacklist this ``trigger_id`` from
                re-activating until its natural duration would have ended.
                This is what makes a user's manual page change stick when a
                plugin keeps re-emitting the same trigger.

        Returns True if the trigger existed and was removed.
        """
        active = self._active_triggers.get(trigger_id)
        if active is None:
            return False

        if suppress:
            # Suppress for whatever was left of the trigger's natural duration,
            # not the full duration — once that window passes, the underlying
            # condition (e.g. "event happening soon") should be gone, and any
            # new trigger from the plugin is a fresh signal worth honoring.
            # Written through to the dismissal store so the suppression
            # survives a restart (#1850); an unsuppressed dismissal stays
            # transient, exactly as before.
            self._suppressed_until[trigger_id] = active.activated_at + timedelta(seconds=active.duration_seconds)
            self._dismissed_at[trigger_id] = _now()
            self._save_dismissals()
            logger.info(
                "Trigger dismissed + suppressed: %s (until %s)",
                trigger_id,
                self._suppressed_until[trigger_id].isoformat(),
            )
        else:
            logger.info("Trigger dismissed: %s", trigger_id)

        del self._active_triggers[trigger_id]
        return True

    def dismiss_active_for_user_override(self) -> int:
        """Dismiss every currently-active trigger and suppress re-firing.

        Called when the user explicitly takes control of what's on the board
        (e.g. via "Change Page" on the Home screen). Returns the number of
        triggers dismissed.
        """
        # Snapshot keys first because dismiss_trigger mutates the dict.
        ids = list(self._active_triggers.keys())
        for tid in ids:
            self.dismiss_trigger(tid, suppress=True)
        if ids:
            logger.info(
                "Dismissed %d trigger(s) for user override; suppressed: %s",
                len(ids),
                ", ".join(ids),
            )
        return len(ids)

    def clear_expired(self) -> None:
        """Remove all triggers that have exceeded their duration."""
        expired = [tid for tid, t in self._active_triggers.items() if t.is_expired()]
        for tid in expired:
            del self._active_triggers[tid]
            logger.debug("Trigger expired and removed: %s", tid)

        # Garbage-collect lapsed suppression entries so the dict doesn't
        # grow without bound. Memory-only: the store prunes lapsed entries
        # itself on every load and write.
        now = _now()
        lapsed = [tid for tid, until in self._suppressed_until.items() if now >= until]
        for tid in lapsed:
            del self._suppressed_until[tid]
            self._dismissed_at.pop(tid, None)

    def clear_all(self) -> None:
        """Remove all active triggers and suppressions (persisted ones too)."""
        self._active_triggers.clear()
        self._suppressed_until.clear()
        self._dismissed_at.clear()
        self._save_dismissals()
        logger.info("All triggers cleared")

    def check_plugin_triggers(self, plugin: PluginBase) -> None:
        """Evaluate a plugin's triggers and activate any that fired.

        Skips disabled plugins and plugins that don't support triggers.
        Errors in ``check_triggers()`` are caught and logged.
        """
        if not plugin.enabled:
            return
        if not plugin.supports_triggers:
            return

        try:
            results = plugin.check_triggers()
        except Exception:
            logger.exception("Error checking triggers for plugin %s", plugin.plugin_id)
            return

        for result in results:
            if result.triggered:
                self.activate_trigger(plugin.plugin_id, result)


# -- Singleton access ------------------------------------------------------

_trigger_service: TriggerService | None = None


def get_trigger_service() -> TriggerService:
    """Get or create the global trigger-service singleton."""
    global _trigger_service
    if _trigger_service is None:
        _trigger_service = TriggerService()
    return _trigger_service


def reset_trigger_service() -> None:
    """Reset the singleton (useful in tests or config reloads)."""
    global _trigger_service
    _trigger_service = None
    logger.info("TriggerService singleton reset")
