# FiestaBoard Plugin Development Guide

This guide explains how to create plugins for FiestaBoard. Whether you're building a quick display for personal data or an advanced multi-variable integration, this guide has you covered.

## Your First Plugin in 5 Minutes

The fastest way to get started: return a dictionary from `fetch_data()` and every key automatically appears in the editor. No variable declarations needed.

### 1. Copy the template

```bash
cp -r plugins/_template plugins/my_plugin
```

### 2. Write a minimal manifest

Only three fields are required:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0"
}
```

That's it. No `variables` section, no `max_lengths`. FiestaBoard auto-discovers everything.

### 3. Implement `fetch_data()`

```python
from src.plugins.base import PluginBase, PluginResult

class MyPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "my_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(
            available=True,
            data={
                "score": 42,
                "status": "All systems go",
                "label": "My Widget",
            }
        )
```

### 4. Use it in a template

Every key in your `data` dictionary becomes a variable:

```jinja
{{my_plugin.score}}
{{my_plugin.status}}
{{my_plugin.label}}
```

They also appear in the editor's variable picker automatically.

### 5. Run the dev container

```bash
docker-compose -f docker-compose.dev.yml up
```

Your plugin shows up in Integrations and your variables appear in the editor.

---

## How Auto-Discovery Works

When your manifest has **no** `variables` section (or it's empty), FiestaBoard automatically:

1. Calls your `fetch_data()` method during startup
2. Inspects the top-level keys in `PluginResult.data`
3. Exposes every scalar value (strings, numbers, booleans) as a template variable
4. Leaves `max_length` unset, so the template engine truncates to the board width at render time

This means beginners can skip the entire `variables` and `max_lengths` configuration and just focus on returning data. Lists and dicts in `data` are skipped by auto-discovery — declare them under `variables.arrays` if you need them as template variables.

### When auto-discovery is active

| Manifest state | Auto-discover? |
|---|---|
| No `variables` section at all | **Yes** |
| Empty `variables: {}` | **Yes** |
| `variables` with `simple` or `arrays` declared | **No** (but undeclared data keys still appear in an "Other" group) |
| Explicit `"auto_discover": true` | **Yes** (even with declared variables) |
| Explicit `"auto_discover": false` | **No** (strict mode -- only declared variables) |

---

## Adding Variable Metadata

As your plugin matures, you'll want to add descriptions, types, and examples to make the editor experience richer. The `variables.simple` field accepts two formats:

### List format (basic)

```json
"variables": {
    "simple": ["temperature", "humidity", "status"]
}
```

This is backward-compatible with the original format. Variables show up in the editor with their raw field names.

### Dict format (rich metadata)

```json
"variables": {
    "simple": {
        "temperature": {
            "description": "Current temperature in configured units",
            "type": "number",
            "max_length": 3,
            "group": "current",
            "example": "72"
        },
        "humidity": {
            "description": "Relative humidity percentage",
            "type": "number",
            "max_length": 3,
            "group": "current",
            "example": "65"
        }
    }
}
```

With this format, the editor shows:
- **Descriptions** as tooltips when hovering over variable pills
- **Live preview values** next to each variable
- **Type hints** for validation

### Metadata fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Tooltip text shown in the editor |
| `type` | string | `"string"`, `"number"`, or `"boolean"` |
| `max_length` | integer | Max characters this variable can produce |
| `group` | string | Group ID to organise this variable under |
| `example` | string | Example value shown in documentation |

All fields are optional. You can mix and match -- add just `description` if that's all you need.

The `max_length` field in metadata replaces the need for a separate top-level `max_lengths` section. If both are present, the top-level `max_lengths` takes precedence.

---

## Config variable interpolation (dynamic URLs and strings)

Related: [GitHub issue #537](https://github.com/Fiestaboard/FiestaBoard/issues/537) (Generic Data and other plugins that call HTTP APIs with non-static URLs).

Board templates use `{{plugin_id.field}}` syntax, but **plugin settings** are plain JSON until your code resolves them. FiestaBoard provides **`{{variable}}` placeholders inside string settings** so URLs and headers can include the current date, time, and other built-ins.

### Built-in placeholders

Use double braces in any string field in your plugin config (same style as templates, but resolved in Python when you ask for it):

| Placeholder | Meaning |
|-------------|---------|
| `{{date}}` | Current date `YYYY-MM-DD` (board timezone when available) |
| `{{year}}`, `{{month}}`, `{{day}}`, `{{hour}}`, `{{minute}}` | Calendar / clock parts |
| `{{timestamp}}` | Unix epoch seconds |
| `{{date:%Y%m%d}}`, `{{date:%m/%d/%Y}}`, … | `strftime` after `date:` (see `src/plugins/config_interpolation.py`) |

Unknown placeholders are **left unchanged** so you can detect typos or missing context.

### API on `PluginBase`

- **`resolve_config_variables(extra_variables=None, timezone=None)`** — deep copy of `self.config` with every string interpolated.
- **`get_resolved_config_value(key, default=None, ...)`** — one key from that resolved dict.
- **`get_url(key="url", default="", ...)`** — convenience for a single URL-like string (e.g. Generic Data’s `url` field).

Optional **`extra_variables`** is a `dict` of name → string for values you compute in code (e.g. `{"weather.location": "sf"}` for a placeholder `{{weather.location}}`). There is **no** automatic wiring from other plugins’ live data into these placeholders unless your plugin supplies that map.

### What you must do in the plugin

Before `requests.get` / `httpx` / etc., resolve strings:

```python
def fetch_data(self) -> PluginResult:
    url = self.get_url()  # or self.get_url("api_url") if your schema uses another key
    # ...
```

If you read nested structures, call `resolved = self.resolve_config_variables()` and walk the dict/list you need.

The **`POST /generic-data/test-fetch`** endpoint applies the same built-in interpolation to the URL, header values, and string POST body so the Integrations UI preview matches date-aware URLs.

---

## Organizing with Groups

When a plugin has many variables, groups help users find what they need:

```json
"variables": {
    "groups": {
        "current": { "label": "Current Conditions" },
        "forecast": { "label": "Forecast" }
    },
    "simple": {
        "temperature": {
            "description": "Current temperature",
            "group": "current"
        },
        "high_temp": {
            "description": "Today's high",
            "group": "forecast"
        }
    }
}
```

In the editor, variables render under their group headings:

```text
▼ Weather
  Current Conditions
    [temperature] [humidity] [condition]
  Forecast
    [high_temp] [low_temp] [chance_rain]
```

Variables without a group (or with an unrecognized group ID) appear under "General".

---

## Array Variables

For plugins that expose lists of items (transit stops, stock tickers, locations), use the `arrays` schema:

```json
"variables": {
    "simple": {
        "last_updated": { "description": "Last data refresh time" }
    },
    "arrays": {
        "locations": {
            "label_field": "name",
            "item_fields": ["name", "temperature", "humidity", "condition"]
        }
    }
}
```

In templates, arrays are accessed by index:

```jinja
{{my_plugin.locations.0.name}}: {{my_plugin.locations.0.temperature}}°F
{{my_plugin.locations.1.name}}: {{my_plugin.locations.1.temperature}}°F
```

The editor shows an expandable list of items with their label field as the heading.

### Sub-arrays (nested)

For deeply nested data (e.g., transit stops with multiple lines):

```json
"arrays": {
    "stops": {
        "label_field": "stop_name",
        "item_fields": ["stop_name", "stop_code"],
        "sub_arrays": {
            "lines": {
                "key_type": "dynamic",
                "key_field": "line",
                "item_fields": ["line", "next_arrival", "is_delayed"]
            }
        }
    }
}
```

Template usage:

```jinja
{{my_plugin.stops.0.lines.N.next_arrival}}
{{my_plugin.stops.0.lines.KT.is_delayed}}
```

---

## Auto-Discovery Deep Dive

### How it works under the hood

1. When `auto_discover` is active, the plugin registry calls `fetch_data()` once during startup
2. It inspects `PluginResult.data` for top-level keys
3. Scalar values (string, int, float, bool) become simple variables
4. Lists and dicts are skipped (those should be declared as arrays in the manifest)
5. Results are cached per plugin lifecycle

### Mixing declared and undeclared variables

When your manifest declares some variables but your `fetch_data()` returns extra keys, those extras appear in the editor under an "Other" group by default. This is by design -- it means you can declare metadata for your main variables while still allowing new keys to be discovered.

### Strict mode

If you want only your declared variables to appear (hiding any extra data keys):

```json
"variables": {
    "auto_discover": false,
    "simple": { ... }
}
```

### Best practice

- **Getting started**: Omit `variables` entirely. Let auto-discovery handle everything.
- **Polishing**: Add metadata to your most important variables. Keep auto-discovery on.
- **Publishing**: Consider declaring all variables with descriptions for the best editor experience.

---

## Plugin Structure

```text
plugins/my_plugin/
├── __init__.py           # Required: Plugin implementation
├── manifest.json         # Required: Plugin metadata + screenshots
├── README.md             # Required: Developer documentation
├── docs/                 # Required: User documentation + images
│   ├── SETUP.md          # Setup guide (API keys, configuration)
│   ├── board-display.png # Required: Primary screenshot (hero image)
│   ├── configuration.png # Optional: Config dialog screenshot
│   └── integrations.png  # Optional: Integrations list screenshot
└── tests/                # Required: Plugin tests (>80% coverage)
    ├── __init__.py
    └── test_plugin.py
```

## Documentation Standards

Each plugin has three documentation layers:

| Layer | File | Audience | Purpose |
|-------|------|----------|---------|
| README | `README.md` | Developers, GitHub browsing | How the plugin works, variables, examples |
| Setup guide | `docs/SETUP.md` | End users | Step-by-step setup, screenshots, troubleshooting |
| Docs site | `docs-site/docs/plugins/<name>.md` | Public website | Published documentation at fiestaboard.app |

### README.md Format

Every plugin README must follow this section order:

```markdown
# {Plugin Name} Plugin

{One-sentence description.}

![{Plugin Name} Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and setup instructions

## Overview
{2-3 sentences on what the plugin does and why it is useful.}

## Template Variables
### {Group Name}
{Variable table or code block, grouped to match manifest groups}

## Example Templates
### {Template Name}
{Code block with template content}

## Configuration
{Table of settings from settings_schema}

## Features
{Bullet list of key capabilities}

## Author
{Author name}
```

The hero image is always `./docs/board-display.png`, matching the `primary: true` screenshot in the manifest.

### docs/SETUP.md Format

Every plugin setup guide must follow this section order:

```markdown
# {Plugin Name} Setup Guide

{One-sentence description.}

## Overview
**What it does:** {bullet list}
**Prerequisites:** {requirements, or "None - works out of the box!"}

## Quick Setup
### 1. Enable the Plugin
{Steps with optional screenshot: integrations.png}
### 2. Configure {Plugin Name}
{Steps with optional screenshot: configuration.png}
### 3. Create a Board Template
{Example template}
### 4. View on Your Board
{Reference to board-display.png}

## Template Variables
{Variable table}

## Configuration Reference
{Full settings table}

### Environment Variables
{Env var code block if applicable}

## Troubleshooting
{Common issues and solutions}
```

### Image Naming Convention

All plugin images live in `plugins/<id>/docs/` with standardized names:

| Filename | Purpose | Required? |
|----------|---------|-----------|
| `board-display.png` | Primary hero image showing the board output | Yes (for published plugins) |
| `configuration.png` | Plugin config dialog in the web UI | No |
| `integrations.png` | Plugin card on the Integrations page | No |

Additional screenshots use descriptive kebab-case names (e.g., `color-rules.png`, `symbol-picker.png`).

### Screenshots in the Manifest

The `screenshots` field in `manifest.json` makes images programmatically discoverable. Any tool, API, or build process can read the manifest to find a plugin's images without parsing markdown.

```json
{
  "screenshots": [
    {
      "src": "docs/board-display.png",
      "alt": "My Plugin displayed on a Vestaboard",
      "caption": "Default template showing the main output",
      "primary": true
    }
  ]
}
```

| Property | Required | Description |
|----------|----------|-------------|
| `src` | Yes | Relative path from the plugin directory |
| `alt` | Yes | Alt text for accessibility |
| `caption` | No | Human-readable description |
| `primary` | No | Exactly one screenshot should be `true` (used as hero image in galleries and the registry) |

The docs-site build process copies the primary screenshot from `plugins/<id>/docs/board-display.png` to `docs-site/static/img/plugins/<id>-board-display.png` for use in the `<BoardScreenshot>` component.

---

## Manifest Reference

### Required Fields

| Field | Description |
|-------|-------------|
| `id` | Unique identifier (must match directory name) |
| `name` | Human-readable name |
| `version` | Semantic version (e.g., "1.0.0") |

### Recommended Fields

| Field | Description |
|-------|-------------|
| `description` | Brief description of the plugin |
| `author` | Author name |
| `icon` | Lucide icon name (default: "puzzle") -- shown in the editor |
| `category` | Category for grouping: `art`, `data`, `entertainment`, `home`, `transit`, `utility`, `weather` |

### Optional Fields

| Field | Description |
|-------|-------------|
| `repository` | GitHub repository URL |
| `documentation` | Path to documentation file |
| `env_vars` | Environment variables the plugin uses |
| `settings_schema` | JSON Schema for configuration UI |
| `variables` | Variable declarations with optional metadata and groups |
| `max_lengths` | Max character lengths (alternative to per-variable `max_length`) |
| `color_rules_schema` | Schema for dynamic color rules |
| `min_refresh_seconds` | Hard floor for refresh interval |
| `screenshots` | Array of screenshot entries for galleries, docs, and the registry (see Documentation Standards) |

### Settings Schema

Use JSON Schema to define configuration fields:

```json
{
  "settings_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "title": "API Key",
        "description": "Get your key from example.com",
        "ui:widget": "password"
      },
      "refresh_seconds": {
        "type": "integer",
        "title": "Refresh Interval",
        "default": 300,
        "minimum": 60
      }
    },
    "required": ["api_key"]
  }
}
```

#### UI Widgets

- `password` - Masked input for secrets
- `textarea` - Multi-line text
- `select` - Dropdown (automatic for `enum` fields)
- `array-input` - Array of items
- `datetime` - Date/time picker
- `timezone` - Timezone selector

## Plugin Implementation

Your plugin must inherit from `PluginBase`:

### PluginBase Methods

| Method | Required | Description |
|--------|----------|-------------|
| `plugin_id` | Yes | Property returning the plugin ID; must match `manifest.json` `id` |
| `fetch_data()` | Yes | Return a `PluginResult` with the data dict for templates |
| `validate_config(config)` | No | Return a list of error strings; empty list means valid |
| `on_config_change(old, new)` | No | Hook called after settings are updated |
| `get_formatted_display()` | No | Return six display lines for "single" page rendering |
| `cleanup()` | No | Release resources when the plugin is disabled |
| `check_triggers()` | No | Return a list of `TriggerResult` if `supports_triggers` is set |
| `receive_payload(payload, headers, raw_body)` | No | Handle inbound webhooks (raise `PermissionError` → 403, `ValueError` → 400) |

### Properties and helpers

Access settings and metadata through these properties on `PluginBase`:

| Member | Kind | Description |
|--------|------|-------------|
| `self.config` | property | Current settings dict (call `.get("key", default)` on it) |
| `self.manifest` | property | Parsed `manifest.json` as a dict |
| `self.info` | property | `PluginInfo` dataclass with `id`, `name`, `version`, `author`, etc. |
| `self.enabled` | property | Whether the plugin is currently enabled |
| `self.refresh_seconds` | property | Effective refresh interval (clamped to `min_refresh_seconds`) |
| `self.resolve_config_variables(extra_variables=None, timezone=None)` | method | Resolved copy of config with `{{var}}` strings interpolated |
| `self.get_resolved_config_value(key, default=None, ...)` | method | One resolved value from the config |
| `self.get_url(key="url", default="", ...)` | method | Resolved string setting (for HTTP endpoint fields) |
| `self.get_settings_schema()` | method | The `settings_schema` block from the manifest |
| `self.get_env_vars()` | method | The `env_vars` array from the manifest |
| `self.clear_cache()` | method | Force a fresh `fetch_data()` on the next `get_data()` |

> **Heads up:** The base class does **not** expose a `self.get_config(...)` method — call `self.config.get(...)` instead. The bundled `plugins/_template/__init__.py` still calls `self.get_config()` and would raise `AttributeError` at runtime; treat it as pseudo-code until that template is fixed.

### PluginResult

Return this from `fetch_data()` (see `src/plugins/base.py`):

```python
@dataclass
class PluginResult:
    available: bool                              # True if data fetched successfully
    data: dict[str, Any] | None = None           # Template variables
    error: str | None = None                     # Error message
    formatted_lines: list[str] | None = None     # Pre-formatted display (6 lines)
```

## Triggering Pages from a Plugin

Most plugins are passive — they provide template variables that get rendered on a schedule. **Triggers** let a plugin push a page to the board the moment something happens: a doorbell ring, a weather alert, a flight landing, the dryer finishing. The trigger wins over the scheduled or manually-selected page until it expires (or the user changes the page).

A few real examples of when a trigger is the right tool:

- A doorbell plugin fires a `"Someone at the door"` page when its webhook receives a press.
- A weather plugin fires a severe-storm alert whenever a new NWS warning lands.
- A countdown plugin fires a `"T-minus 60 seconds"` page in the final minute before zero.

If your plugin just polls and displays steady-state data (weather, transit, stocks), you don't need triggers — return data from `fetch_data()` and let users put it on a page.

### 1. Declare trigger support in the manifest

Set `supports_triggers: true` at the top level of `manifest.json`. Without this flag the trigger service skips your plugin entirely, even if you override `check_triggers()`.

```json
{
  "id": "doorbell",
  "name": "Doorbell",
  "version": "1.0.0",
  "supports_triggers": true,
  "settings_schema": {
    "type": "object",
    "properties": {
      "trigger_page_id": {
        "type": "string",
        "title": "Page to show when the doorbell rings",
        "description": "Pick a template page. The trigger's data is exposed as {{doorbell.*}}.",
        "ui:widget": "page-picker"
      },
      "refresh_seconds": {
        "type": "integer",
        "default": 60,
        "minimum": 10
      }
    }
  }
}
```

The `trigger_page_id` field is a convention recognised by the display loop (see step 3). Using `"ui:widget": "page-picker"` makes the FiestaBoard settings UI render a page-chooser dropdown for that field instead of a raw text input.

### 2. Implement `check_triggers()` on your plugin

`PluginBase` defines `check_triggers()` with a no-op default. Override it to evaluate your conditions and return a list of `TriggerResult` objects. Only entries with `triggered=True` activate; `triggered=False` entries are ignored (returning a non-firing result is fine — handy for state-machine clarity).

```python
from src.plugins.base import PluginBase, PluginResult, TriggerResult


class DoorbellPlugin(PluginBase):
    @property
    def plugin_id(self) -> str:
        return "doorbell"

    def fetch_data(self) -> PluginResult:
        # Passive data — used when no trigger is active.
        return PluginResult(available=True, data={"last_ring": self._last_ring_iso()})

    def check_triggers(self) -> list[TriggerResult]:
        ring = self._pending_ring()  # your own state, e.g. from receive_payload()
        if ring is None:
            return []

        return [
            TriggerResult(
                triggered=True,
                trigger_id=f"doorbell_ring_{ring.id}",   # stable per event — see dedup notes
                priority=80,                              # higher beats lower; default 0
                duration_seconds=45,                      # auto-expires after this
                data={
                    "visitor": ring.visitor_label,        # available as {{doorbell.visitor}}
                    "timestamp": ring.timestamp_iso,
                },
                message="Someone at the door",            # fallback if no trigger_page_id
            )
        ]
```

The `TriggerResult` fields are defined in `src/plugins/base.py`:

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `triggered` | bool | (required) | Whether the trigger fires. `False` entries are ignored. |
| `trigger_id` | str | `""` | Stable identifier. Same id replaces the prior trigger (dedup). |
| `priority` | int | `0` | Higher wins when multiple triggers are active simultaneously. |
| `duration_seconds` | int | `30` | How long the trigger stays active before auto-expiring. |
| `data` | dict \| None | `None` | Template context exposed as `{{<plugin_id>.*}}` when rendering `trigger_page_id`. |
| `message` | str \| None | `None` | Plain-text fallback sent to the board if no `trigger_page_id` is configured. |
| `formatted_lines` | list[str] \| None | `None` | Pre-formatted 6-line board content; takes precedence over `message`. |

### 3. Lifecycle: when triggers fire and what they replace

The display loop ticks at the configured polling interval (see `src/main.py:683`). Each tick, **before** evaluating the scheduled or manual page, it calls `check_triggers()` on every enabled plugin where `supports_triggers` is `true`. The order of operations:

1. **Silence mode wins.** If the board is in silence mode, triggers are *not* evaluated — no plugin code runs at all. The silence indicator stays on the board.
2. **Each trigger-capable plugin is asked.** `check_triggers()` is called; any returned `triggered=True` results are recorded in the `TriggerService`.
3. **Highest-priority non-expired trigger is selected.** Ties are broken by insertion order. Expired triggers (older than their `duration_seconds`) are dropped first.
4. **The page is chosen.** In priority order:
   - If the plugin's config has `trigger_page_id` set and that page exists and is a `template` page, it is rendered with `{plugin_id: trigger.data}` as template context — so a doorbell trigger with `data={"visitor": "UPS"}` makes `{{doorbell.visitor}}` resolve to `"UPS"` in that page.
   - Else, if the `TriggerResult` has `formatted_lines`, those are sent as-is.
   - Else, if it has `message`, that text is sent.
   - Else, fall through to the normal scheduled/manual page.
5. **The previously-displayed page is replaced.** When the trigger expires (or is dismissed), the next tick falls through to the scheduled/manual page automatically — no special handling needed.

#### Dedup

Re-emitting a `TriggerResult` with the same `trigger_id` *replaces* the existing active trigger (same id, refreshed `activated_at` and `duration_seconds`). This means it's safe — and expected — to keep returning the same trigger every tick while the underlying condition holds. The board doesn't flicker because the `TriggerService` only sends content to the board when the rendered content actually changes (`src/main.py:630-633`).

Pick `trigger_id` values that are **stable per event** (e.g. `"doorbell_ring_<event_uuid>"`, `"storm_alert_<nws_id>"`). Using a fixed string like `"doorbell"` works too, but means a second ring within the duration window can't visibly re-fire — it just refreshes the existing trigger's clock.

#### User override

If the user manually changes the page (e.g. via the "Change Page" button on the home screen), every active trigger is dismissed *and* suppressed for the remainder of its natural duration (`src/triggers/service.py:186-203`). A plugin can keep returning the same `TriggerResult` every tick — it won't re-activate until the suppression window lapses. This is what makes manual page changes "stick" against a chatty plugin.

#### Rate limiting

The trigger service does not rate-limit firing — that's your plugin's job. The simplest pattern is to track the last-fired timestamp per condition and return `[]` until enough time has passed.

### 4. Inspecting and controlling triggers via the API

The platform exposes triggers over HTTP for the UI and external systems:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/triggers` | List all active triggers (sorted by priority desc). |
| `GET` | `/triggers/active` | Return the single highest-priority active trigger, or `null`. |
| `POST` | `/triggers/{trigger_id}/dismiss` | Remove a specific trigger. |
| `POST` | `/triggers/clear` | Remove all active triggers. |
| `POST` | `/triggers/check` | Force an immediate evaluation of every trigger-capable plugin. |

`POST /triggers/check` is useful in tests and when wiring up webhook-driven plugins — call it from `receive_payload()` after queueing a new event so the trigger fires without waiting for the next polling tick.

### 5. Common patterns

**Event-on-state-change.** Compare the latest fetched state against the previous one and fire when something crosses a boundary. Don't fire on every tick the condition is true — track the transition.

```python
def check_triggers(self) -> list[TriggerResult]:
    current = self._read_sensor()
    if current == self._last_state:
        return []
    self._last_state = current
    if current != "alert":
        return []
    return [TriggerResult(
        triggered=True,
        trigger_id=f"sensor_alert_{current.event_id}",
        priority=50,
        duration_seconds=120,
        data={"reading": current.value},
    )]
```

**Threshold alert.** Fire when a numeric value crosses a configured threshold and stay active until it recovers.

**Webhook-driven.** Override `receive_payload()` (see `src/plugins/base.py:458`) to enqueue an event when an external system pushes to your plugin's webhook endpoint. Then `check_triggers()` consumes the queue. Hit `POST /triggers/check` from `receive_payload()` to fire immediately rather than waiting for the next tick.

**Scheduled interrupt.** A countdown plugin can fire a high-priority trigger in the final minute before an event so the board interrupts whatever else is showing.

### Gotchas

- ❌ **Don't fire on every tick without a stable `trigger_id`.** Without an id the trigger replaces itself anyway, but using event-derived ids makes dedup, dismiss, and API inspection sane.
- ❌ **Don't return `triggered=True` for steady-state data.** Triggers preempt the user's scheduled page. Reserve them for genuine events.
- ❌ **Don't raise from `check_triggers()` and assume the loop handles it gracefully.** It does (`src/triggers/service.py:240-244`), but the error is silently logged — your trigger just stops firing. Catch and log inside the method if you need visibility.
- ❌ **Don't store secrets or PII in `TriggerResult.data`.** It's exposed via `GET /triggers` and the page template engine.
- ❌ **Don't expect triggers to fire during silence mode.** They're explicitly suppressed.
- ⚠️ **`priority` is plugin-author choice.** There's no global scale, so coordinate with other trigger-capable plugins if you ship a registry plugin. As a rough convention so far: ambient/informational ~10, notable ~50, urgent/safety ~80+.

## Testing Your Plugin

**All plugins must include tests with a minimum of 80% code coverage.** CI will fail if coverage is below this threshold.

### Test Directory Structure

```text
plugins/my_plugin/tests/
├── __init__.py       # Required (can be empty)
├── conftest.py       # Test fixtures
└── test_plugin.py    # Test cases (must start with test_)
```

### What to Test

1. **Plugin ID** matches directory name
2. **Successful data fetch** returns expected variables
3. **Missing/invalid config** returns appropriate errors
4. **Network errors** are handled gracefully
5. **Config validation** catches invalid input
6. **Variable output** matches manifest declarations
7. **Manifest metadata** has descriptions and valid groups (if using rich format)

### Running Tests

```bash
# Single plugin
python scripts/run_plugin_tests.py --plugin=my_plugin

# All plugins
python scripts/run_plugin_tests.py

# With verbose output
python scripts/run_plugin_tests.py --verbose

# Without coverage enforcement (for development)
python scripts/run_plugin_tests.py --no-coverage
```

### Coverage Requirements

| Requirement | Value |
|-------------|-------|
| Minimum coverage | **80%** |
| Coverage scope | Per-plugin (not global) |
| CI enforcement | Yes - builds fail below threshold |

## Best Practices

### Error Handling

```python
def fetch_data(self) -> PluginResult:
    try:
        data = self._call_api()
        return PluginResult(available=True, data=data)
    except requests.RequestException as e:
        logger.warning(f"Network error: {e}")
        return PluginResult(available=False, error="Network unavailable")
    except Exception as e:
        logger.exception("Unexpected error")
        return PluginResult(available=False, error=str(e))
```

### Configuration

Prefer UI configuration over environment variables. Settings live on `self.config`:

```python
def fetch_data(self) -> PluginResult:
    api_key = self.config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")
```

For settings that contain `{{date}}` / `{{year}}` placeholders (e.g. dynamic URLs), use `self.get_resolved_config_value("api_url")` or the URL-specific shortcut `self.get_url("api_url")`.

### Logging

```python
logger.debug("Detailed info for debugging")
logger.info("Plugin initialized successfully")
logger.warning("Non-critical issue occurred")
logger.error("Failed to fetch data")
```

## Plugin Updates

External plugins installed from the registry or a git URL are updated automatically. A background task in `src/api_server.py` polls every hour, calls `registry.check_for_updates()`, and — when the user's **Auto-update plugins** setting is on — silently pulls the latest commit for any plugin that has changed.

The behaviour is controlled by **Settings → Plugin Updates**. Users can choose between automatic application and a manual flow that surfaces the available update on the Integrations page (per-plugin update button or the bulk "Apply all updates" action).

For plugin authors this means users on the default settings will receive fixes and new variables shortly after changes land on the plugin's default branch. Keep the default branch stable — breaking changes should be gated behind a version bump in `manifest.json`.

## Contributing Plugins

To contribute a plugin to the FiestaBoard repository:

1. Create a feature branch: `git checkout -b feat-plugin-name`
2. Copy the template: `cp -r plugins/_template plugins/my_plugin`
3. Implement your plugin following this guide
4. Add tests with >80% coverage
5. Add documentation in `README.md` and `docs/SETUP.md`
6. Add your plugin to the main `README.md` "Available Plugins" list
7. Submit a pull request

### PR Checklist

- [ ] Plugin ID matches directory name
- [ ] `manifest.json` has at least `id`, `name`, `version`
- [ ] `manifest.json` includes `screenshots` array with `primary: true` entry
- [ ] `__init__.py` implements `PluginBase` correctly
- [ ] Tests exist in `tests/` with >80% coverage
- [ ] `README.md` follows the canonical section order (see Documentation Standards)
- [ ] `docs/SETUP.md` follows the canonical section order (see Documentation Standards)
- [ ] `docs/board-display.png` exists (primary screenshot)
- [ ] No hardcoded secrets or personal information
- [ ] Plugin added to main README.md "Available Plugins" list
