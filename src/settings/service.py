"""Settings service for managing runtime configuration.

This service allows runtime modification of settings like transition
animations and output targets, which can be controlled from the UI.
"""

import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# Valid values
VALID_STRATEGIES = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]
VALID_OUTPUT_TARGETS = ["ui", "board", "both"]

OutputTarget = Literal["ui", "board", "both"]
TransitionStrategy = Literal["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]


@dataclass
class TransitionSettings:
    """Transition animation settings."""

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


BOARD_SENSITIVE_FIELDS = {"local_api_key", "cloud_key", "note_array_token"}


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
        """Return a copy of a board dict with sensitive fields masked."""
        masked = dict(board)
        for key in BOARD_SENSITIVE_FIELDS:
            if masked.get(key):
                masked[key] = "***"
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
    """A user-initiated, time-limited page override.

    While active, the specified page is shown instead of the scheduled or
    manual page. When it expires the revert_mode determines what happens next:
      - "schedule": clear override, schedule resumes naturally
      - "blank": clear override, board is blanked
      - "page": clear override, active page is set to revert_page_id
    """

    page_id: str
    expires_at: str  # ISO 8601 UTC timestamp (e.g. "2026-05-16T21:30:00+00:00")
    revert_mode: str  # "schedule" | "blank" | "page"
    revert_page_id: str | None = None

    def is_expired(self) -> bool:
        """Return True when the override's expiry timestamp has passed."""
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return datetime.now(UTC) >= expiry
        except (ValueError, TypeError):
            return True

    def remaining_seconds(self) -> float:
        """Return the number of seconds remaining before expiry (0 if expired)."""
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TemporaryOverride":
        return cls(
            page_id=data["page_id"],
            expires_at=data["expires_at"],
            revert_mode=data.get("revert_mode", "schedule"),
            revert_page_id=data.get("revert_page_id"),
        )


@dataclass
class ScheduleSettings:
    """Schedule system settings.

    ``enabled`` is **deprecated** as the source of truth: schedule mode is now
    authoritative per-board via ``boards[i].schedule_enabled``. This flag is
    retained for one release only as a back-compat mirror of the *primary*
    board's value. Use ``SettingsService.is_schedule_enabled(board_id)``.
    """

    enabled: bool = False  # Deprecated mirror of the primary board's schedule_enabled

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleSettings":
        return cls(enabled=data.get("enabled", False))


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

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DisplaySettings":
        return cls(
            reduce_motion=bool(data.get("reduce_motion", False)),
            board_animations=_coerce_board_animations(data.get("board_animations", "on")),
            site_animations=_coerce_site_animations(data.get("site_animations", "on")),
        )


@dataclass
class PluginSettings:
    """Plugin system settings."""

    auto_update: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PluginSettings":
        return cls(auto_update=bool(data.get("auto_update", True)))


@dataclass
class BetaSettings:
    """Opt-in beta features.

    These are experimental settings that may change behavior, require a
    container restart, or be removed in future releases. Currently:

    - https_enabled: When true, nginx serves HTTPS on the container's
      external port using a per-instance self-signed certificate
      generated at container startup. Toggling this requires a restart
      to take effect.
    """

    https_enabled: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BetaSettings":
        return cls(https_enabled=bool(data.get("https_enabled", False)))


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

CURRENT_SETTINGS_SCHEMA_VERSION = 1

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


MIGRATIONS: list[tuple[int, Callable[[dict], int]]] = [
    (1, _migrate_v0_to_v1),
]


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
        if settings_file is None:
            # Default to data directory in project root
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.settings_file = data_dir / "settings.json"
        else:
            self.settings_file = Path(settings_file)

        # Run ordered schema migrations on the raw settings file BEFORE any
        # subsystem reads, so every _load_* sees fully migrated values. This
        # includes the legacy carousel:->collection: rewrite (folded into the
        # v0->v1 migration) plus per-board active-page / schedule_enabled moves.
        self._run_migrations()

        # Load initial settings from env/file
        self._transition = self._load_transition_settings()
        self._output = self._load_output_settings()
        self._active_page = self._load_active_page_settings()
        self._polling = self._load_polling_settings()
        self._board = self._load_board_settings()
        self._schedule = self._load_schedule_settings()
        self._mqtt = self._load_mqtt_settings()
        self._display = self._load_display_settings()
        self._location = self._load_location_settings()
        self._beta = self._load_beta_settings()
        self._plugins = self._load_plugin_settings()
        self._temporary_override: TemporaryOverride | None = self._load_temporary_override()

        if getattr(self, "_needs_migration_save", False):
            self._save_to_file()
            self._needs_migration_save = False

        logger.info(f"SettingsService initialized (file: {self.settings_file})")

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

        if current_version >= CURRENT_SETTINGS_SCHEMA_VERSION:
            return

        backup_path = self.settings_file.with_suffix(f".json.v{current_version}_backup")
        if not backup_path.exists():
            try:
                shutil.copy2(self.settings_file, backup_path)
                logger.info(f"Created pre-migration settings backup at {backup_path}")
            except OSError as e:
                logger.warning(f"Could not create settings backup: {e}")

        for target_version, migrate_fn in MIGRATIONS:
            if current_version >= target_version:
                continue
            count = migrate_fn(data)
            logger.info(f"Settings schema migration v{current_version}->v{target_version}: {count} change(s) applied")
            current_version = target_version

        data["schema_version"] = CURRENT_SETTINGS_SCHEMA_VERSION

        try:
            with open(self.settings_file, "w") as f:  # noqa: PTH123
                json.dump(data, f, indent=2)
            logger.info("Saved migrated settings to file")
        except OSError as e:
            logger.warning(f"Could not write migrated settings: {e}")

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

    def _save_to_file(self) -> None:
        """Save current settings to JSON file."""
        try:
            data = {
                "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION,
                "transitions": self._transition.to_dict(),
                "output": self._output.to_dict(),
                "active_page": self._active_page.to_dict(),
                "polling": self._polling.to_dict(),
                "board": self._board.to_dict(mask_secrets=False),
                "schedule": self._schedule.to_dict(),
                "mqtt": self._mqtt.to_dict(mask_secrets=False),
                "display": self._display.to_dict(),
                "location": self._location.to_dict(),
                "beta": self._beta.to_dict(),
                "plugins": self._plugins.to_dict(),
                "temporary_override": self._temporary_override.to_dict() if self._temporary_override else None,
            }
            # Use builtins.open (not Path.open) so existing tests can
            # patch builtins.open to inject write errors.
            with open(self.settings_file, "w") as f:  # noqa: PTH123
                json.dump(data, f, indent=2)
            logger.debug("Settings saved to file")
        except OSError as e:
            logger.error(f"Failed to save settings file: {e}")

    def _load_transition_settings(self) -> TransitionSettings:
        """Load transition settings from file or env."""
        # Try file first
        file_data = self._load_from_file()
        if "transitions" in file_data:
            return TransitionSettings.from_dict(file_data["transitions"])

        # Fall back to env
        from src.config import Config

        return TransitionSettings(
            strategy=Config.FB_TRANSITION_STRATEGY,
            step_interval_ms=Config.FB_TRANSITION_INTERVAL_MS,
            step_size=Config.FB_TRANSITION_STEP_SIZE,
        )

    def _load_output_settings(self) -> OutputSettings:
        """Load output settings from file or env."""
        # Try file first
        file_data = self._load_from_file()
        if "output" in file_data:
            return OutputSettings.from_dict(file_data["output"])

        # Fall back to env
        from src.config import Config

        return OutputSettings(target=Config.OUTPUT_TARGET)

    def _load_active_page_settings(self) -> ActivePageSettings:
        """Load active page settings from file."""
        file_data = self._load_from_file()
        if "active_page" in file_data:
            return ActivePageSettings.from_dict(file_data["active_page"])
        return ActivePageSettings()

    def _load_polling_settings(self) -> PollingSettings:
        """Load polling settings from file."""
        file_data = self._load_from_file()
        if "polling" in file_data:
            return PollingSettings.from_dict(file_data["polling"])
        return PollingSettings()  # Default to 60 seconds

    def _load_board_settings(self) -> BoardSettings:
        """Load board settings from file.

        If the first board has no connection settings, migrate them from
        the global board config (config.json) so existing setups keep working.
        Migration is deferred -- _migrate_global_connection sets a flag,
        and the actual save happens after all settings are fully initialized.
        """
        file_data = self._load_from_file()
        if "board" in file_data:
            settings = BoardSettings.from_dict(file_data["board"])
        else:
            settings = BoardSettings()

        self._needs_migration_save = self._apply_global_connection(settings)
        return settings

    def _apply_global_connection(self, settings: BoardSettings) -> bool:
        """Copy global board connection config into board instances that lack one.

        Returns True if settings were modified and need saving.
        """
        if not settings.boards:
            return False

        first = settings.boards[0]
        if first.get("local_api_key") or first.get("cloud_key"):
            return False

        try:
            from src.config_manager import get_config_manager

            global_cfg = get_config_manager().get_board()
        except Exception:
            return False

        if not global_cfg.get("local_api_key") and not global_cfg.get("cloud_key"):
            return False

        first["api_mode"] = global_cfg.get("api_mode", "local")
        first["host"] = global_cfg.get("host", "")
        first["local_api_key"] = global_cfg.get("local_api_key", "")
        first["cloud_key"] = global_cfg.get("cloud_key", "")
        logger.info("Migrated global board connection to first board instance")
        return True

    def _load_schedule_settings(self) -> ScheduleSettings:
        """Load schedule settings from file."""
        file_data = self._load_from_file()
        if "schedule" in file_data:
            return ScheduleSettings.from_dict(file_data["schedule"])
        return ScheduleSettings()

    def _load_mqtt_settings(self) -> "MQTTSettings":
        """Load MQTT settings from file, falling back to env vars."""
        file_data = self._load_from_file()
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

    def _load_display_settings(self) -> "DisplaySettings":
        """Load display settings from file."""
        file_data = self._load_from_file()
        if "display" in file_data:
            return DisplaySettings.from_dict(file_data["display"])
        return DisplaySettings()

    def _load_location_settings(self) -> "LocationSettings":
        """Load location settings from file."""
        file_data = self._load_from_file()
        if "location" in file_data:
            return LocationSettings.from_dict(file_data["location"])
        return LocationSettings()

    def _load_beta_settings(self) -> "BetaSettings":
        """Load beta-feature settings from file."""
        file_data = self._load_from_file()
        if "beta" in file_data:
            return BetaSettings.from_dict(file_data["beta"])
        return BetaSettings()

    def _load_plugin_settings(self) -> "PluginSettings":
        """Load plugin system settings from file."""
        file_data = self._load_from_file()
        if "plugins" in file_data:
            return PluginSettings.from_dict(file_data["plugins"])
        return PluginSettings()

    def _load_temporary_override(self) -> Optional["TemporaryOverride"]:
        """Load temporary override from file, returning None if absent or expired."""
        file_data = self._load_from_file()
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
    def get_transition_settings(self) -> TransitionSettings:
        """Get current transition settings."""
        return self._transition

    def update_transition_settings(
        self, strategy: str | None = ..., step_interval_ms: int | None = ..., step_size: int | None = ...
    ) -> TransitionSettings:
        """Update transition settings.

        Use ... (Ellipsis) to leave a setting unchanged, None to clear it.

        Args:
            strategy: Transition strategy or None to disable
            step_interval_ms: Step interval or None for default
            step_size: Step size or None for default

        Returns:
            Updated TransitionSettings
        """
        if strategy is not ...:
            if strategy is not None and strategy not in VALID_STRATEGIES:
                raise ValueError(f"Invalid strategy: {strategy}. Must be one of {VALID_STRATEGIES}")
            self._transition.strategy = strategy

        if step_interval_ms is not ...:
            self._transition.step_interval_ms = step_interval_ms

        if step_size is not ...:
            self._transition.step_size = step_size

        self._save_to_file()
        logger.info(f"Transition settings updated: {self._transition}")
        return self._transition

    # Output settings
    def get_output_settings(self) -> OutputSettings:
        """Get current output settings."""
        return self._output

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

    def should_send_to_ui(self) -> bool:
        """Determine if message should be sent to UI."""
        return True

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

    def set_active_page_id(self, page_id: str | None, board_id: str | None = None) -> ActivePageSettings:
        """Set the active (manual) page ID for a board.

        Args:
            page_id: Page ID to set as active, or None to clear.
            board_id: Board to update. ``None`` resolves to the primary board.

        When the targeted board is the primary board the legacy
        ``active_page.page_id`` mirror is kept in sync for one release.

        Returns:
            Updated ActivePageSettings
        """
        primary_id = self.get_primary_board_id()
        bid = board_id if board_id is not None else primary_id

        if bid is not None:
            if page_id:
                self._active_page.by_board[bid] = page_id
            else:
                self._active_page.by_board.pop(bid, None)

        # Keep the legacy primary mirror in sync (also covers the no-boards case
        # where bid is None and we only have the mirror to write to).
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
                    BoardInstance(
                        name=name,
                        device_type=dt,
                        board_color=self._board.board_type or "black",
                    ).to_dict()
                )

        self._board.boards = new_boards
        self._save_to_file()
        logger.info(f"Configured devices set to: {valid_devices}")
        return self._board

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

        validated = []
        for b in boards:
            # Preserve sensitive fields if the incoming value is masked
            existing = existing_by_id.get(b.get("id"), {})
            for key in BOARD_SENSITIVE_FIELDS:
                if b.get(key) == "***":
                    b[key] = existing.get(key, "")
            instance = BoardInstance.from_dict(b)
            validated.append(instance.to_dict())

        self._board.boards = validated
        # Keep board_type in sync with the first board's color
        first_color = validated[0].get("board_color") if validated else None
        if first_color in ("black", "white"):
            self._board.board_type = first_color
        self._save_to_file()
        logger.info(f"Configured boards set to: {[b.get('name') for b in validated]}")
        return self._board

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
        instance = BoardInstance.from_dict(board)
        self._board.boards.append(instance.to_dict())
        self._save_to_file()
        logger.info(f"Added board: {instance.name} ({instance.device_type})")
        return self._board

    def _next_board_name(self) -> str:
        """Generate the next available 'My Board' name."""
        existing = {b.get("name", "") for b in self._board.boards}
        if "My Board" not in existing:
            return "My Board"
        n = 2
        while f"My Board {n}" in existing:
            n += 1
        return f"My Board {n}"

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
            logger.warning(f"Board {board_id} not found for set_paused")
            return False
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

    def get_mqtt_settings(self) -> "MQTTSettings":
        """Return current MQTT integration settings."""
        return self._mqtt

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
        self._save_to_file()
        logger.info(f"Display settings updated: {self._display}")
        return self._display

    def get_location_settings(self) -> "LocationSettings":
        """Return current location settings for sun-based schedules."""
        return self._location

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

    def get_beta_settings(self) -> "BetaSettings":
        """Return current beta-feature settings."""
        return self._beta

    def update_beta_settings(self, updates: dict) -> "BetaSettings":
        """Update beta-feature settings and persist.

        Only keys present in *updates* are changed. This method only
        records the user's preference -- side effects like generating
        or removing TLS certificates are handled by the API layer so
        the settings module stays free of system-level concerns.
        """
        if "https_enabled" in updates:
            self._beta.https_enabled = bool(updates["https_enabled"])
        self._save_to_file()
        logger.info(f"Beta settings updated: {self._beta}")
        return self._beta

    def get_plugin_settings(self) -> "PluginSettings":
        """Return current plugin system settings."""
        return self._plugins

    def update_plugin_settings(self, updates: dict) -> "PluginSettings":
        """Update plugin settings and persist. Only keys present in *updates* are changed."""
        if "auto_update" in updates:
            self._plugins.auto_update = bool(updates["auto_update"])
        self._save_to_file()
        logger.info(f"Plugin settings updated: {self._plugins}")
        return self._plugins

    # Temporary override
    def get_temporary_override(self) -> TemporaryOverride | None:
        """Return the active temporary override, or None if absent or expired.

        Auto-clears the stored override when it has expired so subsequent
        reads don't need to check expiry themselves.
        """
        if self._temporary_override is None:
            return None
        if self._temporary_override.is_expired():
            self._temporary_override = None
            self._save_to_file()
            return None
        return self._temporary_override

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
            self._save_to_file()
        return raw

    def set_temporary_override(self, override: TemporaryOverride) -> TemporaryOverride:
        """Persist a new temporary override, replacing any existing one."""
        self._temporary_override = override
        self._save_to_file()
        logger.info(
            "Temporary override set: page=%s expires=%s revert=%s",
            override.page_id,
            override.expires_at,
            override.revert_mode,
        )
        return override

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
