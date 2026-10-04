# OAuth for Plugins: How It Works and Why

Status: shipped in 9.5.0 (Fiestaboard/FiestaBoard#2093). First consumer:
[fiestaboard-plugin--spotify](https://github.com/Fiestaboard/fiestaboard-plugin--spotify).
9.11.0 adds provider quirk fields, the `key_exchange` and `plex_pin` flows,
paste-to-finish, `report_oauth_rejected()`, and FiestaBot AI sign-in through
the same service.

This is the maintainer's reference: the pieces, the decisions behind them, and
what must not change. Two other documents cover the other audiences, and this
one does not repeat them:

- Plugin authors: [`docs/development/plugin-oauth.md`](../../development/plugin-oauth.md)
  (published). The manifest block, `get_oauth_token()`, testing, checklist.
- Users: [`docs/features/connecting-accounts.md`](../../features/connecting-accounts.md)
  (published).

## The Problem

A board is reached at something like `http://192.168.1.50:4420`: plain HTTP,
on a home network, with no public name. OAuth providers only redirect a
signed-in user to an `https://` URL registered in advance (loopback excepted).
A board cannot be that URL, and FiestaBoard runs no server that could be.

## The Shape of the Answer

```text
 Browser                Provider              fiestaboard.app/auth          Board (LAN)
    │  press Sign in                                                            │
    │──────────────────────────────────────────────────────────────────────────▶│ POST /api/oauth/connections/{id}/authorize
    │◀──────────────────────────────────────────────────────────────────────────│ authorization_url (state, PKCE challenge)
    │──── authorize ───────▶│                                                   │
    │◀─── 302 redirect_uri?code&state ──│                                       │
    │──────────────────────────────────▶│ oauth/redirect.html (static)          │
    │       reads board address from state; asks once per browser               │
    │◀────── location.replace(<board>/api/oauth/callback?code&state) ───────────│
    │──────────────────────────────────────────────────────────────────────────▶│ verify state, exchange code + verifier
    │◀──────────────────────────────────────────────────────────────────────────│ 302 ../../integrations?oauth=connected
```

Two flows, chosen per plugin in its manifest:

- **`relay`**: authorization code with PKCE, returning through a static page.
  Works with every provider.
- **`device`**: device authorization grant (RFC 8628). No redirect at all; the
  board polls. Only where the provider supports it for the needed scopes.

Two more since 9.11.0, for providers that are not standard OAuth:

- **`key_exchange`**: OpenRouter's PKCE exchange. No client ID; the return
  address goes in `callback_url`, and the token endpoint takes JSON and
  returns a non-expiring key. A headless start sends neither `callback_url`
  nor `state`, so the provider shows a bare code to paste. Every
  key_exchange start accepts a paste without `state` (PKCE binds the code),
  so a callback that comes back without `state` can still be finished.
- **`plex_pin`**: not OAuth. The board creates a strong PIN at plex.tv, sends
  the browser to app.plex.tv, and polls the PIN every 2 seconds on the device
  flow's thread machinery (`_DeviceFlow.kind`). Endpoints are constants in
  `plex.py`; a per-install `data/.oauth_client_identifier` is the
  `X-Plex-Client-Identifier`.

## The Pieces

| Piece | Where | What it does |
|---|---|---|
| Relay site | repo [Fiestaboard/auth](https://github.com/Fiestaboard/auth), served at `https://fiestaboard.app/auth/` | Static pages. `oauth/redirect.html` forwards the provider's response to the board; `oauth/boards.html` lists and forgets remembered boards. |
| OAuth module | `src/oauth/` | Flows, state, token storage, refresh. |
| Routes | `src/oauth/routes.py` | `GET /oauth/connections`, `GET`/`DELETE /oauth/connections/{id}`, `POST /oauth/connections/{id}/authorize` (takes `headless`), `POST /oauth/connections/{id}/complete` (paste to finish), `GET /oauth/callback`. |
| Plugin hook | `PluginBase.get_oauth_token()` and `report_oauth_rejected()` in `src/plugins/base.py` | The whole plugin-facing API. |
| AI sign-in | `src/ai/sign_in.py` | FiestaBot provider presets (OpenRouter, Hugging Face, ChatGPT), `AiProviderConnectionSource`, and the per-request token swap. |
| Manifest validation | `src/oauth/provider.py`, called from `src/plugins/manifest.py` | A bad `oauth` block refuses the plugin at load. |
| Settings UI | `web/src/components/plugin-settings/oauth-connection.tsx` | The "Account connection" section; mounted in the Integrations settings sheet, which also handles the `?oauth=` return. |
| Mock provider | `scripts/mock_oauth_provider.py` | Strict stand-in provider for end-to-end tests. |

Inside `src/oauth/`:

| File | Responsibility |
|---|---|
| `provider.py` | Parse and validate the manifest `oauth` block. Pure; imported by `src/plugins/manifest.py`, so it must not import the rest of `src`. |
| `pkce.py` | Verifier and S256 challenge. |
| `state.py` | Sign and verify `state`; the per-install key file. |
| `client.py` | HTTP to the provider's token and device endpoints, over an injectable transport. `HttpTransport` (`request_json`) carries JSON, GET, and custom headers for `key_exchange` and Plex. |
| `paste.py` | Parse a pasted redirect address or bare code. Pure. |
| `plex.py` | The Plex PIN calls and the client identifier file. |
| `tokens.py` | `data/oauth_tokens.json`. |
| `service.py` | Orchestration: start, callback, paste, device and PIN polling, refresh, rejection reports, disconnect. Start here. |
| `models.py`, `routes.py`, `errors.py` | Wire models, router, domain errors. |

The domain is in both ratchets (`tests/conventions_manifest.json`,
`tests/layering_manifest.json`).

## Decisions, and Why

**The relay lives at `fiestaboard.app/auth`, not its own subdomain.** A project
Pages site under the org's existing custom domain needs no DNS record and gets
the existing certificate. The cost is sharing an origin with the docs site: a
script injection there could add to the relay's remembered-boards list. It
could still only add a local address, because the list is re-validated on
every read.

**The board's address travels in `state`.** The relay has to know which board
to return to. The board puts the address the user is browsing it at into the
`state` payload (`b`), so nothing has to be set up first, and two boards on
one network each get their own sign-ins back. The relay cannot check the
signature, so it treats the address as a suggestion: it must be a local
address, and the person approves it once per browser. The board only checks
the address's shape (`normalize_board_url`); what counts as local is decided
in one place, the relay's `src/lib/board-address.js`.

**The callback is public.** `GET /oauth/callback` is in `AuthMiddleware`'s
public list because it arrives by cross-site navigation. What authenticates it
is the `state`: HMAC-signed with a dedicated per-install key
(`data/.oauth_state_key`, not the session key), expiring after ten minutes,
and single use because the board remembers the nonce of each flow it started
and drops it on first callback. Every other `/oauth` route needs a session.

**The callback path is `/api/oauth/callback`.** nginx already routes `/api/*`
to the backend in every config and under Home Assistant ingress, so no nginx
change was needed. The callback answers with a relative redirect
(`../../integrations?...`) so it also resolves under an ingress path prefix.

**The callback always redirects.** The caller is a person mid-sign-in. Every
failure comes back to Integrations as `?oauth=error&reason=...`, where `reason`
is one of `invalid_state`, `expired`, `access_denied`, `exchange_failed`,
`provider_error`, and the UI turns it into a sentence.

**Connections are per plugin instance.** Tokens are keyed by registry key
(`spotify`, `spotify:kitchen`). Two plugins on the same provider never share
tokens. Uninstalling a plugin or deleting an instance deletes its tokens
(`PluginService`).

**No provider is named in `src/`.** Providers come from plugin manifests. A
client secret in a manifest is refused, because plugin repositories are public.

**Users bringing their own app get a guided setup.** Most providers cap apps
they have not reviewed (Spotify: five hand-added accounts), so the usual model
is that each user registers an app and enters its client ID. The connection
API reports `client_id_setting`, `client_secret_setting`, and `app_setup_url`;
the settings UI renders numbered steps with those fields inside the Account
connection panel, leaves them out of the general settings form, and its
sign-in button saves the settings before starting the flow. The Spotify plugin
briefly shipped FiestaBoard's own client ID instead (1.1.0) and went back to
this model in 1.2.0 for that reason.

**Unknown `oauth` fields are a warning, not an error.** Plugins auto-update
hourly and cores are updated by hand, so a plugin routinely lands on an older
core. `provider_block_warnings` reports the field through
`GET /plugins/errors` and the plugin loads. 9.5.0 through 9.7.x refused the
manifest instead, which is why a plugin that must run there cannot use
`app_setup_url`.

**A plugin may bring its own app.** `oauth.client_id` ships a client ID. A
client ID or secret saved in the plugin's config only counts if
`settings_schema` declares that field (`OAuthProvider.user_client_id`), so a
plugin that ships an ID and offers no field cannot have it replaced. The
connection API reports `user_app`, and the UI hides app-setup help when it is
false. It also reports `shared_app` (a shipped client ID): when both are true,
the UI leads with a plain Sign in and offers the user's own app as an optional,
collapsed "Use your own app" section.

**Provider quirks are manifest fields, not code.** (9.11.0) `client_id_param`,
`scope_separator`, `device_scope_param`, `device_poll_scope`,
`endpoint_base_setting`, `plex_product`, `token_auth_method` and
`refresh_params` keep "no provider named in `src/`" true for TikTok, Strava,
Todoist, Twitch, Home Assistant, Plex, X and WHOOP. Each defaults to the
standard behavior. `token_auth_method: "basic"` moves the secret (and the
client ID) out of the form into an HTTP Basic header, form-encoding each part
as RFC 6749 §2.3.1 says; with no secret the body keeps the client ID. The
transport then gets a `headers=` keyword, which it is never sent otherwise,
so older two-argument transports keep working. Answer shapes need no field:
`client._raise_for_oauth_error` maps Twitch's `{"status", "message"}` errors
to RFC codes before looking at `error`, `_parse_scopes` takes a JSON array,
and `_token_request` unwraps `{"data": [{...}]}` (Instagram). `OAuthProvider.resolve_endpoints(config)` is
the only place endpoints are read, so a settings-based base URL applies to
every flow at once.

**Settings-based endpoints allow plain http only on the home network.**
(9.11.0) For `endpoint_base_setting`, `_base_url_error` accepts `https` to any
host, and `http` only to a host judged local from its name alone (RFC 1918,
loopback, link-local, CGNAT, IPv6 ULA, single-label names, `.local`, `.lan`,
`.home.arpa`, `.internal`). No DNS lookup, so a name cannot be made to look
local. This is a different rule from the relay's local-address rule and
answers a different question: where the board may send a client secret.

**Paste to finish.** (9.11.0) A relay can fail to reach the board (another
device, a blocked redirect), and some providers show a code instead of
redirecting. `POST /oauth/connections/{id}/complete` takes the pasted address
or code. Unlike the callback it needs a session. A pasted `state` must be one this
board issued, for this connection, and unused. A code with no `state` (a bare
code, or an address without one) is accepted only by a pending flow that opted
in (a headless `key_exchange`), because nothing else binds it to a flow. Refusals are `PastedCodeRejected` (400) with a reason slug.

A connection whose provider has a `redirect_uri_override` (ChatGPT's
loopback-only redirect) reports `paste_expected: true` on
`GET /oauth/connections`, so the UI knows before a sign-in starts that it
can only finish by paste. It opens the provider in a new tab from the click
itself (a tab opened after the authorize request returns is blocked by
Safari), keeps the board's tab on an open, focused "Finish signing in"
step, and says up front that the provider's tab will end on a page that
cannot load.

**Plugins can report a rejected token.** (9.11.0, closes Known Gap 1)
`report_oauth_rejected()` forces one refresh, at most once per 60 seconds per
connection (`FORCED_REFRESH_COOLDOWN_SECONDS`), and returns the new token. With
no refresh possible, the connection is marked for reauthorization with
`reauth_reason="rejected"`, which the API reports as `status_reason` so the UI
can say the provider stopped accepting the sign-in.

**FiestaBot AI providers are connections too.** (9.11.0) An AI provider in
`config.json` with `"sign_in": {"preset": "..."}` is a connection with id
`ai.<provider id>` and `kind: "ai"`, served by `AiProviderConnectionSource`
next to the plugin registry (`CompositeConnectionSource`). Its tokens live in
the token store, never in `config.json`; `resolve_provider_auth` swaps the
current token in as the provider's `api_key` on every request, and a provider
without `sign_in` is passed through untouched. The Integrations page ignores
`kind == "ai"`, and the callback returns AI sign-ins to Settings. Presets may
set fields no manifest can (`redirect_uri_override`, `token_params`,
`accept_issued_client_id`, `first_sign_in_params`) for ChatGPT's loopback
redirect and issued client. The ChatGPT `id_token` is discarded unread.

**Plugins may swap and renew their own token.** (9.11.0) Meta hands out a
1-hour token at sign-in that the app trades for a 60-day one and renews with
its own call, not a refresh token. Rather than a Meta-shaped manifest option
or a general plugin key-value store, `PluginBase` has two optional hooks,
found through `ConnectionTarget.plugin` (the registry's plugin object; `None`
for AI providers). `exchange_oauth_token(token)` runs after every successful
code exchange or device approval, before the tokens are stored;
`refresh_oauth_token(token)` runs inside `_try_refresh` (so under the
per-connection refresh lock) before the standard grant, and also for tokens
with no refresh token. Both get `{access_token, refresh_token, expires_at,
scopes}` and return `None` (no change, fall through) or `{access_token,
expires_in?, refresh_token?}`. A raising exchange hook keeps the provider's
token; a raising refresh hook counts as `_REFRESH_FAILED`. The base-class
defaults return `None`, so behavior for every other plugin is unchanged: the
only difference is that a token with no refresh token, inside the refresh
margin, looks up its target once per fetch to ask the hook. Hooks must not
call `get_oauth_token()` (the refresh lock is not re-entrant).

**Dev-only URL overrides.** `FIESTABOARD_OAUTH_URL_OVERRIDES`
(`src/oauth/overrides.py`) is a JSON object of URL prefix to replacement,
applied to every endpoint `ConnectionTarget.endpoints()` returns, to plex.tv
and app.plex.tv, and to an AI preset's `base_url`. It exists so the mock
provider can stand in for constant URLs. Unset, nothing changes.

**Tokens are not in backups.** `oauth_tokens.json` is not in the backup
allow-list. Restoring onto a new board means signing in again.

**Validation messages never repeat manifest values.** CodeQL treats anything
named `oauth` as a credential, and validation errors reach install logs. The
messages are fixed text; a test feeds a marker through every field.

## Behavior Worth Knowing

- Access tokens are refreshed when within 60 seconds of expiry
  (`REFRESH_MARGIN_SECONDS`), under a per-connection lock so that rotating
  refresh tokens are used once.
- A refresh refused with `invalid_grant`, `invalid_client`, or
  `unauthorized_client` marks the connection `reauthorization_required` and is
  not retried. Any other failure keeps serving the old token until it actually
  expires.
- Started-but-unfinished relay flows are held in memory, capped at 50. A
  restart forgets them; the user presses the button again.
- Device polling runs on a daemon thread per flow, honors the provider's
  interval, and adds five seconds on `slow_down`.
- `FIESTABOARD_OAUTH_REDIRECT_URI` overrides the redirect URI, for someone
  hosting their own copy of the relay.

## What Must Not Change

- **`https://fiestaboard.app/auth/oauth/redirect`, and the same address with
  `.html` on the end.** One or the other is registered as the redirect URI in
  every OAuth app anyone has created for a FiestaBoard plugin: 9.5.0 through
  9.7.x send the `.html` form, 9.8.0 and later the short one. GitHub Pages
  serves `oauth/redirect.html` at both. Renaming the `auth` repository,
  moving that page, changing the domain, or moving to a host that does not
  serve the page without its extension breaks every sign-in until each registration
  is edited by hand.
- **The `state` payload's `b` field and its `<base64url JSON>.<signature>`
  shape.** The relay parses it. Change both sides together, relay first.
- **`/api/oauth/callback`.** The relay appends it to the board address.
- **The local-address rule lives in the relay only.** Do not copy the list
  into the board.

## Testing

Unit tests: `tests/test_oauth_*.py`. They drive `OAuthService` with a scripted
transport and a fake clock, and the routes through the real app.

End to end, with the mock provider (this is how the feature was verified
before any real provider was involved):

```bash
# docker-compose.oauth-test.yml:  services: { fiestaboard: { ports: ["9400:9400"] } }
docker compose -f docker-compose.dev.yml -f docker-compose.oauth-test.yml up -d
docker compose -f docker-compose.dev.yml exec -d fiestaboard python scripts/mock_oauth_provider.py
```

Put a throwaway plugin whose `oauth` block points at `http://localhost:9400`
in `data/external_plugins/<id>/`, restart, and sign in from the Integrations
page. For Plex and the AI presets, set `FIESTABOARD_OAUTH_URL_OVERRIDES` (the
script's docstring has a ready mapping); the mock serves `key_exchange`,
Plex PINs, Home Assistant, Hugging Face and OpenAI paths, `/v1/responses`
and `/v1/models`. `tests/test_mock_oauth_provider.py` drives core against it
over real HTTP. The relay flow goes through the live relay and back to
`http://localhost:4420`. The walkthrough in the published guide lists the
cases to check: refresh (tokens live 20 seconds), revocation
(`POST /revoke-all`), replayed and tampered callbacks, disconnect.

The relay has its own tests (`npm test`, `npm run test:dist`) in its repo.

## Known Gaps

Raised while building the Spotify plugin. None is a bug; each is a candidate
for follow-up.

1. ~~**A plugin cannot report a rejected token.**~~ Closed in 9.11.0 by
   `report_oauth_rejected()`. Plugins that do not call it still show
   Connected until the next refresh fails.
2. **`get_oauth_token()` returns `None` for both "never signed in" and
   "reconnect needed".** The plugin's message cannot name the right button.
   The settings UI can (`status_reason`), but the plugin still cannot.
3. **Per-board-shape caching multiplies API calls**, and unavailable results
   are not cached, so every OAuth plugin against a rate-limited API writes its
   own shared snapshot and backoff.
4. **An `oauth` manifest on a pre-9.5.0 board loads silently without it.**
   `fiestaboard_version` is the guard.
5. **Nothing shows a device code on the board itself.**
6. ~~**The mock provider covers only `relay` and `device`.**~~ Closed in
   9.11.0: it serves every flow, and `FIESTABOARD_OAUTH_URL_OVERRIDES` reaches
   the constant URLs.
