"""The per-call verdict of one board write.

A board driver's ``send_characters`` / ``render`` have always
answered ``(success, was_sent)``, and a write the client-side send floor
dropped is byte-identical to an unchanged-content skip: ``(True, False)``.
The client kept the difference on an instance flag (``last_send_throttled``)
that callers read *after* the call returned — after the per-board send lock
was released — so any concurrent sender on the same client (the engine tick,
a BoardSendWorker job, a debug write) could flip it in the gap and the
caller settled the wrong verdict (#1931 review).

:class:`SendOutcome` carries the verdict with the call instead. Every send
method returns it behind ``with_outcome=True``; without the keyword the
two-tuple contract is unchanged, so no existing caller moves.

It lives in its own module because both the output plugin driver (produces
it) and :mod:`src.board_guards` (consumes it) need the type, and neither
should import the other for it.

``WriteResult`` (plan D3) is the same verdict plus whether the write reached
only *part* of the board — a local note array is several devices, and one
tile can fail while the rest take their slice. ``SendOutcome`` is kept as
an alias of it, so every existing import and comparison stands.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class FrameRegion(NamedTuple):
    """A rectangle of board cells, in rows/cols of flaps (0-based)."""

    row: int
    col: int
    rows: int
    cols: int

    def as_dict(self) -> dict[str, int]:
        return {"row": self.row, "col": self.col, "rows": self.rows, "cols": self.cols}


class WriteResult(NamedTuple):
    """What one write did, decided under the send lock and handed back."""

    #: The client is not in an error state: the write went out, or it was
    #: deliberately not attempted (unchanged, or throttled).
    success: bool
    #: Flaps moved: the content reached the board on this call.
    was_sent: bool
    #: ``was_sent`` is False because the send floor DROPPED the write — the
    #: content did not land, unlike an unchanged skip where it already had.
    throttled: bool = False
    #: Whole seconds until the floor admits another write — the REMAINING
    #: window at the time of this call, rounded up, never 0. ``None`` unless
    #: throttled.
    retry_after_seconds: int | None = None
    #: The board's minimum send interval in whole seconds, when it has one.
    floor_seconds: int | None = None
    #: The write failed for part of the board but landed on the rest: the
    #: board shows a mix of the new and the old content. Always alongside
    #: ``success=False``; a write that reached nothing is not partial.
    partial: bool = False
    #: The cells that did not update (a failed tile's rectangle), when the
    #: driver can say. Empty for a whole-board verdict.
    failed_regions: tuple[FrameRegion, ...] = ()

    @classmethod
    def of(cls, result: Any) -> WriteResult:
        """Coerce a send result to an outcome.

        A :class:`WriteResult` passes through. A bare ``(success, was_sent)``
        pair — a test double, or a client that predates the outcome — is
        taken at face value with no throttle verdict, which is the safe
        reading: nobody said it was dropped.
        """
        if isinstance(result, cls):
            return result
        if isinstance(result, tuple | list) and len(result) == 2:
            return cls(bool(result[0]), bool(result[1]))
        raise TypeError(f"not a send result: {result!r}")


#: The name every caller used before the outcome learned about partial writes.
SendOutcome = WriteResult
