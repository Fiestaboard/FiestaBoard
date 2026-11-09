"""Mint a one-time password-reset code, from inside the container (H17).

Run where only the owner can::

    docker compose exec fiestaboard python -m src.auth.password_reset

Whoever can run that already controls the hub (its data volume, signing key
and account file), so the reset adds no remote attack surface: no network
request can start one. The code works once, for 15 minutes, and only the
newest one is live. Only its digest is stored, in ``auth_sessions.sqlite3``
(the running server reads it per request). It is printed here, never logged.
Use it at ``/reset-password`` (``POST /auth/password-reset``).

This never writes ``auth.json``: the running server caches that file and
rewrites it whole.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .session_store import SessionStore

#: The same audit stream as sign-outs (src/auth/device_service.py).
audit = logging.getLogger("src.auth.audit")

#: How long a reset code works.
RESET_TTL_MS = 15 * 60 * 1000


def _usernames(auth_file: Path) -> list[str]:
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(u["username"]) for u in data.get("users", []) if isinstance(u, dict) and u.get("username")]


def redeem(code: str, new_password: str) -> str | None:
    """Use *code* to set *new_password*: the account's username, or ``None``
    when the code is wrong, used, superseded, expired, or names an account
    that no longer exists (``POST /auth/password-reset``)."""
    from .service import InvalidCredentials, get_auth_service

    auth = get_auth_service()
    username = auth.sessions.consume_password_reset(code)
    if username is None:
        return None
    try:
        auth.reset_password(username, new_password)
    except InvalidCredentials:
        return None
    audit.info("Password reset with a recovery code for %s", username)
    return username


def main(argv: list[str] | None = None, *, auth_file: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.auth.password_reset",
        description="Print a one-time code to reset the FiestaBoard account password.",
    )
    parser.add_argument("--username", help="The account to reset (default: the only account).")
    args = parser.parse_args(argv)

    if auth_file is None:
        from .service import _default_auth_file

        auth_file = _default_auth_file()
    users = _usernames(auth_file)
    if not users:
        print("This hub has no account yet. Open the FiestaBoard web app to create one.")
        return 1
    username = args.username or users[0]
    if username not in users:
        print(f"There is no account named {username!r} on this hub.")
        return 1

    store = SessionStore(auth_file.parent / "auth_sessions.sqlite3")
    code, expires_ms = store.create_password_reset(username, RESET_TTL_MS)
    expires = datetime.fromtimestamp(expires_ms / 1000, UTC).replace(microsecond=0).isoformat()
    print(f"One-time password reset code for {username} (works once, for 15 minutes, until {expires}):")
    print()
    print(f"    {code}")
    print()
    print("Open FiestaBoard at /reset-password#code=" + code)
    print("or enter the code on its Reset password page, then choose a new password.")
    print("Every signed-in browser, TV and phone will be signed out.")
    return 0


if __name__ == "__main__":  # pragma: no cover - the CLI entry point
    sys.exit(main())
