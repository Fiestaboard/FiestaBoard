"""A FiestaPanel's frame is served from core's last-frame store (plan D4).

``GET /panel/{id}/frame`` used to ask the virtual board client for its
private "glass" — a module-level registry the client kept so throwaway
clients for the same board saw the same frame. Every write now goes through
the board's live runtime, so the frame a TV pulls is simply that runtime's
last-frame store. Core took over the two things the client's glass did:

- **stale-shape refusal** — a frame whose shape no longer matches the
  board (a TV-size re-fit) is never served;
- **release** — deleting a panel or re-fitting its grid drops the board's
  stored frames.

And the engine's UI-only exemption asks the registry whether the board's
output is pulled (``delivery == "pull"``), not whether the client says it
is virtual — anything unknown is treated as hardware.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.outputs import OutputRuntime
from src.outputs.frames import FrameCache
from src.panels.models import PanelCreate
from tests.live_boards import install_live_boards

PANEL_BOARD = {
    "id": "vb-store",
    "name": "Hall TV",
    "api_mode": "virtual",
    "device_type": "panel",
    "grid_rows": 6,
    "grid_cols": 22,
}
LOCAL_BOARD = {
    "id": "b-local",
    "name": "Kitchen",
    "api_mode": "local",
    "device_type": "flagship",
    "host": "192.0.2.10",
    "local_api_key": "test_key",
}


def _grid(rows: int = 6, cols: int = 22, fill: int = 1) -> list[list[int]]:
    return [[fill] * cols for _ in range(rows)]


@pytest.fixture
def api() -> TestClient:
    from src.api_server import app

    return TestClient(app)


# --- the store, in core ------------------------------------------------------------


class TestCoreStore:
    def test_the_store_serves_a_copy_of_a_frame_of_the_boards_shape(self):
        frames = FrameCache()
        frames.record_sent(_grid(fill=4))
        served = frames.last_frame_shaped(6, 22)
        assert served == _grid(fill=4)
        served[0][0] = 9
        assert frames.last_frame == _grid(fill=4)

    def test_the_store_refuses_a_frame_of_another_shape(self):
        frames = FrameCache()
        frames.record_sent(_grid(3, 15))
        assert frames.last_frame_shaped(6, 22) is None

    def test_clear_releases_the_last_frame_and_the_dedupe_cache(self):
        frames = FrameCache()
        frames.record_sent(_grid())
        frames.clear()
        assert frames.last_frame is None
        assert frames.last_sent_at is None
        assert frames.characters is None

    @pytest.mark.parametrize(
        ("output_id", "delivery"),
        [("fiestapanel", "pull"), ("vestaboard", "push"), ("not-installed", None), (None, None)],
    )
    def test_a_runtime_answers_its_outputs_delivery(self, output_id, delivery):
        assert OutputRuntime("b", output_id=output_id).delivery == delivery


# --- the live service records each runtime's output -----------------------------------


def test_each_live_runtime_knows_its_output():
    service = install_live_boards([LOCAL_BOARD, PANEL_BOARD])
    assert service.get_runtime("b-local").output.output_id == "vestaboard"
    assert service.get_runtime("vb-store").output.output_id == "fiestapanel"


# --- the route --------------------------------------------------------------------


def _create_panel(api: TestClient) -> tuple[dict, object]:
    """A panel created through the API, with the live service built around it."""
    install_live_boards([LOCAL_BOARD])
    created = api.post("/panels", json={"name": "Wire TV", "screen_diagonal_inches": 43})
    assert created.status_code in (200, 201), created.text
    import src.display_runtime as display_runtime

    return created.json(), display_runtime.get_service()


class TestPanelFrameRoute:
    def test_the_frame_is_served_from_the_runtimes_last_frame_store(self, api, monkeypatch):
        service = install_live_boards([LOCAL_BOARD, PANEL_BOARD])
        rt = service.get_runtime("vb-store")
        rt.client.send_characters(_grid(fill=5))

        def no_client_read(*_args, **_kwargs):
            raise AssertionError("the panel frame read the virtual client, not the runtime's store")

        monkeypatch.setattr(rt.client, "read_current_message", no_client_read)
        from src.panels.service import get_panel_service

        panel = get_panel_service().create_panel(PanelCreate(name="Hall TV"), board_id="vb-store")
        frame = api.get(f"/panel/{panel.id}/frame").json()
        assert frame["characters"] == _grid(fill=5)
        assert frame["updated_at"] is not None

    def test_a_frame_left_behind_by_a_re_fit_is_never_served(self, api):
        service = install_live_boards([LOCAL_BOARD, PANEL_BOARD])
        rt = service.get_runtime("vb-store")
        rt.client.send_characters(_grid(fill=5))
        # The settings re-fit lands before the runtime is rebuilt: the store
        # still holds the 6x22 frame, the board is now 9x22.
        from src.settings.service import get_settings_service

        get_settings_service().set_boards([LOCAL_BOARD, {**PANEL_BOARD, "grid_rows": 9}])
        from src.panels.service import get_panel_service

        panel = get_panel_service().create_panel(PanelCreate(name="Hall TV"), board_id="vb-store")
        frame = api.get(f"/panel/{panel.id}/frame").json()
        assert frame["characters"] is None
        assert (frame["rows"], frame["cols"]) == (9, 22)

    def test_deleting_a_panel_releases_its_boards_frames(self, api):
        panel, service = _create_panel(api)
        old = service.get_runtime(panel["board_id"]).output
        rows, cols = panel["rows"], panel["cols"]
        assert api.post(f"/v1/boards/{panel['board_id']}/message", json={"text": "BYE"}).status_code == 200
        assert old.last_frame is not None, "seed frame never landed"

        assert api.delete(f"/panels/{panel['id']}").status_code == 200

        assert old.last_frame is None
        assert old.displayed_frame(rows, cols) is None
        assert service.get_runtime(panel["board_id"]) is None

    def test_re_fitting_a_panel_releases_the_old_shape_frame(self, api):
        panel, service = _create_panel(api)
        old = service.get_runtime(panel["board_id"]).output
        assert api.post(f"/v1/boards/{panel['board_id']}/message", json={"text": "OLD"}).status_code == 200
        assert old.last_frame is not None, "seed frame never landed"

        resized = api.patch(f"/panels/{panel['id']}", json={"screen_diagonal_inches": 85})
        assert resized.status_code == 200, resized.text

        assert old.last_frame is None
        assert old.frames.characters is None
        new = service.get_runtime(panel["board_id"]).output
        assert new.last_frame is None
        assert api.get(f"/panel/{panel['id']}/frame").json()["characters"] is None
