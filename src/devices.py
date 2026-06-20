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

    @property
    def is_connection_configured(self) -> bool:
        if is_note_array(self.device_type):
            # notes_wide/notes_tall are always >= 1 (clamped in __post_init__),
            # so configuration hinges solely on having a token.
            return bool(self.note_array_token)
        if self.api_mode == "cloud":
            return bool(self.cloud_key)
        return bool(self.local_api_key and self.host)

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
            note_array_token=data.get("note_array_token", "").strip(),
            notes_wide=data.get("notes_wide", 1),
            notes_tall=data.get("notes_tall", 1),
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
