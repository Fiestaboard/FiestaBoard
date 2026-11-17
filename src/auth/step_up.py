"""H21s: step-up elevation for phone (``control``) sign-ins.

Tier-2 operations (installing code, host changes, AI provider changes, backups)
are listed in ``src/auth/scopes.py`` as step-up rules. A phone reaches them only
while its sign-in is *elevated*: the user re-entered the account password on
that phone (``POST /auth/device/elevate``) within the last ten minutes.

* The elevation is a row keyed on the phone's session id. It is never a token
  and never leaves the hub, so there is nothing to steal or replay.
* A revoked or expired session is never elevated (the check joins the session).
* Password attempts share the browser login's lockout counter.
* Without elevation a tier-2 route answers ``403`` with ``error`` and ``code``
  both ``step_up_required``, so the app can show its password sheet.
"""

from __future__ import annotations

from .service import AuthService

#: How long one password re-entry lasts (owner-approved: 10 minutes).
STEP_UP_SECONDS = 600

STEP_UP_REQUIRED = "step_up_required"


def elevated_until(auth: AuthService, session_id: str | None) -> int | None:
    """When *session_id*'s step-up ends (epoch ms), or None. None for a missing id."""
    if not session_id:
        return None
    return auth.sessions.elevated_until(session_id)


def is_elevated(auth: AuthService, session_id: str | None) -> bool:
    return elevated_until(auth, session_id) is not None


#: The ``403`` body of a tier-2 route reached without a step-up.
STEP_UP_REQUIRED_BODY = {
    "error": STEP_UP_REQUIRED,
    "code": STEP_UP_REQUIRED,
    "detail": "Enter your password on this phone to continue.",
}
