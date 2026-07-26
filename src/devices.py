"""Device type definitions and board dimensions.

Defines the supported Vestaboard device types and their physical constraints.
"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal, NamedTuple

DeviceType = Literal["flagship", "note", "note_array"]

DEVICE_TYPES = ("flagship", "note", "note_array")


class DeviceDimensions(NamedTuple):
    """Physical board dimensions for a device type."""

    rows: int
    cols: int


# Board dimensions per device type
DEVICE_DIMENSIONS: dict[str, DeviceDimensions] = {
    "flagship": DeviceDimensions(rows=6, cols=22),
    "note": DeviceDimensions(rows=3, cols=15),
}


# Note-array unit size and guardrail
NOTE_ROWS: int = 3
NOTE_COLS: int = 15
MAX_NOTES_PER_AXIS: int = 8

NOTE_ARRAY_PRESETS: list[dict] = [
    {"id": "2_wide", "label": "2 side-by-side", "notes_wide": 2, "notes_tall": 1},  # → 3 rows × 30 cols
    {"id": "4_wide", "label": "4 side-by-side", "notes_wide": 4, "notes_tall": 1},  # → 3 rows × 60 cols
    {"id": "2_tall", "label": "2 stacked", "notes_wide": 1, "notes_tall": 2},  # → 6 rows × 15 cols
    {"id": "4_tall", "label": "4 stacked", "notes_wide": 1, "notes_tall": 4},  # → 12 rows × 15 cols
    {"id": "2x2_grid", "label": "2×2 grid", "notes_wide": 2, "notes_tall": 2},  # → 6 rows × 30 cols
]

VALID_API_MODES = ("local", "cloud")

# Sensitive per-tile fields for local note arrays (masked in API responses)
TILE_SENSITIVE_FIELDS = {"local_api_key"}


def normalize_note_array_tiles(tiles) -> list[dict]:
    """Normalize a local note-array tile list.

    Each tile addresses one physical Note over the local API:
    ``{"row", "col", "host", "port", "local_api_key", "enabled"}`` with
    ``row``/``col`` 0-indexed in note coordinates.

    Drops non-dict entries and entries without a usable row/col, coerces field
    types, and dedupes by (row, col) keeping the last occurrence. Does NOT
    filter to the board's current notes_wide/notes_tall — out-of-range tiles
    are preserved in storage so shrinking and re-growing an array never
    destroys hard-to-reobtain local API keys. Filter at point of use via
    BoardInstance.configured_tiles().
    """
    if not isinstance(tiles, list):
        return []
    by_pos: dict[tuple[int, int], dict] = {}
    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        try:
            row = int(tile.get("row"))
            col = int(tile.get("col"))
        except (TypeError, ValueError):
            continue
        if isinstance(tile.get("row"), bool) or isinstance(tile.get("col"), bool):
            continue
        if row < 0 or col < 0:
            continue
        port = tile.get("port")
        if not isinstance(port, int) or isinstance(port, bool):
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 7000
        by_pos[(row, col)] = {
            "row": row,
            "col": col,
            "host": str(tile.get("host") or "").strip(),
            "port": port,
            "local_api_key": str(tile.get("local_api_key") or "").strip(),
            "enabled": bool(tile.get("enabled", True)),
        }
    return [by_pos[key] for key in sorted(by_pos)]


@dataclass
class BoardInstance:
    """A configured Vestaboard instance.

    Represents a single physical board with its own identity,
    device type, display color, and connection settings.
    Each board has its own API credentials and connection mode.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    device_type: str = "flagship"
    board_color: str = "black"
    enabled: bool = True
    # Per-board pause flag (issue #970). When True, FiestaBoard does not push
    # anything to this board — polling loop, schedule rotation, manual sends,
    # plugin triggers, MQTT commands, debug sends, welcome message, etc. The
    # board is left alone until the user resumes it. Distinct from
    # ``schedule_enabled``: pause silences ALL output paths, where disabling
    # the schedule only affects the schedule-driven rotation.
    paused: bool = False
    schedule_enabled: bool = False  # Per-board: use schedule mode for this board
    api_mode: str = "local"
    host: str = ""
    port: int = 7000  # Local API port (default Vestaboard); used for multi-board mock e2e
    local_api_key: str = ""
    cloud_key: str = ""
    note_array_token: str = ""  # X-Vestaboard-Token for note-array boards
    notes_wide: int = 1
    notes_tall: int = 1
    # Local array mode: per-tile local API endpoints, one per physical Note.
    # Only meaningful when device_type == "note_array" and api_mode == "local".
    tiles: list = field(default_factory=list)

    def __post_init__(self):
        if self.device_type not in DEVICE_TYPES:
            self.device_type = "flagship"
        if self.board_color not in ("black", "white"):
            self.board_color = "black"
        if self.api_mode not in VALID_API_MODES:
            self.api_mode = "local"
        if not isinstance(self.enabled, bool):
            self.enabled = bool(self.enabled)
        if not isinstance(self.paused, bool):
            self.paused = bool(self.paused)
        if not self.name:
            self.name = "My Board"
        # Normalize notes_wide / notes_tall: must be positive ints (bool is a
        # subclass of int, so reject it explicitly), clamped to MAX_NOTES_PER_AXIS
        if isinstance(self.notes_wide, bool) or not isinstance(self.notes_wide, int) or self.notes_wide < 1:
            self.notes_wide = 1
        if self.notes_wide > MAX_NOTES_PER_AXIS:
            self.notes_wide = MAX_NOTES_PER_AXIS
        if isinstance(self.notes_tall, bool) or not isinstance(self.notes_tall, int) or self.notes_tall < 1:
            self.notes_tall = 1
        if self.notes_tall > MAX_NOTES_PER_AXIS:
            self.notes_tall = MAX_NOTES_PER_AXIS
        # Tiles only make sense on note-array boards
        self.tiles = normalize_note_array_tiles(self.tiles) if self.device_type == "note_array" else []

    @property
    def uses_local_tiles(self) -> bool:
        """True when this note array is driven tile-by-tile over the local API.

        Requires BOTH api_mode == "local" and at least one saved tile: legacy
        array dicts created without an explicit api_mode default to "local"
        but carry only a cloud token — those must keep driving via the cloud.
        """
        return is_note_array(self.device_type) and self.api_mode == "local" and bool(self.tiles)

    @property
    def is_connection_configured(self) -> bool:
        if is_note_array(self.device_type):
            if self.uses_local_tiles:
                # A partial array is usable: assigned tiles receive their
                # slice, unassigned slots simply stay dark. Requiring every
                # slot would flip a half-assembled array back to
                # "unconfigured" and could re-trigger first-run detection.
                return bool(self.configured_tiles())
            # notes_wide/notes_tall are always >= 1 (clamped in __post_init__),
            # so configuration hinges solely on having a token.
            return bool(self.note_array_token)
        if self.api_mode == "cloud":
            return bool(self.cloud_key)
        return bool(self.local_api_key and self.host)

    def configured_tiles(self) -> list[dict]:
        """Return tiles that are in-range for the current W×H, enabled, and credentialed.

        Single source of truth for "which tiles can actually be driven" —
        used by the client factory, the configured check, and identify.
        """
        return [
            t
            for t in self.tiles
            if t["row"] < self.notes_tall
            and t["col"] < self.notes_wide
            and t["enabled"]
            and t["host"]
            and t["local_api_key"]
        ]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BoardInstance":
        port = data.get("port")
        if port is not None and not isinstance(port, int):
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 7000
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            device_type=data.get("device_type", "flagship"),
            board_color=data.get("board_color", "black"),
            enabled=data.get("enabled", True),
            paused=data.get("paused", False),
            schedule_enabled=data.get("schedule_enabled", False),
            api_mode=data.get("api_mode", "local"),
            host=data.get("host", ""),
            port=port if port is not None else 7000,
            local_api_key=data.get("local_api_key", ""),
            cloud_key=data.get("cloud_key", ""),
            note_array_token=(data.get("note_array_token") or "").strip(),
            notes_wide=data.get("notes_wide", 1),
            notes_tall=data.get("notes_tall", 1),
            tiles=data.get("tiles") or [],
        )


@dataclass(frozen=True)
class BoardContext:
    """Read-only description of the board a plugin is rendering on.

    Passed to plugins at render time so their code can adapt content to the
    physical board — e.g. show "Friday, August 27" on a Flagship (22x6) but
    "Fri, Aug 27" on a Note (15x3). Plugins read this via ``self.board``.

    ``rows``/``cols`` match the existing :class:`DeviceDimensions` convention;
    ``width``/``height`` are provided as readability aliases. Dimensions are
    stored explicitly (not re-derived from ``device_type``) so a future
    composite multi-board render can construct, e.g.,
    ``BoardContext("composite", rows=6, cols=30)`` directly without needing a
    matching :data:`DEVICE_DIMENSIONS` entry.
    """

    device_type: str  # "flagship" | "note" | future/composite
    rows: int  # height in tiles
    cols: int  # width in tiles

    @property
    def width(self) -> int:
        """Board width in tiles (alias for ``cols``)."""
        return self.cols

    @property
    def height(self) -> int:
        """Board height in tiles (alias for ``rows``)."""
        return self.rows

    @classmethod
    def from_device_type(cls, device_type: str) -> "BoardContext":
        """Build a context from a known device type.

        Args:
            device_type: "flagship" or "note"

        Raises:
            ValueError: If device_type is not recognized.
        """
        dims = get_dimensions(device_type)
        return cls(device_type=device_type, rows=dims.rows, cols=dims.cols)


def get_dimensions(device_type: str) -> DeviceDimensions:
    """Get board dimensions for a device type.

    Args:
        device_type: "flagship" or "note"

    Returns:
        DeviceDimensions with rows and cols

    Raises:
        ValueError: If device_type is not recognized
    """
    if device_type not in DEVICE_DIMENSIONS:
        raise ValueError(
            f"Unknown device type: {device_type}. "
            f"get_dimensions() supports {tuple(DEVICE_DIMENSIONS)}; "
            "for note arrays use resolve_dimensions()."
        )
    return DEVICE_DIMENSIONS[device_type]


def note_array_dimensions(notes_wide: int, notes_tall: int) -> DeviceDimensions:
    """Return dimensions for a note array grid.

    Does NOT validate inputs — call is_valid_note_array_grid separately if needed.
    """
    return DeviceDimensions(rows=notes_tall * NOTE_ROWS, cols=notes_wide * NOTE_COLS)


def is_note_array(device_type: str) -> bool:
    """Return True if device_type is 'note_array'."""
    return device_type == "note_array"


def slice_note_array_grid(
    grid: list[list[int]], notes_wide: int, notes_tall: int
) -> dict[tuple[int, int], list[list[int]]]:
    """Slice a full note-array grid into per-tile 3×15 subgrids.

    The grid must be exactly (notes_tall * NOTE_ROWS) × (notes_wide * NOTE_COLS).
    Returns subgrids keyed by (row, col) in note coordinates, 0-indexed.

    Raises ValueError if the grid does not match the expected dimensions.
    """
    dims = note_array_dimensions(notes_wide, notes_tall)
    if len(grid) != dims.rows or any(len(row) != dims.cols for row in grid):
        raise ValueError(f"Grid must be exactly {dims.rows}×{dims.cols} for a {notes_wide}×{notes_tall} note array")
    return {
        (tr, tc): [grid[tr * NOTE_ROWS + i][tc * NOTE_COLS : (tc + 1) * NOTE_COLS] for i in range(NOTE_ROWS)]
        for tr in range(notes_tall)
        for tc in range(notes_wide)
    }


def stitch_note_array_grid(
    subgrids: dict[tuple[int, int], list[list[int]]],
    notes_wide: int,
    notes_tall: int,
    fill: int = 0,
) -> list[list[int]]:
    """Stitch per-tile 3×15 subgrids back into a full note-array grid.

    Inverse of slice_note_array_grid. Missing or malformed subgrids leave
    their slot filled with ``fill``.
    """
    dims = note_array_dimensions(notes_wide, notes_tall)
    grid = [[fill] * dims.cols for _ in range(dims.rows)]
    for (tr, tc), sub in subgrids.items():
        if tr < 0 or tr >= notes_tall or tc < 0 or tc >= notes_wide:
            continue
        if not isinstance(sub, list) or len(sub) != NOTE_ROWS:
            continue
        if any(not isinstance(r, list) or len(r) != NOTE_COLS for r in sub):
            continue
        for i in range(NOTE_ROWS):
            grid[tr * NOTE_ROWS + i][tc * NOTE_COLS : (tc + 1) * NOTE_COLS] = sub[i]
    return grid


def identify_pattern(row: int, col: int, notes_wide: int) -> list[list[int]]:
    """Render the identify flash for one tile: a 3×15 grid labeling its slot.

    Shows the reading-order position number plus the (row, col) coordinate,
    1-indexed for humans — mirroring OS monitor-arrangement identify.
    """
    from .text_to_board import text_to_board_array

    position = row * notes_wide + col + 1
    text = f"\nPOSITION {position}\nR{row + 1} C{col + 1}"
    return text_to_board_array(text, rows=NOTE_ROWS, cols=NOTE_COLS)


def is_valid_note_array_grid(rows: int, cols: int) -> bool:
    """Return True if (rows, cols) is a valid note-array size.

    Valid means:
      - rows > 0 and cols > 0
      - rows is a multiple of NOTE_ROWS (3)
      - cols is a multiple of NOTE_COLS (15)
      - notes_tall = rows // NOTE_ROWS <= MAX_NOTES_PER_AXIS
      - notes_wide = cols // NOTE_COLS <= MAX_NOTES_PER_AXIS
    """
    if rows <= 0 or cols <= 0:
        return False
    if rows % NOTE_ROWS != 0 or cols % NOTE_COLS != 0:
        return False
    return (rows // NOTE_ROWS) <= MAX_NOTES_PER_AXIS and (cols // NOTE_COLS) <= MAX_NOTES_PER_AXIS


def resolve_dimensions(
    device_type: str,
    notes_wide: int = 1,
    notes_tall: int = 1,
) -> DeviceDimensions:
    """Resolve board dimensions for any device type.

    For 'flagship' and 'note': looks up DEVICE_DIMENSIONS (notes_wide/notes_tall ignored).
    For 'note_array': computes from notes_wide × notes_tall using NOTE_ROWS/NOTE_COLS.
    Raises ValueError for unknown device types.
    """
    if device_type in DEVICE_DIMENSIONS:
        return DEVICE_DIMENSIONS[device_type]
    if device_type == "note_array":
        return note_array_dimensions(notes_wide, notes_tall)
    raise ValueError(f"Unknown device type: {device_type}. Must be one of {DEVICE_TYPES}")


def classify_dimensions(rows: int, cols: int) -> dict:
    """Classify a grid (rows × cols) into a device type and optional note-array geometry.

    Used to auto-detect a board's type/size from a live layout read.

    Returns a dict with at minimum ``{"device_type", "rows", "cols"}``:

      - flagship / note:
        ``{"device_type": "flagship"|"note", "rows": int, "cols": int}``
      - note array (rows a multiple of NOTE_ROWS, cols a multiple of NOTE_COLS,
        each axis within MAX_NOTES_PER_AXIS, and not the fixed flagship/note size)::

            {
                "device_type": "note_array",
                "rows": int,
                "cols": int,
                "notes_wide": cols // NOTE_COLS,
                "notes_tall": rows // NOTE_ROWS,
                "matched_preset": <preset label> | None,
            }

    Order matters: an exact 6×22 is a flagship and an exact 3×15 is a Note —
    both are checked before the note-array branch, so a single Note never
    classifies as a 1×1 array.

    Raises ValueError for a grid that is neither the flagship size, the Note
    size, nor a valid note-array grid.
    """
    flagship = DEVICE_DIMENSIONS["flagship"]
    if rows == flagship.rows and cols == flagship.cols:
        return {"device_type": "flagship", "rows": rows, "cols": cols}

    note = DEVICE_DIMENSIONS["note"]
    if rows == note.rows and cols == note.cols:
        return {"device_type": "note", "rows": rows, "cols": cols}

    if is_valid_note_array_grid(rows, cols):
        notes_wide = cols // NOTE_COLS
        notes_tall = rows // NOTE_ROWS
        matched_preset: str | None = None
        for preset in NOTE_ARRAY_PRESETS:
            if preset["notes_wide"] == notes_wide and preset["notes_tall"] == notes_tall:
                matched_preset = preset["label"]
                break
        return {
            "device_type": "note_array",
            "rows": rows,
            "cols": cols,
            "notes_wide": notes_wide,
            "notes_tall": notes_tall,
            "matched_preset": matched_preset,
        }

    # All dimensions in this message are rows×cols (matching the "{rows}×{cols}"
    # grid description) so the comparison sizes read consistently.
    raise ValueError(
        f"Grid {rows}×{cols} is unclassifiable: not a flagship ({flagship.rows}×{flagship.cols}), "
        f"not a Note ({note.rows}×{note.cols}), and not a valid note-array grid "
        f"(rows must be a multiple of {NOTE_ROWS}, cols a multiple of {NOTE_COLS}, "
        f"each axis ≤ {MAX_NOTES_PER_AXIS} notes)."
    )


# Default device type for backward compatibility
DEFAULT_DEVICE_TYPE: DeviceType = "flagship"


def size_key(device_type: str, notes_wide: int = 1, notes_tall: int = 1) -> str:
    """Canonical family + resolved-size key for page<->board compatibility.

    Examples: ``"flagship:6x22"``, ``"note:3x15"``, ``"note_array:6x30"``
    (a 2x2 note grid). The device family is part of the key on purpose:
    a Note page is NOT compatible with a 1x1 note array even though both
    resolve to 3x15 — they are driven differently and are distinct families.

    Falls back to the default device type for an unrecognized ``device_type``
    so a bad stored value never crashes a validation path (mirrors
    :func:`board_context_for`).
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    except ValueError:
        device_type = DEFAULT_DEVICE_TYPE
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    return f"{device_type}:{dims.rows}x{dims.cols}"


def _geometry_of(obj) -> tuple[str, int, int]:
    """Extract (device_type, notes_wide, notes_tall) from a page/board.

    Accepts either a mapping (board dicts from settings storage) or an object
    with attributes (Page models, BoardInstance). Missing or falsy values get
    the platform defaults (flagship, 1x1).
    """
    if isinstance(obj, dict):
        device_type = obj.get("device_type") or DEFAULT_DEVICE_TYPE
        notes_wide = obj.get("notes_wide") or 1
        notes_tall = obj.get("notes_tall") or 1
    else:
        device_type = getattr(obj, "device_type", None) or DEFAULT_DEVICE_TYPE
        notes_wide = getattr(obj, "notes_wide", None) or 1
        notes_tall = getattr(obj, "notes_tall", None) or 1
    return str(device_type), int(notes_wide), int(notes_tall)


def pages_compatible_with_board(page, board) -> bool:
    """True when *page* renders 1:1 on *board*: EXACT :func:`size_key` match.

    Family-aware: flagship != note even at identical dimensions, and note
    arrays must match the resolved W×H grid exactly. Both arguments may be
    Page/BoardInstance objects or raw board dicts.
    """
    return size_key(*_geometry_of(page)) == size_key(*_geometry_of(board))


def board_context_for(device_type: str, notes_wide: int = 1, notes_tall: int = 1) -> BoardContext:
    """Build a :class:`BoardContext` for any device type, including note arrays.

    Unlike :meth:`BoardContext.from_device_type` (flagship/note only), this
    resolves note-array geometry from ``notes_wide``/``notes_tall`` via
    :func:`resolve_dimensions`, so plugins receive the board's true size. Falls
    back to the default device for an unrecognized type so a bad value never
    crashes a render.
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    except ValueError:
        device_type = DEFAULT_DEVICE_TYPE
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    return BoardContext(device_type=device_type, rows=dims.rows, cols=dims.cols)
