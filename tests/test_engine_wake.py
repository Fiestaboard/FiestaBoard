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

import threading
import time
from unittest import mock

from fastapi.testclient import TestClient

from tests.live_boards import install_live_boards
from tests.test_wire_goldens import install_wire_recorder, local_flagship


def test_a_woken_engine_stops_idling_at_once():
    from src.main import DisplayService

    service = DisplayService()
    threading.Timer(0.05, service.wake).start()
    started = time.monotonic()
    assert service.idle(5.0) is True
    assert time.monotonic() - started < 2.0


def test_an_engine_nobody_wakes_idles_out_its_step():
    from src.main import DisplayService

    assert DisplayService().idle(0.01) is False


def test_a_wake_is_consumed_by_the_idle_step_it_ends():
    from src.main import DisplayService

    service = DisplayService()
    service.wake()
    assert service.idle(0.01) is True
    assert service.idle(0.01) is False


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
