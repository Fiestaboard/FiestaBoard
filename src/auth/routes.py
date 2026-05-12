"""FastAPI router exposing the ``/auth/*`` endpoints."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from .service import (
    AlreadySetup,
    InvalidCredentials,
    SESSION_COOKIE_NAME,
    SetupRequired,
    auth_mode,
    get_auth_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Models ----------------------------------------------------------------


class StatusResponse(BaseModel):
    enabled: bool
    setup_required: bool
    authenticated: bool
    username: Optional[str] = None
    # Tri-state mode + ``first_run`` so the UI can show the opt-in /
    # opt-out picker on a brand-new install. ``first_run`` is true iff
    # the admin hasn't recorded a preference and the env var is unset.
    mode: str = "disabled"
    first_run: bool = False


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=1024)


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    new_password: str = Field(..., min_length=8, max_length=1024)


class ChangeUsernameRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    new_username: str = Field(..., min_length=1, max_length=64)


class PreferenceRequest(BaseModel):
    # ``True`` -> persist "enabled" (admin must then call /setup).
    # ``False`` -> persist "disabled" (auth becomes a no-op).
    enabled: bool


class SimpleResponse(BaseModel):
    status: str
    username: Optional[str] = None


# --- Cookie helpers --------------------------------------------------------


def _is_secure_request(request: Request) -> bool:
    """Decide whether to set the ``Secure`` cookie flag.

    We trust the ``X-Forwarded-Proto`` header set by nginx, falling back to
    the request scheme. Setting Secure on an http connection would prevent
    the cookie from ever being sent back, breaking pure-local installs.
    """
    fwd = request.headers.get("x-forwarded-proto", "").lower()
    if fwd == "https":
        return True
    return request.url.scheme == "https"


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=7 * 24 * 3600,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


# --- Brute-force throttle --------------------------------------------------

# Tiny in-memory throttle. Not a substitute for a real WAF / fail2ban, but
# stops casual password-guessing without adding any infrastructure. Keyed
# on the remote client address.
_FAILED_ATTEMPTS: dict = {}
_LOCKOUT_THRESHOLD = 10
_LOCKOUT_WINDOW_SECONDS = 60


def _client_ip(request: Request) -> str:
    # Behind nginx we expect X-Forwarded-For; fall back to direct peer.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _check_lockout(ip: str) -> None:
    now = time.time()
    attempts = [t for t in _FAILED_ATTEMPTS.get(ip, []) if now - t < _LOCKOUT_WINDOW_SECONDS]
    _FAILED_ATTEMPTS[ip] = attempts
    if len(attempts) >= _LOCKOUT_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
        )


def _record_failure(ip: str) -> None:
    _FAILED_ATTEMPTS.setdefault(ip, []).append(time.time())


def _clear_failures(ip: str) -> None:
    _FAILED_ATTEMPTS.pop(ip, None)


# --- Endpoints -------------------------------------------------------------


@router.get("/status", response_model=StatusResponse)
async def auth_status(request: Request) -> StatusResponse:
    """Report whether auth is enabled, set-up, and whether the caller is logged in.

    Always public so the web UI can decide whether to redirect to /login.
    """
    svc = get_auth_service()
    mode = auth_mode()
    enabled = mode in ("enabled", "undecided")
    has_user = svc.has_user()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    username = svc.verify_session(cookie) if cookie else None
    return StatusResponse(
        enabled=enabled,
        setup_required=enabled and not has_user,
        authenticated=bool(username),
        username=username,
        mode=mode,
        first_run=mode == "undecided" and not has_user,
    )


@router.post("/preference", response_model=SimpleResponse)
async def auth_preference(payload: PreferenceRequest) -> SimpleResponse:
    """Record the admin's first-run auth on/off choice.

    Only valid when:

    * The env var ``FIESTABOARD_AUTH_ENABLED`` is unset (it always wins).
    * No user has been provisioned yet — once an account exists the
      decision is "enabled" and disabling must go through a future
      password-gated endpoint to avoid drive-by lockouts.
    """
    env_raw = os.environ.get("FIESTABOARD_AUTH_ENABLED", "").strip().lower()
    if env_raw:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auth mode is pinned by FIESTABOARD_AUTH_ENABLED.",
        )
    svc = get_auth_service()
    if svc.has_user():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A user already exists. Sign in and use the account "
                "settings to change preferences."
            ),
        )
    svc.set_auth_preference("enabled" if payload.enabled else "disabled")
    return SimpleResponse(status="ok")


@router.post("/setup", response_model=SimpleResponse, status_code=201)
async def auth_setup(payload: SetupRequest, request: Request, response: Response) -> SimpleResponse:
    """Create the first user. Only callable when no user exists yet."""
    svc = get_auth_service()
    if svc.has_user():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user has already been created. Use /auth/login.",
        )
    try:
        svc.create_initial_user(payload.username, payload.password)
    except AlreadySetup:
        # Race with another setup call.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already set up")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # Log them in straight away so the UI can hand control to the dashboard.
    token = svc.authenticate(payload.username, payload.password)
    _set_session_cookie(response, request, token)
    logger.info("Initial user '%s' created", payload.username)
    return SimpleResponse(status="ok", username=payload.username)


@router.post("/login", response_model=SimpleResponse)
async def auth_login(payload: LoginRequest, request: Request, response: Response) -> SimpleResponse:
    """Verify credentials and issue a session cookie."""
    ip = _client_ip(request)
    _check_lockout(ip)
    svc = get_auth_service()
    try:
        token = svc.authenticate(payload.username, payload.password)
    except SetupRequired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No user has been created. Call /auth/setup first.",
        )
    except InvalidCredentials:
        _record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    _clear_failures(ip)
    _set_session_cookie(response, request, token)
    return SimpleResponse(status="ok", username=payload.username)


@router.post("/logout", response_model=SimpleResponse)
async def auth_logout(response: Response) -> SimpleResponse:
    """Clear the session cookie."""
    _clear_session_cookie(response)
    return SimpleResponse(status="ok")


@router.post("/change-password", response_model=SimpleResponse)
async def auth_change_password(
    payload: ChangePasswordRequest, request: Request, response: Response
) -> SimpleResponse:
    """Change the logged-in user's password."""
    svc = get_auth_service()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    username = svc.verify_session(cookie) if cookie else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        svc.change_password(username, payload.current_password, payload.new_password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # Mint a fresh session under the bumped sessions_valid_after watermark
    # so the user stays signed in and any previously-issued cookies are
    # implicitly revoked.
    new_token = svc.authenticate(username, payload.new_password)
    _set_session_cookie(response, request, new_token)
    return SimpleResponse(status="ok", username=username)


@router.post("/change-username", response_model=SimpleResponse)
async def auth_change_username(
    payload: ChangeUsernameRequest, request: Request, response: Response
) -> SimpleResponse:
    """Rename the logged-in user, gated by their current password."""
    svc = get_auth_service()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    username = svc.verify_session(cookie) if cookie else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        new_username = svc.change_username(
            username, payload.current_password, payload.new_username
        )
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # The username rename bumped ``sessions_valid_after_ms``, so the old
    # cookie is now invalid. Issue a fresh session under the new name.
    new_token = svc.authenticate(new_username, payload.current_password)
    _set_session_cookie(response, request, new_token)
    return SimpleResponse(status="ok", username=new_username)
