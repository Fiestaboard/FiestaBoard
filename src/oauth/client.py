"""HTTP calls to an OAuth provider's token and device endpoints.

Kept apart from the service so tests can substitute the transport and so the
one place that ever holds a client secret on the wire is small enough to read.
Nothing here logs a request or response body.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote_plus

import requests

from .errors import ProviderError, TokenEndpointError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 15
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
DEFAULT_DEVICE_INTERVAL_SECONDS = 5
#: Client authentication at the token endpoint (RFC 6749 §2.3.1).
AUTH_METHOD_POST = "post"
AUTH_METHOD_BASIC = "basic"

#: Twitch reports token-endpoint errors as ``{"status": 400, "message": ...}``
#: with no ``error`` key. These messages map to the RFC 6749/8628 codes.
_MESSAGE_ERRORS = {
    "authorization_pending": "authorization_pending",
    "slow_down": "slow_down",
    "expired_token": "expired_token",
    "access_denied": "access_denied",
    "invalid device code": "expired_token",
    "invalid refresh token": "invalid_grant",
}


class Transport(Protocol):
    """POST a form and return ``(status_code, parsed JSON body)``.

    ``headers`` is passed only when a request needs one (HTTP Basic client
    authentication), so a two-argument transport keeps working for the rest.
    """

    def __call__(self, url: str, form: dict[str, str]) -> tuple[int, Any]:
        """Send *form* to *url*; raise :class:`ProviderError` if it cannot be reached."""


def post_form(url: str, form: dict[str, str], headers: dict[str, str] | None = None) -> tuple[int, Any]:
    """The production :class:`Transport`."""
    try:
        response = requests.post(
            url,
            data=form,
            # GitHub answers form-encoded unless asked for JSON.
            headers={"Accept": "application/json", **(headers or {})},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ProviderError(f"Could not reach the sign-in provider ({type(exc).__name__}).") from exc
    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise ProviderError(f"The sign-in provider answered HTTP {response.status_code} without JSON.") from exc


class HttpTransport(Protocol):
    """Send a JSON-answering request and return ``(status_code, parsed JSON body)``.

    For providers that do not speak the RFC 6749 form protocol: a JSON body
    (OpenRouter's key exchange) or custom headers and GET (Plex PINs).
    """

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        form: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        """Send the request; raise :class:`ProviderError` if it cannot be reached."""


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    form: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """The production :class:`HttpTransport`."""
    try:
        response = requests.request(
            method,
            url,
            data=form,
            json=json_body,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ProviderError(f"Could not reach the sign-in provider ({type(exc).__name__}).") from exc
    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise ProviderError(f"The sign-in provider answered HTTP {response.status_code} without JSON.") from exc


@dataclass(frozen=True)
class TokenResponse:
    """A successful token-endpoint answer."""

    access_token: str
    token_type: str
    refresh_token: str
    #: Lifetime in seconds, or ``None`` when the provider did not say.
    expires_in: int | None
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class DeviceAuthorization:
    """A successful device-authorization answer (RFC 8628 §3.2)."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


def _parse_scopes(raw: Any) -> tuple[str, ...]:
    # RFC 6749 says space-delimited; GitHub sends commas; Twitch a JSON array.
    if isinstance(raw, list):
        return tuple(part for part in raw if isinstance(part, str) and part)
    if not isinstance(raw, str):
        return ()
    return tuple(part for part in raw.replace(",", " ").split() if part)


def _positive_int(raw: Any) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _raise_for_oauth_error(status: int, body: Any) -> dict[str, Any]:
    """Return *body* when it is a success object; raise otherwise.

    Some providers (GitHub) report an OAuth error with HTTP 200, so the body
    is what decides, not the status code.
    """
    if not isinstance(body, dict):
        raise ProviderError(f"The sign-in provider answered HTTP {status} with an unexpected body.")
    message = body.get("message")
    if isinstance(message, str) and message.strip().lower() in _MESSAGE_ERRORS:
        raise TokenEndpointError(_MESSAGE_ERRORS[message.strip().lower()])
    if "error" in body:
        raise TokenEndpointError(str(body["error"]), str(body.get("error_description", "")))
    if status >= 400:
        raise ProviderError(f"The sign-in provider answered HTTP {status}.")
    return body


class ProviderClient:
    """Speaks to one provider's endpoints over an injectable transport."""

    def __init__(self, transport: Transport = post_form, http: HttpTransport = request_json) -> None:
        self._transport = transport
        self.http = http

    def exchange_key(self, token_url: str, *, code: str, code_verifier: str) -> TokenResponse:
        """Trade a code for an API key (the ``key_exchange`` flow): JSON in, ``{"key"}`` out.

        The key does not expire and there is no refresh token.
        """
        status, body = self.http(
            "POST",
            token_url,
            headers={"Accept": "application/json"},
            json_body={"code": code, "code_verifier": code_verifier, "code_challenge_method": "S256"},
        )
        if isinstance(body, dict) and "error" in body and not isinstance(body["error"], str):
            # OpenRouter nests its error: {"error": {"code": 400, "message": "..."}}.
            raise TokenEndpointError("key_exchange_failed")
        body = _raise_for_oauth_error(status, body)
        key = body.get("key")
        if not isinstance(key, str) or not key:
            raise ProviderError("The sign-in provider answered without a key.")
        return TokenResponse(access_token=key, token_type="Bearer", refresh_token="", expires_in=None, scopes=())

    def _token_request(
        self,
        token_url: str,
        form: dict[str, str],
        client_secret: str,
        *,
        client_id_param: str = "client_id",
        auth_method: str = AUTH_METHOD_POST,
    ) -> TokenResponse:
        if client_secret and auth_method == AUTH_METHOD_BASIC:
            # client_secret_basic: the credentials go in the header and nowhere
            # else (one authentication method per request, RFC 6749 §2.3).
            form = dict(form)
            client_id = form.pop(client_id_param, "")
            credentials = f"{quote_plus(client_id)}:{quote_plus(client_secret)}".encode()
            headers = {"Authorization": "Basic " + base64.b64encode(credentials).decode("ascii")}
            reply = self._transport(token_url, form, headers=headers)  # type: ignore[call-arg]
        else:
            if client_secret:
                form = {**form, "client_secret": client_secret}
            reply = self._transport(token_url, form)
        body = _raise_for_oauth_error(*reply)
        data = body.get("data")
        if "access_token" not in body and isinstance(data, list) and data and isinstance(data[0], dict):
            # Instagram wraps the code-exchange answer: {"data": [{...}]}.
            body = data[0]
        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ProviderError("The sign-in provider answered without an access token.")
        refresh_token = body.get("refresh_token")
        return TokenResponse(
            access_token=access_token,
            token_type=str(body.get("token_type") or "Bearer"),
            refresh_token=refresh_token if isinstance(refresh_token, str) else "",
            expires_in=_positive_int(body.get("expires_in")),
            scopes=_parse_scopes(body.get("scope")),
        )

    def exchange_code(
        self,
        token_url: str,
        *,
        code: str,
        redirect_uri: str,
        client_id: str,
        code_verifier: str,
        client_secret: str = "",
        client_id_param: str = "client_id",
        extra_form: dict[str, str] | None = None,
        auth_method: str = AUTH_METHOD_POST,
    ) -> TokenResponse:
        """Trade an authorization code (plus PKCE verifier) for tokens."""
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            client_id_param: client_id,
            "code_verifier": code_verifier,
            **(extra_form or {}),
        }
        return self._token_request(
            token_url, form, client_secret, client_id_param=client_id_param, auth_method=auth_method
        )

    def refresh(
        self,
        token_url: str,
        *,
        refresh_token: str,
        client_id: str,
        client_secret: str = "",
        client_id_param: str = "client_id",
        extra_form: dict[str, str] | None = None,
        auth_method: str = AUTH_METHOD_POST,
    ) -> TokenResponse:
        """Trade a refresh token for a new access token.

        *extra_form* adds fields a provider wants on refresh (WHOOP: ``scope``).
        """
        form = {
            **(extra_form or {}),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            client_id_param: client_id,
        }
        return self._token_request(
            token_url, form, client_secret, client_id_param=client_id_param, auth_method=auth_method
        )

    def start_device_authorization(
        self,
        device_authorization_url: str,
        *,
        client_id: str,
        scopes: tuple[str, ...],
        client_id_param: str = "client_id",
        scope_param: str = "scope",
        scope_separator: str = " ",
    ) -> DeviceAuthorization:
        """Ask the provider for a device code and the code the user types."""
        form = {client_id_param: client_id}
        if scopes:
            form[scope_param] = scope_separator.join(scopes)
        body = _raise_for_oauth_error(*self._transport(device_authorization_url, form))
        device_code = body.get("device_code")
        user_code = body.get("user_code")
        # Google spells it verification_url.
        verification_uri = body.get("verification_uri") or body.get("verification_url")
        expires_in = _positive_int(body.get("expires_in"))
        if not (isinstance(device_code, str) and isinstance(user_code, str) and isinstance(verification_uri, str)):
            raise ProviderError("The sign-in provider's device authorization answer is incomplete.")
        if not device_code or not user_code or not verification_uri or expires_in is None:
            raise ProviderError("The sign-in provider's device authorization answer is incomplete.")
        complete = body.get("verification_uri_complete")
        return DeviceAuthorization(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=complete if isinstance(complete, str) else "",
            expires_in=expires_in,
            interval=_positive_int(body.get("interval")) or DEFAULT_DEVICE_INTERVAL_SECONDS,
        )

    def poll_device_token(
        self,
        token_url: str,
        *,
        device_code: str,
        client_id: str,
        client_secret: str = "",
        client_id_param: str = "client_id",
        extra_form: dict[str, str] | None = None,
        auth_method: str = AUTH_METHOD_POST,
    ) -> TokenResponse:
        """Ask whether the user has approved the device code yet.

        Raises :class:`TokenEndpointError` with ``authorization_pending`` or
        ``slow_down`` while they have not.
        """
        form = {"grant_type": DEVICE_GRANT_TYPE, "device_code": device_code, client_id_param: client_id}
        form.update(extra_form or {})
        return self._token_request(
            token_url, form, client_secret, client_id_param=client_id_param, auth_method=auth_method
        )
