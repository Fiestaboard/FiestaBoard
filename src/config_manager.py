"""Configuration file manager for FiestaBoard Display Service.

Manages reading and writing configuration to a JSON file with validation
and thread-safe file operations.

Supports:
- Legacy features (config.features.*) for backward compatibility
- Plugin system (config.plugins.*) for data source integrations
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import TimeService for migration
from .time_service import get_time_service

logger = logging.getLogger(__name__)

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
PLUGIN_ID_RENAMES: Dict[str, str] = {
    # v2.0.0 of the bike share plugin generalised to all Lyft-operated
    # GBFS systems (Bay Wheels, CitiBike, Capital Bikeshare, Biketown,
    # Divvy, ...) and renamed the plugin id.
    "baywheels": "lyft_bike_share",
}

# Per-rename adjustments to the migrated settings dict. Each handler
# receives a deep-copied settings dict and returns the adjusted dict
# that will be written under the new plugin id. Used to drop fields
# that no longer exist in the new manifest and seed new defaults.
def _adjust_baywheels_to_lyft_bike_share(cfg: Dict[str, Any]) -> Dict[str, Any]:
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


PLUGIN_RENAME_ADJUSTERS: Dict[str, Any] = {
    "baywheels": _adjust_baywheels_to_lyft_bike_share,
}

# Default configuration schema
DEFAULT_CONFIG: Dict[str, Any] = {
    "board": {
        "api_mode": "local",
        "local_api_key": "",
        "cloud_key": "",
        "host": "",
        "transition_strategy": None,
        "transition_interval_ms": None,
        "transition_step_size": None,
    },
    "features": {
        "weather": {
            "enabled": False,
            "api_key": "",
            "provider": "weatherapi",
            "location": "San Francisco, CA",
            "refresh_seconds": 300,  # 5 minutes - weather doesn't change fast
            "color_rules": {
                # Temperature color rules: prepend color tile based on value
                "temp": [
                    {"condition": ">=", "value": 90, "color": "red"},
                    {"condition": ">=", "value": 80, "color": "orange"},
                    {"condition": ">=", "value": 70, "color": "yellow"},
                    {"condition": ">=", "value": 60, "color": "green"},
                    {"condition": ">=", "value": 45, "color": "blue"},
                    {"condition": "<", "value": 45, "color": "violet"},
                ],
            },
        },
        "date_time": {
            "enabled": True,
            "timezone": "America/Los_Angeles",
            # No refresh_seconds - always current
            "color_rules": {},
        },
        "home_assistant": {
            "enabled": False,
            "base_url": "",
            "access_token": "",
            "entities": [],
            "timeout": 5,
            "refresh_seconds": 30,  # 30 seconds for home status
            "color_rules": {
                # Entity state colors: shows status at a glance
                "state": [
                    {"condition": "==", "value": "on", "color": "red"},
                    {"condition": "==", "value": "open", "color": "red"},
                    {"condition": "==", "value": "unlocked", "color": "red"},
                    {"condition": "==", "value": "off", "color": "green"},
                    {"condition": "==", "value": "closed", "color": "green"},
                    {"condition": "==", "value": "locked", "color": "green"},
                ],
            },
        },
        "guest_wifi": {
            "enabled": False,
            "ssid": "",
            "password": "",
            # No refresh_seconds - static data
            "color_rules": {},
        },
        "star_trek_quotes": {
            "enabled": False,
            "ratio": "3:5:9",
            # No refresh_seconds - changes per rotation
            "color_rules": {
                # Series colors match the show themes
                "series": [
                    {"condition": "==", "value": "TNG", "color": "yellow"},
                    {"condition": "==", "value": "VOY", "color": "blue"},
                    {"condition": "==", "value": "DS9", "color": "red"},
                ],
            },
        },
        "air_fog": {
            "enabled": False,
            "purpleair_api_key": "",  # PurpleAir API key
            "openweathermap_api_key": "",  # OpenWeatherMap API key
            "purpleair_sensor_id": "",  # Optional specific sensor ID
            "latitude": 37.7749,  # San Francisco
            "longitude": -122.4194,  # San Francisco
            "refresh_seconds": 600,  # 10 minutes
            "color_rules": {
                "air_status": [
                    {"condition": "==", "value": "GOOD", "color": "green"},
                    {"condition": "==", "value": "MODERATE", "color": "yellow"},
                    {"condition": "==", "value": "UNHEALTHY_SENSITIVE", "color": "orange"},
                    {"condition": "==", "value": "UNHEALTHY", "color": "red"},
                ],
            },
        },
        "muni": {
            "enabled": False,
            "api_key": "",  # 511.org API key
            "stop_code": "",  # Muni stop code (e.g., "15726") - backward compatibility
            "stop_codes": [],  # List of stop codes to monitor (up to 4)
            "stop_names": [],  # List of stop names for display
            "line_name": "",  # Optional line filter (e.g., "N" for N-Judah)
            "refresh_seconds": 60,  # 1 minute for transit data
            "transit_cache_enabled": True,  # Enable regional transit cache
            "transit_cache_refresh_seconds": 90,  # Refresh regional cache every 90 seconds
            "color_rules": {},
        },
        "surf": {
            "enabled": False,
            "latitude": 37.7599,  # Ocean Beach, SF
            "longitude": -122.5121,  # Ocean Beach, SF
            "refresh_seconds": 1800,  # 30 minutes for surf conditions
            "color_rules": {
                "quality": [
                    {"condition": "==", "value": "EXCELLENT", "color": "green"},
                    {"condition": "==", "value": "GOOD", "color": "yellow"},
                    {"condition": "==", "value": "FAIR", "color": "orange"},
                    {"condition": "==", "value": "POOR", "color": "red"},
                ],
            },
        },
        "baywheels": {
            "enabled": False,
            "station_id": "",  # Bay Wheels/GBFS station ID (backward compatibility)
            "station_ids": [],  # List of station IDs to monitor (up to 4)
            "station_name": "",  # Display name for the station (backward compatibility)
            "refresh_seconds": 60,  # 1 minute for bike availability
            "color_rules": {
                # Status colors based on electric bike availability
                "electric_bikes": [
                    {"condition": "<", "value": 2, "color": "red"},
                    {"condition": "<=", "value": 5, "color": "yellow"},
                    {"condition": ">", "value": 5, "color": "green"},
                ],
            },
        },
        "traffic": {
            "enabled": False,
            "api_key": "",  # Google Routes API key (using api_key for consistency)
            "origin": "",  # Origin address or lat,lng - backward compatibility
            "destination": "",  # Destination address or lat,lng - backward compatibility
            "destination_name": "DOWNTOWN",  # Display name for destination - backward compatibility
            "routes": [],  # List of route dicts: [{origin, destination, destination_name}]
            "refresh_seconds": 300,  # 5 minutes
            "color_rules": {
                "traffic_status": [
                    {"condition": "==", "value": "LIGHT", "color": "green"},
                    {"condition": "==", "value": "MODERATE", "color": "yellow"},
                    {"condition": "==", "value": "HEAVY", "color": "red"},
                ],
            },
        },
        "silence_schedule": {
            "enabled": False,
            "start_time": "20:00",  # 8pm (will be migrated to UTC ISO format)
            "end_time": "07:00",  # 7am (will be migrated to UTC ISO format)
            # Behavior while silence is active:
            #   "indicator" - clear the board and show "SNOOZING" centered (default)
            #   "freeze"    - leave whatever is currently on the board, stop updating
            #   "page"      - render the chosen page once, then stop updating
            "mode": "indicator",
            # Page id to display when mode == "page" (variables are frozen at silence-start)
            "page_id": None,
        },
        "stocks": {
            "enabled": False,
            "finnhub_api_key": "",  # Optional - enables better symbol search/autocomplete
            "symbols": ["GOOG"],  # List of stock symbols (max 5)
            "time_window": "1 Day",  # Options: "1 Day", "5 Days", "1 Month", "3 Months", "6 Months", "1 Year", "2 Years", "5 Years", "ALL"
            "refresh_seconds": 300,  # 5 minutes default
            "color_rules": {
                "change_percent": [
                    {"condition": ">", "value": 0, "color": "green"},  # Positive = green
                    {"condition": "<", "value": 0, "color": "red"},   # Negative = red
                ],
            },
        },
    },
    "general": {
        "timezone": "America/Los_Angeles",  # User's timezone for display purposes
        "refresh_interval_seconds": 300,
        "output_target": "board",
        "instance_name": "",       # Friendly name for this FiestaBoard install
        "time_format": "12h",      # "12h" or "24h" for web UI time display
        "date_format": "MM/DD/YYYY",  # "MM/DD/YYYY", "DD/MM/YYYY", or "YYYY-MM-DD"
        "welcome_message": "",     # Custom board greeting; empty = use default
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
    "access_token",
    "password",
    "finnhub_api_key",
    "purpleair_api_key",
    "openweathermap_api_key",
    "client_id",
    "client_secret",
}


class ConfigManager:
    """Manages configuration file read/write operations."""

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __new__(cls, config_path: Optional[str] = None) -> "ConfigManager":
        """Singleton pattern to ensure only one config manager exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[str] = None) -> None:
        """Initialize the config manager.
        
        Args:
            config_path: Path to the config file. Defaults to config.json in project root.
        """
        if self._initialized:
            return

        self._file_lock = threading.Lock()
        
        # Determine config file path
        if config_path:
            self._config_path = Path(config_path)
        else:
            # Default to data directory
            data_dir = Path(__file__).parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            self._config_path = data_dir / "config.json"
        
        self._config: Dict[str, Any] = {}
        self._raw_features: Dict[str, Any] = {}
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
                    with open(self._config_path, "r") as f:
                        self._config = json.load(f)
                    logger.info(f"Loaded config from {self._config_path}")
                    
                    # Snapshot features actually present before merge fills in defaults
                    self._raw_features = self._deep_copy(
                        self._config.get("features", {})
                    )
                    
                    # Merge with defaults to handle missing keys
                    self._config = self._merge_with_defaults(self._config)
                    self._save_internal()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in config file: {e}")
                    logger.info("Creating new config with defaults")
                    self._config = DEFAULT_CONFIG.copy()
                    self._apply_profile_defaults()
                    self._save_internal()
            else:
                logger.info(f"Config file not found, creating defaults at {self._config_path}")
                self._config = self._deep_copy(DEFAULT_CONFIG)
                self._apply_profile_defaults()
                self._save_internal()

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
        elif isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        return obj

    # Fields that should be replaced entirely (not recursively merged)
    REPLACE_FIELDS = {"color_rules"}

    def _merge_with_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge config with defaults to handle missing keys.
        
        Note: Some fields like 'color_rules' are replaced entirely rather than
        recursively merged, so user deletions are preserved.
        """
        result = self._deep_copy(DEFAULT_CONFIG)
        
        def merge(base: Dict, update: Dict, path: str = "") -> Dict:
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

        to_migrate: List[tuple] = []
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
        backup_path = self._config_path.with_suffix(
            f".json.v1_backup"
        )
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
                    k: self._deep_copy(v)
                    for k, v in feature_cfg.items()
                    if k not in MIGRATION_EXCLUDED_FIELDS
                }
                self._config["plugins"][plugin_id] = plugin_cfg
                logger.info(
                    f"Auto-migrated feature '{feature_key}' -> plugin '{plugin_id}'"
                )

            self._save_internal()

        logger.info(
            f"Auto-migration complete: {len(to_migrate)} feature(s) migrated to plugins"
        )

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

        renamed: List[tuple] = []
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
                    f"Plugin rename '{old_id}' -> '{new_id}': new id already "
                    f"present, dropping stale old config"
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

        logger.info(
            f"Plugin rename migration complete: {len(renamed)} plugin(s) processed"
        )

    def _save_internal(self) -> None:
        """Internal save without acquiring lock (called from locked context)."""
        try:
            with open(self._config_path, "w") as f:
                json.dump(self._config, f, indent=2)
            logger.debug(f"Saved config to {self._config_path}")
        except IOError as e:
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
        if v.startswith("your_") or v.startswith("your-"):
            return True
        if v.endswith("_here") or v.endswith("-here"):
            return True
        if v in ("changeme", "replace_me", "replace-me", "example", "placeholder"):
            return True
        return False

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to config.
        
        Only sets values if they're empty in config (allows env vars to provide defaults).
        Environment variables take precedence for initial setup but UI changes are preserved.
        Placeholder values from .env (e.g. ``your_api_key_here``) are ignored.
        """
        changed = False
        
        # Ensure structures exist
        if "board" not in self._config:
            self._config["board"] = {}
        if "features" not in self._config:
            self._config["features"] = {}
        if "general" not in self._config:
            self._config["general"] = {}
        
        # Helper to safely get/create feature config
        def get_feature(name: str) -> dict:
            if name not in self._config["features"]:
                self._config["features"][name] = {}
            return self._config["features"][name]
        
        # Helper to apply string env var
        def apply_str(config: dict, key: str, env_var: str, alt_env_var: str = None) -> bool:
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
        def apply_int(config: dict, key: str, env_var: str, alt_env_var: str = None) -> bool:
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
        
        # Helper to apply float env var
        def apply_float(config: dict, key: str, env_var: str) -> bool:
            value = os.getenv(env_var, "").strip()
            if value and config.get(key) is None:
                try:
                    config[key] = float(value)
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
        changed |= apply_str(board_config, "transition_strategy", "BOARD_TRANSITION_STRATEGY", "FB_TRANSITION_STRATEGY")
        changed |= apply_int(board_config, "transition_interval_ms", "BOARD_TRANSITION_INTERVAL_MS", "FB_TRANSITION_INTERVAL_MS")
        changed |= apply_int(board_config, "transition_step_size", "BOARD_TRANSITION_STEP_SIZE", "FB_TRANSITION_STEP_SIZE")
        
        # ==================== General Configuration ====================
        changed |= apply_str(general_config, "timezone", "TIMEZONE")
        changed |= apply_int(general_config, "refresh_interval_seconds", "REFRESH_INTERVAL_SECONDS")
        changed |= apply_str(general_config, "output_target", "OUTPUT_TARGET")
        
        # Silence schedule start/end times (enabling via env var is no longer supported;
        # use the UI or config.json to set silence_schedule.enabled)
        changed |= apply_str(general_config, "silence_schedule_start_time", "SILENCE_SCHEDULE_START_TIME")
        changed |= apply_str(general_config, "silence_schedule_end_time", "SILENCE_SCHEDULE_END_TIME")
        
        # ==================== Weather Feature ====================
        weather = get_feature("weather")
        changed |= apply_str(weather, "api_key", "WEATHER_API_KEY")
        changed |= apply_str(weather, "provider", "WEATHER_PROVIDER")
        changed |= apply_str(weather, "location", "WEATHER_LOCATION")
        
        # ==================== Guest WiFi Feature ====================
        guest_wifi = get_feature("guest_wifi")
        changed |= apply_str(guest_wifi, "ssid", "GUEST_WIFI_SSID")
        changed |= apply_str(guest_wifi, "password", "GUEST_WIFI_PASSWORD")
        changed |= apply_int(guest_wifi, "refresh_seconds", "GUEST_WIFI_REFRESH_SECONDS")
        
        # ==================== Home Assistant Feature ====================
        home_assistant = get_feature("home_assistant")
        changed |= apply_str(home_assistant, "base_url", "HOME_ASSISTANT_BASE_URL")
        changed |= apply_str(home_assistant, "access_token", "HOME_ASSISTANT_ACCESS_TOKEN")
        changed |= apply_int(home_assistant, "timeout", "HOME_ASSISTANT_TIMEOUT")
        changed |= apply_int(home_assistant, "refresh_seconds", "HOME_ASSISTANT_REFRESH_SECONDS")
        # Handle entities JSON
        entities_str = os.getenv("HOME_ASSISTANT_ENTITIES", "").strip()
        if entities_str and not home_assistant.get("entities"):
            try:
                import json
                home_assistant["entities"] = json.loads(entities_str)
                logger.info("Applied HOME_ASSISTANT_ENTITIES from environment variable")
                changed = True
            except json.JSONDecodeError:
                logger.warning(f"Invalid HOME_ASSISTANT_ENTITIES JSON: {entities_str}")
        
        # ==================== Star Trek Quotes Feature ====================
        star_trek = get_feature("star_trek_quotes")
        changed |= apply_str(star_trek, "ratio", "STAR_TREK_QUOTES_RATIO")
        
        # ==================== Muni Feature ====================
        muni = get_feature("muni")
        changed |= apply_str(muni, "api_key", "MUNI_API_KEY")
        changed |= apply_int(muni, "refresh_seconds", "MUNI_REFRESH_SECONDS")
        
        # ==================== Traffic Feature ====================
        traffic = get_feature("traffic")
        changed |= apply_str(traffic, "api_key", "GOOGLE_ROUTES_API_KEY")
        changed |= apply_int(traffic, "refresh_seconds", "TRAFFIC_REFRESH_SECONDS")
        
        # ==================== Bay Wheels Feature ====================
        baywheels = get_feature("baywheels")
        changed |= apply_int(baywheels, "refresh_seconds", "BAYWHEELS_REFRESH_SECONDS")
        
        # ==================== Surf Feature ====================
        surf = get_feature("surf")
        changed |= apply_float(surf, "latitude", "SURF_LATITUDE")
        changed |= apply_float(surf, "longitude", "SURF_LONGITUDE")
        changed |= apply_int(surf, "refresh_seconds", "SURF_REFRESH_SECONDS")
        
        # ==================== Air/Fog Feature ====================
        air_fog = get_feature("air_fog")
        changed |= apply_str(air_fog, "purpleair_api_key", "PURPLEAIR_API_KEY")
        changed |= apply_str(air_fog, "purpleair_sensor_id", "PURPLEAIR_SENSOR_ID")
        changed |= apply_str(air_fog, "openweathermap_api_key", "OPENWEATHERMAP_API_KEY")
        changed |= apply_float(air_fog, "latitude", "AIR_FOG_LATITUDE")
        changed |= apply_float(air_fog, "longitude", "AIR_FOG_LONGITUDE")
        changed |= apply_int(air_fog, "refresh_seconds", "AIR_FOG_REFRESH_SECONDS")
        
        # ==================== Stocks Feature ====================
        stocks = get_feature("stocks")
        changed |= apply_str(stocks, "finnhub_api_key", "FINNHUB_API_KEY")
        changed |= apply_str(stocks, "time_window", "STOCKS_TIME_WINDOW")
        changed |= apply_int(stocks, "refresh_seconds", "STOCKS_REFRESH_SECONDS")
        # Handle symbols as comma-separated list
        symbols_str = os.getenv("STOCKS_SYMBOLS", "").strip()
        if symbols_str and not stocks.get("symbols"):
            stocks["symbols"] = [s.strip() for s in symbols_str.split(",") if s.strip()]
            logger.info("Applied STOCKS_SYMBOLS from environment variable")
            changed = True
        
        # Save if any changes were made
        if changed:
            with self._file_lock:
                self._save_internal()
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_or_create()
        self._apply_env_overrides()
        logger.info("Configuration reloaded from file")

    def get_all(self) -> Dict[str, Any]:
        """Get full configuration (internal use - includes secrets)."""
        with self._file_lock:
            return self._deep_copy(self._config)

    def get_all_masked(self) -> Dict[str, Any]:
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
        elif isinstance(obj, list):
            return [self._mask_sensitive(item, path) for item in obj]
        return obj

    def get_board(self) -> Dict[str, Any]:
        """Get board configuration."""
        with self._file_lock:
            # Support both old "board_legacy" and new "board" keys for migration
            config = self._config.get("board") or self._config.get("board_legacy", {})
            return self._deep_copy(config)

    def set_board(self, settings: Dict[str, Any]) -> None:
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
    def get_board_legacy(self) -> Dict[str, Any]:
        """Backward compatibility alias for get_board()."""
        return self.get_board()

    def set_board_legacy(self, settings: Dict[str, Any]) -> None:
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
            self._config["board"] = {k: v for k, v in DEFAULT_CONFIG["board"].items()}
            self._save_internal()
        logger.info("Board config reset to defaults (first-run mode, env overrides skipped)")

    def get_feature(self, feature_name: str) -> Optional[Dict[str, Any]]:
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

    def set_feature(self, feature_name: str, settings: Dict[str, Any]) -> bool:
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
                self._config["features"][feature_name] = self._deep_copy(
                    DEFAULT_CONFIG["features"][feature_name]
                )
            
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

    def get_general(self) -> Dict[str, Any]:
        """Get general configuration."""
        with self._file_lock:
            return self._deep_copy(self._config.get("general", {}))

    def set_general(self, settings: Dict[str, Any]) -> bool:
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

    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled.
        
        Args:
            feature_name: Name of the feature.
            
        Returns:
            True if feature is enabled, False otherwise.
        """
        feature = self.get_feature(feature_name)
        if feature:
            return feature.get("enabled", False)
        return False

    def get_feature_list(self) -> list:
        """Get list of all available features."""
        return list(DEFAULT_CONFIG.get("features", {}).keys())

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
        
        # Validate features that are enabled
        features = config.get("features", {})
        
        if features.get("weather", {}).get("enabled"):
            if not features["weather"].get("api_key"):
                errors.append("Weather API key is required when weather is enabled")
        
        if features.get("home_assistant", {}).get("enabled"):
            ha = features["home_assistant"]
            if not ha.get("base_url"):
                errors.append("Home Assistant base_url is required when enabled")
            if not ha.get("access_token"):
                errors.append("Home Assistant access_token is required when enabled")
        
        if features.get("guest_wifi", {}).get("enabled"):
            wifi = features["guest_wifi"]
            if not wifi.get("ssid"):
                errors.append("Guest WiFi SSID is required when enabled")
            if not wifi.get("password"):
                errors.append("Guest WiFi password is required when enabled")
        
        return (len(errors) == 0, errors)
    
    def migrate_silence_schedule_to_utc(self) -> bool:
        """Migrate silence_schedule times from old HH:MM format to UTC ISO format.
        
        This method detects if the silence_schedule is using the old local time format
        (e.g., "20:00") and converts it to the new UTC ISO format (e.g., "04:00+00:00").
        
        Returns:
            True if migration was performed, False if no migration needed
        """
        with self._lock:
            silence_config = self.get_feature("silence_schedule")
            start_time = silence_config.get("start_time", "")
            end_time = silence_config.get("end_time", "")
            
            # Check if migration is needed (old format is just HH:MM, 5 chars)
            if not start_time or not end_time:
                return False
            
            # Old format: "20:00" (5 chars), New format: "20:00-08:00" (11+ chars)
            needs_migration = (len(start_time) == 5 and ":" in start_time and 
                             len(end_time) == 5 and ":" in end_time)
            
            if not needs_migration:
                logger.debug("Silence schedule already in UTC format, no migration needed")
                return False
            
            # Get timezone for conversion (try general.timezone first, then datetime.timezone)
            general_config = self.get_general()
            timezone = general_config.get("timezone")
            
            if not timezone:
                # Fall back to date_time feature timezone
                datetime_config = self.get_feature("date_time")
                timezone = datetime_config.get("timezone", "America/Los_Angeles")
            
            logger.info(f"Migrating silence schedule from local time to UTC using timezone: {timezone}")
            
            # Convert times to UTC
            time_service = get_time_service()
            start_utc = time_service.local_to_utc_iso(start_time, timezone)
            end_utc = time_service.local_to_utc_iso(end_time, timezone)
            
            # Update the config
            silence_config["start_time"] = start_utc
            silence_config["end_time"] = end_utc
            
            success = self.set_feature("silence_schedule", silence_config)
            
            if success:
                logger.info(f"Successfully migrated silence schedule: {start_time} → {start_utc}, {end_time} → {end_utc}")
            else:
                logger.error("Failed to save migrated silence schedule")
            
            return success

    # ==================== Plugin Configuration Methods ====================
    
    def get_plugin_config(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific plugin.
        
        Args:
            plugin_id: Plugin identifier (e.g., 'weather', 'stocks').
            
        Returns:
            Plugin configuration dict or None if not found.
        """
        with self._file_lock:
            plugins = self._config.get("plugins", {})
            if plugin_id in plugins:
                return self._deep_copy(plugins[plugin_id])
            return None
    
    def set_plugin_config(self, plugin_id: str, config: Dict[str, Any]) -> bool:
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
            for key, value in config.items():
                if key in SENSITIVE_FIELDS and value == "***":
                    # Keep existing value
                    config[key] = existing.get(key, "")
            
            self._config["plugins"][plugin_id] = config
            self._save_internal()
        
        logger.info(f"Plugin '{plugin_id}' configuration updated")
        return True
    
    def update_plugin_config(self, plugin_id: str, updates: Dict[str, Any]) -> bool:
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
            
            # Merge updates, preserving masked sensitive fields
            for key, value in updates.items():
                if key in SENSITIVE_FIELDS and value == "***":
                    logger.debug(f"Preserving existing value for masked field: plugins.{plugin_id}.{key}")
                    continue
                self._config["plugins"][plugin_id][key] = value
            
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
    
    def get_all_plugin_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all plugin configurations.
        
        Returns:
            Dict mapping plugin_id to configuration.
        """
        with self._file_lock:
            return self._deep_copy(self._config.get("plugins", {}))
    
    def get_all_plugin_configs_masked(self) -> Dict[str, Dict[str, Any]]:
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

    def get_enabled_plugins(self) -> List[str]:
        """Get list of enabled plugin IDs.
        
        Returns:
            List of plugin IDs that are enabled.
        """
        enabled = []
        for plugin_id, config in self.get_all_plugin_configs().items():
            if config.get("enabled", False):
                enabled.append(plugin_id)
        return enabled
    
    def migrate_feature_to_plugin(self, feature_name: str, plugin_id: str) -> bool:
        """Migrate a legacy feature configuration to plugin format.
        
        This copies the feature configuration to the plugins section,
        mapping field names as needed.
        
        Args:
            feature_name: Name of the legacy feature.
            plugin_id: Target plugin identifier.
            
        Returns:
            True if migration was performed.
        """
        feature_config = self.get_feature(feature_name)
        if not feature_config:
            logger.warning(f"Feature '{feature_name}' not found for migration")
            return False
        
        # Copy to plugins section
        return self.set_plugin_config(plugin_id, feature_config)


# Global instance getter
def get_config_manager() -> ConfigManager:
    """Get the singleton ConfigManager instance."""
    return ConfigManager()

