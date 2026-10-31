"""Optional native rotation never claims a synchronized member is displayed."""

import dataclasses
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.main import BoardRuntime, DisplayService
from src.outputs.cells import RichCells, cells_from_codes
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult
from tests.test_per_board_engine import _board, _page_service, _schedule_service, _settings_service, _time_service


class NativeSign(OutputPluginBase):
    def __init__(self, config=None):
        super().__init__("b1", config if config is not None else {"native_rotation": True})
        self.playlists = []
        self.writes = []
        self.result = WriteResult(True, True)
        self.token = None
        self.news = None

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix", delivery="push", animation="none", native_transitions=frozenset()
        )

    def device_key(self):
        return f"native-test:{id(self)}"

    def write(self, frame, *, native, cancel):
        self.writes.append(frame)
        return WriteResult(True, True)

    def write_cells(self, cells, *, native, cancel):
        self.writes.append(cells)
        return WriteResult(True, True)

    def sync_native_playlist(self, playlist, *, cancel):
        self.token = cancel
        self.playlists.append(playlist)
        return self.result

    def poll_device(self):
        return self.news


def snapshot():
    from src.plugins import NativePlaylist, NativePlaylistEntry

    return NativePlaylist("b1", "collection:test", (NativePlaylistEntry("pA", cells_from_codes([[1]]), 30000),))


@pytest.mark.parametrize("value", [None, False, "true", 1, {}, []])
def test_native_rotation_requires_literal_opt_in(value):
    driver = OutputPluginDriver(NativeSign({"native_rotation": value}))
    assert getattr(driver, "native_rotation_enabled", None) is False


def test_opt_in_also_requires_a_real_method_override():
    class OldSign(NativeSign):
        sync_native_playlist = getattr(OutputPluginBase, "sync_native_playlist", None)

    assert getattr(OutputPluginDriver(OldSign()), "native_rotation_enabled", None) is False


def test_playlist_sync_uses_cancel_token_without_caching_a_member_as_displayed():
    plugin = NativeSign()
    driver = OutputPluginDriver(plugin)
    operation = getattr(driver, "sync_native_playlist", None)
    assert callable(operation), "driver must dispatch native playlists under its output runtime"
    assert operation(snapshot()) == (True, True)
    assert isinstance(plugin.token.cancelled, bool)
    assert driver._frames.characters is None
    assert driver._frames.last_frame is None


def test_snapshot_owns_cells_and_canvas_layers():
    from src.plugins import NativePlaylist, NativePlaylistEntry

    cells = RichCells(cells_from_codes([[1]]), layers=("canvas-bitmap",))
    entry = NativePlaylistEntry("pA", cells, 30000)
    cells[0][0] = cells_from_codes([[2]])[0][0]
    assert entry.cells[0][0].value == "A"
    assert entry.cells.layers == ("canvas-bitmap",)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.duration_ms = 100
    assert isinstance(NativePlaylist("b1", "pA", [entry]).entries, tuple)


@pytest.fixture
def native_engine():
    board = _board("b1", "One")
    plugin = NativeSign()
    driver = OutputPluginDriver(plugin, character_set=BUILTIN_CHARACTER_SETS["led_3x5"])
    service = DisplayService()
    rt = BoardRuntime(client=driver, board_id="b1")
    service.runtimes = {"b1": rt}
    service._primary_board_id = "b1"
    pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BRAVO"}})
    settings = _settings_service([board], schedule_off=("b1",), manual={"b1": "collection:test"})
    settings.get_transition_settings.return_value = SimpleNamespace(
        strategy=None, step_interval_ms=None, step_size=None
    )
    settings.get_polling_settings.return_value = SimpleNamespace(board_read_interval_local=30)
    collections = MagicMock()
    collections.get_collection.return_value = SimpleNamespace(
        selection_mode="time", page_ids=["pA", "pB"], time=SimpleNamespace(interval_seconds=30)
    )
    collections.resolve_page_id.return_value = "pA"
    with (
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_page_service", return_value=pages),
        patch("src.main.get_schedule_service", return_value=_schedule_service({})),
        patch("src.main.get_collection_service", return_value=collections),
        patch("src.time_service.get_time_service", return_value=_time_service()),
        patch("src.main.Config") as cfg,
        patch.object(service, "_check_trigger_override", return_value=None),
        patch.object(service, "request_board_refresh"),
    ):
        cfg.is_silence_mode_active.return_value = False
        cfg.silence_config_for.return_value = {"mode": "freeze"}
        yield SimpleNamespace(
            service=service,
            rt=rt,
            plugin=plugin,
            pages=pages,
            settings=settings,
            collections=collections,
            board=board,
            cfg=cfg,
            drive=lambda: service.check_and_send_for_board("b1", rt, is_primary=True, board=board, contexts={}),
        )
    if rt.send_worker is not None:
        rt.send_worker.wait_idle(2)
        rt.send_worker.stop()


def test_timed_collection_renders_every_member_in_order(native_engine):
    env = native_engine
    env.drive()
    assert len(env.plugin.playlists) == 1, "timed collection must reach playlist hook"
    playlist = env.plugin.playlists[-1]
    assert playlist.reference_id == "collection:test"
    assert [(e.page_id, e.duration_ms) for e in playlist.entries] == [("pA", 30000), ("pB", 30000)]
    assert [call.args[0] for call in env.pages.preview_page.call_args_list] == ["pA", "pB"]
    assert env.plugin.writes == []
    assert env.rt.last_active_page_id is None


def test_single_page_is_one_native_entry(native_engine):
    env = native_engine
    env.settings.get_active_page_id.return_value = "pA"
    env.settings.get_active_page_id.side_effect = None
    env.drive()
    assert env.plugin.playlists, "single page must use native mode when opted in"
    assert [(e.page_id, e.duration_ms) for e in env.plugin.playlists[-1].entries] == [("pA", 0)]


def test_flexible_native_member_uses_its_board_grid_without_page_geometry(native_engine, tmp_path):
    from src.pages.models import Page
    from src.pages.service import PageService
    from src.pages.storage import PageStorage

    env = native_engine
    env.board["device_type"] = "note"
    env.collections.get_collection.return_value.page_ids = ["pA"]
    pages = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    pages.storage.create(
        Page(
            id="pA",
            name="Flexible native page",
            type="flexible",
            layout={"gap": "none"},
            blocks=[{"id": "message", "kind": "text", "text": "HELLO"}],
        )
    )
    with patch("src.main.get_page_service", return_value=pages):
        env.drive()

    assert len(env.plugin.playlists) == 1, env.rt.last_send_error
    cells = env.plugin.playlists[0].entries[0].cells
    assert (len(cells), len(cells[0])) == (3, 15)
    assert "".join(cell.value or "" for cell in cells[0]).startswith("HELLO")


@pytest.mark.parametrize("mode", ["random", "variable"])
def test_non_timed_collections_keep_core_selection(native_engine, mode):
    env = native_engine
    env.collections.get_collection.return_value.selection_mode = mode
    env.drive()
    assert env.plugin.playlists == []
    assert env.plugin.writes


def test_native_failure_retries_without_starting_competing_core_rotation(native_engine):
    env = native_engine
    env.plugin.result = WriteResult(False, False)
    env.drive()
    assert len(env.plugin.playlists) == 1, "native error must come from playlist attempt"
    assert env.plugin.writes == []
    assert env.rt.last_send_error
    env.plugin.result = WriteResult(True, True)
    env.drive()
    assert len(env.plugin.playlists) == 2


def test_poll_reports_hardware_selection_and_retains_configured_reference(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    assert env.rt.last_active_page_id == "pB"
    assert env.settings.get_active_page_id(board_id="b1") == "collection:test"
    env.plugin.news = DevicePoll(native_selection=NativePageSelection(None))
    # Main polls physical outputs on their configured cadence. Make the
    # next observation due without sleeping or bypassing that production gate.
    env.rt.device_poll_attempted_at -= 30
    env.service._poll_output_devices()
    assert env.rt.last_active_page_id is None


def test_invalid_member_never_partially_syncs_or_falls_back(native_engine):
    env = native_engine
    env.collections.get_collection.return_value.page_ids.append("missing")
    env.drive()
    assert env.plugin.playlists == []
    assert env.plugin.writes == []
    assert env.rt.last_send_error, "invalid playlist must fail visibly"


def test_native_collection_skips_incompatible_members_like_core_selection(native_engine):
    env = native_engine
    pages = _page_service({"pA": {"content": "ALPHA"}, "pB": {"content": "BRAVO", "device_type": "note"}})
    with patch("src.main.get_page_service", return_value=pages):
        env.drive()
    assert len(env.plugin.playlists) == 1, env.rt.last_send_error
    assert [entry.page_id for entry in env.plugin.playlists[0].entries] == ["pA"]
    assert [call.args[0] for call in pages.preview_page.call_args_list] == ["pA"]


def test_native_collection_with_no_fitting_member_keeps_installed_snapshot(native_engine):
    env = native_engine
    env.drive()
    installed = env.rt.native_playlist
    pages = _page_service(
        {"pA": {"content": "A", "device_type": "note"}, "pB": {"content": "B", "device_type": "note"}}
    )
    with patch("src.main.get_page_service", return_value=pages):
        env.drive()
    assert len(env.plugin.playlists) == 1
    assert env.rt.native_playlist == installed
    assert env.rt.last_send_error


def test_native_selection_clears_when_selected_member_no_longer_fits(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pA"))
    env.service._poll_output_devices()
    pages = _page_service({"pA": {"content": "A", "device_type": "note"}, "pB": {"content": "B"}})
    with patch("src.main.get_page_service", return_value=pages):
        env.drive()
    assert [entry.page_id for entry in env.rt.native_playlist.entries] == ["pB"]
    assert env.service.native_page_selection("collection:test", "b1") == NativePageSelection(None)


def test_freeze_silence_retires_native_rotation_on_the_confirmed_selected_page(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    selected_cells = env.plugin.playlists[-1].entries[1].cells
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.cfg.is_silence_mode_active.return_value = True
    env.drive()
    assert env.plugin.writes == [selected_cells], "freeze must stop owned firmware rotation through a still write"
    assert env.rt.native_playlist is None
    assert env.rt.snoozing_message_sent


def test_active_page_resolution_uses_hardware_selection(native_engine):
    from src.collections.service import resolve_active_page_id, resolve_next_check_seconds
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    with patch("src.display_runtime.peek_service", return_value=env.service):
        assert resolve_active_page_id("collection:test", lambda: env.collections, board_id="b1") == "pB"
        assert resolve_next_check_seconds("collection:test", lambda: env.collections, board_id="b1") is None


def test_unknown_native_selection_does_not_invent_a_clock_selected_member(native_engine):
    from src.collections.service import resolve_active_page_id

    env = native_engine
    env.drive()
    with patch("src.display_runtime.peek_service", return_value=env.service):
        assert resolve_active_page_id("collection:test", lambda: env.collections) is None


def test_manual_write_persists_until_native_source_content_changes(native_engine):
    env = native_engine
    env.drive()
    env.rt.client.render([[2]], force=True)
    env.service.mark_showing_out_of_band("b1")
    env.drive()
    assert len(env.plugin.playlists) == 1
    assert env.rt.showing_out_of_band
    original = env.pages.preview_page.side_effect
    env.pages.preview_page.side_effect = lambda pid, **kw: (
        SimpleNamespace(available=True, formatted="NEW") if pid == "pB" else original(pid, **kw)
    )
    env.drive()
    assert len(env.plugin.playlists) == 2
    assert not env.rt.showing_out_of_band


def test_playlist_timeout_cancels_the_plugin_without_claiming_a_visible_member(monkeypatch):
    cancelled = threading.Event()

    class SlowSign(NativeSign):
        def capabilities(self):
            return dataclasses.replace(super().capabilities(), write_timeout_ms=20)

        def sync_native_playlist(self, playlist, *, cancel):
            cancel.wait(1)
            if cancel.cancelled:
                cancelled.set()
            return WriteResult(True, False, superseded=True)

    driver = OutputPluginDriver(SlowSign())
    assert driver.sync_native_playlist(snapshot()) == (False, False)
    assert cancelled.wait(1)
    assert "did not finish" in driver.last_write_error
    assert driver._frames.last_frame is None


def test_playlist_cancellation_is_exposed_without_successful_delivery():
    class CancelledSign(NativeSign):
        def sync_native_playlist(self, playlist, *, cancel):
            self.token = cancel
            return WriteResult(True, False, superseded=True)

    driver = OutputPluginDriver(CancelledSign())
    outcome = driver.sync_native_playlist(snapshot(), with_outcome=True)
    assert outcome.superseded
    assert driver.last_send_preempted
    assert driver._frames.last_frame is None


def test_unchanged_native_snapshot_still_reconciles_after_reboot(native_engine):
    from src.plugins import DevicePoll

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(restarted=True)
    env.service._poll_output_devices()
    env.drive()
    assert len(env.plugin.playlists) == 2
    assert env.plugin.playlists[0] == env.plugin.playlists[1]
    assert env.rt.last_active_page_id is None


def test_duplicate_members_render_once_and_preserve_occurrences(native_engine):
    env = native_engine
    env.collections.get_collection.return_value.page_ids = ["pA", "pB", "pA"]
    env.drive()
    assert [e.page_id for e in env.plugin.playlists[-1].entries] == ["pA", "pB", "pA"]
    assert [c.args[0] for c in env.pages.preview_page.call_args_list] == ["pA", "pB"]


def test_disabled_native_mode_uses_existing_frame_path(native_engine):
    env = native_engine
    env.plugin.config["native_rotation"] = False
    env.drive()
    assert env.plugin.writes
    assert not env.plugin.playlists


def test_native_sync_drops_a_preceding_still_from_expected_frame_cache():
    driver = OutputPluginDriver(NativeSign())
    driver.render([[1]])
    assert driver._frames.last_frame == [[1]]
    driver.sync_native_playlist(snapshot())
    assert driver._frames.last_frame is None, "a rotating playlist has no single expected still frame"


@pytest.mark.asyncio
async def test_active_page_api_is_scoped_to_the_hardware_board(native_engine):
    from src.plugins import DevicePoll, NativePageSelection
    from src.settings.routes import get_active_page

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    with (
        patch("src.settings.routes.get_settings_service", return_value=env.settings),
        patch("src.settings.routes.get_collection_service", return_value=env.collections),
        patch("src.display_runtime.peek_service", return_value=env.service),
    ):
        state = await get_active_page(board_id="b1")
        assert state["page_id"] == "collection:test"
        assert state["resolved_page_id"] == "pB"
        env.settings.get_active_page_id.side_effect = None
        env.settings.get_active_page_id.return_value = "collection:test"
        state = await get_active_page(board_id="b2")
        assert state["resolved_page_id"] == "pA", "other boards must not inherit b1's button selection"


def test_later_native_member_dependencies_keep_the_display_context(native_engine, tmp_path, monkeypatch):
    from src.pages.models import Page
    from src.pages.service import PageService
    from src.pages.storage import PageStorage
    from tests.test_demand_driven_fetch import _engine_with, _fetched_ids, _install_plugin, _make_registry

    env = native_engine
    registry = _make_registry()
    alpha = _install_plugin(registry, "alpha")
    beta = _install_plugin(registry, "beta")
    pages = PageService(storage=PageStorage(storage_file=str(tmp_path / "pages.json")))
    pages.storage.create(
        Page(id="pA", name="First", type="template", template=["{{alpha.value}}"], device_type="flagship")
    )
    pages.storage.create(
        Page(
            id="pB", name="Second", type="template", template=["{{alpha.value}} {{beta.value}}"], device_type="flagship"
        )
    )
    monkeypatch.setattr("src.plugins.registry.get_plugin_registry", lambda: registry)
    monkeypatch.setattr("src.pages.service.get_template_engine", lambda: _engine_with(registry))
    env.rt.client.plugin.bind_board(
        device_model={"id": "sample", "technology": "led_matrix", "pixelWidth": 64, "pixelHeight": 32}
    )
    with patch("src.main.get_page_service", return_value=pages):
        env.drive()
    assert len(env.plugin.playlists) == 1
    assert _fetched_ids(registry) == {"alpha": 1, "beta": 1}
    alpha_board = alpha.get_data.call_args.args[0]
    beta_board = beta.get_data.call_args.args[0]
    assert beta_board == alpha_board
    assert beta_board.display is not None


def test_mqtt_current_page_reports_native_selection(native_engine):
    from src.mqtt.state import StatePublisher
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.settings.get_active_page_id.side_effect = None
    env.settings.get_active_page_id.return_value = "collection:test"
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.pages.get_page.side_effect = lambda pid: SimpleNamespace(
        id=pid, name={"pA": "First", "pB": "Second"}.get(pid, "Collection")
    )
    with (
        patch("src.settings.service.get_settings_service", return_value=env.settings),
        patch("src.pages.service.get_page_service", return_value=env.pages),
        patch("src.display_runtime.peek_service", return_value=env.service),
        patch("src.api_server.peek_service", return_value=env.service),
        patch("src.api_server._get_board_client", return_value=env.rt.client),
    ):
        state = StatePublisher(MagicMock())._gather_state()
        assert state["current_page"] == "Second"


def test_temporary_override_still_wins_over_native_freeze_silence(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.cfg.is_silence_mode_active.return_value = True
    env.settings.consume_temporary_override.return_value = SimpleNamespace(
        is_expired=lambda: False, is_inline=False, page_id="pA"
    )
    env.drive()
    assert env.plugin.writes[-1][0][0].value == "A", "explicit override must win over selected B freeze"


def test_native_feedback_is_ignored_after_a_plain_override(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.settings.consume_temporary_override.return_value = SimpleNamespace(
        is_expired=lambda: False, is_inline=False, page_id="pA"
    )
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    assert env.rt.last_active_page_id == "pA"


def test_invalid_selection_feedback_cannot_break_all_board_polling(native_engine):
    from src.plugins import DevicePoll

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection="bad-plugin-feedback")
    env.service._poll_output_devices()
    assert env.rt.last_active_page_id is None


def test_native_completion_uses_its_own_outcome_if_another_writer_changes_flags(native_engine):
    env = native_engine
    driver = env.rt.client
    original = driver.sync_native_playlist

    def another_writer_after_result(playlist, **kwargs):
        result = original(playlist, **kwargs)
        driver._last_send_throttled = True
        return result

    driver.sync_native_playlist = another_writer_after_result
    env.drive()
    assert env.rt.native_playlist is not None, "completion must settle this call's outcome"


def test_native_floor_blocks_the_second_playlist_before_plugin_io():
    class PacedSign(NativeSign):
        def capabilities(self):
            return dataclasses.replace(super().capabilities(), min_interval_ms=5000)

    plugin = PacedSign()
    driver = OutputPluginDriver(plugin, clock=lambda: 100.0)
    assert driver.sync_native_playlist(snapshot()) == (True, True)
    outcome = driver.sync_native_playlist(snapshot(), with_outcome=True)
    assert outcome.throttled
    assert len(plugin.playlists) == 1


@pytest.mark.asyncio
async def test_current_display_template_comes_from_hardware_selected_member(native_engine):
    from src.pages.models import Page
    from src.pages.routes import get_current_display
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.settings.is_schedule_enabled.side_effect = None
    env.settings.is_schedule_enabled.return_value = False
    env.settings.get_active_page_id.side_effect = None
    env.settings.get_active_page_id.return_value = "collection:test"
    env.pages.get_page.side_effect = lambda pid: Page(id=pid, name=pid, type="template", template=[pid])
    with (
        patch("src.pages.routes.get_settings_service", return_value=env.settings),
        patch("src.pages.routes.get_page_service", return_value=env.pages),
        patch("src.pages.routes.get_collection_service", return_value=env.collections),
        patch("src.display_runtime.peek_service", return_value=env.service),
    ):
        result = await get_current_display()
    assert result.page_id == "pB"
    assert result.template == ["pB"]


def test_mcp_selection_uses_hardware_member(native_engine):
    from src.mcp_server import _build_mcp_server
    from src.pages.models import Page
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.pages.get_page.side_effect = lambda pid: Page(id=pid, name=pid, type="template", template=[pid])
    with (
        patch("src.settings.service.get_settings_service", return_value=env.settings),
        patch("src.pages.service.get_page_service", return_value=env.pages),
        patch("src.collections.service.get_collection_service", return_value=env.collections),
        patch("src.display_runtime.peek_service", return_value=env.service),
    ):
        mcp = _build_mcp_server()
        result = mcp._tool_manager._tools["get_active_page"].fn(board_id="b1")
    assert result["active_ref"] == "collection:test"
    assert result["resolved_page_id"] == "pB"


def test_freeze_silence_preserves_a_manual_write_after_native_rotation(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.rt.client.render([[3]], force=True)
    env.service.mark_showing_out_of_band("b1")
    env.cfg.is_silence_mode_active.return_value = True
    env.drive()
    assert env.plugin.writes == [[[3]]], "silence freeze must preserve the current manual message"


def test_native_collection_adopts_message_delivered_after_silence(native_engine):
    from src import silence_queue

    env = native_engine
    env.drive()
    env.cfg.silence_config_for.return_value["show_queued_on_exit"] = True
    silence_queue.hold(silence_queue.HeldSend.text("QUEUED MESSAGE", board_id="b1"))
    env.drive()
    assert len(env.plugin.writes) == 1
    env.drive()
    env.drive()
    assert len(env.plugin.playlists) == 1, "queued message must survive unchanged native source refreshes"
    assert silence_queue.peek("b1") is None
    original = env.pages.preview_page.side_effect
    env.pages.preview_page.side_effect = lambda pid, **kw: (
        SimpleNamespace(available=True, formatted="NEW") if pid == "pB" else original(pid, **kw)
    )
    env.drive()
    assert len(env.plugin.playlists) == 2


def test_failed_initial_native_sync_reports_unknown_selection(native_engine):
    from src.collections.service import resolve_active_page_id

    env = native_engine
    env.plugin.result = WriteResult(False, False)
    env.drive()
    with patch("src.display_runtime.peek_service", return_value=env.service):
        assert resolve_active_page_id("collection:test", lambda: env.collections) is None


def test_failed_changed_native_reference_does_not_report_a_clock_member(native_engine):
    from src.collections.service import resolve_active_page_id
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.settings.get_active_page_id.side_effect = None
    env.settings.get_active_page_id.return_value = "collection:other"
    env.plugin.result = WriteResult(False, False)
    env.drive()
    with patch("src.display_runtime.peek_service", return_value=env.service):
        assert resolve_active_page_id("collection:other", lambda: env.collections) is None


def test_freeze_uses_cached_selection_when_current_member_render_is_unavailable(native_engine):
    from src.plugins import DevicePoll, NativePageSelection

    env = native_engine
    env.drive()
    selected = env.plugin.playlists[-1].entries[1].cells
    env.plugin.news = DevicePoll(native_selection=NativePageSelection("pB"))
    env.service._poll_output_devices()
    env.cfg.is_silence_mode_active.return_value = True
    env.pages.preview_page.side_effect = None
    env.pages.preview_page.return_value = SimpleNamespace(available=False, error="provider unavailable")
    env.drive()
    assert env.plugin.writes == [selected]


def test_missing_native_runtime_does_not_read_or_initialize_settings(native_engine):
    service = native_engine.service
    with patch("src.main.get_settings_service", side_effect=AssertionError("feedback must only peek")):
        assert service.native_page_selection("page-42", "not-initialized") is None


def test_optional_native_state_does_not_break_legacy_runtime_consumers(native_engine):
    from src.display_runtime import native_page_selection

    env = native_engine
    env.service.runtimes["legacy"] = SimpleNamespace(last_active_page_id="pA")
    with patch("src.display_runtime.peek_service", return_value=env.service):
        assert native_page_selection("pA", "legacy") is None
