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
| **Where to turn on** | Always available | **Settings → Advanced → Beta Features → Transition Plugins** |
| **Step Interval / Step Size** | Supported | Not used — plugins set their own pacing |
| **Stability** | Stable | Deprecated; removal is being considered for v11 |

## Built-in Flip Strategies

Built-in strategies are a **Vestaboard Local API** feature. FiestaBoard sends the new message plus the name of a flip pattern through the API, and the board handles the animation.

Set the default in **Settings → Behavior → Board Transitions**:

| Name in the UI | API value | What it looks like |
|---|---|---|
| **None** | `null` | No animation — every character flips at once |
| **Wave** | `column` | Flips column by column, left to right |
| **Drift** | `reverse-column` | Flips column by column, right to left |
| **Curtain** | `edges-to-center` | Flips from both edges, meeting in the middle |
| **Row** | `row` | Flips row by row, top to bottom |
| **Diagonal** | `diagonal` | Flips in a diagonal wave, corner to corner |
| **Random** | `random` | Flips tiles in a random order |

Two optional settings tune the built-in strategies:

- **Step Interval (ms)** — delay between animation steps. Leave empty for the board default.
- **Step Size** — how many rows or columns animate at once. Leave empty for the board default.

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

1. Open **Settings → Advanced → Beta Features**.
2. Enable **Transition Plugins**. The change takes effect immediately — no restart.
3. Installed transition plugins appear in every transition picker.

There is no separate enable step for an individual transition plugin. Installing one is opting in: any installed transition plugin is selectable as soon as the beta flag is on. On the **Integrations** page they show up badged **Transition** and **Deprecated**, with no on/off toggle.

:::warning This is genuinely experimental
Every frame of a plugin transition is a real send to your board, so plugin transitions are bound by the board's send pacing. On some connections and some boards an animation will look less smooth than you expect, or will take longer. The plugin SDK is deprecated and will not reach general availability.
:::

FiestaBoard enforces per-plugin caps so a runaway animation cannot take your board hostage — a maximum frame count (default 500), a maximum runtime (default 120 seconds), and a minimum interval between frames (default 50 ms). When a run hits a cap, FiestaBoard snaps the board to the final message and stops.

## Choosing Where a Transition Applies

There are two places to choose a transition, and the more specific one wins.

### Global default

**Settings → Behavior → Board Transitions** sets the default for every board update. When the beta is on, the picker lists the built-in strategies under **Built-in** and your installed transition plugins under **Transition Plugins**.

### Per page

The page editor's header toolbar has a **Transition** dropdown. It offers:

- **Use global default** — the page inherits whatever is set in Settings
- Any built-in strategy
- Any installed transition plugin, when the beta is on

Picking anything other than **Use global default** creates a page-level override that applies whenever that page is sent. Switching back to **Use global default** clears the override.

### Resolution order

1. The page's own transition, if it has one
2. Otherwise, the global default from Settings

:::note
Transitions cannot currently be set per collection or per schedule entry. A scheduled page uses its own page-level transition if it has one, and the global default otherwise.
:::

## Troubleshooting

### Nothing animates — the whole board just changes at once

Most often this is a Cloud API board. Built-in strategies and transition plugins both animate only over the Local API: on a Cloud API board the new message appears at once. Switch the board to the Local API (see [API Keys](/docs/setup/api-keys)) to see transitions.

Note-array boards do not support built-in strategies at all.

### No plugins in the transition pickers

Plugin transitions stay hidden until the beta is on. Enable **Settings → Advanced → Beta Features → Transition Plugins** — the plugin entries appear immediately. Built-in strategies do not need the beta flag; they are always listed in Settings and in the page editor's **Transition** dropdown.

### A plugin transition looks choppy or slow

Every frame is a real send to the board, so a run is limited by the board's send pacing. Increasing the plugin's frame interval usually looks better than fighting for a faster one. This is a known limitation of animating a physical split-flap over an API.

### Step Interval and Step Size seem to do nothing

They only apply to built-in strategies. Transition plugins pace themselves through their own settings — for example Typewriter's `chars_per_frame` and `frame_interval_ms`.

### A `/transitions/*` endpoint returns 404

The Transition Lab's endpoints (`GET /transitions/plugins`, `POST /transitions/preview`, `POST /transitions/test-live`, `POST /transitions/restore`) were removed with the Lab. To find installed transition plugins, read `GET /plugins` and keep the entries whose `plugin_type` is `transition`; set one by storing `plugin:<id>` as a page's `transition_strategy` or as the global strategy under `/settings/transitions`.

## Next Steps

- [Page Editor](/docs/features/page-editor) - Set a per-page transition while you build a page
- [Plugin Development Guide](/docs/development/plugin-guide) - The plugin kinds, including the deprecated transition kind
- [API Endpoints](/docs/reference/api-endpoints) - The published REST API reference
