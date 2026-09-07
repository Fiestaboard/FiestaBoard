---
sidebar_position: 2
description: "Configure FiestaBoard's schedule mode to automatically rotate pages on your split-flap display at set times."
keywords: [FiestaBoard schedule, page rotation, timed display, auto rotate, scheduled content, Vestaboard scheduler]
---

# Schedule Mode

FiestaBoard's schedule mode lets you automate which pages display on your board at different times and days. Use the visual calendar interface to set up time-based page rotation.

## Overview

The schedule feature provides a visual calendar where you can assign pages to specific time slots throughout the week. This is perfect for:

- Showing weather in the morning and stocks during market hours
- Displaying transit times during your commute
- Showing fun content like Star Trek quotes on weekends
- Setting a default "home" page for unscheduled times

<AppShot name="schedule-calendar" alt="Schedule Calendar" />

## Creating a Schedule Entry

1. Open the FiestaBoard Web UI at `http://localhost:4420`
2. Navigate to the **Schedule** page
3. Click to create a new schedule entry
4. Configure the entry:
   - **Page** - Select which page to display
   - **Start Time** - When the page should start showing
   - **End Time** - When the page should stop showing
   - **Days** - Which days this schedule applies to

<AppShot name="schedule-entry-form" alt="Schedule entry form with page, time, and day selection" />

### Day Patterns

| Pattern | Days |
|---------|------|
| **All Days** | Monday through Sunday |
| **Weekdays** | Monday through Friday |
| **Weekends** | Saturday and Sunday |
| **Custom** | Select individual days |

### Time Granularity

Schedule times are set in **15-minute increments** and displayed in your local timezone.

## Calendar and List Views

The schedule page offers two views:

### Calendar View

The calendar view provides a visual weekly overview. Each scheduled page appears as a colored block on the timeline, making it easy to see your full schedule at a glance.

### List View

The list view shows all schedule entries in a table format, which is useful for managing many entries or making quick edits.

<AppShot name="schedule-list-view" alt="Schedule list view showing entries in table format" />

## Schedule Validation

FiestaBoard automatically validates your schedule and provides real-time feedback:

- **Overlap Detection** - Warns if two schedules overlap on the same day/time
- **Gap Detection** - Shows unscheduled time periods
- **Active Page Resolution** - The system checks at your configured polling interval (default: 15 seconds) which page should be displayed based on the current time

:::info
When no schedule is active, FiestaBoard displays the default page. You can set the default page in Settings.
:::

## How Page Resolution Works

At your configured polling interval (default: 15 seconds), the display service:

1. Checks the current local time and day of week
2. Looks for enabled schedule entries that match the current time
3. If a match is found, displays that page
4. If no match is found, displays the default page

> **Note:** Schedules can cross midnight (e.g., 11 PM to 1 AM). The system handles the rollover automatically.

## Known Limitations

- **Switching delay** - There may be a delay of up to one refresh interval when switching between scheduled pages.
- **Recommended limit** - For optimal performance, keep the total number of schedule entries under 50.

## Next Steps

- [Page Editor](/docs/features/page-editor) - Create pages to use in your schedule
- [Silence Schedule](/docs/features/silence-schedule) - Set quiet hours for your board
- [Plugins Overview](/docs/plugins/overview) - Add data sources to your pages
