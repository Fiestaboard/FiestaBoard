"""Bounded synchronous notification delivery, callable by trusted hub producers.

There is no durable queue: the caller owns event policy. Every attempt checks
account generation, live browser session and both unchanged consent revisions.
"""

import math
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from requests import RequestException

from .models import DeliveryResult, Notification
from .service import configured_subject
from .transport import DeliveryCancelled, PinnedTransport, UnsafeEndpoint

_SEND_SLOTS = threading.BoundedSemaphore(2)


def _retry_delay(response, attempt):
    value = response.headers.get("Retry-After", "") if response is not None else ""
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 2**attempt
    # Never retry earlier than a provider requested. Long waits belong to a
    # durable producer queue; this bounded synchronous sender simply stops.
    if not math.isfinite(delay) or delay > 5:
        return None
    return max(1, delay)


class PushNotifier:
    def __init__(
        self, store, auth, *, transport=None, sleep=time.sleep, clock_ms=None, monotonic=time.monotonic, subject=None
    ):
        self.store = store
        self.auth = auth
        self.transport = transport
        self.sleep = sleep
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.monotonic = monotonic
        self.subject = subject or configured_subject()

    def _authorized(self, row):
        user = self.auth.get_user(row["username"])
        if not user or int(user.get("sessions_valid_after_ms", 0)) != row["generation"]:
            return False
        sessions = self.auth.sessions.list_sessions(row["username"])
        return self.store.eligible(row) and any(
            s.id == row["session_id"] and s.kind == "browser" and s.account_generation == row["generation"]
            for s in sessions
        )

    def notify(self, username, payload, ttl_seconds=300, *, session_id=None):
        """Deliver at most 20 subscriptions within 30s, three attempts each.

        ``session_id`` narrows a test to its authenticated browser. Production
        callers pass only server-owned alert text; payloads never enter logs.
        """
        data = Notification.model_validate(payload).model_dump_json()
        if len(data.encode("utf-8")) > 3993:
            raise ValueError("Push payload exceeds the encrypted record size limit")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("Push TTL must be 1..86400 seconds")
        if not self.subject:
            raise ValueError("A web push contact subject is required")
        rows = [row for row in self.store.candidates(username) if session_id is None or row["session_id"] == session_id]
        result = DeliveryResult()
        if not _SEND_SLOTS.acquire(blocking=False):
            result.skipped = len(rows)
            return result
        try:
            deadline = self.monotonic() + 30
            expires_ms = self.clock_ms() + ttl_seconds * 1000
            for row in rows:
                outcome = self._deliver(row, data, expires_ms, deadline)
                setattr(result, outcome, getattr(result, outcome) + 1)
            return result
        finally:
            _SEND_SLOTS.release()

    def _deliver(self, row, data, expires_ms, deadline):
        for attempt in range(3):
            now = self.clock_ms()
            if row["expires_ms"] is not None and row["expires_ms"] <= now:
                self.store.delete_if_current(row)
                return "expired"
            if now >= expires_ms or self.monotonic() >= deadline or not self._authorized(row):
                return "skipped"
            response = None
            try:
                transport = (
                    self.transport
                    if self.transport is not None
                    else PinnedTransport(guard=lambda: self._transport_guard(row, expires_ms, deadline))
                )
                response = webpush(
                    {"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}},
                    data=data,
                    vapid_private_key=Vapid(self.store.private_key),
                    vapid_claims={"sub": self.subject},
                    ttl=max(1, (expires_ms - now) // 1000),
                    timeout=min(5, deadline - self.monotonic()),
                    requests_session=transport,
                    verbose=False,
                )
                status = response.status_code
            except WebPushException as exc:
                response = exc.response
                status = response.status_code if response is not None else 0
            except RequestException:
                status = 0
            except DeliveryCancelled:
                return "skipped"
            except (UnsafeEndpoint, ValueError):
                return "failed"
            if 200 <= status < 300:
                return "sent"
            if status in (404, 410):
                self.store.delete_if_current(row)
                return "expired"
            if status not in (0, 429) and not 500 <= status < 600:
                return "failed"
            if attempt == 2:
                return "failed"
            delay = _retry_delay(response, attempt)
            if delay is None or self.monotonic() + delay >= deadline or self.clock_ms() + delay * 1000 >= expires_ms:
                return "skipped"
            self.sleep(delay)
        return "failed"

    def _transport_guard(self, row, expires_ms, deadline):
        now = self.clock_ms()
        if (
            now >= expires_ms
            or self.monotonic() >= deadline
            or (row["expires_ms"] is not None and row["expires_ms"] <= now)
            or not self._authorized(row)
        ):
            raise DeliveryCancelled()
        return max(1, (expires_ms - now) // 1000)
