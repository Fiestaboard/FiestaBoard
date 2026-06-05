"""Data models for carousels.

Carousels are ordered collections of pages that rotate automatically
at a configured interval. They can be used anywhere a page_id is accepted
by using the prefixed ID format: carousel:{uuid}.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

CAROUSEL_ID_PREFIX = "carousel:"


def make_carousel_id() -> str:
    """Generate a new carousel ID with the standard prefix."""
    return f"{CAROUSEL_ID_PREFIX}{uuid.uuid4()}"


def is_carousel_id(ref_id: str) -> bool:
    """Check whether an ID string refers to a carousel."""
    return bool(ref_id) and ref_id.startswith(CAROUSEL_ID_PREFIX)


def extract_carousel_uuid(carousel_id: str) -> str:
    """Strip the prefix and return the bare UUID portion."""
    return carousel_id[len(CAROUSEL_ID_PREFIX) :]


class Carousel(BaseModel):
    """A carousel – an ordered collection of pages that cycle automatically."""

    id: str = Field(default_factory=make_carousel_id)
    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)
    interval_seconds: int = Field(default=30, ge=5, le=3600)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    def validate_config(self) -> list[str]:
        errors: list[str] = []
        if not self.page_ids:
            errors.append("Carousel requires at least one page")
        if len(self.page_ids) != len(set(self.page_ids)):
            errors.append("Carousel contains duplicate pages")
        for pid in self.page_ids:
            if is_carousel_id(pid):
                errors.append("Carousels cannot contain other carousels")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate_config()) == 0

    def current_page_index(self, now_unix: float) -> int:
        """Determine which page should be displayed right now.

        Uses deterministic time-based cycling so the position survives
        restarts without needing persistent state.
        """
        if not self.page_ids:
            return 0
        return int(now_unix / self.interval_seconds) % len(self.page_ids)

    def current_page_id(self, now_unix: float) -> str:
        return self.page_ids[self.current_page_index(now_unix)]

    def total_cycle_seconds(self) -> int:
        """Total duration of one complete cycle through all pages.

        Returns:
            Number of seconds for one full rotation (num_pages * interval_seconds).
        """
        return len(self.page_ids) * self.interval_seconds


class CarouselCreate(BaseModel):
    """Request model for creating a new carousel."""

    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)
    interval_seconds: int = Field(default=30, ge=5, le=3600)


class CarouselUpdate(BaseModel):
    """Request model for updating an existing carousel."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    page_ids: list[str] | None = Field(default=None, min_length=1)
    interval_seconds: int | None = Field(default=None, ge=5, le=3600)
