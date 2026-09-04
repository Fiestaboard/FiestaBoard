"""Board-scoped silence schedule API (issue #1788).

``GET /silence-status`` takes an optional ``board_id`` query param and
``PUT /settings/silence-schedule`` takes an optional ``board_id`` in the
**body** (mirroring ``PUT /settings/active-page``; the path must not change
because the web client asserts it).

Also covers the second half of the issue: the silence page must be validated
against the *target board's* size, so a 22x6 Flagship page can no longer be
selected for a 15x3 Note.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app

FLAGSHIP = {"id": "flag-1", "name": "Kitchen", "device_type": "flagship"}
NOTE = {"id": "note-1", "name": "Desk", "device_type": "note"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def silence_store():
    """Config manager backed by a real dict, with per-board write support."""
    with patch("src.api_server.get_config_manager") as mock_get:
        cm = Mock()
        store = {
            "enabled": True,
            "start_time": "04:00+00:00",
            "end_time": "15:00+00:00",
            "mode": "freeze",
            "page_id": None,
            "indicator_text": "SNOOZING",
            "indicator_position": "center",
            "by_board": {},
        }

        def _get_feature(name):
            return dict(store) if name == "silence_schedule" else {}

        def _set_feature(name, value):
            if name != "silence_schedule":
                return False
            by_board = store.get("by_board", {})
            store.clear()
            store.update(value)
            store.setdefault("by_board", by_board)
            return True

        def _set_for_board(board_id, values):
            store.setdefault("by_board", {})[board_id] = dict(values)
            return True

        cm.get_feature.side_effect = _get_feature
        cm.set_feature.side_effect = _set_feature
        cm.set_silence_schedule_for_board.side_effect = _set_for_board
        cm.migrate_silence_schedule_to_utc.return_value = False
        cm.migrate_silence_schedule_to_per_board.return_value = 0
        mock_get.return_value = cm
        yield cm, store


@pytest.fixture
def boards():
    """Two boards of different sizes registered with the settings service."""
    with patch("src.api_server.get_settings_service") as mock_get:
        svc = Mock()
        svc.get_board_settings.return_value = Mock(boards=[FLAGSHIP, NOTE])
        svc.get_primary_board_id.return_value = FLAGSHIP["id"]
        mock_get.return_value = svc
        yield svc


class TestGetSilenceStatusPerBoard:
    def test_board_id_returns_that_boards_window(self, client, silence_store, boards):
        _cm, store = silence_store
        store["by_board"]["note-1"] = {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}

        data = client.get("/silence-status?board_id=note-1").json()

        assert data["start_time_utc"] == "06:00+00:00"
        assert data["end_time_utc"] == "12:00+00:00"
        assert data["board_id"] == "note-1"

    def test_unconfigured_board_falls_back_to_install_wide_window(self, client, silence_store, boards):
        data = client.get("/silence-status?board_id=flag-1").json()

        assert data["start_time_utc"] == "04:00+00:00"
        assert data["board_id"] == "flag-1"

    def test_omitting_board_id_reports_the_primary_board(self, client, silence_store, boards):
        """Runtime status, not a config dump: no board means the primary board.

        This replaces an assertion that omitting ``board_id`` returns the
        install-wide layer. That contract broke the single-board install: the
        settings form writes the board layer, so the dashboard overlay, the
        silence-imminent banner and this endpoint all kept reporting the
        pre-save window (PR #1801 review). The install-wide layer is still
        readable as raw config through ``GET /settings/all``.
        """
        _cm, store = silence_store
        store["by_board"]["flag-1"] = {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}

        data = client.get("/silence-status").json()

        assert data["start_time_utc"] == "06:00+00:00"
        assert data["end_time_utc"] == "12:00+00:00"
        assert data["board_id"] == "flag-1"

    def test_a_board_without_its_own_entry_still_reads_the_install_wide_window(self, client, silence_store, boards):
        """The primary board with no override inherits the install-wide values."""
        _cm, store = silence_store
        store["by_board"]["note-1"] = {"start_time": "06:00+00:00", "end_time": "12:00+00:00"}

        data = client.get("/silence-status").json()

        assert data["start_time_utc"] == "04:00+00:00"
        assert data["board_id"] == "flag-1"

    def test_per_board_mode_and_page_are_reported(self, client, silence_store, boards):
        _cm, store = silence_store
        store["by_board"]["note-1"] = {"mode": "page", "page_id": "note-night"}

        data = client.get("/silence-status?board_id=note-1").json()

        assert data["mode"] == "page"
        assert data["page_id"] == "note-night"

    def test_status_never_leaks_by_board(self, client, silence_store, boards):
        assert "by_board" not in client.get("/silence-status").json()


class TestPutSilenceSchedulePerBoard:
    def _body(self, **overrides):
        body = {"enabled": True, "start_time": "06:00+00:00", "end_time": "12:00+00:00"}
        body.update(overrides)
        return body

    def test_board_id_in_body_writes_only_that_board(self, client, silence_store, boards):
        cm, store = silence_store

        response = client.put("/settings/silence-schedule", json=self._body(board_id="note-1"))

        assert response.status_code == 200
        assert response.json()["board_id"] == "note-1"
        cm.set_feature.assert_not_called()
        assert store["by_board"]["note-1"]["start_time"] == "06:00+00:00"
        # The install-wide layer is untouched.
        assert store["start_time"] == "04:00+00:00"

    def test_omitting_board_id_still_writes_the_install_wide_layer(self, client, silence_store, boards):
        cm, store = silence_store

        response = client.put("/settings/silence-schedule", json=self._body())

        assert response.status_code == 200
        assert response.json()["board_id"] is None
        cm.set_feature.assert_called_once()
        assert store["start_time"] == "06:00+00:00"

    def test_unknown_board_returns_404(self, client, silence_store, boards):
        response = client.put("/settings/silence-schedule", json=self._body(board_id="ghost"))

        assert response.status_code == 404
        assert "ghost" in response.json()["detail"]

    def test_response_config_is_the_resolved_board_config(self, client, silence_store, boards):
        client.put(
            "/settings/silence-schedule",
            json=self._body(board_id="note-1", mode="indicator", indicator_text="hush"),
        )
        data = client.put("/settings/silence-schedule", json=self._body(board_id="note-1")).json()

        assert data["config"]["start_time"] == "06:00+00:00"
        assert "by_board" not in data["config"]

    def test_normalisation_rules_still_apply_per_board(self, client, silence_store, boards):
        data = client.put(
            "/settings/silence-schedule",
            json=self._body(board_id="note-1", mode="garbage", indicator_text="  hush  ", indicator_position="up"),
        ).json()

        assert data["config"]["mode"] == "freeze"
        assert data["config"]["indicator_text"] == "HUSH"
        assert data["config"]["indicator_position"] == "center"

    def test_page_mode_without_page_id_still_400s_per_board(self, client, silence_store, boards):
        response = client.put("/settings/silence-schedule", json=self._body(board_id="note-1", mode="page"))
        assert response.status_code == 400


class TestSilencePageBoardCompatibility:
    """Issue #1788 bug 2: the silence page must fit the target board."""

    def _compat(self, ok, error=None):
        return patch("src.api_server.check_ref_board_compatibility", return_value=Mock(ok=ok, error=error, warnings=[]))

    def test_flagship_page_is_rejected_for_a_note_board(self, client, silence_store, boards):
        with self._compat(False, "Page 'Big' (flagship) is not compatible with board 'Desk' (note)") as spy:
            response = client.put(
                "/settings/silence-schedule",
                json={
                    "enabled": True,
                    "start_time": "06:00+00:00",
                    "end_time": "12:00+00:00",
                    "mode": "page",
                    "page_id": "big-page",
                    "board_id": "note-1",
                },
            )

        assert response.status_code == 400
        assert "not compatible" in response.json()["detail"]
        spy.assert_called_once_with("big-page", "note-1")

    def test_compatible_page_is_accepted(self, client, silence_store, boards):
        with self._compat(True):
            response = client.put(
                "/settings/silence-schedule",
                json={
                    "enabled": True,
                    "start_time": "06:00+00:00",
                    "end_time": "12:00+00:00",
                    "mode": "page",
                    "page_id": "small-page",
                    "board_id": "note-1",
                },
            )

        assert response.status_code == 200

    def test_no_board_id_skips_the_board_check(self, client, silence_store, boards):
        """Legacy install-wide writes have no board to validate against."""
        with self._compat(False, "nope") as spy:
            response = client.put(
                "/settings/silence-schedule",
                json={
                    "enabled": True,
                    "start_time": "06:00+00:00",
                    "end_time": "12:00+00:00",
                    "mode": "page",
                    "page_id": "big-page",
                },
            )

        assert response.status_code == 200
        spy.assert_not_called()
