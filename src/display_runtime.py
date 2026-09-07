"""The ``DisplayService`` singleton, owned outside the FastAPI app module.

``get_service()`` and ``peek_service()`` lived in ``src/api_server.py``, so
every extracted router had to reach them with a call-time
``from src.api_server import get_service`` — the seam that makes serving one
request re-import the whole 10k-line app module (2026-09 audit, Phase 2 §2.3).
The accessor has nothing to do with the app object, so it lives here.

``src.api_server`` still imports both names, so its own handlers and the tests
that patch ``src.api_server.get_service`` / ``.peek_service`` for those
handlers are unchanged. Domain routers import from here and are patched at
``src.<domain>.routes.get_service``.

What stays in ``api_server``: the background-thread lifecycle
(``_service_running``, ``run_service_background``, ``start_service``,
``stop_service``). That is server lifecycle, not an accessor, and
``tests/test_service_lifecycle.py`` owns it.
"""

from __future__ import annotations

import logging
import threading

from .main import DisplayService

logger = logging.getLogger(__name__)

_service: DisplayService | None = None
_service_lock = threading.Lock()


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
