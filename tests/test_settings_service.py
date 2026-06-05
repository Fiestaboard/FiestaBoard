"""Tests for src.settings.service module.

Tests dataclasses (TransitionSettings, OutputSettings, ActivePageSettings,
PollingSettings, BoardSettings, ScheduleSettings) and SettingsService class
that manages runtime settings persisted to JSON.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.settings.service import (
    VALID_OUTPUT_TARGETS,
    ActivePageSettings,
    BetaSettings,
    BoardSettings,
    DisplaySettings,
    OutputSettings,
    PollingSettings,
    ScheduleSettings,
    SettingsService,
    TransitionSettings,
    get_settings_service,
)

# ==================== TransitionSettings ====================


class TestTransitionSettings:
    """Test TransitionSettings dataclass."""

    def test_from_dict_with_all_fields(self):
        data = {"strategy": "column", "step_interval_ms": 100, "step_size": 2}
        ts = TransitionSettings.from_dict(data)
        assert ts.strategy == "column"
        assert ts.step_interval_ms == 100
        assert ts.step_size == 2

    def test_from_dict_with_partial_fields(self):
        data = {"strategy": "random"}
        ts = TransitionSettings.from_dict(data)
        assert ts.strategy == "random"
        assert ts.step_interval_ms is None
        assert ts.step_size is None

    def test_from_dict_empty(self):
        ts = TransitionSettings.from_dict({})
        assert ts.strategy is None
        assert ts.step_interval_ms is None
        assert ts.step_size is None

    def test_to_dict(self):
        ts = TransitionSettings(strategy="diagonal", step_interval_ms=50, step_size=1)
        d = ts.to_dict()
        assert d == {"strategy": "diagonal", "step_interval_ms": 50, "step_size": 1}


# ==================== OutputSettings ====================


class TestOutputSettings:
    """Test OutputSettings dataclass."""

    def test_from_dict_valid_target(self):
        for target in VALID_OUTPUT_TARGETS:
            os = OutputSettings.from_dict({"target": target})
            assert os.target == target

    def test_from_dict_invalid_target_defaults_to_board(self):
        os = OutputSettings.from_dict({"target": "invalid"})
        assert os.target == "board"

    def test_from_dict_empty_defaults_to_board(self):
        os = OutputSettings.from_dict({})
        assert os.target == "board"

    def test_to_dict(self):
        os = OutputSettings(target="both")
        assert os.to_dict() == {"target": "both"}


# ==================== ActivePageSettings ====================


class TestActivePageSettings:
    """Test ActivePageSettings dataclass."""

    def test_from_dict_with_page_id(self):
        aps = ActivePageSettings.from_dict({"page_id": "page-123"})
        assert aps.page_id == "page-123"

    def test_from_dict_empty(self):
        aps = ActivePageSettings.from_dict({})
        assert aps.page_id is None

    def test_to_dict(self):
        aps = ActivePageSettings(page_id="abc")
        assert aps.to_dict() == {"page_id": "abc"}


# ==================== PollingSettings ====================


class TestPollingSettings:
    """Test PollingSettings dataclass."""

    def test_from_dict_valid_interval(self):
        ps = PollingSettings.from_dict({"interval_seconds": 60})
        assert ps.interval_seconds == 60

    def test_from_dict_below_minimum_enforced_to_10(self):
        ps = PollingSettings.from_dict({"interval_seconds": 5})
        assert ps.interval_seconds == 10

    def test_from_dict_zero_enforced_to_10(self):
        ps = PollingSettings.from_dict({"interval_seconds": 0})
        assert ps.interval_seconds == 10

    def test_from_dict_empty_defaults_to_15(self):
        ps = PollingSettings.from_dict({})
        assert ps.interval_seconds == 15

    def test_to_dict(self):
        ps = PollingSettings(interval_seconds=15)
        d = ps.to_dict()
        assert d["interval_seconds"] == 15
        assert d["board_read_interval_local"] == 30
        assert d["board_read_interval_cloud"] == 180


# ==================== BoardSettings ====================


class TestBoardSettings:
    """Test BoardSettings dataclass."""

    def test_post_init_creates_default_board_when_boards_empty(self):
        with patch("src.devices.BoardInstance") as mock_bi:
            mock_bi.return_value.to_dict.return_value = {
                "name": "My Board",
                "device_type": "flagship",
                "board_color": "black",
            }
            bs = BoardSettings(boards=[])
            assert len(bs.boards) == 1
            mock_bi.assert_called_once_with(
                name="My Board",
                device_type="flagship",
                board_color="black",
            )

    def test_post_init_with_existing_boards_unchanged(self):
        existing = [{"name": "Board 1", "device_type": "flagship"}]
        bs = BoardSettings(boards=existing)
        assert bs.boards == existing

    def test_devices_returns_unique_device_types(self):
        boards = [
            {"device_type": "flagship"},
            {"device_type": "note"},
            {"device_type": "flagship"},
        ]
        bs = BoardSettings(boards=boards)
        assert bs.devices == ["flagship", "note"]

    def test_devices_falls_back_to_flagship_when_empty_or_invalid(self):
        bs = BoardSettings(boards=[{"device_type": "unknown_type"}])
        assert bs.devices == ["flagship"]

    def test_devices_falls_back_when_boards_empty(self):
        with patch("src.devices.BoardInstance") as mock_bi:
            mock_bi.return_value.to_dict.return_value = {"device_type": "invalid"}
            bs = BoardSettings(boards=[])
            assert bs.devices == ["flagship"]

    def test_mask_board_masks_sensitive_fields(self):
        board = {"name": "B", "local_api_key": "secret", "cloud_key": "cloud-secret"}
        masked = BoardSettings._mask_board(board)
        assert masked["local_api_key"] == "***"
        assert masked["cloud_key"] == "***"
        assert masked["name"] == "B"

    def test_mask_board_skips_empty_sensitive_fields(self):
        board = {"name": "B", "local_api_key": "", "cloud_key": ""}
        masked = BoardSettings._mask_board(board)
        assert masked["local_api_key"] == ""
        assert masked["cloud_key"] == ""

    def test_to_dict_with_mask_secrets(self):
        bs = BoardSettings(boards=[{"name": "B", "local_api_key": "key"}])
        d = bs.to_dict(mask_secrets=True)
        assert d["boards"][0]["local_api_key"] == "***"

    def test_to_dict_without_mask_secrets(self):
        bs = BoardSettings(boards=[{"name": "B", "local_api_key": "key"}])
        d = bs.to_dict(mask_secrets=False)
        assert d["boards"][0]["local_api_key"] == "key"

    def test_from_dict_with_boards(self):
        boards = [{"name": "B1", "device_type": "flagship"}]
        bs = BoardSettings.from_dict({"board_type": "white", "boards": boards})
        assert bs.board_type == "white"
        assert bs.boards == boards

    def test_from_dict_legacy_devices_only_format(self):
        with patch("src.devices.BoardInstance") as mock_bi:
            mock_bi.return_value.to_dict.side_effect = [
                {"name": "My Board", "device_type": "flagship"},
                {"name": "My Board 2", "device_type": "note"},
            ]
            bs = BoardSettings.from_dict({"devices": ["flagship", "note"]})
            assert len(bs.boards) == 2
            assert mock_bi.call_count == 2

    def test_from_dict_invalid_board_type_defaults_to_black(self):
        bs = BoardSettings.from_dict({"board_type": "invalid", "boards": [{}]})
        assert bs.board_type == "black"


# ==================== ScheduleSettings ====================


class TestScheduleSettings:
    """Test ScheduleSettings dataclass."""

    def test_from_dict_enabled(self):
        ss = ScheduleSettings.from_dict({"enabled": True})
        assert ss.enabled is True

    def test_from_dict_disabled(self):
        ss = ScheduleSettings.from_dict({"enabled": False})
        assert ss.enabled is False

    def test_from_dict_empty_defaults_to_false(self):
        ss = ScheduleSettings.from_dict({})
        assert ss.enabled is False

    def test_to_dict(self):
        ss = ScheduleSettings(enabled=True)
        assert ss.to_dict() == {"enabled": True}


# ==================== SettingsService ====================


@pytest.fixture
def settings_file(tmp_path):
    """Path to a temporary settings file."""
    return str(tmp_path / "settings.json")


@pytest.fixture
def mock_config():
    """Mock Config for transition/output fallback."""
    with patch("src.config.Config") as mock:
        mock.FB_TRANSITION_STRATEGY = "column"
        mock.FB_TRANSITION_INTERVAL_MS = 100
        mock.FB_TRANSITION_STEP_SIZE = 2
        mock.OUTPUT_TARGET = "board"
        yield mock


@pytest.fixture
def settings_service(settings_file, mock_config):
    """Create SettingsService with tmp_path settings file."""
    return SettingsService(settings_file=settings_file)


class TestSettingsServiceInit:
    """Test SettingsService initialization."""

    def test_init_with_custom_settings_file(self, tmp_path):
        path = tmp_path / "custom.json"
        svc = SettingsService(settings_file=str(path))
        assert svc.settings_file == path

    def test_init_without_settings_file_uses_default_path(self, mock_config):
        svc = SettingsService(settings_file=None)
        assert "data" in str(svc.settings_file)
        assert svc.settings_file.name == "settings.json"

    def test_load_from_file_returns_empty_when_file_missing(self, settings_file, mock_config):
        svc = SettingsService(settings_file=settings_file)
        # Use a path that was never written to (service may have saved during init)
        svc.settings_file = Path(settings_file).parent / "nonexistent.json"
        result = svc._load_from_file()
        assert result == {}

    def test_load_from_file_handles_invalid_json(self, settings_file, mock_config):
        svc = SettingsService(settings_file=settings_file)
        Path(settings_file).write_text("not valid json {")
        result = svc._load_from_file()
        assert result == {}

    def test_load_from_file_handles_io_error(self, settings_file, mock_config):
        Path(settings_file).write_text("{}")
        with patch("builtins.open", side_effect=OSError("read error")):
            svc = SettingsService(settings_file=settings_file)
            result = svc._load_from_file()
        assert result == {}

    def test_save_to_file_writes_json(self, settings_service, settings_file):
        settings_service._save_to_file()
        data = json.loads(Path(settings_file).read_text())
        assert "transitions" in data
        assert "output" in data
        assert "board" in data

    def test_save_to_file_handles_io_error(self, settings_service):
        with patch("builtins.open", side_effect=OSError("write error")):
            settings_service._save_to_file()  # Should not raise


class TestSettingsServiceTransitions:
    """Test SettingsService transition settings."""

    def test_get_transition_settings(self, settings_service):
        ts = settings_service.get_transition_settings()
        assert isinstance(ts, TransitionSettings)

    def test_update_transition_settings_valid_strategy(self, settings_service):
        result = settings_service.update_transition_settings(strategy="random")
        assert result.strategy == "random"

    def test_update_transition_settings_step_interval_only(self, settings_service):
        result = settings_service.update_transition_settings(strategy=..., step_interval_ms=150, step_size=...)
        assert result.step_interval_ms == 150

    def test_update_transition_settings_invalid_strategy_raises(self, settings_service):
        with pytest.raises(ValueError, match="Invalid strategy"):
            settings_service.update_transition_settings(strategy="invalid")


class TestSettingsServiceOutput:
    """Test SettingsService output settings."""

    def test_set_output_target_valid(self, settings_service):
        for target in VALID_OUTPUT_TARGETS:
            result = settings_service.set_output_target(target)
            assert result.target == target

    def test_set_output_target_invalid_raises(self, settings_service):
        with pytest.raises(ValueError, match="Invalid target"):
            settings_service.set_output_target("invalid")

    def test_should_send_to_board_board_target(self, settings_service):
        settings_service.set_output_target("board")
        assert settings_service.should_send_to_board() is True

    def test_should_send_to_board_both_target(self, settings_service):
        settings_service.set_output_target("both")
        assert settings_service.should_send_to_board() is True

    def test_should_send_to_board_ui_target(self, settings_service):
        settings_service.set_output_target("ui")
        assert settings_service.should_send_to_board() is False

    def test_should_send_to_ui_always_true(self, settings_service):
        assert settings_service.should_send_to_ui() is True


class TestSettingsServiceActivePage:
    """Test SettingsService active page settings."""

    def test_get_set_active_page_id(self, settings_service):
        settings_service.set_active_page_id("page-1")
        assert settings_service.get_active_page_id() == "page-1"

    def test_set_active_page_id_none(self, settings_service):
        settings_service.set_active_page_id(None)
        assert settings_service.get_active_page_id() is None

    def test_get_active_page_settings(self, settings_service):
        settings_service.set_active_page_id("page-x")
        aps = settings_service.get_active_page_settings()
        assert aps.page_id == "page-x"


class TestSettingsServicePolling:
    """Test SettingsService polling settings."""

    def test_set_polling_interval_valid(self, settings_service):
        result = settings_service.set_polling_interval(30)
        assert result.interval_seconds == 30
        assert settings_service.get_polling_interval() == 30

    def test_set_polling_interval_below_min_raises(self, settings_service):
        with pytest.raises(ValueError, match="at least 10 seconds"):
            settings_service.set_polling_interval(5)


class TestSettingsServiceBoard:
    """Test SettingsService board settings."""

    def test_set_board_type_valid(self, settings_service):
        settings_service.set_board_type("white")
        assert settings_service.get_board_settings().board_type == "white"

    def test_set_board_type_invalid_raises(self, settings_service):
        with pytest.raises(ValueError, match="Invalid board_type"):
            settings_service.set_board_type("invalid")

    def test_set_devices_valid(self, settings_service):
        result = settings_service.set_devices(["flagship", "note"])
        assert len(result.boards) == 2

    def test_set_devices_invalid_raises(self, settings_service):
        with pytest.raises(ValueError, match="At least one valid device"):
            settings_service.set_devices(["invalid_type"])

    def test_set_devices_empty_list_raises(self, settings_service):
        with pytest.raises(ValueError, match="At least one valid device"):
            settings_service.set_devices([])

    def test_set_boards_preserves_masked_sensitive_fields(self, settings_service):
        settings_service.set_boards([{"device_type": "flagship", "local_api_key": "secret"}])
        settings_service.set_boards(
            [{"device_type": "flagship", "id": settings_service._board.boards[0]["id"], "local_api_key": "***"}]
        )
        assert settings_service._board.boards[0]["local_api_key"] == "secret"

    def test_set_boards_empty_raises(self, settings_service):
        with pytest.raises(ValueError, match="At least one board"):
            settings_service.set_boards([])

    def test_add_board(self, settings_service):
        result = settings_service.add_board({"device_type": "note"})
        assert len(result.boards) == 2

    def test_add_board_with_name(self, settings_service):
        result = settings_service.add_board({"name": "Custom", "device_type": "note"})
        assert any(b.get("name") == "Custom" for b in result.boards)

    def test_next_board_name_first_available(self, settings_service):
        # Default board is "My Board", so first available is "My Board 2" if taken
        settings_service._board.boards = []
        name = settings_service._next_board_name()
        assert name == "My Board"

    def test_next_board_name_increments_when_taken(self, settings_service):
        settings_service._board.boards = [{"name": "My Board"}]
        name = settings_service._next_board_name()
        assert name == "My Board 2"

    def test_remove_board(self, settings_service):
        settings_service.add_board({"device_type": "note"})
        board_id = settings_service._board.boards[1]["id"]
        result = settings_service.remove_board(board_id)
        assert len(result.boards) == 1

    def test_remove_board_last_raises(self, settings_service):
        with pytest.raises(ValueError, match="Cannot remove the last board"):
            settings_service.remove_board(settings_service._board.boards[0]["id"])

    def test_remove_board_not_found_raises(self, settings_service):
        settings_service.add_board({"device_type": "note"})  # Ensure we have 2 boards
        with pytest.raises(ValueError, match="not found"):
            settings_service.remove_board("nonexistent-id")


class TestSettingsServiceSchedule:
    """Test SettingsService schedule settings."""

    def test_get_schedule_settings(self, settings_service):
        ss = settings_service.get_schedule_settings()
        assert isinstance(ss, ScheduleSettings)

    def test_is_schedule_enabled_global_no_boards(self, settings_service):
        settings_service._schedule.enabled = True
        settings_service._board.boards = []
        assert settings_service.is_schedule_enabled() is True

    def test_is_schedule_enabled_global_with_boards(self, settings_service):
        settings_service._board.boards[0]["schedule_enabled"] = True
        assert settings_service.is_schedule_enabled() is True

    def test_is_schedule_enabled_by_board_id(self, settings_service):
        board_id = settings_service._board.boards[0]["id"]
        settings_service._board.boards[0]["schedule_enabled"] = True
        assert settings_service.is_schedule_enabled(board_id=board_id) is True

    def test_is_schedule_enabled_board_not_found_returns_false(self, settings_service):
        assert settings_service.is_schedule_enabled(board_id="nonexistent") is False

    def test_set_schedule_enabled_global(self, settings_service):
        settings_service.set_schedule_enabled(True)
        assert settings_service._schedule.enabled is True

    def test_set_schedule_enabled_by_board_id(self, settings_service):
        board_id = settings_service._board.boards[0]["id"]
        settings_service.set_schedule_enabled(True, board_id=board_id)
        assert settings_service._board.boards[0]["schedule_enabled"] is True

    def test_set_schedule_enabled_board_not_found(self, settings_service):
        result = settings_service.set_schedule_enabled(True, board_id="nonexistent")
        assert result == settings_service._schedule


class TestSettingsServiceLoadFromFile:
    """Test loading each setting type from file."""

    def test_load_transition_from_file(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"transitions": {"strategy": "row", "step_interval_ms": 50}}))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_transition_settings().strategy == "row"

    def test_load_output_from_file(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"output": {"target": "both"}}))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_output_settings().target == "both"

    def test_load_active_page_from_file(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"active_page": {"page_id": "p1"}}))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_active_page_id() == "p1"

    def test_load_polling_from_file(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"polling": {"interval_seconds": 120}}))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_polling_interval() == 120

    def test_load_schedule_from_file(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"schedule": {"enabled": True}}))
        svc = SettingsService(settings_file=settings_file)
        assert svc.get_schedule_settings().enabled is True


class TestSettingsServiceMigration:
    """Test _apply_global_connection migration."""

    def test_apply_global_connection_migrates_when_first_board_empty(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(
                {
                    "board": {
                        "board_type": "black",
                        "boards": [{"name": "B", "device_type": "flagship"}],
                    }
                }
            )
        )
        mock_cm = MagicMock()
        mock_cm.get_board.return_value = {
            "local_api_key": "migrated-key",
            "cloud_key": "",
            "host": "192.168.1.1",
            "api_mode": "local",
        }
        with patch("src.config_manager.get_config_manager", return_value=mock_cm):
            svc = SettingsService(settings_file=settings_file)
        assert svc._board.boards[0]["local_api_key"] == "migrated-key"

    def test_apply_global_connection_skips_when_board_has_keys(self, settings_file, mock_config):
        Path(settings_file).write_text(
            json.dumps(
                {
                    "board": {
                        "boards": [{"name": "B", "device_type": "flagship", "local_api_key": "existing"}],
                    }
                }
            )
        )
        with patch("src.config_manager.get_config_manager") as mock_get:
            SettingsService(settings_file=settings_file)
            mock_get.assert_not_called()

    def test_apply_global_connection_skips_when_global_empty(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"board": {"boards": [{"name": "B", "device_type": "flagship"}]}}))
        mock_cm = MagicMock()
        mock_cm.get_board.return_value = {"local_api_key": "", "cloud_key": ""}
        with patch("src.config_manager.get_config_manager", return_value=mock_cm):
            svc = SettingsService(settings_file=settings_file)
        assert svc._board.boards[0].get("local_api_key", "") == ""

    def test_apply_global_connection_handles_exception(self, settings_file, mock_config):
        Path(settings_file).write_text(json.dumps({"board": {"boards": [{"name": "B", "device_type": "flagship"}]}}))
        with patch("src.config_manager.get_config_manager", side_effect=Exception("err")):
            svc = SettingsService(settings_file=settings_file)
        assert "local_api_key" not in svc._board.boards[0] or svc._board.boards[0].get("local_api_key") == ""


class TestGetSettingsService:
    """Test get_settings_service singleton."""

    def test_get_settings_service_returns_singleton(self, mock_config):
        from src.settings import service as settings_module

        settings_module._settings_service = None
        svc1 = get_settings_service()
        svc2 = get_settings_service()
        assert svc1 is svc2

    def test_get_settings_service_creates_with_defaults_when_none(self, mock_config):
        from src.settings import service as settings_module

        settings_module._settings_service = None
        svc = get_settings_service()
        assert svc is not None
        assert isinstance(svc, SettingsService)


# ==================== BetaSettings ====================


class TestBetaSettings:
    """Test BetaSettings dataclass."""

    def test_defaults_to_disabled(self):
        bs = BetaSettings()
        assert bs.https_enabled is False

    def test_from_dict_with_https_enabled(self):
        bs = BetaSettings.from_dict({"https_enabled": True})
        assert bs.https_enabled is True

    def test_from_dict_empty(self):
        bs = BetaSettings.from_dict({})
        assert bs.https_enabled is False

    def test_from_dict_coerces_truthy(self):
        bs = BetaSettings.from_dict({"https_enabled": 1})
        assert bs.https_enabled is True
        bs = BetaSettings.from_dict({"https_enabled": ""})
        assert bs.https_enabled is False

    def test_to_dict_roundtrip(self):
        original = BetaSettings(https_enabled=True)
        restored = BetaSettings.from_dict(original.to_dict())
        assert restored.https_enabled is True


class TestSettingsServiceBeta:
    """Test SettingsService beta-feature methods."""

    def test_get_beta_settings_default(self, settings_service):
        bs = settings_service.get_beta_settings()
        assert bs.https_enabled is False

    def test_update_beta_settings_enables_https(self, settings_service):
        bs = settings_service.update_beta_settings({"https_enabled": True})
        assert bs.https_enabled is True
        # Reload from disk to confirm persistence.
        with open(settings_service.settings_file) as f:
            data = json.load(f)
        assert data["beta"]["https_enabled"] is True

    def test_update_beta_settings_partial_update_preserves_other_keys(self, settings_service):
        settings_service.update_beta_settings({"https_enabled": True})
        # Empty update keeps existing value.
        bs = settings_service.update_beta_settings({})
        assert bs.https_enabled is True

    def test_update_beta_settings_disables_https(self, settings_service):
        settings_service.update_beta_settings({"https_enabled": True})
        bs = settings_service.update_beta_settings({"https_enabled": False})
        assert bs.https_enabled is False

    def test_beta_settings_persist_across_reload(self, settings_file, mock_config):
        svc1 = SettingsService(settings_file=settings_file)
        svc1.update_beta_settings({"https_enabled": True})

        svc2 = SettingsService(settings_file=settings_file)
        assert svc2.get_beta_settings().https_enabled is True


class TestDisplaySettings:
    """Test DisplaySettings dataclass."""

    def test_defaults(self):
        ds = DisplaySettings()
        assert ds.reduce_motion is False
        assert ds.board_animations == "on"
        assert ds.site_animations == "on"

    def test_from_dict_empty_uses_defaults(self):
        ds = DisplaySettings.from_dict({})
        assert ds.reduce_motion is False
        assert ds.board_animations == "on"
        assert ds.site_animations == "on"

    def test_from_dict_with_all_fields(self):
        ds = DisplaySettings.from_dict(
            {
                "reduce_motion": True,
                "board_animations": "desktop",
                "site_animations": "off",
            }
        )
        assert ds.reduce_motion is True
        assert ds.board_animations == "desktop"
        assert ds.site_animations == "off"

    def test_from_dict_rejects_invalid_board_animations(self):
        ds = DisplaySettings.from_dict({"board_animations": "bogus"})
        assert ds.board_animations == "on"

    def test_from_dict_rejects_invalid_site_animations(self):
        ds = DisplaySettings.from_dict({"site_animations": "sometimes"})
        assert ds.site_animations == "on"

    def test_from_dict_case_insensitive(self):
        ds = DisplaySettings.from_dict(
            {
                "board_animations": "DESKTOP",
                "site_animations": "OFF",
            }
        )
        assert ds.board_animations == "desktop"
        assert ds.site_animations == "off"

    def test_to_dict_roundtrip(self):
        original = DisplaySettings(
            reduce_motion=True,
            board_animations="off",
            site_animations="off",
        )
        restored = DisplaySettings.from_dict(original.to_dict())
        assert restored == original


class TestSettingsServiceDisplay:
    """Test SettingsService display-settings methods."""

    def test_get_display_settings_defaults(self, settings_service):
        ds = settings_service.get_display_settings()
        assert ds.board_animations == "on"
        assert ds.site_animations == "on"
        assert ds.reduce_motion is False

    def test_update_board_animations(self, settings_service):
        ds = settings_service.update_display_settings({"board_animations": "desktop"})
        assert ds.board_animations == "desktop"

    def test_update_site_animations(self, settings_service):
        ds = settings_service.update_display_settings({"site_animations": "off"})
        assert ds.site_animations == "off"

    def test_update_display_settings_partial_preserves_others(self, settings_service):
        settings_service.update_display_settings(
            {
                "board_animations": "off",
                "site_animations": "off",
            }
        )
        # Only touch reduce_motion — other keys must stick around.
        ds = settings_service.update_display_settings({"reduce_motion": True})
        assert ds.reduce_motion is True
        assert ds.board_animations == "off"
        assert ds.site_animations == "off"

    def test_update_rejects_invalid_value(self, settings_service):
        ds = settings_service.update_display_settings({"board_animations": "wat"})
        # Invalid input falls back to "on" rather than raising — keeps the
        # UI from getting wedged if an old client sends a stale value.
        assert ds.board_animations == "on"

    def test_display_settings_persist_across_reload(self, settings_file, mock_config):
        svc1 = SettingsService(settings_file=settings_file)
        svc1.update_display_settings(
            {
                "board_animations": "desktop",
                "site_animations": "off",
            }
        )

        svc2 = SettingsService(settings_file=settings_file)
        ds = svc2.get_display_settings()
        assert ds.board_animations == "desktop"
        assert ds.site_animations == "off"
