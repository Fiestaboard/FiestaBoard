"""Tests for the Quiet Library transition plugin."""

import json
from pathlib import Path

import pytest

from plugins.quiet_library import (
    QuietLibraryTransition,
    _group_row_changes,
    _word_segments,
)
from src.devices import BoardContext

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text())

FLAGSHIP = BoardContext(device_type="flagship", rows=6, cols=22)


@pytest.fixture
def plugin() -> QuietLibraryTransition:
    return QuietLibraryTransition(MANIFEST)


def _grid(value: int, rows: int = 6, cols: int = 22):
    return [[value] * cols for _ in range(rows)]


def _row(text: str, cols: int = 22):
    """Build a row of tile codes from text: '.' = blank(0), letters = ord offset."""
    codes = [0 if ch == "." else (ord(ch) - ord("A") + 1) for ch in text]
    return codes + [0] * (cols - len(codes))


def test_plugin_id_matches_manifest(plugin):
    assert plugin.plugin_id == MANIFEST["id"]


def test_transition_settings_loaded_from_manifest(plugin):
    settings = plugin.transition_settings
    assert settings["interruptible"] is True
    assert settings["max_frames"] == 512
    assert settings["max_runtime_seconds"] == 1800
    assert settings["min_interval_ms"] == 1000


# ---------------------------------------------------------------------------
# Word segmentation
# ---------------------------------------------------------------------------


def test_word_segments_finds_words():
    assert _word_segments(_row("HI.THERE.", 9)) == [(0, 2), (3, 8)]


def test_word_segments_empty_row():
    assert _word_segments([0] * 10) == []


def test_word_segments_word_at_row_end():
    assert _word_segments(_row("..HI", 4)) == [(2, 4)]


# ---------------------------------------------------------------------------
# Change grouping
# ---------------------------------------------------------------------------


def test_changes_grouped_per_word():
    """Changed cells in two different words form two separate blocks."""
    target = _row("HI.THERE", 8)
    blocks = _group_row_changes([0, 1, 3, 4], target)
    assert blocks == [[0, 1], [3, 4]]


def test_trailing_space_cleanup_attaches_to_preceding_word():
    """A cell cleared to blank after a word rides with that word's block."""
    target = _row("HI......", 8)
    # Cols 0-1 write the word; cols 2-4 clear leftovers from the old frame.
    blocks = _group_row_changes([0, 1, 2, 3, 4], target)
    assert blocks == [[0, 1, 2, 3, 4]]


def test_leading_cleanup_attaches_to_following_word():
    """Blank-target cells before the row's first word join that word."""
    target = _row("...HI", 5)
    blocks = _group_row_changes([0, 1, 3, 4], target)
    assert blocks == [[0, 1, 3, 4]]


def test_row_cleared_entirely_forms_single_block():
    """A row with no words in the target still groups its cleanup cells."""
    target = [0] * 8
    blocks = _group_row_changes([2, 3, 6], target)
    assert blocks == [[2, 3, 6]]


def test_no_changes_yields_no_blocks():
    assert _group_row_changes([], _row("HI", 2)) == []


# ---------------------------------------------------------------------------
# Frame generation
# ---------------------------------------------------------------------------


def test_no_diff_yields_no_frames(plugin):
    grid = _grid(5)
    frames = list(plugin.generate_frames(grid, grid, FLAGSHIP, {}))
    assert frames == []


def test_batches_never_span_words(plugin):
    """Two 2-letter words with batch_size=6 still take two frames."""
    from_grid = _grid(0, rows=1, cols=8)
    to_grid = [_row("HI.BY", 8)]
    frames = list(plugin.generate_frames(from_grid, to_grid, FLAGSHIP, {"batch_size": 6, "step_delay_ms": 0}))
    assert len(frames) == 2
    # First frame flips only the first word.
    assert frames[0][0][0][:3] == to_grid[0][:3]
    assert frames[0][0][0][3:5] == [0, 0]
    # Second frame completes the target.
    assert frames[1][0] == to_grid


def test_word_larger_than_batch_is_micro_batched(plugin):
    """A 7-letter word with batch_size=6 splits into a 6-tile and a 1-tile step."""
    from_grid = _grid(0, rows=1, cols=10)
    to_grid = [_row("LIBRARY", 10)]
    frames = list(plugin.generate_frames(from_grid, to_grid, FLAGSHIP, {"batch_size": 6, "step_delay_ms": 0}))
    assert len(frames) == 2
    first_flipped = sum(1 for c in range(10) if frames[0][0][0][c] != 0)
    assert first_flipped == 6
    assert frames[1][0] == to_grid


def test_final_frame_equals_target(plugin):
    frames = list(plugin.generate_frames(_grid(3), _grid(7), FLAGSHIP, {"batch_size": 6, "step_delay_ms": 0}))
    assert frames[-1][0] == _grid(7)


def test_step_delay_applied_to_every_frame(plugin):
    frames = list(
        plugin.generate_frames(
            _grid(0, rows=1, cols=4),
            [_row("HI.A", 4)],
            FLAGSHIP,
            {"batch_size": 2, "step_delay_ms": 2000},
        )
    )
    assert frames
    assert all(delay == 2000 for _, delay in frames)


def test_default_delay_clears_flap_debounce(plugin):
    frames = list(plugin.generate_frames(_grid(0, rows=1, cols=2), [_row("HI", 2)], FLAGSHIP, {}))
    assert frames[0][1] == 14_500


def test_unchanged_cells_never_touched_early(plugin):
    """Cells identical in from/to are never flipped in intermediate frames."""
    from_grid = [_row("HI.OLD", 6)]
    to_grid = [_row("HI.NEW", 6)]
    frames = list(plugin.generate_frames(from_grid, to_grid, FLAGSHIP, {"batch_size": 1, "step_delay_ms": 0}))
    for grid, _ in frames:
        assert grid[0][:3] == from_grid[0][:3]  # "HI " untouched throughout


def test_mismatched_from_grid_shape_is_tolerated(plugin):
    """A from-grid smaller than the target is padded with blanks, not crashed."""
    from_grid = [[1, 2]]  # 1x2 stale cache
    to_grid = [_row("HI", 4), _row("YO", 4)]
    frames = list(plugin.generate_frames(from_grid, to_grid, FLAGSHIP, {"batch_size": 6, "step_delay_ms": 0}))
    assert frames[-1][0] == to_grid


def test_empty_target_grid_yields_nothing(plugin):
    assert list(plugin.generate_frames([], [], FLAGSHIP, {})) == []


def test_note_array_dimensions_supported(plugin):
    """Works on a 2x1 note array (6x30) grid, not just flagship."""
    ctx = BoardContext(device_type="note_array", rows=6, cols=30)
    frames = list(
        plugin.generate_frames(
            _grid(0, rows=6, cols=30),
            _grid(4, rows=6, cols=30),
            ctx,
            {"batch_size": 15, "step_delay_ms": 0},
        )
    )
    assert frames[-1][0] == _grid(4, rows=6, cols=30)
