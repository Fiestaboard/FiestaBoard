# v9 manual-send silence contract

This is the backend contract for the #1943/#1944 stable backport. The existing
v9 clients, geometry, output-target rules, previews and temporary overrides
remain in use. `force` only requests a resend of unchanged content.

## Requests and responses

`override_silence` defaults to false. JSON bodies require a real boolean;
query strings accept the normal FastAPI boolean spelling. An explicit true
allows a write during silence, but never bypasses pause.

| Surface | Request location | Silence response |
| --- | --- | --- |
| `POST /send-message` | JSON `override_silence` beside `text`, optional `board_id` | 202 if held; otherwise existing 409 refusal |
| `POST /v1/boards/{board}/message` | JSON `override_silence` beside any supported content form | 202 if held; otherwise existing 409 refusal |
| `PUT /settings/active-page` | JSON beside `page_id`, optional `board_id` | 200, selection saved, `sent_to_board: false` |
| `PUT /v1/boards/{board}/active-page` | JSON beside `page_id` | 200, selection saved, `sent: false` |
| `POST /pages/{id}/send` | JSON or query; explicit query wins | 200 preview, `sent_to_board: false` |
| `POST /displays/{type}/send` | Query; existing primary-board targeting | 200 preview, `sent_to_board: false` |
| `POST /templates/render/live` | JSON beside template and optional board | 200 rendered preview, `sent_to_board: false` |
| MCP / canonical ops `send_message`, `set_active_page` | Optional `override_silence` argument | Existing result envelope plus silence fields |
| MQTT `send_message`, `active_page` | Optional boolean in JSON payload | Persist/hold or send; plain-string payload never overrides |

The response models above add `silenced: boolean`, `held: boolean`, and
`ends_at_utc: string | null`. Their ordinary defaults are false, false and
null. `ends_at_utc` is an ISO-8601 UTC instant for the active window's end.
`silenced: true` means this request did not write because of silence.
`held: true` means its intent was accepted into the persistent per-board slot.

Held legacy messages return the usual `message`, with `sent: false`,
`silenced: true`, `held: true` and the window end. Held v1 messages also retain
the rendered `characters` and `text`, set `reason` to "Held until silence ends",
and leave `expires_at` null. No timed override is armed by a held message.
Pause keeps the existing 409 message refusal or the preview/selection's
`paused: true` behavior. v1's `if_paused: "preview"` and UI-only response
contracts are unchanged.

UI-only page/display/selection requests do not create holds. Live output keeps
v9's explicit live-send targeting semantics. Malformed requests and unknown
write targets are rejected before queue mutation. Preview responses do not
claim a successful board write.

## Holding and delivery

Holding requires `show_queued_on_exit: true` in the resolved silence settings;
the default is false. An omitted board id resolves to the primary. New holds
replace only that board's slot and expire after 24 hours. Text wraps at delivery
for the target geometry; lines and raw grids retain their content; pages and
plugin displays render fresh. Live/template snapshots use a raw-grid intent.

The engine tries pending intent after silence, pause and output-target gates.
Its worker rechecks those gates and that the intent is still current before
writing. Offline, throttled, paused, mismatched or unrenderable attempts retain
the intent for a later attempt or expiry. Only an actual successful delivery
discards it. A newer successful explicit send also supersedes the older intent
it observed before writing. Both use atomic conditional discard, preserving a
newer hold created during an older in-flight send. Discard cannot undo hardware
I/O that already started.

After held delivery, the message stays until active content changes or an
explicit refresh replaces it, following v9's manual-message behavior. The engine
snapshots fresh normal active content just before the held write and records
that baseline only on actual success, so edits, dynamic data and schedule
changes before the next tick are detected. A missing or unrenderable baseline
does not block held delivery; the normal engine can send once content becomes
available. Existing trigger and temporary-override priority is preserved.

MQTT page/collection selection validates target compatibility before changing
selection or held intent. UI-only selections persist without creating or
replacing a hold. Held plugin displays receive the target board's full render
context, including Note and array dimensions, just as immediate v1 sends do.

`GET /silence-status` and `DELETE /silence-queue?board_id=...` keep Task 1's
contract. Status includes the held preview and window end. Discard clears only
that board. Home's Show now can resend the selected active page with
`override_silence: true`; no held-replay endpoint is introduced.

Setup welcome, board diagnostic operations, and v9's dedicated temporary
override semantics retain their existing contracts.
