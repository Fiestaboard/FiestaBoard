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

from fastapi import HTTPException

from . import settings as _settings_pkg  # noqa: F401  (ensures the submodule is importable)
from .config import Config
from .devices import resolve_dimensions

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
    note_array boards. Safe to call from any endpoint — never raises.
    """
    try:
        return resolve_dimensions(
            board.get("device_type") or "flagship",
            board.get("notes_wide") or 1,
            board.get("notes_tall") or 1,
        )
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
