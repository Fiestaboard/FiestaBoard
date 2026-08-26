"""Tests for FiestaPanel Pydantic models."""

import pytest
from pydantic import ValidationError

from src.panels.models import AutoDim, Panel, PanelCreate, PanelUpdate


def _panel(**overrides):
    defaults = {"name": "Living Room TV", "board_id": "board-1"}
    defaults.update(overrides)
    return Panel(**defaults)


class TestPanelDefaults:
    def test_id_is_url_safe_and_long_enough(self):
        panel = _panel()
        assert len(panel.id) >= 12
        assert all(c.isalnum() or c in "-_" for c in panel.id)

    def test_ids_are_unique(self):
        assert _panel().id != _panel().id

    def test_defaults(self):
        panel = _panel()
        assert panel.screen_diagonal_inches == 55.0
        assert panel.calibration_scale == 1.0
        assert panel.backdrop == "wall"
        assert panel.auto_dim.enabled is False
        assert panel.auto_dim.start == "22:00"
        assert panel.auto_dim.end == "07:00"
        assert panel.created_at is not None
        assert panel.updated_at is not None


class TestPanelValidation:
    def test_rejects_tiny_screen(self):
        with pytest.raises(ValidationError):
            _panel(screen_diagonal_inches=5)

    def test_rejects_out_of_range_calibration(self):
        with pytest.raises(ValidationError):
            _panel(calibration_scale=2.0)

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            _panel(name="")

    def test_rejects_unknown_backdrop(self):
        with pytest.raises(ValidationError):
            _panel(backdrop="disco")

    def test_rejects_malformed_auto_dim_time(self):
        with pytest.raises(ValidationError):
            AutoDim(enabled=True, start="25:99", end="07:00")

    def test_accepts_valid_auto_dim_times(self):
        dim = AutoDim(enabled=True, start="23:30", end="06:15")
        assert dim.start == "23:30"
        assert dim.end == "06:15"


class TestRequestModels:
    def test_create_requires_shape(self):
        with pytest.raises(ValidationError):
            PanelCreate(name="TV", device_type="note_array", screen_diagonal_inches=55)

    def test_create_accepts_real_shapes(self):
        for shape in ("flagship", "note"):
            req = PanelCreate(name="TV", device_type=shape, screen_diagonal_inches=43)
            assert req.device_type == shape

    def test_update_is_all_optional(self):
        update = PanelUpdate()
        assert update.model_dump(exclude_unset=True) == {}
