"""Native sign-in enrollment and explicit browser approval endpoints."""

from fastapi import APIRouter, Request

from src.api_errors import errors

from .browser_routes import require_browser_mutation, require_browser_session
from .device_models import (
    AuthFlowError,
    DeviceChallenge,
    DeviceCode,
    DeviceExchange,
    DeviceLogin,
    DeviceMetadata,
    DeviceTokenResult,
    EnrollmentSettings,
    PendingDevice,
    Success,
    UserCode,
)
from .device_service import DeviceService
from .middleware import _bearer_from
from .routes import _check_lockout, _clear_failures, _client_ip, _record_failure
from .service import InvalidCredentials, get_auth_service

router = APIRouter(prefix="/auth/device", tags=["auth"])
RESPONSES = errors(400, 401, 403, 409, 422, 429, 503)


@router.post("/authorize", response_model=DeviceChallenge, responses=RESPONSES)
def authorize(payload: DeviceMetadata, request: Request):
    return DeviceService(get_auth_service()).authorize(payload, _client_ip(request))


@router.post("/token", response_model=DeviceTokenResult, responses=RESPONSES)
def exchange(payload: DeviceExchange):
    return DeviceService(get_auth_service()).exchange(payload.device_code, payload.client_id)


@router.post("/login", response_model=DeviceTokenResult, responses=RESPONSES)
def login(payload: DeviceLogin, request: Request):
    ip = _client_ip(request)
    _check_lockout(ip)
    service = DeviceService(get_auth_service())
    metadata = DeviceMetadata(
        client_id=payload.client_id, device_name=payload.device_name, app_version=payload.app_version
    )
    try:
        result = service.login(payload.username, payload.password, metadata)
    except InvalidCredentials:
        _record_failure(ip)
        raise AuthFlowError("invalid_credentials", "That username or password did not work.", 401) from None
    _clear_failures(ip)
    return result


@router.post("/cancel", response_model=Success, responses=RESPONSES)
def cancel(payload: DeviceCode):
    DeviceService(get_auth_service()).cancel(payload.device_code)
    return Success()


def _decision_context(request: Request):
    browser = require_browser_mutation(request)
    service = DeviceService(get_auth_service())
    service.limit("decision:" + browser.username + ":" + _client_ip(request), 10)
    return browser, service


@router.post("/inspect", response_model=PendingDevice, responses=RESPONSES)
def inspect(payload: UserCode, request: Request):
    _, service = _decision_context(request)
    return service.inspect(payload.user_code)


@router.post("/approve", response_model=Success, responses=RESPONSES)
def approve(payload: UserCode, request: Request):
    browser, service = _decision_context(request)
    service.decide(payload.user_code, browser, True)
    return Success()


@router.post("/deny", response_model=Success, responses=RESPONSES)
def deny(payload: UserCode, request: Request):
    browser, service = _decision_context(request)
    service.decide(payload.user_code, browser, False)
    return Success()


@router.get("/settings", response_model=EnrollmentSettings, responses=RESPONSES)
def settings(request: Request):
    require_browser_session(request)
    return EnrollmentSettings(enabled=get_auth_service().sessions.enrollment_enabled)


@router.put("/settings", response_model=EnrollmentSettings, responses=RESPONSES)
def update_settings(payload: EnrollmentSettings, request: Request):
    require_browser_mutation(request)
    get_auth_service().sessions.set_enrollment(payload.enabled)
    return payload


@router.delete("/session", response_model=Success, responses=RESPONSES)
def revoke_self(request: Request):
    auth = get_auth_service()
    session = DeviceService(auth).authenticate_tv(_bearer_from(request) or "")
    if not session:
        raise AuthFlowError("unauthorized", "This TV sign-in is no longer valid.", 401)
    auth.sessions.revoke_session(session.username, session.id)
    return Success()
