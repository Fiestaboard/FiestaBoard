"""Copy a panel's content to a new grid without changing shared originals.

The caller saves the panel/board inside the context. Failed saves restore the
reference snapshots before deleting copies. A durable undo journal recovers
interrupted cross-file saves before the next startup reconciliation.
"""

import logging
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from src.collections.models import Collection, is_collection_id, make_collection_id
from src.collections.service import get_collection_service
from src.config import resolve_silence_schedule
from src.config_manager import get_config_manager
from src.devices import DeviceDimensions, dimensions_of
from src.pages.models import Page
from src.pages.service import get_page_service
from src.panels.content_resize_recovery import (
    commit_resize_journal,
    discard_resize_journal,
    prepare_resize_journal,
    restore_resize_geometry,
)
from src.schedules.service import get_schedule_service
from src.settings.service import get_settings_service

logger = logging.getLogger(__name__)


def _copy_name(name: str, board: dict) -> str:
    suffix = f" ({str(board.get('name') or board['id'])[:64]})"
    return name[: 100 - len(suffix)] + suffix


@contextmanager
def panel_content_resize(
    board: dict, target: DeviceDimensions, enabled: bool, *, prospective_panel: dict | None = None
):
    """Yield JSON-safe copy mappings, rewiring only ``board`` when enabled.

    Templates, row configuration, and canvas cell areas are kept verbatim.
    Canvas origins outside a smaller grid, missing content, and pending
    temporary overrides are refused before the first write. Holding the store
    locks through the caller's save keeps reference snapshots stable.
    """
    summary = {"page_copies": [], "collection_copies": []}
    if not enabled:
        yield summary
        return

    settings = get_settings_service()
    config = get_config_manager()
    pages = get_page_service().storage
    collections = get_collection_service().storage
    schedule_service = get_schedule_service()
    schedules = schedule_service.storage
    board_id = board.get("id")

    with ExitStack() as locks:
        for lock in (settings.lock, config.lock, pages.lock, collections.lock, schedules.lock):
            locks.enter_context(lock)
        if not board_id or not any(b.get("id") == board_id for b in settings.get_board_settings().boards):
            raise ValueError("Cannot copy content: the panel's board no longer exists")
        # Peek rather than expire: expiry can still have a pending revert_page_id.
        if settings.peek_temporary_override() is not None:
            raise ValueError("Cancel the temporary override before copying panel content, then try again")

        active = settings.get_active_page_id(board_id)
        default = schedule_service.get_default_page(board_id)
        silence = config.get_feature("silence_schedule")
        silence_ref = resolve_silence_schedule(silence, board_id)["page_id"]
        board_schedules = schedule_service.list_schedules(board_id)

        page_map: dict[str, str] = {}
        collection_map: dict[str, str] = {}
        new_pages: list[Page] = []
        new_collections: list[Collection] = []

        def copy_page(ref: str) -> str:
            if ref in page_map:
                return page_map[ref]
            original = pages.get(ref)
            if original is None:
                raise ValueError(f"Cannot copy panel content: page {ref!r} is missing; repair its reference first")
            if dimensions_of(original) == target:
                page_map[ref] = ref
                return ref
            data = original.model_dump()
            data.update(
                id=str(uuid4()),
                name=_copy_name(original.name, board),
                device_type="panel",
                grid_rows=target.rows,
                grid_cols=target.cols,
                notes_wide=1,
                notes_tall=1,
                created_at=datetime.now(UTC),
                updated_at=None,
                demo_plugin_id=None,
            )
            try:
                copied = Page(**data)
            except ValueError as exc:
                raise ValueError(f"Cannot copy page {original.name!r} to {target.cols} × {target.rows}: {exc}") from exc
            page_map[ref] = copied.id
            new_pages.append(copied)
            summary["page_copies"].append({"from_id": ref, "to_id": copied.id, "name": copied.name})
            return copied.id

        def copy_ref(ref: str | None) -> str | None:
            if not ref:
                return ref
            if not is_collection_id(ref):
                return copy_page(ref)
            if ref in collection_map:
                return collection_map[ref]
            original = collections.get(ref)
            if original is None:
                raise ValueError(
                    f"Cannot copy panel content: collection {ref!r} is missing; repair its reference first"
                )
            errors = original.validate_config()
            if errors:
                raise ValueError(f"Cannot copy collection {original.name!r}: {'; '.join(errors)}")
            mapped = [copy_page(pid) for pid in original.page_ids]
            if mapped == original.page_ids:
                collection_map[ref] = ref
                return ref
            data = original.model_dump()
            data.update(
                id=make_collection_id(),
                name=_copy_name(original.name, board),
                page_ids=mapped,
                created_at=datetime.now(UTC),
                updated_at=None,
            )
            if data["variable"]:
                variable = data["variable"]
                # Config can remain saved while another selection mode is active.
                variable["default_page_id"] = copy_page(variable["default_page_id"])
                for rule in variable["rules"]:
                    rule["page_id"] = copy_page(rule["page_id"])
            copied = Collection(**data)
            errors = copied.validate_config()
            if errors:
                raise ValueError(f"Cannot copy collection {original.name!r}: {'; '.join(errors)}")
            collection_map[ref] = copied.id
            new_collections.append(copied)
            summary["collection_copies"].append({"from_id": ref, "to_id": copied.id, "name": copied.name})
            return copied.id

        # Prepare and validate every copy before any storage mutation.
        new_active = copy_ref(active)
        schedule_refs = {s.id: copy_ref(s.page_id) for s in board_schedules}
        new_default = copy_ref(default)
        new_silence = copy_ref(silence_ref)

        # Public setters do not restore absence/inheritance or timestamps, and
        # can mutate memory before a failed write. Keep exact reference snapshots
        # for rollback; do not replace board settings saved by the caller.
        active_snapshot = deepcopy(settings.get_active_page_settings())
        schedule_snapshot = {s.id: s.model_copy(deep=True) for s in board_schedules}
        defaults_snapshot = deepcopy(schedules._default_page_by_board)
        silence_snapshot = deepcopy(config._config.get("features", {}).get("silence_schedule"))
        touched: set[str] = set()
        attempted_pages: list[str] = []
        attempted_collections: list[str] = []
        journal = prepare_resize_journal(
            board,
            target,
            summary,
            {
                "active": new_active,
                "default": new_default,
                "silence": new_silence,
                "schedules": schedule_refs,
            },
            prospective_panel=prospective_panel,
        )

        try:
            for copied in new_pages:
                if pages.exists(copied.id):
                    raise ValueError(f"Page with ID {copied.id} already exists")
                attempted_pages.append(copied.id)
                pages.create(copied)
            for copied in new_collections:
                if collections.exists(copied.id):
                    raise ValueError(f"Collection with ID {copied.id} already exists")
                attempted_collections.append(copied.id)
                collections.create(copied)
            for entry in board_schedules:
                if schedule_refs[entry.id] != entry.page_id:
                    touched.add("schedules")
                    if schedules.update(entry.id, {"page_id": schedule_refs[entry.id]}) is None:
                        raise ValueError("Schedule disappeared while copying panel content")
            if new_active != active:
                touched.add("active")
                settings.set_active_page_id(new_active, board_id)
            if new_default != default:
                touched.add("schedules")
                # Service.set_default_page clears the global legacy default for
                # the primary board, changing other boards that inherit it.
                schedules.set_default_page_id(new_default, board_id)
            if new_silence != silence_ref:
                touched.add("silence")
                if not config.set_silence_schedule_for_board(board_id, {"page_id": new_silence}):
                    raise OSError("Could not save the panel's copied silence page")
            yield summary
            commit_resize_journal(journal)
        except BaseException as exc:
            rollback_errors = []
            for surface in ("active", "schedules", "silence"):
                if surface not in touched:
                    continue
                try:
                    if surface == "active":
                        settings._active_page = active_snapshot
                        settings._save_to_file()
                    elif surface == "schedules":
                        schedules._schedules.update(
                            {
                                sid: entry.model_copy(update={"revision": str(uuid4())})
                                for sid, entry in schedule_snapshot.items()
                            }
                        )
                        schedules._default_page_by_board = defaults_snapshot
                        schedules.default_revision = str(uuid4())
                        schedules._save()
                    else:
                        features = config._config.setdefault("features", {})
                        if silence_snapshot is None:
                            features.pop("silence_schedule", None)
                        else:
                            features["silence_schedule"] = silence_snapshot
                        config._save_internal()
                except Exception:
                    rollback_errors.append(surface)
                    logger.exception("Could not restore %s after panel content conversion failed", surface)
            try:
                restore_resize_geometry(journal)
            except Exception:
                rollback_errors.append("geometry")
                logger.exception("Could not restore panel geometry after content conversion failed")
            # A persisted reference may still point to a copy after a failed
            # rollback. Retain all copies in that case rather than orphan it.
            if rollback_errors:
                raise RuntimeError(
                    "Panel content conversion failed and some references could not be restored "
                    f"({', '.join(rollback_errors)}). Original content and copies were retained; "
                    "check storage and the board's page selections before retrying."
                ) from exc
            cleanup_failed = False
            for storage, ids in ((collections, attempted_collections), (pages, attempted_pages)):
                # A collection whose deletion did not persist can still refer
                # to these pages. Leave them available for manual recovery.
                if cleanup_failed:
                    break
                for copy_id in reversed(ids):
                    try:
                        if storage.exists(copy_id):
                            storage.delete(copy_id)
                    except Exception:
                        cleanup_failed = True
                        logger.exception("Could not remove unused panel content copy %s", copy_id)
            discard_resize_journal()
            raise
