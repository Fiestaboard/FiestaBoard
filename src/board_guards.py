"""Board lookup and send guards, shared by every router that pushes to a board.

These five helpers grew up inside ``src/api_server.py``, which meant a router
extracted out of it could only reach them by importing ``src.api_server``
*inside each handler* — the call-time seam the 2026-09 audit counted going up
4.2x across Phase 1. Serving one request then dragged the whole 10k-line
module, its route table and its background tasks back into the process.

They have no dependency on the app object, so they live here instead:
``src.api_server`` imports them (its own handlers and the tests that patch
``src.api_server.<name>`` for those handlers are unaffected — the name is
still bound there), and each domain router imports them directly and is
patched at ``src.<domain>.routes.<name>``.

The pause/silence pair is deliberately forgiving: a guard that raises would
block sends on an unrelated failure, so both degrade to "not blocked" and log.
``_require_board`` is the opposite — it is the single place the "unknown
board" verdict is made, and it raises 404. See the "board_id validation" note
in ``docs/internal/reference/API_CONVENTIONS.md`` for why writes 404 and reads
fall back.

The config slice added the two **host** guards at the bottom of this file.
They answer a different question from the lookups above — "is this string a
host I am willing to open a socket to?" rather than "does this board exist?"
— but they are the same kind of thing: a verdict a router needs before it
touches a board, with no dependency on the app object.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from . import settings as _settings_pkg  # noqa: F401  (ensures the submodule is importable)
from .config import Config
from .devices import geometry_of, resolve_dimensions
from .send_outcome import SendOutcome

logger = logging.getLogger(__name__)


def get_settings_service():
    """Resolve the settings service at call time.

    Bound late, and re-exported here, so a test can stub the settings a guard
    sees by patching ``src.board_guards.get_settings_service`` — one seam for
    every router that imports these guards, rather than one per router.
    """
    from .settings.service import get_settings_service as _get

    return _get()


def _find_board(board_id: str) -> dict | None:
    """Return the settings.boards entry for a board id, or None (issue #1244)."""
    try:
        boards = get_settings_service().get_board_settings().boards or []
    except Exception as exc:
        logger.debug("Could not read boards list: %s", exc)
        return None
    for board in boards:
        if isinstance(board, dict) and board.get("id") == board_id:
            return board
    return None


def primary_board_entry() -> dict | None:
    """First entry of the settings.boards store, or None when it is empty.

    The *default* board — what an endpoint means when it says "the board" with
    no id. Safe to call from any endpoint: never raises (mirrors
    :func:`_find_board`).
    """
    try:
        boards = get_settings_service().get_board_settings().boards or []
        if isinstance(boards, list) and boards and isinstance(boards[0], dict):
            return boards[0]
    except Exception as exc:
        logger.debug("Could not read boards list: %s", exc)
    return None


def _require_board(board_id: str) -> dict:
    """Return the ``settings.boards`` entry for *board_id*, or raise 404.

    The single place the "unknown board" verdict is made. The pattern was
    open-coded in nine handlers and simply missing from four schedule write
    endpoints, which persisted state bound to a board that does not exist and
    reported success (#1888).

    Use this on any path that *writes* something scoped to a board. Board-
    scoped **reads** deliberately fall back to their safe default instead —
    see the "board_id validation" note in
    ``docs/internal/reference/API_CONVENTIONS.md``.
    """
    board = _find_board(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail=f"Board not found: {board_id}")
    return board


def _board_dims(board: dict):
    """Resolved dimensions for a settings.boards entry (flagship fallback).

    Uses resolve_dimensions — never get_dimensions, which raises for
    note_array and panel boards. Safe to call from any endpoint — never raises.
    """
    try:
        return resolve_dimensions(*geometry_of(board))
    except Exception as exc:
        logger.debug("Could not resolve board dims (using flagship default): %s", exc)
        return resolve_dimensions("flagship")


def _board_is_paused(board_id: str | None = None) -> bool:
    """Return True when the target board (or default board) is paused.

    Centralizes the per-board pause check used at every API push site
    (issue #970). When True, callers MUST skip the send so paused boards
    are left untouched.

    Only treats a strict ``True`` as paused — any non-bool return
    (including a ``Mock`` from an under-configured test fixture) is
    coerced to "not paused" so this guard never silently swallows sends
    in tests that pre-date the pause feature.
    """
    try:
        result = get_settings_service().is_paused(board_id=board_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Pause check failed (treating as not paused): %s", e)
        return False
    return result is True


def _silence_active(board_id: str | None = None) -> bool:
    """Return True when the target board (or the primary board) is silenced.

    Mirrors :func:`_board_is_paused`: silence is per board since issue #1788,
    so every send guard must resolve the window of the board it is about to
    touch. ``Config.is_silence_mode_active(None)`` deliberately keeps its
    legacy install-wide meaning for the ~20 fixtures that call it zero-arg, so
    the primary board is resolved here instead — without this an override on
    the bedroom Note was ignored by every manual-send path and a 2am send from
    the web UI or Home Assistant woke the board up.
    """
    resolved = board_id
    if resolved is None:
        try:
            resolved = get_settings_service().get_primary_board_id()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("Could not resolve primary board for silence check: %s", e)
            resolved = None
    return Config.is_silence_mode_active(resolved)


# ---------------------------------------------------------------------------
# Silence verdict — "may this write wake the board?" (issues #1943, #1944)
#
# Every write surface (the active-page PUTs, v1 message, /send-message, MCP,
# MQTT, page/display sends, live render) asks the same question the same way,
# so the copy, the logging and the hold-until-silence-ends queue cannot drift.
# ---------------------------------------------------------------------------

#: The bare 409 detail for a write silence refused.
SILENCE_DETAIL = "Manual sends are blocked while the board is silenced."
#: Appended to :data:`SILENCE_DETAIL` only on routes that accept the override.
SILENCE_OVERRIDE_HINT = (
    " Send override_silence=true to write anyway, or turn on show_queued_on_exit to hold it until silence ends."
)


def resolve_board_id(board_id: str | None) -> str | None:
    """*board_id*, or the primary board's id when it is ``None``. Never raises."""
    if board_id is not None:
        return board_id
    try:
        primary = get_settings_service().get_primary_board_id()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Could not resolve primary board: %s", e)
        return None
    return primary if isinstance(primary, str) and primary else None


@dataclass(frozen=True)
class SilenceTiming:
    """Where one board's silence window stands right now."""

    active: bool
    #: ``HH:MM+00:00`` of the next active/inactive boundary.
    next_change_utc: str
    #: Wall-clock seconds to that boundary; ``None`` when silence is disabled.
    seconds_until_next_change: int | None
    #: ISO-8601 instant of that boundary (now + seconds); ``None`` when disabled.
    next_change_at: str | None


def silence_timing(silence_config: dict) -> SilenceTiming:
    """Resolve a board's silence window against the clock.

    The one copy of the arithmetic ``GET /silence-status`` reports and every
    "silenced until 7:00" message quotes, so the UI and the API never
    disagree about when the window ends.
    """
    from datetime import timedelta

    from src.time_service import get_time_service

    time_service = get_time_service()
    enabled = bool(silence_config.get("enabled"))
    start_time = silence_config.get("start_time")
    end_time = silence_config.get("end_time")
    active = time_service.is_time_in_window(start_time, end_time) if enabled else False
    next_change_utc = end_time if active else start_time
    seconds: int | None = None
    at: str | None = None
    if enabled:
        current_utc = time_service.get_current_utc()
        next_change_dt = time_service.parse_iso_time(next_change_utc)
        if next_change_dt is not None:
            delta_seconds = int((next_change_dt - current_utc).total_seconds())
            # next_change_dt is anchored to "today" in UTC, so a negative value
            # means the boundary already passed today and will recur tomorrow.
            if delta_seconds < 0:
                delta_seconds += 86_400
            seconds = delta_seconds
            at = (current_utc + timedelta(seconds=delta_seconds)).isoformat()
    return SilenceTiming(
        active=active, next_change_utc=next_change_utc, seconds_until_next_change=seconds, next_change_at=at
    )


def silence_window_end(board_id: str | None) -> str | None:
    """ISO-8601 instant the board's current silence window ends, or ``None``.

    ``None`` when the board is not silenced or the window cannot be resolved.
    Never raises: a message that cannot name the time still says the rest.
    """
    try:
        timing = silence_timing(Config.silence_config_for(resolve_board_id(board_id)))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Could not resolve the silence window end: %s", e)
        return None
    return timing.next_change_at if timing.active else None


def silence_ends_hhmm(ends_at_utc: str | None) -> str:
    """``HH:MM`` (UTC) of an :func:`silence_window_end` instant, for API copy."""
    if ends_at_utc:
        from datetime import datetime

        try:
            return datetime.fromisoformat(ends_at_utc).strftime("%H:%M")
        except ValueError:
            pass
    return "the end of the window"


@dataclass(frozen=True)
class SilenceVerdict:
    """What silence says about one write."""

    silenced: bool
    held: bool = False
    ends_at_utc: str | None = None

    @property
    def ends_hhmm(self) -> str:
        return silence_ends_hhmm(self.ends_at_utc)


def silence_verdict(
    board_id: str | None,
    *,
    override_silence: bool,
    hold: Any = None,
    what: str | None = None,
) -> SilenceVerdict:
    """Decide whether silence blocks a write to *board_id* (primary when ``None``).

    * ``override_silence`` true — the caller explicitly asked to wake the
      board: never silenced. Pause is NOT this function's business; every
      caller checks it afterwards and it is never overridden.
    * Otherwise, when the board's window is active the write is silenced. If
      the caller offered a :class:`~src.silence_queue.HeldSend` (or a
      callable building one from the resolved board id) and the board's
      resolved ``show_queued_on_exit`` is on, it is held for delivery when
      the window ends (``held``).

    One log line per outcome, naming the board and the end of the window.
    """
    if override_silence:
        return SilenceVerdict(silenced=False)
    if not _silence_active(board_id):
        return SilenceVerdict(silenced=False)

    resolved = resolve_board_id(board_id)
    ends_at = silence_window_end(resolved)
    kind = what or (getattr(hold, "kind", None) and f"{hold.kind} send") or "manual send"
    holds = False
    try:
        holds = Config.silence_config_for(resolved).get("show_queued_on_exit") is True
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Could not resolve show_queued_on_exit: %s", e)
    if callable(hold) and resolved:
        # A factory: the caller did not resolve "the primary board" itself.
        hold = hold(resolved)
    if hold is not None and not callable(hold) and holds:
        from src import silence_queue

        silence_queue.hold(hold)
        logger.info("Silence active - holding %s for board %s until %s", kind, resolved, silence_ends_hhmm(ends_at))
        return SilenceVerdict(silenced=True, held=True, ends_at_utc=ends_at)
    logger.info(
        "Silence active - refusing %s for board %s (pass override_silence=true to write anyway)", kind, resolved
    )
    return SilenceVerdict(silenced=True, held=False, ends_at_utc=ends_at)


# ---------------------------------------------------------------------------
# Host guards — "is this string a host I will open a socket to?"
#
# Moved out of src/api_server.py by the config slice. The SSRF barrier below
# is CodeQL-recognised (py/full-ssrf); it is reproduced verbatim, not rewritten.
# ---------------------------------------------------------------------------

# Hostnames are restricted to RFC 1123 labels (letters, digits, hyphens) and
# IPv4 dotted-quad notation.  This rejects exotic forms (URL-encoded chars,
# ``user:pass@host``, schemes embedded in the host, etc.) before we ever try
# to connect to a board over HTTP.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)\.)*"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)$"
)


def validate_board_host(host: str) -> None:
    """Validate that ``host`` is a plain IP/hostname (no scheme, port, path).

    Used before constructing URLs that target a Vestaboard on the local
    network.  Raises :class:`HTTPException` (status 400) when invalid.
    """
    if not isinstance(host, str) or not host:
        raise HTTPException(status_code=400, detail="host is required")
    # Reject anything that looks like a full URL or contains delimiters that
    # could redirect the request elsewhere (``@``, ``/``, ``:``, ``?``,
    # ``#`` or whitespace).
    if any(c in host for c in "@/:?# \t\r\n\\"):
        raise HTTPException(
            status_code=400,
            detail="host must be a bare IP address or hostname",
        )
    # Try IPv4 first, then a hostname pattern.
    try:
        ipaddress.IPv4Address(host)
        return
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(host):
        raise HTTPException(
            status_code=400,
            detail="host must be a valid IPv4 address or hostname",
        )


def validate_board_host_is_local_network(host: str) -> None:
    """Ensure ``host`` resolves only to private/local IPv4 addresses.

    Prevents SSRF to arbitrary internet hosts while still allowing local
    network boards.
    """

    def _is_allowed_ipv4(addr: ipaddress.IPv4Address) -> bool:
        return addr.is_private or addr.is_loopback or addr.is_link_local

    try:
        ip = ipaddress.IPv4Address(host)
        if not _is_allowed_ipv4(ip):
            raise HTTPException(
                status_code=400,
                detail="host must resolve to a local/private IPv4 address",
            )
        return
    except ValueError:
        pass

    try:
        addrinfo = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="host could not be resolved") from None

    resolved_ips = {ipaddress.IPv4Address(info[4][0]) for info in addrinfo if info and len(info) >= 5 and info[4]}
    if not resolved_ips:
        raise HTTPException(status_code=400, detail="host did not resolve to an IPv4 address")

    if not all(_is_allowed_ipv4(ip) for ip in resolved_ips):
        raise HTTPException(
            status_code=400,
            detail="host must resolve only to local/private IPv4 addresses",
        )


# ---------------------------------------------------------------------------
# Send guards — the refusals a manual-send endpoint owes its caller
#
# ``src/board_api/routes.py`` and ``src/debug/routes.py`` each grew their own
# byte-identical copy of these two, plus a second definition of PAUSED_DETAIL.
# They answer the same question about the same board, so they live here once.
# ---------------------------------------------------------------------------

PAUSED_DETAIL = "Board is paused — sends are blocked until it is resumed."


def raise_if_paused(board_id: str | None = None, *, what: str = "manual send") -> None:
    """A paused board refuses writes: 409 (issue #970).

    Both senders answered 200 with ``{"status": "blocked"}`` before the
    conventions pass — a refusal dressed as a success, which any client
    checking only the status code read as "sent".

    ``board_id`` resolves the *target* board's pause state; omitted means the
    primary. Pause is per board (#970) and so is silence (#1788), so a guard
    that only ever asked about the primary would let a targeted send through
    to a paused secondary. It answered 200 for exactly that case until this
    parameter existed.

    ``_board_is_paused`` is deliberately resolved through
    ``src.display_runtime`` at call time rather than from this module's own
    binding: that attribute is the patch seam the endpoint tests use
    (``tests/test_platform_contract.py::PAUSED``,
    ``tests/test_debug_decoupled.py``), and reading the local name would
    silently ignore it. The import is function-local because
    ``display_runtime`` imports this module.
    """
    from . import display_runtime as runtime

    if runtime._board_is_paused(board_id):
        logger.info("Board is paused - blocking %s", what)
        raise HTTPException(status_code=409, detail=PAUSED_DETAIL)


def throttle_retry_after(outcome: Any) -> int | None:
    """Seconds until the board's send floor admits another write, or ``None``.

    ``outcome`` is the per-call :class:`~src.send_outcome.SendOutcome` the
    send returned (``with_outcome=True``); a bare ``(success, was_sent)``
    pair is accepted and read as "not throttled", because nobody said it
    was. It is the call's own verdict, decided under the send lock, not the
    client's ``last_send_throttled`` flag — that flag is whatever the *last*
    sender on the client left there, and a concurrent engine tick or send
    worker can rewrite it between a send returning and its caller looking
    (#1931 review).

    ``None`` means the write was not throttled: either it went out, or it
    was the unchanged-content skip that reports the same ``(True, False)``
    but leaves the board showing what was asked (#1794).

    The number is the REMAINING window, rounded up to whole seconds and
    never 0 — not the board's whole floor. A client that reports a throttle
    without a remaining window (a double) falls back to its floor, or to
    the 15s cloud floor when it has none.

    Shared by the HTTP guard below and the ops executors
    (:func:`src.ops.executors.send_message`), so every surface computes the
    same retry hint (#1931).
    """
    outcome = SendOutcome.of(outcome)
    if not outcome.throttled:
        return None
    return outcome.retry_after_seconds or outcome.floor_seconds or 15


def throttled_detail(retry_after: int, floor_seconds: int | None = None) -> str:
    """The one sentence every surface uses for a write the send floor dropped.

    Names both numbers a caller needs: the board's floor (why it happened)
    and the remaining window (when to retry — the same value the HTTP
    surfaces put in ``Retry-After``, for the MCP text-only error path).
    """
    floor = floor_seconds or retry_after
    return f"Send skipped: the board accepts at most one message every {floor}s. Retry in {retry_after}s."


def raise_if_throttled(outcome: Any) -> None:
    """A write dropped by the client-side send floor is a 429 (#1868, #1754).

    Cloud boards and note arrays enforce a minimum interval between sends; a
    send inside that window returns ``(True, False)`` — the content was
    DROPPED, not delivered, and unlike the engine tick (which retries next
    pass) these manual endpoints never retry. ``outcome`` is that send's
    :class:`~src.send_outcome.SendOutcome`; see :func:`throttle_retry_after`
    for why it is the outcome and not the client.
    """
    outcome = SendOutcome.of(outcome)
    retry_after = throttle_retry_after(outcome)
    if retry_after is None:
        return
    raise HTTPException(
        status_code=429,
        detail=throttled_detail(retry_after, outcome.floor_seconds),
        headers={"Retry-After": str(retry_after)},
    )
