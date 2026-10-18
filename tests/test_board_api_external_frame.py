"""The remembered external frame over HTTP (issue #1945).

``GET /board/current-message`` carries ``external_characters`` and
``external_detected_at`` ONLY while the board's runtime holds a confirmed
external frame — the keys are absent otherwise (the route's
``response_model_exclude_unset``), so every existing response stays
byte-identical. ``DELETE /board/external-frame`` forgets it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src.main import BoardRuntime, DisplayService

DISPLAY_SERVICE = "src.display_runtime.get_service"

BOARDS = [
    {"id": "b1", "name": "Living Room", "device_type": "flagship", "api_mode": "local"},
    {"id": "b2", "name": "Kitchen", "device_type": "note", "api_mode": "local"},
]

# 2023-11-14T22:13:20+00:00
DETECTED_AT = 1_700_000_000.0


def grid(rows: int, cols: int, code: int) -> list[list[int]]:
    return [[code] * cols for _ in range(rows)]


FLAGSHIP_EXTERNAL = grid(6, 22, 8)
NOTE_EXTERNAL = grid(3, 15, 9)


@pytest.fixture
def settings(tmp_path, monkeypatch):
    import src.settings.service as settings_module

    svc = settings_module.SettingsService(settings_file=str(tmp_path / "settings.json"))
    svc.set_boards([dict(b) for b in BOARDS])
    monkeypatch.setattr(settings_module, "_settings_service", svc)
    return svc


@pytest.fixture
def service(monkeypatch):
    """A real DisplayService: two hardware runtimes, both with a poll cache."""
    svc = DisplayService()
    runtimes = {}
    for board_id, shape in (("b1", (6, 22)), ("b2", (3, 15))):
        client = MagicMock()
        client.is_virtual = False
        client.use_cloud = False
        rt = BoardRuntime(client=client, board_id=board_id)
        rt.polled_characters = grid(*shape, 1)
        rt.polled_at = DETECTED_AT
        runtimes[board_id] = rt
    svc.runtimes = runtimes
    svc._primary_board_id = "b1"
    monkeypatch.setattr(DISPLAY_SERVICE, lambda: svc)
    # Inside the TTL.
    monkeypatch.setattr(main_module.time, "time", lambda: DETECTED_AT + 60)
    return svc


@pytest.fixture
def client(settings):
    from src.api_server import app

    return TestClient(app)


class TestCurrentMessage:
    def test_current_message_carries_external_fields_when_held(self, client, service):
        service.runtimes["b1"].external_frame = (FLAGSHIP_EXTERNAL, DETECTED_AT)

        response = client.get("/board/current-message")

        assert response.status_code == 200
        body = response.json()
        assert body["external_characters"] == FLAGSHIP_EXTERNAL
        assert body["external_detected_at"] == "2023-11-14T22:13:20+00:00"

    def test_current_message_omits_external_keys_when_none(self, client, service):
        response = client.get("/board/current-message")

        assert response.status_code == 200
        body = response.json()
        assert "external_characters" not in body
        assert "external_detected_at" not in body

    def test_current_message_omits_a_frame_past_its_ttl(self, client, service, monkeypatch):
        service.runtimes["b1"].external_frame = (FLAGSHIP_EXTERNAL, DETECTED_AT)
        monkeypatch.setattr(main_module.time, "time", lambda: DETECTED_AT + main_module.EXTERNAL_FRAME_TTL_SECONDS + 1)

        body = client.get("/board/current-message").json()

        assert "external_characters" not in body

    def test_secondary_board_external_fields_are_per_board(self, client, service):
        service.runtimes["b2"].external_frame = (NOTE_EXTERNAL, DETECTED_AT)

        secondary = client.get("/board/current-message?board_id=b2").json()
        primary = client.get("/board/current-message").json()

        assert secondary["external_characters"] == NOTE_EXTERNAL
        assert "external_characters" not in primary

        service.runtimes["b2"].external_frame = None
        service.runtimes["b1"].external_frame = (FLAGSHIP_EXTERNAL, DETECTED_AT)

        assert "external_characters" not in client.get("/board/current-message?board_id=b2").json()
        assert client.get("/board/current-message?board_id=b1").json()["external_characters"] == FLAGSHIP_EXTERNAL


class TestDeleteExternalFrame:
    def test_delete_external_frame_clears_it(self, client, service):
        service.runtimes["b1"].external_frame = (FLAGSHIP_EXTERNAL, DETECTED_AT)

        response = client.delete("/board/external-frame")

        assert response.status_code == 204
        assert response.content == b""
        assert service.runtimes["b1"].external_frame is None
        assert "external_characters" not in client.get("/board/current-message").json()

    def test_delete_external_frame_targets_the_named_board_only(self, client, service):
        service.runtimes["b1"].external_frame = (FLAGSHIP_EXTERNAL, DETECTED_AT)
        service.runtimes["b2"].external_frame = (NOTE_EXTERNAL, DETECTED_AT)

        response = client.delete("/board/external-frame?board_id=b2")

        assert response.status_code == 204
        assert service.runtimes["b2"].external_frame is None
        assert service.runtimes["b1"].external_frame == (FLAGSHIP_EXTERNAL, DETECTED_AT)

    def test_delete_without_a_frame_is_still_204(self, client, service):
        assert client.delete("/board/external-frame").status_code == 204

    def test_delete_external_frame_unknown_board_is_404(self, client, service):
        response = client.delete("/board/external-frame?board_id=nope")

        assert response.status_code == 404

    def test_delete_external_frame_no_service_is_503(self, client, monkeypatch):
        monkeypatch.setattr(DISPLAY_SERVICE, lambda: None)

        response = client.delete("/board/external-frame")

        assert response.status_code == 503
