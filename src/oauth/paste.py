"""Read what a user pasted when a sign-in did not come back on its own.

Three cases: the relay redirect failed and the user copied the address they
landed on; a provider showed a bare code (OpenRouter without a callback); or
a loopback redirect failed to load and the user copied that address. Pure: no
I/O, nothing logged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .errors import PastedCodeRejected

MAX_PASTED_LENGTH = 4096
_BARE_CODE_RE = re.compile(r"^[A-Za-z0-9._~\-]{4,2048}$")


@dataclass(frozen=True)
class PastedAuthorization:
    """What a paste said. Empty strings for anything it did not carry."""

    code: str
    state: str
    error: str
    #: A client ID the provider issued during sign-in and put in the address
    #: (OpenAI's dynamic clients). Only flows that expect one use it.
    issued_client_id: str


def _first(values: dict[str, list[str]], key: str) -> str:
    found = values.get(key)
    return found[0].strip() if found else ""


def parse_pasted(text: str) -> PastedAuthorization:
    """Parse *text* as a redirect address or a bare code; raise :class:`PastedCodeRejected` otherwise."""
    pasted = (text or "").strip()
    unreadable = PastedCodeRejected(
        "unreadable", "That doesn't look like a sign-in address or code. Copy the whole address and try again."
    )
    if not pasted or len(pasted) > MAX_PASTED_LENGTH:
        raise unreadable
    if "://" in pasted:
        parts = urlsplit(pasted)
        # The fragment first so the query, which is the standard place, wins.
        values = parse_qs(parts.fragment)
        values.update(parse_qs(parts.query))
        parsed = PastedAuthorization(
            code=_first(values, "code"),
            state=_first(values, "state"),
            error=_first(values, "error"),
            issued_client_id=_first(values, "client_id"),
        )
        if not (parsed.code or parsed.error):
            raise unreadable
        return parsed
    if _BARE_CODE_RE.match(pasted):
        return PastedAuthorization(code=pasted, state="", error="", issued_client_id="")
    raise unreadable
