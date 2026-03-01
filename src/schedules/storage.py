"""JSON file-based storage for schedule entries.

Provides simple persistence for schedule configurations that survives restarts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .models import ScheduleEntry, DEFAULT_BOARD_ID

logger = logging.getLogger(__name__)


class ScheduleStorage:
    """JSON file-based storage for schedule entries.
    
    Stores schedules and default page configuration in a JSON file for
    simple persistence. Thread-safe for basic operations.
    """
    
    def __init__(self, storage_file: Optional[str] = None):
        """Initialize schedule storage.
        
        Args:
            storage_file: Path to JSON storage file. Defaults to data/schedules.json
        """
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "schedules.json"
        else:
            self.storage_file = Path(storage_file)
        
        # In-memory cache
        self._schedules: Dict[str, ScheduleEntry] = {}
        self._default_page_id: Optional[str] = None  # legacy single default
        self._default_page_by_board: Dict[str, str] = {}  # board_id -> page_id

        # Load existing schedules
        self._load()
        
        logger.info(
            f"ScheduleStorage initialized "
            f"(file: {self.storage_file}, schedules: {len(self._schedules)})"
        )
    
    def _load(self) -> None:
        """Load schedules from storage file."""
        if not self.storage_file.exists():
            self._schedules = {}
            self._default_page_id = None
            self._default_page_by_board = {}
            return

        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)

            self._schedules = {}
            for schedule_data in data.get("schedules", []):
                try:
                    if "board_id" not in schedule_data:
                        schedule_data["board_id"] = DEFAULT_BOARD_ID
                    if "created_at" in schedule_data and isinstance(schedule_data["created_at"], str):
                        schedule_data["created_at"] = datetime.fromisoformat(schedule_data["created_at"])
                    if "updated_at" in schedule_data and isinstance(schedule_data["updated_at"], str):
                        schedule_data["updated_at"] = datetime.fromisoformat(schedule_data["updated_at"])

                    schedule = ScheduleEntry(**schedule_data)
                    self._schedules[schedule.id] = schedule
                except Exception as e:
                    logger.warning(f"Failed to load schedule: {e}")

            self._default_page_id = data.get("default_page_id")
            self._default_page_by_board = dict(data.get("default_page_by_board") or {})

            logger.info(f"Loaded {len(self._schedules)} schedules from storage")

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load schedules file: {e}")
            self._schedules = {}
            self._default_page_id = None
            self._default_page_by_board = {}
    
    def _save(self) -> None:
        """Save schedules to storage file."""
        try:
            data = {
                "schedules": [schedule.model_dump() for schedule in self._schedules.values()],
                "default_page_id": self._default_page_id,
                "default_page_by_board": self._default_page_by_board,
            }
            
            # Convert datetime objects to ISO strings for JSON serialization
            for schedule_data in data["schedules"]:
                if schedule_data.get("created_at"):
                    schedule_data["created_at"] = schedule_data["created_at"].isoformat()
                if schedule_data.get("updated_at"):
                    schedule_data["updated_at"] = schedule_data["updated_at"].isoformat()
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self._schedules)} schedules to storage")
            
        except IOError as e:
            logger.error(f"Failed to save schedules file: {e}")
            raise
    
    def list_all(self, board_id: Optional[str] = None) -> List[ScheduleEntry]:
        """Get stored schedules, optionally filtered by board_id.
        
        Args:
            board_id: Filter by board_id. None returns default board schedules.
                     Use explicit "*" to get ALL schedules across all boards (for cleanup/admin).

        Returns:
            List of schedules (for board_id if given), ordered by created_at
        """
        if board_id == "*":
            # Return all schedules across all boards
            schedules = list(self._schedules.values())
        else:
            bid = board_id if board_id is not None else DEFAULT_BOARD_ID
            schedules = [s for s in self._schedules.values() if (s.board_id or DEFAULT_BOARD_ID) == (bid or DEFAULT_BOARD_ID)]
        schedules.sort(key=lambda s: s.created_at)
        return schedules
    
    def get(self, schedule_id: str) -> Optional[ScheduleEntry]:
        """Get a schedule by ID.
        
        Args:
            schedule_id: The schedule ID
            
        Returns:
            ScheduleEntry if found, None otherwise
        """
        return self._schedules.get(schedule_id)
    
    def create(self, schedule: ScheduleEntry) -> ScheduleEntry:
        """Create a new schedule entry."""
        if schedule.id in self._schedules:
            raise ValueError(f"Schedule with ID {schedule.id} already exists")
        if not schedule.board_id:
            schedule.board_id = DEFAULT_BOARD_ID
        errors = schedule.validate_config()
        if errors:
            raise ValueError(f"Invalid schedule configuration: {errors}")
        self._schedules[schedule.id] = schedule
        self._save()
        logger.info(f"Created schedule: {schedule.id} (board_id={schedule.board_id})")
        return schedule
    
    def update(self, schedule_id: str, updates: dict) -> Optional[ScheduleEntry]:
        """Update an existing schedule.
        
        Args:
            schedule_id: The schedule ID
            updates: Dictionary of fields to update
            
        Returns:
            Updated schedule if found, None otherwise
        """
        if schedule_id not in self._schedules:
            return None
        
        schedule = self._schedules[schedule_id]
        
        # Apply updates
        schedule_dict = schedule.model_dump()
        for key, value in updates.items():
            if value is not None and key in schedule_dict:
                schedule_dict[key] = value
        
        # Update timestamp
        schedule_dict["updated_at"] = datetime.now(timezone.utc)
        
        # Recreate schedule with updates
        updated_schedule = ScheduleEntry(**schedule_dict)
        
        # Validate
        errors = updated_schedule.validate_config()
        if errors:
            raise ValueError(f"Invalid schedule configuration: {errors}")
        
        self._schedules[schedule_id] = updated_schedule
        self._save()
        
        logger.info(f"Updated schedule: {schedule_id}")
        return updated_schedule
    
    def delete(self, schedule_id: str) -> bool:
        """Delete a schedule.
        
        Args:
            schedule_id: The schedule ID
            
        Returns:
            True if deleted, False if not found
        """
        if schedule_id not in self._schedules:
            return False
        
        del self._schedules[schedule_id]
        self._save()
        
        logger.info(f"Deleted schedule: {schedule_id}")
        return True
    
    def exists(self, schedule_id: str) -> bool:
        """Check if a schedule exists.
        
        Args:
            schedule_id: The schedule ID
            
        Returns:
            True if exists
        """
        return schedule_id in self._schedules
    
    def count(self) -> int:
        """Get the number of stored schedules."""
        return len(self._schedules)
    
    def get_default_page_id(self, board_id: Optional[str] = None) -> Optional[str]:
        """Get the default page ID for schedule gaps for the given board."""
        bid = board_id or DEFAULT_BOARD_ID
        if bid in self._default_page_by_board:
            return self._default_page_by_board[bid] or None
        return self._default_page_id

    def set_default_page_id(self, page_id: Optional[str], board_id: Optional[str] = None) -> None:
        """Set the default page ID for schedule gaps for the given board."""
        bid = board_id or DEFAULT_BOARD_ID
        if bid == DEFAULT_BOARD_ID:
            self._default_page_id = page_id
        if page_id:
            self._default_page_by_board[bid] = page_id
        else:
            self._default_page_by_board.pop(bid, None)
            if bid == DEFAULT_BOARD_ID:
                self._default_page_id = None
        self._save()
        logger.info(f"Set default page ID for board {bid!r} to: {page_id}")
