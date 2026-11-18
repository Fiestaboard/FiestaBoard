# Temporary override cancel Undo

`GET /settings/temporary-override?board_id=<id>` advertises `undo_supported: true`.
Older hubs omit the field. Clients must use this capability, not infer support
from the application version. Existing cancel requests keep their original
`{"revert_mode": ...}` response.

Opt into a receipt with
`DELETE /settings/temporary-override?board_id=<id>&undo=true`. The response adds
nullable `undo_token` and `undo_expires_at`; no active override means no receipt.
Cancellation and a page revert are one settings critical section. Cache eviction
still asks the display engine to render its resulting state immediately.

Restore with `POST /settings/temporary-override/undo` and a JSON object containing
only `board_id` and `undo_token`. Success returns the existing override status
shape. An unknown display is 404; unavailable, expired, used, stale, wrong-session
or wrong-display authority is 409. Invalid bodies are 422. An in-flight manual
write also returns 409. Clients must refresh state on failed or unknown outcomes
and must not automatically retry mutations. Receipt responses use `no-store`.

Authority lasts at most 30 seconds and never beyond the cancelled run's original
expiry. It is scoped to the issuing native session or browser session; local
installs with authentication disabled share their existing anonymous authority.
The server retains the exact original payload, geometry, revert metadata,
started_at and expiry in memory. The client cannot supply restored content or a
new duration. Successful restoration consumes authority before persistence;
a failed persistence write cannot be retried with the receipt. Restart/reload
discards receipts. Neither receipt tokens nor cancelled content are persisted.
This follows the existing single-process deployment contract in PERSISTENCE.md.

Restoration checks under the established settings/config/pages/collections/
schedules lock order. Each display has its own Undo generation, advanced by
every settings save that changes that display's override, active page, own
board settings (including its removal) or primary status; content-owner saves/reloads change their runtime generations.
ABA changes and internal/background content writes are therefore refused even
when their HTTP/SSE response has already completed, while a cancel, page change
or override expiry on another display leaves the receipt usable. Physical manual
HTTP writes and internal/MCP/MQTT sends use an in-flight barrier; successful or
uncertain writes invalidate authority. Native/MCP active-page and refresh
operations carry manual intent into the existing send pool. Each queued manual
or trigger job retains separate authority until terminal worker completion,
including fire-and-forget submission, timeouts, adoption by a newer pending job,
and worker stop. The send pool also owns the underlying concurrent future,
so cancelling an HTTP/SSE await cannot end authority while a hardware thread
continues. Root-path and explicit `/api` route forms are normalized. MQTT
immediate active-page delivery and output/identify actions carry the same
manual intent. Trigger/held-message delivery joins that barrier without
changing its delivery, silence or queue semantics. Unauthenticated
HTTP attempts never reach it; previews do not enter it.

Invalidation is otherwise conservative: any successful manual HTTP write
(on any display), config and content saves, admitted output actions (which
declare no read-only effect metadata), and uncertain hardware outcomes can
refuse Undo. Settings saves that leave the display's own state alone (polling,
another display) do not. Cold template-engine initialization can persist plugin
defaults, so the first preview may refuse a receipt because of that actual config
save. Once initialized, read-only previews and validation refusals leave receipts
usable. Automatic schedule rendering after cancellation does not itself revoke
Undo; a newer intentional control/content mutation does. External device changes
outside the hub and unsupported writers bypassing these service owners are outside
this API's single-process authority.
