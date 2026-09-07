"""The display-service runtime: the singleton, its lifecycle clock, and the
board helpers every endpoint asks the same questions through.

Extracted from ``src/api_server.py`` (Phase 2 Task 8, the debug slice). These
collaborators had no canonical home — they lived in the app module purely
because that is where the handlers that used them were declared — so every
extracted router reached back into ``api_server`` at call time to find them,
which is how the 2026-09 audit counted the import seams going *up* 4.2x
during Phase 1.

``src/api_server.py`` imports every name below at module level under the
identity it had before the move, so the ~130 existing
``patch("src.api_server.get_service")``-style targets keep resolving for the
handlers still declared there. A converted router binds from *this* module
instead, and its tests patch ``src.display_runtime.<name>``.

Deliberately still in ``api_server``: the ``_service_running`` flag and the
service thread. They are written by the start/stop lifecycle endpoints, read
at 22 sites and patched at ~46 test sites, and moving them is the
display/board-control slice's job, not this one. :func:`is_service_running`
reads the flag through a probe ``api_server`` registers at import — one
source of truth, reachable without importing the module that owns it.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from .devices import resolve_dimensions
from .main import DisplayService
from .settings.service import get_settings_service

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Service singleton
# --------------------------------------------------------------------------

_service: DisplayService | None = None
_service_lock = threading.Lock()

#: Set when the display loop starts; ``None`` while it has never run.
_service_start_time: float | None = None

#: Installed by ``src.api_server`` at import time. Until then — a fresh
#: interpreter that imports only a router, for instance — the service is not
#: running, which is the truthful answer.
_running_probe: Callable[[], bool] | None = None


def set_running_probe(probe: Callable[[], bool]) -> None:
    """Register the reader for the ``api_server`` service-running flag."""
    global _running_probe
    _running_probe = probe


def is_service_running() -> bool:
    """True when the display loop thread is running."""
    return bool(_running_probe()) if _running_probe is not None else False


def mark_service_started() -> None:
    """Start the uptime clock (called when the display loop thread starts)."""
    global _service_start_time
    _service_start_time = time.time()


def get_service() -> DisplayService | None:
    """Get or create the service instance."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                try:
                    _service = DisplayService()
                    if not _service.initialize():
                        logger.warning(
                            "Service initialization failed - service can be started later when configuration is fixed"
                        )
                        # Keep the service instance but mark it as uninitialized
                        # This allows the /start endpoint to retry initialization
                        return _service
                except Exception as e:
                    logger.error(f"Failed to create service: {e}", exc_info=True)
                    return None
    return _service


def peek_service() -> DisplayService | None:
    """Return the existing DisplayService instance without creating one.

    For callers that only need to touch state that already exists (e.g.
    invalidating dedupe caches after an out-of-band board write, issue
    #1794): when no service exists there is nothing to invalidate, and
    building one as a side effect would be wrong.
    """
    return _service


def _publish_mqtt_state_update() -> None:
    """Push fresh MQTT state after an out-of-band board write (issue #1794).

    No-op when the MQTT integration isn't wired. Errors are swallowed —
    MQTT reporting must never fail the board write that triggered it.
    """
    try:
        from .mqtt import get_mqtt_client

        client = get_mqtt_client()
        publisher = getattr(client, "_state_publisher", None) if client else None
        if publisher is None:
            return
        publisher.mark_display_updated()
        publisher.gather_and_publish()
    except Exception as e:
        logger.debug(f"MQTT state publish after board write failed: {e}")


def _note_out_of_band_write() -> None:
    """Record a successful out-of-band write to the primary board and push
    fresh MQTT state (issue #1831).

    The write bypassed the display loop and persists (issue #1794), so the
    board no longer shows the configured page; flagging it lets the state
    publisher report that instead of the page name. Peek only — with no
    DisplayService there is nothing to flag, and reporting must never fail
    the board write that triggered it.
    """
    service = peek_service()
    if service is not None:
        try:
            service.mark_showing_out_of_band()
        except Exception as e:
            logger.debug(f"Out-of-band mark failed: {e}")
    _publish_mqtt_state_update()


def _send_with_status(service, method: str, fallback: str, *args, **kwargs) -> tuple[bool, str | None]:
    """Run a ``check_and_send_*`` pass and return ``(sent, failure reason)``.

    ``check_and_send_*`` swallow exceptions and return a bool that conflates
    "failed" with benign skips, so endpoints reported silent failures as
    success (issue #1791). The ``*_with_status`` wrappers capture the reason
    for *this* call in a thread-local, which is why the reason must come back
    from the call rather than be read off the runtime afterwards — the engine
    thread rewrites ``last_send_error`` on its own cadence.

    Falls back to the plain method (and no reason) when the service does not
    expose the wrapper, so Mock services from older test fixtures still work.
    Only a non-empty ``str`` counts as a reason, for the same Mock reason
    (same convention as ``_board_is_paused``).
    """
    wrapper = getattr(service, method, None)
    if callable(wrapper):
        result = wrapper(*args, **kwargs)
        if isinstance(result, tuple) and len(result) == 2:
            sent, error = result
            return sent is True, (error if isinstance(error, str) and error else None)
    sent = getattr(service, fallback)(*args, **kwargs)
    return sent is True, None


def _get_server_ip() -> str:
    """Get the server's IP address."""
    import socket

    try:
        # Create a socket to determine the IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "unknown"


def _get_service_uptime() -> float | None:
    """Get service uptime in seconds."""
    if _service_start_time is None:
        return None
    return time.time() - _service_start_time


def _format_uptime(seconds: float | None) -> str:
    """Format uptime seconds as 'Xd Xh Xm'."""
    if seconds is None:
        return "not running"

    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or len(parts) == 0:
        parts.append(f"{minutes}m")

    return " ".join(parts)


def _get_board_client():
    """Get the board client from the service."""
    service = get_service()
    if service and service.vb_client:
        return service.vb_client
    return None


def _primary_board_entry() -> dict | None:
    """First entry of the settings.boards store, or None when it is empty.

    Safe to call from any endpoint — never raises (mirrors
    ``_get_first_board_dims``).
    """
    try:
        boards = get_settings_service().get_board_settings().boards or []
        if isinstance(boards, list) and boards and isinstance(boards[0], dict):
            return boards[0]
    except Exception as exc:
        logger.debug("Could not read boards list: %s", exc)
    return None


def _primary_connection_info() -> tuple[str, str]:
    """Return ``(connection_mode, board_host)`` for the primary board.

    Reads the boards[] store — the source the live clients are built from
    and what Settings → Boards displays — then falls back to the live
    primary client. The legacy config.json copy is never consulted: board
    credentials are unified on settings.json (issue #1760), so with no
    boards entry and no live client the install is simply unconfigured.
    """
    board = _primary_board_entry()
    if board is not None:
        mode = board.get("api_mode") or "local"
        host = board.get("host") or ""
        return (mode.lower() if isinstance(mode, str) else "local", host if isinstance(host, str) else "")

    client = _get_board_client()
    if client is not None:
        # Strict-True guard so Mock clients from older test fixtures don't
        # read as cloud (same convention as _board_is_paused).
        mode = "cloud" if getattr(client, "use_cloud", False) is True else "local"
        host = getattr(client, "host", "")
        return mode, host if isinstance(host, str) else ""

    return "local", ""


def _get_first_board_dims():
    """Return resolved dimensions for the first configured board.

    Falls back to flagship 6×22 when the boards list is empty or settings
    cannot be read. Safe to call from any endpoint — never raises.
    """
    try:
        settings_service = get_settings_service()
        board_settings = settings_service.get_board_settings()
        boards = getattr(board_settings, "boards", None) or []
        if boards:
            first = boards[0]
            if isinstance(first, dict):
                dt = first.get("device_type", "flagship")
                nw = first.get("notes_wide", 1)
                nt = first.get("notes_tall", 1)
            else:
                dt = getattr(first, "device_type", "flagship")
                nw = getattr(first, "notes_wide", 1)
                nt = getattr(first, "notes_tall", 1)
            return resolve_dimensions(dt, notes_wide=nw, notes_tall=nt)
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
