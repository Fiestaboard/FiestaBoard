"""Settings service for managing runtime configuration.

This service allows runtime modification of settings like transition
animations and output targets, which can be controlled from the UI.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from typing import Optional, Literal, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Valid values
VALID_STRATEGIES = [
    "column", "reverse-column", "edges-to-center",
    "row", "diagonal", "random"
]
VALID_OUTPUT_TARGETS = ["ui", "board", "both"]

OutputTarget = Literal["ui", "board", "both"]
TransitionStrategy = Literal[
    "column", "reverse-column", "edges-to-center",
    "row", "diagonal", "random"
]


@dataclass
class TransitionSettings:
    """Transition animation settings."""
    strategy: Optional[str] = None
    step_interval_ms: Optional[int] = None
    step_size: Optional[int] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "TransitionSettings":
        return cls(
            strategy=data.get("strategy"),
            step_interval_ms=data.get("step_interval_ms"),
            step_size=data.get("step_size")
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
    """Active page settings for display."""
    page_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ActivePageSettings":
        return cls(page_id=data.get("page_id"))


@dataclass
class PollingSettings:
    """Polling interval settings for board updates."""
    interval_seconds: int = 30  # Default to 30 seconds
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PollingSettings":
        interval = data.get("interval_seconds", 30)
        # Ensure minimum of 10 seconds to avoid overloading
        if interval < 10:
            interval = 10
        return cls(interval_seconds=interval)


BOARD_SENSITIVE_FIELDS = {"local_api_key", "cloud_key"}


@dataclass
class BoardSettings:
    """Board display settings for UI rendering.
    
    Supports multiple board instances, each with its own device type,
    board color, and connection settings. The `devices` property provides
    backward-compatible access to the list of unique device types.
    """
    board_type: Optional[Literal["black", "white"]] = "black"
    boards: List[dict] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.boards:
            from ..devices import BoardInstance
            self.boards = [BoardInstance(
                name="My Board",
                device_type="flagship",
                board_color=self.board_type or "black",
            ).to_dict()]
    
    @property
    def devices(self) -> List[str]:
        """Backward-compatible list of unique device types across all boards."""
        from ..devices import DEVICE_TYPES
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
            from ..devices import BoardInstance
            devices = data["devices"]
            if isinstance(devices, list):
                for i, dt in enumerate(devices):
                    name = "My Board" if i == 0 else f"My Board {i + 1}"
                    boards.append(BoardInstance(
                        name=name,
                        device_type=dt,
                        board_color=board_type or "black",
                    ).to_dict())
        
        return cls(board_type=board_type, boards=boards)


@dataclass
class ScheduleSettings:
    """Schedule system settings."""
    enabled: bool = False  # Schedule mode disabled by default
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScheduleSettings":
        return cls(enabled=data.get("enabled", False))


class SettingsService:
    """Service for managing runtime settings.
    
    Settings can be modified at runtime via the API and are persisted
    to a JSON file so they survive restarts.
    """
    
    def __init__(self, settings_file: Optional[str] = None):
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
        
        # Load initial settings from env/file
        self._transition = self._load_transition_settings()
        self._output = self._load_output_settings()
        self._active_page = self._load_active_page_settings()
        self._polling = self._load_polling_settings()
        self._board = self._load_board_settings()
        self._schedule = self._load_schedule_settings()
        
        if getattr(self, "_needs_migration_save", False):
            self._save_to_file()
            self._needs_migration_save = False
        
        logger.info(f"SettingsService initialized (file: {self.settings_file})")
    
    def _load_from_file(self) -> dict:
        """Load settings from JSON file."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load settings file: {e}")
        return {}
    
    def _save_to_file(self) -> None:
        """Save current settings to JSON file."""
        try:
            data = {
                "transitions": self._transition.to_dict(),
                "output": self._output.to_dict(),
                "active_page": self._active_page.to_dict(),
                "polling": self._polling.to_dict(),
                "board": self._board.to_dict(mask_secrets=False),
                "schedule": self._schedule.to_dict()
            }
            with open(self.settings_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.debug("Settings saved to file")
        except IOError as e:
            logger.error(f"Failed to save settings file: {e}")
    
    def _load_transition_settings(self) -> TransitionSettings:
        """Load transition settings from file or env."""
        # Try file first
        file_data = self._load_from_file()
        if "transitions" in file_data:
            return TransitionSettings.from_dict(file_data["transitions"])
        
        # Fall back to env
        from ..config import Config
        return TransitionSettings(
            strategy=Config.FB_TRANSITION_STRATEGY,
            step_interval_ms=Config.FB_TRANSITION_INTERVAL_MS,
            step_size=Config.FB_TRANSITION_STEP_SIZE
        )
    
    def _load_output_settings(self) -> OutputSettings:
        """Load output settings from file or env."""
        # Try file first
        file_data = self._load_from_file()
        if "output" in file_data:
            return OutputSettings.from_dict(file_data["output"])
        
        # Fall back to env
        from ..config import Config
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
            from ..config_manager import get_config_manager
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
        return ScheduleSettings()  # Default to disabled
    
    # Transition settings
    def get_transition_settings(self) -> TransitionSettings:
        """Get current transition settings."""
        return self._transition
    
    def update_transition_settings(
        self,
        strategy: Optional[str] = ...,
        step_interval_ms: Optional[int] = ...,
        step_size: Optional[int] = ...
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
    
    def should_send_to_board(self, dev_mode: bool = False) -> bool:
        """Determine if message should be sent to board.
        
        Args:
            dev_mode: Whether dev mode is enabled
            
        Returns:
            True if message should be sent to board
        """
        if dev_mode:
            # In dev mode, only send if target is "both"
            return self._output.target == "both"
        else:
            # In prod mode, send unless target is "ui"
            return self._output.target in ["board", "both"]
    
    def should_send_to_ui(self, dev_mode: bool = False) -> bool:
        """Determine if message should be sent to UI.
        
        Args:
            dev_mode: Whether dev mode is enabled
            
        Returns:
            True if message should be sent to UI (always True for preview)
        """
        # UI preview is always available
        return True
    
    # Active page settings
    def get_active_page_id(self) -> Optional[str]:
        """Get the currently active page ID.
        
        Returns:
            Active page ID or None if not set
        """
        return self._active_page.page_id
    
    def set_active_page_id(self, page_id: Optional[str]) -> ActivePageSettings:
        """Set the active page ID.
        
        Args:
            page_id: Page ID to set as active, or None to clear
            
        Returns:
            Updated ActivePageSettings
        """
        self._active_page.page_id = page_id
        self._save_to_file()
        logger.info(f"Active page set to: {page_id}")
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
    
    def set_board_type(self, board_type: Optional[Literal["black", "white"]]) -> BoardSettings:
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
    
    def set_devices(self, devices: List[str]) -> BoardSettings:
        """Set the configured device types (backward-compatible).
        
        Creates/updates board instances to match the desired device type list.
        Preserves existing board instances where possible.
        
        Args:
            devices: List of device type strings (e.g. ["flagship", "note"])
            
        Returns:
            Updated BoardSettings
        """
        from ..devices import DEVICE_TYPES, BoardInstance
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
                new_boards.append(BoardInstance(
                    name=name,
                    device_type=dt,
                    board_color=self._board.board_type or "black",
                ).to_dict())
        
        self._board.boards = new_boards
        self._save_to_file()
        logger.info(f"Configured devices set to: {valid_devices}")
        return self._board
    
    def set_boards(self, boards: List[dict]) -> BoardSettings:
        """Set the configured board instances.
        
        Each board must have at least a device_type. 
        ID and name are auto-generated if not provided.
        Masked sensitive fields ("***") are preserved from existing data.
        
        Args:
            boards: List of board instance dicts
            
        Returns:
            Updated BoardSettings
        """
        from ..devices import BoardInstance
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
        from ..devices import BoardInstance
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
    
    # Schedule settings
    def get_schedule_settings(self) -> ScheduleSettings:
        """Get current schedule settings.
        
        Returns:
            ScheduleSettings instance
        """
        return self._schedule
    
    def is_schedule_enabled(self, board_id: Optional[str] = None) -> bool:
        """Check if schedule mode is enabled for a board.

        When board_id is None, returns the first board's schedule_enabled, or global setting if no boards.
        """
        if board_id:
            for b in self._board.boards:
                if b.get("id") == board_id:
                    return b.get("schedule_enabled", False)
            return False
        if self._board.boards:
            return self._board.boards[0].get("schedule_enabled", self._schedule.enabled)
        return self._schedule.enabled

    def set_schedule_enabled(self, enabled: bool, board_id: Optional[str] = None) -> ScheduleSettings:
        """Enable or disable schedule mode for a board (or globally when board_id is None)."""
        if board_id:
            for b in self._board.boards:
                if b.get("id") == board_id:
                    b["schedule_enabled"] = enabled
                    self._save_to_file()
                    logger.info(f"Schedule mode for board {board_id}: {'enabled' if enabled else 'disabled'}")
                    return self._schedule
            logger.warning(f"Board {board_id} not found for set_schedule_enabled")
            return self._schedule
        self._schedule.enabled = enabled
        if self._board.boards:
            self._board.boards[0]["schedule_enabled"] = enabled
        self._save_to_file()
        logger.info(f"Schedule mode (default): {'enabled' if enabled else 'disabled'}")
        return self._schedule


# Singleton instance
_settings_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get or create the settings service singleton."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service

