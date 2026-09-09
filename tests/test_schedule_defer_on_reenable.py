"""Deferring the schedule takeover when schedule mode is re-enabled.

Reported on Discord: a Home Assistant automation flips the FiestaBoard
schedule switch off while a movie is playing and back on when it ends.
Turning it back on repaints the board immediately, because every polling
tick re-resolves the active page from the clock -- there is no memory of a
"current window", only "what should be showing at this instant".

With ``schedule.defer_on_reenable`` turned on, re-enabling the schedule
records whichever schedule entry is winning at that moment and keeps
driving the board from the manually selected page until a *different*
entry wins -- i.e. until the next scheduled time the board would have
changed anyway. A schedule gap (no entry matches, default page showing) is
deferred the same way, so the toggle never repaints the board on its own.

The setting is off by default: existing installs keep repainting on
re-enable exactly as before.
"""

import tempfile
from datetime import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.schedules.models import ScheduleCreate
from src.schedules.service import ScheduleService
from src.schedules.storage import ScheduleStorage
from src.settings.service import ScheduleSettings

# ---------------------------------------------------------------------------
# 1. ScheduleService.get_active_schedule_entry
# ---------------------------------------------------------------------------


@pytest.fixture
def schedule_service():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    yield ScheduleService(storage=ScheduleStorage(storage_file=temp_path))
    Path(temp_path).unlink(missing_ok=True)


class TestActiveScheduleEntry:
    """The defer logic compares schedule *entries*, not page ids: two
    consecutive windows may point at the same page, and comparing page ids
    would leave such a board deferred forever."""

    def test_returns_the_winning_entry(self, schedule_service):
        created = schedule_service.create_schedule(
            ScheduleCreate(page_id="page-morning", start_time="09:00", end_time="10:00", day_pattern="all")
        )

        entry = schedule_service.get_active_schedule_entry(time(9, 30), "monday")

        assert entry is not None
        assert entry.id == created.id

    def test_returns_none_in_a_gap(self, schedule_service):
        schedule_service.create_schedule(
            ScheduleCreate(page_id="page-morning", start_time="09:00", end_time="10:00", day_pattern="all")
        )

        assert schedule_service.get_active_schedule_entry(time(11, 30), "monday") is None

    def test_distinct_entries_sharing_one_page_stay_distinct(self, schedule_service):
        """Back-to-back windows on the same page must resolve to different
        entries, otherwise a deferred board could never resume."""
        first = schedule_service.create_schedule(
            ScheduleCreate(page_id="page-same", start_time="09:00", end_time="10:00", day_pattern="all")
        )
        second = schedule_service.create_schedule(
            ScheduleCreate(page_id="page-same", start_time="10:00", end_time="11:00", day_pattern="all")
        )

        assert schedule_service.get_active_schedule_entry(time(9, 30), "monday").id == first.id
        assert schedule_service.get_active_schedule_entry(time(10, 30), "monday").id == second.id

    def test_get_active_page_id_still_resolves_through_the_entry(self, schedule_service):
        schedule_service.create_schedule(
            ScheduleCreate(page_id="page-morning", start_time="09:00", end_time="10:00", day_pattern="all")
        )

        assert schedule_service.get_active_page_id(time(9, 30), "monday") == "page-morning"


# ---------------------------------------------------------------------------
# 2. The setting itself
# ---------------------------------------------------------------------------


class TestDeferSetting:
    def test_defaults_off(self):
        assert ScheduleSettings().defer_on_reenable is False

    def test_round_trips_through_dict(self):
        restored = ScheduleSettings.from_dict(ScheduleSettings(defer_on_reenable=True).to_dict())

        assert restored.defer_on_reenable is True

    def test_missing_key_reads_as_off(self):
        """Configs written before this setting existed must load as off."""
        assert ScheduleSettings.from_dict({"enabled": True}).defer_on_reenable is False


# ---------------------------------------------------------------------------
# 3. The display loop
# ---------------------------------------------------------------------------


@pytest.fixture
def loop():
    """A DisplayService whose schedule state the test drives tick by tick.

    Returns a small controller: ``tick()`` runs one polling pass and reports
    which page the loop decided to render.
    """
    patches = {
        "config": patch("src.main.Config"),
        "settings": patch("src.main.get_settings_service"),
        "page": patch("src.main.get_page_service"),
        "schedule": patch("src.main.get_schedule_service"),
        "collection": patch("src.main.get_collection_service"),
        "trigger": patch("src.main.get_trigger_service"),
    }
    mocks = {name: p.start() for name, p in patches.items()}
    mocks["config"].is_silence_mode_active.return_value = False

    state = {"schedule_enabled": False, "defer_on_reenable": False, "entry": None}

    settings_service = Mock()
    settings_service.is_paused.return_value = False
    settings_service.get_polling_interval.return_value = 60
    settings_service.consume_temporary_override.return_value = None
    settings_service.get_active_page_id.return_value = "page-manual"
    settings_service.is_schedule_enabled.side_effect = lambda board_id=None: state["schedule_enabled"]
    settings_service.get_schedule_settings.side_effect = lambda: ScheduleSettings(
        enabled=state["schedule_enabled"], defer_on_reenable=state["defer_on_reenable"]
    )
    board_settings = Mock()
    board_settings.boards = [{"id": "board-1", "device_type": "flagship"}]
    settings_service.get_board_settings.return_value = board_settings
    transition = Mock()
    transition.strategy = None
    transition.step_interval_ms = 0
    transition.step_size = 1
    settings_service.get_transition_settings.return_value = transition
    mocks["settings"].return_value = settings_service

    schedule_service = Mock()
    schedule_service.get_active_schedule_entry.side_effect = lambda *a, **k: state["entry"]
    schedule_service.get_active_page_id.side_effect = lambda *a, **k: (
        state["entry"].page_id if state["entry"] else "page-default"
    )
    schedule_service.get_default_page.return_value = "page-default"
    mocks["schedule"].return_value = schedule_service

    page_service = Mock()

    def _get_page(page_id):
        page = Mock()
        page.id = page_id
        page.device_type = "flagship"
        page.transition_strategy = None
        page.transition_interval_ms = None
        page.transition_step_size = None
        return page

    page_service.get_page.side_effect = _get_page
    page_service.list_pages.return_value = []

    def _preview(page_id, **kwargs):
        preview = Mock()
        preview.available = True
        preview.formatted = f"content for {page_id}"
        return preview

    page_service.preview_page.side_effect = _preview
    mocks["page"].return_value = page_service

    from src.main import DisplayService

    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.send_characters.return_value = (True, True)
    svc.vb_client.render.return_value = (True, True)

    class Controller:
        def __init__(self):
            self.state = state

        def set_entry(self, entry_id, page_id):
            entry = Mock()
            entry.id = entry_id
            entry.page_id = page_id
            state["entry"] = entry

        def tick(self):
            """Run one polling pass; return the page id the loop rendered."""
            page_service.preview_page.reset_mock()
            with patch.object(svc, "_check_trigger_override", return_value=None):
                svc.check_and_send_active_page()
            if not page_service.preview_page.call_args_list:
                return None
            return page_service.preview_page.call_args_list[0][0][0]

    yield Controller()

    for p in patches.values():
        p.stop()


class TestDeferOnReenable:
    def test_reenable_holds_the_manual_page_until_the_entry_changes(self, loop):
        """The Discord report: re-enabling mid-window must not repaint."""
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = True

        loop.state["schedule_enabled"] = False
        assert loop.tick() == "page-manual"

        loop.state["schedule_enabled"] = True
        assert loop.tick() == "page-manual"

    def test_deferred_board_resumes_at_the_next_entry(self, loop):
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = True
        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True
        loop.tick()

        loop.set_entry("entry-night", "page-night")

        assert loop.tick() == "page-night"

    def test_resumed_board_stays_on_the_schedule(self, loop):
        """The defer is one-shot: once released it must not re-arm."""
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = True
        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True
        loop.tick()
        loop.set_entry("entry-night", "page-night")
        loop.tick()

        assert loop.tick() == "page-night"

    def test_setting_off_repaints_immediately(self, loop):
        """Default behavior is unchanged for everyone who hasn't opted in."""
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = False

        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True

        assert loop.tick() == "page-evening"

    def test_reenable_during_a_gap_also_holds(self, loop):
        """A gap resolves to the default page; deferring it too means the
        toggle never repaints the board on its own."""
        loop.state["entry"] = None
        loop.state["defer_on_reenable"] = True

        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True

        assert loop.tick() == "page-manual"

    def test_gap_defer_releases_when_a_window_starts(self, loop):
        loop.state["entry"] = None
        loop.state["defer_on_reenable"] = True
        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True
        loop.tick()

        loop.set_entry("entry-morning", "page-morning")

        assert loop.tick() == "page-morning"

    def test_first_tick_after_startup_does_not_defer(self, loop):
        """Startup is not a re-enable: a board that boots with the schedule
        already on must show the scheduled page, not the manual one."""
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = True
        loop.state["schedule_enabled"] = True

        assert loop.tick() == "page-evening"

    def test_disabling_again_clears_a_pending_defer(self, loop):
        """Off -> on (defer armed) -> off -> on must re-arm against the entry
        that is current at the *second* re-enable, not the first."""
        loop.set_entry("entry-evening", "page-evening")
        loop.state["defer_on_reenable"] = True
        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.state["schedule_enabled"] = True
        loop.tick()

        loop.state["schedule_enabled"] = False
        loop.tick()
        loop.set_entry("entry-night", "page-night")
        loop.state["schedule_enabled"] = True

        assert loop.tick() == "page-manual"


# ---------------------------------------------------------------------------
# 4. HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """TestClient over a SettingsService whose schedule settings round-trip."""
    from fastapi.testclient import TestClient

    from src.api_server import app

    with patch("src.api_server.get_settings_service") as mock_get:
        settings = ScheduleSettings()
        service = Mock()
        service.get_schedule_settings.side_effect = lambda: settings

        def _set(defer):
            settings.defer_on_reenable = bool(defer)
            return settings

        service.set_schedule_defer_on_reenable.side_effect = _set
        mock_get.return_value = service
        yield TestClient(app)


class TestScheduleSettingsEndpoint:
    def test_get_reports_the_setting(self, api_client):
        response = api_client.get("/schedules/settings")

        assert response.status_code == 200
        assert response.json() == {"defer_on_reenable": False}

    def test_put_round_trips(self, api_client):
        assert api_client.put("/schedules/settings", json={"defer_on_reenable": True}).status_code == 200

        assert api_client.get("/schedules/settings").json()["defer_on_reenable"] is True

    def test_put_rejects_a_missing_field(self, api_client):
        assert api_client.put("/schedules/settings", json={}).status_code == 400

    def test_put_rejects_a_non_boolean(self, api_client):
        assert api_client.put("/schedules/settings", json={"defer_on_reenable": "yes"}).status_code == 400

    def test_settings_route_is_not_shadowed_by_the_schedule_id_route(self, api_client):
        """`/schedules/{schedule_id}` must not swallow `/schedules/settings`."""
        assert api_client.get("/schedules/settings").json() == {"defer_on_reenable": False}
