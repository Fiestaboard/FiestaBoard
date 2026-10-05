---
sidebar_position: 4
description: "Write a FiestaBoard output plugin that drives a display device: per-board instances, the manifest output block, device models and character sets, board settings screens and actions, OutputPluginBase, the LED renderer, the conformance suite, and publishing."
keywords: [FiestaBoard output plugin, OutputPluginBase, display driver, LED matrix plugin, device model, character set, output_api, conformance suite, Divoom Pixoo, plugin development]
---

# Writing an Output Plugin

An output plugin teaches FiestaBoard to drive a new kind of display: an LED matrix, a sign, a screen. FiestaBoard renders pages, schedules them and decides when to send; your plugin moves each frame to one device. You **declare** the device in `manifest.json` and **implement** a small Python class that writes frames.

This page is the complete reference for output plugin authors. It assumes you know how plugins are packaged from the [Plugin Development Guide](/docs/development/plugin-guide). If you want to show FiestaBoard on a screen you control without writing a plugin, read the frame stream instead: [Subscribing to Board Frames](/docs/development/output-stream-api). For every way to build on FiestaBoard, see [Building on FiestaBoard](/docs/development/integrations-overview).

:::info Beta: FiestaBoard 10.0.0 and later
Output plugins arrive with FiestaBoard **10.0.0**, and the contract (`output_api` 1) is a **beta**: it may still change before it is declared stable. Set `"fiestaboard_version": ">=10.0.0"` in your manifest.

Third-party output plugins, installed from the plugin registry or a git URL, run only while **Settings → Advanced → Beta Features → Output Plugins** is on. Outputs that ship with FiestaBoard need no beta.
:::

## The Short Version

1. Name the repository `fiestaboard-output--<name>` and set `"plugin_type": "output"` in `manifest.json`.
2. Add an `output` block: the `output_api` you target, the device models you drive, how fast the device can take writes, and the settings each board needs.
3. Subclass `OutputPluginBase` and implement `write()`. Talk to the device only through `self.http`.
4. Leave policy to core. Never sleep to throttle, retry in a loop, or skip a frame because it looks unchanged.
5. Run FiestaBoard's `OutputConformanceSuite` in your tests.

## Concepts

### A board is an instance of an output

The user-facing noun stays **board**. A board is one instance of an output: the Vestaboard on the wall, a TV showing a FiestaPanel, a Pixoo on a shelf. Every board names its output and keeps that output's settings in its `output_config`.

Unlike a data plugin, an output plugin is **instantiated once per board**. The loader never constructs your class. It loads the class and the manifest. When a board needs a device, core builds `YourPlugin(board_id, output_config)`, calls `open()` before the first write, and calls `close()` when the board is removed or its connection settings change. Two boards on two devices are two instances with two configs.

### What core does for you

Core owns the send policy for every board. Your plugin is a pipe.

| Concern | What core does | What your plugin does |
|---------|----------------|-----------------------|
| **Send floor** | Spaces writes to one device by your `min_interval_ms`, keyed by `device_key()`, so a board re-save does not reset the window | Declares `min_interval_ms` and a stable `device_key()` |
| **Latest wins** | Preempts the write in flight when a newer frame arrives, and fires the write's cancel token | Checks `cancel` between requests and stops early |
| **Dedupe** | Skips a frame the device already shows (color-aware for rich frames) | Nothing |
| **Pause and silence** | Never writes to a paused or silenced board | Nothing |
| **Transitions** | Resolves which transition a board runs, drives frame-by-frame transitions, and hands LED transitions to you | Implements the transition hooks it supports |
| **Host allowlist** | Refuses any device request to a host outside `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` before a socket opens | Sends every request through `self.http` |
| **Timeouts** | Gives each write 30 seconds (or your lower `write_timeout_ms`), then stops waiting and fires `cancel` | Honors `cancel` in every wait |
| **Circuit breaker** | After 3 failed writes in a row, refuses writes to that device for 300 seconds without calling you, then lets one probe through | Reports failures in `WriteResult` instead of raising |
| **Last frame** | Stores what each board shows, for the TV viewer and the API | Nothing |

### What your plugin does

- Turns a frame into the device's wire format and sends it.
- Reports what happened in a `WriteResult`.
- Answers probes: a connection test, discovery, identify, and any custom setup step your device needs.

## Repository Layout

```text
fiestaboard-output--acme-sign/
├── __init__.py                  # AcmeSign(OutputPluginBase)
├── manifest.json                # plugin_type "output" and the output block
├── output/
│   └── device-models.json       # FiestaUI DeviceModel objects
├── package.json                 # optional: data-only npm package
├── README.md
├── docs/
│   └── SETUP.md
└── tests/
    ├── conftest.py
    └── test_conformance.py
```

**Naming.** Registry repositories are named `fiestaboard-output--<name>`, lowercase with dashes. The plugin id is the name with dashes turned into underscores: `fiestaboard-output--acme-sign` is `acme_sign`. A repository installed from a git URL may use any name.

**Data-only `package.json`.** Your device data is plain JSON, so JavaScript tools can depend on it too. FiestaUI's Storybook, for example, previews a device from its plugin's `output/device-models.json`. Make the repository a data-only npm package that ships only that folder, and keep its `version` equal to the manifest's:

```json
{
  "name": "@your-scope/output-acme-sign",
  "version": "0.1.0",
  "description": "Device data for the Acme Sign output plugin (data only, no code).",
  "files": ["output/*.json"],
  "private": true
}
```

It carries no JavaScript. FiestaBoard never runs plugin JavaScript: every screen for your device is rendered from your manifest.

## The Manifest

A complete manifest for a LAN-connected LED sign:

```json
{
  "id": "acme_sign",
  "name": "Acme Sign",
  "version": "0.1.0",
  "description": "Show FiestaBoard pages on an Acme LED sign over your local network.",
  "author": "Your Name",
  "repository": "https://github.com/your-username/fiestaboard-output--acme-sign",
  "icon": "monitor",
  "plugin_type": "output",
  "fiestaboard_version": ">=10.0.0",
  "data_files": ["output/device-models.json"],
  "output": {
    "output_api": 1,
    "device_models": { "$ref": "output/device-models.json" },
    "delivery": "push",
    "min_interval_ms": 1000,
    "read_back": { "supported": false },
    "native_transitions": [],
    "write_timeout_ms": 10000,
    "settings_schema": {
      "type": "object",
      "properties": {
        "host": {
          "type": "string",
          "title": "Sign address",
          "description": "The sign's IP address on your network, for example 192.168.1.50.",
          "minLength": 1
        },
        "token": { "type": "string", "title": "Pairing token", "secret": true },
        "brightness": { "type": "integer", "title": "Brightness", "minimum": 0, "maximum": 100 }
      },
      "required": ["host"],
      "ui:sections": [
        { "id": "connection", "title": "Connection", "fields": ["host", "token"] },
        { "id": "advanced", "title": "Advanced", "fields": ["brightness"], "collapsible": true, "collapsed": true }
      ]
    },
    "actions": [
      { "id": "test_connection", "label": "Test connection" },
      { "id": "identify", "label": "Flash the sign" },
      {
        "id": "pair",
        "label": "Pair",
        "description": "Enter the code the sign shows.",
        "input_schema": {
          "type": "object",
          "properties": { "code": { "type": "string", "title": "Pairing code" } },
          "required": ["code"]
        },
        "result_fields": { "token": { "secret": true, "fills": "token" } }
      }
    ]
  }
}
```

And its device model, `output/device-models.json`:

```json
[
  {
    "id": "acme_sign_64",
    "label": "Acme Sign 64",
    "technology": "led_matrix",
    "family": "acme",
    "geometry": { "kind": "pixels", "width": 64, "height": 64 },
    "color": { "kind": "rgb", "bitDepth": 24 },
    "charset": "led_3x5",
    "font": "3x5",
    "animation": { "delivery": "none", "maxFps": 0 },
    "appearance": { "pixelShape": "round", "dotRatio": 0.8, "offColor": "#1a1a1a" }
  }
]
```

An output plugin declares no `variables`, `teaser` or `previews`: it shows other plugins' content and has none of its own. The rest of the manifest (`id`, `name`, `version`, `icon`, `author`, `repository`) follows the [Plugin Development Guide](/docs/development/plugin-guide#step-3-define-your-manifest).

### The `output` block

| Field | Required | Default | What it declares |
|-------|----------|---------|------------------|
| `output_api` | Yes | — | The contract major your plugin targets. This FiestaBoard supports `1`. Anything else is refused at load. |
| `device_models` | Yes | — | A non-empty array of FiestaUI DeviceModel objects or built-in model ids, or `{"$ref": "output/device-models.json"}`. The first model is the default. |
| `character_set` | No | the model's `charset` | A FiestaUI CharacterSet object, or a `$ref` to one. When declared, it is the output's character set and wins over every model's `charset`. |
| `delivery` | No | `"push"` | `"push"`: core calls your writes. `"pull"`: a client fetches frames from core (a TV browser), and core only stores them. |
| `min_interval_ms` | No | `0` | The send floor: the least time between two writes or sequences to one device. |
| `read_back` | No | not supported | `{"supported", "cost", "suggested_interval_s"}`. Set `supported` when the device can report what it shows, and implement `read_current()`. `cost` is `"cheap"` or `"network"`. |
| `native_transitions` | No | `[]` | Transition strategies the device animates itself. Core passes one to `write()` only if you declare it. |
| `write_timeout_ms` | No | `30000` | Lowers how long core waits for one write. It may only lower the default, never raise it. |
| `settings_schema` | No | `{}` | JSON Schema for each board's `output_config`, rendered as the board's settings screen. |
| `actions` | No | `[]` | The settings screen's buttons. See [Actions](#actions). |

A `$ref` names a JSON file inside your plugin directory, and the same path must be listed in the manifest's `data_files`. Keeping device data in its own file lets FiestaBoard, FiestaUI and your plugin read one copy.

### Device models

`device_models` uses FiestaUI's open device vocabulary, validated against FiestaUI's published DeviceModel JSON Schema. Each model is either:

- a **built-in id** that FiestaBoard already knows, such as `divoom_pixoo64`, `hub75_64x64` or `vestaboard_flagship`. An unknown id is an error and is never treated as a Vestaboard.
- a **DeviceModel object** with these fields:

| Field | Required | Notes |
|-------|----------|-------|
| `id` | Yes | Lowercase, `^[a-z][a-z0-9_]*$`. Qualify it with the maker, for example `acme_sign_64`. |
| `label` | Yes | Shown in the Device model picker. |
| `technology` | Yes | `"led_matrix"` or `"split_flap"`. |
| `family` | Yes | The protocol family, for example `"acme"`. |
| `geometry` | Yes | `{"kind": "pixels", "width", "height"}` for an LED matrix (required for `led_matrix`), `{"kind": "cells", "rows", "cols"}` for a fixed character grid, or `{"kind": "panel"}` / `{"kind": "note_array"}` for a grid sized per board. |
| `color` | Yes | `{"kind": "rgb", "bitDepth": 24}`, `{"kind": "monochrome", "color": "#ff2200", "bitDepth": 1}`, or `{"kind": "tiles"}`. |
| `charset` | Yes | A built-in set id (`vestaboard_v1`, `vestaboard_v2`, `led_5x7`, `led_3x5`) or an embedded CharacterSet. |
| `animation` | Yes | `{"delivery": "stream" \| "sequence" \| "none", "maxFps"}`, plus `maxFrames` and `minFrameMs` for a `sequence` device. |
| `font` | No | `"3x5"` or `"5x7"`, the LED font that lays out characters. |
| `appearance` | No | Preview cosmetics only. See [Appearance](#appearance). |

**The 3 × 15 floor.** Every board must hold at least 3 rows of 15 characters, the size of a Vestaboard Note, so every page fits every board. A `pixels` model's grid is how many glyphs of its font fit: a 64 × 64 matrix with the 3×5 font and 1-pixel gaps is 10 rows × 16 columns. A model below 3 × 15 is refused when a board is created, never enlarged. A 64 × 64 matrix with the 5×7 font is only 8 × 10, so it does not fit. Declare only models that reach the floor.

### Character sets

A character set says what a board can draw: which characters, which color tiles, which icons, and whether it can color text (`colorSpans`) or fill a cell's background (`blockSpans`). FiestaBoard uses the board's set to fit every message to the device, to warn about content a board cannot show, and to decide whether the board speaks [extended markup](/docs/reference/color-guide#colored-text-blocks-and-icons).

Most plugins reference a built-in set through their model's `charset`. A device with its own glyphs declares a set:

```json
{
  "id": "acme_sign_charset",
  "label": "Acme Sign",
  "extends": "led_3x5",
  "icons": ["sun", "cloud", "rain", "check", "cross"]
}
```

The rules, applied when your plugin loads:

- **`extends`** names a built-in set (or a set already loaded). Each field you give overrides the parent's whole field: `label`, `chars`, `tiles`, `icons`, `mixedCase`, `colorSpans`, `blockSpans`, `code62Glyph`, `font` and `glyphs`. Arrays are replaced, never merged.
- **`version`** defaults to `1` and is not inherited. Bump it whenever the set's content changes.
- A set **without** `extends` must be complete.
- An unknown parent, or a set that extends itself, is an error.
- **`glyphs`** maps a character to rows of `#` and `.` matching the font box, and wins over the shared font. Every glyph's character must also be in `chars`.

FiestaBoard flattens the set once, at load. Your plugin reads the result as `self.character_set`.

### Appearance

A model's `appearance` describes how the device looks in a preview: `pixelShape` (`"round"` or `"square"`), `dotRatio`, `offColor`, `substrateColor`, `bezel` and, for split-flap boards, `boardColors`. It is **preview-only**: nothing in it ever changes the bytes sent to a device. `options` lists the appearance fields a board may override, each with its allowed values, for example `{"board_color": ["black", "white"]}`.

### Delivery, floor and read-back

- **`min_interval_ms`** is the device's safe write rate. Core spaces whole writes and whole sequences by it. Inside one `write_sequence` upload, pacing the individual requests is your job.
- **`device_key()`** identifies the physical device, so the floor follows the device: two boards on one sign share one window. Use the host and port, or a hash of a token. Never put a credential in it.
- **`read_back`** lets core read what a device shows when something else changed it. Only declare it if `read_current()` returns the device's frame.

### Board settings

`settings_schema` is the board's settings screen. FiestaBoard renders it in **Settings → Hardware** and in the setup wizard, from the same JSON Schema vocabulary as a data plugin's settings, plus three things device setup needs:

**Sections.** `ui:sections` on the schema root groups properties. Properties in no section render first.

```json
"ui:sections": [
  { "id": "connection", "title": "Connection", "fields": ["mode", "host", "cloud_key"] },
  { "id": "advanced", "title": "Advanced", "fields": ["brightness"], "collapsible": true, "collapsed": true }
]
```

**Conditional fields.** `ui:visible_when` on a property shows it only while its sibling values match. A hidden field is not validated, and its saved value is kept.

```json
"host": { "type": "string", "title": "Sign address", "ui:visible_when": { "mode": "lan" } },
"cloud_key": { "type": "string", "title": "Cloud key", "secret": true, "ui:visible_when": { "mode": "cloud" } }
```

The whole grammar:

| Condition | True when |
|-----------|-----------|
| `{"mode": "lan"}` | `mode` equals `"lan"` |
| `{"mode": ["lan", "usb"]}` | `mode` is one of the values |
| `{"mode": "lan", "tls": true}` | every pair holds |
| `{"not": {"mode": "lan"}}` | the inner condition does not hold |
| `{"any": [{"mode": "lan"}, {"mode": "usb"}]}` | at least one holds |

Values are compared without coercion: `true` is not `1`. A field with no value reads as its `default`, else `null`.

A name starting with `@` reads the **board**, not a sibling: `@device_type` (`flagship`, `note`, `note_array` or `panel`) and `@device_model` (the board's device model id). Use them when one output's settings differ by board shape. The Vestaboard shows a Note array its tiles and a Flagship its address:

```json
"host": { "type": "string", "ui:visible_when": { "api_mode": "local", "@device_type": ["flagship", "note"] } },
"tiles": { "type": "array", "ui:widget": "tile-grid", "ui:visible_when": { "api_mode": "local", "@device_type": "note_array" } }
```

**Widgets.** Besides the standard widgets (`password`, `textarea`, `timezone`, `datetime`, `remote-options`), an output may use three device-setup widgets:

| Widget | On | What it renders |
|--------|----|-----------------|
| `mode-cards` | a string `enum` | Selectable cards, one per value. `ui:options.cards` gives each value a `title` and `description`. |
| `device-picker` | a string | A field filled from discovery results. `ui:options.action` names the action (default `discover`), `value_key` the device key written (default `ip`), and `label_key` the one shown (default `hostname`). |
| `tile-grid` | an array of objects with `row` and `col` | A grid for assigning one device per position, one dialog per slot with the item's other fields. `ui:options.rows_field` and `cols_field` name the integer properties that size it, or `"layout": "board"` sizes it by the board's own layout (a Note array's Notes down × across). `item_actions` names actions each slot's dialog runs on that one tile. `unique_fields` names item fields that should not repeat across tiles (a warning). An item's `required` fields decide when a tile counts as assigned. |

The widget set is closed and versioned with `output_api`: a widget outside your `output_api`'s set is a manifest error, because a settings screen that cannot render is a board that cannot be set up.

**Secrets.** Mark a credential `"secret": true`. FiestaBoard masks it as `***` in every API response, restores it when a masked value is saved back, and hands your plugin the real value.

### Actions

`actions` declares the buttons on the board's settings screen. Each entry is `{"id", "label", "description"?, "input_schema"?, "result_fields"?, "visible_when"?, "auto_apply"?}`.

| Action id | Calls |
|-----------|-------|
| `test_connection` | `check_connection()` |
| `discover` | `discover(timeout)` or `discover(timeout, hint=None)` (a class method) |
| `identify` | `identify()` |
| `detect_geometry` | `detect_geometry()` |
| any other id | `action_<id>(inputs)` |

- **`input_schema`** describes inputs that are not settings, such as a pairing code. FiestaBoard asks for them in a dialog and validates them before calling you.
- **`result_fields`** declares what a result fills in: `{"token": {"secret": true, "fills": "token"}}` writes the returned `token` into the `token` setting, through the secret path.
- **`visible_when`** shows the button only while a condition holds, in the same grammar as fields (board facts included).
- **`auto_apply`**: `true` applies a detected `geometry` at once instead of offering **Apply size**.

**The network hint (`hint_host`).** FiestaBoard usually runs in Docker's bridge mode, where its own address (`172.x`) belongs to a container network, not to the network your device is on. So a scan of "this host's subnet" searches the wrong network. The settings screen fills that gap: when the user opened FiestaBoard at a private IPv4 address (`10.x`, `172.16`–`172.31.x`, `192.168.x`, or link-local `169.254.x`; never `localhost` or a hostname), it sends that address as the input `hint_host` with every scan, for every output:

- a `discover` action receives it as `hint` when your `discover` takes one: declare `discover(cls, timeout, hint=None)`, and search the `/24` around `hint` before your own. A `discover(timeout)` written before the hint keeps working; it is called without it. A `hint_host` that is not a private IPv4 address is refused with a 400.
- a custom scan action receives it in `inputs["hint_host"]` if its `input_schema` declares `hint_host`. FiestaBoard fills it in for you and leaves it out of the action's dialog. Any action that does not declare it never sees it.
- a `device-picker` sends it with the action it runs. If that action declares a `subnet` input, the picker also offers a field for the user to type a network (`192.168.1.0/24`) to search.

Keep a scan to private networks and to a size you can sweep within the timeout: the Divoom Pixoo plugin's `candidate_subnets` is one way to do it.

A button is not repeated for an action a visible widget already runs: a `device-picker`'s discover, or a `tile-grid`'s `item_actions`. The dialog for an action's `input_schema` starts from the settings of the same name. A tile action takes its input from the tile's fields, asks in the tile's dialog for the rest, and fills its result into the tile.

Actions run on a throwaway instance built from the settings on screen, and it is closed afterwards. They work before a board exists: the setup wizard tests a device and pairs with it, then saves the board.

An action that needs more than that overrides the class method `handle_action(ctx)`. `ctx` is an `ActionContext`: `ctx.action`, `ctx.inputs`, `ctx.board` (the board's facts, with `board_id` `None` for a draft), `ctx.config` (its settings, secrets restored), and what FiestaBoard lends the action, since it builds every instance itself:

| Member | Gives you |
|--------|-----------|
| `ctx.instance(config=None)` | A throwaway instance from the board's settings, or from other settings (one device of an array). `None` when they make no usable connection. Closed for you afterwards. |
| `ctx.with_live(fn)` | Runs `fn(instance)` on the board's **live** instance while holding its send lock, for an action that writes to the device the board is driving. Raises a 503 refusal when the board has none. |
| `ctx.reader()` | A callable that reads what the board shows (through the live board, else a throwaway one), or `None`. |
| `ctx.invalidate()` | Asks FiestaBoard to send the board's content again on its next cycle, after an action wrote over it. |

Raise `OutputActionError(status_code, detail)` to refuse before anything is contacted. The default `handle_action` answers `discover` with the class's `discover(timeout)` (handing it `hint` when it takes one) and everything else through `run_action` on `ctx.instance()`. The Vestaboard's `actions.py` is a complete example.

An action returns an `ActionOutcome`, which FiestaBoard renders as one result panel:

| Field | Meaning |
|-------|---------|
| `status` | `"ok"`, `"warning"` or `"error"` |
| `message` | One line for the user |
| `guidance` | Steps to try, shown as a list |
| `fields` | Values to fill in, each an `ActionField(value, secret=False)` |
| `geometry` | A detected size: `{"device_type", "rows", "cols"}`, with an **Apply size** button (applied at once for an `auto_apply` action) |
| `devices` | Discovered devices, each a dict with at least `ip` and `port` |

Return `None` for a plain success. Mark every credential you hand back `ActionField(value, secret=True)`: FiestaBoard never logs it. `detail` is for raw data an older route of your own needs; FiestaBoard never shows or logs it.

### Board status and stored settings

A board card in **Settings → Boards** shows **Connected** or **Not configured** when the output says which. Override the class method `board_status(config, board)` to return an `OutputStatus(configured, attempted=True, message="")`: `configured` means the settings are enough to reach the device; `attempted` means the user has entered anything at all (FiestaBoard treats a board with some but not all settings as needing attention, not as a fresh install). The default, `None`, shows no badge. It is read from the settings, so it must not contact the device.

How a board's settings are stored and shown also has defaults you can override, all class methods:

| Method | Default |
|--------|---------|
| `normalize_config(config, board)` | Stores the settings as given |
| `mask_config(config, schema)` | Shows each set `secret` field as `***` |
| `restore_config(incoming, stored, schema)` | Puts each echoed `***` back from the stored settings; array items are matched by `id`, `name` or `key` |
| `masked_config_paths(config, schema)` | Lists the `***` values that could not be restored, so the save is refused |

Override them only when your settings need a rule the schema cannot state. The Vestaboard matches a Note's key to its tile by the Note's address, because tiles have no id.

## The Plugin Class

The Acme Sign plugin in full:

```python
"""Acme Sign output plugin for FiestaBoard."""

from __future__ import annotations

import base64
import logging

import requests

from src.plugins import (
    ActionField,
    ActionOutcome,
    CancelToken,
    CellFrame,
    ConnectionCheck,
    LedLayoutOptions,
    OutputHostBlocked,
    OutputPluginBase,
    RichCellFrame,
    WriteResult,
    cells_from_codes,
    layout_message,
    led_spec_for_model,
    rasterize,
)

logger = logging.getLogger(__name__)


class AcmeSign(OutputPluginBase):
    """Drives one Acme sign. Core builds one instance per board."""

    @property
    def url(self) -> str:
        return f"http://{self.config['host']}"

    def device_key(self) -> str:
        # Stable and credential-free: two boards on one sign share its floor.
        return f"acme_sign:{self.config['host']}"

    def write(self, frame: CellFrame, *, native, cancel: CancelToken) -> WriteResult:
        return self.write_cells(cells_from_codes(frame), native=native, cancel=cancel)

    def write_cells(self, cells: RichCellFrame, *, native, cancel: CancelToken) -> WriteResult:
        layout = layout_message(
            cells, led_spec_for_model(self.device_model), LedLayoutOptions(charset=self.character_set)
        )
        pixels = rasterize(layout).pixels  # RGB888, row-major
        try:
            response = self.http.post(f"{self.url}/frame", json={"rgb": base64.b64encode(pixels).decode()})
            response.raise_for_status()
        except requests.RequestException as exc:
            # A device failure is reported, never raised.
            logger.warning("Acme sign %s: write failed: %s", self.config["host"], exc)
            return WriteResult(success=False, was_sent=False)
        return WriteResult(success=True, was_sent=True)

    def check_connection(self) -> ConnectionCheck:
        try:
            self.http.get(f"{self.url}/status").raise_for_status()
        except OutputHostBlocked:
            return ConnectionCheck.blocked(self.config["host"])
        except requests.Timeout:
            return ConnectionCheck(success=False, message="The sign did not answer in time.", failure="timeout")
        except requests.RequestException as exc:
            return ConnectionCheck(
                success=False,
                message="Could not reach the sign.",
                failure="unreachable",
                error=str(exc),
                troubleshooting=("Check the sign is on and on the same network as FiestaBoard.",),
            )
        return ConnectionCheck(success=True, message="The sign answered.")

    def identify(self) -> None:
        self.http.post(f"{self.url}/flash", setup=True)

    def action_pair(self, inputs: dict) -> ActionOutcome:
        response = self.http.post(f"{self.url}/pair", json={"code": inputs["code"]})
        if response.status_code != 200:
            return ActionOutcome(status="error", message="The sign refused that code.")
        token = response.json()["token"]
        return ActionOutcome(message="Paired.", fields={"token": ActionField(token, secret=True)})
```

Import everything from `src.plugins`. That one module is the output plugin API, versioned with `output_api`, and nothing else in FiestaBoard core is a stable import. Besides the contract it carries helpers an output may need: `validate_board_host` and `validate_board_host_is_local_network` for an address the user typed, `check_dns_resolution` and `check_port_reachable` for diagnostics, `local_ipv4` for a subnet scan, and `text_to_board_array` to lay text out as codes.

### `OutputPluginBase` reference

| Member | Required | Purpose |
|--------|----------|---------|
| `__init__(board_id, config)` | — | Called by core. `board_id` is `None` for a throwaway instance that runs an action on unsaved settings. `config` is the board's `output_config` with secrets unmasked. Call `super().__init__` if you override it. |
| `write(frame, *, native, cancel)` | **Yes** | Show a frame of character codes 0–71. Return a `WriteResult`. |
| `write_cells(cells, *, native, cancel)` | No | Show a rich frame. Override it to receive colors and icons. See [Frames](#frames-codes-and-rich-cells). |
| `write_transition(before, after, transition, *, cancel)` | No | Animate one change with the board's LED transition. See [Transitions](#transitions). |
| `write_sequence(frames, *, cancel)` | No | Upload a timed list of frames in one go, for `animation.delivery: "sequence"` devices. |
| `device_key()` | Recommended | The physical device's identity for the send floor. The default is the board, which is wrong when two boards share a device. |
| `capabilities()` | No | Defaults to what the manifest declares. Override it to narrow a board's capabilities, for example a cloud connection that cannot animate. |
| `open()` / `close()` | No | Bracket the instance's lifetime: connect, warm up, release. |
| `check_connection()` | No | Probe the device once. Return a `ConnectionCheck`; never raise. |
| `discover(timeout, hint=None)` | No | A class method. Return found devices, each a dict with at least `ip` and `port`. `hint` is the private IPv4 address the user opened FiestaBoard at, or `None`; see [the network hint](#actions). |
| `identify()` | No | Make the device show which one it is: flash, blink, beep. |
| `detect_geometry()` | No | Read the device's size: `{"device_type": "panel", "rows", "cols"}`, or `None`. |
| `read_current()` | No | What the device shows, as codes, when `read_back.supported`. |
| `accepts_frame(frame)` | No | Whether a frame has a shape the device takes. Core asks before it spends anything on the write; a refused frame is a failed write. |
| `connection_label()` | No | How the board is connected, in words (the MQTT `board_api_mode` sensor). Defaults to the plugin id. |
| `test_connection()` | No | Whether the device answers. Defaults to `check_connection()`'s verdict. |
| `cache_synced(frame)` / `cache_cleared()` | No | Core adopted a read-back as what the board shows, or forgot it. Only an output that keeps its own per-device dedupe (one frame fanned out to several devices) needs them. |
| `forced` | — | `True` while core runs a forced write, so an output with its own per-device dedupe re-sends everything. Read it; never set it. |
| `config_from_board(board)` | No | A class method: the instance's config from a saved board. The default is the board's `output_config`. Return `None` for a board with no usable connection. |
| `declared_capabilities(manifest)` | No | A class method: the output's capabilities before any board exists. Defaults to the manifest's; override it when the output is more than its first device model says. |
| `markup_follows_charset` | — | A class attribute, `True` by default. `False` keeps a board's content in split-flap markup even when its character set is rich. |
| `diagnostics()` | No | A list of `DiagnosticCheck(name, ok, detail)`. Reserved: not shown in the app yet. |
| `run_action(action, inputs)` | No | The action dispatcher. Override it only to route actions yourself. |
| `handle_action(ctx)` | No | A class method: runs one action with an `ActionContext`. See [Actions](#actions). |
| `board_status(config, board)` | No | A class method: the board card's Connected / Not configured. See [Board status](#board-status-and-stored-settings). |

What core resolved for the board is on the instance:

| Accessor | Value |
|----------|-------|
| `self.config` | The board's `output_config` |
| `self.board_id` | The board's id, or `None` for a draft |
| `self.device_model` | The board's DeviceModel dict: the model the board was created as, else your first |
| `self.character_set` | The board's character set, flattened |
| `self.board_geometry` | The board's character grid, `(rows, cols)` |
| `self.http` | The device HTTP client |

### `WriteResult`

Return `WriteResult(success, was_sent)`:

- `WriteResult(success=True, was_sent=True)`: the frame landed.
- `WriteResult(success=False, was_sent=False)`: the device failed. Log why and return; do not raise.
- A write that landed on part of the board (one panel of several failed): `success=False`, `partial=True`, and `failed_regions` naming the cells that did not update, each a `FrameRegion(row, col, rows, cols)`.

Leave `floor_seconds` alone, and `throttled` and `retry_after_seconds` too unless the device itself refused the write for rate (an HTTP 429). Then return `WriteResult(True, False, throttled=True, retry_after_seconds=N)`: core keeps the board's send slot closed for `N` seconds and reports the send as throttled. Core keeps its own floor; never wait it out yourself.

### Talking to the device: `self.http`

Every request to the device goes through `self.http`, never `requests` directly. It has the `requests` methods you know (`get`, `post`, `put`, `delete`, `request`), takes the same keywords, and returns a `requests.Response`. In front of your code it puts:

- **The host allowlist.** With `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` set, a request to any other host raises `OutputHostBlocked` before a socket opens. FiestaBoard's dev stack sets it to its mock devices, so a developer's real device stays untouched while they work on something else.
- **Timeouts.** A request with no `timeout` gets a default `(connect, read)` timeout, so a dead device fails one request in seconds.
- **No redirects.** A redirect would reach a host the allowlist never checked.
- **Cancel.** Once the write's cancel token fires, the next request raises `RequestCancelled` without reaching the device.
- **Setup requests.** Pass `setup=True` for a request that is not the board write itself, such as a reset or a brightness command. A failed setup request you tolerate does not make a landed write count as failed.

Every error is a `requests` exception, so one `except requests.RequestException` handles a blocked, cancelled or unreachable device.

### Frames: codes and rich cells

`write()` receives a `CellFrame`: the whole board as rows of FiestaBoard [character codes](/docs/reference/character-codes) 0–71. Codes 63–71 are color tiles. Every output understands this frame.

A device that can draw color and icons should also override `write_cells()`. Once you override it, core sends every frame it has rich cells for through `write_cells()` instead, and dedupes color-aware, so recoloring a word is a new frame. Each cell is a `BoardToken`:

| Field | Value |
|-------|-------|
| `type` | `"char"` (a character) or `"color"` (a color tile) |
| `value` | The character, for `"char"` |
| `code` | The tile's numeric code as a string (`"63"`), for `"color"` |
| `color` | Text color from a color span, or `None` |
| `background` | Cell background from a block span, or `None` |
| `icon` | The icon name, when the cell is an icon |
| `flap_code` | The cell as a 0–71 code |

Core has already fitted every cell to the board's character set, so each one is something the set can draw. Frames that were only ever codes, such as a blank board or a transition plugin's intermediate frames, still arrive through `write()`. Convert them with `cells_from_codes()` if you want one rendering path, as the example does.

### Rendering LED frames: `src.led`

FiestaBoard ships the same LED renderer FiestaUI previews with, so the board matches its preview pixel for pixel. Plugins cannot install dependencies, so the renderer is pure Python. From `src.plugins`:

| Function | Does |
|----------|------|
| `led_spec_for_model(model)` | The matrix spec (size, font) for a DeviceModel: pass `self.device_model` |
| `layout_message(frame, spec, options)` | Lays out rich cells (or a markup string) on the matrix. Pass `LedLayoutOptions(charset=self.character_set)` |
| `rasterize(layout)` | Renders a layout to an RGB888 frame; `.pixels` is the bytes, row-major |
| `plan_transition(before, after, spec)` | Plans an LED transition between two layouts |
| `transition_frames(planned, fps=30)` | The planned transition's frames, each with `.pixels`, ending on the target |
| `resolve_led_transition(choice, model)` | Which LED transition a device model runs, fitted to what it can show |
| `led_flip_seed(...)` | The seed of FiestaBoard's deterministic flip, for reproducing it exactly |

### Transitions

A board's transition reaches your plugin in one of three ways:

- **LED transitions.** Override `write_transition(before, after, transition, *, cancel)`. Core calls it instead of `write_cells()` for every change once it knows what the board showed before. `transition` is the board's resolved LED transition with its `spec` already fitted to your device's frame budget. Plan it with `plan_transition()`, render it with `transition_frames()`, upload it, and land on `after`. It counts as one write for the floor. A device too slow for any LED transition resolves to `none`, and core then sends a still through `write_cells()` instead. A board setting that names no LED transition at all, such as a stale or mistyped value, falls back to the model's default, with `source` set to `"fallback"` and a `reason`.
- **Transition plugins.** A board can use a frame-by-frame transition plugin. For a `sequence` device, core collects its frames and calls `write_sequence(frames, *, cancel)` once; each `TimedFrame` has a `frame` and a `duration_ms`, and the last frame is always the target. Upload at most the model's `maxFrames`. For other devices core sends the frames one at a time through `write()`.
- **Native transitions.** If the device animates changes itself, list the strategies in `native_transitions`. Core passes the chosen one to `write()` as `native`, and never passes one you did not declare.

## Testing

### The conformance suite

FiestaBoard publishes one definition of a well-behaved output plugin, `OutputConformanceSuite`. Core runs it against its own test plugin, and every output plugin repository runs it in its CI:

```python
from pathlib import Path

from src.outputs.conformance import OutputConformanceSuite

from plugins.acme_sign import AcmeSign

PLUGIN_DIR = Path(__file__).resolve().parent.parent


def make_plugin(board_id, config, transport):
    return AcmeSign(board_id, config)  # the suite routes self.http to its fake device


def test_the_plugin_is_conformant():
    OutputConformanceSuite(
        plugin_dir=PLUGIN_DIR,
        factory=make_plugin,
        config={"host": "192.0.2.10", "token": "test_token_1234"},
    ).assert_conformant()
```

The suite plays the device: it routes your plugin's `self.http` to a fake transport, so your real request code runs. Give `config` a value for every secret field. To check that a `sequence` upload ends on its target frame, also pass `decode`, a function that turns one request's payload back into the frame it carries.

| Rule | Checks |
|------|--------|
| `manifest` | `manifest.json` loads with no error and is `plugin_type: "output"` |
| `character_set` | Every declared character set flattens to a non-empty set |
| `geometry_floor` | Every device model reaches the 3 × 15 floor |
| `import_network` | Importing the plugin makes no network call |
| `device_key` | Non-empty, stable across calls and instances, and free of secrets |
| `floor` | The plugin does not throttle itself or talk to the device outside a write |
| `device_traffic` | Writes and probes go only through `self.http` |
| `write_result` | Every write returns a well-formed `WriteResult`, and a device failure is reported, not raised |
| `cancel` | After `cancel` fires, a write starts no new request and returns promptly |
| `sequence` | A `sequence` upload stays within `maxFrames` and ends on the target |
| `check_connection` | Returns a `ConnectionCheck`, never raises, and reports a failing device |

### A mock device

The conformance suite proves the contract. Your own tests prove the wire format: run a small mock of your device on `127.0.0.1` that records each request and can fail, hang or answer slowly on purpose. Block every other host with `pytest-socket`, so no test can reach a real device:

```bash
python -m pytest tests/ --disable-socket --allow-hosts=127.0.0.1
```

Keep coverage at 80% or more, as for every plugin.

### Running the tests against FiestaBoard

Tests import FiestaBoard core (`src.plugins`, `src.outputs.conformance`), so they run against a FiestaBoard checkout at 10.0.0 or later. Put the checkout on `PYTHONPATH` and expose your plugin as `plugins.<plugin_id>`, the way FiestaBoard loads it:

```bash
mkdir -p plugins && touch plugins/__init__.py
ln -s .. plugins/acme_sign
PYTHONPATH="$(pwd):/path/to/FiestaBoard" python -m pytest tests/
```

## Installing and Publishing

### Install it while you develop

With **Settings → Advanced → Beta Features → Output Plugins** on, install your repository from **Integrations → Marketplace → Install Plugin from Git**, or with the API:

```bash
curl -X POST http://localhost:4420/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"repository": "https://github.com/your-username/fiestaboard-output--acme-sign"}'
```

Then add a board for it in **Settings → Hardware → Add Board → Other displays**. Your plugin's settings screen opens there, rendered from your manifest. Boards can also be created with `POST /outputs/acme_sign/boards`, naming one of your device models.

Set `FIESTABOARD_OUTPUTS_ALLOW_HOSTS` to your device's address while you test, so nothing else on your network can be reached by mistake.

### Versioning: `output_api`

`output_api` is a hard gate, unlike a data plugin's advisory `fiestaboard_version`. FiestaBoard refuses a plugin whose `output_api` it does not implement, at three points:

1. **The update check** reads the incoming manifest and never offers an update this FiestaBoard cannot run.
2. **An update** that fails verification or does not load is rolled back to the version it replaced, and that version is not offered again until a newer one appears.
3. **Load** refuses the plugin and reports why with the plugin's load errors. A first-party output falls back to the copy FiestaBoard shipped with.

The settings widgets you may use are versioned with it, too. When the contract changes incompatibly, the major goes up; keep targeting the major your users' FiestaBoard supports.

An output plugin a board uses cannot be uninstalled. Remove the board first.

### Publishing to the registry

Once it works on your device, open a pull request against FiestaBoard that adds your plugin to `plugin-registry.json`, as for any [external plugin](/docs/development/plugin-guide#developing-an-external-plugin), with `"plugin_type": "output"` in the entry. Your repository must follow the `fiestaboard-output--<name>` convention.

:::note Third-party outputs in the beta
While the contract is in beta, every third-party output plugin, listed in the registry or installed by git URL, stays behind **Settings → Advanced → Beta Features → Output Plugins**. The setup wizard shows such displays as needing the beta, and offers to turn it on.
:::

### Outputs that ship with FiestaBoard

The Vestaboard and FiestaPanel are output plugins too, written against the same API as yours, each in its own repository: [fiestaboard-output--vestaboard](https://github.com/Fiestaboard/fiestaboard-output--vestaboard) and [fiestaboard-output--fiestapanel](https://github.com/Fiestaboard/fiestaboard-output--fiestapanel). Either is a good place to read a complete output, with its tests.

First-party outputs are pinned in FiestaBoard's `outputs.lock.json` (repository, commit, `output_api` and a digest of the files) and baked into the image at build time, so they need no network, which matters on a Raspberry Pi or in the Home Assistant add-on. The Vestaboard and FiestaPanel run straight from that copy, which FiestaBoard checks against the digest each time it loads them, and they update when FiestaBoard does. Any other first-party output installs from the copy, and if its installed copy cannot run, FiestaBoard falls back to the copy it shipped with, so a board never goes dark because of its plugin. First-party outputs never need the beta.

## Worked Example: Divoom Pixoo 64

The Divoom Pixoo 64 plugin, [fiestaboard-output--divoom-pixoo](https://github.com/Fiestaboard/fiestaboard-output--divoom-pixoo), is the reference output plugin. It is in development; its device data was measured on a Pixoo 64 in October 2026. Read it for:

- **Device data in its own file.** `output/device-models.json` holds the `divoom_pixoo64` model: 64 × 64 RGB pixels, the `led_3x5` set and 3×5 font (a 10 × 16 grid), square-pixel `appearance`, and `stream` animation at 2 frames a second. That is the device's safe push rate, below every LED transition's minimum, so a Pixoo snaps from one message to the next. The manifest points at it with `$ref`, and the repository is also a data-only npm package.
- **One rendering path.** `write()` and `write_cells()` both go through one `render()` built on `layout_message()` and `rasterize()`.
- **Device quirks as named constants.** Request pacing inside an upload, a periodic reset of the device's animation counter, and connect and read timeouts each live at the top of `__init__.py`, with the community sources they came from.
- **Tests.** A mock Pixoo on loopback that can fail, hang or freeze, a network fence, and the conformance suite with a `decode` that maps an upload back to its grid.

## Next Steps

- [Subscribing to Board Frames](/docs/development/output-stream-api) - Show a board on a screen you control, with no plugin
- [Building on FiestaBoard](/docs/development/integrations-overview) - Every way in: push, pull and data
- [Plugin Development Guide](/docs/development/plugin-guide) - Packaging, manifests and external repositories
- [Color Guide](/docs/reference/color-guide) - What color spans, blocks and icons look like on each kind of board
