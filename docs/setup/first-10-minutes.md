---
sidebar_position: 3
description: "Your first 10 minutes with FiestaBoard: create a page, enable plugins, and set up a schedule for your split-flap display."
keywords: [FiestaBoard getting started, first page, enable plugins, setup walkthrough, Vestaboard tutorial]
---

# Your First 10 Minutes

You've got FiestaBoard running at **http://localhost:4420** and your board is connected. Now what? This guide walks you through everything you can do in your first 10 minutes to get the most out of your board.

## 1. Verify the Display Service

The display service starts automatically when the container is running. Open the dashboard at **http://localhost:4420** and verify the status shows **Running**.

## 2. Enable Your First Plugins

Plugins are data sources - they pull information like weather, time, stock prices, and more so you can put that data on your board.

1. Click **Integrations** in the navigation
2. You'll see all available plugins. Start by enabling a few that need no API key:

| Plugin | What It Shows |
|--------|--------------|
| **Date & Time** | Current date and time in various formats |
| **Star Trek Quotes** | Random quotes from TNG, Voyager, and DS9 |
| **Visual Clock** | A large pixel-art clock that fills the whole board |
| **Sun Art** | A full-screen art pattern that changes with the sun's position |
| **Disney Parks** | Current wait times for Disney park rides |
| **Surf Conditions** | Wave height and quality at popular surf spots |
| **Guest WiFi** | Your WiFi network name and password |

1. Toggle each plugin **on** to enable it
2. For Guest WiFi, enter your WiFi network name and password when prompted

:::tip
You can always come back and enable more plugins later, including ones that need API keys (weather, traffic, stocks, etc.). The Integrations page links to setup instructions for each one.
:::

<ThemedScreenshot src="/img/guides/integrations-full.png" alt="Integrations page showing all plugins with toggle switches" />

<ThemedScreenshot src="/img/guides/integrations-plugin-config.png" alt="Plugin settings modal for Weather plugin configuration" />

## 3. Create Your First Page

Pages are the templates for what your board displays. Each page is a layout you design using the visual editor.

1. Click **Pages** in the navigation
2. Select the tab matching your board type (**Flagship** for the standard 22x6 board, **Note** for the compact 15x3)
3. Click **New**
4. Give your page a name (e.g., "Morning Info")

<ThemedScreenshot src="/img/guides/page-editor-grid.png" alt="Empty page editor grid matching board dimensions" />

### Type some static text

The editor shows a grid matching your board's dimensions. Click on a row and start typing. The preview shows exactly how it will look on your board.

### Add live data from plugins

This is where it gets fun. Click the **Variables** button in the editor toolbar. You'll see a list of all the variables available from your enabled plugins.

For example, if you enabled the Date & Time plugin, you'll see variables like:

- `{date_time.datetime}` - Inserts the current date and time
- `{date_time.date}` - Inserts just the date
- `{date_time.time}` - Inserts just the time

Click any variable to insert it into your page at the cursor position. When the page is displayed on your board, the variable is automatically replaced with live data.

<ThemedScreenshot src="/img/guides/page-editor-variable-picker-open.png" alt="Variable Picker dropdown open showing available plugin variables" />

<ThemedScreenshot src="/img/guides/page-editor-with-variables.png" alt="Page editor with template variables inserted into the grid" />

### Example: A simple morning page

Here's a page layout you could create using Date & Time and Star Trek Quotes:

```text
  GOOD MORNING
  {date_time.date}
  {date_time.time}

  {star_trek_quotes.quote}
```

### Save your page

Click **Save** when you're happy with your layout. Your page is now stored and ready to use.

## 4. Display Your Page

Back on the Pages list, select your new page to make it the active page. Within about 60 seconds (or however long your refresh interval is), your board will update with the content from your page.

<ThemedScreenshot src="/img/guides/page-editor-preview.png" alt="Page editor with live board preview showing rendered content" />

## 5. Try a Plugin-Only Page

Some plugins fill the entire board with formatted content. These are great for "set it and forget it" displays:

- **Visual Clock** - A large, attractive clock display
- **Sun Art** - An art pattern that changes throughout the day
- **Surf Conditions** - Full surf report with wave height and conditions

To use these, create a new page and insert just the plugin's main variable (e.g., `{visual_clock.display}` or `{sun_art.display}`). The plugin handles the entire layout.

## 6. Set Up a Schedule (Optional)

Instead of manually switching between pages, you can have FiestaBoard automatically change pages based on the time of day.

1. Click **Schedule** in the navigation
2. Toggle **Schedule Mode** on
3. Click to create a new schedule entry
4. Choose:
   - **Which page** to display
   - **Start time** and **end time**
   - **Which days** (every day, weekdays, weekends, or specific days)
5. Repeat for other time slots

### Example schedule for a home board

| Time | Page | Days |
|------|------|------|
| 7:00 AM - 9:00 AM | Morning Info (weather + commute) | Weekdays |
| 9:00 AM - 5:00 PM | Visual Clock | Weekdays |
| 5:00 PM - 10:00 PM | Evening (stocks + sports) | Weekdays |
| All day | Fun (Star Trek quotes + surf) | Weekends |

:::tip Set a default page
In Schedule settings, you can set a **default page** that displays whenever there's a gap in your schedule. This way your board always shows something.
:::

<ThemedScreenshot src="/img/guides/schedule-calendar-populated.png" alt="Schedule calendar with multiple time-based entries" />

## 7. Set Quiet Hours (Optional)

Split-flap displays can be noisy when they flip. If your board is in a bedroom or living room, you'll want to set quiet hours:

1. Go to **Settings**
2. Find the **Silence Schedule** section
3. Set a start time (e.g., 10:00 PM) and end time (e.g., 7:00 AM)
4. Save

During quiet hours, FiestaBoard stops sending updates to the board. Whatever was last displayed stays on the board until quiet hours end.

<ThemedScreenshot src="/img/guides/settings-silence-schedule.png" alt="Settings page Silence Schedule section for configuring quiet hours" />

## What's Next?

Now that you have the basics down, here are some things to explore:

### Add more data sources

Head to the **Integrations** page and set up plugins that need API keys. These are the most popular:

- **[Weather](/docs/plugins/weather)** - Free API key from weatherapi.com (1 million calls/month free)
- **[Stocks](/docs/plugins/configuration)** - Works without an API key; optional Finnhub key for better search
- **[Sports Scores](/docs/plugins/sports-scores)** - Works without an API key
- **[Traffic](/docs/plugins/traffic)** - Requires a Google Routes API key (free tier available)

### Design more pages

Create pages for different moods and times of day. Mix and match plugin variables to build exactly what you want. The [Page Editor guide](/docs/features/page-editor) covers colors, alignment, and advanced formatting.

### Explore all the features

- **[Color Guide](/docs/reference/color-guide)** - Add colored tiles to your pages
- **[Character Codes](/docs/reference/character-codes)** - Special characters available on the board
- **[Schedule Mode](/docs/features/schedule)** - Advanced scheduling with day patterns
- **[All Plugins](/docs/plugins/overview)** - Full list of all 50+ plugins
