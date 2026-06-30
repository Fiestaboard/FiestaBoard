# Designing a plugin that's actually good

Three things separate a plugin people love from one that merely passes tests: the **auth**
path has to be *possible* on a domain-less appliance, the **variables** have to be things
people actually want on a board, and the **config** has to be completable by a
non-developer. The scaffold gives you a correct skeleton — this is how you make it good.
Read this before you implement `fetch_data`, the manifest variables, and the settings.

## Authentication on a network appliance — read this BEFORE choosing an integration

FiestaBoard usually runs as a **LAN appliance with no public domain and no inbound internet**
— a Docker container on someone's home or office network at something like
`http://192.168.1.50:4420`. That breaks the assumption most "Log in with X" flows make.

- **Redirect / authorization-code OAuth is a poor fit.** It needs a registered, reachable
  `redirect_uri` (often https + a verified domain), and the consent round-trip has to land
  back on the appliance. A domain-less box on a LAN usually can't satisfy that, and it's
  fragile across providers and remote access. **Don't design around it.**
- **Prefer these, in order:**
  1. **API key / personal access token the user pastes in.** Simplest and most robust. A
     `settings_schema` string with `"ui:widget": "password"` + a matching `env_vars` entry,
     read as `self.config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")`. In the SETUP
     guide, document *exactly* where the user generates the key.
  2. **OAuth 2.0 Device Authorization Grant ("device flow").** The OAuth profile designed for
     input-/domain-constrained devices — supported by Google, GitHub, Spotify, Twitch, and
     others. The user gets a short code, authorizes on a phone/laptop, and the plugin polls
     for the token — **no redirect URI needed.** Store the refresh token in config and
     refresh as needed.
  3. **Long-lived / self-issued tokens** — e.g. a Home Assistant long-lived access token, or
     a service's "personal token". User generates it once and pastes it in.
- **If a service only supports redirect OAuth**, treat it as a red flag. Find a token or
  device-flow path, or tell the user up front it isn't a clean fit — don't ship an auth flow
  that can't complete on their board.
- **Inbound webhooks** (the `webhook` plugin type) assume something on the internet can reach
  the appliance — often it can't without a tunnel. If you use them, say so in the setup docs.

In the Step 1 interview, ask what the source requires and steer toward one of the three
patterns above. If the only path is redirect OAuth, raise it before scaffolding.

## Variables people actually want on a board

The board is **6 rows × 22 columns** of physical tiles. Design variables for *that*, not as
a dump of the API response.

- **Expose display-ready values, sized to the board.** Raw `temperature: 22.4` is less useful
  than `temp_display: "72°F"`. Often expose **both** — a raw value for users who want to
  compose their own layout, and a pre-formatted one for drop-in use. Round sensibly, include
  units, and set realistic `max_length`s (most strings want to fit in ≤22 chars).
- **Curate.** Not every API field deserves to be a variable. Surface the one or two numbers
  and the status word a person reads at a glance; drop the rest.
- **Handle empty / unavailable / loading states.** Decide what shows when the source is down
  or unconfigured: return `PluginResult(available=False, error=...)` with a clear message, and
  make sure any `formatted_lines` degrade gracefully rather than render "None".
- **Use color tiles (`{NN}`) where status is glanceable** — green/amber/red for an index,
  say. See art-type plugins and `src/board_chars.py`.
- **Name and group for the variable picker.** Every `simple` var needs a `description` and a
  `group`; write them so the in-app picker reads like a menu, with realistic `example`s.
- **Make the flagship `demo` template genuinely nice.** It's the first thing a user sees —
  compose a board that looks good, not just a list of fields.

## Configuration a non-developer can complete

The person configuring this is often not the author. The settings form *is* the UX.

- **Minimize required fields.** Anything that can have a sensible default should. `required`
  is only what truly can't be guessed — usually just the key or the location.
- **Every setting needs a clear `title` and `description`.** The description is the only help
  the user gets: say what it does and what a good value looks like.
- **Right widget for the job:** `password` for secrets, `timezone`, `page-picker` (triggers),
  numeric `minimum`/`maximum` for bounds.
- **Validate with actionable messages.** `validate_config` should return
  `"Station ID must be a 7-digit NOAA code"`, not `"invalid"`.
- **Expose what a board owner cares about; hide internal knobs.** Location, units, refresh
  interval — yes. Cache TTLs, retry counts — no.

Your README/SETUP are only as good as the design above: the variables table and the
configuration table are just the documented surface of these decisions.
