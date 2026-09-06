"""Configuration file manager for FiestaBoard Display Service.

Manages reading and writing configuration to a JSON file with validation
and thread-safe file operations.

Supports:
- Plugin system (config.plugins.*) for data source integrations
- System features (config.features.*) — since #1761 only ``silence_schedule``
  lives there; the legacy per-integration feature blocks were retired and
  survive solely as raw input to the one-shot feature->plugin migration
"""

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from src.paths import get_data_dir

# Import TimeService for migration
from .atomic_io import write_json_atomic
from .time_service import get_time_service

logger = logging.getLogger(__name__)

# Key under which we record the last app version that booted against this
# config. Used by the boot-time snapshot guard below.
APP_VERSION_SEEN_KEY = "app_version_seen"

# The silence-schedule keys that can be overridden per board (issue #1788).
# Anything outside this tuple (notably ``by_board`` itself) is never copied
# into a per-board entry.
SILENCE_SCHEDULE_KEYS = (
    "enabled",
    "start_time",
    "end_time",
    "mode",
    "page_id",
    "indicator_text",
    "indicator_position",
)

# Mapping from legacy feature keys to plugin IDs.
# silence_schedule is a system feature and is NOT migrated here.
FEATURE_TO_PLUGIN_MAP = {
    "weather": "weather",
    "date_time": "date_time",
    "home_assistant": "home_assistant",
    "guest_wifi": "guest_wifi",
    "star_trek_quotes": "star_trek_quotes",
    "air_fog": "air_fog",
    "muni": "muni",
    "surf": "surf",
    "baywheels": "baywheels",
    "traffic": "traffic",
    "stocks": "stocks",
}

# Fields excluded from feature-to-plugin migration (handled by manifest defaults)
MIGRATION_EXCLUDED_FIELDS = {"color_rules"}

# Plugin renames applied on startup. Maps an obsolete plugin id to its
# replacement id. Each entry is a one-shot, idempotent rename of the
# `plugins.<old_id>` config block to `plugins.<new_id>`.
PLUGIN_ID_RENAMES: dict[str, str] = {
    # v2.0.0 of the bike share plugin generalised to all Lyft-operated
    # GBFS systems (Bay Wheels, CitiBike, Capital Bikeshare, Biketown,
    # Divvy, ...) and renamed the plugin id.
    "baywheels": "lyft_bike_share",
}


# Per-rename adjustments to the migrated settings dict. Each handler
# receives a deep-copied settings dict and returns the adjusted dict
# that will be written under the new plugin id. Used to drop fields
# that no longer exist in the new manifest and seed new defaults.
def _adjust_baywheels_to_lyft_bike_share(cfg: dict[str, Any]) -> dict[str, Any]:
    """Adjust a v1 baywheels config to fit the v2 lyft_bike_share schema.

    - Promotes the legacy singular ``station_id`` into ``station_ids`` if
      the list is empty (so users with the old single-station setup
      keep monitoring the same station).
    - Drops the deprecated singular ``station_id`` and ``station_name``
      fields, which were removed in v2.0.0.
    - Seeds a default ``gbfs_base_url`` (Bay Wheels) if not present, so
      existing users keep pointing at the same feed without manual
      reconfiguration.
    """
    legacy_id = cfg.pop("station_id", None)
    cfg.pop("station_name", None)

    station_ids = cfg.get("station_ids")
    if not station_ids and legacy_id:
        cfg["station_ids"] = [legacy_id]

    cfg.setdefault("gbfs_base_url", "https://gbfs.baywheels.com/gbfs/en")
    return cfg


PLUGIN_RENAME_ADJUSTERS: dict[str, Any] = {
    "baywheels": _adjust_baywheels_to_lyft_bike_share,
}

# ---------------------------------------------------------------------------
# Read-time env-var overlay for plugin config (issue #1761).
#
# Historically these env vars were written into the legacy ``features.*``
# blocks and persisted — which made them silent no-ops on any install already
# migrated to the plugin system, and left stale values on disk after the
# variable was unset. They are now a pure overlay: applied when plugin config
# is READ (``get_plugin_config`` / ``get_all_plugin_configs``, the choke
# point the plugin registry and API read through), never persisted, and the
# stored value returns as soon as the variable is unset.
#
# Semantics:
#   * An env var wins over the stored value while it is set.
#   * Placeholder values (``your_api_key_here`` etc.) are ignored.
#   * Unparseable numeric/JSON values are ignored with a warning.
#   * The overlay only augments plugins that already have a stored config
#     entry — it never conjures a config for an uninstalled plugin.
#   * Instance keys (``weather:sf``) share their base plugin's overrides.
#
# Board-connection and general env vars (BOARD_*, TIMEZONE, ...) are a
# separate mechanism and keep their seed-once-into-config.json behavior in
# ``_apply_env_overrides``.


def _env_csv(value: str) -> list[str]:
    """Parse a comma-separated env value into a list of stripped items."""
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_json(value: str) -> Any:
    """Parse a JSON env value (e.g. HOME_ASSISTANT_ENTITIES)."""
    return json.loads(value)


# env var -> (plugin id, plugin config key, parser)
ENV_PLUGIN_OVERRIDES: dict[str, tuple[str, str, Any]] = {
    # Weather
    "WEATHER_API_KEY": ("weather", "api_key", str),
    "WEATHER_PROVIDER": ("weather", "provider", str),
    "WEATHER_LOCATION": ("weather", "location", str),
    # Guest WiFi
    "GUEST_WIFI_SSID": ("guest_wifi", "ssid", str),
    "GUEST_WIFI_PASSWORD": ("guest_wifi", "password", str),
    "GUEST_WIFI_REFRESH_SECONDS": ("guest_wifi", "refresh_seconds", int),
    # Home Assistant
    "HOME_ASSISTANT_BASE_URL": ("home_assistant", "base_url", str),
    "HOME_ASSISTANT_ACCESS_TOKEN": ("home_assistant", "access_token", str),
    "HOME_ASSISTANT_TIMEOUT": ("home_assistant", "timeout", int),
    "HOME_ASSISTANT_REFRESH_SECONDS": ("home_assistant", "refresh_seconds", int),
    "HOME_ASSISTANT_ENTITIES": ("home_assistant", "entities", _env_json),
    # Star Trek quotes
    "STAR_TREK_QUOTES_RATIO": ("star_trek_quotes", "ratio", str),
    # Muni
    "MUNI_API_KEY": ("muni", "api_key", str),
    "MUNI_REFRESH_SECONDS": ("muni", "refresh_seconds", int),
    # Traffic
    "GOOGLE_ROUTES_API_KEY": ("traffic", "api_key", str),
    "TRAFFIC_REFRESH_SECONDS": ("traffic", "refresh_seconds", int),
    # Bike share (the baywheels plugin was renamed to lyft_bike_share; the
    # env var keeps its historical name)
    "BAYWHEELS_REFRESH_SECONDS": ("lyft_bike_share", "refresh_seconds", int),
    # Surf
    "SURF_LATITUDE": ("surf", "latitude", float),
    "SURF_LONGITUDE": ("surf", "longitude", float),
    "SURF_REFRESH_SECONDS": ("surf", "refresh_seconds", int),
    # Air quality / fog
    "PURPLEAIR_API_KEY": ("air_fog", "purpleair_api_key", str),
    "PURPLEAIR_SENSOR_ID": ("air_fog", "purpleair_sensor_id", str),
    "OPENWEATHERMAP_API_KEY": ("air_fog", "openweathermap_api_key", str),
    "AIR_FOG_LATITUDE": ("air_fog", "latitude", float),
    "AIR_FOG_LONGITUDE": ("air_fog", "longitude", float),
    "AIR_FOG_REFRESH_SECONDS": ("air_fog", "refresh_seconds", int),
    # Stocks
    "FINNHUB_API_KEY": ("stocks", "finnhub_api_key", str),
    "STOCKS_TIME_WINDOW": ("stocks", "time_window", str),
    "STOCKS_REFRESH_SECONDS": ("stocks", "refresh_seconds", int),
    "STOCKS_SYMBOLS": ("stocks", "symbols", _env_csv),
}

# Default configuration schema

DEFAULT_CONFIG: dict[str, Any] = {
    "board": {
        "api_mode": "local",
        "local_api_key": "",
        "cloud_key": "",
        "note_array_token": "",
        "host": "",
        "transition_strategy": None,
        "transition_interval_ms": None,
        "transition_step_size": None,
    },
    "features": {
        "silence_schedule": {
            "enabled": False,
            "start_time": "20:00",  # 8pm (will be migrated to UTC ISO format)
            "end_time": "07:00",  # 7am (will be migrated to UTC ISO format)
            # Behavior while silence is active:
            #   "indicator" - clear the board and show custom text centered (default)
            #   "freeze"    - leave whatever is currently on the board, stop updating
            #   "page"      - render the chosen page once, then stop updating
            "mode": "freeze",
            # Custom text to display when mode == "indicator"
            "indicator_text": "SNOOZING",
            # Position of indicator text on board: center, top-left, top-right, bottom-left, bottom-right
            "indicator_position": "center",
            # Page id to display when mode == "page" (variables are frozen at silence-start)
            "page_id": None,
            # Per-board overrides (issue #1788): board_id -> partial dict of the
            # seven keys above. A board with no entry inherits the values above,
            # which act as the install-wide default. MUST stay in DEFAULT_CONFIG:
            # set_feature() whitelists keys against it and would otherwise drop
            # this one silently.
            "by_board": {},
        },
    },
    "general": {
        "timezone": "America/Los_Angeles",  # User's timezone for display purposes
        "refresh_interval_seconds": 300,
        "output_target": "board",
        "instance_name": "",  # Friendly name for this FiestaBoard install
        "time_format": "12h",  # "12h" or "24h" for web UI time display
        "date_format": "MM/DD/YYYY",  # "MM/DD/YYYY", "DD/MM/YYYY", or "YYYY-MM-DD"
        "welcome_message": "",  # Custom board greeting; empty = use default
    },
    # AI provider configuration for the "Gen AI" page-generation feature.
    # BYO-LLM: users supply their own OpenAI-compatible endpoint, key,
    # and list of model identifiers. We never bundle a key. Keys are
    # masked in API responses via SENSITIVE_FIELDS below.
    "ai_providers": {
        "enabled": False,
        "providers": [],
        "default_provider_id": None,
    },
    # Plugin configurations
    # Each plugin's config is stored under plugins.<plugin_id>
    # Example: plugins.weather = {enabled: true, api_key: "...", ...}
    "plugins": {},
}

# Fields that should be masked in API responses
SENSITIVE_FIELDS = {
    "api_key",
    "local_api_key",
    "cloud_key",
    "note_array_token",
    "access_token",
    "password",
    "finnhub_api_key",
    "purpleair_api_key",
    "openweathermap_api_key",
    "client_id",
    "client_secret",
}

# What the API substitutes for a sensitive value on the way out. Anything that
# comes back from a settings form carries this rather than the real secret.
MASKED_VALUE = "***"


def unmask_sensitive_values(values: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Return *values* with every masked sensitive field restored from *stored*.

    The browser never holds a real secret: :meth:`ConfigManager._mask_sensitive`
    replaces every :data:`SENSITIVE_FIELDS` entry with :data:`MASKED_VALUE`
    before the config leaves the process. Anything the form posts back
    therefore says ``"***"`` where the API key used to be, and writing that
    through — or handing it to a plugin — replaces a working credential with
    three asterisks.

    A masked key at a path that *does* exist in *stored* but holds nothing
    resolves to ``""`` rather than being dropped, matching the persisted-config
    behaviour this was extracted from: the field was explicitly submitted, so
    it should end up present and empty rather than silently absent. That is a
    key with no secret behind it, not a secret being erased.

    Nested dicts and lists are walked too, mirroring
    :meth:`ConfigManager._mask_sensitive`, which masks at any depth. A flat
    un-mask left every nested secret — a plugin's ``sources[0].api_key``, say —
    reading ``"***"`` on the way out and persisting ``"***"`` on the way back
    in (issue #1743).

    Inside a list, a secret is restored only into the element it belongs to.
    See :func:`_match_stored_element` for how an element is identified and what
    happens when it cannot be.

    Args:
        values: Incoming settings, possibly carrying masked placeholders.
        stored: The currently persisted settings to restore secrets from.

    Returns:
        A new dict; *values* is not mutated.
    """
    return _unmask_node(values, stored)


# Sentinel for "no stored counterpart could be identified for this node", as
# distinct from "the stored counterpart is known and holds nothing". The first
# means guessing; the second is an ordinary absent value.
_UNMATCHED = object()

# Fields that identify a list element across an edit, most specific first.
IDENTITY_FIELDS = ("id", "name", "key")


def _match_stored_element(item: Any, stored_list: list[Any]) -> Any:
    """Return the stored element *item* is confidently the same as, or ``_UNMATCHED``.

    Positional matching is not safe here: deleting, reordering, or inserting a
    list element shifts every later index, and the secret restored into an
    element would then be its neighbour's. A wrong-but-plausible credential is
    worse than a visibly broken one — it fails as an auth error the user blames
    on the provider, whereas ``"***"`` fails loudly and locally.

    So an element is matched only on evidence: a unique hit on the first
    :data:`IDENTITY_FIELDS` key it carries, or — when it carries none — a
    unique stored element whose non-sensitive keys are all equal to its own.
    Anything else (no candidate, several candidates, a renamed identity) is
    ``_UNMATCHED``, and every masked field below it keeps the sentinel for the
    schema layer to reject.
    """
    if not isinstance(item, dict):
        return _UNMATCHED

    candidates = [element for element in stored_list if isinstance(element, dict)]

    for field in IDENTITY_FIELDS:
        if field in item and isinstance(item[field], (str, int)) and not isinstance(item[field], bool):
            matches = [element for element in candidates if element.get(field) == item[field]]
            return matches[0] if len(matches) == 1 else _UNMATCHED

    signature = _non_sensitive_keys(item)
    matches = [element for element in candidates if _non_sensitive_keys(element) == signature]
    return matches[0] if len(matches) == 1 else _UNMATCHED


def _non_sensitive_keys(element: dict[str, Any]) -> dict[str, Any]:
    """The part of *element* a client can echo back unchanged: everything unmasked."""
    return {key: value for key, value in element.items() if key not in SENSITIVE_FIELDS}


def _unmask_node(value: Any, stored: Any) -> Any:
    """Recursive worker for :func:`unmask_sensitive_values`."""
    if isinstance(value, dict):
        unmatched = stored is _UNMATCHED
        stored_dict = stored if isinstance(stored, dict) else {}
        merged: dict[str, Any] = {}
        for key, item in value.items():
            if key in SENSITIVE_FIELDS and item == MASKED_VALUE:
                # Under an unmatched element there is nothing to restore from,
                # and "" would destroy a secret just as surely as "***" did.
                merged[key] = MASKED_VALUE if unmatched else stored_dict.get(key, "")
            else:
                merged[key] = _unmask_node(item, _UNMATCHED if unmatched else stored_dict.get(key))
        return merged
    if isinstance(value, list):
        if stored is _UNMATCHED:
            return [_unmask_node(item, _UNMATCHED) for item in value]
        stored_list = stored if isinstance(stored, list) else []
        return [_unmask_node(item, _match_stored_element(item, stored_list)) for item in value]
    return value


class ConfigManager:
    """Manages configuration file read/write operations."""

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, config_path: str | None = None) -> "ConfigManager":
        """Singleton pattern to ensure only one config manager exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    # Initialised once per singleton lifetime (NOT in __init__,
                    # which can re-run before _initialized flips — see the latch
                    # in _maybe_snapshot_on_version_change). A re-entrant
                    # ConfigManager() during the first __init__ (plugin-registry
                    # init reaches back through get_config_manager) would
                    # otherwise reset this to False and silently disable the
                    # post-upgrade auto-restore (#1102).
                    cls._instance._version_changed_on_load = False
        return cls._instance

    def __init__(self, config_path: str | None = None) -> None:
        """Initialize the config manager.

        Args:
            config_path: Path to the config file. Defaults to config.json in project root.
        """
        if self._initialized:
            return

        # Re-entrant so a method that needs the whole read-modify-write to be
        # atomic (``migrate_silence_schedule_to_utc``) can hold it across the
        # public accessors, which take it again.  A plain Lock would deadlock
        # there, which is why that migration reached for the class-level
        # singleton lock instead and blocked ConfigManager() everywhere (#1746).
        self._file_lock = threading.RLock()

        # Determine config file path
        if config_path:
            self._config_path = Path(config_path)
        else:
            # Default to data directory
            self._config_path = get_data_dir() / "config.json"

        self._config: dict[str, Any] = {}
        self._raw_features: dict[str, Any] = {}
        self._load_or_create()
        self._auto_migrate_features_to_plugins()
        self._migrate_renamed_plugins()
        self._apply_env_overrides()
        self._initialized = True

    def _load_or_create(self) -> None:
        """Load config from file or create with defaults if missing."""
        with self._file_lock:
            if self._config_path.exists():
                try:
                    with self._config_path.open() as f:
                        self._config = json.load(f)
                    logger.info(f"Loaded config from {self._config_path}")

                    # Take a pre-init safety snapshot BEFORE any migration or
                    # merge touches the loaded data. This covers every upgrade
                    # path (docker compose pull, FiestaUpdater button, FiestaPi
                    # button, watchtower, manual swap) — anything that brings
                    # up a new binary against an existing data dir. See
                    # issue #948 (integrations lost on upgrade).
                    self._maybe_snapshot_on_version_change()

                    # Snapshot features actually present before merge fills in defaults
                    self._raw_features = self._deep_copy(self._config.get("features", {}))

                    # Merge with defaults to handle missing keys
                    self._config = self._merge_with_defaults(self._config)
                    self._stamp_app_version_seen()
                    self._save_internal()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in config file: {e}")
                    logger.info("Creating new config with defaults")
                    # Deep copy: a shallow .copy() shares the nested dicts, so
                    # every later in-place write (env overrides, profile
                    # defaults) would silently mutate DEFAULT_CONFIG itself.
                    self._config = self._deep_copy(DEFAULT_CONFIG)
                    self._apply_profile_defaults()
                    self._stamp_app_version_seen()
                    self._save_internal()
            else:
                logger.info(f"Config file not found, creating defaults at {self._config_path}")
                self._config = self._deep_copy(DEFAULT_CONFIG)
                self._apply_profile_defaults()
                self._stamp_app_version_seen()
                self._save_internal()

    # ── boot-time safety snapshot (issue #948) ──────────────────────────
    #
    # Whenever the app version on disk differs from the one we just booted,
    # snapshot data/ to data/update-backups/ BEFORE we touch anything. The
    # existing /system/update/rollback flow already knows how to list and
    # restore these files — by reusing the `pre-update-<ts>.json` naming
    # convention we get rollback for free, regardless of which upgrade
    # path the user took (compose pull, FiestaUpdater, FiestaPi button…).

    def _stamp_app_version_seen(self) -> None:
        """Record the running app version into the loaded config dict.

        Caller is responsible for persisting via ``_save_internal``.
        """
        try:
            from src import __version__ as current_version
        except Exception:  # pragma: no cover - defensive
            return
        self._config[APP_VERSION_SEEN_KEY] = current_version

    # Files captured in the pre-init snapshot. Mirrors backup/service.py's
    # DATA_FILES but is intentionally inlined: BackupService.build_backup()
    # eagerly initialises the plugin registry, which during ConfigManager
    # init recurses back through __init__ and corrupts self._config_path.
    # A flat dict of file payloads is enough for the rollback flow to
    # restore from.
    _PRE_INIT_SNAPSHOT_FILES = (
        "config.json",
        "settings.json",
        "pages.json",
        "collections.json",
        "schedules.json",
    )

    def _maybe_snapshot_on_version_change(self) -> None:
        """If the running version differs from what was last seen, write a
        pre-init snapshot of ``data/*.json`` to ``update-backups/``.

        No-op when:
          * the version matches (no upgrade happened),
          * there is no prior version AND no meaningful user data (fresh
            install — nothing to back up).

        Failures are swallowed: the snapshot is a safety net, never a
        gate that could prevent the app from booting.

        Implementation note: we deliberately bypass BackupService here.
        Its ``build_backup`` calls ``_collect_installed_plugins`` →
        ``get_plugin_registry`` → ``PluginRegistry.initialize`` →
        ``get_config_manager`` — which during ``ConfigManager.__init__``
        re-enters this singleton with the *default* config path and
        clobbers the one the caller passed in. We hand-roll a minimal
        snapshot to keep the safety net free of that init-time recursion.
        """
        try:
            from src import __version__ as current_version
        except Exception:  # pragma: no cover
            return

        seen = self._config.get(APP_VERSION_SEEN_KEY)
        # Latch: once True for this process it stays True. A second load (e.g. a
        # re-entrant get_config_manager() during plugin-registry init, or an
        # explicit reload()) runs AFTER _stamp_app_version_seen has rewritten
        # app_version_seen to the current version — recomputing from scratch
        # would clear the flag and silently disable the auto-restore (#1102).
        self._version_changed_on_load = self._version_changed_on_load or (seen is not None and seen != current_version)
        if seen == current_version:
            return

        # Treat as a "first boot" if there's neither a recorded version nor
        # any user-authored data worth backing up. A fresh install legitimately
        # has neither, and dumping an empty backup just clutters the rollback
        # picker.
        has_user_data = bool(
            self._config.get("plugins")
            or self._config.get("features", {}).get("silence_schedule")
            or self._config.get("board", {}).get("local_api_key")
            or self._config.get("board", {}).get("cloud_key")
        )
        if seen is None and not has_user_data:
            return

        try:
            data_dir = self._config_path.parent
            snapshot_dir = data_dir / "update-backups"
            snapshot_dir.mkdir(parents=True, exist_ok=True)

            data_payload: dict[str, Any] = {}
            for filename in self._PRE_INIT_SNAPSHOT_FILES:
                source = data_dir / filename
                if not source.is_file():
                    data_payload[filename[:-5]] = None
                    continue
                try:
                    data_payload[filename[:-5]] = json.loads(source.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    data_payload[filename[:-5]] = None

            doc = {
                "fiestaboard_backup": True,
                "schema_version": 1,
                "exported_at": datetime.now(UTC).isoformat(),
                "app_version": current_version,
                "data": data_payload,
                "installed_plugins": [],
                "_fiestaupdater": {
                    "previous_digest": None,
                    "previous_image": None,
                    "previous_version": seen or "unknown",
                    "current_version": current_version,
                    "trigger": "boot-version-change",
                },
            }

            # Match the existing pre-update-<ts>.json shape so the same
            # rollback endpoint can list and restore these snapshots
            # without any extra plumbing.
            now = datetime.now(UTC)
            ts = now.strftime("%Y%m%dT%H%M%S") + f".{now.microsecond // 1000:03d}Z"
            target = snapshot_dir / f"pre-update-{ts}.json"

            # Belt-and-braces against same-millisecond collisions when
            # multiple boot snapshots fire from a tight test/CI loop.
            for bump in range(1, 1000):
                if not target.exists():
                    break
                ms = (now.microsecond // 1000 + bump) % 1000
                ts = now.strftime("%Y%m%dT%H%M%S") + f".{ms:03d}Z"
                target = snapshot_dir / f"pre-update-{ts}.json"

            write_json_atomic(target, doc)

            logger.info(
                "Version change detected (%s -> %s); pre-init snapshot written to %s",
                seen or "<unknown>",
                current_version,
                target.name,
            )
        except Exception:
            logger.warning(
                "Could not write pre-init snapshot for version change %s -> %s",
                seen or "<unknown>",
                current_version,
                exc_info=True,
            )

    def _apply_profile_defaults(self) -> None:
        """Apply install-profile-specific overrides at fresh-config creation
        time only.

        On the FiestaPi flashable image (`FIESTABOARD_PROFILE=pi`), default
        the friendly instance name to "FiestaPi" so the sidebar/browser tab
        show something meaningful out of the box. Users can rename via
        Settings; we only set this when creating a brand-new config so a
        deliberate clear from the UI isn't reset on every restart.
        """
        profile = os.getenv("FIESTABOARD_PROFILE", "docker").strip().lower() or "docker"
        if profile == "pi":
            general = self._config.setdefault("general", {})
            if not general.get("instance_name"):
                general["instance_name"] = "FiestaPi"

    def _deep_copy(self, obj: Any) -> Any:
        """Create a deep copy of a nested dict/list structure."""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        return obj

    # Fields that should be replaced entirely (not recursively merged)
    REPLACE_FIELDS = {"color_rules"}

    def _merge_with_defaults(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge config with defaults to handle missing keys.

        Note: Some fields like 'color_rules' are replaced entirely rather than
        recursively merged, so user deletions are preserved.
        """
        result = self._deep_copy(DEFAULT_CONFIG)

        def merge(base: dict, update: dict, path: str = "") -> dict:
            for key, value in update.items():
                current_path = f"{path}.{key}" if path else key
                # Check if this field should be replaced entirely
                if key in self.REPLACE_FIELDS:
                    base[key] = self._deep_copy(value)
                elif key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    merge(base[key], value, current_path)
                else:
                    base[key] = value
            return base

        return merge(result, config)

    def _auto_migrate_features_to_plugins(self) -> None:
        """Automatically migrate legacy features to plugins on startup.

        For each known feature that was **actually present in the user's config
        file** (not just filled in by defaults) and has no corresponding entry
        in ``plugins.*``, copy the feature config into the plugins section so
        the v2 plugin system picks it up.  A JSON backup of the original config
        is created before any changes are written.

        This is idempotent — once a plugin entry exists the feature is skipped.
        """
        plugins = self._config.get("plugins", {})

        to_migrate: list[tuple] = []
        for feature_key, plugin_id in FEATURE_TO_PLUGIN_MAP.items():
            if feature_key not in self._raw_features:
                continue
            if plugin_id in plugins:
                continue
            raw_cfg = self._raw_features[feature_key]
            if not raw_cfg or not isinstance(raw_cfg, dict):
                continue
            merged_cfg = self._config.get("features", {}).get(feature_key, raw_cfg)
            to_migrate.append((feature_key, plugin_id, merged_cfg))

        if not to_migrate:
            return

        # Back up config before making changes
        backup_path = self._config_path.with_suffix(".json.v1_backup")
        if not backup_path.exists():
            try:
                import shutil

                shutil.copy2(self._config_path, backup_path)
                logger.info(f"Created pre-migration backup at {backup_path}")
            except Exception as e:
                logger.warning(f"Could not create backup: {e}")

        with self._file_lock:
            if "plugins" not in self._config:
                self._config["plugins"] = {}

            for feature_key, plugin_id, feature_cfg in to_migrate:
                plugin_cfg = {
                    k: self._deep_copy(v) for k, v in feature_cfg.items() if k not in MIGRATION_EXCLUDED_FIELDS
                }
                self._config["plugins"][plugin_id] = plugin_cfg
                logger.info(f"Auto-migrated feature '{feature_key}' -> plugin '{plugin_id}'")

            self._save_internal()

        logger.info(f"Auto-migration complete: {len(to_migrate)} feature(s) migrated to plugins")

    def _migrate_renamed_plugins(self) -> None:
        """Apply one-shot plugin id renames defined in PLUGIN_ID_RENAMES.

        For each ``old_id -> new_id`` entry, if ``plugins.<old_id>`` exists
        and ``plugins.<new_id>`` does not, the old block is moved under the
        new id (running an optional adjuster to drop/rename fields). If
        both exist, the old block is dropped to avoid leaking stale
        settings. The pass is naturally idempotent — once the rename has
        run, ``plugins.<old_id>`` no longer exists and the loop is a
        no-op.
        """
        plugins = self._config.get("plugins")
        if not isinstance(plugins, dict) or not plugins:
            return

        renamed: list[tuple] = []
        for old_id, new_id in PLUGIN_ID_RENAMES.items():
            if old_id not in plugins:
                continue

            old_cfg = plugins[old_id]
            if not isinstance(old_cfg, dict):
                # Unexpected shape; drop it silently rather than raise.
                plugins.pop(old_id, None)
                continue

            if new_id in plugins:
                # User already has the new plugin configured; drop the
                # stale old entry without overwriting their config.
                plugins.pop(old_id, None)
                logger.info(
                    f"Plugin rename '{old_id}' -> '{new_id}': new id already present, dropping stale old config"
                )
                renamed.append((old_id, new_id, False))
                continue

            adjuster = PLUGIN_RENAME_ADJUSTERS.get(old_id)
            new_cfg = self._deep_copy(old_cfg)
            if adjuster is not None:
                try:
                    new_cfg = adjuster(new_cfg)
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(
                        f"Adjuster for plugin rename '{old_id}' -> '{new_id}' "
                        f"failed ({e}); falling back to a plain rename"
                    )
                    new_cfg = self._deep_copy(old_cfg)

            plugins[new_id] = new_cfg
            plugins.pop(old_id, None)
            renamed.append((old_id, new_id, True))
            logger.info(f"Renamed plugin config '{old_id}' -> '{new_id}'")

        if not renamed:
            return

        with self._file_lock:
            self._save_internal()

        logger.info(f"Plugin rename migration complete: {len(renamed)} plugin(s) processed")

    def _save_internal(self) -> None:
        """Internal save without acquiring lock (called from locked context).

        Writes go through :func:`src.atomic_io.write_json_atomic` (process-
        scoped staging file + ``os.replace``) so a mid-write crash (OOM,
        SIGKILL, power loss) never leaves a truncated config file (see #1304)
        and concurrent processes never collide on a fixed staging name.
        """
        try:
            write_json_atomic(self._config_path, self._config)
            logger.debug(f"Saved config to {self._config_path}")
        except OSError as e:
            logger.error(f"Failed to save config: {e}")
            raise

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """Return True if a string looks like an unedited .env placeholder.

        Recognises patterns such as ``your_api_key_here``, ``changeme``,
        ``replace_me``, ``example_key``, etc.  These ship in the default
        ``.env`` / ``env.example`` and should never be treated as real
        configuration.
        """
        v = value.lower().strip()
        if v.startswith(("your_", "your-")):
            return True
        if v.endswith(("_here", "-here")):
            return True
        return v in ("changeme", "replace_me", "replace-me", "example", "placeholder")

    def _apply_env_overrides(self) -> None:
        """Apply board/general environment variable overrides to config.

        Only sets values if they're empty in config (allows env vars to provide defaults).
        Environment variables take precedence for initial setup but UI changes are preserved.
        Placeholder values from .env (e.g. ``your_api_key_here``) are ignored.

        Plugin env vars (``WEATHER_API_KEY`` and friends) are NOT handled
        here anymore: since #1761 they are a read-time overlay applied in
        :meth:`get_plugin_config` / :meth:`get_all_plugin_configs` — never
        persisted, active only while the variable is set. This method keeps
        only the board-connection and general settings, which by design
        seed ``config.json`` once on first boot.
        """
        changed = False

        # Ensure structures exist
        if "board" not in self._config:
            self._config["board"] = {}
        if "general" not in self._config:
            self._config["general"] = {}

        # Helper to apply string env var
        def apply_str(config: dict, key: str, env_var: str, alt_env_var: str | None = None) -> bool:
            value = os.getenv(env_var, "").strip()
            if not value and alt_env_var:
                value = os.getenv(alt_env_var, "").strip()
            if value and ConfigManager._is_placeholder(value):
                logger.debug(f"Ignoring placeholder value for {env_var}")
                return False
            if value and not config.get(key):
                config[key] = value
                logger.info(f"Applied {env_var} from environment variable")
                return True
            return False

        # Helper to apply int env var
        def apply_int(config: dict, key: str, env_var: str, alt_env_var: str | None = None) -> bool:
            value = os.getenv(env_var, "").strip()
            if not value and alt_env_var:
                value = os.getenv(alt_env_var, "").strip()
            if value and config.get(key) is None:
                try:
                    config[key] = int(value)
                    logger.info(f"Applied {env_var} from environment variable")
                    return True
                except ValueError:
                    logger.warning(f"Invalid {env_var} value: {value}")
            return False

        board_config = self._config["board"]
        general_config = self._config["general"]

        # ==================== Board Configuration ====================
        changed |= apply_str(board_config, "api_mode", "BOARD_API_MODE", "FB_API_MODE")
        changed |= apply_str(board_config, "local_api_key", "BOARD_LOCAL_API_KEY", "FB_LOCAL_API_KEY")
        changed |= apply_str(board_config, "host", "BOARD_HOST", "FB_HOST")
        changed |= apply_str(board_config, "cloud_key", "BOARD_READ_WRITE_KEY", "FB_READ_WRITE_KEY")
        changed |= apply_str(board_config, "note_array_token", "BOARD_NOTE_ARRAY_TOKEN")
        changed |= apply_str(board_config, "transition_strategy", "BOARD_TRANSITION_STRATEGY", "FB_TRANSITION_STRATEGY")
        changed |= apply_int(
            board_config, "transition_interval_ms", "BOARD_TRANSITION_INTERVAL_MS", "FB_TRANSITION_INTERVAL_MS"
        )
        changed |= apply_int(
            board_config, "transition_step_size", "BOARD_TRANSITION_STEP_SIZE", "FB_TRANSITION_STEP_SIZE"
        )

        # ==================== General Configuration ====================
        changed |= apply_str(general_config, "timezone", "TIMEZONE")
        changed |= apply_int(general_config, "refresh_interval_seconds", "REFRESH_INTERVAL_SECONDS")
        changed |= apply_str(general_config, "output_target", "OUTPUT_TARGET")

        # Save if any changes were made
        if changed:
            with self._file_lock:
                self._save_internal()

    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_or_create()
        self._apply_env_overrides()
        logger.info("Configuration reloaded from file")

    @property
    def lock(self) -> threading.RLock:
        """The manager's file lock, for callers that write ``config.json``
        out-of-band (the backup restore) and must not interleave with a
        concurrent ``_save_internal`` (#1860)."""
        return self._file_lock

    @property
    def version_changed_on_load(self) -> bool:
        """True if this process loaded an existing config from an older app version.

        False on fresh installs, corrupt-config resets, and same-version restarts.
        Drives the post-upgrade auto-restore so it only runs on a real upgrade boot.
        """
        return self._version_changed_on_load

    def get_all(self) -> dict[str, Any]:
        """Get full configuration (internal use - includes secrets)."""
        with self._file_lock:
            return self._deep_copy(self._config)

    def get_all_masked(self) -> dict[str, Any]:
        """Get full configuration with sensitive fields masked."""
        config = self.get_all()
        return self._mask_sensitive(config)

    def _mask_sensitive(self, obj: Any, path: str = "") -> Any:
        """Recursively mask sensitive fields in config."""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                if key in SENSITIVE_FIELDS and value:
                    # Show that a value is set without revealing it
                    result[key] = "***" if value else ""
                else:
                    result[key] = self._mask_sensitive(value, current_path)
            return result
        if isinstance(obj, list):
            return [self._mask_sensitive(item, path) for item in obj]
        return obj

    def get_board(self) -> dict[str, Any]:
        """Get board configuration."""
        with self._file_lock:
            # Support both old "board_legacy" and new "board" keys for migration
            config = self._config.get("board") or self._config.get("board_legacy", {})
            return self._deep_copy(config)

    def set_board(self, settings: dict[str, Any]) -> None:
        """Update board configuration.

        Args:
            settings: Partial board settings to update.
        """
        with self._file_lock:
            if "board" not in self._config:
                self._config["board"] = {}

            # Only update provided fields
            for key, value in settings.items():
                if key in DEFAULT_CONFIG["board"]:
                    # IMPORTANT: Don't overwrite real values with masked placeholders
                    if key in SENSITIVE_FIELDS and value == "***":
                        logger.debug(f"Preserving existing value for masked field: board.{key}")
                        continue
                    self._config["board"][key] = value

            self._save_internal()
        logger.info("Board settings updated")

    # Backward compatibility aliases
    def get_board_legacy(self) -> dict[str, Any]:
        """Backward compatibility alias for get_board()."""
        return self.get_board()

    def set_board_legacy(self, settings: dict[str, Any]) -> None:
        """Backward compatibility alias for set_board()."""
        self.set_board(settings)

    def reset_board_config(self) -> None:
        """Reset board configuration to defaults, bypassing env-var re-application.

        Unlike calling ``set_board`` with empty fields followed by ``Config.reload()``,
        this method writes the default board values and does **not** re-apply
        ``_apply_env_overrides``.  This puts the backend back into first-run mode
        regardless of what ``BOARD_HOST``/``BOARD_LOCAL_API_KEY`` env vars are set to,
        which is the behaviour the setup-wizard integration test needs.
        """
        with self._file_lock:
            self._config["board"] = dict(DEFAULT_CONFIG["board"].items())
            self._save_internal()
        logger.info("Board config reset to defaults (first-run mode, env overrides skipped)")

    def get_feature(self, feature_name: str) -> dict[str, Any] | None:
        """Get configuration for a specific feature.

        Args:
            feature_name: Name of the feature (e.g., 'weather', 'guest_wifi').

        Returns:
            Feature configuration dict or None if not found.
        """
        with self._file_lock:
            features = self._config.get("features", {})
            if feature_name in features:
                return self._deep_copy(features[feature_name])
            # If feature not in config but exists in defaults, return default
            if feature_name in DEFAULT_CONFIG.get("features", {}):
                return self._deep_copy(DEFAULT_CONFIG["features"][feature_name])
            return None

    def set_feature(self, feature_name: str, settings: dict[str, Any]) -> bool:
        """Update configuration for a specific feature.

        Args:
            feature_name: Name of the feature.
            settings: Partial feature settings to update.

        Returns:
            True if successful, False if feature doesn't exist.
        """
        with self._file_lock:
            if "features" not in self._config:
                self._config["features"] = {}

            if feature_name not in DEFAULT_CONFIG.get("features", {}):
                logger.warning(f"Unknown feature: {feature_name}")
                return False

            if feature_name not in self._config["features"]:
                self._config["features"][feature_name] = self._deep_copy(DEFAULT_CONFIG["features"][feature_name])

            # Only update provided fields
            for key, value in settings.items():
                # Allow any key that exists in defaults, 'enabled', or 'color_rules'
                if key in DEFAULT_CONFIG["features"].get(feature_name, {}) or key in ("enabled", "color_rules"):
                    # IMPORTANT: Don't overwrite real values with masked placeholders
                    # If the incoming value is "***" (our masking placeholder) and the field
                    # is a sensitive field, preserve the existing value
                    if key in SENSITIVE_FIELDS and value == "***":
                        # Keep the existing value, don't overwrite with the mask
                        logger.debug(f"Preserving existing value for masked field: {feature_name}.{key}")
                        continue
                    self._config["features"][feature_name][key] = value

            self._save_internal()
        logger.info(f"Feature '{feature_name}' settings updated")
        return True

    def get_general(self) -> dict[str, Any]:
        """Get general configuration."""
        with self._file_lock:
            return self._deep_copy(self._config.get("general", {}))

    def set_general(self, settings: dict[str, Any]) -> bool:
        """Update general configuration.

        Args:
            settings: Partial general settings to update.

        Returns:
            True if settings were saved successfully, False otherwise.
        """
        try:
            with self._file_lock:
                if "general" not in self._config:
                    self._config["general"] = {}

                for key, value in settings.items():
                    if key in DEFAULT_CONFIG.get("general", {}):
                        # Don't overwrite real values with masked placeholders
                        if key in SENSITIVE_FIELDS and value == "***":
                            logger.debug(f"Preserving existing value for masked field: general.{key}")
                            continue
                        self._config["general"][key] = value

                self._save_internal()
            logger.info("General settings updated")
            return True
        except Exception as e:
            logger.error(f"Failed to update general settings: {e}")
            return False

    def get_ai_providers(self) -> dict[str, Any]:
        """Get the AI providers configuration block.

        Returns the full block (enabled flag, providers list, default id).
        Caller is responsible for masking before returning to the API
        (use ``get_ai_providers_masked``).
        """
        with self._file_lock:
            return self._deep_copy(
                self._config.get(
                    "ai_providers",
                    {
                        "enabled": False,
                        "providers": [],
                        "default_provider_id": None,
                    },
                )
            )

    def get_ai_providers_masked(self) -> dict[str, Any]:
        """Get the AI providers config with each provider's api_key masked."""
        return self._mask_sensitive(self.get_ai_providers())

    def get_ai_provider(self, provider_id: str) -> dict[str, Any] | None:
        """Return the unmasked provider dict for ``provider_id``, or None."""
        block = self.get_ai_providers()
        for provider in block.get("providers", []):
            if isinstance(provider, dict) and provider.get("id") == provider_id:
                return provider
        return None

    def set_ai_providers(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Update the AI providers configuration block.

        Accepts a partial dict with any of: ``enabled`` (bool),
        ``providers`` (list of provider dicts), ``default_provider_id``.

        For ``providers``, the list replaces the stored list, but for any
        provider whose ``api_key`` field is the mask placeholder ``"***"``
        we look up the existing provider with the same ``id`` and
        preserve its real key (matching the behavior used elsewhere for
        masked sensitive fields).

        Returns the updated, masked config block.
        """
        with self._file_lock:
            existing = self._config.setdefault(
                "ai_providers",
                {"enabled": False, "providers": [], "default_provider_id": None},
            )
            existing_by_id = {
                p.get("id"): p for p in existing.get("providers", []) if isinstance(p, dict) and p.get("id")
            }

            if "enabled" in settings:
                existing["enabled"] = bool(settings["enabled"])

            if "default_provider_id" in settings:
                value = settings["default_provider_id"]
                existing["default_provider_id"] = value if value else None

            if "providers" in settings and isinstance(settings["providers"], list):
                cleaned: list[dict[str, Any]] = []
                for raw in settings["providers"]:
                    if not isinstance(raw, dict):
                        continue
                    provider = self._deep_copy(raw)
                    pid = provider.get("id")
                    # Preserve api_key if the incoming value is the mask
                    if provider.get("api_key") == "***" and pid in existing_by_id:
                        provider["api_key"] = existing_by_id[pid].get("api_key", "")
                    cleaned.append(provider)
                existing["providers"] = cleaned

            self._save_internal()

        logger.info("AI providers settings updated")
        return self.get_ai_providers_masked()

    def get_color_rules(self, feature_name: str, field_name: str) -> list:
        """Get color rules for a specific feature field.

        Args:
            feature_name: Name of the feature (e.g., 'weather').
            field_name: Name of the field (e.g., 'temp').

        Returns:
            List of color rule dicts, or empty list if none defined.
        """
        feature = self.get_feature(feature_name)
        if not feature:
            return []

        color_rules = feature.get("color_rules", {})
        return color_rules.get(field_name, [])

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the current configuration.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []
        config = self.get_all()

        # Validate board settings (support both old and new key names)
        board = config.get("board") or config.get("board_legacy", {})
        api_mode = board.get("api_mode", "local")

        if api_mode == "cloud":
            if not board.get("cloud_key"):
                errors.append("Board cloud_key is required when api_mode is 'cloud'")
        else:
            if not board.get("local_api_key"):
                errors.append("Board local_api_key is required when api_mode is 'local'")
            if not board.get("host"):
                errors.append("Board host is required when api_mode is 'local'")

        # If the legacy board config is empty but any board instance configured
        # via the multi-board settings service has connection credentials, the
        # service can start fine — _build_board_clients() prefers settings.boards
        # over Config when present. Without this, users who set up their board
        # through Settings (rather than the first-run wizard) get stuck in a
        # startup retry loop with the legacy-config validation errors above,
        # even though the UI's /config/validate endpoint considers them
        # configured. (issue #1102)
        if errors and self._has_configured_board_instance():
            board_error_prefixes = ("Board cloud_key", "Board local_api_key", "Board host")
            errors = [e for e in errors if not e.startswith(board_error_prefixes)]

        return (len(errors) == 0, errors)

    @staticmethod
    def _has_configured_board_instance() -> bool:
        """Return True if any board in the multi-board settings service has connection creds."""
        try:
            from .devices import BoardInstance
            from .settings.service import get_settings_service

            board_settings = get_settings_service().get_board_settings()
        except Exception:
            return False

        for board_dict in board_settings.boards or []:
            try:
                instance = BoardInstance.from_dict(board_dict)
            except Exception:
                continue
            if instance.is_connection_configured:
                return True
        return False

    @staticmethod
    def _needs_utc_migration(start_time: Any, end_time: Any) -> bool:
        """True when a window pair is still in the legacy local "HH:MM" format.

        Old format: "20:00" (5 chars). New format: "20:00+00:00" (11 chars).
        """
        return (
            isinstance(start_time, str)
            and isinstance(end_time, str)
            and len(start_time) == 5
            and ":" in start_time
            and len(end_time) == 5
            and ":" in end_time
        )

    def migrate_silence_schedule_to_utc(self) -> bool:
        """Migrate silence_schedule times from old HH:MM format to UTC ISO format.

        This method detects if a silence window is using the old local time format
        (e.g., "20:00") and converts it to the new UTC ISO format (e.g., "04:00+00:00").

        Held under ``_file_lock`` — the lock that guards config data — for the
        whole read-modify-write.  It previously took the class-level ``_lock``,
        which only guards singleton construction: that both left the migration's
        read racing other config writers and stalled every thread calling
        ``ConfigManager()`` for the duration of the disk I/O (#1746).

        The 5-char heuristic is applied **per window** — to the install-wide
        default and to every ``by_board`` entry independently (issue #1788).
        Applying it once for the whole feature would strand every per-board
        window in local time as soon as the global one had been migrated.

        Idempotent: a window already in UTC ISO format is left untouched.

        Returns:
            True if any window was migrated, False if no migration was needed.
        """
        with self._file_lock:
            silence_config = self.get_feature("silence_schedule")
            by_board = silence_config.get("by_board")
            if not isinstance(by_board, dict):
                by_board = {}

            global_needs = self._needs_utc_migration(
                silence_config.get("start_time", ""), silence_config.get("end_time", "")
            )
            board_needs = [
                board_id
                for board_id, entry in by_board.items()
                if isinstance(entry, dict)
                and self._needs_utc_migration(entry.get("start_time", ""), entry.get("end_time", ""))
            ]

            if not global_needs and not board_needs:
                logger.debug("Silence schedule already in UTC format, no migration needed")
                return False

            # Get timezone for conversion (try general.timezone first, then datetime.timezone)
            general_config = self.get_general()
            timezone = general_config.get("timezone")

            if not timezone:
                # Fall back to the legacy date_time feature timezone, read raw
                # from whatever is still stored in an old config file. This is
                # an upgrade path: the features.* blocks are retired (#1761)
                # but a pre-migration install may still carry the value.
                legacy_datetime = self._config.get("features", {}).get("date_time") or {}
                timezone = legacy_datetime.get("timezone", "America/Los_Angeles")

            logger.info(f"Migrating silence schedule from local time to UTC using timezone: {timezone}")

            time_service = get_time_service()

            if global_needs:
                start_time = silence_config["start_time"]
                end_time = silence_config["end_time"]
                silence_config["start_time"] = time_service.local_to_utc_iso(start_time, timezone)
                silence_config["end_time"] = time_service.local_to_utc_iso(end_time, timezone)
                logger.info(
                    "Migrating install-wide silence window: %s → %s, %s → %s",
                    start_time,
                    silence_config["start_time"],
                    end_time,
                    silence_config["end_time"],
                )

            for board_id in board_needs:
                entry = by_board[board_id]
                entry["start_time"] = time_service.local_to_utc_iso(entry["start_time"], timezone)
                entry["end_time"] = time_service.local_to_utc_iso(entry["end_time"], timezone)
            if board_needs:
                silence_config["by_board"] = by_board
                logger.info("Migrated %d per-board silence window(s) to UTC", len(board_needs))

            success = self.set_feature("silence_schedule", silence_config)

            if success:
                logger.info("Successfully migrated silence schedule to UTC")
            else:
                logger.error("Failed to save migrated silence schedule")

            return success

    def set_silence_schedule_for_board(self, board_id: str, values: dict[str, Any]) -> bool:
        """Write one board's silence-schedule override (issue #1788).

        Only ``features.silence_schedule.by_board[board_id]`` is touched — the
        install-wide default (the top-level keys) is left alone so other boards
        keep resolving to it.

        Args:
            board_id: Board whose override to write.
            values: Full or partial dict of the seven silence keys.

        Returns:
            True if the write was persisted.
        """
        with self._file_lock:
            features = self._config.setdefault("features", {})
            silence = features.setdefault(
                "silence_schedule", self._deep_copy(DEFAULT_CONFIG["features"]["silence_schedule"])
            )
            by_board = silence.get("by_board")
            if not isinstance(by_board, dict):
                by_board = {}
            entry = dict(by_board.get(board_id) or {}) if isinstance(by_board.get(board_id), dict) else {}
            entry.update({k: v for k, v in values.items() if k in SILENCE_SCHEDULE_KEYS})
            by_board[board_id] = entry
            silence["by_board"] = by_board
            self._save_internal()
        logger.info("Silence schedule for board %s updated", board_id)
        return True

    def prune_silence_schedule_for_board(self, board_id: str) -> bool:
        """Drop one board's silence-schedule override (issue #1788 review).

        Used in two places:

        * ``SettingsService.remove_board`` — a removed board must not leave an
          orphan entry behind. Harmless on its own (``resolve_silence_schedule``
          falls back cleanly for an unknown id) but the orphans accumulate.
        * The install-wide write path — see
          ``PUT /settings/silence-schedule``. A single-board install has no
          meaningful distinction between "the install default" and "this
          board", so a lingering override there can only shadow the value the
          user just saved.

        Returns:
            True if an entry was removed (and the config resaved).
        """
        with self._file_lock:
            silence = self._config.get("features", {}).get("silence_schedule")
            if not isinstance(silence, dict):
                return False
            by_board = silence.get("by_board")
            if not isinstance(by_board, dict) or board_id not in by_board:
                return False
            by_board.pop(board_id)
            # Keep the on-disk snapshot in step so the structural migration
            # guard still sees this install as migrated.
            raw = self._raw_features.get("silence_schedule")
            if isinstance(raw, dict) and isinstance(raw.get("by_board"), dict):
                raw["by_board"].pop(board_id, None)
            self._save_internal()
        logger.info("Pruned silence schedule override for board %s", board_id)
        return True

    def migrate_silence_schedule_to_per_board(self) -> int:
        """Seed per-board silence overrides from the install-wide values (issue #1788).

        Before #1788 the silence schedule was a single global window. On the
        first boot after upgrading, every configured board is given an explicit
        copy of it so nothing changes behaviourally.

        ``config.json`` has no integer schema_version runner, so the guard is
        structural and reads ``self._raw_features`` — the features section as it
        existed **on disk before** the defaults merge (which would otherwise
        supply an empty ``by_board`` and make every install look migrated). A
        ``by_board`` key in the stored file means this install has already been
        migrated. That cannot double-apply, and it also means a user who
        deliberately deletes a board's override does not get it silently
        re-seeded on the next boot (the resolution rule already falls back to
        the install-wide values for them).

        Returns:
            Number of boards seeded (0 when nothing needed migrating).
        """
        # Resolve the board list BEFORE taking the file lock. ``_file_lock`` is
        # a plain (non-reentrant) ``threading.Lock`` and
        # ``get_settings_service()`` constructs a ``SettingsService`` whose
        # ``__init__`` reads ``FB_TRANSITION_STRATEGY`` ->
        # ``Config._get_board()`` -> ``ConfigManager.get_board()``, which takes
        # that same lock. Calling it from inside the ``with`` block deadlocks
        # the whole process: the lock is never released, so every config read
        # blocks forever with no exception and no timeout. Every production
        # caller happens to warm the settings service first, which is the only
        # reason this was latent rather than a hang on boot.
        board_ids = self._configured_board_ids()

        with self._file_lock:
            stored = self._raw_features.get("silence_schedule")
            if isinstance(stored, dict) and isinstance(stored.get("by_board"), dict):
                logger.debug("Silence schedule already per-board, no migration needed")
                return 0

            features = self._config.setdefault("features", {})
            silence = features.setdefault(
                "silence_schedule", self._deep_copy(DEFAULT_CONFIG["features"]["silence_schedule"])
            )
            legacy = {k: silence[k] for k in SILENCE_SCHEDULE_KEYS if k in silence}
            silence["by_board"] = {board_id: dict(legacy) for board_id in board_ids}
            # Mark the stored snapshot as migrated too, so a second call in the
            # same process short-circuits without re-reading the file.
            self._raw_features.setdefault("silence_schedule", {})["by_board"] = self._deep_copy(silence["by_board"])
            self._save_internal()

        if board_ids:
            logger.info(
                "Migrated silence schedule to per-board: seeded %d board(s) from the install-wide window",
                len(board_ids),
            )
        else:
            logger.info("Migrated silence schedule to per-board: seeded 0 board(s) (none configured)")
        return len(board_ids)

    @staticmethod
    def _configured_board_ids() -> list[str]:
        """Board ids from the multi-board settings service (empty on any failure)."""
        try:
            from .settings.service import get_settings_service

            boards = get_settings_service().get_board_settings().boards or []
        except Exception:  # pragma: no cover - defensive: never break boot
            logger.warning("Could not read board settings for silence migration", exc_info=True)
            return []
        return [str(b["id"]) for b in boards if isinstance(b, dict) and b.get("id")]

    # ==================== Plugin Configuration Methods ====================

    @staticmethod
    def _plugin_env_overrides(plugin_id: str) -> dict[str, Any]:
        """Current env-var overrides for one plugin (issue #1761).

        Computed from ``os.environ`` on every call so that unsetting a
        variable immediately reverts reads to the stored value. Instance
        keys (``weather:sf``) resolve to their base plugin id.
        """
        base_id = plugin_id.split(":", 1)[0]
        overrides: dict[str, Any] = {}
        for env_var, (target_id, key, parse) in ENV_PLUGIN_OVERRIDES.items():
            if target_id != base_id:
                continue
            raw = os.getenv(env_var, "").strip()
            if not raw:
                continue
            if ConfigManager._is_placeholder(raw):
                logger.debug(f"Ignoring placeholder value for {env_var}")
                continue
            try:
                overrides[key] = parse(raw)
            except (ValueError, json.JSONDecodeError):
                logger.warning(f"Invalid {env_var} value: {raw!r} — ignoring override")
        return overrides

    def get_plugin_config(self, plugin_id: str, include_env_overrides: bool = True) -> dict[str, Any] | None:
        """Get configuration for a specific plugin.

        Environment-variable overrides (:data:`ENV_PLUGIN_OVERRIDES`) are
        layered on top of the stored values at read time — they are never
        persisted, and disappear as soon as the variable is unset. Callers
        on a read-merge-write path (un-masking "***" against stored config,
        or persisting a merged config) must pass
        ``include_env_overrides=False`` so an env secret can never leak
        into ``config.json``.

        Args:
            plugin_id: Plugin identifier (e.g., 'weather', 'stocks').
            include_env_overrides: Layer current env-var overrides over the
                stored values (default True — what plugins should run with).

        Returns:
            Plugin configuration dict or None if not found.
        """
        with self._file_lock:
            plugins = self._config.get("plugins", {})
            if plugin_id not in plugins:
                return None
            config = self._deep_copy(plugins[plugin_id])
        if include_env_overrides:
            config.update(self._plugin_env_overrides(plugin_id))
        return config

    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> bool:
        """Set configuration for a specific plugin.

        Args:
            plugin_id: Plugin identifier.
            config: Full plugin configuration (replaces existing).

        Returns:
            True if successful.
        """
        with self._file_lock:
            if "plugins" not in self._config:
                self._config["plugins"] = {}

            # Preserve sensitive fields if they're masked
            existing = self._config["plugins"].get(plugin_id, {})
            config.update(unmask_sensitive_values(config, existing))

            self._config["plugins"][plugin_id] = config
            self._save_internal()

        logger.info(f"Plugin '{plugin_id}' configuration updated")
        return True

    def update_plugin_config(self, plugin_id: str, updates: dict[str, Any]) -> bool:
        """Update specific fields in a plugin's configuration.

        Args:
            plugin_id: Plugin identifier.
            updates: Partial configuration to merge.

        Returns:
            True if successful.
        """
        with self._file_lock:
            if "plugins" not in self._config:
                self._config["plugins"] = {}

            if plugin_id not in self._config["plugins"]:
                self._config["plugins"][plugin_id] = {}

            # Merge updates, restoring masked sensitive fields from what is
            # already stored. Shares unmask_sensitive_values with
            # set_plugin_config: a flat top-level check here would go on
            # persisting "***" over secrets nested in dicts and lists, which is
            # exactly the drift that produced #1743.
            existing = self._config["plugins"][plugin_id]
            existing.update(unmask_sensitive_values(updates, existing))

            self._save_internal()

        logger.debug(f"Plugin '{plugin_id}' configuration updated")
        return True

    def is_plugin_enabled(self, plugin_id: str) -> bool:
        """Check if a plugin is enabled.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            True if plugin is enabled, False otherwise.
        """
        config = self.get_plugin_config(plugin_id)
        if config:
            return config.get("enabled", False)
        return False

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            True if successful.
        """
        return self.update_plugin_config(plugin_id, {"enabled": True})

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin.

        Args:
            plugin_id: Plugin identifier.

        Returns:
            True if successful.
        """
        return self.update_plugin_config(plugin_id, {"enabled": False})

    def get_all_plugin_configs(self, include_env_overrides: bool = True) -> dict[str, dict[str, Any]]:
        """Get all plugin configurations.

        Environment-variable overrides are layered over each stored entry at
        read time (see :meth:`get_plugin_config`); the overlay never adds
        entries for plugins that have no stored config.

        Args:
            include_env_overrides: Layer current env-var overrides over the
                stored values (default True).

        Returns:
            Dict mapping plugin_id to configuration.
        """
        with self._file_lock:
            configs = self._deep_copy(self._config.get("plugins", {}))
        if include_env_overrides:
            for plugin_id, config in configs.items():
                if isinstance(config, dict):
                    config.update(self._plugin_env_overrides(plugin_id))
        return configs

    def get_all_plugin_configs_masked(self) -> dict[str, dict[str, Any]]:
        """Get all plugin configurations with sensitive fields masked.

        Returns:
            Dict mapping plugin_id to masked configuration.
        """
        configs = self.get_all_plugin_configs()
        return self._mask_sensitive(configs)

    def delete_plugin_config(self, plugin_id: str) -> bool:
        """Delete configuration for a specific plugin.

        Removes the plugin entry from the plugins section and saves.

        Args:
            plugin_id: Plugin identifier (e.g., 'weather:sf').

        Returns:
            True if an entry was removed, False if not found.
        """
        with self._file_lock:
            plugins = self._config.get("plugins", {})
            if plugin_id not in plugins:
                logger.debug(f"No config entry to delete for plugin '{plugin_id}'")
                return False
            del plugins[plugin_id]
            self._save_internal()

        logger.info(f"Plugin '{plugin_id}' configuration deleted")
        return True

    def get_enabled_plugins(self) -> list[str]:
        """Get list of enabled plugin IDs.

        Returns:
            List of plugin IDs that are enabled.
        """
        enabled = []
        for plugin_id, config in self.get_all_plugin_configs().items():
            if config.get("enabled", False):
                enabled.append(plugin_id)
        return enabled

    # ── plugin-migration bookkeeping (issue #937) ─────────────────────────────
    #
    # The v2→v3 migration that auto-installs orphaned external plugins must run
    # exactly once per install. Without this flag every boot would treat a
    # user-uninstalled plugin as orphaned and silently re-clone it, producing
    # the "sticky plugin" bug reported in #937.

    def is_v2_plugin_migration_done(self) -> bool:
        """Return True once the v2→v3 plugin migration has run on this install."""
        with self._file_lock:
            return bool(self._config.get("plugin_migrations", {}).get("v2_completed", False))

    def mark_v2_plugin_migration_done(self) -> None:
        """Persist that the v2→v3 plugin migration has run, so it does not run
        again on subsequent boots."""
        with self._file_lock:
            migrations = self._config.setdefault("plugin_migrations", {})
            if migrations.get("v2_completed") is True:
                return
            migrations["v2_completed"] = True
            self._save_internal()
        logger.info("v2 plugin migration marked as complete")

    # ── per-plugin retry list (issue #948) ────────────────────────────────────
    #
    # If the v2→v3 auto-install fails for a specific plugin (e.g. transient
    # network during the git clone), we record its id here. On the next boot
    # the migration retries JUST those ids — provided the user still has a
    # matching stored config. This keeps the #937 "don't resurrect deliberately
    # uninstalled plugins" invariant intact while letting a flaky first boot
    # recover instead of permanently stranding the user.

    def get_v2_plugin_failed_installs(self) -> list[str]:
        """Return the list of plugin ids that failed to install on a previous
        v2→v3 migration run."""
        with self._file_lock:
            raw = self._config.get("plugin_migrations", {}).get("v2_failed_installs")
            if not isinstance(raw, list):
                return []
            # Defensive filter: only return non-empty string ids.
            return [pid for pid in raw if isinstance(pid, str) and pid]

    def set_v2_plugin_failed_installs(self, plugin_ids: list[str]) -> None:
        """Persist the list of plugin ids that should be retried on the next boot.

        Passing an empty list clears the retry queue.
        """
        with self._file_lock:
            migrations = self._config.setdefault("plugin_migrations", {})
            current = migrations.get("v2_failed_installs") or []
            normalized = sorted({pid for pid in plugin_ids if isinstance(pid, str) and pid})
            if current == normalized:
                return
            if normalized:
                migrations["v2_failed_installs"] = normalized
            else:
                migrations.pop("v2_failed_installs", None)
            self._save_internal()
        if normalized:
            logger.info("v2 plugin migration: queued %d id(s) for retry: %s", len(normalized), normalized)
        else:
            logger.info("v2 plugin migration: retry queue cleared")

    def clear_v2_plugin_failed_installs(self) -> None:
        """Drop any persisted retry queue. Equivalent to ``set_v2_plugin_failed_installs([])``."""
        self.set_v2_plugin_failed_installs([])

    # ── deliberate-removal tombstones (issue #1394) ───────────────────────────
    #
    # When the user uninstalls a plugin (or deletes a named instance) we record
    # its id in a persistent top-level ``removed_plugins`` list. The post-upgrade
    # auto-restore and the v2→v3 reconcile consult this list so a pre-update
    # snapshot or an orphaned config entry can never resurrect something the
    # user deliberately removed. The tombstone is cleared when the user
    # explicitly reinstalls the plugin (or re-creates the instance).
    #
    # Compound instance keys use the ``base:label`` form (see
    # ``src.plugins.registry.INSTANCE_SEPARATOR``); a base-plugin tombstone
    # covers all of its instances.

    def get_removed_plugins(self) -> list[str]:
        """Return the list of deliberately removed plugin ids (tombstones)."""
        with self._file_lock:
            raw = self._config.get("removed_plugins")
            if not isinstance(raw, list):
                return []
            return [pid for pid in raw if isinstance(pid, str) and pid]

    def is_plugin_removed(self, plugin_id: str) -> bool:
        """Return True when *plugin_id* — or, for an instance key like
        ``weather:sf``, its base plugin — was deliberately removed."""
        removed = set(self.get_removed_plugins())
        if plugin_id in removed:
            return True
        base = plugin_id.split(":", 1)[0]
        return base != plugin_id and base in removed

    def mark_plugin_removed(self, plugin_id: str) -> None:
        """Persist a deliberate-removal tombstone for *plugin_id*."""
        if not isinstance(plugin_id, str) or not plugin_id:
            return
        with self._file_lock:
            current = self._config.get("removed_plugins")
            current = [pid for pid in current if isinstance(pid, str) and pid] if isinstance(current, list) else []
            if plugin_id in current:
                return
            self._config["removed_plugins"] = sorted({*current, plugin_id})
            self._save_internal()
        logger.info("Plugin '%s' tombstoned as deliberately removed", plugin_id)

    def clear_plugin_removed(self, plugin_id: str) -> None:
        """Drop the tombstone for *plugin_id*.

        For a base plugin id this also drops tombstones of its named
        instances (``plugin_id:*``), since reinstalling the base is the
        explicit user action that makes those ids installable again.
        """
        with self._file_lock:
            current = self._config.get("removed_plugins")
            if not isinstance(current, list):
                return
            prefix = f"{plugin_id}:"
            kept = [
                pid
                for pid in current
                if isinstance(pid, str) and pid and pid != plugin_id and not pid.startswith(prefix)
            ]
            if kept == current:
                return
            if kept:
                self._config["removed_plugins"] = kept
            else:
                self._config.pop("removed_plugins", None)
            self._save_internal()
        logger.info("Cleared deliberate-removal tombstone for plugin '%s'", plugin_id)


# Global instance getter
def get_config_manager() -> ConfigManager:
    """Get the singleton ConfigManager instance."""
    return ConfigManager()
