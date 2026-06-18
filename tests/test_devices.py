"""Tests for device type definitions and board dimensions."""

import pytest

from src.devices import (
    DEVICE_DIMENSIONS,
    DEVICE_TYPES,
    MAX_NOTES_PER_AXIS,
    NOTE_ARRAY_PRESETS,
    NOTE_COLS,
    NOTE_ROWS,
    VALID_API_MODES,
    BoardInstance,
    DeviceDimensions,
    get_dimensions,
    is_note_array,
    is_valid_note_array_grid,
    note_array_dimensions,
    resolve_dimensions,
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
        """DEVICE_TYPES contains flagship, note, and note_array."""
        assert DEVICE_TYPES == ("flagship", "note", "note_array")
        assert "flagship" in DEVICE_TYPES
        assert "note" in DEVICE_TYPES
        assert "note_array" in DEVICE_TYPES

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


class TestNoteArrayConstants:
    """Tests for NOTE_ROWS, NOTE_COLS, MAX_NOTES_PER_AXIS constants."""

    def test_note_rows_value(self):
        assert NOTE_ROWS == 3

    def test_note_cols_value(self):
        assert NOTE_COLS == 15

    def test_max_notes_per_axis_value(self):
        assert MAX_NOTES_PER_AXIS == 8


class TestNoteArrayDimensions:
    """Tests for note_array_dimensions function."""

    def test_2_side_by_side(self):
        """2 wide × 1 tall → 3 rows, 30 cols."""
        assert note_array_dimensions(2, 1) == DeviceDimensions(rows=3, cols=30)

    def test_4_side_by_side(self):
        """4 wide × 1 tall → 3 rows, 60 cols."""
        assert note_array_dimensions(4, 1) == DeviceDimensions(rows=3, cols=60)

    def test_2_stacked(self):
        """1 wide × 2 tall → 6 rows, 15 cols."""
        assert note_array_dimensions(1, 2) == DeviceDimensions(rows=6, cols=15)

    def test_4_stacked(self):
        """1 wide × 4 tall → 12 rows, 15 cols."""
        assert note_array_dimensions(1, 4) == DeviceDimensions(rows=12, cols=15)

    def test_2x2_grid(self):
        """2 wide × 2 tall → 6 rows, 30 cols."""
        assert note_array_dimensions(2, 2) == DeviceDimensions(rows=6, cols=30)

    def test_custom_3x3(self):
        """3 wide × 3 tall → 9 rows, 45 cols."""
        assert note_array_dimensions(3, 3) == DeviceDimensions(rows=9, cols=45)


class TestNoteArrayPresets:
    """Tests for NOTE_ARRAY_PRESETS list."""

    def test_preset_count(self):
        """Exactly 5 presets defined."""
        assert len(NOTE_ARRAY_PRESETS) == 5

    def test_preset_ids_unique(self):
        ids = [p["id"] for p in NOTE_ARRAY_PRESETS]
        assert len(ids) == len(set(ids))

    def test_preset_dimensions(self):
        """Each preset produces the documented dimensions."""
        expected = [
            ("2_wide", DeviceDimensions(3, 30)),
            ("4_wide", DeviceDimensions(3, 60)),
            ("2_tall", DeviceDimensions(6, 15)),
            ("4_tall", DeviceDimensions(12, 15)),
            ("2x2_grid", DeviceDimensions(6, 30)),
        ]
        by_id = {p["id"]: p for p in NOTE_ARRAY_PRESETS}
        for preset_id, expected_dims in expected:
            p = by_id[preset_id]
            assert note_array_dimensions(p["notes_wide"], p["notes_tall"]) == expected_dims, preset_id

    def test_presets_have_required_keys(self):
        for p in NOTE_ARRAY_PRESETS:
            assert "id" in p
            assert "label" in p
            assert "notes_wide" in p
            assert "notes_tall" in p


class TestIsNoteArray:
    """Tests for is_note_array function."""

    def test_note_array_returns_true(self):
        assert is_note_array("note_array") is True

    def test_flagship_returns_false(self):
        assert is_note_array("flagship") is False

    def test_note_returns_false(self):
        assert is_note_array("note") is False

    def test_empty_returns_false(self):
        assert is_note_array("") is False


class TestIsValidNoteArrayGrid:
    """Tests for is_valid_note_array_grid function."""

    def test_valid_2x1_array(self):
        """3 rows × 30 cols (2 wide × 1 tall) is valid."""
        assert is_valid_note_array_grid(3, 30) is True

    def test_valid_4x1_array(self):
        """3 rows × 60 cols is valid."""
        assert is_valid_note_array_grid(3, 60) is True

    def test_valid_1x4_array(self):
        """12 rows × 15 cols is valid."""
        assert is_valid_note_array_grid(12, 15) is True

    def test_valid_2x2_grid(self):
        """6 rows × 30 cols is valid."""
        assert is_valid_note_array_grid(6, 30) is True

    def test_flagship_dimensions_are_invalid(self):
        """6×22 flagship dims are not a valid note-array size (22 % 15 != 0)."""
        assert is_valid_note_array_grid(6, 22) is False

    def test_non_multiple_rows_invalid(self):
        """7 rows is not a multiple of 3."""
        assert is_valid_note_array_grid(7, 15) is False

    def test_non_multiple_cols_invalid(self):
        """16 cols is not a multiple of 15."""
        assert is_valid_note_array_grid(3, 16) is False

    def test_zero_rows_invalid(self):
        assert is_valid_note_array_grid(0, 15) is False

    def test_zero_cols_invalid(self):
        assert is_valid_note_array_grid(3, 0) is False

    def test_negative_values_invalid(self):
        assert is_valid_note_array_grid(-3, 15) is False

    def test_over_cap_rows_invalid(self):
        """9 notes tall (27 rows) exceeds MAX_NOTES_PER_AXIS=8."""
        assert is_valid_note_array_grid(27, 15) is False

    def test_over_cap_cols_invalid(self):
        """9 notes wide (135 cols) exceeds MAX_NOTES_PER_AXIS=8."""
        assert is_valid_note_array_grid(3, 135) is False

    def test_at_cap_is_valid(self):
        """8 notes wide, 8 notes tall is exactly at the cap."""
        assert is_valid_note_array_grid(24, 120) is True


class TestResolveDimensions:
    """Tests for resolve_dimensions function."""

    def test_flagship(self):
        assert resolve_dimensions("flagship") == DeviceDimensions(6, 22)

    def test_note(self):
        assert resolve_dimensions("note") == DeviceDimensions(3, 15)

    def test_note_array_4x1(self):
        """resolve_dimensions('note_array', 4, 1) → rows=3, cols=60."""
        assert resolve_dimensions("note_array", 4, 1) == DeviceDimensions(rows=3, cols=60)

    def test_note_array_2x2(self):
        assert resolve_dimensions("note_array", 2, 2) == DeviceDimensions(rows=6, cols=30)

    def test_note_array_defaults_1x1(self):
        """Default notes_wide=1, notes_tall=1 → 3×15."""
        assert resolve_dimensions("note_array") == DeviceDimensions(rows=3, cols=15)

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown device type: invalid"):
            resolve_dimensions("invalid")

    def test_flagship_ignores_notes_args(self):
        """notes_wide/notes_tall are ignored for static types."""
        assert resolve_dimensions("flagship", notes_wide=4, notes_tall=4) == DeviceDimensions(6, 22)


class TestBoardInstanceNotesFields:
    """Tests for notes_wide and notes_tall fields on BoardInstance."""

    def test_default_notes_wide_and_tall(self):
        board = BoardInstance()
        assert board.notes_wide == 1
        assert board.notes_tall == 1

    def test_valid_notes_wide_set(self):
        board = BoardInstance(notes_wide=4, notes_tall=2)
        assert board.notes_wide == 4
        assert board.notes_tall == 2

    def test_notes_wide_zero_clamped_to_1(self):
        board = BoardInstance(notes_wide=0)
        assert board.notes_wide == 1

    def test_notes_tall_negative_clamped_to_1(self):
        board = BoardInstance(notes_tall=-1)
        assert board.notes_tall == 1

    def test_notes_wide_over_cap_clamped(self):
        board = BoardInstance(notes_wide=MAX_NOTES_PER_AXIS + 1)
        assert board.notes_wide == MAX_NOTES_PER_AXIS

    def test_notes_tall_over_cap_clamped(self):
        board = BoardInstance(notes_tall=MAX_NOTES_PER_AXIS + 1)
        assert board.notes_tall == MAX_NOTES_PER_AXIS

    def test_notes_round_trip_via_to_dict_from_dict(self):
        original = BoardInstance(device_type="note_array", notes_wide=3, notes_tall=2)
        data = original.to_dict()
        assert data["notes_wide"] == 3
        assert data["notes_tall"] == 2
        restored = BoardInstance.from_dict(data)
        assert restored.notes_wide == 3
        assert restored.notes_tall == 2

    def test_from_dict_missing_notes_fields_default_to_1(self):
        """Old JSON without notes fields loads cleanly (migration check)."""
        data = {"id": "x", "device_type": "flagship"}
        board = BoardInstance.from_dict(data)
        assert board.notes_wide == 1
        assert board.notes_tall == 1

    def test_note_array_device_type_accepted(self):
        """'note_array' is now a valid device_type — not normalized to 'flagship'."""
        board = BoardInstance(device_type="note_array")
        assert board.device_type == "note_array"
