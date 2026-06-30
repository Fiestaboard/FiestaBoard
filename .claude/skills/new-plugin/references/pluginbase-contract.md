# PluginBase contract

The interface your plugin implements. Source of truth: `src/plugins/base.py` in the
FiestaBoard core repo. Read that file when you need a detail this summary omits.

A plugin is a subclass of `PluginBase` (imported as `from src.plugins.base import
PluginBase, PluginResult`). It is constructed with the **manifest dict** (the parsed
`manifest.json`), and the module exports `Plugin = <YourClass>` at the bottom so the
loader can find it.

## Must implement

| Member | Signature | Notes |
| --- | --- | --- |
| `plugin_id` | `@property def plugin_id(self) -> str` | Abstract. Return the hardcoded id literal — must equal manifest `id` and the directory name. The loader asserts this. |
| `fetch_data` | `def fetch_data(self) -> PluginResult` | Abstract. The one required method. Fetch/compute, return a `PluginResult`. **Must catch its own exceptions** and return `PluginResult(available=False, error=str(e))` — never let it raise. |

## May override (sensible defaults exist)

| Member | Signature | Default | When to override |
| --- | --- | --- | --- |
| `validate_config` | `(self, config: dict) -> list[str]` | `[]` | Return human-readable error strings for bad config (empty = valid). Call `self._validate_refresh_seconds(config)` if you expose a `refresh_seconds` setting. |
| `get_formatted_display` | `(self) -> list[str] | None` | `None` | Return the fallback rendering: **exactly 6 strings, each ≤22 chars**. Used when a user has no custom template. |
| `cleanup` | `(self) -> None` | no-op | Release resources when the plugin is disabled. |
| `check_triggers` | `(self) -> list[TriggerResult]` | `[]` | Only when manifest has `"supports_triggers": true`. See `plugin-types.md`. |
| `receive_payload` | `(self, payload, headers, raw_body=b"") -> None` | raises `NotImplementedError` | Webhook plugins. Raise `PermissionError`→403, `ValueError`→400. |
| `on_config_change` | `(self, old, new) -> None` | logs | React to config changes. |

## Helpers the base class gives you (don't reimplement)

- `self.config` — current config dict; read settings with `self.config.get("key")`.
- `self.get_data()` — **cached** wrapper around `fetch_data()`. The platform calls *this*,
  not `fetch_data` directly. Don't override it; control caching via the manifest
  (`live_data: true` to bypass cache every tick, or a `refresh_seconds` setting).
- `self.clear_cache()`, `self.refresh_seconds`, `self.min_refresh_seconds`, `self.live_data`.
- `self._validate_refresh_seconds(config)` — returns error strings if `refresh_seconds` is
  out of the schema's `minimum`/`maximum`. Call it from `validate_config`.
- `self.resolve_config_variables(...)` / `self.get_url(...)` — interpolate `{{date_time.*}}`
  and other variables inside string settings (useful for templated API URLs).

Module constants in `base.py`: `DEFAULT_REFRESH_SECONDS = 300`, `MIN_REFRESH_SECONDS = 10`,
`MAX_REFRESH_SECONDS = 86400`.

## The board-output format: `PluginResult`

```python
@dataclass
class PluginResult:
    available: bool                       # required — is the plugin configured & working?
    data: dict[str, Any] | None = None    # the template variables, keyed by name
    error: str | None = None              # message when available is False
    formatted_lines: list[str] | None = None   # optional 6-line fallback render
```

- **`data` is the primary output.** Each key `k` becomes the template token `{{<plugin_id>.k}}`
  that users reference in board templates. Values are normally strings. The board itself is
  driven by user **templates** referencing these variables — your job is to expose clean,
  well-named variables, not to render the board.
- **Declare every `data` key in the manifest `variables.simple`**, and return every declared
  variable in `data`. The tests check both directions. This keeps the UI's variable picker
  accurate.
- **`formatted_lines`** is the optional no-template fallback: a `list` of exactly 6 strings,
  each ≤22 chars (6 rows × 22 cols = flagship board). Pad short lists with `""`; truncate
  long lines. It is a list, never a single string.
- Board character codes can be embedded in string values as `{NN}` tokens (e.g. `"{66}"`
  renders a colored tile) — used by art-style plugins. See `plugin-types.md`.
- **The board's character set is limited** — uppercase letters, digits, space, and a little
  punctuation. No unicode, no emoji, **no backslash**. Any text you put in `data` values or
  `formatted_lines` must be board-safe; the authoritative map is `src/board_chars.py` /
  `src/text_to_board.py`. For jokes/quotes/facts/emoticon plugins, add a test that asserts
  every output string is board-safe — that's the failure mode reviewers catch.

For event-driven plugins, `check_triggers()` returns `list[TriggerResult]`:

```python
@dataclass
class TriggerResult:
    triggered: bool
    trigger_id: str = ""          # stable per logical event (dedup key)
    message: str | None = None    # fallback text when no trigger_page_id is set
    formatted_lines: list[str] | None = None
    priority: int = 0             # higher wins when several fire
    duration_seconds: int = 30    # auto-expire
    data: dict | None = None      # → {{<id>.*}} on the triggered page
```

## Worked minimal example (http)

```python
from typing import List, Optional
import logging
import requests
from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)
API_URL = "https://api.example.com/v1/thing"
USER_AGENT = "FiestaBoard Tide Times Plugin (https://github.com/Fiestaboard/fiestaboard-plugin--tide-times)"


class TideTimesPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "tide_times"

    def fetch_data(self) -> PluginResult:
        try:
            station = self.config.get("station") or "9414290"
            r = requests.get(API_URL, params={"station": station},
                             headers={"User-Agent": USER_AGENT}, timeout=10)
            r.raise_for_status()
            payload = r.json()
            return PluginResult(available=True, data={
                "next_high": payload["highs"][0]["time"],
                "next_low": payload["lows"][0]["time"],
            })
        except Exception as e:
            logger.exception("Error fetching tide times")
            return PluginResult(available=False, error=str(e))


Plugin = TideTimesPlugin
```

Mirror this in the tests by patching `requests.get` (see `../fiestaboard-plugin--dad-jokes/
tests/test_plugin.py` for the canonical mocking pattern).
