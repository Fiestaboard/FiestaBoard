# manifest.json reference

The manifest is the plugin's contract with the platform: metadata, the config form, and
the template variables. Validated by `PluginManifest.from_dict` / `MANIFEST_SCHEMA` in
`src/plugins/manifest.py`. The scaffold emits a valid starting manifest; this is what each
field means when you customize it.

## Top-level fields

| Field | Required | Type / constraint | Notes |
| --- | --- | --- | --- |
| `id` | **yes** | `^[a-z][a-z0-9_]*$` | Must equal the directory name and `plugin_id`. |
| `name` | **yes** | string, 1–50 chars | Display name (Title Case). |
| `version` | **yes** | `^\d+\.\d+\.\d+$` | Semver. Bumping this on `main` triggers `release.yml`. |
| `description` | no | ≤200 chars | One sentence; also used as the registry description. |
| `author` | no | string | The one place real contact info is allowed. |
| `repository` | no | uri | `https://github.com/Fiestaboard/fiestaboard-plugin--<slug>`. |
| `documentation` | no | string | Default `"README.md"`. |
| `icon` | no | string | Lucide icon name. |
| `category` | no | enum | `art`, `data`, `transit`, `weather`, `entertainment`, `utility`, `home`. **Never invent one.** |
| `fiestaboard_version` | no | semver constraint | e.g. `">=4.2.0"`. Min platform version. |
| `min_refresh_seconds` | no | integer | Hard floor on how often the plugin may fetch. |
| `live_data` | no | boolean | `true` = bypass the cache every tick (clocks, animations). |
| `supports_triggers` | no | boolean | Enables `check_triggers`; injects a page-picker setting. |
| `settings_schema` | no | JSON Schema object | The config form. See below. |
| `env_vars` | no | array of `{name*, required?, description?, default?}` | Env-var equivalents of settings (e.g. API keys). |
| `variables` | no | object | Template variables. See below. |
| `max_lengths` | no | `{var: int}` | Truncation limits; merged with per-variable `max_length`. |
| `color_rules_schema` | no | object | Optional dynamic color rules. |
| `screenshots` | no | array of `{src*, alt*, caption?, primary?}` | Exactly one `primary: true` (the hero image). |
| `demo` | no | object | Bundled demo page(s). See below. |

## settings_schema

Standard JSON Schema (`type: object`, `properties`, `required`). Per-property conventions:

- `type`: `string` | `integer` | `boolean` | `array`
- `title`: the UI label; `description`: help text; `default`: default value
- `minimum` / `maximum`: numeric bounds (used by refresh validation)
- arrays: `items: {type: string}`, `minItems`, `maxItems`, `default: [...]`
- `"ui:widget"`: custom widgets — `"password"` (secrets), `"datetime"`, `"timezone"`,
  `"page-picker"`
- Conventionally include an `enabled` boolean. Add a `refresh_seconds` integer (with
  `default`/`minimum`/`maximum`) to opt into time-based caching — its validation is then
  handled by the base class via `_validate_refresh_seconds`.

For an API key: a `string` property with `"ui:widget": "password"` plus a matching
`env_vars` entry, read in `fetch_data` as `self.config.get("api_key") or os.getenv("X")`.
**Never hardcode or commit a real key.**

## variables (the rich dict format — preferred)

```json
"variables": {
  "groups": { "main": { "label": "Main Data" } },
  "simple": {
    "value": {
      "description": "The primary value",   // shown in the editor's variable picker
      "type": "string",                       // string | number | boolean (default string)
      "max_length": 22,                       // merged into max_lengths
      "group": "main",                        // must reference a defined group
      "example": "123"
    }
  },
  "arrays": {                                  // optional — repeated/indexed items
    "items": {
      "label_field": "name",
      "item_fields": ["name", "value", "status"]
    }
  }
}
```

- Each `simple` variable becomes the template token `{{<plugin_id>.<name>}}`.
- Every variable needs a `description` and a valid `group` (the tests enforce both).
- Array fields are referenced as `{{<id>.items.0.name}}`, `{{<id>.items.1.value}}`, etc.
- Keep `simple` keys in lockstep with the keys your `fetch_data` returns in `data`.

## demo

A bundled preview page. Keyed by device type (`flagship` and/or `note`), or a single flat
object. Each entry:

```json
"demo": {
  "flagship": {
    "name": "Tide Times Demo",
    "template": ["", "{{tide_times.status}}", "Value: {{tide_times.value}}", "", "", ""],
    "line_metadata": [{"alignment": "center", "wrap": false}, ...]   // one per line
  }
}
```

- `template` is an array of board lines; `{{...}}` placeholders **must reference declared
  variables** (the `date_time.*` system prefix is allowed). `test_demo_pages.py` enforces
  this — when you change variables, change the demo too.
- `line_metadata[i]`: `alignment` ∈ `left|center|right`, `wrap` bool.

## screenshots

```json
"screenshots": [
  { "src": "docs/board-display.png", "alt": "Tide Times displayed on a Vestaboard",
    "caption": "Default template", "primary": true }
]
```

`src` + `alt` required; exactly one `primary: true`. The scaffold emits a placeholder
`docs/board-display.png` — replace it with a real board render before registering.
