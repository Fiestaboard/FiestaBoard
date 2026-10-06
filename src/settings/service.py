"""Settings service for managing runtime configuration.

This service allows runtime modification of settings like transition
animations and output targets, which can be controlled from the UI.
"""

import functools
import json
import logging
import os
import shutil
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Optional, TypeVar, get_args

from pydantic import BaseModel, ValidationError

from src.atomic_io import staging_path, write_json_atomic
from src.storage.json_store import JsonStore, SchemaTooNewError

_Section = TypeVar("_Section")

logger = logging.getLogger(__name__)

# Valid values for the built-in (hardware) transition strategies.  Plugin
# transitions use the ``plugin:<id>`` form and are validated dynamically
# against the transition-plugin registry rather than this list.
VALID_STRATEGIES = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

#: Where rendered content goes. The Literal is the definition and the list is
#: derived from it, so a request model annotated ``target: OutputTarget``
#: publishes exactly the set ``set_output_target`` enforces — they used to be
#: two hand-copied spellings of the same three words.
OutputTarget = Literal["ui", "board", "both"]
VALID_OUTPUT_TARGETS = list(get_args(OutputTarget))

#: The six BUILT-IN strategies. Deliberately NOT the whole vocabulary and so
#: deliberately not a wire enum: ``is_valid_strategy`` also accepts any
#: ``plugin:<id>`` reference, so a closed enum on the wire would refuse every
#: transition plugin.
TransitionStrategy = Literal["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

# Prefix that marks a strategy string as referring to a transition plugin
# (e.g. ``"plugin:typewriter"``).  Kept in sync with
# :data:`src.outputs.transitions.TRANSITION_PLUGIN_PREFIX`.
TRANSITION_PLUGIN_PREFIX = "plugin:"


def is_valid_strategy(strategy: str | None) -> bool:
    """Return True if *strategy* is None, a built-in, or a plugin reference.

    Plugin references must carry a non-empty id after stripping whitespace;
    ``"plugin: "`` and similar typos are rejected here rather than being
    silently accepted and then falling through to a non-animated send at
    render time.  The runtime separately checks whether the named plugin
    is actually loaded and enabled before driving a transition.
    """
    if strategy is None:
        return True
    if strategy in VALID_STRATEGIES:
        return True
    if isinstance(strategy, str) and strategy.startswith(TRANSITION_PLUGIN_PREFIX):
        plugin_id = strategy[len(TRANSITION_PLUGIN_PREFIX) :].strip()
        return bool(plugin_id)
    return False


#: A display's own "no transition" (plan D21). Distinct from an unset choice,
#: which on an output plugin's board means its device model's default.
BOARD_TRANSITION_NONE = "none"

#: The engine's runtime key for the primary board when it has no id of its
#: own yet (``DisplayService._PRIMARY_FALLBACK_KEY``): reads the first board.
PRIMARY_RUNTIME_KEY = "__primary__"


def is_valid_board_transition(choice: str | None) -> bool:
    """Whether *choice* is something a display's transition menu offers.

    ``None`` (the device's default), ``"none"``, a split-flap
    strategy or ``plugin:<id>`` (:func:`is_valid_strategy`), or an LED menu
    id (FiestaUI's registry, :func:`src.led.transition_registry.is_led_transition_id`).
    Whether the device can run it is the runtime's call: an LED choice a
    device cannot honour falls back to its model's default with a reason.
    """
    if choice is None or choice == BOARD_TRANSITION_NONE or is_valid_strategy(choice):
        return True
    from src.led.transition_registry import is_led_transition_id

    return is_led_transition_id(choice)


@dataclass
class TransitionSettings:
    """The transition one display runs: its strategy and speed.

    Settings v6: a display's own (``SettingsService.get_transition_settings``);
    there is no install-wide transition any more.
    """

    strategy: str | None = None
    step_interval_ms: int | None = None
    step_size: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TransitionSettings":
        return cls(
            strategy=data.get("strategy"),
            step_interval_ms=data.get("step_interval_ms"),
            step_size=data.get("step_size"),
        )


def page_transition(display, page, runs: Callable[[str], bool] | None = None) -> TransitionSettings:
    """What a send of *page* runs on a display whose own transition is
    *display* (anything with ``strategy`` / ``step_interval_ms`` /
    ``step_size``): the page's own transition where it sets one, field by
    field, else the display's.

    A page strategy counts when it is truthy; a page interval or step size
    counts whenever it is not ``None`` (0 ms is a real choice). *runs* is the
    board driver's own answer to "can you run this?"
    (:func:`src.outputs.transitions.driver_runs_strategy`): a page strategy
    it cannot run (a split-flap strategy on an LED display, an LED id on a
    Vestaboard...) does not override the display's, and the send runs the
    display's transition, speed included, since the page's speed was chosen
    for its strategy. Without *runs*, the page strategy is taken as given.
    """
    strategy = getattr(page, "transition_strategy", None)
    interval = getattr(page, "transition_interval_ms", None)
    step_size = getattr(page, "transition_step_size", None)
    if isinstance(strategy, str) and strategy and runs is not None and not runs(strategy):
        logger.debug("Page transition %r cannot run on this board; using the board's own", strategy)
        strategy = interval = step_size = None
    return TransitionSettings(
        strategy=strategy if strategy else display.strategy,
        step_interval_ms=interval if interval is not None else display.step_interval_ms,
        step_size=step_size if step_size is not None else display.step_size,
    )


@dataclass
class OutputSettings:
    """Output target settings."""

    target: OutputTarget = "board"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "OutputSettings":
        target = data.get("target", "board")
        if target not in VALID_OUTPUT_TARGETS:
            target = "board"
        return cls(target=target)


@dataclass
class ActivePageSettings:
    """Active page settings for display.

    The manual active page is stored **per-board** in ``by_board`` (board_id ->
    page_id). ``page_id`` is kept as a back-compat mirror of the *primary*
    board's value for one release so older readers (and external tooling) keep
    working. New code should go through ``SettingsService.get_active_page_id``
    / ``set_active_page_id`` rather than touching these fields directly.
    """

    page_id: str | None = None
    by_board: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActivePageSettings":
        raw_by_board = data.get("by_board") or {}
        # Defensively coerce to a plain str->str dict; ignore malformed entries.
        if isinstance(raw_by_board, dict):
            clean = {str(k): str(v) for k, v in raw_by_board.items() if isinstance(v, str)}
        else:
            clean = {}
        return cls(page_id=data.get("page_id"), by_board=clean)


BOARD_READ_INTERVAL_MIN = 20  # Hard floor: no faster than once every 20 seconds


@dataclass
class PollingSettings:
    """Polling interval settings for board updates."""

    interval_seconds: int = 15  # Default to 15 seconds
    board_read_interval_local: int = 30  # How often to read board state in local mode
    board_read_interval_cloud: int = 180  # How often to read board state in cloud mode (3 min)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PollingSettings":
        interval = data.get("interval_seconds", 15)
        if interval < 10:
            interval = 10
        read_local = data.get("board_read_interval_local", 30)
        if read_local < BOARD_READ_INTERVAL_MIN:
            read_local = BOARD_READ_INTERVAL_MIN
        read_cloud = data.get("board_read_interval_cloud", 180)
        if read_cloud < BOARD_READ_INTERVAL_MIN:
            read_cloud = BOARD_READ_INTERVAL_MIN
        return cls(
            interval_seconds=interval,
            board_read_interval_local=read_local,
            board_read_interval_cloud=read_cloud,
        )


def _output_settings_schema(output_id: str | None) -> dict | None:
    """The ``output_config`` schema of an installed output plugin, else ``None``."""
    from src.outputs.registry import output_registry

    definition = output_registry().get(output_id)
    return dict(definition.settings_schema) if definition is not None and definition.plugin else None


def _restore_output_config(board: dict, existing: dict) -> object:
    """The incoming board's ``output_config`` with echoed secrets restored.

    Raises ``ValueError`` when a secret cannot be restored (an array element
    that no longer matches a stored one) or the config does not fit the
    output's ``settings_schema`` — a credential is never saved as ``"***"``.
    """
    from src.outputs.config_hooks import masked_config_paths, restore_config
    from src.outputs.output_config import board_context, validate_output_config

    output_id = board.get("output")
    schema = _output_settings_schema(output_id)
    stored = existing.get("output_config") if existing.get("output") == output_id else None
    config = restore_config(output_id, board["output_config"], stored)
    unresolved = masked_config_paths(output_id, config)
    if unresolved:
        raise ValueError(f"Re-enter the secret settings for board output '{output_id}': {', '.join(unresolved)}")
    if schema is not None:
        errors = validate_output_config(config if config is not None else {}, schema, board_context(board))
        if errors:
            raise ValueError("; ".join(errors))
    return config


def restore_masked_board_secrets(board: dict, existing: dict) -> dict:
    """Restore every echoed ``"***"`` secret in *board* from *existing*, in place.

    The one merge rule for a board coming back from the API masked. *board*
    may be in either shape (settings-v3 flat fields, the v4
    ``output_config``, or both — an echo of ``GET /settings/board``);
    *existing* is the stored board. Every ``output_config`` is restored by
    its output's rules (:mod:`src.outputs.config_hooks`) — a Vestaboard's by
    its plugin's (each tile's key matched by endpoint, then by position:
    tiles carry no id), an output plugin's by its schema's secrets — and the
    settings-v3 flat fields of a legacy write by the Vestaboard's, whose
    settings they are. ``set_boards`` runs it on every save, and the
    saved-board action route (``POST /boards/{id}/actions/{action}``) on every
    action body, so a test run from the settings page never tests a literal
    ``***``.

    Raises ``ValueError`` when an output plugin's ``output_config`` secret
    cannot be restored or the config does not fit the output's schema.
    """
    from src.devices import LEGACY_CONNECTION_FIELDS, derive_output_id
    from src.outputs.config_hooks import restore_config, restore_flat_fields
    from src.settings.board_shape import FIESTAPANEL, VESTABOARD, flat_connection

    stored = flat_connection(existing) if existing else {}
    flat = {key: board[key] for key in LEGACY_CONNECTION_FIELDS if key in board}
    if flat:
        board.update(restore_flat_fields(flat, stored))
    if "output_config" in board:
        output_id = derive_output_id(board)
        if output_id == VESTABOARD:
            if isinstance(board["output_config"], dict):
                board["output_config"] = restore_config(VESTABOARD, board["output_config"], stored)
        elif output_id != FIESTAPANEL:
            board["output_config"] = _restore_output_config(board, existing)
    return board


@dataclass
class BoardSettings:
    """Board display settings for UI rendering.

    Supports multiple board instances, each with its own device type,
    board color, and connection settings. The `devices` property provides
    backward-compatible access to the list of unique device types.
    """

    board_type: Literal["black", "white"] | None = "black"
    boards: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if not self.boards:
            from src.devices import BoardInstance

            self.boards = [
                BoardInstance(
                    name="My Board",
                    device_type="flagship",
                    board_color=self.board_type or "black",
                ).to_dict()
            ]

    @property
    def devices(self) -> list[str]:
        """Backward-compatible list of unique device types across all boards."""
        from src.devices import DEVICE_TYPES

        seen: set[str] = set()
        result = []
        for b in self.boards:
            dt = b.get("device_type", "flagship")
            if dt not in seen and dt in DEVICE_TYPES:
                seen.add(dt)
                result.append(dt)
        return result if result else ["flagship"]

    @staticmethod
    def _mask_board(board: dict) -> dict:
        """Return the API view of a board dict: the flat view, secrets masked.

        Settings v4 stores a Vestaboard's connection in ``output_config``;
        the API still answers in the settings-v3 flat shape
        (:func:`src.settings.board_shape.board_view`, plan D8), with
        ``output`` and ``output_config`` beside it. Credentials are masked in
        both halves, by the output's rules (:mod:`src.outputs.config_hooks`):
        the ``output_config`` — a Vestaboard's by its plugin's, an output
        plugin's by its schema's secrets (an uninstalled output's is withheld
        whole) — and the flat fields by the Vestaboard's, whose settings they
        are. Masking copies, so it never corrupts the stored dicts.

        Also carries the resolved FiestaUI ``device_model`` and ``charset``
        ids (src/outputs/board_profile.py). ``device_model_spec`` -- the
        model document, for a model FiestaUI does not build in (a
        FiestaPanel's, a plugin's own) -- is added only then. ``led_layout``
        -- an LED board's resolved ``tile_gap`` / ``block_padding`` (plan
        D23), what its preview must draw to match the device -- is added only
        for an LED board.
        """
        from src.devices import LEGACY_CONNECTION_FIELDS
        from src.outputs.board_profile import board_led_layout, board_model_spec, board_profile
        from src.outputs.config_hooks import mask_config, mask_flat_fields
        from src.settings.board_shape import FIESTAPANEL, board_view

        masked = board_view(board)
        masked.update(mask_flat_fields({key: masked[key] for key in LEGACY_CONNECTION_FIELDS}))
        output_id = masked["output"]
        masked["device_model"], masked["charset"] = board_profile(board)
        spec = board_model_spec(board)
        if spec is not None:
            masked["device_model_spec"] = spec
        led_layout = board_led_layout(board)
        if led_layout is not None:
            masked["led_layout"] = led_layout
        if output_id != FIESTAPANEL:
            masked["output_config"] = mask_config(output_id, masked["output_config"])
        return masked

    def to_dict(self, mask_secrets: bool = True) -> dict:
        boards = [self._mask_board(b) for b in self.boards] if mask_secrets else self.boards
        return {
            "board_type": self.board_type,
            "boards": boards,
            "devices": self.devices,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BoardSettings":
        board_type = data.get("board_type", "black")
        if board_type not in ["black", "white", None]:
            board_type = "black"

        boards = data.get("boards", [])

        # Migrate from legacy devices-only format
        if not boards and "devices" in data:
            from src.devices import BoardInstance

            devices = data["devices"]
            if isinstance(devices, list):
                for i, dt in enumerate(devices):
                    name = "My Board" if i == 0 else f"My Board {i + 1}"
                    boards.append(
                        BoardInstance(
                            name=name,
                            device_type=dt,
                            board_color=board_type or "black",
                        ).to_dict()
                    )

        return cls(board_type=board_type, boards=boards)


VALID_REVERT_MODES = ["schedule", "blank", "page"]
TEMPORARY_OVERRIDE_DURATION_MIN = 1
TEMPORARY_OVERRIDE_DURATION_MAX = 480


@dataclass
class TemporaryOverride:
    """A user-initiated page override.

    An override carries **exactly one** kind of content:

    - ``page_id``: a saved Page (or Collection) reference, or
    - ``template``: inline, never-persisted board content — the "one-off
      message" of issue #1787, optionally with ``line_metadata`` and the
      geometry it was composed for.

    ``expires_at`` is optional. When it is ``None`` the override is
    **indefinite**: it stays on the board until the user cancels it. A
    one-off message that silently vanishes after N minutes is not what a
    manual-mode user asks for, so the duration is opt-in.

    When a *time-limited* override expires the revert_mode determines what
    happens next:
      - "schedule": clear override, schedule resumes naturally
      - "blank": clear override, board is blanked
      - "page": clear override, active page is set to revert_page_id
    """

    page_id: str | None = None
    expires_at: str | None = None  # ISO 8601 UTC timestamp, or None for indefinite
    revert_mode: str = "schedule"  # "schedule" | "blank" | "page"
    revert_page_id: str | None = None

    # Inline (one-off) content — mutually exclusive with page_id
    template: list[str] | None = None
    line_metadata: list[dict] | None = None
    device_type: str | None = None
    notes_wide: int | None = None
    notes_tall: int | None = None
    grid_rows: int | None = None
    grid_cols: int | None = None

    def __post_init__(self) -> None:
        has_page = bool(self.page_id)
        has_template = bool(self.template)
        if has_page == has_template:
            raise ValueError("TemporaryOverride requires exactly one of page_id or template")

    @property
    def is_inline(self) -> bool:
        """True when this override carries inline content instead of a page reference."""
        return bool(self.template)

    def is_expired(self) -> bool:
        """Return True when the override's expiry timestamp has passed.

        An indefinite override (``expires_at is None``) is never expired.
        """
        if self.expires_at is None:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return datetime.now(UTC) >= expiry
        except (ValueError, TypeError):
            return True

    def remaining_seconds(self) -> float | None:
        """Seconds remaining before expiry (0 if expired, None if indefinite)."""
        if self.expires_at is None:
            return None
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            delta = (expiry - datetime.now(UTC)).total_seconds()
            return max(0.0, delta)
        except (ValueError, TypeError):
            return 0.0

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "expires_at": self.expires_at,
            "revert_mode": self.revert_mode,
            "revert_page_id": self.revert_page_id,
            "template": self.template,
            "line_metadata": self.line_metadata,
            "device_type": self.device_type,
            "notes_wide": self.notes_wide,
            "notes_tall": self.notes_tall,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemporaryOverride":
        return cls(
            page_id=data.get("page_id"),
            expires_at=data.get("expires_at"),
            revert_mode=data.get("revert_mode", "schedule"),
            revert_page_id=data.get("revert_page_id"),
            template=data.get("template"),
            line_metadata=data.get("line_metadata"),
            device_type=data.get("device_type"),
            notes_wide=data.get("notes_wide"),
            notes_tall=data.get("notes_tall"),
            grid_rows=data.get("grid_rows"),
            grid_cols=data.get("grid_cols"),
        )


class TemporaryOverrideStatus(BaseModel):
    """The wire shape of a :class:`TemporaryOverride`, or of "there isn't one".

    One shape is shared by ``GET``/``POST /settings/temporary-override`` and by
    the inline block on ``GET /schedules/active/page``, so the three can never
    drift. Declared as a model (rather than assembled ad hoc) so routers can
    name it in ``response_model=`` — see
    ``docs/internal/reference/API_CONVENTIONS.md``.

    ``remaining_seconds`` is None both when there is no override and when the
    override is indefinite (issue #1787).
    """

    active: bool
    page_id: str | None = None
    expires_at: str | None = None
    remaining_seconds: float | None = None
    revert_mode: str | None = None
    revert_page_id: str | None = None
    template: list[str] | None = None
    line_metadata: list[dict] | None = None
    device_type: str | None = None
    notes_wide: int | None = None
    notes_tall: int | None = None
    grid_rows: int | None = None
    grid_cols: int | None = None


def temporary_override_payload(override: "TemporaryOverride | None") -> dict:
    """Serialize a TemporaryOverride (or None) for the API.

    Lived in ``src/api_server.py`` until Phase 2 §2.3. It reads nothing but the
    override, so it belongs next to the model it serializes — and the schedules
    router can now import it instead of reaching into the app module at call
    time.
    """
    if override is None:
        return {
            "active": False,
            "page_id": None,
            "expires_at": None,
            "remaining_seconds": None,
            "revert_mode": None,
            "revert_page_id": None,
            "template": None,
            "line_metadata": None,
            "device_type": None,
            "notes_wide": None,
            "notes_tall": None,
            "grid_rows": None,
            "grid_cols": None,
        }
    remaining = override.remaining_seconds()
    return {
        "active": True,
        "page_id": override.page_id,
        "expires_at": override.expires_at,
        "remaining_seconds": round(remaining, 1) if remaining is not None else None,
        "revert_mode": override.revert_mode,
        "revert_page_id": override.revert_page_id,
        "template": override.template,
        "line_metadata": override.line_metadata,
        "device_type": override.device_type,
        "notes_wide": override.notes_wide,
        "notes_tall": override.notes_tall,
        "grid_rows": override.grid_rows,
        "grid_cols": override.grid_cols,
    }


@dataclass
class ScheduleSettings:
    """Schedule system settings.

    ``enabled`` is **deprecated** as the source of truth: schedule mode is now
    authoritative per-board via ``boards[i].schedule_enabled``. This flag is
    retained for one release only as a back-compat mirror of the *primary*
    board's value. Use ``SettingsService.is_schedule_enabled(board_id)``.
    """

    enabled: bool = False  # Deprecated mirror of the primary board's schedule_enabled

    # When True, turning schedule mode back on does not repaint the board:
    # it keeps showing the manually selected page until the schedule reaches
    # its next window. Off by default — see SettingsService.set_schedule_defer_on_reenable.
    defer_on_reenable: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleSettings":
        return cls(
            enabled=data.get("enabled", False),
            defer_on_reenable=bool(data.get("defer_on_reenable", False)),
        )


@dataclass
class LocationSettings:
    """Location settings for sun-based schedule features (sunrise/sunset)."""

    latitude: float | None = None
    longitude: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationSettings":
        lat = data.get("latitude")
        lon = data.get("longitude")
        return cls(
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
        )


BOARD_ANIMATIONS_VALUES = ("on", "desktop", "off")
SITE_ANIMATIONS_VALUES = ("on", "off")


def _coerce_board_animations(value: object) -> str:
    s = str(value).lower() if value is not None else "on"
    return s if s in BOARD_ANIMATIONS_VALUES else "on"


def _coerce_site_animations(value: object) -> str:
    s = str(value).lower() if value is not None else "on"
    return s if s in SITE_ANIMATIONS_VALUES else "on"


# Named split-flap cadences for the ON-SCREEN board preview, in milliseconds
# per character step. Mirrors FLAP_SPEED_PRESETS in @fiestaboard/ui — the web
# UI imports the numbers from the package, so this list only has to agree on
# the *names*. Unrelated to TransitionSettings.step_interval_ms, which paces
# the physical Vestaboard over the Local API.
BOARD_FLAP_SPEED_VALUES = ("hardware", "quick", "standard", "relaxed")

# Below ~8ms nothing survives a frame boundary; above 2s a board would take
# minutes to settle. Matches the clamp in @fiestaboard/ui's resolveFlapSpeed.
BOARD_FLAP_SPEED_MIN_MS = 8
BOARD_FLAP_SPEED_MAX_MS = 2000


def _coerce_board_flap_speed(value: object) -> str | int:
    """Accept a preset name, or a raw millisecond count as an escape hatch.

    The settings UI only writes preset names. A number lets an advanced user
    (or the AI settings tool) pick a cadence the UI does not offer; it is
    clamped rather than rejected so a bad value degrades instead of raising.
    Anything unrecognised falls back to the default.
    """
    if isinstance(value, bool):
        return "standard"
    if isinstance(value, (int, float)):
        return max(BOARD_FLAP_SPEED_MIN_MS, min(BOARD_FLAP_SPEED_MAX_MS, round(value)))
    if isinstance(value, str):
        s = value.strip().lower()
        if s in BOARD_FLAP_SPEED_VALUES:
            return s
        try:
            return max(BOARD_FLAP_SPEED_MIN_MS, min(BOARD_FLAP_SPEED_MAX_MS, round(float(s))))
        except (TypeError, ValueError):
            return "standard"
    return "standard"


@dataclass
class DisplaySettings:
    """Web UI display preferences."""

    reduce_motion: bool = False
    # Split-flap board animation. "on" = animate everywhere, "desktop" =
    # animate on desktop but skip on mobile (saves battery / avoids motion
    # sickness on small screens), "off" = never animate the board.
    board_animations: str = "on"
    # General UI motion (transitions, hovers, page enter/leave).
    # "on" = animate, "off" = disable. `reduce_motion` overrides to off.
    site_animations: str = "on"
    # How fast a tile flips one character in the on-screen board preview:
    # a preset name from BOARD_FLAP_SPEED_VALUES, or a raw ms count.
    # "standard" is 80ms — what the app has always shipped.
    board_flap_speed: str | int = "standard"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DisplaySettings":
        return cls(
            reduce_motion=bool(data.get("reduce_motion", False)),
            board_animations=_coerce_board_animations(data.get("board_animations", "on")),
            site_animations=_coerce_site_animations(data.get("site_animations", "on")),
            board_flap_speed=_coerce_board_flap_speed(data.get("board_flap_speed", "standard")),
        )


@dataclass
class PluginSettings:
    """Plugin system settings.

    - auto_update: update installed plugins in the background.
    - transition_plugins_enabled: transition plugins (frame-by-frame board
      animations driven by the TransitionPluginBase SDK) become selectable as
      a display's or a page's transition. Off by default. Deprecated
      (removal considered for v11). ``beta.transition_plugins_enabled``
      until settings v6.
    - output_plugins_enabled: output plugins installed from the registry or
      a git URL can drive boards (a board whose ``output`` names one). Off by
      default; first-party outputs (bundled in ``plugins/`` or carried by the
      image's output seed) are always on. ``beta.output_plugins_enabled``
      until settings v6.
    """

    auto_update: bool = True
    transition_plugins_enabled: bool = False
    output_plugins_enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PluginSettings":
        return cls(
            auto_update=bool(data.get("auto_update", True)),
            transition_plugins_enabled=bool(data.get("transition_plugins_enabled", False)),
            output_plugins_enabled=bool(data.get("output_plugins_enabled", False)),
        )


#: How the setup wizard ended: finished, or skipped ("I'll add a display
#: later"). ``None``: it never ran to an end on this install.
WizardState = Literal["completed", "skipped"]
VALID_WIZARD_STATES: tuple[str, ...] = ("completed", "skipped")


@dataclass
class WizardSettings:
    """The setup wizard's outcome, kept server-side (plan D18).

    First run is "no board has a usable output AND the wizard was neither
    completed nor skipped" (``src/config_api/service.py``), so a user who
    skips setup is not sent back to it by the next browser they open.
    Additive, no schema bump: the section is written only once set, so a file
    saved by a build that predates it round-trips unchanged.
    """

    state: WizardState | None = None

    def to_dict(self) -> dict:
        return {"state": self.state}

    @classmethod
    def from_dict(cls, data: dict) -> "WizardSettings":
        state = data.get("state") if isinstance(data, dict) else None
        return cls(state=state if state in VALID_WIZARD_STATES else None)


@dataclass
class MQTTSettings:
    """MQTT integration settings for Home Assistant auto-discovery.

    When enabled, FiestaBoard publishes itself as a device to an MQTT broker
    and Home Assistant picks it up automatically via MQTT Discovery.

    Attributes:
        enabled: Whether the MQTT client should run.
        broker_host: Hostname or IP of the MQTT broker.
        broker_port: Port of the MQTT broker (default 1883).
        username: Optional broker username.
        password: Optional broker password (stored, masked in API responses).
        external_url: Public URL of this FiestaBoard instance shown as the
            "Visit" link on the HA device page.  None omits the link.
    """

    enabled: bool = False
    broker_host: str = "localhost"
    broker_port: int = 1883
    username: str = ""
    password: str = ""
    external_url: str = ""

    def to_dict(self, mask_secrets: bool = True) -> dict:
        return {
            "enabled": self.enabled,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "username": self.username,
            "password": "***" if mask_secrets and self.password else self.password,
            "external_url": self.external_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MQTTSettings":
        return cls(
            enabled=bool(data.get("enabled", False)),
            broker_host=data.get("broker_host", "localhost") or "localhost",
            broker_port=int(data.get("broker_port", 1883) or 1883),
            username=data.get("username", "") or "",
            password=data.get("password", "") or "",
            external_url=data.get("external_url", "") or "",
        )


# ==================== Settings schema versioning ====================
#
# settings.json carries an integer ``schema_version`` and is migrated through
# an ordered ``MIGRATIONS`` list on startup (mirrors src/schedules/storage.py).
# Migrations operate on the **raw dict** before any Pydantic/dataclass parsing,
# are idempotent, log how many records changed, and a one-time backup of the
# pre-migration file is written to ``settings.json.v{N}_backup`` before the
# first migration runs.

CURRENT_SETTINGS_SCHEMA_VERSION = 6

_LEGACY_CAROUSEL_PREFIX = "carousel:"
_COLLECTION_PREFIX = "collection:"


def primary_board_id_from_raw(data: dict) -> str | None:
    """Return the primary (first) board's id from a raw settings dict.

    The primary board is the first entry in ``board.boards``. Returns None when
    there are no boards or the first board has no id. This is the migration-safe
    counterpart to ``SettingsService.get_primary_board_id`` and operates purely
    on raw JSON so it can be used inside migrations (before parsing).
    """
    board = data.get("board")
    if not isinstance(board, dict):
        return None
    boards = board.get("boards")
    if isinstance(boards, list) and boards and isinstance(boards[0], dict):
        bid = boards[0].get("id")
        return bid if isinstance(bid, str) and bid else None
    return None


def _rewrite_carousel_ref(ref: object) -> tuple[object, bool]:
    """Rewrite a single ``carousel:<uuid>`` reference to ``collection:<uuid>``.

    Returns ``(new_ref, changed)``. Non-carousel and non-str refs pass through.
    """
    if isinstance(ref, str) and ref.startswith(_LEGACY_CAROUSEL_PREFIX):
        return _COLLECTION_PREFIX + ref[len(_LEGACY_CAROUSEL_PREFIX) :], True
    return ref, False


def _migrate_v0_to_v1(data: dict) -> int:
    """Migration 0 -> 1 (idempotent; operates on the raw settings dict).

    Three independent fix-ups, each counted toward the returned change total:

    1. Rewrite legacy ``carousel:<uuid>`` page references to
       ``collection:<uuid>`` in ``active_page.page_id`` and
       ``temporary_override.page_id`` / ``revert_page_id`` (prior behavior of
       ``_migrate_legacy_carousel_refs``).
    2. Move the global ``active_page.page_id`` into
       ``active_page.by_board[primary_id]`` so the manual active page becomes
       per-board. The ``page_id`` mirror is left in place as a back-compat
       value for the primary board. Skipped when ``by_board[primary_id]`` is
       already set. Deferred (mirror left untouched, read-path fallback covers
       it) when there are no boards yet.
    3. Reconcile per-board ``schedule_enabled``: when the primary board lacks a
       ``schedule_enabled`` key and the legacy global ``schedule.enabled`` is
       True, stamp ``schedule_enabled = True`` on the primary board.
    """
    changes = 0

    active = data.get("active_page")
    if not isinstance(active, dict):
        active = {}

    # (1) carousel -> collection rewrites
    new_ref, did = _rewrite_carousel_ref(active.get("page_id"))
    if did:
        active["page_id"] = new_ref
        data["active_page"] = active
        changes += 1

    override = data.get("temporary_override")
    if isinstance(override, dict):
        for key in ("page_id", "revert_page_id"):
            new_ref, did = _rewrite_carousel_ref(override.get(key))
            if did:
                override[key] = new_ref
                changes += 1

    primary_id = primary_board_id_from_raw(data)

    # (2) global active page -> primary board's by_board slot
    if primary_id is not None:
        by_board = active.get("by_board")
        if not isinstance(by_board, dict):
            by_board = {}
        legacy_page_id = active.get("page_id")
        if legacy_page_id and primary_id not in by_board:
            by_board[primary_id] = legacy_page_id
            active["by_board"] = by_board
            data["active_page"] = active
            changes += 1

    # (3) reconcile schedule_enabled onto the primary board
    schedule = data.get("schedule")
    global_enabled = bool(schedule.get("enabled")) if isinstance(schedule, dict) else False
    if primary_id is not None and global_enabled:
        board = data.get("board")
        boards = board.get("boards") if isinstance(board, dict) else None
        if isinstance(boards, list) and boards and isinstance(boards[0], dict):
            primary = boards[0]
            if "schedule_enabled" not in primary:
                primary["schedule_enabled"] = True
                changes += 1

    return changes


_INLINE_OVERRIDE_KEYS = (
    "template",
    "line_metadata",
    "device_type",
    "notes_wide",
    "notes_tall",
    "grid_rows",
    "grid_cols",
)


def _migrate_v1_to_v2(data: dict) -> int:
    """Migration 1 -> 2 (idempotent; operates on the raw settings dict).

    ``temporary_override`` gained the inline one-off fields of issue #1787
    (``template`` / ``line_metadata`` / ``device_type`` / note-array geometry).
    A stored v1 override predates them, so stamp them as explicit nulls: the
    persisted shape then matches what ``TemporaryOverride.to_dict`` writes and
    a v1 file no longer round-trips into a different shape on first save.

    Returns 1 when an override was backfilled, 0 otherwise (so re-running is a
    no-op).
    """
    override = data.get("temporary_override")
    if not isinstance(override, dict):
        return 0
    if all(key in override for key in _INLINE_OVERRIDE_KEYS):
        return 0
    for key in _INLINE_OVERRIDE_KEYS:
        override.setdefault(key, None)
    return 1


# Board-connection fields copied from the legacy config.json board block into
# a credential-less settings board (v2 -> v3 migration and first-boot seed).
_LEGACY_CONNECTION_FIELDS = ("api_mode", "host", "local_api_key", "cloud_key", "note_array_token")


def _board_dict_has_credentials(board: dict) -> bool:
    """True when a raw board dict already carries any connection credential.

    Credentials are the local API key, the cloud read/write key, the
    note-array token, or configured local-array tiles. A virtual board
    (FiestaPanel) counts too: carrying no credential fields is its nature,
    not an unconfigured state — mirroring
    ``BoardInstance.has_connection_attempt`` — so stale physical credentials
    never flip its ``api_mode`` (#1866 review). A board matching any of
    these is a *maintained* copy and must never be overwritten by the legacy
    config.json block (issue #1760 precedence rule).
    """
    from src.settings.board_shape import flat_connection

    # Either shape: a v2/v3 raw board (migrations) or a v4 one (first-boot seed).
    connection = flat_connection(board)
    if connection["api_mode"] == "virtual":
        return True
    if connection["local_api_key"] or connection["cloud_key"] or connection["note_array_token"]:
        return True
    tiles = connection["tiles"]
    return isinstance(tiles, list) and len(tiles) > 0


def _read_legacy_board_connection() -> dict | None:
    """Read the legacy ``config.json -> board.*`` connection block.

    Returns a dict of :data:`_LEGACY_CONNECTION_FIELDS`, or None when the
    legacy block carries no credential worth importing. A *failure* to read
    it propagates instead of masquerading as "no credentials": swallowing it
    let a transient config read failure stamp the new schema version with
    nothing imported (#1866 review). The migration runner aborts the run so
    schema_version stays pre-migration and the import retries next boot.
    This is the ONLY remaining read of board credentials from config.json;
    everything at runtime goes through the settings store (issue #1760).
    """
    from src.config_manager import get_config_manager

    legacy = get_config_manager().get_board()
    if not (legacy.get("local_api_key") or legacy.get("cloud_key") or legacy.get("note_array_token")):
        return None
    return {
        "api_mode": legacy.get("api_mode", "local") or "local",
        "host": legacy.get("host", "") or "",
        "local_api_key": legacy.get("local_api_key", "") or "",
        "cloud_key": legacy.get("cloud_key", "") or "",
        "note_array_token": legacy.get("note_array_token", "") or "",
    }


def _connection_fields_for_board(legacy: dict, board: dict) -> dict | None:
    """Restrict an imported legacy connection to fields the target board can use.

    A note-array token only ever drives a note-array board. Importing it onto
    a flagship/note primary satisfied ``has_connection_attempt`` — the setup
    wizard never appeared — while no client could ever be built from it
    (#1866 review). For non-array targets the token is dropped; if no real
    credential remains, nothing imports and the wizard shows as it did
    pre-#1760.
    """
    from src.devices import is_note_array

    if is_note_array(board.get("device_type", "flagship")):
        return legacy
    fields = dict(legacy)
    fields["note_array_token"] = ""
    if not (fields.get("local_api_key") or fields.get("cloud_key")):
        return None
    return fields


def _migrate_v2_to_v3(data: dict) -> int:
    """Migration 2 -> 3 (idempotent; operates on the raw settings dict).

    Unify board credentials on settings.json (issue #1760): import the legacy
    ``config.json -> board.*`` connection block into the primary settings
    board — once, gated on schema_version, replacing the old copy-on-every-boot
    seam that kept resurrecting stale config.json keys (#948/#1102).

    Precedence: settings is the maintained copy. Only a credential-less
    primary board inherits from config.json; a board that already carries any
    credential (local key, cloud key, note-array token, or local-array tiles)
    is left untouched. config.json itself is not modified — its board block
    stays on disk as a rollback copy for older versions but is no longer read
    at runtime.

    Returns 1 when the primary board inherited the legacy connection,
    0 otherwise.
    """
    board = data.get("board")
    if not isinstance(board, dict):
        return 0
    boards = board.get("boards")
    materialize = False
    if not isinstance(boards, list) or not boards or not isinstance(boards[0], dict):
        # Devices-era file: a raw ``board`` dict without a ``boards`` list
        # (e.g. {"board_type": "black", "devices": ["flagship"]}) — a shape
        # BoardSettings.from_dict still parses. Gating only on a raw
        # boards[0] let these installs slip between the migration and the
        # first-boot seed: schema stamped v3 with the credentials stranded
        # in config.json (#1866 review). Run the import against the
        # POST-PARSE board list instead, and materialize it on import.
        parsed = BoardSettings.from_dict(board)
        boards = [b for b in parsed.boards if isinstance(b, dict)]
        if not boards:
            return 0
        materialize = True
    first = boards[0]
    if _board_dict_has_credentials(first):
        return 0
    legacy = _read_legacy_board_connection()
    if legacy is None:
        return 0
    importable = _connection_fields_for_board(legacy, first)
    if importable is None:
        return 0
    first.update(importable)
    if materialize:
        board["boards"] = boards
    logger.info("Imported legacy config.json board connection into the primary settings board")
    return 1


def _migrate_v3_to_v4(data: dict) -> int:
    """Migration 3 -> 4 (idempotent; operates on the raw settings dict).

    Every board becomes an output's board (output-plugins plan D8): each
    ``board.boards[]`` entry gains ``output`` and ``output_config``, and a
    Vestaboard's connection fields (``api_mode``, ``host``, ``port``,
    ``local_api_key``, ``cloud_key``, ``note_array_token``, ``tiles``) move
    into its ``output_config``. ``output`` precedence: an explicit ``output``
    wins -> ``api_mode == "virtual"`` is ``fiestapanel`` -> else
    ``vestaboard``. ``device_type``, geometry, name and display fields stay
    top-level: they describe the content's shape, which pages and previews
    key on. See :func:`src.settings.board_shape.migrate_board_to_v4`.

    A devices-era section (no ``boards`` list) needs nothing: its boards are
    built at load in the v4 shape. Returns the number of boards changed.
    """
    from src.settings.board_shape import migrate_board_to_v4

    board = data.get("board")
    boards = board.get("boards") if isinstance(board, dict) else None
    if not isinstance(boards, list):
        return 0
    return sum(1 for b in boards if isinstance(b, dict) and migrate_board_to_v4(b))


def _migrate_v4_to_v5(data: dict) -> int:
    """Migration 4 -> 5 (idempotent; operates on the raw settings dict).

    The HTTPS (Beta) feature is removed (settings reorg, PR B): drop
    ``beta.https_enabled`` whatever its value. An install that had it on now
    serves plain HTTP on its usual port; the self-signed cert files the old
    entrypoint generated are deleted at startup by
    :func:`src.system.legacy_https.remove_legacy_https_certs`. Every other beta
    flag is kept. Returns 1 when the flag was dropped, 0 otherwise.
    """
    beta = data.get("beta")
    if not isinstance(beta, dict) or "https_enabled" not in beta:
        return 0
    was_on = bool(beta.pop("https_enabled"))
    if was_on:
        logger.warning(
            "HTTPS (Beta) has been removed; FiestaBoard now serves plain HTTP. Browse to http://<host>:4420 instead."
        )
    return 1


def _legacy_env_transition() -> tuple[str | None, int | None, int | None]:
    """The transition the legacy env / config.json board block sets
    (``BOARD_TRANSITION_STRATEGY``, ``BOARD_TRANSITION_INTERVAL_MS``,
    ``BOARD_TRANSITION_STEP_SIZE``): what a new split-flap display starts
    with. A read failure is "unset": these only seed a default.
    """
    try:
        from src.config import Config

        return (
            Config.FB_TRANSITION_STRATEGY or None,
            Config.FB_TRANSITION_INTERVAL_MS,
            Config.FB_TRANSITION_STEP_SIZE,
        )
    except Exception:
        logger.warning("Could not read the legacy transition settings; using none", exc_info=True)
        return None, None, None


def default_board_transition(board: dict, *, plugins_enabled: bool = False) -> dict:
    """The transition keys a new display starts with (settings v6).

    A split-flap display (a Vestaboard or a FiestaPanel) starts with what
    the legacy env / config.json sets, else ``"none"``: a plain write, the
    board's own flip, which is what an install with no transition did. An
    output plugin's display (an LED matrix) starts with ``"none"``: it snaps.

    The legacy values are validated, because adding a display must never
    fail over its default: a strategy no menu offers, or a ``plugin:`` one
    while transition plugins are off (*plugins_enabled*), falls back to
    ``"none"``, and an out-of-range speed to the device's default, each with
    a warning.
    """
    from src.devices import is_split_flap, transition_speed

    if not is_split_flap(board):
        return {"transition": BOARD_TRANSITION_NONE}
    strategy, interval, step_size = _legacy_env_transition()
    if strategy is not None and (
        not is_valid_strategy(strategy) or (strategy.startswith(TRANSITION_PLUGIN_PREFIX) and not plugins_enabled)
    ):
        logger.warning(
            "BOARD_TRANSITION_STRATEGY %r is not a transition a new display can use%s; it starts with none",
            strategy,
            " while transition plugins are off" if is_valid_strategy(strategy) else "",
        )
        strategy = None
    defaults: dict = {"transition": strategy or BOARD_TRANSITION_NONE}
    for key, value in (("transition_step_interval_ms", interval), ("transition_step_size", step_size)):
        if value is None:
            continue
        if transition_speed(key, value) is None:
            logger.warning("Legacy %s %r is out of range; a new display uses the device default", key, value)
            continue
        defaults[key] = value
    return defaults


def _check_strategy_for_board(strategy: str, board: dict) -> None:
    """Refuse a strategy *board*'s own menu does not offer, naming what it
    does. The menu follows the board's device model, as the display page's
    does (:func:`src.outputs.board_profile.board_is_led`): an LED matrix
    takes LED menu ids; any other board (a Vestaboard, a split-flap
    FiestaPanel, a non-LED output plugin's) takes ``"none"``, the split-flap
    strategies and ``plugin:<id>``."""
    from src.led.transition_registry import LED_TRANSITIONS, is_led_transition_id
    from src.outputs.board_profile import board_is_led

    if board_is_led(board):
        if is_led_transition_id(strategy):
            return
        raise ValueError(f"Invalid strategy: {strategy}. This LED display takes one of {list(LED_TRANSITIONS)}")
    if strategy == BOARD_TRANSITION_NONE or is_valid_strategy(strategy):
        return
    raise ValueError(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES} or 'plugin:<id>'")


def _with_default_transition(board: dict, *, plugins_enabled: bool) -> dict:
    """*board* with :func:`default_board_transition` applied, unless it
    already names a transition. A speed the board carries is kept."""
    if isinstance(board.get("transition"), str) and board["transition"].strip():
        return board
    defaults = default_board_transition(board, plugins_enabled=plugins_enabled)
    return {**defaults, **{k: v for k, v in board.items() if v is not None}, "transition": defaults["transition"]}


#: The flags settings v5 still kept under ``beta``; v6 moves them to ``plugins``.
_BETA_FLAGS = ("transition_plugins_enabled", "output_plugins_enabled")


#: Where the v5 -> v6 migration parks the install's transition when the file
#: has no boards to copy it onto (no ``board`` section, ``boards: []``, a
#: devices-era section). The board loader applies it to the boards it builds
#: (after the first-boot seed, which fills a fresh board's connection) and
#: saves; the save never writes this key, so it is consumed.
PENDING_TRANSITION_KEY = "pending_board_transition"


def _apply_install_transition(entry: dict, strategy, interval, step_size) -> bool:
    """Copy a v5 install-wide transition onto one board dict (v5 -> v6).

    No ``transition`` of its own: the install's strategy; with none, ``"none"``
    on a split-flap board and unset on an output plugin's (its model's
    default, what it ran). No speed of its own: the install's. Returns
    whether the board changed.
    """
    from src.devices import is_split_flap

    changed = False
    own = entry.get("transition")
    if not (isinstance(own, str) and own.strip()):
        if strategy is not None:
            entry["transition"] = strategy
            changed = True
        elif is_split_flap(entry):
            entry["transition"] = BOARD_TRANSITION_NONE
            changed = True
    if interval is not None and entry.get("transition_step_interval_ms") is None:
        entry["transition_step_interval_ms"] = interval
        changed = True
    if step_size is not None and entry.get("transition_step_size") is None:
        entry["transition_step_size"] = step_size
        changed = True
    return changed


def _clamp_stored_speeds(entry: dict) -> bool:
    """Clamp a stored board's speeds into range (logged); whether it changed.

    Data written before the cap must load, and never block a later write."""
    from src.devices import TRANSITION_SPEED_BOUNDS, clamp_transition_speed

    changed = False
    for key in TRANSITION_SPEED_BOUNDS:
        if key not in entry or entry[key] is None:
            continue
        value = clamp_transition_speed(key, entry[key])
        if value != entry[key]:
            if value is None:
                del entry[key]
            else:
                entry[key] = value
            changed = True
    return changed


def _migrate_v5_to_v6(data: dict) -> int:
    """Migration 5 -> 6 (idempotent; operates on the raw settings dict).

    Each display owns its transition (settings reorg, PR C):

    1. The install-wide ``transitions`` block (``strategy``,
       ``step_interval_ms``, ``step_size``) is copied onto the boards, then
       deleted. A board without a ``transition`` of its own gets the
       install's strategy; when that was null, a split-flap board (a
       Vestaboard or a FiestaPanel) gets ``"none"`` (null was no
       transition), while an output plugin's board stays unset: unset there
       is its device model's default, which is what it ran. Every board with
       no speed of its own gets the install's step interval and step size
       (they were always the install's, even for a board with its own
       style). An interval above the cap is clamped. When there is no board
       to copy onto (no ``board`` section, ``boards: []``, a devices-era
       section built at load), the transition is parked under
       :data:`PENDING_TRANSITION_KEY` for the board loader, so it is never
       dropped. The migration never reads config.json and cannot abort.
    2. The ``beta`` flags (``transition_plugins_enabled``,
       ``output_plugins_enabled``) move into the ``plugins`` section, and
       ``beta`` is deleted: nothing else was left in it after v5.

    Returns the number of boards changed plus one per block removed. A
    re-run finds no block, and every split-flap board already has a
    transition, so it changes nothing.
    """
    from src.devices import clamp_transition_speed

    changes = 0
    strategy = interval = step_size = None
    if "transitions" in data:
        raw = data.pop("transitions")
        if isinstance(raw, dict):
            strategy, interval, step_size = raw.get("strategy"), raw.get("step_interval_ms"), raw.get("step_size")
        changes += 1
    strategy = strategy.strip() if isinstance(strategy, str) and strategy.strip() else None
    interval = clamp_transition_speed("transition_step_interval_ms", interval)
    step_size = clamp_transition_speed("transition_step_size", step_size)

    board = data.get("board")
    boards = board.get("boards") if isinstance(board, dict) else None
    if isinstance(boards, list) and boards:
        for entry in boards:
            if isinstance(entry, dict):
                changed = _apply_install_transition(entry, strategy, interval, step_size)
                changes += _clamp_stored_speeds(entry) or changed
    elif any(value is not None for value in (strategy, interval, step_size)):
        # No boards yet: they are built at load (the first-boot seed fills a
        # fresh board's connection). Never read config.json here.
        data[PENDING_TRANSITION_KEY] = {"strategy": strategy, "step_interval_ms": interval, "step_size": step_size}

    if "beta" in data:
        beta = data.pop("beta")
        plugins = data.get("plugins")
        if not isinstance(plugins, dict):
            plugins = data["plugins"] = {}
        for key in _BETA_FLAGS:
            if isinstance(beta, dict) and key in beta:
                plugins.setdefault(key, bool(beta[key]))
        changes += 1
    return changes


MIGRATIONS: list[tuple[int, Callable[[dict], int]]] = [
    (1, _migrate_v0_to_v1),
    (2, _migrate_v1_to_v2),
    (3, _migrate_v2_to_v3),
    (4, _migrate_v3_to_v4),
    (5, _migrate_v4_to_v5),
    (6, _migrate_v5_to_v6),
]


# ---------------------------------------------------------------------------
# Downgrade bridge (output-plugins plan D8, "Rollback")
#
# A newer build migrates settings.json past CURRENT_SETTINGS_SCHEMA_VERSION
# and, before it does, snapshots this build's file as
# ``settings.json.v{CURRENT}_backup`` — written only when no such backup
# exists. When the user rolls back to this build, that snapshot is exactly
# what this build last wrote, so instead of refusing to boot we step back onto
# it. Everything changed since the upgrade is in the set-aside file, which the
# web UI names so hand-edits can be recovered.
# ---------------------------------------------------------------------------

#: Written next to settings.json when the bridge fires; served by
#: ``GET /settings/restore-notice`` until the user dismisses it.
RESTORE_NOTICE_FILENAME = "settings_restore_notice.json"


class SettingsRestoreNotice(BaseModel):
    """What the downgrade bridge did, for the web UI's banner."""

    #: Where the newer build's settings were kept, as this process sees it.
    aside_path: str
    aside_file: str
    #: schema_version of the set-aside file / of the restored backup.
    found_version: int
    restored_version: int
    #: When the swap happened, ISO 8601 UTC with a trailing ``Z``.
    restored_at: str


def _downgrade_backup_path(settings_file: Path) -> Path:
    """The pre-migration snapshot a newer build left of this build's file."""
    return settings_file.with_suffix(f".json.v{CURRENT_SETTINGS_SCHEMA_VERSION}_backup")


def _schema_version_of(path: Path) -> int | None:
    """The file's schema_version (0 when unstamped), or None if unreadable."""
    try:
        with open(path) as f:  # noqa: PTH123
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("schema_version", 0)
    return version if isinstance(version, int) else 0


def _bridge_from_downgrade_backup(settings_file: Path, found_version: int) -> SettingsRestoreNotice | None:
    """Swap a too-new settings.json for this build's pre-upgrade snapshot.

    Returns the notice when the swap happened, None when there is nothing
    safe to swap in (no backup, or one this build cannot read either) — the
    caller then refuses to boot exactly as before.

    Order matters for crash safety. The too-new file is *copied* aside first
    (so settings.json is never missing — a missing file would boot as a fresh
    install), the backup is staged and atomically replaced over settings.json,
    and only then is the backup deleted. A crash before the replace leaves the
    too-new file in place and the bridge simply runs again next boot.

    The backup is deleted, not kept: the newer build only snapshots when no
    backup exists, so a leftover would make the *next* upgrade-then-rollback
    restore this upgrade's stale snapshot and lose everything in between.
    """
    backup = _downgrade_backup_path(settings_file)
    if not backup.exists():
        return None
    restored_version = _schema_version_of(backup)
    if restored_version is None or restored_version > CURRENT_SETTINGS_SCHEMA_VERSION:
        logger.error(
            f"Settings downgrade: {backup} exists but this build cannot read it "
            f"(schema_version {restored_version}); not restoring it"
        )
        return None

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    aside = settings_file.with_name(f"{settings_file.name}.v{found_version}_aside-{stamp}")
    n = 1
    while aside.exists():  # two rollbacks inside one second must not clobber the first aside
        n += 1
        aside = settings_file.with_name(f"{settings_file.name}.v{found_version}_aside-{stamp}-{n}")

    shutil.copy2(settings_file, aside)
    staged = staging_path(settings_file)
    shutil.copy2(backup, staged)
    staged.replace(settings_file)
    backup.unlink()

    notice = SettingsRestoreNotice(
        aside_path=str(aside),
        aside_file=aside.name,
        found_version=found_version,
        restored_version=restored_version,
        restored_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    logger.warning(
        "SETTINGS ROLLED BACK: %s was written by a newer FiestaBoard (settings schema v%d; this build reads v%d). "
        "Restored the pre-upgrade snapshot %s and set the newer file aside as %s. Changes made since the "
        "upgrade are NOT in the restored settings; they are in the set-aside file.",
        settings_file,
        found_version,
        CURRENT_SETTINGS_SCHEMA_VERSION,
        backup.name,
        aside,
    )
    try:
        write_json_atomic(settings_file.with_name(RESTORE_NOTICE_FILENAME), notice.model_dump())
    except OSError as e:
        # The swap already happened and is what matters; the banner is a
        # courtesy. The log line above still names the aside file.
        logger.error(f"Could not record the settings restore notice: {e}")
    return notice


def _locked(method):
    """Run *method* under the settings store lock.

    Every mutating method is a read-modify-write over the shared in-memory
    sections followed by a full-file save; without one lock around the whole
    thing, two concurrent PUTs race the save and one silently overwrites the
    other's section with a stale snapshot (#1848). The lock is the JsonStore's
    RLock, so nested ``_save_to_file`` calls re-enter cleanly.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._store.lock:
            return method(self, *args, **kwargs)

    return wrapper


class SettingsService:
    """Service for managing runtime settings.

    Settings can be modified at runtime via the API and are persisted
    to a JSON file so they survive restarts.
    """

    def __init__(self, settings_file: str | None = None):
        """Initialize settings service.

        Args:
            settings_file: Path to settings JSON file. Defaults to data/settings.json
        """
        # The storage kernel owns the lock and the atomic write. Migrations
        # stay domain-run in _run_migrations below (they must execute before
        # any _load_* reads sections, and settings' error semantics — swallow
        # unreadable files, skip non-dict payloads — predate the kernel), so
        # no migrations are handed to the store.
        self._store = JsonStore(
            "settings.json" if settings_file is None else settings_file,
            current_schema_version=CURRENT_SETTINGS_SCHEMA_VERSION,
            label="Settings",
        )
        self.settings_file = self._store.path

        # Run ordered schema migrations on the raw settings file BEFORE any
        # subsystem reads, so every _load_* sees fully migrated values. This
        # includes the legacy carousel:->collection: rewrite (folded into the
        # v0->v1 migration) plus per-board active-page / schedule_enabled moves.
        self._run_migrations()

        # Load initial settings from env/file. settings.json is read and
        # parsed ONCE here and handed to every section loader. Each loader
        # used to call _load_from_file() itself, so constructing the service
        # opened and fully parsed the same file 12 times (13 with the
        # migration pass above) — on a 15 KB file that is ~200 KB read and
        # ~185 KB parsed per construction, on the Pi boot path.
        file_data = self._load_from_file()
        self._output = self._load_output_settings(file_data)
        self._active_page = self._load_section(file_data, "active_page", ActivePageSettings)
        self._polling = self._load_section(file_data, "polling", PollingSettings)
        self._board = self._load_board_settings(file_data)
        self._schedule = self._load_section(file_data, "schedule", ScheduleSettings)
        self._mqtt = self._load_mqtt_settings(file_data)
        self._display = self._load_section(file_data, "display", DisplaySettings)
        self._location = self._load_section(file_data, "location", LocationSettings)
        self._plugins = self._load_section(file_data, "plugins", PluginSettings)
        self._wizard = self._load_section(file_data, "wizard", WizardSettings)
        self._temporary_override: TemporaryOverride | None = self._load_temporary_override(file_data)

        if getattr(self, "_needs_seed_save", False):
            try:
                self._save_to_file()
            except OSError as e:
                # Boot path, not a request path: refusing to construct the
                # service would take the whole process down over a seed
                # write. Running with in-memory defaults and an unwritable
                # data dir is strictly better, and the next setter call —
                # which *is* a request — will surface the same OSError to
                # the caller as a 5xx.
                logger.error(f"Could not persist seeded settings at startup: {e}")
            self._needs_seed_save = False

        logger.info(f"SettingsService initialized (file: {self.settings_file})")

    @property
    def lock(self) -> threading.RLock:
        """The kernel store's lock, for out-of-band writers of settings.json
        (the backup restore, #1860) to serialise against normal saves."""
        return self._store.lock

    @property
    def _restore_notice_path(self) -> Path:
        return self.settings_file.with_name(RESTORE_NOTICE_FILENAME)

    def get_restore_notice(self) -> SettingsRestoreNotice | None:
        """The downgrade bridge's notice, until dismissed; None when there is none.

        A notice file that cannot be read or parsed counts as none: it only
        drives a banner, and the bridge's log line is the record of the swap.
        """
        try:
            raw = json.loads(self._restore_notice_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            logger.warning(f"Could not read the settings restore notice: {e}")
            return None
        try:
            return SettingsRestoreNotice.model_validate(raw)
        except ValidationError:
            logger.warning("Ignoring a malformed settings restore notice")
            return None

    def dismiss_restore_notice(self) -> None:
        """Forget the notice. The set-aside file itself is never touched.

        Idempotent. A failure to remove the file propagates (OSError).
        """
        self._restore_notice_path.unlink(missing_ok=True)

    @_locked
    def _run_migrations(self) -> None:
        """Run pending settings schema migrations on the raw settings file.

        Reads ``settings.json``, runs any migrations whose target version is
        newer than the file's ``schema_version`` (default 0), and resaves once
        when anything changed. A one-time backup of the pre-migration file is
        written to ``settings.json.v{N}_backup`` before the first migration
        runs. Migrations operate on the raw dict (before dataclass parsing) so
        every subsequent ``_load_*`` sees migrated values. No-op when the file
        does not exist or is already at the current version.
        """
        if not self.settings_file.exists():
            return

        try:
            with open(self.settings_file) as f:  # noqa: PTH123
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not pre-read settings for migration: {e}")
            return

        if not isinstance(data, dict):
            return

        current_version = data.get("schema_version", 0)
        if not isinstance(current_version, int):
            current_version = 0

        if current_version > CURRENT_SETTINGS_SCHEMA_VERSION:
            # Written by a newer build. Migrations are forward-only, so
            # there is nothing to run and no way to read this correctly.
            # Falling through would read v(N+1) content as vN and the next
            # save would stamp vN back onto it. This file is the one store
            # whose schema has actually diverged across a release boundary,
            # so it is what a downgrading user hits first.
            #
            # The downgrade bridge (D8) steps back onto the snapshot the newer
            # build took of this build's file, if there is one. This runs
            # before anything loads the file through the storage kernel, so
            # the kernel never latches the store read-only.
            if _bridge_from_downgrade_backup(self.settings_file, current_version) is None:
                backup = _downgrade_backup_path(self.settings_file)
                raise SchemaTooNewError(
                    label="settings",
                    path=self.settings_file,
                    found=current_version,
                    supported=CURRENT_SETTINGS_SCHEMA_VERSION,
                    remedy=(
                        f"This build restores its own pre-upgrade snapshot ({backup.name}) automatically, "
                        f"but no usable one is next to it. To recover, reinstall the newer FiestaBoard "
                        f"version, or replace {self.settings_file} with a settings backup taken before the "
                        f"upgrade, then restart."
                    ),
                )
            try:
                with open(self.settings_file) as f:  # noqa: PTH123
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Could not read the restored settings for migration: {e}")
                return
            current_version = data.get("schema_version", 0) if isinstance(data, dict) else 0
            if not isinstance(current_version, int):
                current_version = 0

        if current_version >= CURRENT_SETTINGS_SCHEMA_VERSION:
            return

        backup_path = self.settings_file.with_suffix(f".json.v{current_version}_backup")
        if not backup_path.exists():
            try:
                shutil.copy2(self.settings_file, backup_path)
                logger.info(f"Created pre-migration settings backup at {backup_path}")
            except OSError as e:
                logger.warning(f"Could not create settings backup: {e}")

        try:
            for target_version, migrate_fn in MIGRATIONS:
                if current_version >= target_version:
                    continue
                count = migrate_fn(data)
                logger.info(
                    f"Settings schema migration v{current_version}->v{target_version}: {count} change(s) applied"
                )
                current_version = target_version
        except Exception:
            # Abort the whole run without saving: schema_version on disk stays
            # pre-migration (no half-stamp — nothing mutated reaches disk) and
            # every pending migration re-runs on the next boot. Migrations are
            # idempotent by contract, so the retry is safe (#1866 review).
            logger.exception(
                f"Settings schema migration to v{CURRENT_SETTINGS_SCHEMA_VERSION} failed — "
                "leaving schema_version unstamped; will retry next boot"
            )
            return

        data["schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION

        try:
            self._atomic_write_json(data)
            logger.info("Saved migrated settings to file")
        except OSError as e:
            logger.warning(f"Could not write migrated settings: {e}")

    def _atomic_write_json(self, data: dict) -> None:
        """Write *data* to ``settings_file`` atomically via the storage kernel.

        A mid-write crash (OOM, SIGKILL, power loss) never truncates the real
        file — it stays untouched until the staged file is fully written and
        renamed over it (see #1304).
        """
        self._store.save(data)

    def _load_from_file(self) -> dict:
        """Load settings from JSON file."""
        if self.settings_file.exists():
            try:
                # Use builtins.open (not Path.open) so existing tests can
                # patch builtins.open to inject read errors.
                with open(self.settings_file) as f:  # noqa: PTH123
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to load settings file: {e}")
        return {}

    @_locked
    def _save_to_file(self) -> None:
        """Save current settings to JSON file.

        Write errors **propagate**, matching every other store in the
        codebase (pages, collections, schedules, panels, config_manager all
        log and re-raise). This used to log and return, so a full disk or a
        read-only ``data/`` produced ~20 endpoints that answered HTTP 200
        having persisted nothing and reverted on the next restart.

        The two callers that must survive a failed write — the boot-time
        seed save and the override expiry GC — catch ``OSError`` at their
        own call site, each with a comment saying why.
        """
        try:
            data = {
                "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION,
                "output": self._output.to_dict(),
                "active_page": self._active_page.to_dict(),
                "polling": self._polling.to_dict(),
                "board": self._board.to_dict(mask_secrets=False),
                "schedule": self._schedule.to_dict(),
                "mqtt": self._mqtt.to_dict(mask_secrets=False),
                "display": self._display.to_dict(),
                "location": self._location.to_dict(),
                "plugins": self._plugins.to_dict(),
                "temporary_override": self._temporary_override.to_dict() if self._temporary_override else None,
            }
            if self._wizard.state is not None:
                data["wizard"] = self._wizard.to_dict()
            self._atomic_write_json(data)
            logger.debug("Settings saved to file")
        except OSError as e:
            logger.error(f"Failed to save settings file: {e}")
            raise

    def _load_section(self, file_data: dict, key: str, cls: type[_Section]) -> _Section:
        """Read one settings section, or fall back to the dataclass default.

        Six sections (active_page, polling, schedule, display, location,
        plugins) are exactly this and nothing else — they had six-line
        methods, one caller each. The section with an env-var fallback
        (output), the one that seeds from legacy config.json (board), the
        one with env fallbacks (mqtt) and the one with expiry
        (temporary_override) keep their own loaders below.
        """
        if key in file_data:
            return cls.from_dict(file_data[key])
        return cls()

    def _load_output_settings(self, file_data: dict) -> OutputSettings:
        """Load output settings from the parsed file, or env."""
        if "output" in file_data:
            return OutputSettings.from_dict(file_data["output"])

        # Fall back to env
        from src.config import Config

        return OutputSettings(target=Config.OUTPUT_TARGET)

    def _load_board_settings(self, file_data: dict) -> BoardSettings:
        """Load board settings from the parsed file.

        Existing files: the schema migrations (run before any ``_load_*``)
        already imported the legacy config.json connection where appropriate,
        so the section is used as-is — a maintained board is never re-seeded
        from config.json (issue #1760).

        First boot only (no board section on disk yet): the freshly created
        default board inherits the legacy ``config.json -> board.*``
        connection, which is where env vars like ``BOARD_READ_WRITE_KEY``
        seed credentials. The seed is persisted after init via
        ``_needs_seed_save``.
        """
        pending = file_data.get(PENDING_TRANSITION_KEY)
        if "board" in file_data:
            settings = BoardSettings.from_dict(file_data["board"])
            changed = False
        else:
            settings = BoardSettings()
            changed = self._seed_connection_from_legacy_config(settings)
        # Settings v6: the install transition a v5 file had no boards for
        # (parked by the migration), then clamp what was stored before the cap.
        for entry in settings.boards:
            if isinstance(pending, dict):
                changed |= _apply_install_transition(
                    entry, pending.get("strategy"), pending.get("step_interval_ms"), pending.get("step_size")
                )
            changed |= _clamp_stored_speeds(entry)
        if "board" not in file_data:
            # The first display owns its transition from the start. Plugins
            # are off on a first boot, so a plugin: default is refused.
            settings.boards[0] = _with_default_transition(settings.boards[0], plugins_enabled=False)
        if changed or isinstance(pending, dict):
            self._needs_seed_save = True
        return settings

    @staticmethod
    def _seed_connection_from_legacy_config(settings: BoardSettings) -> bool:
        """First-boot seed: copy the legacy config.json connection into the
        default board when it carries no credential of its own.

        Returns True if settings were modified and need saving.
        """
        if not settings.boards:
            return False
        first = settings.boards[0]
        if _board_dict_has_credentials(first):
            return False
        try:
            legacy = _read_legacy_board_connection()
        except Exception:
            # First boot has no schema-version retry lever; skip the seed and
            # leave the board section unsaved so the next boot tries again.
            logger.warning("Could not read legacy board connection for first-boot seed", exc_info=True)
            return False
        if legacy is None:
            return False
        importable = _connection_fields_for_board(legacy, first)
        if importable is None:
            return False
        from src.devices import BoardInstance

        settings.boards[0] = BoardInstance.from_dict({**first, **importable}).to_dict()
        logger.info("Seeded first-boot board connection from legacy config.json")
        return True

    def _load_mqtt_settings(self, file_data: dict) -> "MQTTSettings":
        """Load MQTT settings from the parsed file, falling back to env vars."""
        if "mqtt" in file_data:
            return MQTTSettings.from_dict(file_data["mqtt"])
        # Fall back to env vars so existing env-based setups continue to work
        env_enabled = os.environ.get("MQTT_ENABLED", "false").lower() in ("1", "true", "yes")
        return MQTTSettings(
            enabled=env_enabled,
            broker_host=os.environ.get("MQTT_BROKER_HOST", "localhost") or "localhost",
            broker_port=int(os.environ.get("MQTT_BROKER_PORT", "1883") or 1883),
            username=os.environ.get("MQTT_USERNAME", "") or "",
            password=os.environ.get("MQTT_PASSWORD", "") or "",
            external_url=os.environ.get("FIESTABOARD_EXTERNAL_URL", "") or "",
        )

    def _load_temporary_override(self, file_data: dict) -> Optional["TemporaryOverride"]:
        """Load temporary override from the parsed file; None if absent or expired."""
        raw = file_data.get("temporary_override")
        if not raw:
            return None
        try:
            override = TemporaryOverride.from_dict(raw)
            if override.is_expired():
                return None
            return override
        except (KeyError, ValueError):
            return None

    # Transition settings
    def _board_entry(self, board_id: str | None) -> dict | None:
        """Stored board *board_id*. ``None``, ``""`` and the engine's primary
        runtime key (:data:`PRIMARY_RUNTIME_KEY`) mean the first board; an id
        no board has is ``None``."""
        boards = self._board.boards
        if board_id in (None, "", PRIMARY_RUNTIME_KEY):
            return boards[0] if boards else None
        return next((b for b in boards if b.get("id") == board_id), None)

    def get_transition_settings(self, board_id: str | None = None) -> TransitionSettings:
        """The transition display *board_id* runs (settings v6: its own).

        Strategy, step interval and step size are the board's
        (``transition``, ``transition_step_interval_ms``,
        ``transition_step_size``); there is no install-wide transition.
        ``"none"`` is no transition: ``None`` for a Vestaboard or FiestaPanel,
        and kept as the LED menu's ``"none"`` for an output plugin's board,
        whose unset strategy means its model's default instead. An unset
        choice on a split-flap board is none too.

        ``None``, ``""`` or :data:`PRIMARY_RUNTIME_KEY` is the first display:
        the engine's primary runtime, and the deprecated install-wide callers
        (``GET /settings/transitions``, MQTT state) until v11. An id no board
        has gets no transition.
        """
        from src.devices import is_split_flap

        board = self._board_entry(board_id)
        if board is None:
            return TransitionSettings()
        choice = board.get("transition")
        strategy: str | None = choice if isinstance(choice, str) and choice else None
        if strategy == BOARD_TRANSITION_NONE and is_split_flap(board):
            strategy = None
        return TransitionSettings(
            strategy=strategy,
            step_interval_ms=board.get("transition_step_interval_ms"),
            step_size=board.get("transition_step_size"),
        )

    @_locked
    def update_transition_settings(
        self, strategy: str | None = ..., step_interval_ms: int | None = ..., step_size: int | None = ...
    ) -> TransitionSettings:
        """Deprecated (until v11): set the FIRST display's transition.

        What ``PUT /settings/transitions`` and the MQTT ``transition_style``
        command still drive. Use ... (Ellipsis) to leave a field unchanged; a
        ``None`` speed is the device's default. A ``None`` strategy means what
        it meant in v5: no transition on a split-flap display (``"none"``),
        the device model's default on an output plugin's (unset). So a GET of
        :meth:`get_transition_settings` put straight back changes nothing.
        Set any display's own through its board settings instead.

        Raises:
            ValueError: an invalid strategy, a transition plugin while they
                are off, a bad speed, or no display to set.
        """
        from src.devices import is_split_flap

        first = self._board_entry(None)
        if first is None:
            raise ValueError("There is no display to set a transition on")
        updates: dict = {}
        if strategy is not ...:
            if strategy is not None:
                _check_strategy_for_board(strategy, first)
            if strategy is None:
                updates["transition"] = BOARD_TRANSITION_NONE if is_split_flap(first) else None
            else:
                updates["transition"] = strategy
        if step_interval_ms is not ...:
            updates["transition_step_interval_ms"] = step_interval_ms
        if step_size is not ...:
            updates["transition_step_size"] = step_size
        stored = self._write_board_fields(first.get("id"), updates)
        resolved = self.get_transition_settings(stored.get("id"))
        logger.info(f"First display's transition updated: {resolved}")
        return resolved

    @_locked
    def _write_board_fields(self, board_id: str | None, updates: dict) -> dict:
        """Write *updates* onto stored board *board_id* (the first when
        ``None``) and save; a ``None`` value removes the key.

        Validated exactly as a board save is (:meth:`_check_board_write`),
        then normalized through :class:`~src.devices.BoardInstance`.
        Returns the stored board.
        """
        from src.devices import BoardInstance

        stored = self._board_entry(board_id)
        if stored is None:
            raise ValueError(f"No display {board_id!r}")
        merged = dict(stored)
        for key, value in updates.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        self._check_board_write(merged, stored)
        normalized = BoardInstance.from_dict(merged).to_dict()
        index = next(i for i, b in enumerate(self._board.boards) if b is stored)
        self._board.boards[index] = normalized
        self._save_to_file()
        return normalized

    # Output settings
    def get_output_settings(self) -> OutputSettings:
        """Get current output settings."""
        return self._output

    @_locked
    def set_output_target(self, target: OutputTarget) -> OutputSettings:
        """Set the output target.

        Args:
            target: One of "ui", "board", or "both"

        Returns:
            Updated OutputSettings
        """
        if target not in VALID_OUTPUT_TARGETS:
            raise ValueError(f"Invalid target: {target}. Must be one of {VALID_OUTPUT_TARGETS}")

        self._output.target = target
        self._save_to_file()
        logger.info(f"Output target set to: {target}")
        return self._output

    def should_send_to_board(self) -> bool:
        """Determine if message should be sent to board based on output target."""
        return self._output.target in ["board", "both"]

    # Active page settings (per-board)
    def get_active_page_id(self, board_id: str | None = None) -> str | None:
        """Get the currently active (manual) page ID for a board.

        Args:
            board_id: Board to read. ``None`` resolves to the primary board.

        Returns:
            The board's active page ID, or None if not set.

        Resolution order:
          1. ``active_page.by_board[board_id]`` when present.
          2. For the primary board only, fall back to the legacy
             ``active_page.page_id`` mirror (covers pre-migration installs and
             the "no boards yet" deferred-migration case).
        """
        bid = board_id if board_id is not None else self.get_primary_board_id()
        if bid is not None and bid in self._active_page.by_board:
            return self._active_page.by_board[bid] or None
        # Legacy mirror fallback for the primary board (or when no board is known).
        if board_id is None or bid is None or bid == self.get_primary_board_id():
            return self._active_page.page_id
        return None

    @_locked
    def set_active_page_id(self, page_id: str | None, board_id: str | None = None) -> ActivePageSettings:
        """Set the active (manual) page ID for a board.

        Args:
            page_id: Page ID to set as active, or None to clear.
            board_id: Board to update. ``None`` resolves to the primary board.

        When the targeted board is the primary board the legacy
        ``active_page.page_id`` mirror is kept in sync for one release.

        Returns:
            Updated ActivePageSettings

        Raises:
            ValueError: ``board_id`` names a board that does not exist.
                Defense in depth (#1888): unreachable over HTTP today, but
                the write is otherwise unconditional, so an unknown id used
                to add a phantom ``by_board`` entry that nothing ever reads
                and nothing reports.
        """
        primary_id = self.get_primary_board_id()
        bid = board_id if board_id is not None else primary_id

        if board_id and not any(b.get("id") == board_id for b in self._board.boards):
            raise ValueError(f"Board not found: {board_id}")

        if bid is not None:
            if page_id:
                self._active_page.by_board[bid] = page_id
            else:
                self._active_page.by_board.pop(bid, None)

        # Keep the legacy primary mirror in sync (also covers the no-boards
        # case where bid is None and we only have the mirror to write to).
        if board_id is None or bid is None or bid == primary_id:
            self._active_page.page_id = page_id

        self._save_to_file()
        logger.info(f"Active page for board {bid!r} set to: {page_id}")
        return self._active_page

    def get_active_page_settings(self) -> ActivePageSettings:
        """Get current active page settings.

        Returns:
            ActivePageSettings instance
        """
        return self._active_page

    # Polling settings
    def get_polling_interval(self) -> int:
        """Get the current polling interval in seconds.

        Returns:
            Polling interval in seconds
        """
        return self._polling.interval_seconds

    @_locked
    def set_polling_interval(self, interval_seconds: int) -> PollingSettings:
        """Set the polling interval.

        Args:
            interval_seconds: Polling interval in seconds (minimum 10)

        Returns:
            Updated PollingSettings
        """
        if interval_seconds < 10:
            raise ValueError("Polling interval must be at least 10 seconds")

        self._polling.interval_seconds = interval_seconds
        self._save_to_file()
        logger.info(f"Polling interval set to: {interval_seconds} seconds")
        return self._polling

    @_locked
    def set_board_read_intervals(
        self,
        local_seconds: int | None = None,
        cloud_seconds: int | None = None,
    ) -> PollingSettings:
        """Set the board state read polling intervals.

        Args:
            local_seconds: Read interval for local-API boards (minimum 20)
            cloud_seconds: Read interval for cloud-API boards (minimum 20)

        Returns:
            Updated PollingSettings
        """
        if local_seconds is not None:
            if local_seconds < BOARD_READ_INTERVAL_MIN:
                raise ValueError(f"Board read interval must be at least {BOARD_READ_INTERVAL_MIN} seconds")
            self._polling.board_read_interval_local = local_seconds
        if cloud_seconds is not None:
            if cloud_seconds < BOARD_READ_INTERVAL_MIN:
                raise ValueError(f"Board read interval must be at least {BOARD_READ_INTERVAL_MIN} seconds")
            self._polling.board_read_interval_cloud = cloud_seconds
        self._save_to_file()
        return self._polling

    def get_polling_settings(self) -> PollingSettings:
        """Get current polling settings.

        Returns:
            PollingSettings instance
        """
        return self._polling

    # Board settings
    def get_board_settings(self) -> BoardSettings:
        """Get current board settings.

        Returns:
            BoardSettings instance
        """
        return self._board

    def get_primary_board_id(self) -> str | None:
        """Return the primary (first) configured board's id, or None.

        This is the single source of truth for "which board is the default"
        and replaces ad-hoc ``boards[0]`` lookups scattered across the codebase
        (main.py, schedules/service.py). Returns None when no boards exist or
        the first board has no id.
        """
        boards = self._board.boards or []
        if boards and isinstance(boards[0], dict):
            bid = boards[0].get("id")
            return bid if bid else None
        return None

    @_locked
    def set_board_type(self, board_type: Literal["black", "white"] | None) -> BoardSettings:
        """Set the board type for UI rendering.

        Args:
            board_type: "black", "white", or None for default

        Returns:
            Updated BoardSettings
        """
        if board_type is not None and board_type not in ["black", "white"]:
            raise ValueError(f"Invalid board_type: {board_type}. Must be 'black' or 'white'")

        self._board.board_type = board_type
        self._save_to_file()
        logger.info(f"Board type set to: {board_type}")
        return self._board

    @_locked
    def set_devices(self, devices: list[str]) -> BoardSettings:
        """Set the configured device types (backward-compatible).

        Creates/updates board instances to match the desired device type list.
        Preserves existing board instances where possible.

        Args:
            devices: List of device type strings (e.g. ["flagship", "note"])

        Returns:
            Updated BoardSettings
        """
        from src.devices import DEVICE_TYPES, BoardInstance

        valid_devices = [d for d in devices if d in DEVICE_TYPES]
        if not valid_devices:
            raise ValueError(f"At least one valid device required. Valid types: {DEVICE_TYPES}")

        # Keep existing boards that match requested device types
        existing_by_type = {}
        for b in self._board.boards:
            dt = b.get("device_type", "flagship")
            if dt not in existing_by_type:
                existing_by_type[dt] = b

        new_boards = []
        for dt in valid_devices:
            if dt in existing_by_type:
                new_boards.append(existing_by_type[dt])
            else:
                existing_names = {b.get("name", "") for b in new_boards}
                name = "My Board"
                n = 2
                while name in existing_names:
                    name = f"My Board {n}"
                    n += 1
                new_boards.append(
                    self._with_default_transition(
                        BoardInstance(
                            name=name,
                            device_type=dt,
                            board_color=self._board.board_type or "black",
                        ).to_dict()
                    )
                )

        self._board.boards = new_boards
        self._save_to_file()
        logger.info(f"Configured devices set to: {valid_devices}")
        return self._board

    @_locked
    def set_boards(self, boards: list[dict]) -> BoardSettings:
        """Set the configured board instances.

        Each board must have at least a device_type.
        ID and name are auto-generated if not provided.
        Masked sensitive fields ("***") are preserved from existing data.

        Args:
            boards: List of board instance dicts

        Returns:
            Updated BoardSettings
        """
        from src.devices import BoardInstance

        if not boards:
            raise ValueError("At least one board instance is required")

        existing_by_id = {b.get("id"): b for b in self._board.boards}

        from src.settings.board_shape import merge_board_write

        validated = []
        for b in boards:
            existing = existing_by_id.get(b.get("id"))
            restore_masked_board_secrets(b, existing or {})
            if existing is None:
                # A new display owns its transition from the start (settings v6).
                b = self._with_default_transition(b)
            # Either shape, or both (an echoed GET): plan D8's bidirectional
            # projection, resolved against the stored board.
            merged = merge_board_write(b, existing)
            self._check_board_write(merged, existing)
            validated.append(BoardInstance.from_dict(merged).to_dict())

        self._board.boards = validated
        # Keep board_type in sync with the first board's color
        first_color = validated[0].get("board_color") if validated else None
        if first_color in ("black", "white"):
            self._board.board_type = first_color
        self._save_to_file()
        logger.info(f"Configured boards set to: {[b.get('name') for b in validated]}")
        return self._board

    @_locked
    def add_board(self, board: dict) -> BoardSettings:
        """Add a new board instance.

        Args:
            board: Board instance dict with at least device_type

        Returns:
            Updated BoardSettings
        """
        from src.devices import BoardInstance

        if not board.get("name"):
            board["name"] = self._next_board_name()
        # Settings v6: a new display owns its transition from the start.
        board = self._with_default_transition(board)
        self._check_board_write(board, None)
        instance = BoardInstance.from_dict(board)
        self._board.boards.append(instance.to_dict())
        self._save_to_file()
        logger.info(f"Added board: {instance.name} ({instance.device_type})")
        return self._board

    def _with_default_transition(self, board: dict) -> dict:
        """*board* with the transition a new display starts with, unless it
        names one (:func:`default_board_transition`)."""
        return _with_default_transition(board, plugins_enabled=self._plugins.transition_plugins_enabled)

    def _check_board_write(self, board: dict, stored: dict | None) -> None:
        """Refuse a board write whose transition no menu offers, a newly
        chosen transition plugin while they are off, or a speed out of
        range — rather than let :class:`~src.devices.BoardInstance` quietly
        drop it. Only the fields the write changes are checked: what is
        already stored never blocks a write."""
        from src.devices import TRANSITION_SPEED_BOUNDS, transition_speed_error

        stored = stored or {}
        choice = board.get("transition")
        choice = (choice.strip() or None) if isinstance(choice, str) else None
        if stored == {} or choice != stored.get("transition"):
            self._check_board_transition(choice, stored.get("transition"))
        for key in TRANSITION_SPEED_BOUNDS:
            if stored == {} or board.get(key) != stored.get(key):
                error = transition_speed_error(key, board.get(key))
                if error:
                    raise ValueError(error)

    def _check_board_transition(self, choice: str | None, stored: str | None) -> None:
        """Refuse a display transition no menu offers, or a newly chosen
        transition plugin while they are off. A plugin choice already stored
        keeps saving with the board."""
        if not is_valid_board_transition(choice):
            raise ValueError(
                f"Invalid transition: {choice}. Must be 'none', one of {VALID_STRATEGIES}, "
                "'plugin:<id>' or an LED transition id"
            )
        if (
            isinstance(choice, str)
            and choice.startswith(TRANSITION_PLUGIN_PREFIX)
            and choice != stored
            and not self._plugins.transition_plugins_enabled
        ):
            raise ValueError(
                "Transition plugins are an experimental beta. "
                "Turn them on in a display's Transition section before selecting a plugin: transition."
            )

    def _next_board_name(self) -> str:
        """Generate the next available 'My Board' name."""
        existing = {b.get("name", "") for b in self._board.boards}
        if "My Board" not in existing:
            return "My Board"
        n = 2
        while f"My Board {n}" in existing:
            n += 1
        return f"My Board {n}"

    @_locked
    def remove_board(self, board_id: str) -> BoardSettings:
        """Remove a board instance by ID.

        Args:
            board_id: The ID of the board to remove

        Returns:
            Updated BoardSettings

        Raises:
            ValueError: If board not found or if it's the last board
        """
        if len(self._board.boards) <= 1:
            raise ValueError("Cannot remove the last board. At least one board is required.")

        new_boards = [b for b in self._board.boards if b.get("id") != board_id]
        if len(new_boards) == len(self._board.boards):
            raise ValueError(f"Board with ID '{board_id}' not found")

        self._board.boards = new_boards
        self._save_to_file()
        # Drop the board's silence-schedule override too (issue #1788 review):
        # nothing else ever removes it, so orphans accumulate in
        # ``features.silence_schedule.by_board`` for boards that no longer
        # exist.
        try:
            from src.config_manager import get_config_manager

            get_config_manager().prune_silence_schedule_for_board(board_id)
        except Exception:  # pragma: no cover - never block board removal
            logger.warning("Could not prune silence override for %s", board_id, exc_info=True)
        logger.info(f"Removed board: {board_id}")
        return self._board

    # Pause settings (per-board) — issue #970.
    # When a board is paused, FiestaBoard does not push anything to it from
    # any code path (polling loop, schedule, manual sends, plugin triggers,
    # MQTT, debug, welcome, etc). The board is left alone until resumed.
    def is_paused(self, board_id: str | None = None) -> bool:
        """Return True when the given board (or the first board) is paused.

        When ``board_id`` is None the first configured board is used. An
        unknown board_id returns False so callers default to "not paused"
        rather than silently dropping sends to an unrelated board.
        """
        if board_id:
            for b in self._board.boards:
                if b.get("id") == board_id:
                    return bool(b.get("paused", False))
            return False
        if self._board.boards:
            return bool(self._board.boards[0].get("paused", False))
        return False

    @_locked
    def set_paused(self, paused: bool, board_id: str | None = None) -> bool:
        """Pause or resume a board (or the first board when board_id is None).

        Returns the new paused state. Logs a warning and returns the prior
        state if ``board_id`` is provided but no matching board exists.
        """
        paused = bool(paused)
        if board_id:
            for b in self._board.boards:
                if b.get("id") == board_id:
                    b["paused"] = paused
                    self._save_to_file()
                    logger.info(f"Board {board_id} {'paused' if paused else 'resumed'}")
                    return paused
            # Defense in depth (#1888): unreachable over HTTP today — every
            # route that gets here validates the board first, or 404s on its
            # own path parameter — but returning False for an unknown board
            # is indistinguishable from "resumed successfully".
            raise ValueError(f"Board not found: {board_id}")
        if self._board.boards:
            self._board.boards[0]["paused"] = paused
            self._save_to_file()
            logger.info(f"Default board {'paused' if paused else 'resumed'}")
        return paused

    # Schedule settings
    def get_schedule_settings(self) -> ScheduleSettings:
        """Get current schedule settings.

        Returns:
            ScheduleSettings instance
        """
        return self._schedule

    def is_schedule_enabled(self, board_id: str | None = None) -> bool:
        """Check if schedule mode is enabled for a board.

        Schedule mode is authoritative **per-board** via
        ``boards[i].schedule_enabled``. ``board_id=None`` resolves to the
        primary board. An unknown board_id returns False. The legacy global
        ``schedule.enabled`` mirror is only consulted when there are no
        configured boards at all (pre-board installs).
        """
        bid = board_id if board_id is not None else self.get_primary_board_id()
        if bid is not None:
            for b in self._board.boards:
                if b.get("id") == bid:
                    return bool(b.get("schedule_enabled", False))
            return False
        # No boards configured: fall back to the deprecated global mirror.
        return self._schedule.enabled

    @_locked
    def set_schedule_enabled(self, enabled: bool, board_id: str | None = None) -> ScheduleSettings:
        """Enable or disable schedule mode for a board.

        ``board_id=None`` resolves to the primary board. Writing the primary
        board also updates the deprecated ``schedule.enabled`` mirror for one
        release.
        """
        primary_id = self.get_primary_board_id()
        bid = board_id if board_id is not None else primary_id

        if bid is not None:
            for b in self._board.boards:
                if b.get("id") == bid:
                    b["schedule_enabled"] = enabled
                    if bid == primary_id:
                        self._schedule.enabled = enabled
                    self._save_to_file()
                    logger.info(f"Schedule mode for board {bid}: {'enabled' if enabled else 'disabled'}")
                    return self._schedule
            logger.warning(f"Board {bid} not found for set_schedule_enabled")
            return self._schedule

        # No boards configured: write the deprecated global mirror only.
        self._schedule.enabled = enabled
        self._save_to_file()
        logger.info(f"Schedule mode (global, no boards): {'enabled' if enabled else 'disabled'}")
        return self._schedule

    def set_schedule_defer_on_reenable(self, defer: bool) -> ScheduleSettings:
        """Set whether re-enabling schedule mode waits for the next window.

        Unlike ``schedule_enabled`` this is a single global preference: it
        describes how the toggle behaves, not what any one board is showing.
        """
        self._schedule.defer_on_reenable = bool(defer)
        self._save_to_file()
        logger.info(f"Schedule defer-on-reenable: {'on' if defer else 'off'}")
        return self._schedule

    def get_mqtt_settings(self) -> "MQTTSettings":
        """Return current MQTT integration settings."""
        return self._mqtt

    @_locked
    def set_mqtt_settings(self, updates: dict) -> "MQTTSettings":
        """Persist MQTT settings and return updated object.

        Only keys present in *updates* are changed; omitted keys keep their
        current values.  The password is only overwritten when the caller
        supplies a non-empty, non-masked value.
        """
        if "enabled" in updates:
            self._mqtt.enabled = bool(updates["enabled"])
        if updates.get("broker_host"):
            self._mqtt.broker_host = updates["broker_host"]
        if "broker_port" in updates:
            self._mqtt.broker_port = int(updates["broker_port"] or 1883)
        if "username" in updates:
            self._mqtt.username = updates["username"] or ""
        if "password" in updates and updates["password"] not in ("", "***"):
            self._mqtt.password = updates["password"]
        if "external_url" in updates:
            self._mqtt.external_url = updates["external_url"] or ""
        self._save_to_file()
        return self._mqtt

    def get_display_settings(self) -> "DisplaySettings":
        """Return current web UI display settings."""
        return self._display

    @_locked
    def update_display_settings(self, updates: dict) -> "DisplaySettings":
        """Update display settings and persist.

        Only keys present in *updates* are changed.
        """
        if "reduce_motion" in updates:
            self._display.reduce_motion = bool(updates["reduce_motion"])
        if "board_animations" in updates:
            self._display.board_animations = _coerce_board_animations(updates["board_animations"])
        if "site_animations" in updates:
            self._display.site_animations = _coerce_site_animations(updates["site_animations"])
        if "board_flap_speed" in updates:
            self._display.board_flap_speed = _coerce_board_flap_speed(updates["board_flap_speed"])
        self._save_to_file()
        logger.info(f"Display settings updated: {self._display}")
        return self._display

    def get_location_settings(self) -> "LocationSettings":
        """Return current location settings for sun-based schedules."""
        return self._location

    @_locked
    def update_location_settings(self, updates: dict) -> "LocationSettings":
        """Update location settings and persist.

        Only keys present in *updates* are changed.
        """
        if "latitude" in updates:
            val = updates["latitude"]
            self._location.latitude = float(val) if val is not None else None
        if "longitude" in updates:
            val = updates["longitude"]
            self._location.longitude = float(val) if val is not None else None
        self._save_to_file()
        logger.info(f"Location settings updated: {self._location}")
        return self._location

    def get_plugin_settings(self) -> "PluginSettings":
        """Return current plugin system settings."""
        return self._plugins

    @_locked
    def update_plugin_settings(self, updates: dict) -> "PluginSettings":
        """Update plugin settings and persist. Only keys present in *updates* are changed.

        ``transition_plugins_enabled`` takes effect immediately;
        ``output_plugins_enabled`` on the next board rebuild (saving a board,
        or a restart).
        """
        for key in ("auto_update", "transition_plugins_enabled", "output_plugins_enabled"):
            if key in updates and updates[key] is not None:
                setattr(self._plugins, key, bool(updates[key]))
        self._save_to_file()
        logger.info(f"Plugin settings updated: {self._plugins}")
        return self._plugins

    # Setup wizard
    def get_wizard_state(self) -> WizardState | None:
        """How the setup wizard ended on this install, or ``None``."""
        return self._wizard.state

    @_locked
    def set_wizard_state(self, state: WizardState | None) -> WizardSettings:
        """Record how the setup wizard ended; ``None`` clears it (a reset).

        Raises:
            ValueError: *state* is not one of :data:`VALID_WIZARD_STATES`.
        """
        if state is not None and state not in VALID_WIZARD_STATES:
            raise ValueError(f"Invalid wizard state: {state}. Must be one of {VALID_WIZARD_STATES}")
        self._wizard.state = state
        self._save_to_file()
        logger.info(f"Setup wizard state set to: {state}")
        return self._wizard

    # Temporary override
    @_locked
    def get_temporary_override(self) -> TemporaryOverride | None:
        """Return the active temporary override, or None if absent or expired.

        Auto-clears the stored override when it has expired so subsequent
        reads don't need to check expiry themselves.
        """
        if self._temporary_override is None:
            return None
        if self._temporary_override.is_expired():
            self._temporary_override = None
            try:
                self._save_to_file()
            except OSError as e:
                # Background GC on a read path (the display loop calls this
                # every tick). The override is already expired in memory, so
                # the caller's answer is correct either way; failing the read
                # would stall the loop over a write that will be retried on
                # the next expiry.
                logger.error(f"Could not persist temporary-override expiry: {e}")
            return None
        return self._temporary_override

    @_locked
    def consume_temporary_override(self) -> TemporaryOverride | None:
        """Return the current temporary override (live or expired) and clear it if expired.

        Used by the display loop so it can detect a just-expired override and
        apply revert-mode side-effects (blank board, set active page, etc.).
        Unlike get_temporary_override(), this returns the expired object instead
        of None so the caller can inspect revert_mode before it's gone.
        """
        raw = self._temporary_override
        if raw is None:
            return None
        if raw.is_expired():
            self._temporary_override = None
            try:
                self._save_to_file()
            except OSError as e:
                # Same background-GC reasoning as get_temporary_override:
                # the display loop must still receive the expired override
                # so it can apply revert_mode.
                logger.error(f"Could not persist temporary-override expiry: {e}")
        return raw

    @_locked
    def set_temporary_override(self, override: TemporaryOverride) -> TemporaryOverride:
        """Persist a new temporary override, replacing any existing one."""
        self._temporary_override = override
        self._save_to_file()
        logger.info(
            "Temporary override set: %s expires=%s revert=%s",
            "inline one-off" if override.is_inline else f"page={override.page_id}",
            override.expires_at or "never",
            override.revert_mode,
        )
        return override

    @_locked
    def clear_temporary_override(self) -> None:
        """Remove the temporary override without applying any revert logic."""
        if self._temporary_override is not None:
            logger.info("Temporary override cleared")
        self._temporary_override = None
        self._save_to_file()


# Singleton instance
_settings_service: SettingsService | None = None


def get_settings_service() -> SettingsService:
    """Get or create the settings service singleton."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service
