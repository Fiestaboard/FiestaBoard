# AI choreography: showing the assistant's work on screen

When FiestaBot changes something, the app walks the user to where the change
lands and shows it arriving: the Pages list, a fresh editor with the name and
lines typed in, the schedule form filling field by field, a setting's new
value ghosted over its control before the real one lands. This document is
the map of that layer. It lives entirely in the web app; the MCP server and
the agent loop know nothing about it.

## Where it lives

| Piece | File | Job |
| --- | --- | --- |
| Anchors | `web/src/lib/ai-choreography/anchors.ts` | Names for places on screen (`pages.new`, `page-editor.name`, `settings.general.instance_name`) resolved by `data-ai-anchor` first, legacy ids second |
| Step language | `web/src/lib/ai-choreography/types.ts` | `navigate`, `waitFor`, `waitBridge`, `spotlight`, `caption`, `ghost`, `type`, `set`, `pause`, `pulse`, `clearGhosts`, `hide`, `run` |
| Engine | `web/src/lib/ai-choreography/engine.ts` | Plays steps at a human pace; ~18 ms per character capped at 600 ms per field, ×4 faster once the result is in, instant under reduced motion; abortable between chunks |
| Scripts | `web/src/lib/ai-choreography/scripts/*.ts` | One per tool that deserves more than the generic walkthrough: pages, schedules, settings |
| Registry | `web/src/lib/ai-choreography/registry.ts`, `home.ts` | `getScript(name)` with the fallback; `homeFor(call)` maps a tool name to the route and anchor it lands on |
| Draft reader | `web/src/lib/ai-choreography/draft.ts` | Reads what is complete in a tool block the model is still writing |
| Choreographer | `web/src/lib/ai-choreography/use-choreographer.ts` | One job per call, played strictly in order; drafts start a job early; Stop aborts and cleans up |
| Spotlight | `web/src/components/ai-spotlight/spotlight-provider.tsx` | The ring, the caption with Stop / Approve / Deny, the ghost values; positions measured per frame from the anchor |
| Bridges | `page-editor-bridge-context.tsx`, `schedule-editor-bridge-context.tsx` | The surfaces a script may drive for real: stage a page's name/lines/device in the editor, open and fill the schedule form |

The drawer (`global-ai-chat-drawer.tsx`) feeds the choreographer from the
chat stream: `tool_streaming` → `onDraft`, `tool_call` → `onToolCall`,
`tool_result` → `onToolResult`, `done{awaiting_approval}` →
`onAwaitingApproval`, Stop/error → `onAbort`, end of turn → `onTurnEnd`.

## The order of things

For every call the server announces:

1. **narrate** — go to the screen, point at the control, show the value
   arriving. Plays while the server runs the tool.
2. **wait** for the call's result. A result that lands mid-narration switches
   the rest of the narration to fast.
3. **settle** (result `ok`) or **fail** (`error`, `blocked`, `denied`) — the
   landed pulse and caption, then out of the way.
4. The next call's narration starts only now. Calls never overlap on screen.

A `tool_streaming` frame (the block the model is still writing) starts a job
before the call exists. `create_page` uses it to open the editor and type
the name and lines as they are written; when the call completes, `narrate`
receives the same `progress` object and types only what is new. A draft that
never becomes a call (a malformed block) is dropped when the turn ends and
its `stop` steps run, so nothing staged is left behind.

## Read-only tools show nothing

`list_pages`, `get_settings_summary` and friends never navigate or spotlight.
The step timeline in the chat panel is where they show up.

## Bridge only when a form must be mounted; otherwise ghost

Two surfaces are driven for real, because the user should be able to take
over mid-way and because the values must survive the reveal: the page editor
(name, lines, device type — `beginStaging` takes one snapshot, suspends the
draft autosave and locks Save; `discardStaging` restores the snapshot;
`reloadFromServer` re-seeds from the saved page) and the schedule form
(`openEmpty`/`openEntry`, then `setField` per field).

Everything else uses a **ghost**: a DOM-level overlay over the control showing
the typed prefix with a caret (`replica`, for text inputs) or the value as a
badge beside it (`badge`, for switches, selects and sliders). Ghosts touch no
React state, which is how all thirty-odd settings cards get the reveal with
no per-card wiring. They are cleared when the real value lands.

## Adding a walkthrough for a new tool

Nothing is required. An unknown writing tool gets the fallback: `homeFor`
picks the route from the tool name (`*schedule*` → `/schedule`, `*plugin*` →
`/integrations`, board state → `/`, hardware → the settings hardware tab, …)
and the most specific anchor the arguments name (`plugin.<plugin_id>`,
`page.<page_id>`, `schedule.row.<schedule_id>`), spotlights it with the
tool's label, and pulses it when the result lands.

To do better:

1. Stamp anchors with `anchorProps("<id>")` on the elements the tool
   touches. Ids are dotted paths; a settings key is
   `settings.<category>.<key>` and falls back to its card `settings.<category>`.
2. Add a script under `scripts/` returning steps for `narrate`, `settle`,
   optionally `fail`, `stop`, `draft` and `approvalAnchor`, and register it in
   `registry.ts`.
3. Add the caption strings to `aiChoreography.*` in every locale.
4. Test it in `web/src/__tests__/ai-choreography-scripts.test.ts` (pure:
   steps in, steps out) and, when it drives a real surface, in Playwright
   with a mock-LLM script.

Anchor ids are a contract shared with the docs captures
(`assets/docs-captures/README.md`, "Anchoring"): renaming one is a docs and
choreography change at once.

## Accessibility

While a walkthrough is driving, the chat drawer is not modal: the focus trap
is released, focus is never moved by the narration, Escape stops the
assistant, and the caption is a `role="status"` region so screen readers hear
what is happening once. Under `prefers-reduced-motion` every reveal is
instant and pauses are a blink; nothing intermediate is shown.
