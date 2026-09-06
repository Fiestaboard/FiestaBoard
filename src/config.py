"""Configuration management for FiestaBoard Display Service.

This module provides the Config class which reads settings from the
ConfigManager (JSON file-based storage).
"""

import logging

from .config_manager import get_config_manager

logger = logging.getLogger(__name__)

# Silence-schedule keys a per-board override may carry (issue #1788).
_SILENCE_KEYS = (
    "enabled",
    "start_time",
    "end_time",
    "mode",
    "page_id",
    "indicator_text",
    "indicator_position",
)

SILENCE_INDICATOR_POSITIONS = ("center", "top-left", "top-right", "bottom-left", "bottom-right")
SILENCE_MODES = ("indicator", "freeze", "page")


def resolve_silence_schedule(feature: dict | None, board_id: str | None = None) -> dict:
    """Resolve a ``silence_schedule`` feature dict for one board (issue #1788).

    Shared by :meth:`Config.silence_config_for` and the ``/silence-status``
    endpoint so both apply exactly the same layering and normalization.

    Args:
        feature: The raw ``features.silence_schedule`` dict (may be None).
        board_id: Board to resolve, or None for the install-wide layer.

    Returns:
        A normalized dict with exactly the seven silence keys — never
        ``by_board``.
    """
    feature = feature or {}
    layer = dict(feature)
    layer.pop("by_board", None)

    if board_id:
        by_board = feature.get("by_board")
        if isinstance(by_board, dict):
            entry = by_board.get(board_id)
            if isinstance(entry, dict):
                layer.update({k: v for k, v in entry.items() if k in _SILENCE_KEYS})

    mode = layer.get("mode", "freeze")
    if mode not in SILENCE_MODES:
        mode = "freeze"

    page_id = layer.get("page_id")
    if not (isinstance(page_id, str) and page_id.strip()):
        page_id = None

    text = layer.get("indicator_text", "SNOOZING")
    indicator_text = text.strip().upper() if isinstance(text, str) and text.strip() else "SNOOZING"

    position = layer.get("indicator_position", "center")
    if position not in SILENCE_INDICATOR_POSITIONS:
        position = "center"

    return {
        "enabled": bool(layer.get("enabled", False)),
        "start_time": layer.get("start_time", "20:00"),
        "end_time": layer.get("end_time", "07:00"),
        "mode": mode,
        "page_id": page_id,
        "indicator_text": indicator_text,
        "indicator_position": position,
    }


class classproperty:
    """Descriptor that acts like @property but on the class itself.

    Python 3.13 removed support for stacking @classmethod on @property.
    This descriptor provides the same behavior.
    """

    def __init__(self, func):
        self.func = func

    def __get__(self, obj, objtype=None):
        return self.func(objtype)


class Config:
    """Application configuration loaded from config.json file.

    This class provides class attributes for accessing configuration values.
    Values are read from the ConfigManager which persists to config.json.
    """

    # Valid transition strategies
    VALID_TRANSITION_STRATEGIES = ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

    @classmethod
    def _get_cm(cls):
        """Get the config manager instance."""
        return get_config_manager()

    @classmethod
    def _get_board(cls) -> dict:
        """Get board config section."""
        return cls._get_cm().get_board()

    @classmethod
    def _get_feature(cls, name: str) -> dict:
        """Get a feature config section."""
        return cls._get_cm().get_feature(name) or {}

    @classmethod
    def _get_general(cls) -> dict:
        """Get general config section."""
        return cls._get_cm().get_general()

    # ==================== Board API Configuration ====================

    @classproperty
    def BOARD_API_MODE(cls) -> str:
        """API mode: 'local' or 'cloud'."""
        return cls._get_board().get("api_mode", "local")

    @classproperty
    def BOARD_LOCAL_API_KEY(cls) -> str:
        """Local API key."""
        return cls._get_board().get("local_api_key", "")

    @classproperty
    def BOARD_READ_WRITE_KEY(cls) -> str:
        """Cloud API read/write key."""
        return cls._get_board().get("cloud_key", "")

    @classproperty
    def BOARD_HOST(cls) -> str:
        """Board host address."""
        return cls._get_board().get("host", "")

    @classproperty
    def BOARD_TRANSITION_STRATEGY(cls) -> str | None:
        """Transition animation strategy."""
        return cls._get_board().get("transition_strategy")

    @classproperty
    def BOARD_TRANSITION_INTERVAL_MS(cls) -> int | None:
        """Transition step interval in milliseconds."""
        return cls._get_board().get("transition_interval_ms")

    @classproperty
    def BOARD_TRANSITION_STEP_SIZE(cls) -> int | None:
        """Transition step size."""
        return cls._get_board().get("transition_step_size")

    @classmethod
    def get_board_api_key(cls) -> str:
        """Get the appropriate API key based on mode."""
        if cls.BOARD_API_MODE.lower() == "cloud":
            return cls.BOARD_READ_WRITE_KEY
        return cls.BOARD_LOCAL_API_KEY

    # Backward compatibility aliases
    @classproperty
    def FB_API_MODE(cls) -> str:
        return cls.BOARD_API_MODE

    @classproperty
    def FB_LOCAL_API_KEY(cls) -> str:
        return cls.BOARD_LOCAL_API_KEY

    @classproperty
    def FB_READ_WRITE_KEY(cls) -> str:
        return cls.BOARD_READ_WRITE_KEY

    @classproperty
    def FB_HOST(cls) -> str:
        return cls.BOARD_HOST

    @classproperty
    def FB_TRANSITION_STRATEGY(cls) -> str | None:
        return cls.BOARD_TRANSITION_STRATEGY

    @classproperty
    def FB_TRANSITION_INTERVAL_MS(cls) -> int | None:
        return cls.BOARD_TRANSITION_INTERVAL_MS

    @classproperty
    def FB_TRANSITION_STEP_SIZE(cls) -> int | None:
        return cls.BOARD_TRANSITION_STEP_SIZE

    @classmethod
    def get_vb_api_key(cls) -> str:
        return cls.get_board_api_key()

    # ==================== Output Configuration ====================

    @classproperty
    def OUTPUT_TARGET(cls) -> str:
        """Output target: 'ui', 'board', or 'both'."""
        return cls._get_general().get("output_target", "board")

    # ==================== General Configuration ====================

    @classproperty
    def GENERAL_TIMEZONE(cls) -> str:
        """General timezone configuration (used as default for all time displays)."""
        return cls._get_general().get("timezone", "")

    @classproperty
    def REFRESH_INTERVAL_SECONDS(cls) -> int:
        """Refresh interval in seconds."""
        return cls._get_general().get("refresh_interval_seconds", 300)

    # ==================== Silence Schedule Configuration ====================

    @classmethod
    def silence_config_for(cls, board_id: str | None = None) -> dict:
        """Resolve the effective silence schedule for one board (issue #1788).

        Silence settings are stored per board under
        ``features.silence_schedule.by_board[board_id]``; the top-level keys of
        the feature are the **install-wide default**.

        Resolution rule: a board's own entry wins key-by-key; anything it does
        not define — including a board with no entry at all — falls back to the
        install-wide values. This deliberately differs from
        :class:`~src.settings.service.ActivePageSettings`, where the legacy
        mirror is only consulted for the *primary* board. Here a newly added
        board should inherit the install's quiet hours rather than be
        unexpectedly loud at 3am.

        Args:
            board_id: Board to resolve. ``None`` returns the install-wide layer
                (what the seven ``SILENCE_SCHEDULE_*`` classproperties read).

        Returns:
            A normalized dict with exactly the seven silence keys. Never
            contains ``by_board``.
        """
        return resolve_silence_schedule(cls._get_feature("silence_schedule"), board_id)

    @classproperty
    def SILENCE_SCHEDULE_ENABLED(cls) -> bool:
        """Whether the install-wide silence schedule is enabled."""
        return cls.silence_config_for()["enabled"]

    @classproperty
    def SILENCE_SCHEDULE_START_TIME(cls) -> str:
        """Install-wide silence schedule start time (HH:MM format)."""
        return cls.silence_config_for()["start_time"]

    @classproperty
    def SILENCE_SCHEDULE_END_TIME(cls) -> str:
        """Install-wide silence schedule end time (HH:MM format)."""
        return cls.silence_config_for()["end_time"]

    @classproperty
    def SILENCE_SCHEDULE_MODE(cls) -> str:
        """Silence behaviour: 'freeze' (default), 'indicator', or 'page'."""
        return cls.silence_config_for()["mode"]

    @classproperty
    def SILENCE_SCHEDULE_PAGE_ID(cls):
        """Page id to display when SILENCE_SCHEDULE_MODE == 'page'."""
        return cls.silence_config_for()["page_id"]

    @classproperty
    def SILENCE_SCHEDULE_INDICATOR_TEXT(cls) -> str:
        """Custom text to display when SILENCE_SCHEDULE_MODE == 'indicator'. Defaults to 'SNOOZING'."""
        return cls.silence_config_for()["indicator_text"]

    @classproperty
    def SILENCE_SCHEDULE_INDICATOR_POSITION(cls) -> str:
        """Position of indicator text: 'center' (default), 'top-left', 'top-right', 'bottom-left', 'bottom-right'."""
        return cls.silence_config_for()["indicator_position"]

    @classmethod
    def is_silence_mode_active(cls, board_id: str | None = None) -> bool:
        """Check if a board is currently in silence mode.

        Uses TimeService to check if current UTC time is within that board's
        configured silence window. Times are stored in UTC ISO format.

        Args:
            board_id: Board to check. ``None`` keeps the legacy meaning — the
                install-wide window — so existing zero-arg callers (MQTT state,
                the AI chat surfaces, manual-send guards) are unchanged.

        Returns:
            True if silence is enabled for that board and the current time is
            within its silence window.
        """
        silence = cls.silence_config_for(board_id)
        if not silence["enabled"]:
            return False

        try:
            # Trigger migration if needed (on first call)
            from .config_manager import get_config_manager

            config_manager = get_config_manager()
            # Seed per-board overrides first (issue #1788) so the UTC migration
            # below converts them in the same pass. Both are cheap no-ops once
            # they have run.
            config_manager.migrate_silence_schedule_to_per_board()
            config_manager.migrate_silence_schedule_to_utc()

            # Re-resolve: the migration may have rewritten the window in place.
            silence = cls.silence_config_for(board_id)

            # Use TimeService to check if we're in the window
            from .time_service import get_time_service

            time_service = get_time_service()

            return time_service.is_time_in_window(silence["start_time"], silence["end_time"])

        except (ValueError, AttributeError) as e:
            logger.warning(f"Invalid silence schedule time format: {e}")
            return False

    # ==================== Helper Methods ====================

    @classmethod
    def get_transition_settings(cls) -> dict:
        """Get current transition settings."""
        return {
            "strategy": cls.FB_TRANSITION_STRATEGY,
            "step_interval_ms": cls.FB_TRANSITION_INTERVAL_MS,
            "step_size": cls.FB_TRANSITION_STEP_SIZE,
        }

    @classmethod
    def reload(cls) -> None:
        """Reload configuration from file."""
        cls._get_cm().reload()
        logger.info("Configuration reloaded")

    @classmethod
    def validate(cls) -> bool:
        """Validate that required configuration is present."""
        is_valid, errors = cls._get_cm().validate()

        if not is_valid:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.info("Configuration validated successfully")
        return True

    @classmethod
    def get_summary(cls) -> dict:
        """Get a summary of configuration (without sensitive keys).

        Since #1761 the per-integration values come from the plugin system
        (``plugins.*``), not the retired legacy ``features.*`` blocks. The
        key set is unchanged so existing consumers keep working; the
        ``*_enabled`` flags now report plugin enablement.

        Since #1760 the board connection fields report the primary settings
        board — the connection the runtime actually uses — not the vestigial
        config.json board block.
        """
        cm = cls._get_cm()
        weather = cm.get_plugin_config("weather") or {}
        board = cls._primary_settings_board()
        board_api_mode = (board.get("api_mode") or "local").lower() if board else "local"
        return {
            "weather_provider": weather.get("provider", "weatherapi"),
            "weather_location": weather.get("location", ""),
            "timezone": cls.GENERAL_TIMEZONE,
            "refresh_interval_seconds": cls.REFRESH_INTERVAL_SECONDS,
            # Service enabled flags (for UI display)
            "datetime_enabled": cm.is_plugin_enabled("date_time"),
            "weather_enabled": cm.is_plugin_enabled("weather") and bool(weather.get("api_key")),
            "guest_wifi_enabled": cm.is_plugin_enabled("guest_wifi"),
            "home_assistant_enabled": cm.is_plugin_enabled("home_assistant"),
            "star_trek_quotes_enabled": cm.is_plugin_enabled("star_trek_quotes"),
            "air_fog_enabled": cm.is_plugin_enabled("air_fog"),
            "muni_enabled": cm.is_plugin_enabled("muni"),
            "surf_enabled": cm.is_plugin_enabled("surf"),
            "baywheels_enabled": cm.is_plugin_enabled("lyft_bike_share"),
            "traffic_enabled": cm.is_plugin_enabled("traffic"),
            "stocks_enabled": cm.is_plugin_enabled("stocks"),
            # Board config (from the primary settings board, issue #1760)
            "board_api_mode": board_api_mode,
            "board_host": (board.get("host") or "") if board_api_mode == "local" else "cloud",
            "board_key_set": bool(board.get("cloud_key") if board_api_mode == "cloud" else board.get("local_api_key")),
            "weather_key_set": bool(weather.get("api_key")),
            # Transition settings (only available in Local API mode)
            "transition_strategy": cls.BOARD_TRANSITION_STRATEGY if board_api_mode == "local" else None,
            "transition_interval_ms": cls.BOARD_TRANSITION_INTERVAL_MS if board_api_mode == "local" else None,
            "transition_step_size": cls.BOARD_TRANSITION_STEP_SIZE if board_api_mode == "local" else None,
        }

    @staticmethod
    def _primary_settings_board() -> dict:
        """Connection fields of the primary settings board (issue #1760).

        Board credentials are unified on settings.json; summaries must report
        the connection the runtime actually uses, not the vestigial
        config.json board block. Returns {} when the settings service is
        unavailable (early startup, broken store).
        """
        try:
            from .settings.service import get_settings_service

            boards = get_settings_service().get_board_settings().boards or []
            if boards and isinstance(boards[0], dict):
                return boards[0]
        except Exception:  # pragma: no cover - defensive
            pass
        return {}
