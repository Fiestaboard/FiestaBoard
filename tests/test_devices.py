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
    BoardContext,
    BoardInstance,
    DeviceDimensions,
    board_context_for,
    classify_dimensions,
    get_dimensions,
    is_note_array,
    is_valid_note_array_grid,
    note_array_dimensions,
    resolve_dimensions,
)


class TestBoardContext:
    """Tests for the BoardContext value object passed to plugins."""

    def test_from_flagship(self):
        board = BoardContext.from_device_type("flagship")
        assert board.device_type == "flagship"
        assert (board.rows, board.cols) == (6, 22)
        assert (board.height, board.width) == (6, 22)

    def test_from_note(self):
        board = BoardContext.from_device_type("note")
        assert board.device_type == "note"
        assert (board.rows, board.cols) == (3, 15)
        assert (board.height, board.width) == (3, 15)

    def test_width_height_aliases_track_cols_rows(self):
        board = BoardContext(device_type="note", rows=3, cols=15)
        assert board.width == board.cols
        assert board.height == board.rows

    def test_supports_composite_dimensions(self):
        """Raw construction supports future multi-board composite sizes."""
        board = BoardContext(device_type="composite", rows=6, cols=30)
        assert (board.width, board.height) == (30, 6)

    def test_is_frozen(self):
        board = BoardContext.from_device_type("flagship")
        with pytest.raises(AttributeError):
            board.cols = 99  # type: ignore[misc]

    def test_from_unknown_device_type_raises(self):
        with pytest.raises(ValueError):
            BoardContext.from_device_type("bogus")


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

    def test_get_dimensions_note_array_raises(self):
        """note_array is not supported by get_dimensions; use resolve_dimensions instead."""
        with pytest.raises(ValueError, match="resolve_dimensions"):
            get_dimensions("note_array")


class TestDeviceConstants:
    """Tests for DEVICE_TYPES and VALID_API_MODES constants."""

    def test_device_types(self):
        """DEVICE_TYPES contains flagship, note, and note_array."""
        assert DEVICE_TYPES == ("flagship", "note", "note_array")
        assert "flagship" in DEVICE_TYPES
        assert "note" in DEVICE_TYPES
        assert "note_array" in DEVICE_TYPES

    def test_valid_api_modes(self):
        """VALID_API_MODES contains only local and cloud (no note_array entry)."""
        assert VALID_API_MODES == ("local", "cloud")
        assert "local" in VALID_API_MODES
        assert "cloud" in VALID_API_MODES
        assert "note_array" not in VALID_API_MODES


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

    def test_note_array_configured_with_token_and_valid_wh(self):
        """Note-array board with token and valid W×H is configured."""
        board = BoardInstance(device_type="note_array", note_array_token="tok-abc", notes_wide=2, notes_tall=1)
        assert board.is_connection_configured is True

    def test_note_array_not_configured_missing_token(self):
        """Note-array board without token is not configured."""
        board = BoardInstance(device_type="note_array", note_array_token="", notes_wide=2, notes_tall=1)
        assert board.is_connection_configured is False

    def test_note_array_not_configured_empty_token_even_with_cloud_key(self):
        """cloud_key is irrelevant for note_array boards — token is required."""
        board = BoardInstance(
            device_type="note_array", note_array_token="", cloud_key="cloud-k", notes_wide=2, notes_tall=1
        )
        assert board.is_connection_configured is False

    def test_note_array_token_does_not_affect_flagship_configured_check(self):
        """Flagship board with note_array_token set but no local creds is still not configured."""
        board = BoardInstance(
            device_type="flagship", note_array_token="tok-abc", api_mode="local", local_api_key="", host=""
        )
        assert board.is_connection_configured is False

    def test_cloud_mode_flagship_still_works_unchanged(self):
        """Cloud mode flagship with cloud_key is configured (unchanged behaviour)."""
        board = BoardInstance(device_type="flagship", api_mode="cloud", cloud_key="ck-xyz")
        assert board.is_connection_configured is True

    def test_local_mode_flagship_still_works_unchanged(self):
        """Local mode flagship with key+host is configured (unchanged behaviour)."""
        board = BoardInstance(api_mode="local", local_api_key="lk", host="192.168.1.1")
        assert board.is_connection_configured is True


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


class TestNoteArrayToken:
    """Tests for the note_array_token field on BoardInstance."""

    def test_note_array_token_default_is_empty_string(self):
        """BoardInstance() initialises note_array_token to an empty string."""
        board = BoardInstance()
        assert board.note_array_token == ""

    def test_note_array_token_explicit_value_preserved(self):
        """An explicit note_array_token is stored unchanged."""
        board = BoardInstance(note_array_token="tok-abc123")
        assert board.note_array_token == "tok-abc123"

    def test_note_array_token_round_trip_to_dict_from_dict(self):
        """note_array_token survives a to_dict/from_dict round-trip."""
        original = BoardInstance(device_type="note_array", note_array_token="tok-xyz", notes_wide=2, notes_tall=1)
        data = original.to_dict()
        assert data["note_array_token"] == "tok-xyz"
        restored = BoardInstance.from_dict(data)
        assert restored.note_array_token == "tok-xyz"

    def test_note_array_token_absent_from_old_json_defaults_to_empty(self):
        """Old JSON without note_array_token key loads with empty string default."""
        data = {"id": "x", "device_type": "note_array", "notes_wide": 2, "notes_tall": 1}
        board = BoardInstance.from_dict(data)
        assert board.note_array_token == ""

    def test_flagship_board_has_note_array_token_field(self):
        """The note_array_token field exists on non-note-array boards too (dataclass symmetry)."""
        board = BoardInstance(device_type="flagship")
        assert board.note_array_token == ""

    def test_note_array_token_whitespace_stripped_on_from_dict(self):
        """from_dict strips surrounding whitespace (consistent with other credential fields)."""
        board = BoardInstance.from_dict(
            {"device_type": "note_array", "note_array_token": "  tok-trim  ", "notes_wide": 2, "notes_tall": 1}
        )
        assert board.note_array_token == "tok-trim"

    def test_note_array_whitespace_only_token_not_configured(self):
        """A whitespace-only token is stripped to empty, so the board is not configured."""
        board = BoardInstance.from_dict(
            {"device_type": "note_array", "note_array_token": "   ", "notes_wide": 2, "notes_tall": 1}
        )
        assert board.note_array_token == ""
        assert board.is_connection_configured is False


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

    def test_notes_wide_bool_rejected(self):
        """bool is a subclass of int; True must not leak through as notes_wide."""
        board = BoardInstance(notes_wide=True)
        assert board.notes_wide == 1
        assert board.notes_wide is not True

    def test_notes_tall_bool_rejected(self):
        board = BoardInstance(notes_tall=True)
        assert board.notes_tall == 1
        assert board.notes_tall is not True

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


class TestClassifyDimensions:
    """Tests for classify_dimensions(rows, cols) — auto-detect from a live grid."""

    # --- Flagship ---
    def test_flagship_6x22(self):
        """6×22 → flagship (no note-array keys)."""
        result = classify_dimensions(6, 22)
        assert result["device_type"] == "flagship"
        assert result["rows"] == 6
        assert result["cols"] == 22
        assert "notes_wide" not in result
        assert "notes_tall" not in result
        assert "matched_preset" not in result

    # --- Note ---
    def test_note_3x15(self):
        """3×15 → note (checked before the note-array branch)."""
        result = classify_dimensions(3, 15)
        assert result["device_type"] == "note"
        assert result["rows"] == 3
        assert result["cols"] == 15
        assert "notes_wide" not in result

    # --- Note array, preset matches ---
    def test_note_array_2x2_grid(self):
        """6×30 → note_array, 2 wide × 2 tall, preset '2×2 grid'."""
        result = classify_dimensions(6, 30)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 2
        assert result["notes_tall"] == 2
        assert result["matched_preset"] == "2×2 grid"
        assert result["rows"] == 6
        assert result["cols"] == 30

    def test_note_array_4_side_by_side(self):
        """3×60 → note_array, 4 wide × 1 tall, preset '4 side-by-side'."""
        result = classify_dimensions(3, 60)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 4
        assert result["notes_tall"] == 1
        assert result["matched_preset"] == "4 side-by-side"

    def test_note_array_2_side_by_side(self):
        """3×30 → note_array, 2 wide × 1 tall, preset '2 side-by-side'."""
        result = classify_dimensions(3, 30)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 2
        assert result["notes_tall"] == 1
        assert result["matched_preset"] == "2 side-by-side"

    def test_note_array_2_stacked(self):
        """6×15 → note_array, 1 wide × 2 tall, preset '2 stacked'."""
        result = classify_dimensions(6, 15)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 1
        assert result["notes_tall"] == 2
        assert result["matched_preset"] == "2 stacked"

    def test_note_array_4_stacked(self):
        """12×15 → note_array, 1 wide × 4 tall, preset '4 stacked'."""
        result = classify_dimensions(12, 15)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 1
        assert result["notes_tall"] == 4
        assert result["matched_preset"] == "4 stacked"

    # --- Note array, no preset match ---
    def test_note_array_no_preset_match(self):
        """9×45 (3 wide × 3 tall) → note_array, matched_preset is None."""
        result = classify_dimensions(9, 45)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 3
        assert result["notes_tall"] == 3
        assert result["matched_preset"] is None

    def test_note_array_8x8_at_cap_no_preset(self):
        """24×120 (8 wide × 8 tall) is at MAX_NOTES_PER_AXIS cap, no preset."""
        result = classify_dimensions(24, 120)
        assert result["device_type"] == "note_array"
        assert result["notes_wide"] == 8
        assert result["notes_tall"] == 8
        assert result["matched_preset"] is None

    # --- Unclassifiable ---
    def test_unclassifiable_5x15_non_multiple_rows(self):
        """5×15: 5 % 3 != 0 → ValueError."""
        with pytest.raises(ValueError, match="unclassifiable"):
            classify_dimensions(5, 15)

    def test_unclassifiable_6x16_non_multiple_cols(self):
        """6×16: 16 % 15 != 0 → ValueError."""
        with pytest.raises(ValueError, match="unclassifiable"):
            classify_dimensions(6, 16)

    def test_unclassifiable_4x4(self):
        """4×4: not flagship, not note, not valid note-array → ValueError."""
        with pytest.raises(ValueError, match="unclassifiable"):
            classify_dimensions(4, 4)

    def test_unclassifiable_over_axis_cap(self):
        """27×15 (9 notes tall > MAX_NOTES_PER_AXIS=8) → ValueError."""
        with pytest.raises(ValueError, match="unclassifiable"):
            classify_dimensions(27, 15)

    def test_unclassifiable_zero_rows(self):
        """0×15 → ValueError."""
        with pytest.raises(ValueError):
            classify_dimensions(0, 15)

    def test_unclassifiable_zero_cols(self):
        """3×0 → ValueError."""
        with pytest.raises(ValueError):
            classify_dimensions(3, 0)


class TestBoardContextFor:
    """Tests for board_context_for() — note-array-aware BoardContext factory."""

    def test_flagship(self):
        b = board_context_for("flagship")
        assert (b.device_type, b.rows, b.cols) == ("flagship", 6, 22)
        assert (b.width, b.height) == (22, 6)

    def test_note(self):
        b = board_context_for("note")
        assert (b.device_type, b.rows, b.cols) == ("note", 3, 15)

    def test_note_array_4_wide(self):
        """4 side-by-side → 3 rows × 60 cols (the case from_device_type cannot build)."""
        b = board_context_for("note_array", notes_wide=4, notes_tall=1)
        assert (b.device_type, b.rows, b.cols) == ("note_array", 3, 60)

    def test_note_array_2x2(self):
        b = board_context_for("note_array", notes_wide=2, notes_tall=2)
        assert (b.device_type, b.rows, b.cols) == ("note_array", 6, 30)

    def test_note_array_distinct_sizes_distinct_dims(self):
        """Two note arrays of different sizes produce different contexts."""
        wide = board_context_for("note_array", notes_wide=4, notes_tall=1)
        tall = board_context_for("note_array", notes_wide=1, notes_tall=4)
        assert (wide.rows, wide.cols) != (tall.rows, tall.cols)

    def test_unknown_falls_back_to_default(self):
        """An unrecognized device type falls back to the default (flagship)."""
        b = board_context_for("nonsense")
        assert (b.device_type, b.rows, b.cols) == ("flagship", 6, 22)


class TestNormalizeNoteArrayTiles:
    """Tile-list normalization for local note arrays."""

    def test_non_list_returns_empty(self):
        from src.devices import normalize_note_array_tiles

        assert normalize_note_array_tiles(None) == []
        assert normalize_note_array_tiles("nope") == []
        assert normalize_note_array_tiles({"row": 0}) == []

    def test_drops_malformed_entries(self):
        from src.devices import normalize_note_array_tiles

        tiles = [
            "not-a-dict",
            {"host": "10.0.0.1"},  # missing row/col
            {"row": "x", "col": 0},  # non-numeric row
            {"row": -1, "col": 0, "host": "10.0.0.1"},  # negative
            {"row": True, "col": 0, "host": "10.0.0.1"},  # bool row
        ]
        assert normalize_note_array_tiles(tiles) == []

    def test_coerces_types_and_defaults(self):
        from src.devices import normalize_note_array_tiles

        [tile] = normalize_note_array_tiles(
            [{"row": "1", "col": "0", "host": " 10.0.0.5 ", "port": "7001", "local_api_key": " k "}]
        )
        assert tile == {
            "row": 1,
            "col": 0,
            "host": "10.0.0.5",
            "port": 7001,
            "local_api_key": "k",
            "enabled": True,
        }

    def test_bad_port_defaults_to_7000(self):
        from src.devices import normalize_note_array_tiles

        [tile] = normalize_note_array_tiles([{"row": 0, "col": 0, "port": "abc"}])
        assert tile["port"] == 7000

    def test_dedupes_by_position_last_wins(self):
        from src.devices import normalize_note_array_tiles

        tiles = normalize_note_array_tiles(
            [
                {"row": 0, "col": 0, "host": "old"},
                {"row": 0, "col": 0, "host": "new"},
            ]
        )
        assert len(tiles) == 1
        assert tiles[0]["host"] == "new"

    def test_out_of_range_positions_preserved(self):
        """Tiles beyond the current W×H are kept — resize must not destroy keys."""
        from src.devices import normalize_note_array_tiles

        tiles = normalize_note_array_tiles([{"row": 5, "col": 7, "host": "10.0.0.9", "local_api_key": "k"}])
        assert len(tiles) == 1


class TestBoardInstanceTiles:
    """BoardInstance tile handling."""

    def _tile(self, row=0, col=0, **kw):
        return {"row": row, "col": col, "host": "10.0.0.1", "port": 7000, "local_api_key": "key", "enabled": True, **kw}

    def test_tiles_cleared_on_non_array_boards(self):
        b = BoardInstance(device_type="flagship", tiles=[self._tile()])
        assert b.tiles == []

    def test_tiles_normalized_on_array_boards(self):
        b = BoardInstance(device_type="note_array", tiles=[self._tile(), "junk"])
        assert len(b.tiles) == 1

    def test_tiles_round_trip_from_dict_to_dict(self):
        b = BoardInstance(device_type="note_array", api_mode="local", notes_wide=2, tiles=[self._tile(col=1)])
        b2 = BoardInstance.from_dict(b.to_dict())
        assert b2.tiles == b.tiles

    def test_configured_tiles_filters_out_of_range(self):
        b = BoardInstance(
            device_type="note_array",
            api_mode="local",
            notes_wide=2,
            notes_tall=1,
            tiles=[self._tile(col=0), self._tile(col=1), self._tile(col=5), self._tile(row=3)],
        )
        assert {(t["row"], t["col"]) for t in b.configured_tiles()} == {(0, 0), (0, 1)}

    def test_configured_tiles_requires_host_key_enabled(self):
        b = BoardInstance(
            device_type="note_array",
            api_mode="local",
            notes_wide=4,
            tiles=[
                self._tile(col=0),
                self._tile(col=1, host=""),
                self._tile(col=2, local_api_key=""),
                self._tile(col=3, enabled=False),
            ],
        )
        assert [(t["row"], t["col"]) for t in b.configured_tiles()] == [(0, 0)]

    def test_local_array_configured_with_one_tile(self):
        b = BoardInstance(device_type="note_array", api_mode="local", notes_wide=2, tiles=[self._tile()])
        assert b.uses_local_tiles
        assert b.is_connection_configured

    def test_local_array_not_configured_when_no_usable_tile(self):
        b = BoardInstance(device_type="note_array", api_mode="local", notes_wide=2, tiles=[self._tile(host="")])
        assert b.uses_local_tiles
        assert not b.is_connection_configured

    def test_legacy_array_without_tiles_keeps_token_semantics(self):
        """api_mode defaults to 'local' on old dicts — token must still work."""
        b = BoardInstance(device_type="note_array", note_array_token="tok")
        assert b.api_mode == "local"
        assert not b.uses_local_tiles
        assert b.is_connection_configured

    def test_cloud_array_ignores_tiles(self):
        b = BoardInstance(device_type="note_array", api_mode="cloud", note_array_token="tok", tiles=[self._tile()])
        assert not b.uses_local_tiles
        assert b.is_connection_configured


class TestSliceStitchNoteArrayGrid:
    """Slicing the virtual frame into per-tile subgrids and back."""

    def _grid(self, notes_wide, notes_tall):
        rows, cols = notes_tall * NOTE_ROWS, notes_wide * NOTE_COLS
        return [[r * 1000 + c for c in range(cols)] for r in range(rows)]

    @pytest.mark.parametrize("w,h", [(1, 1), (2, 1), (1, 2), (2, 2), (4, 1), (8, 8)])
    def test_slice_stitch_round_trip(self, w, h):
        from src.devices import slice_note_array_grid, stitch_note_array_grid

        grid = self._grid(w, h)
        subgrids = slice_note_array_grid(grid, w, h)
        assert len(subgrids) == w * h
        assert stitch_note_array_grid(subgrids, w, h) == grid

    def test_tile_0_1_gets_cols_15_to_29(self):
        from src.devices import slice_note_array_grid

        grid = self._grid(2, 1)
        sub = slice_note_array_grid(grid, 2, 1)[(0, 1)]
        assert len(sub) == NOTE_ROWS
        assert all(len(r) == NOTE_COLS for r in sub)
        assert sub[0] == grid[0][15:30]
        assert sub[2] == grid[2][15:30]

    def test_tile_1_0_gets_rows_3_to_5(self):
        from src.devices import slice_note_array_grid

        grid = self._grid(1, 2)
        sub = slice_note_array_grid(grid, 1, 2)[(1, 0)]
        assert sub == [grid[3], grid[4], grid[5]]

    def test_slice_rejects_wrong_dimensions(self):
        from src.devices import slice_note_array_grid

        with pytest.raises(ValueError):
            slice_note_array_grid(self._grid(2, 1), 2, 2)
        with pytest.raises(ValueError):
            slice_note_array_grid([[0] * 14] * 3, 1, 1)

    def test_stitch_fills_missing_slots(self):
        from src.devices import slice_note_array_grid, stitch_note_array_grid

        grid = self._grid(2, 1)
        subgrids = slice_note_array_grid(grid, 2, 1)
        del subgrids[(0, 1)]
        stitched = stitch_note_array_grid(subgrids, 2, 1, fill=0)
        assert stitched[0][:15] == grid[0][:15]
        assert stitched[0][15:] == [0] * 15

    def test_stitch_ignores_out_of_range_and_malformed(self):
        from src.devices import stitch_note_array_grid

        stitched = stitch_note_array_grid({(5, 5): [[1] * NOTE_COLS] * NOTE_ROWS, (0, 0): [[1] * 3]}, 1, 1)
        assert stitched == [[0] * NOTE_COLS for _ in range(NOTE_ROWS)]


class TestIdentifyPattern:
    """Identify-flash pattern rendering."""

    def test_shape_is_note_sized(self):
        from src.devices import identify_pattern

        pattern = identify_pattern(0, 0, notes_wide=2)
        assert len(pattern) == NOTE_ROWS
        assert all(len(r) == NOTE_COLS for r in pattern)

    def test_distinct_slots_produce_distinct_patterns(self):
        from src.devices import identify_pattern

        assert identify_pattern(0, 0, 2) != identify_pattern(0, 1, 2)
        assert identify_pattern(0, 1, 2) != identify_pattern(1, 0, 2)


class TestSizeKey:
    """Canonical family+size key for page/board compatibility (issue #1245)."""

    def test_flagship(self):
        from src.devices import size_key

        assert size_key("flagship") == "flagship:6x22"

    def test_note(self):
        from src.devices import size_key

        assert size_key("note") == "note:3x15"

    def test_note_array_resolves_dimensions(self):
        from src.devices import size_key

        assert size_key("note_array", notes_wide=2, notes_tall=2) == "note_array:6x30"
        assert size_key("note_array", notes_wide=2, notes_tall=1) == "note_array:3x30"
        assert size_key("note_array", notes_wide=1, notes_tall=4) == "note_array:12x15"
        assert size_key("note_array") == "note_array:3x15"

    def test_flagship_ignores_note_counts(self):
        from src.devices import size_key

        assert size_key("flagship", notes_wide=3, notes_tall=2) == "flagship:6x22"

    def test_unknown_device_type_falls_back_to_default(self):
        from src.devices import size_key

        assert size_key("mystery") == "flagship:6x22"


class TestPagesCompatibleWithBoard:
    """Exact size_key compatibility predicate (issue #1245)."""

    @staticmethod
    def _board(device_type, notes_wide=1, notes_tall=1):
        return {"id": "b1", "device_type": device_type, "notes_wide": notes_wide, "notes_tall": notes_tall}

    @staticmethod
    def _page(device_type, notes_wide=1, notes_tall=1):
        from src.pages.models import Page

        return Page(
            name="p",
            type="template",
            device_type=device_type,
            template=["hi"],
            notes_wide=notes_wide,
            notes_tall=notes_tall,
        )

    def test_flagship_page_flagship_board(self):
        from src.devices import pages_compatible_with_board

        assert pages_compatible_with_board(self._page("flagship"), self._board("flagship")) is True

    def test_flagship_page_note_board(self):
        from src.devices import pages_compatible_with_board

        assert pages_compatible_with_board(self._page("flagship"), self._board("note")) is False

    def test_note_page_note_board(self):
        from src.devices import pages_compatible_with_board

        assert pages_compatible_with_board(self._page("note"), self._board("note")) is True

    def test_note_page_1x1_note_array_board_is_family_mismatch(self):
        """Same 3x15 dimensions but different family: note != note_array."""
        from src.devices import pages_compatible_with_board

        assert pages_compatible_with_board(self._page("note"), self._board("note_array", 1, 1)) is False

    def test_note_array_exact_grid_match(self):
        from src.devices import pages_compatible_with_board

        page = self._page("note_array", notes_wide=2, notes_tall=2)
        assert pages_compatible_with_board(page, self._board("note_array", 2, 2)) is True
        assert pages_compatible_with_board(page, self._board("note_array", 2, 1)) is False
        assert pages_compatible_with_board(page, self._board("note_array", 4, 1)) is False

    def test_board_instance_object(self):
        from src.devices import pages_compatible_with_board

        board = BoardInstance(device_type="note_array", notes_wide=2, notes_tall=1)
        assert pages_compatible_with_board(self._page("note_array", 2, 1), board) is True
        assert pages_compatible_with_board(self._page("note_array", 1, 2), board) is False

    def test_board_dict_missing_geometry_defaults(self):
        """Board dicts without device_type/notes fields behave as a flagship."""
        from src.devices import pages_compatible_with_board

        assert pages_compatible_with_board(self._page("flagship"), {"id": "b1"}) is True
        assert pages_compatible_with_board(self._page("note"), {"id": "b1"}) is False
