# Slot Machine Plugin

A transition plugin where each column "spins" through random characters like a slot-machine reel before locking on the target. Columns stagger left-to-right so the board settles in a satisfying cascade.

![Slot Machine Display](./docs/board-display.png)

**→ [Setup Guide](./docs/SETUP.md)**

## Overview

Slot Machine is a transition plugin -- it doesn't display its own content. When the active page changes, each column of the board spins through a sequence of random tile codes (mimicking a flap reel cycling) and then locks on the target. The stagger setting controls how much later each column starts locking than the previous one, producing a left-to-right cascade.

This plugin plays to the unique nature of the Vestaboard's split-flap mechanism: where the built-in strategies like Wave or Edges to Center simply *move* the final state into place, Slot Machine animates the *flaps themselves* as if the board were a row of mechanical reels. Those built-in strategies are Local API features; Slot Machine is drawn frame by frame by FiestaBoard and sent as ordinary board updates, so it runs on any board connection.

## Template Variables

None. Transition plugins don't expose template variables.

## Example Templates

Slot Machine isn't referenced from a template. With the **Transition Plugins** beta on (Settings → Advanced → Beta Features), select it from the **Transition** dropdown in the page editor's toolbar for one page, or from Settings → Behavior → Board Transitions for every page. The per-page choice wins; "Use global default" clears it.

Pages store the choice as `transition_strategy = "plugin:slot_machine"`.

## Configuration

| Setting               | Type    | Default | Description                                                                              |
| --------------------- | ------- | ------- | ---------------------------------------------------------------------------------------- |
| `spin_frames`         | integer | 6       | Random-character frames each column shows before locking (1-30).                          |
| `column_stagger`      | integer | 1       | Frames between adjacent column locks (0-10). 0 = simultaneous, higher = more pronounced cascade. |
| `frame_interval_ms`   | integer | 80      | Pause between frames in milliseconds (0-1000). Smaller = faster spin.                     |
| `seed`                | integer | 0       | Fixed integer for deterministic playback (useful for previews). 0 = fresh random.        |

## Features

- Visually striking flap-reel effect that plays to the Vestaboard's mechanical character
- Tunable cascade pattern via `column_stagger`
- Random spin per run (or seeded for predictable previews)
- Works on any board connection, Local API or Cloud
- Bounded: capped at 300 frames / 60 seconds runtime
- Interruptible: a new page or trigger cancels the in-flight spin cleanly

## Author

FiestaBoard
