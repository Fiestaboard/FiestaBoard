# Compose intent protocol

A board advertises `compose_protocol: "compose-intent-v1"` on
`GET /v1/boards/{board}`. A client must verify this exact capability before
using `POST /v1/boards/{board}/compose`.

The request captures an immutable UUID `request_id`, offset RFC3339
`prepared_at`, original `template` lines, matching optional `line_metadata`
(`alignment`, `wrap`), explicit `geometry`, `silence: "hold" | "override"`,
and one tagged duration:

- `{"kind":"minutes","minutes":120}`: integer 1 through 480; starts when
  the driver accepts delivery, including an unchanged-content acknowledgement.
- `{"kind":"until","ends_at":"2026-11-17T20:00:00Z"}`: future offset
  instant within 480 minutes at admission and actual release. An expired end
  never becomes an indefinite override or a rounded one-minute duration.
- `{"kind":"until_cancel"}`: an explicit indefinite override.

New admission requires `prepared_at` within five minutes of the hub clock.
A repeated UUID with the same target, actor and exact payload reads its
existing outcome; a conflicting UUID never writes hardware. The bounded
durable ledger retains live held requests and refuses admission when full.
After a restart, interrupted preparing/dispatching records become unknown.
Clients must not recover an unknown outcome by creating another request UUID.

Pause and a UI-only output target refuse Compose. Silence override requires
explicit consent. Explicit Hold persists the original request even when the
legacy automatic Hold preference is disabled. The existing engine releases
that typed request after silence; relative duration begins at acceptance.
Only the captured held entry can be consumed. Geometry, runtime and newer
manual authority are rechecked before dispatch and after acknowledgement.
A replaced action may have physically sent content and still be superseded;
its old override is never armed over the newer action.

Responses use `Cache-Control: no-store`. Sent and unchanged outcomes are 200;
held or unfinished delivery is 202 with `sent` false or null respectively.
Policy/expiry/supersession is 409, rate limit is 429 plus `Retry-After`, and
partial/refused driver output is 502. Unknown or unavailable durable state is
503. Error bodies put the receipt in `detail`; schema rejection is FastAPI's
422 validation response. A generic 200 or 202 is not physical-send proof.

`GET /v1/boards/{board}/compose/{request_id}` returns this authenticated
session's recorded receipt without issuing a mutation. Other sessions cannot
read or reuse its UUID authority. Active override readback on board detail
includes nonsecret Compose UUID, exact duration and acceptance timestamps.
The worker owns terminal authority after HTTP timeout or cancellation; an
older pending worker cannot inherit the success of its replacement.

This protocol does not authorize preview or Save as Page. Those operations
have separate routes and audits. It does not add a client timer, a second
write to arm duration, or a replay queue on the phone.
