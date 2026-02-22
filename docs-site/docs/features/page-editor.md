---
sidebar_position: 1
description: "Use FiestaBoard's WYSIWYG page editor to create and design custom content for your split-flap display."
keywords: [FiestaBoard page editor, WYSIWYG, display content, custom pages, split-flap editor, Vestaboard editor]
---

# Page Editor

FiestaBoard's WYSIWYG page editor lets you create and edit board display pages with a visual editor that shows exactly how content will appear on your split-flap display.

## Overview

The page editor is the core of FiestaBoard's content creation experience. It provides a real-time preview of your board layout, template variable insertion, and color formatting—all in a visual interface.

![Page Editor](/img/page-editor-wysiwyg.png)

## Creating a New Page

1. Open the FiestaBoard Web UI at `http://localhost:3000`
2. Navigate to the **Pages** section
3. Click **New Page**
4. Give your page a name
5. Use the editor to compose your content
6. Click **Save**

## Using Template Variables

Template variables let you insert live data from your enabled plugins into any page. Variables are automatically replaced with real-time data when the page is displayed.

### Inserting Variables

1. In the page editor, click the **Variable Picker** button
2. Browse available variables grouped by plugin
3. Click a variable to insert it at the cursor position

### Variable Types

| Type | Description | Example |
|------|-------------|---------|
| **Simple** | Single value replacement | `{weather.temperature}` → `72°F` |
| **Array** | Multi-line data | `{stocks.prices}` → formatted stock rows |

### Example Variables

Here are some commonly used template variables:

- `{weather.temperature}` — Current temperature
- `{weather.conditions}` — Weather conditions (Sunny, Cloudy, etc.)
- `{stocks.prices}` — Stock price display
- `{date_time.current}` — Current date and time
- `{muni.arrivals}` — Transit arrival times

## Working with Colors

The split-flap display supports colored tiles using special character codes. You can use these in the editor to add visual emphasis to your pages.

| Code | Color | Common Use |
|------|-------|------------|
| `{63}` | 🟥 Red | Alerts, high temperatures |
| `{64}` | 🟧 Orange | Warm temperatures |
| `{65}` | 🟨 Yellow | Comfortable, warnings |
| `{66}` | 🟩 Green | Good status, success |
| `{67}` | 🟦 Blue | Cold temperatures, info |
| `{68}` | 🟪 Violet | Very cold, accents |
| `{69}` | ⬜ White | Backgrounds |
| `{70}` | ⬛ Black | Backgrounds |

See the [Color Guide](/docs/reference/color-guide) for detailed usage examples.

## Page Layout

The board display is a grid of **6 rows × 22 columns** (132 characters total). The editor reflects this layout so you can see exactly how your content will be positioned.

### Tips for Good Layouts

- **Keep text concise** — You have limited characters per row
- **Use alignment** — Center important information for readability
- **Mix data sources** — Combine multiple plugin variables on one page
- **Test with preview** — Use the live preview to check formatting before saving

## Managing Pages

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

## Next Steps

- [Schedule Mode](/docs/features/schedule) — Automate when pages are displayed
- [Plugins Overview](/docs/plugins/overview) — See available data sources for your pages
- [Color Guide](/docs/reference/color-guide) — Learn about color formatting options
