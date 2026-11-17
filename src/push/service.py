"""Application orchestration for browser push settings; no HTTP or secrets in errors."""

import os
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

from src.auth.service import get_auth_service

from .models import PushStatus
from .store import PushConflict, PushLimit, get_push_store


class PushError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def configured_subject():
    value = os.environ.get("FIESTABOARD_WEB_PUSH_SUBJECT", "")
    parts = urlsplit(value)
    if (
        len(value) <= 512
        and not any(c.isspace() or ord(c) < 32 for c in value)
        and (
            (parts.scheme == "mailto" and "@" in parts.path)
            or (parts.scheme == "https" and parts.hostname and not parts.username and not parts.fragment)
        )
    ):
        return value
    return None


@contextmanager
def storage_errors():
    try:
        yield
    except PushConflict:
        raise PushError(409, "Subscription is already registered") from None
    except PushLimit:
        raise PushError(429, "Push subscription limit reached") from None
    except (OSError, sqlite3.Error, ValueError):
        raise PushError(503, "Push storage unavailable") from None


def status(session):
    with storage_errors():
        store = get_push_store()
        state = store.status(session)
        return PushStatus(
            public_key=store.public_key,
            **state,
            test_available=bool(configured_subject() and state["user_enabled"] and state["device_enabled"]),
        )


def set_preferences(session, payload):
    with storage_errors():
        get_push_store().set_user_enabled(session, payload.enabled)
    return status(session)


def subscribe(session, payload):
    if (
        payload.subscription.expirationTime is not None
        and payload.subscription.expirationTime <= time.time_ns() // 1_000_000
    ):
        raise PushError(400, "Subscription has expired")
    with storage_errors():
        store = get_push_store()
        auth = get_auth_service()
        for owner in store.owners():
            candidates = store.cleanup_candidates(owner)
            store.prune(candidates, auth.sessions.list_sessions(owner) if auth.get_user(owner) else [])
        store.subscribe(session, payload)
    return status(session)


def unsubscribe(session):
    with storage_errors():
        get_push_store().unsubscribe(session)
    return status(session)


def send_test(session):
    current = status(session)
    if not current.user_enabled or not current.device_enabled or not current.subscribed:
        raise PushError(409, "Enable notifications for this user and browser first")
    subject = configured_subject()
    if not subject:
        raise PushError(503, "Configure FIESTABOARD_WEB_PUSH_SUBJECT before sending notifications")
    with storage_errors():
        store = get_push_store()
        if not store.reserve_test(session, time.time_ns() // 1_000_000):
            raise PushError(429, "Wait one minute before sending another test")
        from .notifier import PushNotifier

        return PushNotifier(store, get_auth_service(), subject=subject).notify(
            session.username,
            {"title": "FiestaBoard", "body": "Notifications are working on this browser."},
            session_id=session.id,
        )
