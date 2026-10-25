---
sidebar_position: 1
description: "Use FiestaBoard's WYSIWYG page editor to create and design custom content for your split-flap display, with optional AI-assisted page drafting."
keywords: [FiestaBoard page editor, WYSIWYG, display content, custom pages, split-flap editor, Vestaboard editor, Vestaboard AI, AI page generation, LLM page drafts]
---

# Page Editor

FiestaBoard's WYSIWYG page editor lets you create and edit board display pages with a visual editor that shows exactly how content will appear on your split-flap display.

## Overview

The page editor is the core of FiestaBoard's content creation experience. It provides a real-time preview of your board layout, template variable insertion, and color formatting, all in a visual interface.

<AppShot name="page-editor-wysiwyg" alt="Page Editor" />

## Device Types

FiestaBoard supports multiple Vestaboard devices with different display sizes:

| Device | Dimensions | Total Characters |
|--------|-----------|------------------|
| **Flagship** | 6 rows × 22 columns | 132 |
| **Note** | 3 rows × 15 columns | 45 |

Pages are device-specific. The **Pages** section has **Flagship** and **Note** tabs to organize pages by device type. The editor and live preview automatically adapt to the selected device's dimensions.

:::tip
The Vestaboard Note supports a heart character (❤) at code 62, which displays as a degree symbol (°) on the Flagship.
:::

## Creating a New Page

1. Open the FiestaBoard Web UI at `http://localhost:4420`
2. Navigate to the **Pages** section
3. Select the **Flagship** or **Note** tab for your target device
4. Click **New**
5. Give your page a name
6. Use the editor to compose your content (dimensions match your target device)
7. Click **Save**

## Using Template Variables

Template variables let you insert live data from your enabled plugins into any page. Variables are automatically replaced with real-time data when the page is displayed.

### Inserting Variables

1. In the page editor, click the **Variables** button
2. Browse available variables grouped by plugin
3. Click a variable to insert it at the cursor position

<AppShot name="page-editor-variable-picker-open" alt="Variable Picker dropdown showing available plugin variables" />

### Variable Types

| Type | Description | Example |
|------|-------------|---------|
| **Simple** | Single value replacement | `{{weather.temperature}}` → `72°F` |
| **Array** | Multi-line data | `{{stocks.prices}}` → formatted stock rows |

### Example Variables

Here are some commonly used template variables:

- `{{weather.temperature}}` - Current temperature
- `{{weather.condition}}` - Weather conditions (Sunny, Cloudy, etc.)
- `{{stocks.prices}}` - Stock price display
- `{{date_time.datetime}}` - Current date and time
- `{{muni.formatted}}` - Transit arrival times

### Inline Formulas (`{{= ... }}`)

For anything beyond a plain value — `IF` / `ELSE`, comparisons, math, string
manipulation, conditional colors — FiestaBoard supports an Excel-style
formula language inside `{{= ... }}` blocks:

```text
{{= IF(weather.temperature > 80, "HOT", "OK") }}
{{= IF(stocks.AAPL.change >= 0, COLOR("green"), COLOR("red")) }} AAPL
```

Formulas also handle the two things plain variables can't:

```text
{{= COUNT(mlb.games) }} GAMES
{{= FOREACH(mlb.games, item.team1 & " " & item.score1, 4) }}
{{= DATEDIFF(TODAY(), DATE(launch.day)) }} DAYS TO GO
```

When a plugin gives you a **list** — today's games, the next departures — use
`COUNT` and `FOREACH` rather than writing one line per possible item.
`FOREACH` returns one board row per item and fills the rows below it, so leave
those rows empty and give it a limit that fits.

See the [Template Formulas reference](/docs/reference/template-formulas) for
the complete syntax, function list, and recipes.

## AI Assistant (optional)

FiestaBoard includes **FiestaBot**, an AI chat assistant that can draft
and edit board pages through natural conversation. Click **AI Assistant**
in the sidebar (the Sparkles icon) to open the panel.

<AppShot name="ai-chat-panel" alt="FiestaBot AI chat panel open alongside the page editor" />

FiestaBoard ships **without any bundled LLM credentials**. You bring
your own provider, your own API key, and your own model list. Two
wire-format protocols are supported out of the box:

- **OpenAI-compatible** chat completions — works with OpenRouter,
  OpenAI, DeepSeek, Mistral, Together AI, Fireworks AI, Ollama,
  LM Studio, vLLM, llama.cpp, and most other local servers.
- **Anthropic Messages API** — direct Claude access via
  `api.anthropic.com`.

### How it works

1. Click **AI Assistant** in the sidebar to open the FiestaBot panel.
2. Type a description of what you want — for example, *"Build a weather
   and transit page for my morning commute"* or *"Replace line 2 with
   today's date"*.
3. FiestaBot shows its work: each action appears in the panel as it
   runs, and the app takes you to the page, schedule or setting it is
   changing so you can watch the values land.
4. Continue the conversation to refine the result, ask questions, or
   request a completely different layout. When a request is ambiguous
   FiestaBot asks first.
5. Anything that cannot be undone — deleting a page or schedule,
   uninstalling a plugin — waits for your **Approve**. **Stop** ends a
   turn at any point.

When a page is open in the editor, FiestaBot automatically has context
of what you're working on — no need to attach anything manually. The
panel is also available from any other section of the app, where it can
answer questions about plugins, variables, and FiestaBoard features.

### What FiestaBot can do

- **Create and edit pages** — draft full template layouts or make
  targeted edits (change a line, add a variable, adjust alignment).
- **Suggest variables** — recommend which plugin variables to use for
  a given goal and explain what they do.
- **Install plugins** — recommend and install a plugin from the registry
  when it's needed for what you're building.
- **Configure settings** — update display, polling, location, or silence
  schedule settings on your behalf.
- **Create and edit schedules and collections** — build automation around
  the pages you create.
- **Everything the MCP server can do** — FiestaBot uses the same tools an
  external MCP client (Claude Desktop, Claude Code) would, so there is one
  set of capabilities, not two.

### Setup

The **AI Assistant** item only appears in the sidebar after you've
configured at least one provider in **Settings → AI Providers**. See the
[AI Providers setup guide](/docs/setup/ai-providers) for the full
walkthrough, recommended models, and a privacy note covering exactly
what FiestaBoard sends to your provider.

## Working with Colors

The split-flap display supports colored tiles using special character codes. You can use these in the editor to add visual emphasis to your pages.

<AppShot name="page-editor-colors" alt="Page editor showing color codes in use" />

| Code | Color | Common Use |
|------|-------|------------|
| `{{63}}` | 🟥 Red | Alerts, high temperatures |
| `{{64}}` | 🟧 Orange | Warm temperatures |
| `{{65}}` | 🟨 Yellow | Comfortable, warnings |
| `{{66}}` | 🟩 Green | Good status, success |
| `{{67}}` | 🟦 Blue | Cold temperatures, info |
| `{{68}}` | 🟪 Violet | Very cold, accents |
| `{{69}}` | ⬜ White | Backgrounds |
| `{{70}}` | ⬛ Black | Backgrounds |

See the [Color Guide](/docs/reference/color-guide) for detailed usage examples.

## Page Transitions

The editor's header toolbar has a **Transition** dropdown that controls how the board animates when it changes to this page.

- **Use the display's transition** - inherit the transition set for the display the page is sent to, in **Displays → (a display) → Transition**
- A **built-in strategy** (Wave, Drift, Curtain, Row, Diagonal, Random) - performed by the board itself, Local API only
- A **transition plugin** (Typewriter, Simple Dissolve, and others) - animated by FiestaBoard, shown only when the Transition Plugins beta is enabled; a Cloud API board shows the new message at once

Anything other than **Use the display's transition** becomes a page-level override that applies whenever this page is sent, on any display. Switching back to **Use the display's transition** clears it.

See [Transitions](/docs/features/transitions) for how the two kinds differ and what they require. Transition plugins are deprecated; pages that use one keep working.

## Page Layout

The board display dimensions depend on the target device:

- **Flagship**: 6 rows × 22 columns (132 characters)
- **Note**: 3 rows × 15 columns (45 characters)

The editor reflects the target device's layout so you can see exactly how your content will be positioned.

### Tips for Good Layouts

- **Keep text concise** - You have limited characters per row (22 for Flagship, 15 for Note)
- **Use alignment** - Center important information for readability
- **Mix data sources** - Combine multiple plugin variables on one page
- **Test with preview** - Use the live preview to check formatting before saving
- **Design per device** - Create separate pages optimized for each device's dimensions

## Managing Pages

<AppShot name="pages-list" alt="Pages list view with Flagship and Note tabs" />

### Editing Existing Pages

1. Go to the **Pages** section
2. Click on any page to open it in the editor
3. Make your changes
4. Click **Save**

### Deleting Pages

1. Go to the **Pages** section
2. Click the delete option on the page you want to remove
3. Confirm the deletion

:::tip
Pages that are referenced in schedules should be updated or removed from the schedule before deleting.
:::

### Saving what another app put on the board

When another app writes to a display, for example the Vestaboard app, the
Divoom app, or a script, FiestaBoard notices and puts your page back on its
next update. You don't have to do anything.

If you share a display with another app on purpose, turn off **Restore
automatically** in that display's settings under **Displays**, next to
**Pause sends**. FiestaBoard then leaves the other app's content alone until
you tap **Restore** or your page changes. The setting is on for every display
unless you turn it off. Turn it off as well if another app or script keeps
writing to the display on purpose: with it on, FiestaBoard takes the display
back every time.

FiestaBoard puts back what it would show right now: the scheduled page, a
timed message, or the page you picked. A message you sent from FiestaBoard by
hand that another app then wrote over comes back as that page, not as the
message.

#### How FiestaBoard notices

- **Vestaboard:** FiestaBoard reads the board back on a timer (every 30
  seconds for a board on your network, every 3 minutes for a cloud board). It
  counts a change as another app's after two reads in a row show it.
- **Divoom Pixoo:** a Pixoo can't report what it's showing, but it does count
  the pictures sent to it. When that count moves past FiestaBoard's own,
  another app uploaded a picture. When the count goes back down, the Pixoo
  restarted or another app reset the count before uploading, which most Pixoo
  scripts do. FiestaBoard can't tell those two apart, so it always sends your
  page again, even with **Restore automatically** off.

Some changes don't show up on a Pixoo. If an app switches the Pixoo to another
channel, such as its clock, without uploading a picture, FiestaBoard can't
tell, so no notice appears. The same goes for an upload that happens to leave
the count where FiestaBoard left it. Whether the Divoom app's own uploads move
the count hasn't been confirmed yet. Call the restore endpoint (see
[Using the API](#using-the-api)) to put your page back.

#### The notice

When a Vestaboard shows something FiestaBoard did not send, a notice appears
above the board preview on **Home** and on that display's own page under
**Displays**:

> **Another app changed this board**
> FiestaBoard will replace it the next time your page updates. Save it to keep it.

- **Save as page** saves exactly what is on the board as a new template page,
  sized for that display. The page is named after the date and time, for
  example "Saved from board Oct 17, 2026, 11:42 PM", in your app language. The
  button then reads **Saved as "…"** with an **Open page** link, so you can
  rename or edit the page right away, and a second tap cannot save it twice.
- **Restore** sends that display's page to it again, over what the other app
  wrote. Your other displays are left alone, and Restore doesn't change which
  page is selected or cancel a timed message.

With **Restore automatically** off, the notice stays until you tap **Restore**
or your page changes. A Pixoo with **Restore automatically** off gets a notice
too, but without a preview, because FiestaBoard can't see what's on it. It has
a **Restore** button.

Restore does not send anything while the display is paused. The notice says
so before you tap it, and if you tap it anyway, FiestaBoard tells you that
nothing was sent and why, instead of reporting success. While silence mode is
on for a display, the notice is hidden: FiestaBoard is leaving that board alone
on purpose, and the notice comes back when silence ends if the other app's
content is still there. Automatic restore also leaves paused and silenced
displays alone.

After FiestaBoard has put your page back, the other app's content is no
longer on the board, but you can still keep it. A quieter notice stays:

> **Another app wrote to this board at 11:42 PM**
> FiestaBoard has since put your page back. You can still save what the other app wrote.

Use **Save as page** to keep it, or **Dismiss** to forget it. The notice stays
until you save or dismiss it, or for 24 hours at most. Restoring your page
from the first notice also dismisses it.

#### Using the API

`POST /v1/boards/{board}/restore` does the same thing as **Restore**: it
restores only that display, and doesn't change the selected page or cancel a
timed message. A paused or silenced display gets a `409` response and nothing
is sent. A `sent: true` response means the display accepted the write.
`device_observed` is always `false`: FiestaBoard doesn't confirm what the
screen shows, so look at the display to check.

To turn automatic restore off or on, send `PATCH /v1/boards/{board}` with
`{"auto_restore": false}` or `{"auto_restore": true}`. `GET /v1/boards/{board}`
reports the current value as `auto_restore`. You can also ask the in-app
assistant to change it. See the [API reference](../reference/api-endpoints.md)
for details.

:::note
FiestaBoard confirms another app's write on its second board read in a row,
so a write that FiestaBoard paints over within about one minute (about six
minutes for a cloud board) is not kept. Paused displays and FiestaPanel TV
displays are not read back: a FiestaPanel always shows exactly what
FiestaBoard sent.
:::

## Next Steps

- [Transitions](/docs/features/transitions) - Choose how the board animates into this page
- [Schedule Mode](/docs/features/schedule) - Automate when pages are displayed
- [Plugin Directory](/plugins) - See available data sources for your pages
- [Color Guide](/docs/reference/color-guide) - Learn about color formatting options
