"""FiestaBoard takes a display back when another app overwrites it (#2354).

Detection was already there for a board that reads back what it shows
(``OutputRuntime.observe_read``, #1945) and, since #2356, for a device that can
only say *another client wrote me* (``DevicePoll.overwritten``, a Pixoo whose
picture counter moved past FiestaBoard's). Detecting it used to stop at a
banner: the display loop's dedupe still believed the page was up and never
wrote it again.

Now a detected overwrite forgets what the board was last sent, so the next pass
puts the page back — unless the display's ``auto_restore`` setting is off, for
a display deliberately shared with another app. The other app's frame is still
kept for "Save as page" either way.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from src.devices import BoardInstance
from src.main import BoardRuntime, DisplayService
from src.outputs.hooks import DevicePoll

SENT = [[1, 2, 3]]
EXTERNAL = [[7, 7, 7]]


# ── the setting ─────────────────────────────────────────────────────────────


def test_auto_restore_is_on_for_a_new_board():
    assert BoardInstance().auto_restore is True


def test_a_board_saved_before_the_setting_restores_automatically():
    assert BoardInstance.from_dict({"id": "b1", "name": "Kitchen"}).auto_restore is True


def test_turning_auto_restore_off_survives_a_save_and_load():
    board = BoardInstance.from_dict({"id": "b1", "name": "Kitchen", "auto_restore": False})

    assert BoardInstance.from_dict(board.to_dict()).auto_restore is False


def test_settings_report_auto_restore_per_board(_isolated_data_dir):
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    stored = settings.set_boards(
        [
            {"device_type": "flagship", "name": "Kitchen"},
            {"device_type": "note", "name": "Hallway", "auto_restore": False},
        ]
    )
    kitchen, hallway = stored.boards[0]["id"], stored.boards[1]["id"]

    assert settings.is_auto_restore(board_id=kitchen) is True
    assert settings.is_auto_restore(board_id=hallway) is False


# ── a read-back board (Vestaboard): the board poll ──────────────────────────


def _read_back_service(*, auto_restore: bool | None = True):
    svc = DisplayService()
    client = Mock()
    svc.vb_client = client
    rt = svc._primary_runtime()
    rt.output.frames.record_sent(SENT)
    rt.last_active_page_content = "SHOWN"
    rt.last_active_page_id = "page-1"
    settings = Mock()
    settings.is_paused.return_value = False
    settings.get_primary_board_id.return_value = rt.board_id
    if auto_restore is not None:
        settings.is_auto_restore.return_value = auto_restore
    return svc, client, rt, settings


def _confirm_external(svc, client, settings):
    """Two mismatching polls against the same baseline: a confirmed external write."""
    client.read_current_message.return_value = EXTERNAL
    with patch("src.main.get_settings_service", return_value=settings):
        svc._poll_board_state_once()
        svc._poll_board_state_once()


def test_an_overwritten_read_back_board_is_put_back_on_the_next_pass():
    svc, client, rt, settings = _read_back_service()

    _confirm_external(svc, client, settings)

    assert rt.last_active_page_content is None
    client.clear_cache.assert_called()


def test_an_overwritten_read_back_board_keeps_the_other_apps_frame_to_save():
    svc, client, rt, settings = _read_back_service()

    _confirm_external(svc, client, settings)

    assert rt.external_frame is not None
    assert rt.external_frame[0] == EXTERNAL


def test_auto_restore_off_leaves_an_overwritten_read_back_board_alone():
    svc, client, rt, settings = _read_back_service(auto_restore=False)

    _confirm_external(svc, client, settings)

    assert rt.last_active_page_content == "SHOWN"
    client.clear_cache.assert_not_called()
    assert rt.showing_out_of_band is True


def test_a_single_mismatch_does_not_restore():
    """One mismatch can be FiestaBoard's own send still propagating."""
    svc, client, rt, settings = _read_back_service()
    client.read_current_message.return_value = EXTERNAL

    with patch("src.main.get_settings_service", return_value=settings):
        svc._poll_board_state_once()

    assert rt.last_active_page_content == "SHOWN"


# ── a device without read-back (Pixoo): the device poll ─────────────────────


def _device_service(news: DevicePoll, *, auto_restore: bool = True, board_id: str = "pixoo-1"):
    client = Mock()
    client.poll_device.return_value = news
    svc = DisplayService()
    rt = BoardRuntime(client, board_id)
    rt.last_active_page_content = "SHOWN"
    rt.last_active_page_id = "page-1"
    svc.runtimes = {board_id: rt}
    settings = Mock()
    settings.is_paused.return_value = False
    settings.is_auto_restore.return_value = auto_restore
    return svc, client, rt, settings


def _poll_devices(svc, settings):
    with patch("src.main.get_settings_service", return_value=settings):
        svc._poll_output_devices()


def test_an_overwritten_device_is_put_back_on_the_next_pass():
    svc, client, rt, settings = _device_service(DevicePoll(overwritten=True))

    _poll_devices(svc, settings)

    assert rt.last_active_page_content is None
    client.clear_cache.assert_called_once()


def test_an_overwritten_device_is_marked_overwritten():
    svc, _client, rt, settings = _device_service(DevicePoll(overwritten=True))

    _poll_devices(svc, settings)

    assert rt.showing_out_of_band is True
    assert isinstance(rt.overwritten_at, float)


def test_auto_restore_off_leaves_an_overwritten_device_alone():
    svc, client, rt, settings = _device_service(DevicePoll(overwritten=True), auto_restore=False)

    _poll_devices(svc, settings)

    assert rt.last_active_page_content == "SHOWN"
    client.clear_cache.assert_not_called()
    assert isinstance(rt.overwritten_at, float)


def test_auto_restore_off_still_resends_after_a_restart():
    """A reboot is not another app: what FiestaBoard sent was simply lost."""
    svc, client, rt, settings = _device_service(DevicePoll(restarted=True), auto_restore=False)

    _poll_devices(svc, settings)

    assert rt.last_active_page_content is None
    client.clear_cache.assert_called_once()


def test_auto_restore_is_asked_about_the_polled_board():
    svc, _client, _rt, settings = _device_service(DevicePoll(overwritten=True), board_id="pixoo-9")

    _poll_devices(svc, settings)

    settings.is_auto_restore.assert_called_with(board_id="pixoo-9")


# ── when the overwrite is over ──────────────────────────────────────────────


def test_the_engine_putting_the_page_back_clears_the_overwrite():
    from tests.test_per_board_engine import _board, _drive, _page_service, _schedule_service, _service_with_runtimes

    boards = [_board("b1", "One")]
    svc, _clients = _service_with_runtimes(boards)
    rt = svc.runtimes["b1"]
    rt.overwritten_at = 1.0
    rt.showing_out_of_band = True

    _drive(svc, boards, pages=_page_service({"pA": {"content": "ALPHA"}}), schedule=_schedule_service({"b1": "pA"}))

    assert rt.overwritten_at is None
    assert rt.showing_out_of_band is False


def test_a_fiestaboard_manual_write_clears_the_overwrite():
    """FiestaBoard's own out-of-band write replaced the other app's content."""
    svc, _client, rt, _settings = _device_service(DevicePoll(overwritten=True))
    rt.overwritten_at = 1.0

    svc.mark_showing_out_of_band("pixoo-1")

    assert rt.overwritten_at is None
    assert rt.showing_out_of_band is True
