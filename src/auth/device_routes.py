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
    PhoneTVList,
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
    """The approver and the service, for approving or denying a TV's code.

    A browser session (portal origin + CSRF), or a signed-in phone's ``fb_mob_``
    Bearer. A Bearer is never ambient, so the phone path needs no CSRF token, and
    on that path a cookie is ignored: neither credential widens the other.
    """
    service = DeviceService(get_auth_service())
    if request.headers.get("authorization"):
        approver = service.authenticate_mobile(_bearer_from(request) or "")
        if not approver:
            raise AuthFlowError("unauthorized", "Sign in on this phone again to approve a TV.", 401)
    else:
        approver = require_browser_mutation(request)
    service.limit("decision:" + approver.username + ":" + _client_ip(request), 10)
    return approver, service


@router.post("/inspect", response_model=PendingDevice, responses=RESPONSES)
def inspect(payload: UserCode, request: Request):
    """Show which TV a code belongs to. From the web portal, or from a signed-in phone."""
    _, service = _decision_context(request)
    return service.inspect(payload.user_code)


@router.post("/approve", response_model=Success, responses=RESPONSES)
def approve(payload: UserCode, request: Request):
    """Allow a TV to sign in. A phone may approve TV codes only."""
    browser, service = _decision_context(request)
    service.decide(payload.user_code, browser, True)
    return Success()


@router.post("/deny", response_model=Success, responses=RESPONSES)
def deny(payload: UserCode, request: Request):
    """Decline a TV's sign-in. From the web portal, or from a signed-in phone."""
    browser, service = _decision_context(request)
    service.decide(payload.user_code, browser, False)
    return Success()


@router.get("/settings", response_model=EnrollmentSettings, responses=RESPONSES)
def settings(request: Request):
    """Read the device sign-in switch, which allows new TV and phone sign-ins.

    Turning it off stops new sign-ins and cancels pending codes; signed-in devices
    keep access until revoked or expired.
    """
    require_browser_session(request)
    return EnrollmentSettings(enabled=get_auth_service().sessions.enrollment_enabled)


@router.put("/settings", response_model=EnrollmentSettings, responses=RESPONSES)
def update_settings(payload: EnrollmentSettings, request: Request):
    """Turn device sign-in (new TV and phone sign-ins) on or off. Browser session only."""
    require_browser_mutation(request)
    get_auth_service().sessions.set_enrollment(payload.enabled)
    return payload


@router.delete("/session", response_model=Success, responses=RESPONSES)
def revoke_self(request: Request):
    auth = get_auth_service()
    session = DeviceService(auth).authenticate_native(_bearer_from(request) or "")
    if not session:
        raise AuthFlowError("unauthorized", "This sign-in is no longer valid.", 401)
    auth.sessions.revoke_session(session.username, session.id)
    return Success()


def _phone(request: Request):
    """The calling phone's session. Browsers manage devices at /auth/sessions instead."""
    service = DeviceService(get_auth_service())
    phone = service.authenticate_mobile(_bearer_from(request) or "")
    if not phone:
        raise AuthFlowError("unauthorized", "Only a signed-in FiestaBoard phone app can manage TVs here.", 401)
    return phone, service


@router.get("/tvs", response_model=PhoneTVList, responses=RESPONSES)
def phone_tvs(request: Request):
    """The account's signed-in TVs, newest first, for the phone app. Phone sign-in only.

    Lists TV sign-ins only, never browsers or phones (those are managed from
    the web app). ``approved_by_you`` marks the TVs whose code this phone approved.
    """
    phone, service = _phone(request)
    return PhoneTVList(tvs=service.phone_tv_rows(phone))


@router.delete("/tvs/{session_id}", response_model=Success, responses=errors(401, 403, 404, 429, 503))
def revoke_phone_tv(session_id: str, request: Request):
    """Sign out one of the account's TVs from the phone app. TVs only: anything else is 404.

    Limited to 20 attempts a minute per phone, misses included, and audited.
    """
    phone, service = _phone(request)
    service.revoke_tv(phone, session_id)
    return Success()
