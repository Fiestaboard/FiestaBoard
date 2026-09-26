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


:func:`reinitialize_board_clients` joined them from the config slice: it is
nothing but "get the service and rebuild its clients", so keeping it in
``api_server`` forced every router that mutates the boards list to import the
app module for one line.

Deliberately still in ``api_server``: the background-thread *state* — the
``_service_running`` flag, the thread handle, ``_shutting_down`` and
``run_service_background``. That is server lifecycle rather than an accessor;
the flag is read at 22 sites and patched at ~30 test sites, all of them
``patch("src.api_server._service_running", ...)``, and relocating a module
global cannot keep those patches live (``mock.patch`` sets the attribute on
the module you name, and a module cannot expose a mutable global as a
property).

So the state stays where it is and this module owns the *seam*.
:func:`is_service_running` reads the flag through a probe, and
:func:`spawn_display_loop` / :func:`halt_display_loop` write it through a pair
of controls — both registered by ``api_server`` at import. One flag, one
owner, and a converted router that never has to import the module that owns
it. Moving the state itself is a follow-up, tracked separately.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from .board_guards import _board_is_paused  # noqa: F401  (re-export: pre-move patch target)
from .board_guards import primary_board_entry as _primary_board_entry  # noqa: F401  (same)
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


#: Installed by ``src.api_server`` at import time, next to the state they
#: mutate. ``spawn`` clears the shutdown flag and starts the loop thread;
#: ``halt`` sets the shutdown flag, tells a running service to stop, and
#: clears the running flag. Neither decides anything — the ``POST /start`` and
#: ``POST /stop`` handlers in :mod:`src.service_api.routes` own the policy.
_loop_spawn: Callable[[], None] | None = None
_loop_halt: Callable[[], None] | None = None


def set_loop_controls(spawn: Callable[[], None], halt: Callable[[], None]) -> None:
    """Register the writers for the ``api_server`` background-loop state."""
    global _loop_spawn, _loop_halt
    _loop_spawn = spawn
    _loop_halt = halt


def spawn_display_loop() -> None:
    """Start the background display loop thread."""
    if _loop_spawn is None:  # pragma: no cover - api_server registers at import
        logger.warning("No display-loop controls registered; cannot start the loop")
        return
    _loop_spawn()


def halt_display_loop() -> None:
    """Stop the background display loop and suppress its auto-restart."""
    if _loop_halt is None:  # pragma: no cover - api_server registers at import
        logger.warning("No display-loop controls registered; cannot stop the loop")
        return
    _loop_halt()


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


def _note_out_of_band_write(board_id: str | None = None) -> None:
    """Record a successful out-of-band write to a board and push fresh MQTT
    state (issue #1831).

    The write bypassed the display loop and persists (issue #1794), so the
    board no longer shows the configured page; flagging it lets the state
    publisher report that instead of the page name. Peek only — with no
    DisplayService there is nothing to flag, and reporting must never fail
    the board write that triggered it.

    ``board_id`` omitted → the primary board, which is what every caller
    meant before ``POST /send-message`` learned to target one (issue #1247);
    ``mark_showing_out_of_band`` resolves it the same way.
    """
    service = peek_service()
    if service is not None:
        try:
            # Called with NO argument for the primary board. mark_showing_out_
            # _of_band(None) means the same thing, but ~4 existing tests assert
            # the zero-argument call, and re-pinning them to record an
            # explicit None would be re-pinning a promise nothing changed.
            if board_id is None:
                service.mark_showing_out_of_band()
            else:
                service.mark_showing_out_of_band(board_id)
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


def reinitialize_board_clients() -> None:
    """Rebuild board clients after a boards-list mutation.

    Without this, the display service keeps the clients it built at startup
    and sends keep targeting the OLD connections — e.g. after removing the
    first board, the promoted board's content was still delivered to the
    removed board's hardware until restart.

    Lives beside :func:`get_service` because that is the only thing it needs.
    ``src.api_server._reinitialize_board_clients`` delegates here, so the
    handlers still patched at that name behave identically; converted routers
    import this directly.
    """
    service = get_service()
    if service:
        service.reinitialize_board_client()
