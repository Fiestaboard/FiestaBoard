"""Data models for collections.

A Collection groups an ordered set of pages and exposes a *selection mode*
that determines which page should be displayed at any given moment.
Collections can be referenced anywhere a page_id is accepted using the
prefixed ID format: ``collection:{uuid}``.

Selection modes:

- ``time``: classic carousel behavior. ``time.interval_seconds`` controls how
  long each page is shown; pages cycle deterministically based on Unix time.
- ``variable``: ordered list of (expression, page_id) rules; the first rule
  whose expression evaluates truthy against the current template context wins.
  Falls back to ``variable.default_page_id`` when no rule matches.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

COLLECTION_ID_PREFIX = "collection:"

SelectionMode = Literal["time", "variable"]


def make_collection_id() -> str:
    """Generate a new collection ID with the standard prefix."""
    return f"{COLLECTION_ID_PREFIX}{uuid.uuid4()}"


def is_collection_id(ref_id: str | None) -> bool:
    """Check whether an ID string refers to a collection."""
    return bool(ref_id) and ref_id.startswith(COLLECTION_ID_PREFIX)


def extract_collection_uuid(collection_id: str) -> str:
    """Strip the prefix and return the bare UUID portion."""
    return collection_id[len(COLLECTION_ID_PREFIX) :]


class TimeModeConfig(BaseModel):
    """Settings for time-based rotation (classic carousel)."""

    interval_seconds: int = Field(default=30, ge=5, le=3600)


class VariableRule(BaseModel):
    """A single (expression, page_id) selection rule.

    The ``expression`` is evaluated by the template expression engine. A
    truthy non-error result selects ``page_id`` as the active page.
    """

    expression: str = Field(min_length=1)
    page_id: str = Field(min_length=1)


class VariableModeConfig(BaseModel):
    """Settings for variable-driven page selection.

    ``rules`` are evaluated in order; the first one whose expression returns
    a truthy non-error value wins. If no rule matches (or all error), the
    collection falls back to ``default_page_id``.

    ``poll_seconds`` controls how often the active-page loop re-evaluates
    the rules.
    """

    rules: list[VariableRule] = Field(default_factory=list)
    default_page_id: str = Field(min_length=1)
    poll_seconds: int = Field(default=10, ge=2, le=600)


class Collection(BaseModel):
    """A collection – an ordered set of pages plus a selection mode."""

    id: str = Field(default_factory=make_collection_id)
    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)

    selection_mode: SelectionMode = "time"
    time: TimeModeConfig = Field(default_factory=TimeModeConfig)
    variable: VariableModeConfig | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _require_variable_config_when_mode_variable(self) -> "Collection":
        if self.selection_mode == "variable" and self.variable is None:
            raise ValueError("selection_mode 'variable' requires a 'variable' config block")
        return self

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if not self.page_ids:
            errors.append("Collection requires at least one page")
        if len(self.page_ids) != len(set(self.page_ids)):
            errors.append("Collection contains duplicate pages")
        for pid in self.page_ids:
            if is_collection_id(pid):
                errors.append("Collections cannot contain other collections")
        if self.selection_mode == "variable":
            if self.variable is None:
                errors.append("Variable mode requires a 'variable' config")
            else:
                if self.variable.default_page_id not in self.page_ids:
                    errors.append("Variable mode default_page_id must be in page_ids")
                for idx, rule in enumerate(self.variable.rules):
                    if rule.page_id not in self.page_ids:
                        errors.append(f"Variable rule {idx} page_id not in page_ids: {rule.page_id}")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate_config()) == 0

    # --- Time-mode helpers (preserved from legacy Carousel) ---------------

    def current_page_index_time(self, now_unix: float) -> int:
        """Deterministic cycling so position survives restarts without state."""
        if not self.page_ids:
            return 0
        return int(now_unix / self.time.interval_seconds) % len(self.page_ids)

    def current_page_id_time(self, now_unix: float) -> str:
        return self.page_ids[self.current_page_index_time(now_unix)]

    def total_cycle_seconds_time(self) -> int:
        return len(self.page_ids) * self.time.interval_seconds


class CollectionCreate(BaseModel):
    """Request model for creating a new collection."""

    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)
    selection_mode: SelectionMode = "time"
    time: TimeModeConfig = Field(default_factory=TimeModeConfig)
    variable: VariableModeConfig | None = None


class CollectionUpdate(BaseModel):
    """Request model for updating an existing collection."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    page_ids: list[str] | None = Field(default=None, min_length=1)
    selection_mode: SelectionMode | None = None
    time: TimeModeConfig | None = None
    variable: VariableModeConfig | None = None
