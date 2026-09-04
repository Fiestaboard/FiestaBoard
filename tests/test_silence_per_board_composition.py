"""Composition of the per-board silence layers (issue #1788, PR #1801 review).

The per-board silence PR shipped a correct write path, a correct read path and
a correct migration — and the three did not agree.  The migration seeded
``features.silence_schedule.by_board[<board>]`` for **every** configured board
(single-board installs included), the engine always resolves per board, and the
UI wrote the *install-wide* layer whenever there was only one board.  The
board-scoped copy then shadowed every subsequent save: the user turned silence
off, the UI said off, and the board kept snoozing at the old time forever.

These tests pin the composition rather than the pieces:

  - a single-board install's save is what the engine resolves, whichever layer
    the client writes
  - the same holds after a 2-board install is reduced to 1 (the surviving
    board keeps its seeded override while the client flips back to
    install-wide writes)
  - removing a board prunes its override instead of leaving an orphan
  - seeding the migration never re-enters ``ConfigManager._file_lock``
"""

import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.config import Config
from src.config_manager import ConfigManager

LEGACY_INSTALL_WIDE = {
    "enabled": True,
    "start_time": "20:00+00:00",
    "end_time": "07:00+00:00",
    "mode": "indicator",
    "page_id": None,
    "indicator_text": "SNOOZING",
    "indicator_position": "center",
}

BOARD_1 = {"id": "board-1", "name": "Kitchen", "device_type": "flagship", "enabled": True}
BOARD_2 = {"id": "board-2", "name": "Desk", "device_type": "note", "enabled": True}


def _write_config(path: Path, silence: dict) -> None:
    path.write_text(json.dumps({"features": {"silence_schedule": silence}}))


@pytest.fixture
def real_config(tmp_path: Path):
    """A real ConfigManager singleton backed by a legacy (pre-#1788) config."""
    ConfigManager._instance = None
    path = tmp_path / "config.json"
    _write_config(path, dict(LEGACY_INSTALL_WIDE))
    manager = ConfigManager(config_path=str(path))
    yield manager
    ConfigManager._instance = None


def _boards(*boards):
    """Patch every settings-service lookup used by the silence paths."""
    service = Mock()
    service.get_board_settings.return_value = Mock(boards=list(boards))
    service.get_primary_board_id.return_value = boards[0]["id"] if boards else None
    return service


def _patch_settings(service):
    return (
        patch("src.settings.service.get_settings_service", return_value=service),
        patch("src.api_server.get_settings_service", return_value=service),
    )


def _save_via_api(client, body: dict) -> None:
    response = client.put("/settings/silence-schedule", json=body)
    assert response.status_code == 200, response.text


# ==================== single-board composition ====================


class TestSingleBoardComposition:
    """The layer the client writes must be the layer the engine reads."""

    def test_single_board_install_save_is_honored_by_the_engine(self, real_config):
        """A single-board install turns silence off; the engine must see it off.

        The migration seeds ``by_board["board-1"]`` from the install-wide
        window, so an install-wide save is shadowed key-by-key unless the two
        layers are reconciled.
        """
        service = _boards(BOARD_1)
        p1, p2 = _patch_settings(service)
        with p1, p2:
            assert real_config.migrate_silence_schedule_to_per_board() >= 0

            client = TestClient(app)
            _save_via_api(
                client,
                {
                    "enabled": False,
                    "start_time": "22:30+00:00",
                    "end_time": "07:00+00:00",
                    "mode": "indicator",
                },
            )

            resolved = Config.silence_config_for("board-1")

        assert resolved["enabled"] is False
        assert resolved["start_time"] == "22:30+00:00"

    def test_board_scoped_save_is_honored_by_the_engine(self, real_config):
        """The board-scoped write path resolves for the board the engine drives."""
        service = _boards(BOARD_1)
        p1, p2 = _patch_settings(service)
        with p1, p2:
            real_config.migrate_silence_schedule_to_per_board()

            client = TestClient(app)
            _save_via_api(
                client,
                {
                    "enabled": False,
                    "start_time": "23:15+00:00",
                    "end_time": "06:00+00:00",
                    "mode": "indicator",
                    "board_id": "board-1",
                },
            )

            resolved = Config.silence_config_for(service.get_primary_board_id())

        assert resolved["enabled"] is False
        assert resolved["start_time"] == "23:15+00:00"

    def test_save_after_dropping_from_two_boards_to_one_is_honored(self, real_config):
        """2 -> 1 board deletion must not strand the survivor's seeded override.

        Reachable without the migration ever running on a single-board install:
        the client flips back to install-wide writes as soon as only one board
        is left, while the survivor still carries a board-scoped copy.
        """
        two = _boards(BOARD_1, BOARD_2)
        p1, p2 = _patch_settings(two)
        with p1, p2:
            real_config.migrate_silence_schedule_to_per_board()

        one = _boards(BOARD_1)
        p1, p2 = _patch_settings(one)
        with p1, p2:
            client = TestClient(app)
            _save_via_api(
                client,
                {
                    "enabled": False,
                    "start_time": "21:45+00:00",
                    "end_time": "05:30+00:00",
                    "mode": "indicator",
                },
            )

            resolved = Config.silence_config_for("board-1")

        assert resolved["enabled"] is False
        assert resolved["start_time"] == "21:45+00:00"


# ==================== orphan pruning ====================


class TestBoardRemovalPrunesOverrides:
    def test_remove_board_prunes_its_silence_override(self, real_config, tmp_path):
        """Removing a board deletes its ``by_board`` entry (issue #1788 review)."""
        from src.settings.service import SettingsService

        real_config.set_silence_schedule_for_board(
            "board-1", {"enabled": True, "start_time": "01:00+00:00", "end_time": "02:00+00:00"}
        )
        real_config.set_silence_schedule_for_board(
            "board-2", {"enabled": True, "start_time": "03:00+00:00", "end_time": "04:00+00:00"}
        )

        service = SettingsService.__new__(SettingsService)
        service._board = Mock(boards=[dict(BOARD_1), dict(BOARD_2)])
        service._save_to_file = Mock()

        service.remove_board("board-2")

        by_board = real_config.get_feature("silence_schedule")["by_board"]
        assert "board-2" not in by_board
        assert by_board["board-1"]["start_time"] == "01:00+00:00"


# ==================== lock re-entrancy ====================


class TestMigrationLockSafety:
    def test_seeding_migration_does_not_hold_the_config_lock_across_the_board_lookup(self, real_config):
        """``_configured_board_ids()`` must run OUTSIDE ``_file_lock``.

        ``get_settings_service()`` constructs a ``SettingsService`` whose
        ``__init__`` reads ``FB_TRANSITION_STRATEGY`` -> ``Config._get_board()``
        -> ``ConfigManager.get_board()``, which takes ``_file_lock``. Calling it
        from inside the migration's ``with`` block self-deadlocked the whole
        process while ``_file_lock`` was a plain ``threading.Lock``: held
        forever, every config read blocked, no exception and no timeout.

        #1746 has since made ``_file_lock`` an ``RLock``, so the same-thread
        re-entry no longer hangs — but that is an implementation detail of the
        lock, not a property of this code. The invariant pinned here is the
        durable one: the config lock is free while the settings service is
        being built. A probe thread proves it, so this fails whether the lock
        is reentrant or not.
        """
        lock_was_free: dict[str, bool] = {}

        def _settings_service_that_reads_config():
            # Another thread must be able to touch config while this runs.
            def _probe():
                acquired = real_config._file_lock.acquire(timeout=2)
                lock_was_free["free"] = acquired
                if acquired:
                    real_config._file_lock.release()

            probe = threading.Thread(target=_probe, daemon=True)
            probe.start()
            probe.join(timeout=5)
            # Exactly what SettingsService.__init__ does today.
            real_config.get_board()
            return _boards(BOARD_1)

        result: dict[str, object] = {}

        def _run():
            try:
                with patch(
                    "src.settings.service.get_settings_service",
                    side_effect=_settings_service_that_reads_config,
                ):
                    result["seeded"] = real_config.migrate_silence_schedule_to_per_board()
            except BaseException as exc:  # pragma: no cover - surfaced via result
                result["error"] = exc

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=15)

        assert not worker.is_alive(), (
            "migrate_silence_schedule_to_per_board() deadlocked: it called "
            "get_settings_service() while holding ConfigManager._file_lock"
        )
        assert "error" not in result, result.get("error")
        assert lock_was_free.get("free") is True, (
            "ConfigManager._file_lock was held across get_settings_service(); "
            "that call reads config through ConfigManager.get_board()"
        )
        assert result["seeded"] == 1
