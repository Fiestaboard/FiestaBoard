"""Browser-only push enrollment. Validation errors never reflect capabilities."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from src.api_errors import ErrorResponse, errors
from src.auth.browser_routes import require_browser_mutation, require_browser_session

from . import service
from .models import DeliveryResult, PushPreference, PushStatus, PushSubscription, TestPushRequest


class PrivatePushRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def private_handler(request):
            try:
                # Bound before JSON decoding and avoid Pydantic's input echo.
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 8192:
                        return JSONResponse({"detail": "Push request too large"}, status_code=413)
                request._body = bytes(body)
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "Invalid push request"}, status_code=422)
            except service.PushError as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status)
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_handler


router = APIRouter(prefix="/push", tags=["push"], route_class=PrivatePushRoute)
RESPONSES = errors(400, 401, 403, 409, 413, 422, 429, 503, models={422: ErrorResponse})
SECURITY = {"security": [{"session": []}]}


@router.get("/status", response_model=PushStatus, responses=RESPONSES, openapi_extra=SECURITY)
def push_status(request: Request):
    """Current account/browser consent and public VAPID key. No subscription secrets."""
    return service.status(require_browser_session(request))


@router.put("/preferences", response_model=PushStatus, responses=RESPONSES, openapi_extra=SECURITY)
def push_preferences(payload: PushPreference, request: Request):
    """Set this account's push consent. Requires portal Origin and X-CSRF-Token."""
    return service.set_preferences(require_browser_mutation(request), payload)


@router.put("/subscription", response_model=PushStatus, responses=RESPONSES, openapi_extra=SECURITY)
def push_subscribe(payload: PushSubscription, request: Request):
    """Register/replace only this browser session's subscription and device consent."""
    return service.subscribe(require_browser_mutation(request), payload)


@router.delete("/subscription", response_model=PushStatus, responses=RESPONSES, openapi_extra=SECURITY)
def push_unsubscribe(request: Request):
    """Idempotently erase this browser's subscription. Requires Origin and CSRF."""
    return service.unsubscribe(require_browser_mutation(request))


@router.post("/test", response_model=DeliveryResult, responses=RESPONSES, openapi_extra=SECURITY)
def push_test(payload: TestPushRequest, request: Request):
    """Send fixed test text to this browser only, at most once per minute."""
    result = service.send_test(require_browser_mutation(request))
    if result.failed:
        raise HTTPException(503, "The push provider did not accept the test. Try again later.")
    return result
