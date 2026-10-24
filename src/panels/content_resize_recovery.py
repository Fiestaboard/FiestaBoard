"""Durable recovery for a panel conversion spanning independent JSON stores."""

import logging
from contextlib import ExitStack
from copy import deepcopy

from src.collections.service import get_collection_service
from src.config import resolve_silence_schedule
from src.config_manager import get_config_manager
from src.devices import GEOMETRY_FIELDS, DeviceDimensions
from src.pages.service import get_page_service
from src.panels.models import Panel
from src.panels.service import get_panel_service
from src.schedules.models import ScheduleEntry
from src.schedules.service import get_schedule_service
from src.settings.service import get_settings_service
from src.storage.json_store import JsonStore

logger = logging.getLogger(__name__)


def journal_store() -> JsonStore:
    # The settings lock serializes this single journal across all boards.
    return JsonStore("panel-content-resize.json", current_schema_version=1, label="Panel content recovery")


def _slot(mapping: dict, key: str) -> dict:
    return {"present": key in mapping, "value": deepcopy(mapping.get(key))}


def _restore_slot(mapping: dict, key: str, slot: dict) -> None:
    if slot["present"]:
        mapping[key] = deepcopy(slot["value"])
    else:
        mapping.pop(key, None)


def prepare_resize_journal(
    board: dict, target: DeviceDimensions, summary: dict, expected: dict, *, prospective_panel: dict | None = None
) -> dict:
    """Persist the undo record before copies, references, or geometry change."""
    store = journal_store()
    if store.exists():
        raise RuntimeError("A panel content recovery is pending; restart to recover it before another conversion")
    settings = get_settings_service()
    schedules = get_schedule_service()
    config = get_config_manager()
    bid = board["id"]
    panel = get_panel_service().get_panel_by_board_id(bid)
    silence = config.get_feature("silence_schedule") or {}
    active = settings.get_active_page_settings()
    record = {
        "phase": "pending",
        "board_id": bid,
        "board_geometry": {key: _slot(board, key) for key in GEOMETRY_FIELDS},
        "target_geometry": {
            "device_type": "panel",
            "notes_wide": 1,
            "notes_tall": 1,
            "grid_rows": target.rows,
            "grid_cols": target.cols,
        },
        "panel": panel.model_dump(mode="json") if panel else None,
        "prospective_panel": Panel.model_validate(prospective_panel).model_dump(mode="json")
        if prospective_panel is not None
        else None,
        "active": _slot(active.by_board, bid),
        "active_effective": settings.get_active_page_id(bid),
        "primary": settings.get_primary_board_id() == bid,
        "legacy_active": active.page_id,
        "default": _slot(schedules.storage._default_page_by_board, bid),
        "default_effective": schedules.get_default_page(bid),
        "silence": _slot(silence.get("by_board") or {}, bid),
        "silence_by_board_present": "by_board" in silence,
        "silence_effective": resolve_silence_schedule(silence, bid)["page_id"],
        "schedules": [entry.model_dump(mode="json") for entry in schedules.list_schedules(bid)],
        "expected": expected,
        "copies": deepcopy(summary),
    }
    store.save(record)
    return record


def discard_resize_journal() -> None:
    journal_store().path.unlink(missing_ok=True)


def commit_resize_journal(record: dict) -> None:
    committed = {**record, "phase": "committed"}
    journal_store().save(committed)
    # A durable commit must never be undone because unlink failed. Startup
    # recognizes this marker and only retries removal.
    try:
        discard_resize_journal()
    except OSError:
        logger.warning("Committed panel conversion journal awaits cleanup", exc_info=True)


def restore_resize_geometry(record: dict) -> None:
    """Restore only the target's prior panel record and board geometry."""
    settings = get_settings_service()
    board = next((b for b in settings.get_board_settings().boards if b.get("id") == record["board_id"]), None)
    if board is None:
        raise RuntimeError("Panel recovery needs a board that was removed; original content and journal retained")
    if record["panel"]:
        panels = get_panel_service().storage
        original = Panel.model_validate(record["panel"])
        if panels.get(original.id) is None:
            raise RuntimeError("Panel recovery found a removed panel; original content and journal retained")
        panels.restore(original)
    for key, slot in record["board_geometry"].items():
        _restore_slot(board, key, slot)
    settings._save_to_file()


def recover_pending_panel_resizes() -> int:
    """Recover before startup reconciliation; refuse uncertain state unchanged.

    Repeated recovery is safe, including after a failed recovery save. Copies
    are retained on startup recovery: a later user edit or selection may have
    made one useful, and restoring the original references does not require
    deleting it. A committed journal only needs removal.
    """
    settings = get_settings_service()
    config = get_config_manager()
    pages = get_page_service().storage
    collections = get_collection_service().storage
    schedules = get_schedule_service().storage
    panels = get_panel_service().storage
    with ExitStack() as locks:
        for lock in (settings.lock, config.lock, pages.lock, collections.lock, schedules.lock, panels.lock):
            locks.enter_context(lock)
        try:
            record = journal_store().load()
            if record is None:
                return 0
            if record["phase"] == "committed":
                discard_resize_journal()
                return 1
            if record["phase"] != "pending":
                raise ValueError("Unknown panel recovery journal phase")
            bid = record["board_id"]
            board = next((b for b in settings.get_board_settings().boards if b.get("id") == bid), None)
            if board is None:
                raise ValueError("The board was removed after conversion began")
            expected = record["expected"]
            silence = config.get_feature("silence_schedule") or {}
            old_silence = record["silence"]
            expected_silence = deepcopy(old_silence)
            if expected["silence"] != record["silence_effective"]:
                expected_silence = {
                    "present": True,
                    "value": {**(old_silence["value"] or {}), "page_id": expected["silence"]},
                }
            if _slot(silence.get("by_board") or {}, bid) not in (old_silence, expected_silence):
                raise ValueError("Silence settings changed after conversion began")
            for current, original, converted in (
                (settings.get_active_page_id(bid), record["active_effective"], expected["active"]),
                (schedules.get_default_page_id(bid), record["default_effective"], expected["default"]),
                (resolve_silence_schedule(silence, bid)["page_id"], record["silence_effective"], expected["silence"]),
            ):
                if current not in (original, converted):
                    raise ValueError("Page selections changed after conversion began")
            old_geometry = {key: slot["value"] for key, slot in record["board_geometry"].items()}
            current_geometry = {key: board.get(key) for key in GEOMETRY_FIELDS}
            if current_geometry not in (old_geometry, record["target_geometry"]):
                raise ValueError("Board geometry changed after conversion began")
            restored_entries = []
            for raw in record["schedules"]:
                current = schedules.get(raw["id"])
                if current is None:
                    raise ValueError("A schedule was removed after conversion began")
                current_data = current.model_dump(mode="json")
                proposed = {**raw, "page_id": expected["schedules"][raw["id"]]}
                for data in (current_data, proposed):
                    data.pop("updated_at", None)
                original_data = {k: v for k, v in raw.items() if k != "updated_at"}
                if current_data not in (original_data, proposed):
                    raise ValueError("Schedule edits were made after conversion began")
                restored_entries.append(ScheduleEntry.model_validate(raw))
            for kind, storage in (("page_copies", pages), ("collection_copies", collections)):
                if any(not storage.exists(copy["from_id"]) for copy in record["copies"][kind]):
                    raise ValueError("Original content was removed after conversion began")
            if record["panel"]:
                current_panel = panels.get(record["panel"]["id"])
                if current_panel is None or current_panel.board_id != bid:
                    raise ValueError("The panel changed boards after conversion began")

                def comparable_panel(raw: dict) -> dict:
                    return {key: value for key, value in raw.items() if key != "updated_at"}

                allowed_panels = [comparable_panel(record["panel"])]
                if record.get("prospective_panel") is not None:
                    allowed_panels.append(comparable_panel(record["prospective_panel"]))
                if comparable_panel(current_panel.model_dump(mode="json")) not in allowed_panels:
                    raise ValueError("Panel settings changed after conversion began")

            # All conflict checks precede the first mutation. Restore just the
            # target's slots so unrelated later board settings remain intact.
            active = settings.get_active_page_settings()
            _restore_slot(active.by_board, bid, record["active"])
            if record["primary"]:
                active.page_id = record["legacy_active"]
            for entry in restored_entries:
                schedules._schedules[entry.id] = entry
            _restore_slot(schedules._default_page_by_board, bid, record["default"])
            schedules._save()
            features = config._config.setdefault("features", {})
            feature = features.setdefault("silence_schedule", {})
            by_board = feature.setdefault("by_board", {})
            _restore_slot(by_board, bid, record["silence"])
            if not by_board and not record["silence_by_board_present"]:
                feature.pop("by_board", None)
            config._save_internal()
            restore_resize_geometry(record)  # Persists active references and board geometry together.
            discard_resize_journal()
            return 1
        except Exception as exc:
            raise RuntimeError(
                f"Panel content recovery failed: {exc}. Journal and copies retained; "
                "resolve storage failures or conflicting edits before retrying."
            ) from exc
