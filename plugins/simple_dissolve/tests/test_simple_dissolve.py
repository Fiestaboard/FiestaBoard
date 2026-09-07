"""Tests for the simple_dissolve transition plugin."""

import json
from pathlib import Path

import pytest

from plugins.simple_dissolve import SimpleDissolveTransition
from src.devices import DEVICE_DIMENSIONS

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text())


@pytest.fixture
def plugin() -> SimpleDissolveTransition:
    return SimpleDissolveTransition(MANIFEST)


def _grid(value: int, rows: int = 6, cols: int = 22):
    return [[value] * cols for _ in range(rows)]


def test_plugin_id_matches_manifest(plugin):
    assert plugin.plugin_id == MANIFEST["id"]


def test_no_differences_yields_no_frames(plugin):
    """When from and to grids are identical, the plugin yields nothing."""
    grid = _grid(5)
    frames = list(
        plugin.generate_frames(
            from_grid=grid,
            to_grid=grid,
            device=DEVICE_DIMENSIONS["flagship"],
            config={"seed": 1},
        )
    )
    assert frames == []


def test_full_change_yields_expected_frame_count(plugin):
    """132 changed tiles at 6 per frame = 22 frames."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={"tiles_per_frame": 6, "frame_interval_ms": 0, "seed": 42},
        )
    )
    assert len(frames) == 22
    assert frames[-1][0] == _grid(1)


def test_only_differing_tiles_are_changed(plugin):
    """If only one tile differs, exactly one tile flips in the only frame."""
    from_grid = _grid(0)
    to_grid = _grid(0)
    to_grid[2][7] = 9
    frames = list(
        plugin.generate_frames(
            from_grid=from_grid,
            to_grid=to_grid,
            device=DEVICE_DIMENSIONS["flagship"],
            config={"tiles_per_frame": 10, "frame_interval_ms": 0, "seed": 1},
        )
    )
    assert len(frames) == 1
    final = frames[0][0]
    assert final == to_grid


def test_deterministic_seed_produces_same_order():
    """Same seed = same shuffle order = identical frame sequence."""
    p1 = SimpleDissolveTransition(MANIFEST)
    p2 = SimpleDissolveTransition(MANIFEST)
    cfg = {"tiles_per_frame": 4, "frame_interval_ms": 0, "seed": 12345}
    f1 = list(p1.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    f2 = list(p2.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    assert f1 == f2


def test_seed_zero_uses_random_default(plugin):
    """seed=0 is treated as 'no seed' (fresh random each run)."""
    cfg = {"tiles_per_frame": 4, "frame_interval_ms": 0, "seed": 0}
    f1 = list(plugin.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    # Different plugin, same args → likely a different order (statistical).
    plugin2 = SimpleDissolveTransition(MANIFEST)
    f2 = list(plugin2.generate_frames(_grid(0), _grid(1), DEVICE_DIMENSIONS["flagship"], cfg))
    # Both terminate on the target.
    assert f1[-1][0] == _grid(1)
    assert f2[-1][0] == _grid(1)


def test_handles_note_device(plugin):
    """Note dims (3x15)."""
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0, rows=3, cols=15),
            to_grid=_grid(2, rows=3, cols=15),
            device=DEVICE_DIMENSIONS["note"],
            config={"tiles_per_frame": 9, "frame_interval_ms": 30, "seed": 7},
        )
    )
    assert len(frames) == 5  # 45 / 9
    assert frames[-1][0] == _grid(2, rows=3, cols=15)


def test_handles_empty_to_grid(plugin):
    frames = list(plugin.generate_frames(from_grid=[], to_grid=[], device=DEVICE_DIMENSIONS["flagship"], config={}))
    assert frames == []


def test_tiles_per_frame_clamped_to_at_least_one(plugin):
    frames = list(
        plugin.generate_frames(
            from_grid=_grid(0),
            to_grid=_grid(1),
            device=DEVICE_DIMENSIONS["flagship"],
            config={"tiles_per_frame": 0, "frame_interval_ms": 0, "seed": 1},
        )
    )
    # treated as 1 → 132 frames
    assert len(frames) == 132


def test_partial_change_with_unchanged_tiles_preserved(plugin):
    """Tiles that don't differ are never modified during the dissolve."""
    from_grid = _grid(0)
    to_grid = _grid(0)
    to_grid[0][0] = 5
    to_grid[5][21] = 7
    frames = list(
        plugin.generate_frames(
            from_grid=from_grid,
            to_grid=to_grid,
            device=DEVICE_DIMENSIONS["flagship"],
            config={"tiles_per_frame": 1, "frame_interval_ms": 0, "seed": 1},
        )
    )
    # 2 changed tiles → 2 frames.
    assert len(frames) == 2
    # Every intermediate frame keeps non-diff tiles at 0.
    for grid, _ in frames:
        for r in range(6):
            for c in range(22):
                if (r, c) not in {(0, 0), (5, 21)}:
                    assert grid[r][c] == 0
    assert frames[-1][0] == to_grid
