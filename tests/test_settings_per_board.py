"""Tests for the per-board settings foundation (issue #1242).

Covers:
  - settings.json schema_version + ordered migrations (v0->v1):
      * carousel:->collection: rewrite (folded from the old one-shot migration)
      * global active_page.page_id -> active_page.by_board[primary_id]
      * global schedule.enabled -> primary board schedule_enabled
      * idempotency, single-board no-op, and pre-migration backup
  - per-board active-page get/set for two boards (with primary mirror)
  - get_primary_board_id() / primary_board_id_from_raw()
  - per-board schedule_enabled authority
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.settings.service import (
    CURRENT_SETTINGS_SCHEMA_VERSION,
    ActivePageSettings,
    SettingsService,
    primary_board_id_from_raw,
)


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "settings.json")


@pytest.fixture
def mock_config():
    with patch("src.config.Config") as mock:
        mock.FB_TRANSITION_STRATEGY = "column"
        mock.FB_TRANSITION_INTERVAL_MS = 100
        mock.FB_TRANSITION_STEP_SIZE = 2
        mock.OUTPUT_TARGET = "board"
        yield mock


def _two_board_raw(active_page=None, schedule=None, schema_version=None):
    """Build a minimal raw settings dict with two boards (ids board-1/board-2)."""
    data = {
        "board": {
            "board_type": "black",
            "boards": [
                {"id": "board-1", "name": "Primary", "device_type": "flagship", "board_color": "black"},
                {"id": "board-2", "name": "Second", "device_type": "flagship", "board_color": "white"},
            ],
        },
    }
    if active_page is not None:
        data["active_page"] = active_page
    if schedule is not None:
        data["schedule"] = schedule
    if schema_version is not None:
        data["schema_version"] = schema_version
    return data


# ==================== ActivePageSettings dataclass ====================


class TestActivePageSettingsByBoard:
    def test_from_dict_parses_by_board(self):
        aps = ActivePageSettings.from_dict({"page_id": "p1", "by_board": {"b1": "p1", "b2": "p2"}})
        assert aps.page_id == "p1"
        assert aps.by_board == {"b1": "p1", "b2": "p2"}

    def test_from_dict_defaults_empty_by_board(self):
        aps = ActivePageSettings.from_dict({"page_id": "p1"})
        assert aps.by_board == {}

    def test_from_dict_ignores_malformed_by_board(self):
        aps = ActivePageSettings.from_dict({"by_board": {"b1": None, "b2": 5, "b3": "ok"}})
        assert aps.by_board == {"b3": "ok"}

    def test_to_dict_roundtrips(self):
        aps = ActivePageSettings(page_id="p1", by_board={"b1": "p1"})
        assert aps.to_dict() == {"page_id": "p1", "by_board": {"b1": "p1"}}


# ==================== primary board helper ====================


class TestPrimaryBoardHelpers:
    def test_primary_board_id_from_raw(self):
        assert primary_board_id_from_raw(_two_board_raw()) == "board-1"

    def test_primary_board_id_from_raw_empty(self):
        assert primary_board_id_from_raw({"board": {"boards": []}}) is None
        assert primary_board_id_from_raw({}) is None
        assert primary_board_id_from_raw({"board": {"boards": [{"name": "no id"}]}}) is None

    def test_get_primary_board_id_matches_first_board(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps(_two_board_raw()))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_primary_board_id() == "board-1"

    def test_get_primary_board_id_default_board(self, settings_file, mock_config):
        # Fresh service auto-creates a default board with a generated id.
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_primary_board_id() == svc._board.boards[0]["id"]


# ==================== migration: carousel rewrite ====================


class TestCarouselMigration:
    def test_rewrites_active_page_and_override_refs(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(
                _two_board_raw(
                    active_page={"page_id": "carousel:abc"},
                    schedule={"enabled": False},
                )
                | {
                    "temporary_override": {
                        "page_id": "carousel:def",
                        "expires_at": "2999-01-01T00:00:00+00:00",
                        "revert_mode": "page",
                        "revert_page_id": "carousel:ghi",
                    }
                }
            )
        )
        SettingsService(settings_file=settings_file)
        data = json.loads(Path(settings_file).read_text())
        # active_page.page_id rewritten and moved to by_board for primary
        assert data["active_page"]["page_id"] == "collection:abc"
        assert data["active_page"]["by_board"]["board-1"] == "collection:abc"
        assert data["temporary_override"]["page_id"] == "collection:def"
        assert data["temporary_override"]["revert_page_id"] == "collection:ghi"


# ==================== migration: global active page -> primary board ====================


class TestActivePageMigration:
    def test_global_active_page_moves_to_primary_board(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(_two_board_raw(active_page={"page_id": "page-1"}))
        )
        svc = SettingsService(settings_file=settings_file)

        data = json.loads(Path(settings_file).read_text())
        assert data["active_page"]["by_board"]["board-1"] == "page-1"
        # Legacy mirror kept for back-compat.
        assert data["active_page"]["page_id"] == "page-1"
        assert data["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

        # Reading with no board_id returns the same value as before (primary).
        assert svc.get_active_page_id() == "page-1"
        assert svc.get_active_page_id(board_id="board-1") == "page-1"
        # The second board did not inherit the global active page.
        assert svc.get_active_page_id(board_id="board-2") is None

    def test_skips_when_by_board_already_set(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(
                _two_board_raw(active_page={"page_id": "page-1", "by_board": {"board-1": "already"}})
            )
        )
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_active_page_id(board_id="board-1") == "already"

    def test_deferred_when_no_boards(self, settings_file, mock_config):
        # No boards configured yet: leave the mirror, read-path fallback covers it.
        Path(settings_file).write_text(
            json.dumps({"active_page": {"page_id": "page-1"}, "board": {"boards": []}})
        )
        svc = SettingsService(settings_file=settings_file)
        # A default board is created on load; read with no board_id still returns
        # the mirror value (no by_board entry was written by the migration).
        assert svc.get_active_page_id() == "page-1"


# ==================== migration: schedule_enabled -> primary board ====================


class TestScheduleEnabledMigration:
    def test_global_schedule_enabled_moves_to_primary(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(_two_board_raw(schedule={"enabled": True}))
        )
        svc = SettingsService(settings_file=settings_file)

        data = json.loads(Path(settings_file).read_text())
        assert data["board"]["boards"][0]["schedule_enabled"] is True
        # Second board untouched.
        assert "schedule_enabled" not in data["board"]["boards"][1] or (
            data["board"]["boards"][1].get("schedule_enabled") is False
        )

        assert svc.is_schedule_enabled() is True
        assert svc.is_schedule_enabled(board_id="board-1") is True
        assert svc.is_schedule_enabled(board_id="board-2") is False

    def test_does_not_override_existing_primary_flag(self, settings_file, mock_config):
        raw = _two_board_raw(schedule={"enabled": True})
        raw["board"]["boards"][0]["schedule_enabled"] = False
        Path(settings_file).write_text(json.dumps(raw))
        svc = SettingsService(settings_file=settings_file)
        assert svc.is_schedule_enabled(board_id="board-1") is False

    def test_global_disabled_no_change(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(_two_board_raw(schedule={"enabled": False}))
        )
        svc = SettingsService(settings_file=settings_file)
        assert svc.is_schedule_enabled(board_id="board-1") is False


# ==================== migration: idempotency, backup, single-board no-op ====================


class TestMigrationMechanics:
    def test_idempotent_rerun_is_noop(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(_two_board_raw(active_page={"page_id": "page-1"}, schedule={"enabled": True}))
        )
        SettingsService(settings_file=settings_file)
        first = Path(settings_file).read_text()

        # Re-instantiating runs migrations again; already-current file is a no-op.
        SettingsService(settings_file=settings_file)
        second = Path(settings_file).read_text()
        assert json.loads(first)["active_page"] == json.loads(second)["active_page"]
        assert json.loads(second)["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION

    def test_backup_created_before_migration(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(_two_board_raw(active_page={"page_id": "page-1"}))
        )
        SettingsService(settings_file=settings_file)
        backup = Path(settings_file).with_suffix(".json.v0_backup")
        assert backup.exists()
        # Backup preserves the pre-migration content (no schema_version, no by_board).
        backup_data = json.loads(backup.read_text())
        assert "schema_version" not in backup_data
        assert "by_board" not in backup_data.get("active_page", {})

    def test_no_backup_when_already_current(self, settings_file, mock_config):
        raw = _two_board_raw(
            active_page={"page_id": "page-1", "by_board": {"board-1": "page-1"}},
            schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
        )
        Path(settings_file).write_text(json.dumps(raw))
        SettingsService(settings_file=settings_file)
        backup = Path(settings_file).with_suffix(f".json.v{CURRENT_SETTINGS_SCHEMA_VERSION}_backup")
        assert not backup.exists()

    def test_single_board_zero_behavior_change(self, settings_file, mock_config):
        """The #1 acceptance criterion: a single-board install migrates with no
        observable behavior change. Global active page -> primary board; reading
        with no board_id returns the same value; schedule flag preserved."""
        raw = {
            "active_page": {"page_id": "my-page"},
            "schedule": {"enabled": True},
            "board": {
                "board_type": "black",
                "boards": [{"id": "only-board", "name": "My Board", "device_type": "flagship"}],
            },
        }
        Path(settings_file).write_text(json.dumps(raw))
        svc = SettingsService(settings_file=settings_file)

        # Reads with no board_id behave exactly as before migration.
        assert svc.get_active_page_id() is None or svc.get_active_page_id() == "my-page"
        assert svc.get_active_page_id() == "my-page"
        assert svc.is_schedule_enabled() is True
        # And these resolve to the single board.
        assert svc.get_active_page_id(board_id="only-board") == "my-page"
        assert svc.is_schedule_enabled(board_id="only-board") is True


# ==================== per-board active page get/set ====================


class TestPerBoardActivePage:
    @pytest.fixture
    def two_board_service(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps(_two_board_raw()))
        return SettingsService(settings_file=settings_file)

    def test_set_get_independent_per_board(self, two_board_service):
        svc = two_board_service
        svc.set_active_page_id("page-A", board_id="board-1")
        svc.set_active_page_id("page-B", board_id="board-2")
        assert svc.get_active_page_id(board_id="board-1") == "page-A"
        assert svc.get_active_page_id(board_id="board-2") == "page-B"
        # Default (None) resolves to the primary board.
        assert svc.get_active_page_id() == "page-A"

    def test_set_primary_updates_mirror(self, two_board_service):
        svc = two_board_service
        svc.set_active_page_id("page-A")  # None -> primary (board-1)
        assert svc._active_page.page_id == "page-A"
        assert svc._active_page.by_board["board-1"] == "page-A"

    def test_set_secondary_does_not_touch_mirror(self, two_board_service):
        svc = two_board_service
        svc.set_active_page_id("page-B", board_id="board-2")
        assert svc._active_page.page_id is None
        assert "board-1" not in svc._active_page.by_board

    def test_clear_per_board(self, two_board_service):
        svc = two_board_service
        svc.set_active_page_id("page-A", board_id="board-1")
        svc.set_active_page_id(None, board_id="board-1")
        assert svc.get_active_page_id(board_id="board-1") is None
        assert "board-1" not in svc._active_page.by_board

    def test_unknown_board_returns_none(self, two_board_service):
        assert two_board_service.get_active_page_id(board_id="does-not-exist") is None

    def test_persists_across_reload(self, settings_file, two_board_service):
        svc = two_board_service
        svc.set_active_page_id("page-A", board_id="board-1")
        svc.set_active_page_id("page-B", board_id="board-2")
        reloaded = SettingsService(settings_file=settings_file)
        assert reloaded.get_active_page_id(board_id="board-1") == "page-A"
        assert reloaded.get_active_page_id(board_id="board-2") == "page-B"


# ==================== per-board schedule_enabled ====================


class TestPerBoardScheduleEnabled:
    @pytest.fixture
    def two_board_service(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps(_two_board_raw()))
        return SettingsService(settings_file=settings_file)

    def test_independent_per_board(self, two_board_service):
        svc = two_board_service
        svc.set_schedule_enabled(True, board_id="board-2")
        assert svc.is_schedule_enabled(board_id="board-1") is False
        assert svc.is_schedule_enabled(board_id="board-2") is True

    def test_set_none_writes_primary_and_mirror(self, two_board_service):
        svc = two_board_service
        svc.set_schedule_enabled(True)  # None -> primary
        assert svc.is_schedule_enabled(board_id="board-1") is True
        assert svc.is_schedule_enabled() is True
        # Deprecated mirror kept in sync for the primary board.
        assert svc._schedule.enabled is True

    def test_set_secondary_does_not_touch_mirror(self, two_board_service):
        svc = two_board_service
        svc.set_schedule_enabled(True, board_id="board-2")
        assert svc._schedule.enabled is False

    def test_unknown_board_returns_false(self, two_board_service):
        assert two_board_service.is_schedule_enabled(board_id="nope") is False

    def test_no_boards_falls_back_to_global_mirror(self, settings_file, mock_config):
        svc = SettingsService(settings_file=settings_file)
        svc._board.boards = []
        svc._schedule.enabled = True
        assert svc.is_schedule_enabled() is True

    def test_set_with_no_boards_writes_global_mirror(self, settings_file, mock_config):
        svc = SettingsService(settings_file=settings_file)
        svc._board.boards = []
        result = svc.set_schedule_enabled(True)
        assert result.enabled is True
        assert svc.is_schedule_enabled() is True
