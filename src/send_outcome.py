"""The per-call verdict of one board write.

``BoardClient.send_characters`` / ``send_text`` / ``render`` have always
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

It lives in its own module because both :mod:`src.board_client` (produces
it) and :mod:`src.board_guards` (consumes it) need the type, and neither
should import the other for it.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class SendOutcome(NamedTuple):
    """What one send did, decided under the send lock and handed back."""

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

    @classmethod
    def of(cls, result: Any) -> SendOutcome:
        """Coerce a send result to an outcome.

        A :class:`SendOutcome` passes through. A bare ``(success, was_sent)``
        pair — a test double, or a client that predates the outcome — is
        taken at face value with no throttle verdict, which is the safe
        reading: nobody said it was dropped.
        """
        if isinstance(result, cls):
            return result
        if isinstance(result, tuple | list) and len(result) == 2:
            return cls(bool(result[0]), bool(result[1]))
        raise TypeError(f"not a send result: {result!r}")
