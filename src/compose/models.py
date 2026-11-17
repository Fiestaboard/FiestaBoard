"""One bounded, explicit Compose intent; omission never means indefinite."""

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from src.devices import ABSOLUTE_MIN_GRID_COLS, ABSOLUTE_MIN_GRID_ROWS, MAX_GRID_COLS, MAX_GRID_ROWS, MAX_NOTES_PER_AXIS

PROTOCOL = "compose-intent-v1"
MAX_MINUTES = 480
_INSTANT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")


class InvalidComposeDuration(ValueError):
    pass


class ExpiredComposeIntent(InvalidComposeDuration):
    pass


def instant(value: str) -> datetime:
    if not _INSTANT.fullmatch(value):
        raise ValueError("An explicit RFC3339 offset instant is required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("A timezone offset is required")
        return result.astimezone(UTC)
    except (ValueError, OverflowError):
        raise ValueError("Invalid offset instant") from None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MinuteDuration(StrictModel):
    kind: Literal["minutes"]
    minutes: StrictInt = Field(ge=1, le=MAX_MINUTES)


class EndDuration(StrictModel):
    kind: Literal["until"]
    ends_at: StrictStr

    @field_validator("ends_at")
    @classmethod
    def valid_instant(cls, value: str) -> str:
        instant(value)
        return value


class IndefiniteDuration(StrictModel):
    kind: Literal["until_cancel"]


class ComposeGeometry(StrictModel):
    device_type: Literal["flagship", "note", "note_array", "panel"]
    notes_wide: StrictInt = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    notes_tall: StrictInt = Field(default=1, ge=1, le=MAX_NOTES_PER_AXIS)
    grid_rows: StrictInt | None = Field(default=None, ge=ABSOLUTE_MIN_GRID_ROWS, le=MAX_GRID_ROWS)
    grid_cols: StrictInt | None = Field(default=None, ge=ABSOLUTE_MIN_GRID_COLS, le=MAX_GRID_COLS)

    @model_validator(mode="after")
    def explicit_panel(self):
        if self.device_type == "panel" and (self.grid_rows is None or self.grid_cols is None):
            raise ValueError("Panel geometry requires both grid axes")
        return self


class LineMetadata(StrictModel):
    alignment: Literal["left", "center", "right"] = "left"
    wrap: StrictBool = False


class ComposeRequest(StrictModel):
    protocol: Literal["compose-intent-v1"]
    request_id: UUID
    prepared_at: StrictStr

    @field_validator("prepared_at")
    @classmethod
    def prepared_instant(cls, value: str) -> str:
        instant(value)
        return value

    template: list[StrictStr] = Field(min_length=1, max_length=512)
    line_metadata: list[LineMetadata] | None = None
    geometry: ComposeGeometry
    duration: Annotated[MinuteDuration | EndDuration | IndefiniteDuration, Field(discriminator="kind")]
    silence: Literal["hold", "override"]

    @model_validator(mode="after")
    def bounded_template(self):
        if sum(len(line.encode("utf-8")) for line in self.template) > 65536:
            raise ValueError("Compose content exceeds 65,536 bytes")
        if any(len(line) > 4096 for line in self.template):
            raise ValueError("A Compose line exceeds 4,096 characters")
        if self.line_metadata is not None and len(self.line_metadata) != len(self.template):
            raise ValueError("Line metadata must match the template")
        return self

    def validate_admission(self, *, now: datetime) -> None:
        if abs((instant(self.prepared_at) - now).total_seconds()) > 300:
            raise InvalidComposeDuration("The prepared request is outside its five-minute clock window")
        self.expires_at(released_at=now)

    def expires_at(self, *, released_at: datetime) -> str | None:
        if released_at.tzinfo is None:
            raise InvalidComposeDuration("Release time must have an offset")
        if isinstance(self.duration, IndefiniteDuration):
            return None
        if isinstance(self.duration, MinuteDuration):
            return (released_at + timedelta(minutes=self.duration.minutes)).isoformat()
        end = instant(self.duration.ends_at)
        if end <= released_at:
            raise ExpiredComposeIntent("The original end time has passed")
        if end - released_at > timedelta(minutes=MAX_MINUTES):
            raise InvalidComposeDuration("An absolute end must be within 480 minutes")
        return end.isoformat()


class ComposeReceipt(StrictModel):
    protocol: Literal["compose-intent-v1"] = "compose-intent-v1"
    request_id: UUID
    board_id: str
    status: Literal[
        "preparing",
        "dispatching",
        "held",
        "sent",
        "unchanged",
        "not_sent",
        "partial",
        "expired",
        "superseded",
        "unknown",
        "rejected",
    ]
    sent: StrictBool | None = None
    expires_at: str | None = None
    started_at: str | None = None
    held_until: str | None = None
    reason: str | None = None
    duration: MinuteDuration | EndDuration | IndefiniteDuration
