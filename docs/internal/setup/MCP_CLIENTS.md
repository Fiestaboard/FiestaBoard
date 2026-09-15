# MCP clients

FiestaBoard exposes a [Model Context Protocol](https://modelcontextprotocol.io)
server at `/api/mcp/`, so an AI assistant like Claude Desktop or Claude Code
can read your pages, render template previews, configure plugins, and manage
schedules through conversation rather than the web UI.

This page walks through wiring each client up to a self-hosted FiestaBoard.

> **Where to get your token:** **Settings → Integrations → MCP / external
> clients → Generate token** (or **Rotate token**). The plaintext value is
> shown exactly once — copy it into your client config immediately.

> **Hostname tip:** The default `docker-compose.yml` uses bridge networking
> (`4420:3000`), which does **not** advertise `fiestaboard.local` — use
> `localhost:4420` or the host's LAN IP instead. The `fiestaboard.local` name
> only resolves if you enable **Option B: Host networking**
> (`network_mode: host`, commented out in `docker-compose.yml`) *and* your host
> has an mDNS/Bonjour resolver. The FiestaPi image ships avahi, so it advertises
> as `fiestapi.local` out of the box. The examples below use `fiestaboard.local`;
> substitute whatever address matches your install.

## Token via environment variable

Docker installs and auth-enabled setups often need to configure the MCP token
before the web UI is reachable. Set `FIESTABOARD_MCP_TOKEN` in your
`docker-compose.yml` (or `.env` file) to skip the UI step entirely:

```bash
FIESTABOARD_MCP_TOKEN=your-token-value-here
```

Generate a suitable value on any machine with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the generated value in the `Authorization: Bearer` header of your MCP
client config — it replaces `<YOUR_TOKEN>` in the examples below.

> **Note:** When `FIESTABOARD_MCP_TOKEN` is set it takes precedence over any
> token stored by the Settings UI, and the **Generate / Rotate token** buttons
> in **Settings → Integrations** are disabled. To manage the token from the UI
> again, unset the variable and restart the container.

> **Once a token exists, `/api/mcp/` requires it** — in every auth mode,
> including `FIESTABOARD_AUTH_ENABLED=false`. Turning off the browser login
> is a UI convenience; it does not switch off a credential you configured on
> purpose. Requests without a valid `Authorization: Bearer` header get a 401,
> so every client needs the token in its config. If you have no token
> configured, nothing changes: `/api/mcp/` follows whatever the auth mode
> says.

> **With the login disabled, the token guards its own management.** The
> paragraph above is about the `/api/mcp/` data path. The *token
> management* routes (`GET` / `POST` / `DELETE /auth/mcp-token`) have no
> session to check when the login is off, so they check possession
> instead: once a token is configured, managing it requires presenting the
> current token as an `Authorization: Bearer` header, and anonymous
> requests get a 401. Only the first mint stays open, by design — until a
> token exists the whole REST surface is open, so gating it would protect
> nothing, and it keeps **Settings → Integrations** rendering without a
> login-redirect loop. (Earlier releases left these routes fully anonymous
> on such installs, so anyone who could reach the port could mint or
> revoke the token — fixed in Fiestaboard/FiestaBoard#1825.)
> Even so, the possession gate is **not a boundary against an attacker
> who can already reach the port**: on an install where the login is
> merely *disabled by preference*, the preference itself is part of the
> open API, so such an attacker can `POST /auth/preference` to enable the
> login, register the first admin via `POST /auth/setup`, and manage the
> token with that session. Treat the gate as protection against casual or
> accidental mint-and-read and revocation.
> `FIESTABOARD_MCP_TOKEN` is the configuration that actually holds: while
> it is set, the mutating routes refuse with `409` even for a caller
> presenting the token, so it cannot be rotated or revoked over the
> network at all. Enabling the browser login gates management behind the
> admin session as usual.

## Why local hosting makes this awkward

The MCP ecosystem is converging on three transports — stdio, HTTP, and
SSE — and three auth styles — bearer tokens, OAuth 2.1 with dynamic client
registration, and "trust the parent process." Different clients support
different combinations:

| Client | Transport | Auth it expects | Works against FiestaBoard? |
|---|---|---|---|
| Claude Desktop | stdio only | parent-process trust | ✅ via the `mcp-remote` proxy |
| Claude Code (CLI) | HTTP, stdio, SSE | bearer tokens, OAuth | ✅ HTTP + bearer, directly |
| claude.ai web (Connectors) | HTTP | OAuth 2.1 + DCR + public HTTPS | ❌ requires public hosting |
| ChatGPT (Apps SDK) | HTTP | OAuth 2.1 + DCR + public HTTPS | ❌ requires public hosting |

FiestaBoard is a **LAN appliance** — no public hostname, no TLS cert, no
OAuth authorization server. That eliminates the web-based clients
automatically. Desktop apps can still reach it because they run on the same
network as you, but they need a small shim to bridge their stdio assumption
to FiestaBoard's HTTP endpoint.

That shim is [`mcp-remote`](https://www.npmjs.com/package/mcp-remote), a
tiny Node program that pretends to be a stdio MCP server to Desktop and
forwards everything as HTTP to FiestaBoard.

## Claude Desktop

**Prerequisites:** Node 18 or newer, with `npx` reachable from Claude
Desktop's launch environment. On macOS with Homebrew Node that usually
"just works"; with `nvm` you may need to use the absolute path (see
[Troubleshooting](#troubleshooting)).

1. In FiestaBoard's web UI, open **Settings → Integrations → MCP / external
   clients** and click **Generate token** (or **Rotate token**). Keep the
   reveal dialog open — it shows the token and a Desktop config snippet.
2. Open the Claude Desktop config file and merge in the `fiestaboard` entry
   from the reveal dialog. It looks like this:

   > **Config file location:**
   > - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   > - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json` (typically `C:\Users\<you>\AppData\Roaming\Claude\`)
   >
   > Create the file if it doesn't exist.

   ```json
   {
     "mcpServers": {
       "fiestaboard": {
         "command": "npx",
         "args": [
           "-y",
           "mcp-remote",
           "http://fiestaboard.local:4420/api/mcp/",
           "--allow-http",
           "--header",
           "Authorization: Bearer <YOUR_TOKEN>"
         ]
       }
     }
   }
   ```

3. **Fully quit** Claude Desktop and relaunch. The `fiestaboard` server should
   appear under the MCP indicator with tools available.

   > **How to fully quit:**
   > - **macOS:** Press ⌘Q (closing the window isn't enough).
   > - **Windows:** Right-click the Claude icon in the system tray and choose **Exit** (closing the window isn't enough).

### What's going on under the hood

- Claude Desktop's `mcpServers` config only accepts stdio entries (a
  `command` plus `args`). It does not honour `"type": "http"`,
  `"url"`, or `"headers"` — if you try those, Desktop will pop a "Some
  MCP servers could not be loaded" dialog and skip the entry.
- `npx -y mcp-remote ...` downloads and runs the proxy on first launch,
  then caches it. It speaks stdio to Desktop and HTTP to FiestaBoard.
- `--allow-http` is mandatory because `mcp-remote` refuses plaintext
  targets by default. We're on a LAN, so http is fine — but the flag
  has to be explicit.
- The **trailing slash** on the URL is load-bearing. Hitting
  `/api/mcp` triggers a FastAPI 307 redirect to `/api/mcp/` that
  rewrites the Location header to drop the `:4420` port. `curl` won't
  follow the redirect by default; Node's `fetch` does, then times out
  on port 80. Always end the URL with `/`.

## Claude Code (CLI)

Claude Code speaks HTTP and bearer tokens directly, so no proxy is needed:

```bash
claude mcp add fiestaboard --transport http \
    --url http://fiestaboard.local:4420/api/mcp/ \
    --header "Authorization: Bearer <YOUR_TOKEN>"
```

Verify with `claude mcp list`. Inside a Claude Code session, the
`fiestaboard` server's tools (`list_pages`, `render_page_preview`, etc.)
become callable just like any built-in tool.

## claude.ai web — not supported

The Connectors flow at **claude.ai → Settings → Connectors → Add custom
connector** is for *public* MCP servers. It performs OAuth 2.1 dynamic
client registration against `/.well-known/oauth-protected-resource` and
`/.well-known/oauth-authorization-server`, neither of which FiestaBoard
exposes, and it requires HTTPS with a publicly-trusted certificate.

If you add a LAN URL there, you'll see:

> Couldn't register with FiestaBoard's sign-in service. You can try
> again, or add an OAuth Client ID in the connector settings.

There is no workaround short of putting FiestaBoard behind a public
HTTPS reverse proxy *and* implementing an OAuth authorization server.
That's well out of scope for a home LED display. **Use Claude Desktop
or Claude Code instead.**

## Upgrading an existing MCP client

The MCP server's wire contract changed in this release. Client *config* is
unaffected — same transport, same URL, same bearer token — so Claude Desktop
and Claude Code keep working with no edit. If you wrote your own client, or
you script against `/api/mcp/` directly, four behaviors are different.

### 1. Tool failures now set the protocol `isError` flag

Every failure used to be a *successful* `CallToolResult` whose payload
happened to say `{"status": "error", ...}`. A client that treated any
non-exception result as success never noticed a failure at all.

Now every tool registers through one wrapper, so any executor error envelope
or unexpected exception comes back as `isError: true`. Check that flag first.

Two things deliberately stay ordinary results:

- **Success** still carries `structuredContent` and `isError: false`.
- **Policy blocks** — a send suppressed by silence mode or pause — are
  `isError: false` with `structuredContent.status == "blocked"`. They are
  policy for the model to relay, not failures. Do not treat them as errors.

### 2. `structuredContent` is absent on the failure path

The old error result carried the machine-readable envelope:

```json
{
  "content": [
    {"type": "text", "text": "{\n  \"status\": \"error\",\n  \"error\": \"Page 'missing' not found.\"\n}"}
  ],
  "isError": false,
  "structuredContent": {"status": "error", "error": "Page 'missing' not found."}
}
```

The new one carries text only:

```json
{
  "content": [
    {"type": "text", "text": "Error executing tool get_page: Page 'missing' not found."}
  ],
  "isError": true
}
```

Anything reading `structuredContent` on the error path now gets nothing.

**No information was lost, only relocated.** The text after the
`Error executing tool <name>:` prefix (and the space after it) is the same
string the old `structuredContent.error` field held — the executors' error envelopes are
still the source, they are just raised as a protocol error at the MCP
boundary rather than returned as a payload. Read `isError`, then
`content[0].text`, and strip the prefix if you were parsing the old field.

Unexpected exceptions are no longer stringified onto the wire. They are
logged server-side with their traceback and reduced to:

```text
<tool> failed unexpectedly (<ExceptionClass>); details are in the server log.
```

That is intentional — raw exception text routinely carried filesystem paths
and config values. Look in the container log for the detail.

### 3. `list_registry_plugins` is paginated

It used to return a top-level JSON array of every registry entry. It now
returns an object:

```json
{"plugins": [], "total": 54, "page": 1, "page_size": 20, "total_pages": 3}
```

(`plugins` elided — it holds the 20 entries of this page.)

A client iterating the old array breaks outright; one that ignores pagination
silently sees a fraction of the marketplace. Pass `page` (1-based) and
`page_size` (1-100, default 20) and walk to `total_pages`. Out-of-range
values are errors, not clamps.

### 4. `teaser` and `previews` are omitted by default

Every registry entry carries `teaser` and `previews` — literal split-flap
board rows used to show what a plugin looks like on a board. They dominate
the payload, so the default projection drops them. Measured against the
54-entry registry: the old full-list response serializes to ~38 KB, the new
default page to ~7.7 KB, a ~80% cut.

A client that rendered board previews straight from this response goes blank
until it opts back in, by naming the fields it wants:

```json
{
  "name": "list_registry_plugins",
  "arguments": {"page": 1, "fields": ["name", "teaser", "previews"]}
}
```

`fields` is an **exact projection, not an additive opt-in**: each entry then
carries only the fields you name, plus `id`, which is always included. Naming
a field no entry has is an error that lists the valid ones.

### Also new: tool annotations

Every tool now carries the standard MCP annotations (`readOnlyHint`,
`destructiveHint`, `idempotentHint`, `openWorldHint`, `title`) in
`tools/list`. Clients that honour them — Claude Desktop and Claude Code do —
stop asking you to confirm reads like `list_pages` and keep asking for the
four that cannot be undone: `delete_page`, `delete_schedule`,
`delete_collection` and `uninstall_plugin`. The `update_*` tools overwrite
but are not flagged destructive; the previous value is one `get_*` call away.
Nothing changes for a client that ignores annotations.

There is also one more tool, `update_setting(category, values)`, for the
display, transitions, output, polling, location, silence-schedule and
active-page settings — the same categories the in-app chat could already
change. Read current values with `get_settings_summary()` first.

### Also new: five tools

`get_active_page`, `get_board_content`, `preview_saved_page`,
`send_message`, and `validate_template` were added in the same release.
Nothing was removed or renamed.

### Page-editor parity: every editor control, share strings, staff picks, the Transition Lab

The in-app AI chat drives FiestaBoard through this same server, so
everything the web page editor can save has to be reachable as a tool.
This release closes that gap. Existing argument names are unchanged; the
additions are all optional.

- **`update_page` and `create_page` accept every editor field**:
  `device_type` (`flagship` / `note` / `note_array`), `notes_wide` and
  `notes_tall` (note-array geometry), `line_metadata` (one
  `{"alignment": "left"|"center"|"right", "wrap": bool}` per line),
  `transition_strategy` / `transition_interval_ms` / `transition_step_size`
  (the per-page transition override) and, on update, `duration_seconds`.
  `update_page(clear_transition_override=True)` removes the override —
  needed because an omitted field means "unchanged". A device or size
  retarget answers `incompatible_references`, the same list
  `PUT /pages/{id}` returns: every schedule entry, board active page or
  silence page that now points the page at a board it no longer fits.
  Warn-only; nothing is mutated.
- **`render_page_preview(notes_wide, notes_tall)`** previews a `note_array`
  at its real size and now reports `rows` / `cols`.
- **`export_page(page_id)`** → the portable share string
  (`GET /pages/{id}/share`); **`import_page(share_string)`** creates a new
  page from one (`POST /pages/import`). Read-only and non-destructive
  respectively.
- **`list_staff_picks()`** and **`import_staff_pick(pick_id)`** — the
  curated gallery (`GET /staff-picks`, then share → import). Listings never
  carry share strings.
- **`get_current_display(board_id?)`** — the live page's raw template plus
  `line_metadata` and device geometry (`GET /pages/current-display`, with a
  `board_id` the REST route lacks).
- **`list_formula_functions()`** — the `{{= ...}}` function reference
  (`GET /v1/functions`).
- **Transition Lab** (beta; errors until Settings → Beta enables transition
  plugins, exactly like the REST routes): **`list_transition_plugins()`**
  (`GET /transitions/plugins`), **`test_transition_live(plugin_id,
  to_page_id, from_page_id?, config?, board_id?)`** (`POST
  /transitions/test-live`) and **`restore_board(board_id?)`** (`POST
  /transitions/restore`). A paused board or an active silence window comes
  back as `status: "blocked"`, the same policy result `send_message`
  returns.

Annotations: `export_page`, `list_staff_picks`, `get_current_display`,
`list_transition_plugins` and `list_formula_functions` are read-only;
`import_page`, `import_staff_pick` and `test_transition_live` are writes
but not destructive (a client should not ask for confirmation);
`restore_board` is additionally idempotent. Nothing here is destructive.

### Also new: the rest of the Integrations page

Everything the **Integrations** page can do is now reachable over MCP, so
the in-app chat (which only calls these tools) can do it too:

| Tool | Mirrors | Annotations |
|---|---|---|
| `install_plugin(repository=…, branch=…, plugin_id=…, initial_config=…)` | **Add from Git** (`POST /plugins/install`) | open-world |
| `list_plugin_instances(plugin_id)` | `GET /plugins/{id}/instances` | read-only |
| `create_plugin_instance(plugin_id, label)` | `POST /plugins/{id}/instances` | — |
| `delete_plugin_instance(plugin_id, label)` | `DELETE /plugins/{id}/instances/{label}` | **destructive** |
| `get_plugin_demo_page(plugin_id, device_type)` | `GET /plugins/{id}/demo-page` | read-only |
| `create_plugin_demo_page(plugin_id, device_type, recreate)` | `POST /plugins/{id}/demo-page` | — |
| `list_pending_plugin_updates()` | `GET /plugins/updates` | read-only |
| `check_plugin_updates()` | `POST /plugins/updates/check` | idempotent, open-world |
| `update_all_plugins()` | `POST /plugins/updates/apply` | idempotent, open-world |
| `list_plugin_options(plugin_id, options_id, parent, query, limit, cursor)` | `POST /plugins/{id}/options/{options_id}` | read-only, open-world |
| `get_plugin_manifest(plugin_id)` | `GET /plugins/{id}/manifest` | read-only |
| `list_plugin_errors()` | `GET /plugins/errors` | read-only |

Notes for scripted clients:

- `install_plugin` still installs from the registry when only `plugin_id` is
  given; `repository` switches it to a git clone (https URLs only) and
  `plugin_id` then becomes an optional override of the derived id. The
  result gains a `source` field (`"registry"` or `"git"`).
- Plugin instances are addressed as `base:label` everywhere else
  (`configure_plugin`, `enable_plugin`, `get_plugin_data`, templates).
- `create_plugin_demo_page` defaults to `recreate=false`, unlike the REST
  endpoint: an existing demo page is kept and reported back (`created:
  false`) rather than rebuilt over the user's edits. Pass `recreate=true`
  for the REST behaviour.
- `configure_plugin` now documents the `color_rules` config key
  (`{field: [{condition, value, color}, …]}`, first match wins) so a model
  can set colour rules; `get_plugin_manifest` lists the eligible fields
  under `color_rules_schema`.
- `list_plugin_options` is a single uncached lookup against the plugin's
  stored config — there is no `draft_config` or `refresh`; configure
  credentials first. Its payload matches the REST endpoint minus the cache
  fields.
- `delete_plugin_instance` joins the destructive set, so annotation-aware
  clients confirm it.

## Schedules, collections and board state

Everything the Schedules page and the Home page can change is reachable
over MCP — the same coverage rule the in-app chat follows, since it drives
these very tools.

### Changed: `list_schedules` answers with the Schedules page's shape

It used to return a bare list of stored entries. It now returns what
`GET /v1/schedules` returns:

```json
{
  "schedules": [{"id": "...", "start_time": "06:00", "start_type": "sunrise",
                 "resolved_start_time": "06:41", "...": "..."}],
  "total": 1,
  "board_id": "board-main",
  "default_page_id": "page-123",
  "schedule_enabled": true
}
```

Each entry carries every stored field plus `resolved_start_time` /
`resolved_end_time` — today's actual HH:MM, which differs from the stored
time only for sunrise/sunset entries. `board_id` is optional (omitted = the
primary board; `"*"` lists every board, with the two per-board fields null).
A client iterating the old array must read `.schedules`.

### Schedule entries: every form field

`create_schedule` and `update_schedule` accept everything the entry form
saves: `custom_days`, `board_id`, `recurrence_type` (`weekly` |
`annual_date` | `one_off_date`) with `annual_date`/`annual_end_date`
(`MM-DD`) or `one_off_date`/`one_off_end_date` (`YYYY-MM-DD`), and
`start_type`/`end_type` (`fixed` | `sunrise` | `sunset`) with
`start_sun_offset`/`end_sun_offset` in minutes. On `update_schedule`,
omitting a field means "unchanged", so the clears are explicit flags:
`clear_end_time`, `clear_custom_days`, `clear_annual_end_date`,
`clear_one_off_end_date`.

Around the entries:

- `validate_schedules(board_id?)` — overlaps and gaps (read-only).
- `set_default_page(page_id | null, board_id?)` — the page shown in gaps.
- `update_setting("schedule_behavior", {"defer_on_reenable": bool})` — the
  global re-enable behaviour.

### Collections: random mode and partial updates

`create_collection` / `update_collection` take `selection_mode: "random"`;
`interval_seconds` is the page duration for both time and random mode.
`update_collection` merges mode config with what is stored, so
`poll_seconds` or `rules` can change alone in variable mode without
re-sending `default_page_id`, and switching to random carries the current
interval over.

### Board state: the Home page's controls

| Tool | REST equivalent | Annotations |
|---|---|---|
| `get_temporary_override()` | `GET /settings/temporary-override` | read-only |
| `set_temporary_override(page_id \| template_lines, duration_minutes?, revert_mode?, …)` | `POST /settings/temporary-override` | write, not idempotent (each call restarts the clock) |
| `cancel_temporary_override()` | `DELETE /settings/temporary-override` | write, idempotent |
| `force_refresh()` | `POST /force-refresh` ("Resend to board") | write, idempotent |
| `get_silence_status(board_id?)` | `GET /silence-status` | read-only |
| `pause_board(board_id?)` / `resume_board(board_id?)` | `PATCH /v1/boards/{id}` `paused` | write, idempotent |

`get_active_page` now also carries `temporary_override`. The override and
the forced resend take no `board_id` on purpose: the override lives in one
store the display loop applies to the primary board, and the resend covers
every board — a parameter the store cannot honour would be a lie in the
schema. None of these is flagged destructive; each is reversible by the
matching tool, so a client that honours annotations does not prompt.

## Troubleshooting

**"Some MCP servers could not be loaded… skipped: fiestaboard"** — your
`claude_desktop_config.json` entry is using the HTTP form (`"type":
"http"`, `"url"`, `"headers"`). Desktop rejects that. Switch to the
`mcp-remote` stdio form shown above.

**`Connection error: fetch failed … ETIMEDOUT`** in the Desktop MCP
log — almost always the missing trailing slash on the URL. Use
`/api/mcp/`, not `/api/mcp`.

**`command not found: npx`** (or `'npx' is not recognized`) in the Desktop
MCP log — Claude Desktop launches outside your normal shell and may not
inherit your PATH.

- **macOS:** Replace `"npx"` in the config with the absolute path from
  `which npx` (e.g. `/opt/homebrew/bin/npx` on Apple Silicon Homebrew).
  `nvm`-managed Node installs put `npx` under
  `~/.nvm/versions/node/<version>/bin/npx`, which changes on every
  upgrade — installing Node via Homebrew (`brew install node`) is more
  stable for this use case.
- **Windows:** Install Node.js from [nodejs.org](https://nodejs.org)
  (the LTS installer adds `node` and `npx` to your system PATH
  automatically), then restart Claude Desktop so the new PATH takes
  effect. If `npx` is still not found, use the full path, for example
  `C:\Program Files\nodejs\npx.cmd`.

**`401 Unauthorized`** — the token is wrong or was rotated. Generate a
new one in **Settings → Integrations** and update the `Authorization`
header.

**Tools call succeeds but the page-preview image doesn't render
inline** — that's expected for now. Claude Desktop renders text and
images from tool results inline, but doesn't iframe HTML resources.
FiestaBoard exposes a self-contained HTML preview at the MCP resource
`fiestaboard://page/{page_id}/preview.html`, which renders inline in
[MCP-UI](https://mcpui.dev)-aware clients but not in Desktop today.
For now, use `render_page_preview()` for an ASCII view or open the
FiestaBoard web UI for the pixel preview.
