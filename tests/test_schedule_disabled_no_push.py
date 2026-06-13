"""Regression test for issue #970: schedule-off must not push to the board.

When a user toggles the schedule off (e.g. so their kid's out-of-band message
sent from the Vestaboard app stays visible), the polling loop must stop
auto-pushing the active page. Triggers and explicit user overrides still
flow through their own paths, so the user retains a way to push when they
want to — but ``check_and_send_active_page`` itself goes quiet.

See: https://github.com/Fiestaboard/FiestaBoard/issues/970
"""

from unittest.mock import Mock, patch

import pytest

from src.main import DisplayService


@pytest.fixture
def service():
    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.send_characters.return_value = (True, True)
    return svc


def _patch_common(active_page_id="active-page", schedule_enabled=False):
    """Build the standard set of mocks for a check_and_send_active_page tick.

    Mirrors the pattern used in tests/test_silence_mode_display.py.
    """
    page = Mock(
        id=active_page_id,
        device_type="note",
        transition_strategy=None,
        transition_interval_ms=None,
        transition_step_size=None,
    )
    result = Mock(available=True, formatted="CLOCK\n12:34")

    page_service = Mock()
    page_service.get_page.return_value = page
    page_service.preview_page.return_value = result
    page_service.list_pages.return_value = [page]

    settings = Mock()
    settings.is_schedule_enabled.return_value = schedule_enabled
    settings.get_active_page_id.return_value = active_page_id
    settings.consume_temporary_override.return_value = None
    settings.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
    settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)

    config = Mock()
    config.is_silence_mode_active.return_value = False
    config.SILENCE_SCHEDULE_MODE = "indicator"
    config.SILENCE_SCHEDULE_PAGE_ID = None
    config.SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
    config.SILENCE_SCHEDULE_INDICATOR_POSITION = "center"

    return page_service, settings, config


class TestScheduleDisabledNoPush:
    """When schedule is off, the polling tick must not touch the board."""

    def test_schedule_off_with_active_page_does_not_send(self, service):
        """Schedule disabled + manually-set active page → no send.

        This is the literal repro from #970: the active page (e.g. a clock with
        live variables) was getting pushed every tick after the user toggled
        the schedule off, overwriting an out-of-band custom message.
        """
        page_service, settings, config = _patch_common(active_page_id="active-page", schedule_enabled=False)

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()
        # The polling render path should also be skipped — no rendering, no
        # plugin variable refresh — so a clock template isn't being recomputed
        # every tick when the user expects "off" to mean "off".
        page_service.preview_page.assert_not_called()

    def test_schedule_off_subsequent_ticks_stay_silent(self, service):
        """Multiple polling ticks with schedule off should never push."""
        page_service, settings, config = _patch_common(active_page_id="active-page", schedule_enabled=False)

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            for _ in range(3):
                assert service.check_and_send_active_page() is False

        service.vb_client.send_characters.assert_not_called()

    def test_schedule_off_with_no_active_page_does_not_default_to_first(self, service):
        """Schedule off + no manual active page → must not default to first page.

        The pre-fix behavior would call ``set_active_page_id(first_page)`` and
        push it. After the fix the polling loop must stay quiet.
        """
        page_service, settings, config = _patch_common(schedule_enabled=False)
        settings.get_active_page_id.return_value = None

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()
        # We must not silently mutate the user's active-page setting either.
        settings.set_active_page_id.assert_not_called()

    def test_schedule_on_still_pushes_active_page(self, service):
        """Sanity: schedule-on path is unchanged — the fix is scoped to off."""
        page_service, settings, config = _patch_common(schedule_enabled=True)
        schedule_svc = Mock()
        schedule_svc.get_active_page_id.return_value = "active-page"

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service", return_value=schedule_svc),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
            patch("src.main.get_collection_service") as collection_svc,
        ):
            collection_svc.return_value.resolve_page_id.return_value = "active-page"
            service.check_and_send_active_page()

        # The board should have received an update via the normal schedule path.
        service.vb_client.send_characters.assert_called()

    def test_schedule_off_still_honors_temporary_override(self, service):
        """A user-initiated temporary override must push even with schedule off.

        ``POST /settings/temporary-override`` is an explicit user action ("show
        this page now"). The schedule-off guard must not swallow it — that
        would be the same class of bug, just on a different toggle.
        """
        page_service, settings, config = _patch_common(schedule_enabled=False)

        override = Mock()
        override.is_expired.return_value = False
        override.page_id = "override-page"
        settings.consume_temporary_override.return_value = override

        # The override flow asks for the override page via get_page.
        override_page = Mock(
            id="override-page",
            device_type="note",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        page_service.get_page.return_value = override_page

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
            patch("src.main.get_collection_service") as collection_svc,
        ):
            collection_svc.return_value.resolve_page_id.return_value = "override-page"
            service.check_and_send_active_page()

        # Explicit overrides MUST still reach the board even when schedule is off.
        service.vb_client.send_characters.assert_called()
