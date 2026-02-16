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
    interval_seconds: int = 60  # Default to 60 seconds (1 minute)
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "PollingSettings":
        interval = data.get("interval_seconds", 60)
        # Ensure minimum of 10 seconds to avoid overloading
        if interval < 10:
            interval = 10
        return cls(interval_seconds=interval)


@dataclass
class BoardSettings:
    """Board display settings for UI rendering."""
    board_type: Optional[Literal["black", "white"]] = "black"
    devices: List[str] = field(default_factory=lambda: ["flagship"])
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "BoardSettings":
        board_type = data.get("board_type", "black")
        # Validate board type
        if board_type not in ["black", "white", None]:
            board_type = "black"
        devices = data.get("devices", ["flagship"])
        # Validate devices
        from ..devices import DEVICE_TYPES
        valid_devices = [d for d in devices if d in DEVICE_TYPES]
        if not valid_devices:
            valid_devices = ["flagship"]
        return cls(board_type=board_type, devices=valid_devices)


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
                "board": self._board.to_dict(),
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
        """Load board settings from file."""
        file_data = self._load_from_file()
        if "board" in file_data:
            return BoardSettings.from_dict(file_data["board"])
        return BoardSettings()  # Default to black board
    
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
        """Set the configured device types.
        
        Args:
            devices: List of device type strings (e.g. ["flagship", "note"])
            
        Returns:
            Updated BoardSettings
        """
        from ..devices import DEVICE_TYPES
        valid_devices = [d for d in devices if d in DEVICE_TYPES]
        if not valid_devices:
            raise ValueError(f"At least one valid device required. Valid types: {DEVICE_TYPES}")
        
        self._board.devices = valid_devices
        self._save_to_file()
        logger.info(f"Configured devices set to: {valid_devices}")
        return self._board
    
    # Schedule settings
    def get_schedule_settings(self) -> ScheduleSettings:
        """Get current schedule settings.
        
        Returns:
            ScheduleSettings instance
        """
        return self._schedule
    
    def is_schedule_enabled(self) -> bool:
        """Check if schedule mode is enabled.
        
        Returns:
            True if schedule mode is active
        """
        return self._schedule.enabled
    
    def set_schedule_enabled(self, enabled: bool) -> ScheduleSettings:
        """Enable or disable schedule mode.
        
        When enabled, the system uses time-based schedules to determine
        which page to display. When disabled, the manual active_page is used.
        
        Args:
            enabled: True to enable schedule mode, False for manual mode
            
        Returns:
            Updated ScheduleSettings
        """
        self._schedule.enabled = enabled
        self._save_to_file()
        mode = "enabled" if enabled else "disabled"
        logger.info(f"Schedule mode {mode}")
        return self._schedule


# Singleton instance
_settings_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get or create the settings service singleton."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service

