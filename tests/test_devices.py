"""Tests for device type definitions and board dimensions."""

import pytest

from src.devices import (
    DEVICE_DIMENSIONS,
    DEVICE_TYPES,
    VALID_API_MODES,
    BoardInstance,
    DeviceDimensions,
    get_dimensions,
)


class TestDeviceDimensions:
    """Tests for device dimensions."""

    def test_flagship_dimensions(self):
        """Flagship device has 6 rows, 22 cols."""
        dims = get_dimensions("flagship")
        assert dims == DeviceDimensions(rows=6, cols=22)
        assert dims.rows == 6
        assert dims.cols == 22

    def test_note_dimensions(self):
        """Note device has 3 rows, 15 cols."""
        dims = get_dimensions("note")
        assert dims == DeviceDimensions(rows=3, cols=15)
        assert dims.rows == 3
        assert dims.cols == 15

    def test_device_dimensions_dict(self):
        """DEVICE_DIMENSIONS has correct mappings."""
        assert "flagship" in DEVICE_DIMENSIONS
        assert "note" in DEVICE_DIMENSIONS
        assert DEVICE_DIMENSIONS["flagship"] == DeviceDimensions(6, 22)
        assert DEVICE_DIMENSIONS["note"] == DeviceDimensions(3, 15)

    def test_get_dimensions_invalid_type_raises(self):
        """Unknown device type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown device type: invalid"):
            get_dimensions("invalid")

    def test_get_dimensions_empty_string_raises(self):
        """Empty string device type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown device type"):
            get_dimensions("")


class TestDeviceConstants:
    """Tests for DEVICE_TYPES and VALID_API_MODES constants."""

    def test_device_types(self):
        """DEVICE_TYPES contains flagship and note."""
        assert DEVICE_TYPES == ("flagship", "note")
        assert "flagship" in DEVICE_TYPES
        assert "note" in DEVICE_TYPES

    def test_valid_api_modes(self):
        """VALID_API_MODES contains local and cloud."""
        assert VALID_API_MODES == ("local", "cloud")
        assert "local" in VALID_API_MODES
        assert "cloud" in VALID_API_MODES


class TestBoardInstanceDefaults:
    """Tests for BoardInstance default values."""

    def test_default_values(self):
        """BoardInstance has correct defaults."""
        board = BoardInstance()
        assert board.device_type == "flagship"
        assert board.board_color == "black"
        assert board.enabled is True
        assert board.schedule_enabled is False
        assert board.api_mode == "local"
        assert board.host == ""
        assert board.port == 7000
        assert board.local_api_key == ""
        assert board.cloud_key == ""
        assert board.id is not None
        assert len(board.id) == 36  # UUID format

    def test_name_defaults_to_my_board_when_empty(self):
        """Empty name defaults to 'My Board'."""
        board = BoardInstance(name="")
        assert board.name == "My Board"


class TestBoardInstancePostInitValidation:
    """Tests for BoardInstance __post_init__ validation."""

    def test_invalid_device_type_defaults_to_flagship(self):
        """Invalid device_type defaults to flagship."""
        board = BoardInstance(device_type="invalid")
        assert board.device_type == "flagship"

    def test_invalid_board_color_defaults_to_black(self):
        """Invalid board_color defaults to black."""
        board = BoardInstance(board_color="red")
        assert board.board_color == "black"

    def test_valid_board_colors(self):
        """Valid board colors are accepted."""
        board_black = BoardInstance(board_color="black")
        board_white = BoardInstance(board_color="white")
        assert board_black.board_color == "black"
        assert board_white.board_color == "white"

    def test_invalid_api_mode_defaults_to_local(self):
        """Invalid api_mode defaults to local."""
        board = BoardInstance(api_mode="invalid")
        assert board.api_mode == "local"

    def test_non_bool_enabled_coerced_to_bool(self):
        """Non-bool enabled is coerced to bool."""
        board = BoardInstance(enabled=1)
        assert board.enabled is True

        board = BoardInstance(enabled="true")
        assert board.enabled is True

        board = BoardInstance(enabled=0)
        assert board.enabled is False

    def test_empty_name_defaults_to_my_board(self):
        """Empty name string defaults to 'My Board'."""
        board = BoardInstance(name="")
        assert board.name == "My Board"


class TestBoardInstanceConnectionConfigured:
    """Tests for is_connection_configured property."""

    def test_cloud_mode_with_cloud_key(self):
        """Cloud mode with cloud_key is configured."""
        board = BoardInstance(api_mode="cloud", cloud_key="abc123")
        assert board.is_connection_configured is True

    def test_cloud_mode_without_cloud_key(self):
        """Cloud mode without cloud_key is not configured."""
        board = BoardInstance(api_mode="cloud", cloud_key="")
        assert board.is_connection_configured is False

    def test_local_mode_with_key_and_host(self):
        """Local mode with local_api_key and host is configured."""
        board = BoardInstance(
            api_mode="local",
            local_api_key="key",
            host="192.168.1.1",
        )
        assert board.is_connection_configured is True

    def test_local_mode_without_key(self):
        """Local mode without local_api_key is not configured."""
        board = BoardInstance(
            api_mode="local",
            local_api_key="",
            host="192.168.1.1",
        )
        assert board.is_connection_configured is False

    def test_local_mode_without_host(self):
        """Local mode without host is not configured."""
        board = BoardInstance(
            api_mode="local",
            local_api_key="key",
            host="",
        )
        assert board.is_connection_configured is False

    def test_local_mode_needs_both_key_and_host(self):
        """Local mode needs both local_api_key and host."""
        board = BoardInstance(
            api_mode="local",
            local_api_key="",
            host="",
        )
        assert board.is_connection_configured is False


class TestBoardInstanceToDict:
    """Tests for BoardInstance to_dict and from_dict."""

    def test_to_dict_round_trip(self):
        """to_dict and from_dict round-trip preserves data."""
        original = BoardInstance(
            id="test-id-123",
            name="Test Board",
            device_type="note",
            board_color="white",
            enabled=False,
            schedule_enabled=True,
            api_mode="cloud",
            host="192.168.1.1",
            port=8000,
            local_api_key="local-key",
            cloud_key="cloud-key",
        )
        data = original.to_dict()
        restored = BoardInstance.from_dict(data)
        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.device_type == original.device_type
        assert restored.board_color == original.board_color
        assert restored.enabled == original.enabled
        assert restored.schedule_enabled == original.schedule_enabled
        assert restored.api_mode == original.api_mode
        assert restored.host == original.host
        assert restored.port == original.port
        assert restored.local_api_key == original.local_api_key
        assert restored.cloud_key == original.cloud_key

    def test_from_dict_with_valid_data(self):
        """from_dict with valid data creates correct instance."""
        data = {
            "id": "custom-id",
            "name": "Custom Board",
            "device_type": "flagship",
            "board_color": "black",
            "enabled": True,
            "schedule_enabled": False,
            "api_mode": "local",
            "host": "10.0.0.1",
            "port": 7000,
            "local_api_key": "key",
            "cloud_key": "",
        }
        board = BoardInstance.from_dict(data)
        assert board.id == "custom-id"
        assert board.name == "Custom Board"
        assert board.port == 7000

    def test_from_dict_with_missing_fields_uses_defaults(self):
        """from_dict with missing fields uses defaults."""
        data = {}
        board = BoardInstance.from_dict(data)
        assert board.device_type == "flagship"
        assert board.board_color == "black"
        assert board.enabled is True
        assert board.schedule_enabled is False
        assert board.api_mode == "local"
        assert board.host == ""
        assert board.port == 7000
        assert board.local_api_key == ""
        assert board.cloud_key == ""
        assert board.id is not None
        # Empty name is normalized to "My Board" by __post_init__
        assert board.name == "My Board"

    def test_from_dict_with_string_port_converts_to_int(self):
        """from_dict converts string port to int."""
        data = {"port": "8000"}
        board = BoardInstance.from_dict(data)
        assert board.port == 8000
        assert isinstance(board.port, int)

    def test_from_dict_with_invalid_port_defaults_to_7000(self):
        """from_dict with invalid port defaults to 7000."""
        data = {"port": "not-a-number"}
        board = BoardInstance.from_dict(data)
        assert board.port == 7000

    def test_from_dict_port_none_defaults_to_7000(self):
        """from_dict with port None uses 7000."""
        data = {"port": None}
        board = BoardInstance.from_dict(data)
        assert board.port == 7000
