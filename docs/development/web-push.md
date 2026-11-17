---
description: Browser enrollment, private VAPID storage, and bounded web push delivery.
---

# Web push

FiestaBoard can register browser push subscriptions and deliver encrypted alerts.
The browser must be signed in, have granted notification permission, and run in a
secure context (HTTPS, or a browser-supported localhost exception). HTTPS setup
is separate from this sender. There is no UI in this backend change.

Set `FIESTABOARD_WEB_PUSH_SUBJECT` to an operator contact such as
`mailto:admin@example.com` or an HTTPS contact URL before sending. This value
appears in the VAPID claim sent to the browser's push provider. Do not put a
credential in it. VAPID signing keys are generated automatically on first use and
persisted in `data/web-push.sqlite3` (or `FIESTABOARD_DATA_DIR`).

## Browser contract

Paths below are API paths; the web portal prefixes them with `/api`. Their typed
OpenAPI schemas are published at `/api/internal/openapi.json`. They are internal
browser endpoints, so they do not appear in the public `/v1` API reference.

Every request requires a live browser session cookie, including when hub sign-in
is disabled. Native TV/phone and API bearer tokens cannot manage push. Mutations
also require a trusted portal `Origin`, JSON (except DELETE), and `X-CSRF-Token`
from `GET /auth/sessions/context`. Responses are `Cache-Control: no-store`.

| Method and path | Request | Result |
| --- | --- | --- |
| `GET /push/status` | None | Current account/browser consent and public VAPID key |
| `PUT /push/preferences` | `{"enabled":true}` | Set consent for the signed-in account generation |
| `PUT /push/subscription` | `{"enabled":true,"subscription":<PushSubscription.toJSON()>}` | Register or replace this browser session's subscription and device consent |
| `DELETE /push/subscription` | None | Erase this browser's subscription |
| `POST /push/test` | `{}` | Fixed test text to the current browser only, at most once a minute |

Status has this shape:

```json
{
  "public_key": "base64url-uncompressed-P256-public-key",
  "user_enabled": false,
  "device_enabled": false,
  "subscribed": false,
  "expiration_time": null,
  "event_sources": [],
  "test_available": false
}
```

Both consent flags default to false. Registration does not grant account consent.
Setting account consent does not register or enable another browser. A device is
a browser session: signing out or revoking it stops delivery, and signing in
again requires registering the browser subscription again. Account-wide session
invalidation also clears effective account consent. Browser permission remains
separate from these server flags.

`public_key` is the `applicationServerKey` for `PushManager.subscribe` after
base64url decoding. Subscription `keys.p256dh` must be an uncompressed P-256 point;
`keys.auth` is a 16-byte secret, both canonical base64url without padding. `expirationTime`
is an optional integer Unix timestamp in milliseconds. An already expired
subscription is rejected. Endpoints and encryption keys are never returned.

Only canonical HTTPS URLs on `fcm.googleapis.com`,
`updates.push.services.mozilla.com`, and `web.push.apple.com` are supported.
Other providers, custom ports, credentials in URLs, fragments, and non-HTTPS
URLs are rejected. The sender checks all DNS answers for public addresses and
connects directly to one checked address while TLS verifies the original
hostname. It follows no redirects and ignores HTTP proxy environment variables.

Requests are limited to 8 KiB, endpoints to 2,048 characters, and subscriptions
to 20 per account / 100 per install. Expired subscriptions return 400; invalid input returns a redacted 422;
identity failures return 401/403, duplicate endpoint ownership and missing test
consent return 409, request size returns 413, and capacity/cooldown returns 429.
Storage/configuration failure or a rejected test delivery returns 503.

The test response is `{sent, failed, skipped, expired}`, with integer counts.
`sent` means the provider accepted the message, not that the browser displayed
it. The test contains only the fixed text “Notifications are working on this
browser.” It accepts no caller-supplied recipient, endpoint, or message.
`test_available` means the contact is configured and both consent flags are on.

## Event producers

H15 provides the sender and test path. `event_sources` is deliberately empty:
the four settings in web 2.13 (display offline, override ended, hub/plugin update
available, and Silence Schedule held a message) still need production event
integration and per-category preferences. Clients must not present them as
working merely because enrollment succeeds.

Trusted hub producers can call:

```python
from src.auth.service import get_auth_service
from src.push.notifier import PushNotifier
from src.push.store import get_push_store

result = PushNotifier(get_push_store(), get_auth_service()).notify(
    username,
    {"title": "FiestaBoard", "body": "A display needs attention.", "url": "/"},
    ttl_seconds=300,
)
```

The caller owns event selection and deduplication; there is no durable queue.
Only alert text should be supplied, never board content, credentials, or plugin
configuration. The payload accepts `title` (1–80 characters), `body` (up to 240),
a hub-relative `url` (up to 1,024), and `tag` (up to 64). TTL is 1–86,400 seconds. The complete serialized UTF-8 payload must fit in 3,993 bytes.
Delivery runs synchronously; producers should schedule it outside display/render
and API event-loop work. At most two calls send concurrently per process.

Each subscription gets at most three attempts. Network failures, 429 and 5xx
responses retry with bounded 1–5 second backoff; other failures do not. Provider
`Retry-After` waits longer than five seconds stop this delivery instead of retrying early. Socket operations time out after at most five seconds;
a notification stops starting attempts after its TTL or a 30-second delivery
budget. DNS resolution uses the operating system resolver, whose own timeout
can extend elapsed time. There is no guarantee of background delivery after a
process restart. Expired subscriptions and provider 404/410 responses remove the
matching stored revision; an old response cannot delete a new registration.

After DNS resolution and TLS setup, delivery rechecks consent and deadlines before any HTTP write and refreshes the provider TTL. Every attempt rechecks account generation, active browser session and both
consent revisions. Opt-out followed by opt-in does not revive an older retry.
A message already accepted by the provider cannot be recalled by signing out.

## Persistence and recovery

The database and initialization lock are owner-only (0600); writes and key
creation are transactional. The private key is stored locally with filesystem
access controls, not encrypted with a second key stored beside it. Protect the
host and the data volume as credentials. Neither application backups nor
pre-update exports include push keys or subscriptions. A restored install needs
fresh browser registration; a full private data-volume backup preserves keys.

An unreadable or corrupt existing store fails closed and never silently rotates
the VAPID key. Restore the private store from a trusted volume backup, or stop
the hub and deliberately remove the push store to reset enrollment. After that
reset, browsers must unsubscribe and resubscribe using the new public key.
Never attach the database, subscription JSON, or raw provider errors to support
reports. The sender does not log payloads, endpoints, keys, or provider bodies.
