# MCP clients

FiestaBoard exposes a [Model Context Protocol](https://modelcontextprotocol.io)
server at `/api/mcp/`, so an AI assistant like Claude Desktop or Claude Code
can read your pages, render template previews, configure plugins, and manage
schedules through conversation rather than the web UI.

This page walks through wiring each client up to a self-hosted FiestaBoard.

> **Where to get your token:** **Settings → Integrations → MCP / external
> clients → Generate token** (or **Rotate token**). The plaintext value is
> shown exactly once — copy it into your client config immediately.

> **Hostname tip:** Docker installs advertise as `fiestaboard.local`; the FiestaPi image advertises as `fiestapi.local`. Use whichever matches your install (or substitute the LAN IP if mDNS doesn't resolve on your network). The examples below use `fiestaboard.local`.

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
2. Open `~/Library/Application Support/Claude/claude_desktop_config.json`
   (create it if it doesn't exist) and merge in the `fiestaboard` entry
   from the reveal dialog. It looks like this:

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

3. **Fully quit** Claude Desktop (⌘Q — closing the window isn't enough)
   and relaunch. The `fiestaboard` server should appear under the MCP
   indicator with tools available.

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

## Troubleshooting

**"Some MCP servers could not be loaded… skipped: fiestaboard"** — your
`claude_desktop_config.json` entry is using the HTTP form (`"type":
"http"`, `"url"`, `"headers"`). Desktop rejects that. Switch to the
`mcp-remote` stdio form shown above.

**`Connection error: fetch failed … ETIMEDOUT`** in the Desktop MCP
log — almost always the missing trailing slash on the URL. Use
`/api/mcp/`, not `/api/mcp`.

**`command not found: npx`** in the Desktop MCP log — Claude Desktop
launches from `launchd` and may not inherit your shell's PATH. Replace
`"npx"` in the config with the absolute path from `which npx` (e.g.
`/opt/homebrew/bin/npx` on Apple Silicon Homebrew). `nvm`-managed Node
installs put `npx` under `~/.nvm/versions/node/<version>/bin/npx`,
which changes on every upgrade — installing Node via Homebrew (`brew
install node`) is more stable for this use case.

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
