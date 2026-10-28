"""Board conversion keeps shared originals and every board-scoped reference safe."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.collections.models import Collection, VariableModeConfig, VariableRule
from src.collections.service import get_collection_service
from src.config import resolve_silence_schedule
from src.config_manager import get_config_manager
from src.devices import DeviceDimensions
from src.pages.models import Page
from src.pages.service import get_page_service
from src.schedules.models import ScheduleEntry
from src.schedules.service import get_schedule_service
from src.settings.service import TemporaryOverride, get_settings_service

TARGET = DeviceDimensions(13, 32)


def resize(board, target=TARGET, enabled=True, **kwargs):
    from src.panels.content_resize import panel_content_resize

    return panel_content_resize(board, target, enabled, **kwargs)


@pytest.fixture
def env():
    settings = get_settings_service()
    settings.set_boards(
        [
            {"id": bid, "name": name, "device_type": "panel", "output": "fiestapanel", "grid_rows": 12, "grid_cols": 29}
            for bid, name in [("tv", "Living Room"), ("other", "Office")]
        ]
    )
    return SimpleNamespace(
        board=settings.get_board_settings().boards[0],
        settings=settings,
        pages=get_page_service().storage,
        collections=get_collection_service().storage,
        schedules=get_schedule_service().storage,
        config=get_config_manager(),
    )


def page(env, name="Weather", **kwargs):
    data = {
        "name": name,
        "type": "template",
        "device_type": "panel",
        "grid_rows": 12,
        "grid_cols": 29,
        "template": ["          {{weather.temperature}}", "LAST COLUMN"],
        "line_metadata": [{"alignment": "right", "wrap": True}],
        "transition_strategy": "column",
    }
    data.update(kwargs)
    return env.pages.create(Page(**data))


def schedule(env, ref, board_id="tv"):
    return env.schedules.create(ScheduleEntry(page_id=ref, board_id=board_id, start_time="09:00"))


def snapshot(env):
    return {
        "pages": [p.model_dump(mode="json") for p in env.pages.list_all()],
        "collections": [c.model_dump(mode="json") for c in env.collections.list_all()],
        "schedules": [
            s.model_dump(mode="json", exclude={"revision", "edit_protocol"})
            for s in env.schedules.list_all(board_id="*")
        ],
        "defaults": deepcopy(env.schedules._default_page_by_board),
        "legacy_default": env.schedules._default_page_id,
        "active": deepcopy(env.settings.get_active_page_settings().to_dict()),
        "silence": env.config.get_feature("silence_schedule"),
    }


def test_direct_copy_preserves_template_canvas_and_other_board(env):
    original = page(
        env,
        canvases=[
            {
                "id": "portrait",
                "area": {"row": 1, "col": 1, "rows": 9, "cols": 9},
                "bleed": ["left", "top"],
                "text": "flow",
                "source": "{{weather.icon}}",
            }
        ],
    )
    before = original.model_dump(mode="json")
    for bid in ("tv", "other"):
        env.settings.set_active_page_id(original.id, board_id=bid)

    with resize(env.board) as summary:
        json.dumps(summary)

    copied = env.pages.get(env.settings.get_active_page_id("tv"))
    assert copied.id != original.id
    assert copied.grid_rows == 13 and copied.grid_cols == 32
    assert copied.template == original.template
    assert copied.line_metadata == original.line_metadata
    assert copied.transition_strategy == original.transition_strategy
    assert copied.canvases == original.canvases
    assert "Living Room" in copied.name
    assert env.pages.get(original.id).model_dump(mode="json") == before
    assert env.settings.get_active_page_id("other") == original.id
    assert summary == {
        "page_copies": [{"from_id": original.id, "to_id": copied.id, "name": copied.name}],
        "collection_copies": [],
    }


def test_collection_variable_rules_and_every_reference_share_one_copy(env):
    original = page(env)
    fitting = page(env, "Already fits", grid_rows=13, grid_cols=32)
    collection = env.collections.create(
        Collection(
            name="Rotation",
            page_ids=[original.id, fitting.id],
            selection_mode="variable",
            variable=VariableModeConfig(
                default_page_id=original.id,
                rules=[
                    VariableRule(expression="{{weather.hot}}", page_id=original.id),
                    VariableRule(expression="{{weather.cold}}", page_id=fitting.id),
                ],
            ),
        )
    )
    original_collection = collection.model_dump(mode="json")
    env.settings.set_active_page_id(collection.id, board_id="tv")
    env.settings.set_active_page_id(collection.id, board_id="other")
    direct_schedule = schedule(env, original.id)
    collection_schedule = schedule(env, collection.id, board_id="")
    other_schedule = schedule(env, collection.id, board_id="other")
    env.schedules.set_default_page_id(collection.id)  # Legacy default inherited by both boards.
    for board_id in ("tv", "other"):
        env.config.set_silence_schedule_for_board(board_id, {"mode": "page", "page_id": collection.id})

    with resize(env.board) as summary:
        pass

    assert len(summary["page_copies"]) == len(summary["collection_copies"]) == 1
    copy_id = summary["page_copies"][0]["to_id"]
    collection_id = summary["collection_copies"][0]["to_id"]
    copied = env.collections.get(collection_id)
    assert copied.page_ids == [copy_id, fitting.id]
    assert copied.variable.default_page_id == copy_id
    assert [rule.page_id for rule in copied.variable.rules] == [copy_id, fitting.id]
    assert copied.variable.rules[0].expression == "{{weather.hot}}"
    assert env.settings.get_active_page_id("tv") == collection_id
    assert env.schedules.get(direct_schedule.id).page_id == copy_id
    assert env.schedules.get(collection_schedule.id).page_id == collection_id
    assert env.schedules.get_default_page_id("tv") == collection_id
    silence = env.config.get_feature("silence_schedule")
    assert resolve_silence_schedule(silence, "tv")["page_id"] == collection_id
    assert resolve_silence_schedule(silence, "other")["page_id"] == collection.id
    assert env.schedules.get_default_page_id("other") == collection.id
    assert env.schedules.get(other_schedule.id).page_id == collection.id
    assert env.settings.get_active_page_id("other") == collection.id
    assert env.collections.get(collection.id).model_dump(mode="json") == original_collection


@pytest.mark.parametrize("surface", ["default", "silence"])
def test_inactive_default_and_silence_pages_are_copied(env, surface):
    original = page(env)
    if surface == "default":
        env.schedules.set_default_page_id(original.id, "tv")
    else:
        env.config.set_silence_schedule_for_board("tv", {"page_id": original.id, "mode": "page"})
    with resize(env.board) as summary:
        pass
    assert summary["page_copies"][0]["from_id"] == original.id


@pytest.mark.parametrize("enabled,rows,cols", [(False, 12, 29), (True, 13, 32)])
def test_disabled_or_already_fitting_content_does_not_change(env, enabled, rows, cols):
    original = page(env, grid_rows=rows, grid_cols=cols)
    collection = env.collections.create(Collection(name="Fits", page_ids=[original.id]))
    env.settings.set_active_page_id(collection.id, "tv")
    before = snapshot(env)
    with resize(env.board, enabled=enabled) as summary:
        assert summary == {"page_copies": [], "collection_copies": []}
    assert snapshot(env) == before


def test_failure_in_caller_restores_all_references_and_removes_copies(env):
    original = page(env)
    collection = env.collections.create(Collection(name="Shared", page_ids=[original.id]))
    env.settings.set_active_page_id(collection.id, "tv")
    entry = schedule(env, original.id)
    default_revision = env.schedules.default_revision
    env.schedules.set_default_page_id(collection.id)
    env.config.set_feature("silence_schedule", {"page_id": original.id, "mode": "page"})
    before = snapshot(env)
    with pytest.raises(RuntimeError, match="board save failed"):
        with resize(env.board):
            raise RuntimeError("board save failed")
    assert snapshot(env) == before
    from src.pages.storage import PageRevisionConflict

    assert env.schedules.default_revision != default_revision
    with pytest.raises(PageRevisionConflict):
        env.schedules.update(entry.id, {"enabled": False}, expected_revision=entry.revision)


@pytest.mark.parametrize("boundary", ["page", "collection", "schedule", "active", "default", "silence"])
def test_partial_persistence_failure_rolls_back_even_if_write_mutated_memory(env, monkeypatch, boundary):
    original = page(env)
    collection = env.collections.create(Collection(name="Shared", page_ids=[original.id]))
    env.settings.set_active_page_id(collection.id, "tv")
    schedule(env, original.id)
    env.schedules.set_default_page_id(collection.id, "tv")
    env.config.set_silence_schedule_for_board("tv", {"page_id": original.id})
    before = snapshot(env)
    obj, method = {
        "page": (env.pages, "create"),
        "collection": (env.collections, "create"),
        "schedule": (env.schedules, "update"),
        "active": (env.settings, "set_active_page_id"),
        "default": (env.schedules, "set_default_page_id"),
        "silence": (env.config, "set_silence_schedule_for_board"),
    }[boundary]
    real = getattr(obj, method)

    def failing_write(*args, **kwargs):
        real(*args, **kwargs)
        raise OSError("disk unavailable")

    monkeypatch.setattr(obj, method, failing_write)
    with pytest.raises(OSError, match="disk unavailable"):
        with resize(env.board):
            pytest.fail("A failed conversion must never enter the caller")
    assert snapshot(env) == before


def test_pending_temporary_override_refuses_before_mutation(env):
    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    env.settings.set_temporary_override(TemporaryOverride(page_id=original.id))
    before = snapshot(env)
    with pytest.raises(ValueError, match=r"[Tt]emporary override"):
        with resize(env.board):
            pytest.fail("Active override must block conversion")
    assert snapshot(env) == before


def test_canvas_outside_shrunk_grid_refuses_before_any_copy(env):
    valid = page(env, "First")
    invalid = page(
        env,
        "Out of bounds",
        canvases=[
            {
                "id": "bottom",
                "area": {"row": 12, "col": 1, "rows": 1, "cols": 1},
                "source": "{{weather.icon}}",
            }
        ],
    )
    env.settings.set_active_page_id(valid.id, "tv")
    schedule(env, invalid.id)
    before = snapshot(env)
    with pytest.raises(ValueError, match=r"[Cc]anvas|canvas"):
        with resize(env.board, target=DeviceDimensions(6, 22)):
            pytest.fail("Unrepresentable canvas must not be silently moved")
    assert snapshot(env) == before


def test_failed_reference_restore_retains_copies_for_persisted_selection(env, monkeypatch):
    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    with pytest.raises(RuntimeError, match="could not be restored"):
        with resize(env.board) as summary:
            copied_id = summary["page_copies"][0]["to_id"]

            def broken_save():
                raise OSError("storage remains unavailable")

            monkeypatch.setattr(env.settings, "_save_to_file", broken_save)
            raise OSError("board update failed")

    assert env.pages.get(original.id) is not None
    assert env.pages.get(copied_id) is not None
    stored = json.loads(env.settings.settings_file.read_text())
    assert stored["active_page"]["by_board"]["tv"] == copied_id


def test_failed_collection_cleanup_keeps_its_page_copies(env, monkeypatch):
    original = page(env)
    collection = env.collections.create(Collection(name="Shared", page_ids=[original.id]))
    env.settings.set_active_page_id(collection.id, "tv")

    def broken_delete(_):
        raise OSError("collection cleanup failed")

    monkeypatch.setattr(env.collections, "delete", broken_delete)
    with pytest.raises(OSError, match="board update failed"):
        with resize(env.board) as summary:
            copied_id = summary["page_copies"][0]["to_id"]
            copied_collection = summary["collection_copies"][0]["to_id"]
            raise OSError("board update failed")

    assert env.settings.get_active_page_id("tv") == collection.id
    assert env.collections.get(copied_collection).page_ids == [copied_id]
    assert env.pages.get(copied_id) is not None


def test_copy_id_collision_never_deletes_the_existing_page(env, monkeypatch):
    from src.panels import content_resize

    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    before = snapshot(env)
    monkeypatch.setattr(content_resize, "uuid4", lambda: original.id)
    with pytest.raises(ValueError, match="already exists"):
        with resize(env.board):
            pytest.fail("A generated ID cannot overwrite existing content")
    assert snapshot(env) == before


def test_success_survives_storage_reload(env):
    from src.collections.storage import CollectionStorage
    from src.pages.storage import PageStorage
    from src.schedules.storage import ScheduleStorage
    from src.settings.service import SettingsService

    original = page(env)
    collection = env.collections.create(Collection(name="Rotation", page_ids=[original.id]))
    env.settings.set_active_page_id(collection.id, "tv")
    entry = schedule(env, original.id)
    env.schedules.set_default_page_id(original.id, "tv")
    with resize(env.board) as summary:
        pass
    copied_id = summary["page_copies"][0]["to_id"]
    copied_collection = summary["collection_copies"][0]["to_id"]
    assert PageStorage(str(env.pages.storage_file)).get(copied_id).grid_cols == 32
    assert CollectionStorage(str(env.collections.storage_file)).get(copied_collection).page_ids == [copied_id]
    reloaded_schedules = ScheduleStorage(str(env.schedules.storage_file))
    assert reloaded_schedules.get(entry.id).page_id == copied_id
    assert reloaded_schedules.get_default_page_id("tv") == copied_id
    assert SettingsService(str(env.settings.settings_file)).get_active_page_id("tv") == copied_collection


@pytest.mark.parametrize("phase", ["copies", "references", "geometry", "committed"])
def test_startup_recovers_interrupted_conversion_and_preserves_copies(env, phase):
    from src.panels.content_resize_recovery import journal_store, recover_pending_panel_resizes
    from src.panels.models import Panel
    from src.panels.service import get_panel_service

    panels = get_panel_service().storage
    panel = panels.create(Panel(name="TV", board_id="tv", render_style="led_matrix"))
    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    entry = schedule(env, original.id)
    before = snapshot(env)
    old_board = deepcopy(env.board)
    intended = {**panel.model_dump(mode="json"), "matrix_layout": "screen"}
    with resize(env.board, prospective_panel=intended) as summary:
        # This is the durable pending state written before the first copy.
        pending = journal_store().load()
        assert pending["phase"] == "pending"
        assert "output_config" not in json.dumps(pending)
        copied_id = summary["page_copies"][0]["to_id"]
        if phase in ("geometry", "committed"):
            panels.update(panel.id, {"matrix_layout": "screen"})
            boards = deepcopy(env.settings.get_board_settings().boards)
            boards[0].update(grid_rows=13, grid_cols=32)
            env.settings.set_boards(boards)
    assert not journal_store().exists()
    if phase == "copies":
        env.settings.set_active_page_id(original.id, "tv")
        env.schedules._schedules[entry.id] = entry
        env.schedules._save()
    # Recreate the on-disk journal a process killed at this phase leaves.
    if phase == "committed":
        pending["phase"] = "committed"
    journal_store().save(pending)
    assert recover_pending_panel_resizes() == 1
    assert recover_pending_panel_resizes() == 0
    assert env.pages.get(original.id) is not None
    assert env.pages.get(copied_id) is not None  # Recovery never guesses copies are unused.
    if phase == "committed":
        assert env.settings.get_active_page_id("tv") == copied_id
        assert panels.get(panel.id).matrix_layout == "screen"
    else:
        assert env.settings.get_active_page_id("tv") == original.id
        assert (
            env.schedules.get(entry.id).model_dump(mode="json", exclude={"revision", "edit_protocol"})
            == before["schedules"][0]
        )
        from src.pages.storage import PageRevisionConflict

        with pytest.raises(PageRevisionConflict):
            env.schedules.update(entry.id, {"enabled": False}, expected_revision=entry.revision)
        assert panels.get(panel.id).model_dump(mode="json") == panel.model_dump(mode="json")
        assert env.settings.get_board_settings().boards[0] == old_board


def test_recovery_failure_retains_journal_then_retries(env, monkeypatch):
    from src.panels.content_resize_recovery import journal_store, recover_pending_panel_resizes

    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    with resize(env.board) as summary:
        pending = journal_store().load()
    journal_store().save(pending)
    copied_id = summary["page_copies"][0]["to_id"]
    save = env.settings._save_to_file

    def broken_save():
        raise OSError("disk offline")

    monkeypatch.setattr(env.settings, "_save_to_file", broken_save)
    with pytest.raises(RuntimeError, match="recovery"):
        recover_pending_panel_resizes()
    assert journal_store().exists()
    assert env.pages.get(copied_id) is not None
    monkeypatch.setattr(env.settings, "_save_to_file", save)
    assert recover_pending_panel_resizes() == 1
    assert env.settings.get_active_page_id("tv") == original.id


def test_recovery_refuses_to_overwrite_subsequent_selection(env):
    from src.panels.content_resize_recovery import journal_store, recover_pending_panel_resizes

    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    with resize(env.board) as summary:
        pending = journal_store().load()
    journal_store().save(pending)
    later = page(env, name="User chose this later")
    env.settings.set_active_page_id(later.id, "tv")
    with pytest.raises(RuntimeError, match=r"changed|edits"):
        recover_pending_panel_resizes()
    assert env.settings.get_active_page_id("tv") == later.id
    assert journal_store().exists()
    assert env.pages.get(summary["page_copies"][0]["to_id"]) is not None


def test_recovery_refuses_later_silence_settings_edits(env):
    from src.panels.content_resize_recovery import journal_store, recover_pending_panel_resizes

    original = page(env)
    env.config.set_silence_schedule_for_board("tv", {"page_id": original.id, "start_time": "20:00"})
    with resize(env.board):
        pending = journal_store().load()
    journal_store().save(pending)
    env.config.set_silence_schedule_for_board("tv", {"start_time": "21:00"})
    with pytest.raises(RuntimeError, match=r"changed|edits"):
        recover_pending_panel_resizes()
    assert resolve_silence_schedule(env.config.get_feature("silence_schedule"), "tv")["start_time"] == "21:00"
    assert journal_store().exists()


@pytest.mark.parametrize("changes", [{"name": "Later name"}, {"matrix_sizing": "fit_panel"}, {"matrix_font": "3x5"}])
@pytest.mark.parametrize("with_expected", [False, True])
def test_recovery_preserves_conflicting_panel_edits(env, changes, with_expected):
    from src.panels.content_resize_recovery import journal_store, recover_pending_panel_resizes
    from src.panels.models import Panel
    from src.panels.service import get_panel_service

    panels = get_panel_service().storage
    panel = panels.create(Panel(name="TV", board_id="tv", render_style="led_matrix"))
    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    intended = {**panel.model_dump(mode="json"), "matrix_layout": "screen"} if with_expected else None
    with resize(env.board, prospective_panel=intended):
        pending = journal_store().load()
    journal_store().save(pending)
    panels.update(panel.id, changes)
    before = snapshot(env)
    edited_panel = panels.get(panel.id).model_dump(mode="json")
    with pytest.raises(RuntimeError, match=r"[Pp]anel.*changed|edits"):
        recover_pending_panel_resizes()
    assert snapshot(env) == before
    assert panels.get(panel.id).model_dump(mode="json") == edited_panel
    assert journal_store().exists()


@pytest.mark.parametrize("failed_phase", ["pending", "committed"])
def test_journal_write_failure_never_leaves_unrecoverable_conversion(env, monkeypatch, failed_phase):
    from src.panels.content_resize_recovery import journal_store
    from src.panels.models import Panel
    from src.panels.service import get_panel_service
    from src.storage.json_store import JsonStore

    original = page(env)
    env.settings.set_active_page_id(original.id, "tv")
    panels = get_panel_service().storage
    panel = panels.create(Panel(name="TV", board_id="tv", render_style="led_matrix"))
    before = snapshot(env)
    save = JsonStore.save

    def broken_save(store, data):
        if store.path.name == "panel-content-resize.json" and data["phase"] == failed_phase:
            raise OSError("journal unavailable")
        return save(store, data)

    monkeypatch.setattr(JsonStore, "save", broken_save)
    with pytest.raises(OSError, match="journal unavailable"):
        with resize(env.board):
            assert journal_store().exists()
            panels.update(panel.id, {"matrix_layout": "screen"})
            boards = deepcopy(env.settings.get_board_settings().boards)
            boards[0].update(grid_rows=13, grid_cols=32)
            env.settings.set_boards(boards)
    assert snapshot(env) == before
    assert panels.get(panel.id).model_dump(mode="json") == panel.model_dump(mode="json")
    assert env.settings.get_board_settings().boards[0]["grid_cols"] == 29
    assert not journal_store().exists()
