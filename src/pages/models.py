"""Data models for pages and layouts.

Pages can be:
- Single: Display a single source type
- Composite: Combine rows from multiple sources
- Template: Custom templated content with dynamic data
"""

from datetime import datetime, timezone
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict
import uuid

from ..devices import DeviceType, get_dimensions, DEFAULT_DEVICE_TYPE


PageType = Literal["single", "composite", "template"]

LineAlignment = Literal["left", "center", "right"]


class LineMetadata(BaseModel):
    """Per-line formatting metadata for template pages.

    Stores alignment and wrap settings that were previously encoded as
    inline prefixes ({center}, {wrap}, etc.) in the template strings.
    """
    alignment: LineAlignment = "left"
    wrap: bool = False


class RowConfig(BaseModel):
    """Configuration for a single row in a composite page.
    
    Specifies which row from which source should be placed at which position.
    Row limits depend on the device type of the parent page.
    """
    source: str  # Display type (weather, datetime, etc.)
    row_index: int = Field(ge=0)  # Which row from source
    target_row: int = Field(ge=0)  # Where to place in output


class Page(BaseModel):
    """A saved page configuration.
    
    Pages can be one of three types:
    - single: Displays a single source type
    - composite: Combines specific rows from multiple sources
    - template: Custom content with templated variables
    
    Each page targets a specific device type (flagship: 22x6, note: 15x3).
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=100)
    type: PageType
    
    # Device type: "flagship" (22x6) or "note" (15x3)
    device_type: DeviceType = Field(default=DEFAULT_DEVICE_TYPE)
    
    # For single pages: which display type to show
    display_type: Optional[str] = None
    
    # For composite pages: row configuration
    rows: Optional[List[RowConfig]] = None
    
    # For template pages: lines of template text (pure content, no alignment prefixes)
    # Templates can include {{variable}} syntax for dynamic data
    # and {color} syntax for board colors
    template: Optional[List[str]] = None

    # Per-line formatting metadata (alignment, wrap) for template pages
    line_metadata: Optional[List[LineMetadata]] = None
    
    # Rotation settings
    duration_seconds: int = Field(default=300, ge=10, le=3600)  # 10s to 1h
    
    # Transition settings (per-page override, None means use system defaults)
    # Valid strategies: column, reverse-column, edges-to-center, row, diagonal, random
    transition_strategy: Optional[str] = None
    transition_interval_ms: Optional[int] = Field(default=None, ge=0, le=5000)
    transition_step_size: Optional[int] = Field(default=None, ge=1)
    
    # Plugin demo page tracking (singleton per plugin)
    demo_plugin_id: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        # Pydantic V2 uses serialization_mode_json for custom serializers
        # datetime is automatically serialized to ISO format in V2
    )
    
    def validate_config(self) -> List[str]:
        """Validate that page configuration is complete and consistent.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        dims = get_dimensions(self.device_type)
        max_row = dims.rows - 1
        
        if self.type == "single":
            if not self.display_type:
                errors.append("Single page requires display_type")
        
        elif self.type == "composite":
            if not self.rows or len(self.rows) == 0:
                errors.append("Composite page requires at least one row config")
            else:
                # Check for duplicate target rows
                target_rows = [r.target_row for r in self.rows]
                if len(target_rows) != len(set(target_rows)):
                    errors.append("Composite page has duplicate target rows")
                # Check row indices are within device limits
                for r in self.rows:
                    if r.row_index > max_row:
                        errors.append(f"Row index {r.row_index} exceeds max {max_row} for {self.device_type}")
                    if r.target_row > max_row:
                        errors.append(f"Target row {r.target_row} exceeds max {max_row} for {self.device_type}")
        
        elif self.type == "template":
            if not self.template or len(self.template) == 0:
                errors.append("Template page requires template content")
        
        return errors
    
    def is_valid(self) -> bool:
        """Check if page configuration is valid."""
        return len(self.validate_config()) == 0


class PageCreate(BaseModel):
    """Request model for creating a new page."""
    name: str = Field(min_length=1, max_length=100)
    type: PageType
    device_type: DeviceType = Field(default=DEFAULT_DEVICE_TYPE)
    display_type: Optional[str] = None
    rows: Optional[List[RowConfig]] = None
    template: Optional[List[str]] = None
    line_metadata: Optional[List[LineMetadata]] = None
    duration_seconds: int = Field(default=300, ge=10, le=3600)
    # Transition settings (per-page override)
    transition_strategy: Optional[str] = None
    transition_interval_ms: Optional[int] = Field(default=None, ge=0, le=5000)
    transition_step_size: Optional[int] = Field(default=None, ge=1)
    # Plugin demo page tracking
    demo_plugin_id: Optional[str] = None


class PageUpdate(BaseModel):
    """Request model for updating an existing page."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    display_type: Optional[str] = None
    rows: Optional[List[RowConfig]] = None
    template: Optional[List[str]] = None
    line_metadata: Optional[List[LineMetadata]] = None
    duration_seconds: Optional[int] = Field(default=None, ge=10, le=3600)
    # Transition settings (per-page override, use ... sentinel to leave unchanged)
    transition_strategy: Optional[str] = None
    transition_interval_ms: Optional[int] = Field(default=None, ge=0, le=5000)
    transition_step_size: Optional[int] = Field(default=None, ge=1)

