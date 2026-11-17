"""Short-lived override authority and existing content-owner coordination.

No payload/credential is logged. The deployment is the existing single process;
restart loses authority safely. These locks match content deletion/resize order.
"""

import hashlib
import inspect
import re
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from functools import wraps

from starlette.types import ASGIApp, Scope


def actor_identity(request) -> str:
    from src.auth.service import SESSION_COOKIE_NAME

    if request is None:
        return "internal"
    scope = request.scope
    session = scope.get("auth_session_id")
    if session:
        return f"native:{scope.get('auth_user', '')}:{session}"
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        digest = hashlib.sha256(cookie.encode()).hexdigest()
        return f"browser:{scope.get('auth_user', '')}:{digest}"
    return "local:" + scope.get("auth_user", "anonymous")


@contextmanager
def content_owners(settings):
    from src.collections.service import get_collection_service
    from src.config_manager import get_config_manager
    from src.pages.service import get_page_service
    from src.schedules.service import get_schedule_service

    config = get_config_manager()
    stores = (get_page_service().storage, get_collection_service().storage, get_schedule_service().storage)
    with ExitStack() as locks:
        for lock in (settings.lock, config.lock, *(store.lock for store in stores)):
            locks.enter_context(lock)
        yield (id(config), config.config_generation, *((id(store), store._store.runtime_revision) for store in stores))


# Only physical-write front doors need an admission barrier. Content/settings
# writes are coordinated by owner locks and generations, including writers
# continuing after an SSE response. Read-only POST previews never enter here.
_MANUAL = re.compile(
    r"/(?:send-message|send-welcome-message|refresh|templates/render/live|"
    r"displays/[^/]+/send|v1/boards/[^/]+/(?:message|restore)|board/external-frame|"
    r"debug/(?:blank|fill|info|test-connection|clear-cache)|force-refresh|clear-cache|"
    r"pages/[^/]+/send|settings/active-page|v1/boards/[^/]+/active-page)"
)


_manual_intent = ContextVar("override_undo_manual_intent", default=False)


def track_send_job(key: tuple):
    """Return a terminal callback owning authority through actual worker completion."""
    if not _manual_intent.get() and (not key or key[0] != "trigger"):
        return None
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.begin_override_mutation()
    return lambda: settings.finish_override_mutation(success=True)


class OverrideMutationMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive, send):
        if (
            scope["type"] != "http"
            or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}
            or not _MANUAL.fullmatch(scope.get("path", ""))
        ):
            return await self.app(scope, receive, send)
        # Registered inside AuthMiddleware: rejected credentials never arrive.
        from src.settings.service import get_settings_service

        settings = get_settings_service()
        settings.begin_override_mutation()
        # A server exception/5xx can follow a partially applied board write.
        success = True

        async def observe(message):
            nonlocal success
            if message["type"] == "http.response.start":
                success = 200 <= message["status"] < 300 or message["status"] >= 500
            await send(message)

        intent = _manual_intent.set(True)
        try:
            await self.app(scope, receive, observe)
        finally:
            _manual_intent.reset(intent)
            settings.finish_override_mutation(success=success)


def _changed(result) -> bool:
    if isinstance(result, dict):
        # An error may follow a write accepted by hardware before timeout.
        # Only explicit blocked/skipped outcomes establish no mutation.
        return bool(
            result.get("partial")
            or result.get("held")
            or (result.get("status") != "blocked" and not result.get("skipped"))
        )
    # Legacy bool/void senders cannot establish that a failed physical send
    # left hardware untouched. Refuse conservatively after any completed run.
    return True


@contextmanager
def _manual_operation():
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.begin_override_mutation()
    intent = _manual_intent.set(True)
    state = [True]
    try:
        yield state
    finally:
        _manual_intent.reset(intent)
        settings.finish_override_mutation(success=state[0])


def manual_mutation(function):
    """Cover HTTP-independent manual operations, including awaited async calls.

    Worker jobs inherit the intent and acquire independent terminal authority,
    so timeout/return/enqueue cannot retire an actual in-flight hardware write.
    """
    if inspect.iscoroutinefunction(function):

        @wraps(function)
        async def asynchronous(*args, **kwargs):
            with _manual_operation() as state:
                result = await function(*args, **kwargs)
                state[0] = _changed(result)
                return result

        return asynchronous

    @wraps(function)
    def synchronous(*args, **kwargs):
        with _manual_operation() as state:
            result = function(*args, **kwargs)
            state[0] = _changed(result)
            return result

    return synchronous
