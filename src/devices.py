"""Device type definitions and board dimensions.

Defines the supported Vestaboard device types and their physical constraints.
"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Literal, NamedTuple, get_args

#: The device vocabulary, defined ONCE. ``DEVICE_TYPES`` is derived from the
#: Literal rather than retyped beside it: the two used to be hand-copied
#: siblings, and a wire model that spells its own copy of a vocabulary is the
#: second source of truth that eventually drifts from the one the runtime
#: enforces. Request models annotate ``device_type: DeviceType`` and get the
#: same set the storage layer validates against.
DeviceType = Literal["flagship", "note", "note_array", "panel"]

DEVICE_TYPES: tuple[str, ...] = get_args(DeviceType)

#: The shapes real Vestaboard hardware comes in. ``"panel"`` is FiestaPanel's
#: virtual per-character grid and is never a physical board, so surfaces that
#: describe hardware (adding a board, detecting a board's size) publish this.
HardwareDeviceType = Literal["flagship", "note", "note_array"]


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

# Panel grid bounds. A "panel" (FiestaPanel, a virtual board on a TV) is sized
# per character from the screen, so its grid is any rows × cols — not a
# multiple of a Note. The floor is one Note (3 × 15): every plugin and
# template is authored for at least that, and a screen too small for it gets
# a Note-sized grid the viewer shrinks to fit. The ceiling covers a 200" TV
# (the largest a panel accepts) in either orientation with headroom.
MIN_GRID_ROWS: int = NOTE_ROWS
MIN_GRID_COLS: int = NOTE_COLS
MAX_GRID_ROWS: int = 96
MAX_GRID_COLS: int = 128

#: Every field that sizes a page/board. A change to any of them is a size
#: retarget (re-validate, warn about now-incompatible references).
GEOMETRY_FIELDS: tuple[str, ...] = ("device_type", "notes_wide", "notes_tall", "grid_rows", "grid_cols")

# Board display names are user-editable (issue #1792) and are rendered in the
# sidebar board selector, Settings cards and page headers, so cap them at
# storage time rather than letting every call site truncate.
MAX_BOARD_NAME_LENGTH: int = 64
DEFAULT_BOARD_NAME: str = "My Board"

NOTE_ARRAY_PRESETS: list[dict] = [
    {"id": "2_wide", "label": "2 side-by-side", "notes_wide": 2, "notes_tall": 1},  # → 3 rows × 30 cols
    {"id": "4_wide", "label": "4 side-by-side", "notes_wide": 4, "notes_tall": 1},  # → 3 rows × 60 cols
    {"id": "2_tall", "label": "2 stacked", "notes_wide": 1, "notes_tall": 2},  # → 6 rows × 15 cols
    {"id": "4_tall", "label": "4 stacked", "notes_wide": 1, "notes_tall": 4},  # → 12 rows × 15 cols
    {"id": "2x2_grid", "label": "2×2 grid", "notes_wide": 2, "notes_tall": 2},  # → 6 rows × 30 cols
]

#: How a board is reached. Same one-definition rule as ``DeviceType`` above.
#: ``virtual`` is a real stored value (FiestaPanel boards), so it belongs in
#: the published vocabulary even though the legacy ``GET /config/board``
#: response advertises only the two hardware modes it can configure.
ApiMode = Literal["local", "cloud", "virtual"]

VALID_API_MODES: tuple[str, ...] = get_args(ApiMode)

# The first-party outputs (src/outputs/registry.py VESTABOARD / FIESTAPANEL),
# whose board settings core still projects to the settings-v3 flat shape.
# Spelled here because the outputs package imports this module;
# tests/test_output_plugin_e2e.py holds the two lists equal.
BUILTIN_OUTPUT_IDS = frozenset({"vestaboard", "fiestapanel"})

# Which glyph a board's character-code-62 flap physically carries (issue #1657).
#
# Code 62 is one code with two possible flaps. Vestaboard shipped every Flagship
# with a degree sign until 2026, then replaced it with a heart on newly
# manufactured units ("Every new Vestaboard purchased will ship with the heart in
# place of the degree symbol"). They published no serial or date boundary, so two
# boards that both report device_type "flagship" can draw different glyphs and
# nothing FiestaBoard can query distinguishes them — the owner has to say.
#
# Note and note-array hardware only ever carried the heart, so this is a Flagship
# setting; see BoardInstance.effective_code62_glyph.
Code62Glyph = Literal["degree", "heart"]

CODE62_GLYPHS = ("degree", "heart")

#: The settings-v3 flat connection fields: settings v3 stored a board's
#: connection at the top level of its dict. Settings v4 (plan D8) stores them
#: in the board's ``output_config``; a dict that still carries them at the
#: top level is a legacy write (or a v3 file), folded in by
#: :meth:`BoardInstance.from_dict`. Core keeps only their names — the shape
#: of its own old storage and of the flat API views; what they mean, and
#: their defaults, are the Vestaboard output's
#: (:mod:`src.outputs.config_hooks`).
LEGACY_CONNECTION_FIELDS: tuple[str, ...] = (
    "api_mode",
    "host",
    "port",
    "local_api_key",
    "cloud_key",
    "note_array_token",
    "tiles",
)

_VESTABOARD = "vestaboard"
_FIESTAPANEL = "fiestapanel"


def derive_output_id(board) -> str:
    """The output a board dict names, by the settings-v4 precedence rule.

    An explicit ``output`` wins; else ``api_mode == "virtual"`` is a
    FiestaPanel (this covers legacy virtual note-array panels, which predate
    the ``panel`` device type); else a Vestaboard. The same rule as
    :func:`src.outputs.registry.resolve_output_id`, spelled here because the
    outputs package imports this module.
    """
    explicit = board.get("output")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if str(board.get("api_mode") or "").lower() == "virtual":
        return _FIESTAPANEL
    return _VESTABOARD


@dataclass
class BoardInstance:
    """A configured board: identity, display, geometry, and its output.

    Settings v4 (plan D8): core keeps what is device-independent — identity,
    display (colour, code-62 glyph), flags, content geometry — plus the
    board's ``output`` (the output plugin that drives it) and
    ``output_config`` (that plugin's settings for it), stored as the output
    normalises it (:func:`src.outputs.config_hooks.normalize_config`); a
    FiestaPanel's is empty. What the settings mean is the output's: whether
    the board is configured is its :class:`~src.outputs.hooks.OutputStatus`.

    The read-only ``api_mode`` / ``host`` / ``port`` / ``local_api_key`` /
    ``cloud_key`` / ``note_array_token`` / ``tiles`` properties are the
    settings-v3 flat view (:func:`src.settings.board_shape.flat_connection`)
    for the readers and public API shapes that still speak it (D8 "Public
    API shapes unchanged"). Construct from flat fields with :meth:`from_dict`.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    device_type: str = "flagship"
    board_color: str = "black"
    # Which glyph this board's character-code-62 flap physically carries
    # (issue #1657). Vestaboard shipped every Flagship with a degree sign until
    # 2026, then replaced it with a heart on newly-manufactured units, and
    # published no serial or date boundary — so nothing FiestaBoard can query
    # tells a degree board from a heart board, and the owner has to say.
    #
    # Flagship only: Note and note-array hardware only ever carried the heart,
    # so ``effective_code62_glyph`` ignores this for them. Defaults to "degree",
    # the glyph every Flagship had before the change, so an existing install
    # renders exactly as it did before this field existed.
    #
    # Display-only. Both glyphs are character code 62 on the wire; this never
    # changes what is sent to a board.
    code62_glyph: str = "degree"
    enabled: bool = True
    # Per-board pause flag (issue #970). When True, FiestaBoard does not push
    # anything to this board — polling loop, schedule rotation, manual sends,
    # plugin triggers, MQTT commands, debug sends, welcome message, etc. The
    # board is left alone until the user resumes it. Distinct from
    # ``schedule_enabled``: pause silences ALL output paths, where disabling
    # the schedule only affects the schedule-driven rotation.
    paused: bool = False
    schedule_enabled: bool = False  # Per-board: use schedule mode for this board
    notes_wide: int = 1
    notes_tall: int = 1
    # Explicit grid for device_type == "panel" (FiestaPanel virtual boards are
    # sized per character from the TV, so they are any rows × cols). None for
    # every other device type, whose size is implied by the type/notes.
    grid_rows: int | None = None
    grid_cols: int | None = None
    # The output that drives this board (plan D2) and its settings for it.
    # Stored for every board since settings v4 (D8): "vestaboard",
    # "fiestapanel", or an output plugin's id.
    output: str = _VESTABOARD
    output_config: dict = field(default_factory=dict)
    # The FiestaUI device model an output plugin's board was created as
    # (POST /outputs/{output_id}/boards). Output-plugin boards only: absent
    # from to_dict for every other board.
    device_model: str | None = None

    def __post_init__(self):
        if self.device_type not in DEVICE_TYPES:
            self.device_type = "flagship"
        if self.board_color not in ("black", "white"):
            self.board_color = "black"
        if self.code62_glyph not in CODE62_GLYPHS:
            self.code62_glyph = "degree"
        self.output = self.output.strip() if isinstance(self.output, str) and self.output.strip() else _VESTABOARD
        # "panel" is a free rows × cols content grid: a FiestaPanel's, or an
        # output plugin's (an LED matrix is any rows × cols, plan D8). No
        # Vestaboard accepts an arbitrary rows × cols frame, so a Vestaboard
        # claiming it falls back to the default like any unknown type —
        # coercing a plugin's board instead would silently make a
        # non-Vestaboard board a Vestaboard-shaped one.
        if self.device_type == "panel" and self.output == _VESTABOARD:
            self.device_type = "flagship"
        if not isinstance(self.enabled, bool):
            self.enabled = bool(self.enabled)
        if not isinstance(self.paused, bool):
            self.paused = bool(self.paused)
        # Name is user-editable (issue #1792): strip, cap, and fall back to
        # the default. "   " is truthy, so a falsy-only guard stored
        # whitespace verbatim and rendered a blank sidebar row.
        self.name = self.name.strip()[:MAX_BOARD_NAME_LENGTH] if isinstance(self.name, str) else ""
        if not self.name:
            self.name = DEFAULT_BOARD_NAME
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
        # A panel always carries a valid grid (clamped; a missing axis falls
        # back to the Note-sized minimum so the board still resolves); every
        # other type carries none, so a stale grid can never leak into a
        # flagship's geometry after a type change.
        if is_panel(self.device_type):
            rows = _optional_int(self.grid_rows)
            cols = _optional_int(self.grid_cols)
            dims = clamp_grid(MIN_GRID_ROWS if rows is None else rows, MIN_GRID_COLS if cols is None else cols)
            self.grid_rows, self.grid_cols = dims.rows, dims.cols
        else:
            self.grid_rows = None
            self.grid_cols = None
        if self.output == _FIESTAPANEL:
            # A panel renders to memory: it has no connection to configure.
            self.output_config = {}
            self.device_model = None
        else:
            from src.outputs.config_hooks import normalize_config

            if self.output in BUILTIN_OUTPUT_IDS:
                self.device_model = None
            else:
                model = self.device_model.strip() if isinstance(self.device_model, str) else ""
                self.device_model = model or None
            self.output_config = normalize_config(self.output, self.output_config, self._geometry_facts())

    # --- the settings-v3 flat view, and the output's status ------------------------------

    def _geometry_facts(self) -> dict:
        """What an output reads about the board besides its settings."""
        return {
            "id": self.id,
            "device_type": self.device_type,
            "notes_wide": self.notes_wide,
            "notes_tall": self.notes_tall,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
            "output": self.output,
            "device_model": self.device_model,
        }

    def _flat(self, name: str):
        from src.settings.board_shape import flat_connection

        return flat_connection({"output": self.output, "output_config": self.output_config})[name]

    @property
    def api_mode(self) -> str:
        return self._flat("api_mode")

    @property
    def host(self) -> str:
        return self._flat("host")

    @property
    def port(self) -> int:
        return self._flat("port")

    @property
    def local_api_key(self) -> str:
        return self._flat("local_api_key")

    @property
    def cloud_key(self) -> str:
        return self._flat("cloud_key")

    @property
    def note_array_token(self) -> str:
        return self._flat("note_array_token")

    @property
    def tiles(self) -> list:
        return self._flat("tiles")

    @property
    def status(self):
        """The board's :class:`~src.outputs.hooks.OutputStatus` as its output
        reads its settings, or ``None`` when the output has nothing to say."""
        from src.outputs.config_hooks import board_status

        return board_status({**self._geometry_facts(), "output_config": self.output_config})

    @property
    def effective_code62_glyph(self) -> str:
        """The glyph this board actually draws for character code 62.

        Note and note-array hardware only ever shipped the heart flap (and
        panels imitate Note hardware, pitched like one), so the glyph is a
        property of the device there and ``code62_glyph`` is not theirs to set — a stale Flagship preference must not make a Note draw a
        degree sign it does not physically have. Only Flagship is ambiguous, and
        only there does the stored setting decide.

        Read this rather than ``code62_glyph`` anywhere a board is rendered.
        """
        if self.device_type in ("note", "note_array", "panel"):
            return "heart"
        return self.code62_glyph

    @property
    def is_connection_configured(self) -> bool:
        """Whether a driver can be built for this board (its output's
        :attr:`status`). A FiestaPanel always is; a board whose output has
        nothing to say is not."""
        status = self.status
        return status is not None and status.configured

    @property
    def has_connection_attempt(self) -> bool:
        """True when the user has entered ANY connection detail for this board.

        Deliberately weaker than :attr:`is_connection_configured`: a board
        with a host but no key (or a note array missing its token) is
        *misconfigured*, not *unconfigured*. First-run detection must use
        this, not the strict check — a misconfigured board should surface
        as a per-board error (#1813), never flip a working install back
        into the setup wizard (#1760). With no status from its output (one
        that is not installed), any stored setting counts.
        """
        status = self.status
        if status is None:
            return any(value not in (None, "", [], {}) for value in self.output_config.values())
        return status.attempted

    def to_dict(self) -> dict:
        """The board as settings v4 stores it."""
        data = asdict(self)
        if self.device_model is None:
            del data["device_model"]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "BoardInstance":
        """A board from a stored or incoming dict, settings v3 or v4.

        The output follows the precedence rule (:func:`derive_output_id`).
        For a Vestaboard, flat connection fields (a settings-v3 board, or a
        write in the legacy flat shape) are folded into ``output_config``,
        and win over a value the dict's ``output_config`` also carries: a
        dict carrying both halves is a flat write over a stored board. A
        caller that has the stored board and must honour whichever half the
        client actually changed merges first
        (:func:`src.settings.board_shape.merge_board_write`). Flat fields mean
        nothing to any other output and are dropped.
        """
        output = derive_output_id(data)
        config = data.get("output_config")
        if output == _VESTABOARD:
            flat = {name: data[name] for name in LEGACY_CONNECTION_FIELDS if name in data}
            config = {**(config if isinstance(config, dict) else {}), **flat}
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            device_type=data.get("device_type", "flagship"),
            board_color=data.get("board_color", "black"),
            # A board saved before this field existed has no key here, and the
            # default is "degree" — the glyph every Flagship carried before
            # Vestaboard changed the flap — so no stored board changes how it
            # renders and no migration is needed (issue #1657).
            code62_glyph=data.get("code62_glyph", "degree"),
            enabled=data.get("enabled", True),
            paused=data.get("paused", False),
            schedule_enabled=data.get("schedule_enabled", False),
            notes_wide=data.get("notes_wide", 1),
            notes_tall=data.get("notes_tall", 1),
            grid_rows=data.get("grid_rows"),
            grid_cols=data.get("grid_cols"),
            output=output,
            output_config=config,
            device_model=data.get("device_model"),
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


def is_panel(device_type: str) -> bool:
    """Return True if device_type is 'panel' (an explicit rows × cols grid)."""
    return device_type == "panel"


def clamp_grid(grid_rows: int, grid_cols: int) -> DeviceDimensions:
    """Clamp a panel grid into [MIN_GRID_*, MAX_GRID_*] on each axis."""
    return DeviceDimensions(
        rows=max(MIN_GRID_ROWS, min(MAX_GRID_ROWS, int(grid_rows))),
        cols=max(MIN_GRID_COLS, min(MAX_GRID_COLS, int(grid_cols))),
    )


def panel_dimensions(grid_rows: int | None, grid_cols: int | None) -> DeviceDimensions:
    """Dimensions of a panel grid, clamped into the supported range.

    Raises ValueError when either axis is missing or not an integer: a panel
    has no implied size, and guessing one would render content at the wrong
    shape without anyone noticing.
    """
    for name, value in (("grid_rows", grid_rows), ("grid_cols", grid_cols)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"A panel grid needs an integer {name} (got {value!r})")
    return clamp_grid(grid_rows, grid_cols)


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
    grid_rows: int | None = None,
    grid_cols: int | None = None,
) -> DeviceDimensions:
    """Resolve board dimensions for any device type.

    For 'flagship' and 'note': looks up DEVICE_DIMENSIONS (other args ignored).
    For 'note_array': computes from notes_wide × notes_tall using NOTE_ROWS/NOTE_COLS.
    For 'panel': the explicit grid_rows × grid_cols (see :func:`panel_dimensions`).
    Raises ValueError for unknown device types, or a panel without a grid.
    """
    if device_type in DEVICE_DIMENSIONS:
        return DEVICE_DIMENSIONS[device_type]
    if device_type == "note_array":
        return note_array_dimensions(notes_wide, notes_tall)
    if device_type == "panel":
        return panel_dimensions(grid_rows, grid_cols)
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


def size_key(
    device_type: str,
    notes_wide: int = 1,
    notes_tall: int = 1,
    grid_rows: int | None = None,
    grid_cols: int | None = None,
) -> str:
    """Canonical family + resolved-size key for page<->board compatibility.

    Examples: ``"flagship:6x22"``, ``"note:3x15"``, ``"note_array:6x30"``
    (a 2x2 note grid), ``"panel:12x29"``. The device family is part of the key on purpose:
    a Note page is NOT compatible with a 1x1 note array even though both
    resolve to 3x15 — they are driven differently and are distinct families.

    Falls back to the default device type for an unrecognized ``device_type``
    so a bad stored value never crashes a validation path (mirrors
    :func:`board_context_for`).
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide, notes_tall, grid_rows, grid_cols)
    except ValueError:
        device_type = DEFAULT_DEVICE_TYPE
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    return f"{device_type}:{dims.rows}x{dims.cols}"


class Geometry(NamedTuple):
    """Everything that determines a page's or board's grid.

    Positional order matches :func:`resolve_dimensions` / :func:`size_key` /
    :func:`board_context_for`, so ``f(*geometry_of(x))`` works for each.
    """

    device_type: str
    notes_wide: int = 1
    notes_tall: int = 1
    grid_rows: int | None = None
    grid_cols: int | None = None


def _optional_int(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def geometry_of(obj) -> Geometry:
    """Extract the :class:`Geometry` of a page/board.

    Accepts either a mapping (board dicts from settings storage) or an object
    with attributes (Page models, BoardInstance, overrides). Missing or falsy
    values get the platform defaults (flagship, 1x1, no explicit grid).
    """
    if isinstance(obj, dict):
        get = obj.get
    else:

        def get(name):
            return getattr(obj, name, None)

    return Geometry(
        device_type=str(get("device_type") or DEFAULT_DEVICE_TYPE),
        notes_wide=_optional_int(get("notes_wide")) or 1,
        notes_tall=_optional_int(get("notes_tall")) or 1,
        grid_rows=_optional_int(get("grid_rows")),
        grid_cols=_optional_int(get("grid_cols")),
    )


def dimensions_of(obj) -> DeviceDimensions:
    """Resolve the rows × cols of a page/board (see :func:`geometry_of`).

    Raises ValueError like :func:`resolve_dimensions` for an unknown type or a
    panel without a grid.
    """
    return resolve_dimensions(*geometry_of(obj))


def pages_compatible_with_board(page, board) -> bool:
    """True when *page* renders 1:1 on *board*: EXACT :func:`size_key` match.

    Family-aware: flagship != note even at identical dimensions, and note
    arrays and panels must match the resolved grid exactly. Both arguments may
    be Page/BoardInstance objects or raw board dicts.
    """
    return size_key(*geometry_of(page)) == size_key(*geometry_of(board))


def board_context_for(
    device_type: str,
    notes_wide: int = 1,
    notes_tall: int = 1,
    grid_rows: int | None = None,
    grid_cols: int | None = None,
) -> BoardContext:
    """Build a :class:`BoardContext` for any device type, including note arrays.

    Unlike :meth:`BoardContext.from_device_type` (flagship/note only), this
    resolves note-array geometry from ``notes_wide``/``notes_tall`` via
    :func:`resolve_dimensions`, so plugins receive the board's true size. Falls
    back to the default device for an unrecognized type so a bad value never
    crashes a render.
    """
    try:
        dims = resolve_dimensions(device_type, notes_wide, notes_tall, grid_rows, grid_cols)
    except ValueError:
        device_type = DEFAULT_DEVICE_TYPE
        dims = resolve_dimensions(device_type, notes_wide, notes_tall)
    return BoardContext(device_type=device_type, rows=dims.rows, cols=dims.cols)
