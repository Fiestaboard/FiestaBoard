"""Tests for the typewriter transition plugin."""

import json
from pathlib import Path

import pytest

from plugins.typewriter import TypewriterTransition
from src.devices import DEVICE_DIMENSIONS

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text())


@pytest.fixture
def plugin() -> TypewriterTransition:
    return TypewriterTransition(MANIFEST)


def _grid(value: int, rows: int = 6, cols: int = 22):
    return [[value] * cols for _ in range(rows)]


def test_plugin_id_matches_manifest(plugin):
    assert plugin.plugin_id == MANIFEST["id"]


def test_transition_settings_loaded_from_manifest(plugin):
    settings = plugin.transition_settings
    assert settings["interruptible"] is True
    assert settings["max_frames"] == 200
    assert settings["max_runtime_seconds"] == 60


def test_generates_one_frame_per_chars_per_frame(plugin):
    """With chars_per_frame=22 (one full row), 6 frames cover the flagship grid."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={"chars_per_frame": 22, "frame_interval_ms": 0},
        )
    )
    assert len(frames) == 6
    # Last frame should equal target.
    assert frames[-1][0] == _grid(1)
    # All delays are 0.
    assert all(delay == 0 for _, delay in frames)


def test_first_frame_only_reveals_first_char():
    """chars_per_frame=1 means the first frame differs from from_grid in exactly one tile."""
    plugin = TypewriterTransition(MANIFEST)
    from_grid = _grid(0)
    to_grid = _grid(1)
    frames = list(
        plugin.generate_frames(
            from_grid=from_grid,
            to_grid=to_grid,
            device=DEVICE_DIMENSIONS["flagship"],
            config={"chars_per_frame": 1, "frame_interval_ms": 50},
        )
    )
    # First frame: only the top-left tile is revealed.
    first_grid, first_delay = frames[0]
    assert first_grid[0][0] == 1
    assert first_grid[0][1] == 0
    assert first_delay == 50


def test_total_frames_matches_grid_area_for_one_per_frame():
    """6 rows × 22 cols = 132 frames at chars_per_frame=1."""
    plugin = TypewriterTransition(MANIFEST)
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={"chars_per_frame": 1, "frame_interval_ms": 0},
        )
    )
    assert len(frames) == 132


def test_handles_note_device(plugin):
    """Note board is 3 rows × 15 cols = 45 tiles."""
    note_grid = _grid(0, rows=3, cols=15)
    target = _grid(7, rows=3, cols=15)
    frames = list(
        plugin.generate_frames(
            from_grid=note_grid,
            to_grid=target,
            device=DEVICE_DIMENSIONS["note"],
            config={"chars_per_frame": 5, "frame_interval_ms": 30},
        )
    )
    assert len(frames) == 9  # 45 / 5
    assert frames[-1][0] == target


def test_chars_per_frame_clamped_to_at_least_one(plugin):
    """Even with invalid config, the loop terminates."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={"chars_per_frame": 0},
        )
    )
    assert len(frames) == 132  # treated as 1 per frame


def test_empty_grid_produces_no_frames(plugin):
    frames = list(
        plugin.generate_frames(
            from_grid=[],
            to_grid=[],
            device=DEVICE_DIMENSIONS["flagship"],
            config={},
        )
    )
    assert frames == []


def test_uses_defaults_when_config_missing(plugin):
    """Calling with empty config still produces frames using manifest defaults."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={},
        )
    )
    assert len(frames) == 132
    assert frames[0][1] == 120  # default frame_interval_ms
