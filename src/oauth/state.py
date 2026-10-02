"""Signed ``state`` values for the authorization-code flow.

``state`` is the only thing that ties a callback to a flow this board
started. It is ``<payload>.<signature>``, where the payload is base64url JSON
carrying a nonce, the connection id and an expiry, and the signature is
HMAC-SHA256 under a per-install key.

The payload also carries ``b``: the address this board was being browsed at
when the flow started. The board never reads it back. It is there for the
relay page, which has no other way to know where to send the browser, and
which treats it as a suggestion: it only forwards to a local address that the
person has approved in that browser (https://github.com/Fiestaboard/auth).

The signature alone does not stop replay — a captured ``state`` verifies as
often as it is presented. Single use comes from the service, which keeps the
nonce of every flow it started and forgets it on first use.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from .errors import InvalidState

#: How long a started flow stays valid. Long enough to sign in and approve a
#: consent screen, short enough that an abandoned flow is not left open.
STATE_TTL_SECONDS = 600

_KEY_FILENAME = ".oauth_state_key"
_MAX_STATE_LENGTH = 2048


@dataclass(frozen=True)
class StatePayload:
    """What a verified ``state`` says about the flow it belongs to."""

    nonce: str
    connection_id: str
    expires_at: int
    #: Where the relay should send the browser back to. Not trusted by anyone.
    board_url: str = ""


def load_state_key(data_dir: Path) -> bytes:
    """Return the per-install state-signing key, creating it on first use.

    A dedicated key rather than the session key in ``src/auth``: neither
    should be able to mint the other's tokens.
    """
    key_path = data_dir / _KEY_FILENAME
    if key_path.exists():
        # Raw bytes, never stripped — see src/auth/service.py::_signing_key.
        return key_path.read_bytes()
    key = secrets.token_bytes(32)
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key)
    return key


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class StateSigner:
    """Mint and verify ``state`` values under one key."""

    def __init__(self, key: bytes) -> None:
        if not key:
            raise ValueError("state signing key must not be empty")
        self._key = key

    def _signature(self, payload: str) -> str:
        return _b64encode(hmac.new(self._key, payload.encode("ascii"), hashlib.sha256).digest())

    def sign(self, payload: StatePayload) -> str:
        """Return the ``state`` string for *payload*."""
        body = json.dumps(
            {"n": payload.nonce, "c": payload.connection_id, "e": payload.expires_at, "b": payload.board_url},
            separators=(",", ":"),
        )
        encoded = _b64encode(body.encode("utf-8"))
        return f"{encoded}.{self._signature(encoded)}"

    def verify(self, state: str | None, now: float) -> StatePayload:
        """Return the payload of *state*, or raise :class:`InvalidState`.

        The signature is checked before the payload is parsed, so nothing an
        outsider wrote is interpreted.
        """
        if not state or len(state) > _MAX_STATE_LENGTH:
            raise InvalidState("invalid_state", "The sign-in response carried no usable state.")
        encoded, separator, signature = state.partition(".")
        if not separator or not encoded or not signature:
            raise InvalidState("invalid_state", "The sign-in response state is not signed.")
        if not hmac.compare_digest(self._signature(encoded), signature):
            raise InvalidState("invalid_state", "The sign-in response state was not issued by this board.")
        try:
            body = json.loads(_b64decode(encoded))
            payload = StatePayload(
                nonce=str(body["n"]),
                connection_id=str(body["c"]),
                expires_at=int(body["e"]),
                board_url=str(body.get("b", "")),
            )
        except (ValueError, KeyError, TypeError, AttributeError, binascii.Error) as exc:
            raise InvalidState("invalid_state", "The sign-in response state is malformed.") from exc
        if now >= payload.expires_at:
            raise InvalidState("expired", "The sign-in took too long. Start the connection again.")
        return payload
