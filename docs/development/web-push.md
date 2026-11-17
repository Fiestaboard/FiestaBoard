---
description: Browser enrollment, private VAPID storage, and bounded web push delivery.
---

# Web push

FiestaBoard can register browser push subscriptions and deliver encrypted alerts.
The browser must be signed in, have granted notification permission, and run in a
secure context (HTTPS, or a browser-supported localhost exception). HTTPS setup
is separate from this sender. Enrollment and test delivery are available in
**Settings > Notifications**.

Set `FIESTABOARD_WEB_PUSH_SUBJECT` to an operator contact such as
`mailto:admin@example.com` or an HTTPS contact URL before sending. This value
appears in the VAPID claim sent to the browser's push provider. Do not put a
credential in it. VAPID signing keys are generated automatically on first use and
persisted in `data/web-push.sqlite3` (or `FIESTABOARD_DATA_DIR`).

## Settings and browser enrollment

Open **Settings > Notifications** in a signed-in browser session. A session is
required even when hub sign-in is turned off. Both account and browser consent
start off, and the browser's notification permission is a separate state.

1. Turn on **Allow notifications for my account** to grant account consent.
2. Turn on **Enable on this browser** to enroll the current browser session.
   This explicit action requests browser permission when needed. Opening
   Settings or enabling account consent does not open a permission prompt.
3. Allow the browser's request, then use **Send a test** once enrollment and the
   hub's push contact are configured. Tests are limited to one per minute.

Account consent alone does not enroll a browser. Enabling another browser
requires its own permission and enrollment. The UI reports browser permission
separately from server enrollment; a browser may retain permission after its
subscription expires or its signed-in session ends. If permission is blocked,
allow notifications for the site in browser settings, then return and enable
this browser. Dismissing the permission prompt leaves enrollment off.

Browser availability also affects enrollment:

| Environment | Required action |
| --- | --- |
| Plain HTTP on a LAN address | Open the hub over HTTPS; the browser's localhost secure-context exception is for local development. |
| Embedded Home Assistant ingress page | Open the hub directly over HTTPS in its own browser tab. HTTPS on the outer Home Assistant page does not enable notification permission inside an iframe. |
| iPhone or iPad browser tab | Add FiestaBoard to the Home Screen, open the installed app, and enable notifications there. |
| Browser without notification, push, or service worker support | Use a browser that supports web push. |

API requests, worker lookup and notification destinations retain the runtime
app base path, including a Home Assistant ingress prefix. Notification clicks
focus a matching app window or open the destination within that scope. External,
traversing or malformed destinations fall back to the app's scope root.

The four **Automatic alerts** rows remain disabled and off: display offline,
override ended, hub/plugin update available, and Silence Schedule held a message.
Their event producers and category preferences are not available yet. Successful
enrollment and test delivery do not enable these automatic alerts.

**Send a test** reports the sender's result. Feedback that the push service
accepted a test means the provider accepted at least one message; browser display
is still subject to browser and operating-system delivery. A test that was
skipped, failed or expired is not reported as delivered. The API counts below
distinguish these outcomes.

## Sign-out and app attention badge

Server logout invalidates this session's enrollment. Browser cleanup also
attempts to unsubscribe this app's push subscription, close its visible
notifications and clear the app badge. Local cleanup has a bounded wait so
unavailable browser storage cannot trap sign-out. Browser site permission stays
under the user's browser settings; signing in again requires browser enrollment.
A message already accepted by the provider may still arrive after sign-out.

Where the browser supports the Badging API, the app badge is a dot for the same
attention shown in **More**, such as an available update or setup required by an
integration. Opening More clears it; new attention can set it again. Sign-out
also clears it. Push delivery and notification clicks do not change this dot,
and no unread-message count is tracked. Browsers without Badging support can
still receive notifications.

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
it.

| Count | Meaning |
| --- | --- |
| `sent` | The push provider accepted the message. |
| `failed` | Delivery did not succeed, including provider rejection or transport failure. |
| `skipped` | Consent, current state or delivery limits prevented delivery. |
| `expired` | The subscription expired or the provider reported that it was gone. |

The test contains only the fixed text “Notifications are working on this
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
