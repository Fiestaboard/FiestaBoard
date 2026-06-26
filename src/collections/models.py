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
- ``random``: pick a page at random each ``random.interval_seconds`` window.
  Uses a stateless, deterministic shuffle-bag so a page is never shown twice
  in a row and the choice survives restarts without stored state.
"""

import random as _random
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

COLLECTION_ID_PREFIX = "collection:"

SelectionMode = Literal["time", "variable", "random"]


def _shuffle_bag_permutation(round_index: int, n: int) -> list[int]:
    """Return a deterministic random permutation of ``range(n)`` for a round.

    Seeded purely by ``round_index`` so the same round always yields the same
    permutation — this is what makes random mode stateless and restart-safe.
    """
    rng = _random.Random(round_index)
    return rng.sample(range(n), n)


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


class RandomModeConfig(BaseModel):
    """Settings for random page selection.

    ``interval_seconds`` is the page duration — how long each randomly chosen
    page is shown before a new one is selected.
    """

    interval_seconds: int = Field(default=30, ge=5, le=3600)


class Collection(BaseModel):
    """A collection – an ordered set of pages plus a selection mode."""

    id: str = Field(default_factory=make_collection_id)
    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)

    selection_mode: SelectionMode = "time"
    time: TimeModeConfig = Field(default_factory=TimeModeConfig)
    variable: VariableModeConfig | None = None
    random: RandomModeConfig | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _require_variable_config_when_mode_variable(self) -> "Collection":
        if self.selection_mode == "variable" and self.variable is None:
            raise ValueError("selection_mode 'variable' requires a 'variable' config block")
        return self

    @model_validator(mode="after")
    def _require_random_config_when_mode_random(self) -> "Collection":
        if self.selection_mode == "random" and self.random is None:
            raise ValueError("selection_mode 'random' requires a 'random' config block")
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

    # --- Random-mode helpers ---------------------------------------------

    def current_page_index_random(self, now_unix: float) -> int:
        """Pick a page index pseudo-randomly for the current duration window.

        Implements a stateless shuffle-bag: each *round* (a full pass over all
        pages) is a permutation seeded by the round number, so every page is
        shown exactly once before any repeats. The round boundary is patched so
        the first page of a round never equals the last page of the previous
        round, guaranteeing a page is never shown twice in a row. Because the
        permutation is derived solely from the time-based round number, the
        sequence is deterministic and survives restarts with no stored state.

        With exactly two pages, "no repeats" forces strict alternation (only the
        starting page is free), so that case is handled directly.
        """
        n = len(self.page_ids)
        if n <= 1:
            return 0
        interval = self.random.interval_seconds if self.random else 30
        bucket = int(now_unix / interval)
        if n == 2:
            phase = _shuffle_bag_permutation(0, 2)[0]
            return (bucket + phase) % 2

        round_index, pos = divmod(bucket, n)
        perm = _shuffle_bag_permutation(round_index, n)
        # Patch the whole round (not just pos 0) so every position reflects the
        # swap. For n >= 3 the swap never touches the last element, so the
        # previous round's last page is its unpatched perm[-1] — no recursion.
        if round_index > 0:
            prev_last = _shuffle_bag_permutation(round_index - 1, n)[-1]
            if perm[0] == prev_last:
                perm[0], perm[1] = perm[1], perm[0]
        return perm[pos]

    def current_page_id_random(self, now_unix: float) -> str:
        return self.page_ids[self.current_page_index_random(now_unix)]


class CollectionCreate(BaseModel):
    """Request model for creating a new collection."""

    name: str = Field(min_length=1, max_length=100)
    page_ids: list[str] = Field(min_length=1)
    selection_mode: SelectionMode = "time"
    time: TimeModeConfig = Field(default_factory=TimeModeConfig)
    variable: VariableModeConfig | None = None
    random: RandomModeConfig | None = None


class CollectionUpdate(BaseModel):
    """Request model for updating an existing collection."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    page_ids: list[str] | None = Field(default=None, min_length=1)
    selection_mode: SelectionMode | None = None
    time: TimeModeConfig | None = None
    variable: VariableModeConfig | None = None
    random: RandomModeConfig | None = None
