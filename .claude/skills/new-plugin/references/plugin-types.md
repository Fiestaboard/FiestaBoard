# Plugin types

The scaffold generates two base shapes (`--type http` and `--type simple`). The three
richer shapes below start from one of those and are hand-extended. For each, the canonical
real example is a sibling repo — read it when you build that shape.

## simple — local computation, no network

`fetch_data` computes values in-process; no HTTP. Tests assert directly (no mocking).
Examples: `../fiestaboard-plugin--stardate`, the bundled `plugins/date_time`,
`plugins/random`. Use when the board content is derived from the clock, config, or a small
local dataset shipped with the plugin.

## http — fetch from an API

`fetch_data` calls `requests.get(...)` with a `User-Agent` and `timeout`, parses the
response, maps it to declared variables. Tests `@patch` `requests.get` with a realistic
payload. Best **root-layout** example (matches the scaffold): `../fiestaboard-plugin--dad-jokes`
(no key). For the API-key pattern: `../fiestaboard-plugin--weather`. Note
`../fiestaboard-plugin--currency` is config-driven and a good read for fetch logic, but it
uses the alternative **nested** layout (`plugins/<id>/` + root shim) — don't copy its
structure into a root-layout scaffold.

Patterns that matter:
- Module-level `API_URL` and `USER_AGENT` constants.
- `requests.get(url, params=..., headers={"User-Agent": USER_AGENT}, timeout=10)` then
  `response.raise_for_status()`.
- Declare any extra runtime dep (beyond `requests`) and add the matching `pip install` line
  to `.github/workflows/ci.yml` (the scaffold leaves a marked spot).
- For a secret key: a `password`-widget setting + `env_vars` entry; read as
  `self.config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")`. Never commit a real key.

## art — color-tile grids

Renders a 6×22 grid of colored tiles rather than text variables. The board has named color
tiles addressed by character code; art plugins build a grid string with `{NN}` / `{color}`
markers. Example: `../fiestaboard-plugin--sun-art`, `../fiestaboard-plugin--visual-clock`,
the bundled `plugins/random`.

Extra notes:
- Art plugins often import more of the core: `from src.board_chars import BoardChars` (tile
  codes) and `from src.config import Config` (timezone). Read sun-art's `__init__.py`.
- They tend to expose a single `formatted`/grid variable plus `formatted_lines`.
- If they depend on a heavy native lib (sun-art uses `astral`), **mock it in tests** so CI
  doesn't need it installed — sun-art does this in `tests/conftest.py` *and* a
  `tests/pytest_configure.py` that pre-mocks the module before import.

## trigger — push a page on an event

Beyond the periodic display, the plugin can *push* a specific page to the board when
something happens (threshold crossed, alert, doorbell). Example:
`../fiestaboard-plugin--calendar-sub`.

To add triggers:
1. Set `"supports_triggers": true` in the manifest (this also injects a `trigger_page_id`
   page-picker into `settings_schema`).
2. Implement `check_triggers(self) -> list[TriggerResult]` (import `TriggerResult` from
   `src.plugins.base`). Return entries with `triggered=True` to fire; use a stable
   `trigger_id` per logical event so the same event doesn't re-fire.
3. `priority` breaks ties; `duration_seconds` auto-expires the pushed page; `data` populates
   `{{<id>.*}}` on the triggered page.

The `_template/__init__.py` in the FiestaBoard repo has a fully commented `check_triggers`
stub to copy.

## webhook — receive inbound payloads

The plugin exposes an endpoint that external services POST to. Example:
`../fiestaboard-plugin--webhook`. Override `receive_payload(self, payload, headers,
raw_body=b"")`; raise `PermissionError` (→403) or `ValueError` (→400) to reject. Call
`self.fire_trigger(...)` to push to the board on receipt (requires `supports_triggers`).

---

When the user's idea is art/trigger/webhook: scaffold the closest base (`http` or
`simple`), get it green, then graft the extension while re-running the container tests after
each change. Don't try to scaffold the richer shape from scratch — evolve the green skeleton.
