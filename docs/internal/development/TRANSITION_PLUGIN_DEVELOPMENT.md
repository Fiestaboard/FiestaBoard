# Transition Plugin Development Guide

> ⚠️ **Beta / Experimental.** Transition plugins ship behind the
> ``beta.transition_plugins_enabled`` settings flag
> (Settings → Advanced → Beta Features → Transition Plugins).
> The SDK contract is not yet stable -- method signatures, manifest
> fields, and runtime semantics may change in future releases before
> general availability. Use it, build with it, send feedback, but don't
> treat your plugin's interface as locked in yet.

Transition plugins drive **frame-by-frame board animations** that change one display state into another. Unlike Vestaboard's built-in strategies (column wave, edges-to-center, etc.), which are Local API features the board performs on its own, a transition plugin emits a sequence of intermediate board grids and the runtime sends each one as a separate ordinary board update -- enabling typewriter reveals, slot-machine spins, dissolves, and anything else that needs custom per-frame control. Because the frames are just normal sends, plugin transitions run on Cloud connections too.

This is a different plugin type from the data plugins documented in [PLUGIN_DEVELOPMENT.md](./PLUGIN_DEVELOPMENT.md). Data plugins fetch information and expose template variables; transition plugins shape *how* a board update happens, not *what* it shows.

## Quick Start

1. Copy the template:

   ```bash
   cp -r plugins/_template_transition plugins/my_transition
   ```

2. Edit `plugins/my_transition/manifest.json`:
   - Set `id` to `my_transition` (must match the directory)
   - Set `plugin_type` to `"transition"` (required)
   - Set `category` to `"transition"`
   - Fill in name, version, description, author
3. Implement `generate_frames()` in `plugins/my_transition/__init__.py`.
4. Add tests under `plugins/my_transition/tests/` aiming for >80% coverage.
5. Run `python scripts/run_plugin_tests.py --plugin=my_transition` to verify.
6. Turn on Settings → Advanced → Beta Features → **Transition Plugins**, then open **Transition Lab** (`/transitions`) to preview your plugin frame by frame between two pages.

## The Plugin Class

Transition plugins inherit from `src.plugins.base.TransitionPluginBase` and must implement:

- `plugin_id` (property): unique id matching the manifest
- `generate_frames(from_grid, to_grid, device, config) -> Iterator[(grid, delay_ms)]`

The `device` argument is a `src.devices.BoardContext` — a frozen descriptor with `device_type` (`"flagship"`, `"note"`, or `"note_array"`), `rows`, and `cols` (plus `height`/`width` aliases). Note arrays are true 2-D grids — up to **120×24 characters** (width×height, matching the `120 × 24` max in [`NOTE_ARRAYS.md`](../reference/NOTE_ARRAYS.md)) — so derive geometry from `device.rows`/`device.cols` (or from the grids themselves) rather than hardcoding the flagship's 22×6.

Optional hooks:

- `validate_config(config) -> List[str]`: return error strings for bad config
- `on_config_change(old, new)`: react to config updates
- `cleanup()`: release any resources on disable

### Example: A "Knight Rider" sweep

```python
from typing import Any, Dict, Iterator, List, Tuple
from src.plugins.base import TransitionPluginBase

class KnightRiderTransition(TransitionPluginBase):
    @property
    def plugin_id(self) -> str:
        return "knight_rider"

    def generate_frames(
        self,
        from_grid: List[List[int]],
        to_grid: List[List[int]],
        device,
        config: Dict[str, Any],
    ) -> Iterator[Tuple[List[List[int]], int]]:
        speed_ms = int(config.get("speed_ms", 80))
        rows = len(to_grid)
        cols = len(to_grid[0]) if rows else 0
        revealed = [list(row) for row in from_grid]
        # Sweep right
        for c in range(cols):
            for r in range(rows):
                revealed[r][c] = to_grid[r][c]
            yield [list(row) for row in revealed], speed_ms
```

## What you get for free

The runtime handles a lot so your generator can stay simple:

- **Final-frame snap**: After your generator exhausts, the runner unconditionally sends `to_grid` to guarantee the board lands on the exact target. You don't have to make your last yield equal `to_grid` exactly.
- **Cancellation**: If a new page or trigger arrives mid-transition and your manifest declares `interruptible: true`, the runner sets a cancel event. Your generator simply gets stopped at the next delay boundary.
- **Caps**: The runner enforces `max_frames`, `max_runtime_seconds`, and a `min_interval_ms` floor on your yielded delays. A runaway loop won't lock up the board.
- **Per-board serialization**: The runner holds the board's send lock for the duration of the transition. Concurrent rotation / trigger sends queue cleanly.

## Manifest fields

```json
{
  "id": "my_transition",
  "name": "My Transition",
  "version": "1.0.0",
  "description": "Short one-liner shown in the picker.",
  "author": "Your Name",
  "icon": "wand-2",
  "category": "transition",
  "plugin_type": "transition",
  "settings_schema": {
    "type": "object",
    "properties": {
      "speed_ms": {
        "type": "integer",
        "title": "Speed (ms)",
        "default": 100,
        "minimum": 0,
        "maximum": 2000
      }
    }
  },
  "transition_settings": {
    "interruptible": true,
    "min_interval_ms": 50,
    "max_frames": 200,
    "max_runtime_seconds": 60
  }
}
```

### `transition_settings` block

| Field                  | Default | Purpose                                                                                                             |
| ---------------------- | ------- | ------------------------------------------------------------------------------------------------------------------- |
| `interruptible`        | `true`  | When `true`, a new send mid-transition cancels your in-flight transition. Set `false` only if mid-stop looks broken.|
| `min_interval_ms`      | `50`    | Floor on the delay between frames. The runner uses `max(your_delay, min_interval_ms)`.                              |
| `max_frames`           | `500`   | Hard cap on frame count. The runner aborts and snaps to target if exceeded.                                          |
| `max_runtime_seconds`  | `120`   | Hard cap on wall-clock seconds.                                                                                      |

Choose conservatively. A transition with `max_frames: 5000` and `min_interval_ms: 0` can flood the board API and block any other update for minutes.

## Selecting a transition plugin

Once your plugin is installed it is ready to use. Unlike data plugins, transition plugins are not gated on the Integrations page's enabled toggle — `PluginRegistry.get_transition_plugin()` never consults it, because a transition has no polling loop or background cost. Installing is opting in. (The `beta.transition_plugins_enabled` flag above still gates the feature as a whole; with it off, `BoardClient.render()` logs and snaps to the target grid.) Users select your plugin from:

- The **Transition** dropdown in the page editor's toolbar, which sets that one page's transition
- Settings → Behavior → Board Transitions, which sets the default for every page

A page's own transition wins over the global default; the dropdown's "Use global default" option clears the page-level override.

Pages store the choice as `transition_strategy = "plugin:my_transition"`. The runtime parses the `plugin:` prefix and routes the send through `TransitionRunner`.

## Visual testing

The **Transition Lab** at `/transitions` (sidebar entry, visible once the beta is on) previews any installed transition plugin between two of your real pages without touching the board. It uses `POST /transitions/preview` under the hood, which calls your `generate_frames()` and returns the resulting grids as JSON. Use the timeline scrubber to step through frames and verify each intermediate state.

The Lab's config box is seeded with the plugin's saved config and passed straight through to `generate_frames()`, so you can try values without saving them — the fastest way to sanity-check `validate_config()` and your defaults.

When you're ready to see it on hardware, **Test live** runs the transition once on the real board and **Restore** puts the active page back (the display loop restores it on its own as well).

## Performance & rate limits

- The Vestaboard hardware has internal timing constraints. Sending frames faster than the flap mechanism can settle (~14s for a full revolution under heavy update) will cause the board to drop requests.
- The Cloud API has stricter rate limits than the Local API. Transition plugins are the *only* way to animate on Cloud-mode boards (the built-in strategies are Local API features and are ignored there), but the practical frame rate is much lower.
- Cloud **note arrays** are throttled to one send per 15 seconds. The runner automatically paces your frames (and the final snap) to the board client's `min_send_interval_ms`, so your plugin still works — it just runs no faster than that floor. Slow, deliberate transitions are the natural fit there.
- Use `min_interval_ms` to protect users from runaway loops in your own plugin.

## Publishing an external transition plugin

External plugins follow the same registry mechanism as data plugins (see [PLUGIN_DEVELOPMENT.md](./PLUGIN_DEVELOPMENT.md#publishing-to-the-plugin-registry)). Transition plugins use the naming convention `fiestaboard-transition--<name>` (vs `fiestaboard-plugin--<name>` for data plugins). Add your repo to `plugin-registry.json` with `"plugin_type": "transition"` so the loader knows what to expect before cloning.

## Reference

- **Base class**: `src/plugins/base.py` → `TransitionPluginBase`
- **Runner**: `src/transitions/runner.py` → `TransitionRunner`
- **Send chokepoint**: `src/board_client.py` → `BoardClient.render()`
- **API endpoints**: `GET /transitions/plugins`, `POST /transitions/preview` in `src/api_server.py`
- **First-party examples**: `plugins/typewriter`, `plugins/simple_dissolve`, `plugins/slot_machine`, `plugins/quiet_library`
