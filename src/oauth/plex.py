"""Plex sign-in by PIN (the ``plex_pin`` flow).

Plex does not do OAuth. An app creates a PIN at plex.tv, sends the browser to
app.plex.tv with it, and polls the PIN until Plex attaches a token. The
endpoints are Plex's own, so they are constants here, not manifest fields.
Plex identifies the app by a per-install ``X-Plex-Client-Identifier``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from . import install_id
from .client import HttpTransport
from .errors import ProviderError
from .overrides import override_url

PINS_URL = "https://plex.tv/api/v2/pins"
AUTH_URL = "https://app.plex.tv/auth#?"
POLL_INTERVAL_SECONDS = 2
DEFAULT_PIN_LIFETIME_SECONDS = 900

_IDENTIFIER_FILENAME = ".oauth_client_identifier"


def load_client_identifier(data_dir: Path) -> str:
    """The per-install client identifier Plex knows this board by, created on first use."""
    return install_id.load_or_create(Path(data_dir) / _IDENTIFIER_FILENAME)


def headers(client_identifier: str, product: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "X-Plex-Client-Identifier": client_identifier,
        "X-Plex-Product": product,
    }


@dataclass(frozen=True)
class Pin:
    id: str
    code: str
    expires_in: int


class PinGone(ProviderError):
    """Plex no longer knows the PIN: it expired or was used."""


def _lifetime(body: dict[str, Any], now: float) -> int:
    expires_in = body.get("expiresIn")
    if isinstance(expires_in, int) and expires_in > 0:
        return expires_in
    expires_at = body.get("expiresAt")
    if isinstance(expires_at, str):
        try:
            remaining = int(datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp() - now)
        except ValueError:
            remaining = 0
        if remaining > 0:
            return remaining
    return DEFAULT_PIN_LIFETIME_SECONDS


def create_pin(http: HttpTransport, client_identifier: str, product: str, now: float) -> Pin:
    """Ask plex.tv for a new strong PIN."""
    status, body = http(
        "POST", f"{override_url(PINS_URL)}?strong=true", headers=headers(client_identifier, product), form={}
    )
    if status >= 400 or not isinstance(body, dict):
        raise ProviderError(f"Plex answered HTTP {status} when asked for a sign-in PIN.")
    pin_id, code = body.get("id"), body.get("code")
    if not isinstance(pin_id, int | str) or not pin_id or not isinstance(code, str) or not code:
        raise ProviderError("Plex's sign-in PIN answer is incomplete.")
    return Pin(id=str(pin_id), code=code, expires_in=_lifetime(body, now))


def check_pin(http: HttpTransport, pin_id: str, client_identifier: str, product: str) -> str:
    """The token Plex attached to the PIN, or ``""`` while the user has not signed in.

    Raises :class:`PinGone` when Plex no longer knows the PIN.
    """
    status, body = http(
        "GET", f"{override_url(PINS_URL)}/{quote(pin_id, safe='')}", headers=headers(client_identifier, product)
    )
    if status == 404:
        raise PinGone("The Plex sign-in PIN expired.")
    if status >= 400 or not isinstance(body, dict):
        raise ProviderError(f"Plex answered HTTP {status} when asked about the sign-in PIN.")
    token = body.get("authToken")
    return token if isinstance(token, str) else ""


def auth_url(client_identifier: str, code: str, product: str, forward_url: str = "") -> str:
    """Where to send the browser to approve the PIN."""
    params = {"clientID": client_identifier, "code": code}
    if forward_url:
        params["forwardUrl"] = forward_url
    params["context[device][product]"] = product
    return override_url(AUTH_URL) + urlencode(params)
