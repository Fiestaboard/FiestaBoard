---
sidebar_position: 2
description: "Build a FiestaBoard plugin that signs in to an online account with OAuth: the manifest oauth block, get_oauth_token(), flows, credentials, testing, and a worked Spotify example."
keywords: [FiestaBoard OAuth plugin, get_oauth_token, manifest oauth block, PKCE, device code flow, redirect URI, plugin sign-in, Spotify plugin, plugin development]
---

# Signing In with OAuth

Some data lives behind a user's account on another service: what they're playing, their calendar, their orders. A plugin reaches that data with OAuth, and FiestaBoard does the hard part for you. You **declare** the provider in `manifest.json` and **ask for a token** in `fetch_data`. The platform runs the sign-in, stores the tokens, refreshes them, and draws the sign-in button in your plugin's settings.

Calling a language model is not a reason to add OAuth: use [FiestaBoard's AI providers](/docs/development/plugin-ai) instead, which the user signs in to once in Settings.

This page is the complete reference for plugin authors, human or AI. It assumes you have read the [Plugin Development Guide](/docs/development/plugin-guide). For what your users see, read [Connecting Accounts](/docs/features/connecting-accounts).

**Requires FiestaBoard 9.5.0 or later.** Set `"fiestaboard_version": ">=9.5.0"` in your manifest. A plugin that uses anything marked **9.11.0** on this page (the `key_exchange` and `plex_pin` flows, the [provider quirk fields](#provider-quirks), or `report_oauth_rejected()`) sets `">=9.11.0"` instead.

## The Short Version

1. Add an `oauth` block to `manifest.json` naming the provider's endpoints and the scopes you need.
2. In `fetch_data`, call `self.get_oauth_token()`. If it returns `None`, return an unavailable result that tells the user to sign in. Otherwise send it as a bearer token.
3. Never write an OAuth flow, store a token, or ship a client secret. The platform owns all three.

```json
{
  "id": "example_music",
  "name": "Example Music",
  "version": "1.0.0",
  "fiestaboard_version": ">=9.5.0",
  "oauth": {
    "provider_name": "Example Music",
    "flows": ["relay"],
    "authorization_url": "https://example.com/oauth/authorize",
    "token_url": "https://example.com/oauth/token",
    "scopes": ["user-read-currently-playing"]
  },
  "settings_schema": {
    "type": "object",
    "properties": {
      "client_id": {
        "type": "string",
        "title": "Client ID",
        "description": "From the app you created in Example Music's developer settings."
      }
    }
  }
}
```

```python
import requests

from src.plugins.base import PluginBase, PluginResult

NOT_SIGNED_IN = "Not signed in to Example Music. Open this plugin's settings and sign in."


class ExampleMusicPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "example_music"

    def fetch_data(self) -> PluginResult:
        try:
            token = self.get_oauth_token()
            if not token:
                return PluginResult(available=False, error=NOT_SIGNED_IN)
            response = requests.get(
                "https://api.example.com/v1/me/now-playing",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 401:
                return PluginResult(available=False, error="Example Music rejected the sign-in. Press Reconnect.")
            response.raise_for_status()
            return PluginResult(available=True, data={"title": response.json()["title"].upper()})
        except Exception as exc:  # fetch_data must never raise
            return PluginResult(available=False, error=str(exc))


Plugin = ExampleMusicPlugin
```

That is a working OAuth plugin. The rest of this page explains each choice.

## Why the Platform Does This

A FiestaBoard usually lives on a home network at an address like `http://192.168.1.50:4420`. OAuth providers only send a signed-in user back to an `https://` address registered in advance, and a board is neither public nor HTTPS. A plugin cannot solve that by itself, so the platform solves it once for every plugin. Most plugins use one of the first two flows; the other two exist for providers that do not do standard OAuth:

| Flow | How the user signs in | Use it when |
|------|-----------------------|-------------|
| `relay` | The browser goes to the provider, then returns through a small static page at `https://fiestaboard.app/auth/oauth/redirect`, which hands it back to the board. Authorization code with PKCE. | Always available: every OAuth provider supports it. |
| `device` | The settings show a short code. The user enters it on the provider's site from any device, and the board waits for approval. Device authorization grant (RFC 8628). | The provider supports device codes **for the scopes you need**. No redirect is involved. |
| `key_exchange` | Like `relay`, but with no client ID: the provider trades the code and PKCE verifier for a long-lived API key, sent as JSON. The provider is told where to return with a `callback_url` parameter. **9.11.0.** | OpenRouter-style "sign in to get a key" providers. |
| `plex_pin` | The board creates a PIN at plex.tv and opens Plex's sign-in page in a new tab. The settings wait while the board polls the PIN for a token. **9.11.0.** | Plex only. The block needs no endpoints: they are plex.tv's. |

If the browser does not make it back to the board after a `relay` or `key_exchange` sign-in, the user can paste the address they landed on (or the code the provider showed) into the settings, and the board finishes the sign-in from that. You do nothing to enable it.

The redirect URI for the `relay` flow is the same for every board and every plugin:

```text
https://fiestaboard.app/auth/oauth/redirect
```

FiestaBoard 9.5.0 through 9.7.x sends the same address with `.html` on the end. Both reach the same page, but providers compare redirect URIs exactly. So in your setup guide, tell users to **copy the redirect URI from the plugin's settings**, which always shows the one their board sends, instead of typing one from your docs.

The first time someone signs in from a browser, that page shows the board's address and asks them to confirm it, then remembers the answer. It only ever forwards to an address on a local network. You do not build, host, or configure any of it.

## The `oauth` Block

| Field | Required | Meaning |
|-------|----------|---------|
| `flows` | yes | `["relay"]`, `["device"]`, or both. The first one listed is the one the sign-in button uses. `key_exchange` and `plex_pin` are also accepted from 9.11.0. |
| `token_url` | yes, except for `plex_pin` | The provider's token endpoint. For `key_exchange`, the endpoint that trades the code for a key. |
| `authorization_url` | for `relay` and `key_exchange` | The provider's authorization endpoint. |
| `device_authorization_url` | for `device` | The provider's device authorization endpoint. |
| `scopes` | no | Scopes to request. Ask for the least that works; users see the list on the consent screen. |
| `provider_name` | no | Shown in the UI ("Sign in with Example Music"). Defaults to your plugin's name. |
| `client_id` | no | A client ID shipped with the plugin. See [Whose App?](#whose-app). |
| `client_id_setting` | no | The `settings_schema` key that holds a user's own client ID. Default `client_id`. |
| `client_secret_setting` | no | The `settings_schema` key that holds a user's client secret, for providers that require one. Omit it for a PKCE-only client. |
| `authorization_params` | no | Extra fixed query parameters for the authorization request, as strings. For example `{"access_type": "offline"}`. |
| `app_setup_url` | no | The provider's developer page, where a user creates their own app. The guided setup links to it. `https://` only. Added in 9.8.0; see the note on unknown fields below. |
| `client_id_param` | no | The name the provider gives the client ID parameter, in the authorization request and the token request. Default `client_id`; TikTok wants `client_key`. **9.11.0.** |
| `scope_separator` | no | How scopes are joined: `" "` (the default) or `","`. Strava, TikTok, and Todoist want `","`. **9.11.0.** |
| `device_scope_param` | no | The scope parameter's name on the device authorization request. Default `scope`; Twitch wants `scopes`. **9.11.0.** |
| `device_poll_scope` | no | `true` to send the scopes again when polling the device token endpoint (Twitch). Default `false`. **9.11.0.** |
| `endpoint_base_setting` | no | A `settings_schema` key that holds the provider's base address, for a provider that runs on the user's own network (Home Assistant). The endpoint fields then hold paths, such as `"/auth/token"`. **9.11.0.** |
| `plex_product` | no | The product name the `plex_pin` flow sends to Plex, shown on Plex's sign-in page and device list. Default `FiestaBoard`. **9.11.0.** |
| `token_auth_method` | no | How the client secret reaches the token endpoint: `"post"` (the default, in the form body) or `"basic"` (an HTTP Basic `Authorization` header, `client_secret_basic`). Applies to the code exchange, refresh, and device poll. Without a secret the client ID stays in the body either way. X wants `"basic"` for confidential apps. **9.11.0.** |
| `refresh_params` | no | Extra form fields sent with every refresh, as strings. For example `{"scope": "offline"}` (WHOOP). May not set `grant_type`, `refresh_token`, `client_id`, `client_secret`, or the name in `client_id_param`. **9.11.0.** |

The manifest is validated when the plugin loads, and a plugin with a bad `oauth` block is refused with a message naming the problem:

- Endpoints must be `https://`. Plain `http://` is accepted only for `localhost`, `127.0.0.1`, and `::1`, which is what a local test provider looks like. With `endpoint_base_setting`, the endpoints must be paths starting with `/` instead, and the address the user saves is checked when they sign in (see [Provider Quirks](#provider-quirks)).
- `flows` must be a non-empty list of `relay`, `device`, `key_exchange`, and `plex_pin`, without repeats.
- `client_id_param`, `device_scope_param`, and `endpoint_base_setting` are parameter names: letters, digits, and underscores. `scope_separator` is `" "` or `","`. `device_poll_scope` is `true` or `false`. `token_auth_method` is `"post"` or `"basic"`. `refresh_params` is an object of strings.
- `endpoint_base_setting` must name a key in `settings_schema`.
- **`client_secret` is never allowed in a manifest.** Plugin repositories are public.
- A field your board's FiestaBoard does not know is ignored and reported as a warning in `GET /plugins/errors`, so a plugin using a field from a newer release still loads on an older one. **9.5.0 through 9.7.x refuse the whole plugin instead**, so a plugin that must run on those releases cannot use `app_setup_url`. A 9.8.x board ignores the 9.11.0 fields the same way, which means it would sign in with the wrong parameter names: set `fiestaboard_version` to `>=9.11.0` when you use them. A flow name an older board does not know refuses the plugin there.
- `authorization_params` may not set `response_type`, `client_id`, `redirect_uri`, `state`, `scope`, `code_challenge`, or `code_challenge_method`, nor the name in `client_id_param`. The platform sets those.
- `scopes` entries are strings without spaces.
- Transition plugins may not declare `oauth`.

## Provider Quirks {#provider-quirks}

**Requires FiestaBoard 9.11.0.** Many providers bend the OAuth standard a little. These fields cover the common bends, so a plugin never has to run its own flow. Each one has a default that matches the standard, so leave out any field you do not need.

A provider that calls the client ID something else and joins scopes with commas (TikTok):

```json
"oauth": {
  "provider_name": "TikTok",
  "flows": ["relay"],
  "authorization_url": "https://www.tiktok.com/v2/auth/authorize/",
  "token_url": "https://open.tiktokapis.com/v2/oauth/token/",
  "scopes": ["user.info.basic", "user.info.stats"],
  "client_id_param": "client_key",
  "scope_separator": ","
}
```

A device flow with a differently named scope parameter, where the token poll repeats the scopes (Twitch):

```json
"oauth": {
  "provider_name": "Twitch",
  "flows": ["device"],
  "device_authorization_url": "https://id.twitch.tv/oauth2/device",
  "token_url": "https://id.twitch.tv/oauth2/token",
  "scopes": ["user:read:follows"],
  "device_scope_param": "scopes",
  "device_poll_scope": true
}
```

A provider that runs on the user's own network (Home Assistant). The endpoints are paths, and the base address comes from a setting the user fills in:

```json
"oauth": {
  "provider_name": "Home Assistant",
  "flows": ["relay"],
  "endpoint_base_setting": "base_url",
  "authorization_url": "/auth/authorize",
  "token_url": "/auth/token"
},
"settings_schema": {
  "type": "object",
  "properties": {
    "base_url": {"type": "string", "title": "Home Assistant address"}
  }
}
```

When the user signs in, the board joins the saved address to each path. It sends credentials only to an `https://` address, or to plain `http://` on the user's own network: a private IP address, `localhost`, a single-label name, or a name ending in `.local`, `.lan`, `.home.arpa`, or `.docker.internal`. Link-local addresses (`169.254.x.x`), other `.internal` names, and cloud metadata hosts are refused. Anything else, an empty value, or an address with a query, fragment, or user name stops the sign-in with a message asking the user to check the address.

A Plex sign-in. The block has no endpoints and no client ID:

```json
"oauth": {
  "provider_name": "Plex",
  "flows": ["plex_pin"],
  "plex_product": "FiestaBoard"
}
```

`get_oauth_token()` returns the Plex token. Send it the way Plex expects, as the `X-Plex-Token` header, not as a bearer token. Each board has its own `X-Plex-Client-Identifier`, created on first use and kept in `data/.oauth_client_identifier`.

A provider that hands out an API key instead of tokens (OpenRouter's flow):

```json
"oauth": {
  "provider_name": "Example Router",
  "flows": ["key_exchange"],
  "authorization_url": "https://router.example.com/auth",
  "token_url": "https://router.example.com/api/v1/auth/keys"
}
```

The key does not expire, so there is nothing to refresh. The settings also offer **Sign in without a browser redirect**, which asks the provider to show a code that the user pastes back.

A confidential client that must send its secret as HTTP Basic, and a provider that wants a field on every refresh:

```json
"oauth": {
  "provider_name": "X",
  "flows": ["relay"],
  "authorization_url": "https://x.com/i/oauth2/authorize",
  "token_url": "https://api.x.com/2/oauth2/token",
  "scopes": ["users.read", "tweet.read", "offline.access"],
  "client_secret_setting": "client_secret",
  "token_auth_method": "basic"
}
```

```json
"refresh_params": {"scope": "offline"}
```

The platform also reads a few answer shapes without any field: Twitch's `{"status": 400, "message": "authorization_pending"}` poll errors (and `slow_down`, `invalid device code`, `Invalid refresh token`), a `scope` sent as a JSON array, and a token answer wrapped as `{"data": [{...}]}` (Instagram).

### Swapping and renewing the token yourself {#token-hooks}

**Requires FiestaBoard 9.11.0.** Some providers hand out a short-lived token at sign-in that the app is expected to trade for a long-lived one, and renew with a call of their own rather than a refresh token (Meta: Instagram, Threads, Facebook). Two optional `PluginBase` methods cover that. The platform still stores the token, so it survives a restart:

```python
def exchange_oauth_token(self, token):
    """Called once after each sign-in. Return None to keep the token."""
    long_lived = self._exchange_for_long_lived(token["access_token"])  # your HTTP call
    return {"access_token": long_lived["access_token"], "expires_in": long_lived["expires_in"]}

def refresh_oauth_token(self, token):
    """Called when the stored token is within a minute of expires_at. Return None for the standard refresh."""
    renewed = self._renew(token["access_token"])
    return {"access_token": renewed["access_token"], "expires_in": renewed["expires_in"]}
```

- Both receive `{"access_token", "refresh_token", "expires_at", "scopes"}` (`expires_at` is epoch seconds or `None`) and return `None` or `{"access_token", "expires_in"?, "refresh_token"?}`. A missing `refresh_token` keeps the one already stored; a missing `expires_in` means the token does not expire.
- If `exchange_oauth_token` raises or returns something without an `access_token`, the sign-in token is kept. If `refresh_oauth_token` raises, the current token is served until it expires and the hook is asked again on the next fetch.
- To renew earlier than the provider's expiry, return a shorter `expires_in`.
- Neither hook may call `get_oauth_token()` or `report_oauth_rejected()`.
- The settings your hooks need, such as a client secret, come from `self.config` as usual. A board before 9.11.0 never calls them.

## Whose App? {#whose-app}

Every OAuth sign-in runs under an "app" (or "client") registered with the provider. You choose who registers it. The choice decides what the user sees.

### Each user registers their own app

Declare a `client_id` field in `settings_schema` and do not ship a `client_id` in the `oauth` block. The user creates an app in the provider's developer settings, gives it the redirect URI, and pastes the app's client ID into your plugin's settings.

FiestaBoard turns this into a guided setup in the plugin's **Account connection** section: numbered steps, a link to the provider's developer page (set `app_setup_url`), a link to your `docs/SETUP.md`, the redirect URI with a copy button, and the Client ID field itself. The sign-in button saves what was typed and starts the sign-in in one press. Your client ID field (and client secret field, if any) appears there and not in the general settings form, so declare it plainly and do not mark it `required`: the panel already will not sign in without it.

This works for every user without limits, and it is the right default: most providers restrict apps they have not reviewed. Your `docs/SETUP.md` must still walk through creating the app, with what to enter in each of the provider's fields.

If the provider requires a client secret, add `"client_secret_setting": "client_secret"` and a matching password field:

```json
"client_secret": {
  "type": "string",
  "title": "Client Secret",
  "ui:widget": "password"
}
```

The names `client_id` and `client_secret` are masked in API responses automatically. The secret is stored on the user's board and sent only to the provider's token endpoint.

### The plugin brings its own app

Ship your app's client ID in the `oauth` block and offer **no** client ID field:

```json
"oauth": {
  "provider_name": "Spotify",
  "flows": ["relay"],
  "authorization_url": "https://accounts.spotify.com/authorize",
  "token_url": "https://accounts.spotify.com/api/token",
  "scopes": ["user-read-playback-state"],
  "client_id": "0123456789abcdef0123456789abcdef"
}
```

Users open the settings and see one button, **Sign in with Spotify**, and nothing to set up. A client ID is not a secret, so publishing it is fine. This only works with providers that support PKCE without a client secret, because a secret cannot ship.

Before you choose this, check the provider's limits on apps they have not reviewed. Spotify, for example, admits only five hand-added accounts to an app in Development Mode and offers no wider mode to open-source projects. Every other user signs in successfully and then gets `403` from the API. If your provider has a limit like this, say so at the top of your setup guide and make your `403` message explain it.

### The rule that decides

**A client ID or secret saved in the plugin's config only counts if `settings_schema` declares that field.**

| Manifest | Client ID used |
|----------|----------------|
| `oauth.client_id` shipped, no settings field | Always the shipped one. A value saved earlier or through the API is ignored. |
| `oauth.client_id` shipped, settings field declared | The user's value if they saved one, otherwise the shipped one. |
| No `oauth.client_id`, settings field declared | The user's value. The sign-in button is disabled until one is saved. |

On FiestaBoard 9.5.0 through 9.7.x a saved value always overrode a shipped client ID, and the settings showed app-setup help even when there was nothing to set up. 9.8.0 and later follow the table above.

## Using the Token

`self.get_oauth_token()` returns the current access token as a string, or `None`.

- **Call it on every fetch and use what it returns.** Do not keep the token in an attribute, a cache, or a file. The platform refreshes it shortly before it expires, and the next call returns the new one.
- **`None` means the user is not signed in, or has to sign in again.** You cannot tell the two apart, so word the message to cover both: "Open this plugin's settings and sign in." Return `PluginResult(available=False, error=...)` and make no request.
- **Each plugin instance has its own connection.** Two instances of your plugin can be signed in to two accounts. Another plugin never sees your tokens.

### Handling the provider's answers

The platform manages the token. Your plugin still has to handle what the provider's API says:

| Answer | What it means | What to do |
|--------|---------------|------------|
| `401` | The token was rejected, usually because the user revoked access. | Return unavailable and tell the user to press **Reconnect**. Do not retry on every render. |
| `403` | Signed in, but not allowed. Common with apps the provider limits to listed accounts. | Return unavailable with a message that says what to do about it. |
| `429` | Rate limited. | Honor `Retry-After`. Do not call again until it has passed. |
| `5xx`, timeout | The provider is having trouble. | Back off for a short while. Consider showing the last good data briefly. |

Two platform behaviors make this your job rather than something you get for free:

- **Unavailable results are not cached.** After a failure, `fetch_data` is called again on the next render. Without your own cooldown, a rate-limited plugin keeps hitting the provider.
- **Results are cached per board shape.** A Flagship and a Note showing the same plugin fetch separately. For a rate-limited API, keep one shared snapshot inside the plugin for a few seconds so that both are served by one request.

### Reporting a rejected token

**Requires FiestaBoard 9.11.0.** When the provider answers `401`, call `self.report_oauth_rejected()`. The platform refreshes the token once if it can and returns the new one, so retry the request once with it. `None` means the user has to sign in again. The settings then say *Provider* stopped accepting the sign-in, so return an unavailable result and make no more requests.

```python
if response.status_code == 401:
    report = getattr(self, "report_oauth_rejected", None)  # absent before 9.11.0
    new_token = report() if report else None
    if not new_token:
        return PluginResult(available=False, error="Example Music rejected the sign-in. Sign in again in this plugin's settings.")
    response = requests.get(url, headers={"Authorization": f"Bearer {new_token}"}, timeout=10)
```

If several requests were in flight with the same token, each may report its own `401`: the platform knows which token it last gave the plugin, so a report about a token it has already replaced just returns the new one. A plugin that keeps tokens elsewhere can pass the refused one as `report_oauth_rejected(token=...)`.

The forced refresh runs at most once a minute per connection, so a plugin that reports on every render does not hammer the provider. Report only a real rejection of the token, never a `403`, `429`, or outage.

On 9.5.0 through 9.8.x, or if you do not call it, the settings can keep showing **Connected** until the platform's next refresh fails. Your error message is what the user sees in the meantime, so make it actionable.

### Guarding against an older FiestaBoard

Setting `fiestaboard_version` to `>=9.5.0` is the main protection. If you want a friendly message on an older board that somehow loads the plugin:

```python
get_token = getattr(self, "get_oauth_token", None)
if get_token is None:
    return PluginResult(available=False, error="Update FiestaBoard to use this plugin.")
```

## What Your Users See

You build no UI. When a plugin declares `oauth`, its settings gain an **Account connection** section:

- **Not connected**: a **Sign in with *Provider*** button. With the user's-own-app model it sits under the guided setup described in [Whose App?](#whose-app) and stays disabled until a Client ID is entered.
- **Waiting for approval** (device flow): the address to visit and the code to enter, with a copy button. It updates by itself when the user approves.
- **Waiting for Plex** (`plex_pin`): Plex's sign-in page opens in a new tab, and the settings update by themselves when the user approves. There is no code to enter.
- **Paste to finish** (9.11.0): after a `relay` or `key_exchange` start, a **Sign-in didn't come back? Paste the address or code** box is offered for ten minutes. The user pastes the address the browser stopped at, or the code the provider showed, and presses **Finish sign-in**.
- **Connected**: **Reconnect** and **Disconnect** buttons.
- **Reconnect needed**: the provider refused a token refresh. Your plugin gets `None` until the user signs in again. When your plugin reported the rejection (9.11.0), the message reads "*Provider* stopped accepting the sign-in. Sign in again."

After a relay sign-in the user lands back on the Integrations page with your plugin's settings open and a confirmation. Failures arrive there too, as a sentence.

## Testing

### Unit tests

Do not test the OAuth flow; the platform does. Test what your plugin does with a token and without one. Replace `get_oauth_token` on the instance and mock the provider's API as you would for any HTTP plugin:

```python
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from plugins.example_music import ExampleMusicPlugin

MANIFEST = json.loads((Path(__file__).parent.parent / "manifest.json").read_text())


@pytest.fixture
def plugin():
    p = ExampleMusicPlugin(MANIFEST)
    p.get_oauth_token = lambda: "test_access_token"
    return p


def test_sends_the_token_as_a_bearer_header(plugin):
    with patch("plugins.example_music.requests.get") as get:
        get.return_value = Mock(status_code=200, json=lambda: {"title": "Low Tide"})
        result = plugin.fetch_data()
    assert result.available is True
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer test_access_token"


def test_makes_no_request_when_not_signed_in(plugin):
    plugin.get_oauth_token = lambda: None
    with patch("plugins.example_music.requests.get") as get:
        result = plugin.fetch_data()
    assert result.available is False
    assert "sign in" in result.error.lower()
    get.assert_not_called()
```

Also cover `401`, `403`, `429` with `Retry-After`, a timeout, and that a new token is used immediately after a rejection.

Validate your `oauth` block with the platform's own validator, so that a mistake fails in your CI and not at install time:

```python
from src.oauth.provider import parse_provider_block, validate_provider_block


def test_oauth_block_is_valid_and_has_no_secret():
    block = MANIFEST["oauth"]
    assert validate_provider_block(block) == []
    assert "client_secret" not in block
    assert parse_provider_block(block, MANIFEST["name"]).flows == ("relay",)
```

Use invented account data in fixtures, and obviously fake tokens such as `test_access_token`.

### CI

A plugin repository's CI checks out FiestaBoard to run against. Pin that checkout to a release that has OAuth, and keep it in step with `fiestaboard_version`:

```yaml
- uses: actions/checkout@v4
  with:
    repository: Fiestaboard/FiestaBoard
    ref: v9.5.0   # keep equal to fiestaboard_version in manifest.json
    path: fiestaboard-core
```

### End to end, without a real account

FiestaBoard ships a strict stand-in provider, `scripts/mock_oauth_provider.py`. It requires PKCE, issues single-use codes, rotates refresh tokens, and expires access tokens after 20 seconds so that refresh happens while you watch. It accepts the client secret in the body or as HTTP Basic, and also serves the other flows: `key_exchange` (`/auth` and `/api/v1/auth/keys`), Plex PINs (`/api/v2/pins` and an approval page at `/plex/auth`), the authorize and token pair under Home Assistant's `/auth/…` and Hugging Face's `/oauth/…` paths, and an OpenAI-style `/v1/responses` stream with `/v1/models`. The docstring at the top of the script lists every endpoint.

1. Start the development stack with port 9400 published, because the relay flow sends your browser to the provider. Save this next to `docker-compose.dev.yml` as `docker-compose.oauth-test.yml`:

   ```yaml
   services:
     fiestaboard:
       ports:
         - "9400:9400"
   ```

   ```bash
   docker compose -f docker-compose.dev.yml -f docker-compose.oauth-test.yml up -d
   docker compose -f docker-compose.dev.yml exec -d fiestaboard python scripts/mock_oauth_provider.py
   ```

2. Put a **copy** of your plugin in `data/external_plugins/<plugin_id>/` and, in that copy only, point the endpoints at the mock:

   ```json
   "authorization_url": "http://localhost:9400/authorize",
   "device_authorization_url": "http://localhost:9400/device/code",
   "token_url": "http://localhost:9400/token"
   ```

   Point the copy's API calls at `http://localhost:9400/me` too, or stub them. Restart the container so the plugin loads.

3. Open `http://localhost:4420`, go to **Integrations**, open the plugin's settings, and sign in. The relay flow passes through the real `fiestaboard.app` page and back. For the device flow, approve the code as if from another device:

   ```bash
   curl "http://localhost:9400/device/approve?user_code=<CODE>"
   ```

4. Check the cases that matter. A plugin's results are cached for its refresh interval (five minutes unless it declares `refresh_seconds`), so to make the plugin fetch again straight away, turn it off and on with its toggle on the Integrations page.
   - Wait 20 seconds and make it fetch: the board refreshes the token and your plugin keeps working.
   - `curl -X POST http://localhost:9400/revoke-all`, then make it fetch: the settings show **Reconnect needed** and your plugin reports that it is not signed in.
   - Press **Disconnect**: your plugin reports that it is not signed in on its next fetch. Signing in and disconnecting clear the plugin's cache, so these two take effect without the toggle.
   - `curl http://localhost:9400/log` shows every request the provider saw, with secrets replaced by their lengths.

For endpoints that are not in a manifest (Plex, and the FiestaBot AI sign-ins), set `FIESTABOARD_OAUTH_URL_OVERRIDES` on the container to a JSON object of URL prefixes and their replacements, for example `{"https://plex.tv": "http://localhost:9400", "https://app.plex.tv": "http://localhost:9400/plex", "https://openrouter.ai": "http://localhost:9400"}`. Approve a Plex PIN without a browser with `curl "http://localhost:9400/plex/approve?code=<CODE>"`. This variable is for development only; leave it unset on a real board.

Never commit the copy that points at the mock. Finish with one sign-in against the real provider before you publish.

## Documenting It for Your Users

Your `docs/SETUP.md` should cover, in this order:

1. **What the plugin can see.** List the scopes in plain words and say what it cannot do ("It can't play, pause, or change anything").
2. **Creating the app**, if users register their own: where to go, which fields matter, and that the redirect URI is copied from the plugin's settings. Mention any plan or account requirement the provider has.
3. **Signing in**: open the settings, press **Sign in with *Provider***, approve, and confirm the board's address the first time. Link to [Connecting Accounts](/docs/features/connecting-accounts) for the details.
4. **Limits**, such as a cap on accounts, stated before the user hits them.
5. **Troubleshooting** keyed by the exact error text your plugin shows.

## Provider Notes

Check the provider's current documentation; these are starting points, not guarantees.

| Provider | Flow | Notes |
|----------|------|-------|
| Spotify | `relay` | PKCE without a secret. No device flow. Development Mode apps admit five listed accounts, and the redirect URI must match exactly. |
| Google | `relay` | Web-application clients need a client secret, so use `client_secret_setting`. Send `{"access_type": "offline", "prompt": "consent"}` in `authorization_params` to receive a refresh token. The device flow allows only a short list of scopes. |
| GitHub | `device` or `relay` | The device flow must be enabled in the app's settings. GitHub reports OAuth errors with HTTP 200 and separates scopes with commas; the platform handles both. |
| Strava | `relay` | `"scope_separator": ","`. |
| TikTok | `relay` | `"client_id_param": "client_key"` and `"scope_separator": ","`. |
| Todoist | `relay` | `"scope_separator": ","`. |
| Twitch | `device` | `"device_scope_param": "scopes"` and `"device_poll_scope": true`. The platform reads Twitch's `message` errors and array scopes. |
| X | `relay` | Confidential (Web App) clients: `"token_auth_method": "basic"`. Native App clients have no secret and need nothing extra. |
| WHOOP | `relay` | `"refresh_params": {"scope": "offline"}`. |
| Instagram, Threads, Facebook | `relay` | Trade the 1-hour token for a long-lived one in `exchange_oauth_token` and renew it in `refresh_oauth_token`. See [Swapping and renewing the token yourself](#token-hooks). |
| Home Assistant | `relay` | Runs on the user's network: `endpoint_base_setting` with path endpoints. |
| Plex | `plex_pin` | Not OAuth. Send the token as `X-Plex-Token`. |
| OpenRouter | `key_exchange` | Yields an API key with no client ID and no expiry. |

## What the Platform Guarantees

- **PKCE on every relay sign-in.** The code verifier is created on the board and never leaves it, so an authorization code is useless to anything that sees it in transit.
- **A signed, single-use, ten-minute `state`.** A callback that this board did not start, that has expired, or that was already used is refused.
- **Tokens stay on the board.** They are stored in `data/oauth_tokens.json`, readable only by the FiestaBoard process, never included in an API response, and never written to backups.
- **One connection per plugin instance.** Tokens are not shared between plugins.
- **Cleanup.** Uninstalling a plugin, deleting an instance, or pressing **Disconnect** deletes the tokens. Disconnecting and signing in also clear the plugin's cached results, so the board stops showing an account's data as soon as the user disconnects it.
- **Refresh.** Access tokens are refreshed a minute before they expire. If the provider refuses, the connection becomes **Reconnect needed** and is not retried on every fetch.

## Checklist

- [ ] `fiestaboard_version` is `>=9.5.0`, or `>=9.11.0` if the plugin uses a 9.11.0 flow, field, or `report_oauth_rejected()`
- [ ] The `oauth` block passes `validate_provider_block` in a test (pass `settings_schema` too when you use `endpoint_base_setting`)
- [ ] No client secret anywhere in the repository
- [ ] Scopes are the least the plugin needs
- [ ] `fetch_data` calls `get_oauth_token()` every time and stores nothing
- [ ] `None` returns an unavailable result that says to sign in, and makes no request
- [ ] `401`, `403`, `429`, `5xx`, and timeouts are handled with a cooldown
- [ ] One request serves every board shape, if the API is rate limited
- [ ] Tests use invented data and fake tokens
- [ ] CI is pinned to a FiestaBoard release with OAuth
- [ ] `docs/SETUP.md` covers permissions, app creation (if any), sign-in, limits, and troubleshooting
- [ ] One sign-in has been tested against the real provider

## Worked Example: Spotify

The [Spotify plugin](https://github.com/Fiestaboard/fiestaboard-plugin--spotify) is the reference implementation. It is worth reading in full:

- `manifest.json`: the `relay` flow, three read-only scopes, and a `client_id` setting, because Spotify limits a shared app to five accounts and so each user brings their own.
- `__init__.py`: one shared snapshot for every board shape, cooldowns for `401`, `403`, `429`, and outages, and stale data shown briefly during an outage.
- `tests/`: `get_oauth_token` replaced on the instance, a fake Spotify API, and the platform's validator run against the manifest.
- `docs/SETUP.md`: a setup guide that walks through creating the Spotify app, field by field.

## Next Steps

- [Plugin Development Guide](/docs/development/plugin-guide) - Everything else about building a plugin
- [Connecting Accounts](/docs/features/connecting-accounts) - The sign-in from the user's side
- [Testing Guide](/docs/development/testing) - Running and writing tests
