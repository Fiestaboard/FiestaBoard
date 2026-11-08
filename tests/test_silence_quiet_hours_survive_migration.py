"""A board's quiet hours survive the deferred per-board silence migration.

``ConfigManager.migrate_silence_schedule_to_per_board`` (issue #1788) seeds
``by_board`` from the install-wide window once, guarded by ``_raw_features``:
the features section as it was on disk at load. ``Config.is_silence_mode_active``
re-runs it whenever the config has been saved since it last ran, but only once
some window is enabled.

On a fresh install ``config.json`` does not exist yet, so ``_raw_features`` is
empty and the migration stays armed for the whole first process. Per-board
writes (a new board's seeded window, a quiet-hours edit from the web or phone)
went to the live config but never to that snapshot, so the first enabled
silence check replaced every board's window with the install-wide one, and
saved it. Anything reading quiet hours afterwards (the engine, panel status,
``next_change_at``) saw the install-wide window, disabled by default.
"""

from __future__ import annotations

import json

QUIET = {"enabled": True, "start_time": "06:00+00:00", "end_time": "15:00+00:00", "mode": "indicator"}


def _fresh_install_with_one_board(data_dir):
    from src.config_manager import get_config_manager
    from src.settings.service import get_settings_service

    assert not (data_dir / "config.json").exists()
    board_id = get_settings_service().set_boards([{"device_type": "flagship", "name": "Kitchen"}]).boards[0]["id"]
    return get_config_manager(), board_id


def test_a_boards_quiet_hours_survive_the_first_silence_check(_isolated_data_dir):
    from src.config import Config

    manager, board_id = _fresh_install_with_one_board(_isolated_data_dir)
    assert manager.set_silence_schedule_for_board(board_id, QUIET)

    Config.is_silence_mode_active(board_id)  # what every engine tick and panel status runs

    resolved = Config.silence_config_for(board_id)
    assert {key: resolved[key] for key in QUIET} == QUIET


def test_the_quiet_hours_on_disk_survive_too(_isolated_data_dir):
    from src.config import Config

    manager, board_id = _fresh_install_with_one_board(_isolated_data_dir)
    manager.set_silence_schedule_for_board(board_id, QUIET)
    Config.is_silence_mode_active(board_id)

    stored = json.loads((_isolated_data_dir / "config.json").read_text())["features"]["silence_schedule"]["by_board"]
    assert {key: stored[board_id][key] for key in QUIET} == QUIET


def test_panel_status_reports_the_boards_own_quiet_hours(_isolated_data_dir, monkeypatch):
    from datetime import UTC, datetime

    from src.panels.status import panel_status
    from src.time_service import TimeService

    class Frozen(TimeService):
        def get_current_utc(self):
            return datetime(2026, 11, 9, 7, 0, 0, 337_000, tzinfo=UTC)

    frozen = Frozen("America/Los_Angeles")
    monkeypatch.setattr("src.time_service.get_time_service", lambda: frozen)
    manager, board_id = _fresh_install_with_one_board(_isolated_data_dir)
    manager.set_silence_schedule_for_board(board_id, QUIET)

    status = panel_status(board_id)

    assert (status.silenced, status.silence_mode, status.silenced_until) == (
        True,
        "indicator",
        "2026-11-09T15:00:00+00:00",
    )


# --- Hardening (Fable re-review of #2452) -------------------------------------------


def _write_unstamped(manager, board_id, values):
    """A per-board window that reached the live config without the snapshot (any ordering)."""
    by_board = manager._config.setdefault("features", {}).setdefault("silence_schedule", {}).setdefault("by_board", {})
    by_board[board_id] = dict(values)
    manager._config_generation += 1


def test_pruning_a_board_stamps_the_migration_snapshot(_isolated_data_dir):
    from src.config import Config

    manager, keep = _fresh_install_with_one_board(_isolated_data_dir)
    manager._raw_features = {}  # the snapshot a pre-#1788 file, or a fresh one, starts with
    _write_unstamped(manager, keep, QUIET)
    _write_unstamped(manager, "gone", QUIET)
    assert manager.prune_silence_schedule_for_board("gone")

    Config.is_silence_mode_active(keep)

    resolved = Config.silence_config_for(keep)
    assert {key: resolved[key] for key in QUIET} == QUIET


def test_a_window_disabled_by_the_migration_is_not_silenced(_isolated_data_dir, monkeypatch):
    # is_silence_mode_active re-resolves after the migrations; it must re-check
    # "enabled" on what it re-resolved, not only on what it read first.
    from datetime import UTC, datetime

    from src.config import Config
    from src.time_service import TimeService

    class Frozen(TimeService):
        def get_current_utc(self):
            return datetime(2026, 11, 9, 7, 0, tzinfo=UTC)  # inside 06:00-15:00

    frozen = Frozen("America/Los_Angeles")
    monkeypatch.setattr("src.time_service.get_time_service", lambda: frozen)
    manager, board_id = _fresh_install_with_one_board(_isolated_data_dir)
    manager.set_silence_schedule_for_board(board_id, QUIET)

    def disables_the_window():
        manager._config["features"]["silence_schedule"]["by_board"][board_id]["enabled"] = False
        manager._config_generation += 1
        return 1

    monkeypatch.setattr(manager, "migrate_silence_schedule_to_per_board", disables_the_window)
    Config._silence_migrations_ran = None

    assert Config.is_silence_mode_active(board_id) is False
