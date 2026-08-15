---
sidebar_position: 6
description: "Animate how your FiestaBoard changes between messages — built-in Vestaboard flip strategies and beta transition plugins like typewriter, dissolve, and slot machine."
keywords: [FiestaBoard transitions, Vestaboard transition, flip animation, transition plugins, typewriter transition, dissolve transition, split-flap animation, Transition Lab]
---

# Transitions

Transitions control how your board gets from the message it is showing now to the next one — a left-to-right wave, a dissolve, a typewriter reveal, or nothing at all.

## Overview

FiestaBoard has **two different kinds of transitions**, and they behave differently. Knowing which one you are looking at explains most of the surprises people run into.

| | Built-in flip strategies | Transition plugins (beta) |
|---|---|---|
| **Who animates** | The Vestaboard itself | FiestaBoard, by sending many frames |
| **Works on** | Local API connections only | Any board connection (Local or Cloud) |
| **Examples** | Wave, Drift, Curtain, Row, Diagonal, Random | Typewriter, Simple Dissolve, Slot Machine, Quiet Library |
| **Where to turn on** | Always available | **Settings → Advanced → Beta Features → Transition Plugins** |
| **Step Interval / Step Size** | Supported | Not used — plugins set their own pacing |
| **Stability** | Stable | Experimental; behavior and settings may change |

## Built-in Flip Strategies

Built-in strategies are a **Vestaboard Local API** feature. FiestaBoard sends the new message plus the name of a flip pattern, and the board hardware performs the animation itself.

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

## Transition Plugins (Beta)

Transition plugins are animated by FiestaBoard, not by the board. The plugin generates a sequence of complete board frames, and FiestaBoard sends them one after another. Because each frame is an ordinary board update, plugin transitions work on **any** connection type — including Cloud API boards that cannot use the built-in strategies.

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
3. **Transition Lab** appears in the sidebar, and installed transition plugins appear in every transition picker.

There is no separate enable step for an individual transition plugin. Installing one is opting in: any installed transition plugin is selectable as soon as the beta flag is on. On the **Integrations** page they show up badged **Transition**, with no on/off toggle.

:::warning This is genuinely experimental
Every frame of a plugin transition is a real send to your board, so plugin transitions are bound by the board's send pacing. On some connections and some boards an animation will look less smooth than the preview does, or will take longer than you expect. The plugin SDK is experimental and its APIs, settings, and behavior may change before general availability.
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

## Transition Lab

The **Transition Lab** (`/transitions`) is a preview harness for plugin transitions. It appears in the sidebar only while the Transition Plugins beta is on.

In the Lab you can:

- Pick a transition plugin and two of your real pages to transition between
- Choose the device shape — Flagship, Note, or a note array
- Override the plugin's settings for a single run with a JSON config
- Play, pause, step frame by frame, or scrub the generated sequence

Previews are generated in FiestaBoard and rendered in your browser. Nothing is sent to your board, so you can iterate as much as you like.

When you want to see it on real tiles, **Test live on board** runs the transition once on your actual board, and **Restore board** snaps it back to its active page. (The normal display loop would restore it on its own too.) Live tests are blocked while silence mode is active or the board is paused, so a quiet-hours board stays quiet.

## Troubleshooting

### Nothing animates — the whole board just changes at once

Most often this is a Cloud API board with a built-in strategy selected. Built-in strategies are a Local API feature. Either switch the board to the Local API (see [API Keys](/docs/setup/api-keys)), or use a transition plugin, which works on any connection.

Note-array boards do not support built-in strategies at all.

### No Transition Lab in the sidebar, and no plugins in the transition pickers

Plugin transitions stay hidden until the beta is on. Enable **Settings → Advanced → Beta Features → Transition Plugins** — the Transition Lab and the plugin entries appear immediately. Built-in strategies do not need the beta flag; they are always listed in Settings and in the page editor's **Transition** dropdown.

### A plugin transition looks choppy or slower than the preview

The preview runs entirely in FiestaBoard; a live run sends every frame to the board and is limited by the board's send pacing. Increasing the plugin's frame interval usually looks better than fighting for a faster one. This is a known limitation of animating a physical split-flap over an API.

### Step Interval and Step Size seem to do nothing

They only apply to built-in strategies. Transition plugins pace themselves through their own settings — for example Typewriter's `chars_per_frame` and `frame_interval_ms`.

### A transition endpoint returns 404

The `/transitions/*` API endpoints are gated behind the beta flag and respond `404` while it is off. See [API Endpoints](/docs/reference/api-endpoints#transition-plugin-endpoints).

## Next Steps

- [Page Editor](/docs/features/page-editor) - Set a per-page transition while you build a page
- [Plugin Development Guide](/docs/development/plugin-guide) - Build your own transition plugin
- [API Endpoints](/docs/reference/api-endpoints) - Drive transitions from the REST API
