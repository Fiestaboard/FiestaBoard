"""Tests for the slot_machine transition plugin."""

import json
from pathlib import Path

import pytest

from plugins.slot_machine import _SPIN_CODES, SlotMachineTransition
from src.devices import DEVICE_DIMENSIONS

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text())


@pytest.fixture
def plugin() -> SlotMachineTransition:
    return SlotMachineTransition(MANIFEST)


def _grid(value: int, rows: int = 6, cols: int = 22):
    return [[value] * cols for _ in range(rows)]


def test_plugin_id_matches_manifest(plugin):
    assert plugin.plugin_id == MANIFEST["id"]


def test_default_interruptible_per_manifest(plugin):
    assert plugin.transition_settings["interruptible"] is True


def test_no_stagger_yields_spin_frames_count(plugin):
    """With column_stagger=0, every column locks at the same frame."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={
                "spin_frames": 4,
                "column_stagger": 0,
                "frame_interval_ms": 0,
                "seed": 1,
            },
        )
    )
    # last_lock = (cols-1)*0 + 4 = 4 → 4 frames
    assert len(frames) == 4
    # Final frame must equal target.
    assert frames[-1][0] == _grid(1)


def test_stagger_extends_frame_count(plugin):
    """column_stagger>0 staggers the last lock further out."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={
                "spin_frames": 3,
                "column_stagger": 2,
                "frame_interval_ms": 0,
                "seed": 1,
            },
        )
    )
    # last_lock = (22-1)*2 + 3 = 45
    assert len(frames) == 45
    assert frames[-1][0] == _grid(1)


def test_columns_lock_left_to_right(plugin):
    """At intermediate frames, the leftmost columns are locked but rightmost are still spinning."""
    target = _grid(1)
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=target,
            device=DEVICE_DIMENSIONS["flagship"],
            config={
                "spin_frames": 2,
                "column_stagger": 3,
                "frame_interval_ms": 0,
                "seed": 1,
            },
        )
    )
    # last_lock = 21*3 + 2 = 65
    # At frame 5 (the 5th yielded), only columns where lock_at <= 5 are locked.
    # lock_at[c] = c*3 + 2 → c=0 locks at 2, c=1 at 5, c=2 at 8.
    mid_grid = frames[4][0]  # 5th frame
    # Columns 0 and 1 should be locked (value 1).
    assert mid_grid[0][0] == 1
    assert mid_grid[0][1] == 1
    # Column 2 still spinning - either a random tile or, by coincidence, the target.
    # We can't assert exact value, but we can assert it's a valid spin code or
    # the target.
    assert mid_grid[0][2] in [*_SPIN_CODES, 1]


def test_spinning_columns_use_spin_codes_only(plugin):
    """While spinning, columns show codes from the SPIN_CODES set (letters + digits)."""
    # Use a target of value 50 (clearly out of SPIN_CODES range).
    target = _grid(50)
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=target,
            device=DEVICE_DIMENSIONS["flagship"],
            config={
                "spin_frames": 4,
                "column_stagger": 5,
                "frame_interval_ms": 0,
                "seed": 1,
            },
        )
    )
    # First frame: no columns are locked (lock_at[0] = 4 > 1). All tiles
    # should be spin codes, none should be 50.
    first = frames[0][0]
    for row in first:
        for tile in row:
            assert tile in _SPIN_CODES
            assert tile != 50


def test_deterministic_seed_produces_same_sequence():
    cfg = {
        "spin_frames": 4,
        "column_stagger": 1,
        "frame_interval_ms": 0,
        "seed": 12345,
    }
    p1 = SlotMachineTransition(MANIFEST)
    p2 = SlotMachineTransition(MANIFEST)
    f1 = list(p1.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    f2 = list(p2.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    assert f1 == f2


def test_seed_zero_is_nondeterministic(plugin):
    """seed=0 means 'fresh random each call'."""
    cfg = {
        "spin_frames": 2,
        "column_stagger": 1,
        "frame_interval_ms": 0,
        "seed": 0,
    }
    # Just verify it terminates and finishes on target.
    frames = list(plugin.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    assert frames[-1][0] == _grid(1)


def test_handles_note_device(plugin):
    """Note board (3×15) works."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0, rows=3, cols=15),
            to_grid=_grid(2, rows=3, cols=15),
            device=DEVICE_DIMENSIONS["note"],
            config={
                "spin_frames": 3,
                "column_stagger": 1,
                "frame_interval_ms": 0,
                "seed": 7,
            },
        )
    )
    # last_lock = 14*1 + 3 = 17
    assert len(frames) == 17
    assert frames[-1][0] == _grid(2, rows=3, cols=15)


def test_clamps_spin_frames_to_at_least_one(plugin):
    """spin_frames=0 is clamped to 1."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={
                "spin_frames": 0,
                "column_stagger": 0,
                "frame_interval_ms": 0,
                "seed": 1,
            },
        )
    )
    assert len(frames) == 1
    assert frames[0][0] == _grid(1)


def test_empty_to_grid_produces_no_frames(plugin):
    frames = list(plugin.generate_frames(from_grid=[], to_grid=[], device=None, config={}))
    assert frames == []


def test_uses_defaults_when_config_missing(plugin):
    """Empty config still produces a valid run using manifest defaults."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={},
        )
    )
    # defaults: spin_frames=6, column_stagger=1 → last_lock = 21*1 + 6 = 27
    assert len(frames) == 27
    assert frames[0][1] == 80  # default frame_interval_ms
    assert frames[-1][0] == _grid(1)
