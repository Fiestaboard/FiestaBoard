"""Monotonic, bounded-arrival soak driver; execution must be serialized by the operator."""

import math

from runtime_common import ProtocolError


class SlotPacer:
    def __init__(self, start, duration, slot_seconds=1.0):
        if not all(math.isfinite(n) for n in (start, duration, slot_seconds)) or duration <= 0 or slot_seconds <= 0:
            raise ProtocolError("Pacing requires finite start/positive duration/interval")
        self.start = start
        self.slot_seconds = slot_seconds
        self.count = math.ceil(duration / slot_seconds)
        self.index = 0

    def next_slot(self, now):
        if not math.isfinite(now) or now < self.start:
            raise ProtocolError("Monotonic clock is invalid or precedes phase start")
        next_due = max(self.index, math.ceil((now - self.start) / self.slot_seconds))
        missed = list(range(self.index, min(self.count, next_due)))
        if next_due >= self.count:
            self.index = self.count
            return {"slot": None, "deadline": None, "missed": missed}
        self.index = next_due + 1
        return {"slot": next_due, "deadline": self.start + next_due * self.slot_seconds, "missed": missed}
