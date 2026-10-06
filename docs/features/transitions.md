---
sidebar_position: 6
description: "Animate how your FiestaBoard changes between messages — built-in Vestaboard flip strategies and the deprecated transition plugins like typewriter, dissolve, and slot machine."
keywords: [FiestaBoard transitions, Vestaboard transition, flip animation, transition plugins, typewriter transition, dissolve transition, split-flap animation]
---

# Transitions

Transitions control how your board gets from the message it is showing now to the next one — a left-to-right wave, a dissolve, a typewriter reveal, or nothing at all.

## Overview

FiestaBoard has **two different kinds of transitions**, and they behave differently. Knowing which one you are looking at explains most of the surprises people run into.

| | Built-in flip strategies | Transition plugins (beta, deprecated) |
|---|---|---|
| **Who animates** | The board, via the Vestaboard Local API | FiestaBoard, by sending many frames |
| **Works on** | Local API connections only | Local API connections; a Cloud API board shows the new message at once |
| **Examples** | Wave, Drift, Curtain, Row, Diagonal, Random | Typewriter, Simple Dissolve, Slot Machine, Quiet Library |
| **Where to turn on** | Always available | **Displays → (a display) → Transition → Transition Plugins** |
| **Step Interval / Step Size** | Supported | Not used — plugins set their own pacing |
| **Stability** | Stable | Deprecated; removal is being considered for v11 |

## Built-in Flip Strategies

Built-in strategies are a **Vestaboard Local API** feature. FiestaBoard sends the new message plus the name of a flip pattern through the API, and the board handles the animation.

Pick one for each display in **Displays → (choose a display) → Transition**:

| Name in the UI | API value | What it looks like |
|---|---|---|
| **None** | `null` | No animation — every character flips at once |
| **Wave** | `column` | Flips column by column, left to right |
| **Drift** | `reverse-column` | Flips column by column, right to left |
| **Curtain** | `edges-to-center` | Flips from both edges, meeting in the middle |
| **Row** | `row` | Flips row by row, top to bottom |
| **Diagonal** | `diagonal` | Flips in a diagonal wave, corner to corner |
| **Random** | `random` | Flips tiles in a random order |

The list shows only the strategies that display can run. With a built-in strategy selected, the same section shows **Speed**, with two optional settings:

- **Step Interval (ms)** — delay between animation steps. Leave empty for the board default.
- **Step Size** — how many rows or columns animate at once. Leave empty for the board default.

LED displays have no split-flap strategies; their **Transition** section offers the effects the device itself supports, such as **None** and **Flip**.

:::info
Built-in strategies only work over the **Local API**. If your board is configured for the Cloud API, FiestaBoard still sends your message, but the strategy is dropped and the board flips all tiles at once. Note-array boards also ignore built-in strategies and their step settings.
:::

## Transition Plugins (Beta, Deprecated)

:::warning Deprecated
Transition plugins are deprecated. Pages and settings that already use one keep working, and installed transition plugins are still offered in the pickers while the beta is on, but no new work is planned for them and removal of the plugin kind is being considered for v11. The **Integrations** page badges every transition plugin **Deprecated**. The Transition Lab preview page has been removed.
:::

Transition plugins are animated by FiestaBoard, not by the board. The plugin generates a sequence of complete board frames, and FiestaBoard sends them one after another, each as an ordinary board update.

On a Cloud API board, a transition plugin skips its frames and shows the new message at once. The Cloud API accepts one message every 15 seconds, so even a short transition would take minutes to finish. Use the Local API to see transitions animate.

FiestaBoard ships with four:

| Plugin | What it does |
|---|---|
| **Typewriter** | Reveals the target message left to right, character by character |
| **Simple Dissolve** | Replaces tiles in random order, dissolving the old message into the new one |
| **Slot Machine** | Spins each column through random characters, then locks columns left to right |
| **Quiet Library** | Updates word by word in small batches with long pauses, for the quietest possible refresh |

### Turning the beta on

1. Open **Displays** and choose a split-flap display (a Vestaboard or a FiestaPanel).
2. In its **Transition** section, turn on **Transition Plugins** (marked **Beta**). The change takes effect immediately — no restart.
3. Installed transition plugins appear in every transition picker.

**Transition Plugins** is one switch for the whole install: turning it on from any display turns it on for all of them. It appears only on displays that can play frame-by-frame transitions, so a Vestaboard connected through the Cloud API does not show it.

There is no separate enable step for an individual transition plugin. Installing one is opting in: any installed transition plugin is selectable as soon as the beta flag is on. On the **Integrations** page they show up badged **Transition** and **Deprecated**, with no on/off toggle.

:::warning This is genuinely experimental
Every frame of a plugin transition is a real send to your board, so plugin transitions are bound by the board's send pacing. On some connections and some boards an animation will look less smooth than you expect, or will take longer. The plugin SDK is deprecated and will not reach general availability.
:::

FiestaBoard enforces per-plugin caps so a runaway animation cannot take your board hostage — a maximum frame count (default 500), a maximum runtime (default 120 seconds), and a minimum interval between frames (default 50 ms). When a run hits a cap, FiestaBoard snaps the board to the final message and stops.

## Choosing Where a Transition Applies

There are two places to choose a transition, and the more specific one wins.

### Per display

Every display owns its transition. Set it in **Displays → (choose a display) → Transition**. A split-flap display offers **None**, the built-in strategies it supports, and — when the beta is on — your installed transition plugins. There is no install-wide default: a display's choice applies to every update sent to that display.

A new display starts with **None**. If `BOARD_TRANSITION_STRATEGY`, `BOARD_TRANSITION_INTERVAL_MS` or `BOARD_TRANSITION_STEP_SIZE` are set in the environment, a new split-flap display starts with those values instead (see [Environment Variables](/docs/reference/environment-variables)).

### Per page

The page editor's header toolbar has a **Transition** dropdown. It offers:

- **Use the display's transition** — the page uses whatever the display it is sent to has set
- Any built-in strategy
- Any installed transition plugin, when the beta is on

Picking anything other than **Use the display's transition** creates a page-level override that applies whenever that page is sent, on any display. Switching back to **Use the display's transition** clears the override.

### Resolution order

1. The page's own transition, setting by setting (strategy, step interval, step size)
2. Otherwise, the transition of the display the page is sent to

:::note
Transitions cannot currently be set per collection or per schedule entry. A scheduled page uses its own page-level transition if it has one, and the display's transition otherwise.
:::

### Upgrading to FiestaBoard 10

Before FiestaBoard 10, one install-wide transition under **Settings → Scheduling → Board Transitions** applied to every display. That setting is gone. On upgrade, FiestaBoard copies the old transition (strategy, step interval and step size) onto each display that had no transition of its own. A display that already had its own style keeps it and picks up the old step interval and step size.

## Troubleshooting

### Nothing animates — the whole board just changes at once

Most often this is a Cloud API board. Built-in strategies and transition plugins both animate only over the Local API: on a Cloud API board the new message appears at once. Switch the board to the Local API (see [API Keys](/docs/setup/api-keys)) to see transitions.

Note-array boards do not support built-in strategies at all.

### No plugins in the transition pickers

Plugin transitions stay hidden until the beta is on. Open **Displays**, choose a split-flap display, and turn on **Transition Plugins** in its **Transition** section — the plugin entries appear immediately. The switch is missing on a Cloud API Vestaboard; turn it on from a display that uses the Local API, or from a FiestaPanel. Built-in strategies do not need the beta flag; they are always listed in a display's **Transition** section and in the page editor's **Transition** dropdown.

### A plugin transition looks choppy or slow

Every frame is a real send to the board, so a run is limited by the board's send pacing. Increasing the plugin's frame interval usually looks better than fighting for a faster one. This is a known limitation of animating a physical split-flap over an API.

### Step Interval and Step Size seem to do nothing

They only apply to built-in strategies. Transition plugins pace themselves through their own settings — for example Typewriter's `chars_per_frame` and `frame_interval_ms`.

### A `/transitions/*` endpoint returns 404

The Transition Lab's endpoints (`GET /transitions/plugins`, `POST /transitions/preview`, `POST /transitions/test-live`, `POST /transitions/restore`) were removed with the Lab. To find installed transition plugins, read `GET /plugins` and keep the entries whose `plugin_type` is `transition`; set one by storing `plugin:<id>` as a page's `transition_strategy`, or as a display's `transition` through `PUT /settings/board`. `GET`/`PUT /settings/transitions` still answers but is deprecated and will be removed in v11: it reads and sets only the first display's transition.

### A page ignores the display's transition

That page has its own transition set. Open it in the page editor and pick **Use the display's transition** from the **Transition** dropdown.

## Next Steps

- [Page Editor](/docs/features/page-editor) - Set a per-page transition while you build a page
- [Plugin Development Guide](/docs/development/plugin-guide) - The plugin kinds, including the deprecated transition kind
- [API Endpoints](/docs/reference/api-endpoints) - The published REST API reference
