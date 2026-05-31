"""FastAPI router exposing the ``/auth/*`` endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from .service import (
    SESSION_COOKIE_NAME,
    AlreadySetup,
    InvalidCredentials,
    SetupRequired,
    _auth_env_override,
    _remember_me_ttl_seconds,
    auth_mode,
    generate_mcp_token,
    get_auth_service,
    mcp_token_source,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Models ----------------------------------------------------------------


class StatusResponse(BaseModel):
    enabled: bool
    setup_required: bool
    authenticated: bool
    username: str | None = None
    # Tri-state mode + ``first_run`` so the UI can show the opt-in /
    # opt-out picker on a brand-new install. ``first_run`` is true iff
    # the admin hasn't recorded a preference and the env var is unset.
    mode: str = "disabled"
    first_run: bool = False


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=1024)
    # "Keep me logged in". When true the session is persisted across browser
    # restarts (long-lived cookie); when false a session cookie is issued that
    # the browser drops on close. Defaults to false for API clients.
    remember_me: bool = False


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    new_password: str = Field(..., min_length=8, max_length=1024)


class ChangeUsernameRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=1024)
    new_username: str = Field(..., min_length=1, max_length=64)


class DisableAuthRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=1024)


class PreferenceRequest(BaseModel):
    # ``True`` -> persist "enabled" (admin must then call /setup).
    # ``False`` -> persist "disabled" (auth becomes a no-op).
    enabled: bool


class SimpleResponse(BaseModel):
    status: str
    username: str | None = None


class McpTokenStatusResponse(BaseModel):
    # Whether the MCP endpoint will accept *any* bearer token right now.
    configured: bool
    # ``"env"``  -> ``FIESTABOARD_MCP_TOKEN`` is set; the UI must show
    #               "managed by ops" and hide rotate/clear controls.
    # ``"stored"`` -> token lives in ``auth.json`` and is UI-managed.
    # ``"none"`` -> nothing configured; ``/mcp`` still requires the
    #               session cookie (legacy behaviour).
    source: str


class McpTokenRotateResponse(BaseModel):
    # Returned ONCE on rotation. The plaintext token is never readable
    # again after this response — the client must show it to the user
    # immediately. The server stores it verbatim (auth.json is 0600) so
    # ``verify_mcp_bearer`` can constant-time-compare future requests.
    token: str


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


def _set_session_cookie(
    response: Response, request: Request, token: str, *, persistent: bool = True
) -> None:
    """Write the session cookie.

    When *persistent* is true the cookie gets a ``Max-Age`` (the "Keep me
    logged in" window) so it survives browser restarts. When false we omit
    ``Max-Age``/``Expires`` entirely, yielding a session cookie that the
    browser discards when it closes. The token's own ``expires_at`` still caps
    the server-side lifetime in either case.
    """
    max_age = _remember_me_ttl_seconds() if persistent else None
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
        max_age=max_age,
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
    env_raw = _auth_env_override()
    if env_raw is not None:
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already set up") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    # Log them in straight away so the UI can hand control to the dashboard.
    # New admins get a persistent session (matches the prior setup behavior).
    token = svc.authenticate(payload.username, payload.password, remember=True)
    _set_session_cookie(response, request, token, persistent=True)
    logger.info("Initial user '%s' created", payload.username)
    return SimpleResponse(status="ok", username=payload.username)


@router.post("/login", response_model=SimpleResponse)
async def auth_login(payload: LoginRequest, request: Request, response: Response) -> SimpleResponse:
    """Verify credentials and issue a session cookie."""
    ip = _client_ip(request)
    _check_lockout(ip)
    svc = get_auth_service()
    try:
        token = svc.authenticate(
            payload.username, payload.password, remember=payload.remember_me
        )
    except SetupRequired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No user has been created. Call /auth/setup first.",
        ) from None
    except InvalidCredentials:
        _record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        ) from None
    _clear_failures(ip)
    _set_session_cookie(response, request, token, persistent=payload.remember_me)
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
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
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
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    # The username rename bumped ``sessions_valid_after_ms``, so the old
    # cookie is now invalid. Issue a fresh session under the new name.
    new_token = svc.authenticate(new_username, payload.current_password)
    _set_session_cookie(response, request, new_token)
    return SimpleResponse(status="ok", username=new_username)


@router.post("/disable", response_model=SimpleResponse)
async def auth_disable(
    payload: DisableAuthRequest, request: Request, response: Response
) -> SimpleResponse:
    """Turn off auth enforcement after a password check.

    Requires both a valid session cookie *and* the current password.
    The cookie alone isn't enough — that would let a stolen-cookie
    attacker silently open the install up. The user record is
    deleted at the same time and the session cookie cleared.
    """
    if _auth_env_override() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Auth mode is pinned by FIESTABOARD_AUTH_ENABLED.",
        )
    svc = get_auth_service()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    username = svc.verify_session(cookie) if cookie else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        svc.disable_auth_for_user(username, payload.current_password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
        ) from None
    _clear_session_cookie(response)
    logger.info("Auth disabled by user '%s'", username)
    return SimpleResponse(status="ok")


# --- MCP bearer-token management ------------------------------------------
#
# These endpoints let an authenticated admin generate / rotate / revoke the
# pre-shared bearer token that external MCP clients (Claude Desktop, Claude
# Code) use to authenticate. The plaintext token is only returned by
# ``POST /auth/mcp-token`` and never read back — the UI is responsible for
# showing it to the user at rotation time.


def _require_admin(request: Request) -> str:
    """Return the logged-in username or raise 401. Shared 1-line gate."""
    svc = get_auth_service()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    username = svc.verify_session(cookie) if cookie else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return username


@router.get("/mcp-token", response_model=McpTokenStatusResponse)
async def auth_mcp_token_status(request: Request) -> McpTokenStatusResponse:
    """Report whether an MCP bearer token is configured, and from where."""
    _require_admin(request)
    source = mcp_token_source()
    return McpTokenStatusResponse(configured=source != "none", source=source)


@router.post(
    "/mcp-token",
    response_model=McpTokenRotateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def auth_mcp_token_rotate(request: Request) -> McpTokenRotateResponse:
    """Generate a fresh MCP bearer token, persist it, and return it ONCE.

    Refuses if ``FIESTABOARD_MCP_TOKEN`` is set, because the env var wins
    in :func:`~src.auth.service.mcp_token` resolution — a UI rotation
    would silently have no effect and confuse the admin.
    """
    username = _require_admin(request)
    if mcp_token_source() == "env":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "MCP token is pinned by FIESTABOARD_MCP_TOKEN environment "
                "variable. Unset it before managing the token from the UI."
            ),
        )
    token = generate_mcp_token()
    get_auth_service().set_stored_mcp_token(token)
    logger.info("MCP token rotated by user '%s'", username)
    return McpTokenRotateResponse(token=token)


@router.delete("/mcp-token", response_model=SimpleResponse)
async def auth_mcp_token_clear(request: Request) -> SimpleResponse:
    """Revoke the stored MCP bearer token.

    External MCP clients will start receiving 401 + Bearer challenge on
    their next request. (If ``FIESTABOARD_MCP_TOKEN`` is set, this only
    clears the stored fallback — the env var continues to be active.)
    """
    username = _require_admin(request)
    if mcp_token_source() == "env":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "MCP token is pinned by FIESTABOARD_MCP_TOKEN environment "
                "variable. Unset it before managing the token from the UI."
            ),
        )
    get_auth_service().set_stored_mcp_token(None)
    logger.info("MCP token revoked by user '%s'", username)
    return SimpleResponse(status="ok")
