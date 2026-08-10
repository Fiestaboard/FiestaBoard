"""Plugin board previews — the ``teaser`` and ``previews`` manifest contract.

A plugin describes what its board *looks like* as literal rows of board text,
so the docs site can render a real split-flap preview instead of shipping a
screenshot. Two fields:

``teaser``
    One line, at most :data:`MAX_TEASER_TILES` tiles. 15 is the Note width —
    the narrowest board FiestaBoard supports — so a teaser fits every device.
    Powers the one-line strip on plugin directory cards.

``previews``
    A list of boards, each declaring its own shape. Powers the detail page.

Both are *literal*: no ``{{variable}}`` placeholders, because there is no
plugin data to resolve against when the docs site renders them.

Validation deliberately reports what :func:`src.text_to_board.text_to_board_array`
would swallow. That function truncates at ``col_idx < cols`` and maps unknown
characters to ``SPACE``, which is correct at render time but hides authoring
mistakes — a row that is three tiles too wide should fail review, not silently
lose its last three tiles.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.board_chars import BoardChars
from src.devices import DEVICE_DIMENSIONS, DeviceDimensions, resolve_dimensions
from src.text_to_board import COLOR_MARKER_PATTERN, text_to_board_array

logger = logging.getLogger(__name__)

# Rendered previews for registry plugins that are not installed locally, so
# there is no manifest to read them from. Refreshed by
# ``scripts/sync_plugin_previews.py``; manifests always win over this seed.
PREVIEW_SEED_FILENAME = "plugin-previews.json"

# The Note is 15 columns — the narrowest board we support. A teaser that fits
# a Note fits everything.
MAX_TEASER_TILES = 15

# Enough to show a plugin across the shapes it supports without turning a
# detail page into a scrolling wall of boards.
MAX_PREVIEWS = 6

# Hardware allows 8×8 (``devices.MAX_NOTES_PER_AXIS``), but an 8×8 array is
# 120×24 = 2,880 tiles. That is not a preview, it is a performance incident.
# 4×4 caps a preview at 60×12 = 720 tiles.
MAX_PREVIEW_NOTES_PER_AXIS = 4

VALID_DEVICE_TYPES = (*DEVICE_DIMENSIONS.keys(), "note_array")

_TEMPLATE_VARIABLE = "{{"


def load_preview_seed(seed_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load rendered board previews for registry plugins.

    The marketplace lists plugins that are mostly *not* installed, so their
    manifests aren't on disk to read ``teaser``/``previews`` from. This seed
    file — refreshed by ``scripts/sync_plugin_previews.py`` — is what fills
    that gap; an installed plugin's own manifest always wins over it.

    Args:
        seed_path: Explicit path.  When *None* the file is located relative to
            the project root.

    Returns:
        ``{plugin_id: {"teaser": str, "previews": list[dict]}}``.  A missing or
        unreadable seed degrades to ``{}`` — no board on the card, never an
        error.
    """
    if seed_path is None:
        seed_path = Path(__file__).parent.parent.parent / PREVIEW_SEED_FILENAME

    if not seed_path.exists():
        logger.debug("Plugin preview seed not found at %s", seed_path)
        return {}

    try:
        with seed_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read plugin preview seed %s: %s", seed_path, exc)
        return {}

    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        logger.error("Plugin preview seed %s has no 'plugins' object", seed_path)
        return {}

    seeded: dict[str, dict[str, Any]] = {}
    for plugin_id, entry in plugins.items():
        if not isinstance(entry, dict):
            continue
        teaser = entry.get("teaser", "")
        previews = entry.get("previews", [])
        seeded[plugin_id] = {
            "teaser": teaser if isinstance(teaser, str) else "",
            "previews": previews if isinstance(previews, list) else [],
        }

    logger.debug("Loaded previews for %d plugins from the seed", len(seeded))
    return seeded


def count_tiles(text: str) -> int:
    """Count how many flaps *text* occupies.

    A colour marker (``{66}``, ``{green}``) is one tile regardless of how many
    characters it takes to write. Closing tags (``{/green}``, ``{/}``) are
    formatting artefacts and occupy none — matching ``text_to_board_array``,
    which skips them without advancing ``col_idx``.
    """
    tiles = 0
    pos = 0
    while pos < len(text):
        match = COLOR_MARKER_PATTERN.match(text, pos)
        if match:
            if not match.group(3):  # group(3) is the closing-tag alternative
                tiles += 1
            pos = match.end()
            continue
        tiles += 1
        pos += 1
    return tiles


def _unmappable_characters(text: str) -> list[str]:
    """Return characters the board cannot render, ignoring colour markers."""
    bad: list[str] = []
    pos = 0
    while pos < len(text):
        match = COLOR_MARKER_PATTERN.match(text, pos)
        if match:
            pos = match.end()
            continue
        char = text[pos]
        if BoardChars.get_char_code(char) is None and char not in bad:
            bad.append(char)
        pos += 1
    return bad


@dataclass
class BoardPreview:
    """One literal board, at one shape."""

    rows: list[str] = field(default_factory=list)
    device_type: str = "flagship"
    notes_wide: int = 1
    notes_tall: int = 1
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.default_label()

    @property
    def dimensions(self) -> DeviceDimensions:
        """Resolved ``(rows, cols)`` for this preview's declared shape."""
        return resolve_dimensions(self.device_type, self.notes_wide, self.notes_tall)

    def default_label(self) -> str:
        """A human label derived from the shape, used when none is declared."""
        if self.device_type == "note_array":
            return f"Note Array {self.notes_wide}×{self.notes_tall}"
        return "Flagship" if self.device_type == "flagship" else "Note"

    def to_grid(self) -> list[list[int]]:
        """Render to the character-code grid the hardware consumes.

        Short previews are padded with blanks; this is the same path a real
        page takes, so a preview that renders here renders on a board.
        """
        dims = self.dimensions
        return text_to_board_array("\n".join(self.rows), rows=dims.rows, cols=dims.cols)


def validate_teaser(teaser: Any) -> list[str]:
    """Validate a ``teaser`` value. Returns a list of human-readable errors."""
    if not isinstance(teaser, str):
        return ["teaser must be a string"]

    if not teaser.strip():
        return ["teaser cannot be empty"]

    if _TEMPLATE_VARIABLE in teaser:
        return ["teaser must be literal board text — {{variable}} references cannot be resolved in previews"]

    if "\n" in teaser:
        return ["teaser must be a single line"]

    errors: list[str] = []

    tiles = count_tiles(teaser)
    if tiles > MAX_TEASER_TILES:
        errors.append(
            f"teaser is {tiles} tiles; maximum is {MAX_TEASER_TILES} (the Note width, so teasers fit every board)"
        )

    bad = _unmappable_characters(teaser)
    if bad:
        errors.append(f"teaser contains characters the board cannot render: {' '.join(bad)}")

    return errors


def _validate_shape(entry: dict[str, Any], where: str) -> tuple[list[str], DeviceDimensions | None]:
    """Validate an entry's device shape, returning errors and resolved dims."""
    device_type = entry.get("device_type", "flagship")
    if device_type not in VALID_DEVICE_TYPES:
        return (
            [f"{where}.device_type must be one of {', '.join(VALID_DEVICE_TYPES)}, got '{device_type}'"],
            None,
        )

    if device_type != "note_array":
        return [], resolve_dimensions(device_type)

    errors: list[str] = []
    for axis in ("notes_wide", "notes_tall"):
        value = entry.get(axis, 1)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"{where}.{axis} must be an integer >= 1")
        elif value > MAX_PREVIEW_NOTES_PER_AXIS:
            errors.append(
                f"{where}.{axis} is {value}; previews are capped at "
                f"{MAX_PREVIEW_NOTES_PER_AXIS} notes per axis to keep detail pages light"
            )

    if errors:
        return errors, None
    return [], resolve_dimensions(device_type, entry.get("notes_wide", 1), entry.get("notes_tall", 1))


def _validate_rows(rows: Any, dims: DeviceDimensions, where: str) -> list[str]:
    """Validate a preview's rows against resolved device dimensions."""
    if not isinstance(rows, list):
        return [f"{where}.rows must be an array of strings"]

    if len(rows) > dims.rows:
        return [f"{where} declares {len(rows)} rows; this board has {dims.rows}"]

    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, str):
            errors.append(f"{where}.rows[{index}] must be a string")
            continue

        tiles = count_tiles(row)
        if tiles > dims.cols:
            errors.append(f"{where}.rows[{index}] is {tiles} tiles wide; this board is {dims.cols}")

        bad = _unmappable_characters(row)
        if bad:
            errors.append(f"{where}.rows[{index}] contains characters the board cannot render: {' '.join(bad)}")

    return errors


def validate_previews(previews: Any) -> list[str]:
    """Validate a ``previews`` value. Returns a list of human-readable errors."""
    if not isinstance(previews, list):
        return ["previews must be an array"]

    if not previews:
        return ["previews must contain at least one board"]

    if len(previews) > MAX_PREVIEWS:
        return [f"previews declares {len(previews)} boards; maximum is {MAX_PREVIEWS}"]

    errors: list[str] = []
    for index, entry in enumerate(previews):
        where = f"previews[{index}]"

        if not isinstance(entry, dict):
            errors.append(f"{where} must be an object")
            continue

        if "rows" not in entry:
            errors.append(f"{where} missing required field: rows")
            continue

        shape_errors, dims = _validate_shape(entry, where)
        if shape_errors:
            errors.extend(shape_errors)
            continue

        assert dims is not None  # _validate_shape returns dims whenever it reports no errors
        errors.extend(_validate_rows(entry["rows"], dims, where))

    return errors


def parse_previews(previews: Any) -> list[BoardPreview]:
    """Parse into :class:`BoardPreview` objects, skipping malformed entries.

    Parsing is lenient by design — :func:`validate_previews` is what rejects.
    This keeps a bad entry in one plugin's manifest from breaking the loader
    for everything else.
    """
    if not isinstance(previews, list):
        return []

    parsed: list[BoardPreview] = []
    for entry in previews:
        if not isinstance(entry, dict) or not isinstance(entry.get("rows"), list):
            continue
        device_type = entry.get("device_type", "flagship")
        if device_type not in VALID_DEVICE_TYPES:
            continue
        rows = [row for row in entry["rows"] if isinstance(row, str)]
        parsed.append(
            BoardPreview(
                rows=rows,
                device_type=device_type,
                notes_wide=entry.get("notes_wide", 1) if isinstance(entry.get("notes_wide", 1), int) else 1,
                notes_tall=entry.get("notes_tall", 1) if isinstance(entry.get("notes_tall", 1), int) else 1,
                label=entry.get("label", "") if isinstance(entry.get("label", ""), str) else "",
            )
        )
    return parsed
