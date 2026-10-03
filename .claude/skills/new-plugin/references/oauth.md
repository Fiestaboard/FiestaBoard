# Plugins that sign in with OAuth

Read this when the data source needs the user to sign in to an account ("Sign in with
Spotify/Google/GitHub…") rather than paste an API key. The platform runs the whole flow.
Your plugin **declares** the provider and **asks for a token**. The full author's guide is
`docs/development/plugin-oauth.md` in the core repo; this is the working recipe.

Reference implementation: `../fiestaboard-plugin--spotify` (also on GitHub under
`Fiestaboard/`). Read its `manifest.json`, `__init__.py`, and `tests/` before writing yours.

**Not for AI.** A plugin that calls a language model (OpenRouter, OpenAI, Hugging Face,
ChatGPT…) gets no `oauth` block and no key of its own: it uses `self.ai_complete()`. See
`ai.md`.

## Decide three things in the Step 1 interview

1. **Is OAuth actually needed?** If the service offers an API key or a personal token, use
   that instead (see `design-guidance.md`). OAuth is for when sign-in is the only way in.
2. **Which flow?** Look up the provider's docs.
   - `device`: the provider supports the device authorization grant *for the scopes you
     need*. The user types a short code. Preferred when available.
   - `relay`: everything else. Authorization code with PKCE, returning through
     `https://fiestaboard.app/auth/oauth/redirect`. Every provider supports it.
   - `key_exchange` (9.9.0): the provider trades the code for a long-lived API key instead
     of tokens (OpenRouter style). No client ID.
   - `plex_pin` (9.9.0): Plex only. No endpoints in the block.
3. **Whose app signs in?** Ask the user; do not guess.
   - **Each user registers their own app** (default): a `client_id` settings field, and a
     SETUP guide that walks through creating the app and pasting the redirect URI.
   - **The plugin brings its own app**: the user gives you a client ID to ship in
     `oauth.client_id`, and there is **no** client ID settings field. Only possible when the
     provider allows PKCE without a client secret. Check the provider's limits on
     unreviewed apps first (Spotify: five hand-added accounts) and tell the user about them
     before building.

If the user pastes a **client secret**, do not put it anywhere: not the manifest, not code,
not tests, not docs, not a commit. Tell them it is not needed for PKCE (or belongs in a
`client_secret_setting` field on each user's board) and that they should rotate it, since it
has now been shared in a conversation.

## Scaffold, then add OAuth by hand

Scaffold with `--type http` as usual. The generator has no OAuth mode; make these edits.

**`manifest.json`**

```json
"fiestaboard_version": ">=9.5.0",
"oauth": {
  "provider_name": "Example Music",
  "flows": ["relay"],
  "authorization_url": "https://example.com/oauth/authorize",
  "token_url": "https://example.com/oauth/token",
  "scopes": ["user-read-currently-playing"]
}
```

- User's own app: keep a `client_id` string in `settings_schema.properties` (no password
  widget needed; `client_id` is masked in API responses automatically) and do **not** list
  it under `required`. The platform shows it inside a guided setup in the Account
  connection panel, not in the settings form. Add `"client_secret_setting": "client_secret"`
  plus a `"ui:widget": "password"` field only if the provider requires a secret. Add
  `"app_setup_url": "https://…"` (the provider's developer page) so the guided setup can
  link to it, but only if `fiestaboard_version` is `>=9.8.0`: 9.5.0-9.7.x refuse a
  manifest with an `oauth` field they do not know.
- Plugin's own app: add `"client_id": "<the id>"` to the `oauth` block and **remove** any
  `client_id` field from `settings_schema`. A saved client ID only counts when the settings
  declare the field, so with no field the shipped one is always used.
- Remove the scaffold's `api_key` setting and its `env_vars` entry if nothing else needs them.
- Endpoints must be `https://`. No `client_secret` key, ever: the manifest is refused.
- Provider quirks (all **9.9.0**, so they need `"fiestaboard_version": ">=9.9.0"`; the full
  table is in `plugin-oauth.md` under "Provider Quirks"):
  - `client_id_param`: the client ID parameter's name (TikTok: `client_key`).
  - `scope_separator`: `" "` (default) or `","` (Strava, TikTok, Todoist).
  - `device_scope_param` / `device_poll_scope`: Twitch's `scopes` name and scopes on the poll.
  - `endpoint_base_setting`: a settings key holding the provider's base address, for a
    provider on the user's own network (Home Assistant); the endpoints are then paths.
  - `plex_product`: the product name `plex_pin` shows on Plex.
  - `token_auth_method`: `"post"` (default) or `"basic"` (client secret as HTTP Basic, X).
  - `refresh_params`: extra string fields sent with every refresh (WHOOP:
    `{"scope": "offline"}`); may not set `grant_type`, `refresh_token`, or the client fields.
- Scopes: the least that works. Read-only where the provider offers it.

**`__init__.py`**

```python
NOT_SIGNED_IN = "Not signed in to Example Music. Open this plugin's settings and sign in."

def fetch_data(self) -> PluginResult:
    try:
        token = self.get_oauth_token()
        if not token:
            return PluginResult(available=False, error=NOT_SIGNED_IN)
        response = requests.get(API_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        ...
    except Exception as exc:  # fetch_data must never raise
        return PluginResult(available=False, error=str(exc))
```

Rules that are easy to get wrong:

- Call `self.get_oauth_token()` on **every** fetch. Never store the token on `self`, in a
  cache, or on disk. The platform refreshes it; the next call returns the new one.
- `None` means not signed in **or** must sign in again. You cannot tell which, so the message
  says "sign in" and names the plugin's settings. Make **no** request.
- Never implement any part of OAuth: no authorize URL, no token exchange, no refresh, no
  redirect handling, no callback route.
- Unavailable results are **not cached** by the platform, so after a failure `fetch_data`
  runs again on the next render. Keep your own cooldown: honor `Retry-After` on `429`, back
  off briefly on `5xx`/timeouts, and do not hammer after `401`/`403`.
- Results are cached **per board shape**. For a rate-limited API, keep one shared snapshot
  for a few seconds so a Flagship and a Note are served by one request.
- `401` → call `self.report_oauth_rejected()` (9.9.0; guard with
  `getattr(self, "report_oauth_rejected", None)`). It returns a refreshed token: retry the
  request **once** with it. `None` → "rejected the sign-in, press Reconnect", no more
  requests. `403` → say what the user can do about it (often an account that is not allowed
  to use the app).

**Token hooks (9.9.0, optional).** Override only for a provider whose tokens need it:

- `exchange_oauth_token(self, token)`: called once after each sign-in with
  `{"access_token", "refresh_token", "expires_at", "scopes"}`. Return `None` to keep it, or
  `{"access_token", "expires_in"?, "refresh_token"?}` to store instead (Meta: swap the
  1-hour token for a 60-day one).
- `refresh_oauth_token(self, token)`: called near `expires_at`, before the standard refresh.
  Return `None` for the standard refresh, or a replacement in the same shape.
- Both: an exception keeps the current token; never call `get_oauth_token()` or
  `report_oauth_rejected()` inside them; set the timeout on every request.

**`tests/`**

- In the plugin fixture: `p.get_oauth_token = lambda: "test_access_token"`. Mock the
  provider's API with `requests` patches as for any `http` plugin.
- Required cases: bearer header carries the token; `None` → unavailable **and no request
  made**; `401` reports the rejection and retries once with the returned token (and stops
  when it returns `None`); `403`; `429` with `Retry-After`; timeout; a new token is used
  right after a rejection. Patch `p.report_oauth_rejected` the same way as the token.
- Validate the block with the platform's validator:

  ```python
  from src.oauth.provider import parse_provider_block, validate_provider_block

  def test_oauth_block_is_valid_and_has_no_secret(manifest_data):
      block = manifest_data["oauth"]
      assert validate_provider_block(block) == []
      assert "client_secret" not in block
  ```

- Fixtures use invented names and obviously fake tokens.

**`.github/workflows/ci.yml`**: pin the FiestaBoard checkout to a release with OAuth and
keep it equal to `fiestaboard_version`:

```yaml
repository: Fiestaboard/FiestaBoard
ref: v9.5.0
```

**`docs/SETUP.md`** (canonical section order still applies): what the plugin can see, in
plain words; how to create the app, field by field (user's-own-app model only); the redirect
URI, which the user **copies from the plugin's Account connection section** (it is
`https://fiestaboard.app/auth/oauth/redirect`, but boards on 9.5-9.7 send it with `.html` on
the end and providers match exactly, so never tell them to type it from your docs); sign in
with the **Sign in with <Provider>** button and confirm the board's address the first time;
any account limits, stated up front; troubleshooting keyed by your exact error strings. Link
to `https://fiestaboard.app/docs/features/connecting-accounts`.

## Verify without a real account

`scripts/mock_oauth_provider.py` in the core repo is a strict stand-in provider (PKCE
required, single-use codes, 20-second access tokens, rotating refresh tokens). The walkthrough
is in `docs/development/plugin-oauth.md` under "End to end, without a real account": publish
port 9400 with a compose override, start the mock in the dev container, put a **copy** of the
plugin with its endpoints pointed at `http://localhost:9400` in `data/external_plugins/<id>/`,
restart, and sign in from the Integrations page. Never commit that copy.

You cannot sign in to the real provider for the user. Say so in your Step 8 summary: one
real sign-in is theirs to do before the registry PR leaves draft.

## Registry entry

`"fiestaboard_version": ">=9.5.0"` in the registry entry too, matching the manifest.

## Checklist before you call it done

- [ ] `oauth` block validates; no `client_secret` anywhere in the repo or its history
- [ ] `fiestaboard_version` `>=9.5.0` in manifest and registry entry; CI pinned to match
- [ ] `get_oauth_token()` called every fetch; nothing stored; `None` makes no request
- [ ] `401` → `report_oauth_rejected()` and one retry; `fiestaboard_version` `>=9.9.0` if any
      9.9.0 flow, quirk field, or hook is used
- [ ] Cooldowns for `401`/`403`/`429`/`5xx`; one request shared across board shapes if rate limited
- [ ] SETUP.md covers permissions, app creation (if any), sign-in, limits, troubleshooting
- [ ] The user knows a real sign-in test is still theirs to do
