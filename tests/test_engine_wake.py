"""A page change wakes the display engine instead of waiting for its next tick.

The active-page route sends the new page to the board at once (measured on
the output-plugins POC stack: a Pixoo and a Vestaboard both change within a
second), but the engine's own pass — which records what each board shows,
and catches up a board the route did not send to — only ran on its poll
tick, ~10 s later for a secondary board. The route now wakes the engine,
which runs a pass within its 1 s idle step; finding the frame already shown,
it writes nothing.
"""

from __future__ import annotations

from unittest import mock

from fastapi.testclient import TestClient

from tests.live_boards import install_live_boards
from tests.test_silence_schedule_polling import service_factory  # noqa: F401  (fixture)
from tests.test_wire_goldens import install_wire_recorder, local_flagship


def test_a_wake_is_taken_once():
    from src.main import DisplayService

    service = DisplayService()
    service.wake()
    assert service.take_wake() is True
    assert service.take_wake() is False


def test_an_engine_nobody_woke_has_nothing_to_take():
    from src.main import DisplayService

    assert DisplayService().take_wake() is False


def test_the_run_loop_runs_a_pass_on_the_step_after_a_wake(service_factory):  # noqa: F811
    """Without the wake the loop would wait for the (patched-out) poll schedule."""
    svc, _mocks, _pages = service_factory(is_silence=False)
    ticks = {"n": 0}

    def fake_sleep(_seconds):
        ticks["n"] += 1
        if ticks["n"] == 2:
            svc.wake()
        if ticks["n"] >= 4:
            svc.running = False

    with (
        mock.patch.object(svc, "check_and_send_active_page", return_value=False) as drive,
        mock.patch.object(svc, "_silence_state_changed", return_value=False),
        mock.patch("src.main.schedule"),
        mock.patch("src.main.time.sleep", fake_sleep),
    ):
        svc.run()
    # The initial pass, then exactly one more: the woken step's.
    assert drive.call_count == 2


def test_setting_the_active_page_wakes_the_engine(monkeypatch):
    from src.api_server import app
    from src.pages.models import PageCreate
    from src.pages.service import get_page_service

    install_wire_recorder(monkeypatch)
    service = install_live_boards([local_flagship()])
    page = get_page_service().create_page(PageCreate(name="Wake", type="template", template=["WAKE UP"]))
    with mock.patch.object(service, "wake") as wake:
        resp = TestClient(app).put("/settings/active-page", json={"page_id": page.id, "board_id": "wire-local"})
    assert resp.status_code == 200, resp.text
    wake.assert_called_once_with()
