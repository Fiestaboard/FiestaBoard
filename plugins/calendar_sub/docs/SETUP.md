# Calendar Subscription Setup Guide

Subscribe to any public iCalendar (.ics) URL and get automatic board alerts before your events start.

## Overview

The Calendar Subscription plugin connects to a public `.ics` calendar feed and displays upcoming events on your Vestaboard. It can also automatically interrupt the board display a configurable number of minutes before each event to show an alert.

**Prerequisites:**
- A public iCalendar subscription URL (`.ics` or `webcal://`) from Google Calendar, Outlook, Apple Calendar, a school/organization website, or any other iCalendar-compatible calendar service
- No API key required

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI, go to **Integrations**, find **Calendar Subscription**, and click **Enable**.

### 2. Configure

Click **Configure** and fill in:

- **Calendar URL** — Paste your `.ics` or `webcal://` URL (see "Getting Your Calendar URL" below)
- **Minutes Before Event** — How early to show the board alert (e.g., `15` for 15 minutes before)
- **Display Duration** — How long the alert stays on screen; set `0` to keep it until the next scheduled page
- **Timezone** — Your local IANA timezone (e.g., `America/New_York`, `America/Los_Angeles`)

### 3. Add a Template

Go to **Pages** and create a page using the Calendar Subscription plugin. A simple template:

```
UPCOMING EVENT
{{event_name}}

{{event_start_date}}  {{event_start}}
{{event_location}}
IN {{minutes_until}} MIN
```

### 4. View Your Board

Events from your calendar will appear on the board, and the alert will automatically trigger when an event is approaching.

---

## Getting Your Calendar URL

### Google Calendar

1. Go to [calendar.google.com](https://calendar.google.com)
2. Click the three-dot menu next to the calendar you want to share
3. Select **Settings and sharing**
4. Scroll to **Integrate calendar**
5. Copy the **Public address in iCal format** (ends in `.ics`)

> The calendar must be set to **public** for the subscription URL to work.

### Outlook / Microsoft 365

1. Go to [outlook.com](https://outlook.com) or your Microsoft 365 calendar
2. Click **Settings** → **View all Outlook settings** → **Calendar** → **Shared calendars**
3. Under **Publish a calendar**, choose your calendar and set permissions to **Can view all details**
4. Click **Publish** and copy the **ICS** link

### Apple Calendar (iCloud)

1. Open Calendar on Mac
2. Right-click (Control-click) a calendar and choose **Get Info** or **Share Calendar**
3. Enable **Public Calendar** and copy the URL
4. Change `webcal://` to `https://` if needed (FiestaBoard handles this automatically)

### School / Organization Calendars

Many schools and organizations publish calendar feeds directly. Look for links labeled:
- "Subscribe to calendar"
- "iCal feed"
- "Add to calendar" → right-click the button and copy the link URL
- A URL ending in `.ics`

---

## Template Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{event_name}}` | Next event name | `Parent Teacher Conf` |
| `{{event_start}}` | Start time | `3:30 PM` |
| `{{event_start_date}}` | Start date | `Apr 3` |
| `{{event_end}}` | End time | `4:30 PM` |
| `{{event_location}}` | Event location | `Room 204` |
| `{{event_description}}` | Description (truncated) | `Bring report card` |
| `{{minutes_until}}` | Minutes until event | `10` |
| `{{is_now}}` | Event in progress now | `false` |
| `{{event_count}}` | Number of upcoming events | `3` |
| `{{events[0].name}}` | First event name | `Weekly Standup` |
| `{{events[0].start}}` | First event start time | `9:00 AM` |
| `{{events[0].start_date}}` | First event date | `Apr 7` |

## Configuration Reference

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| `calendar_url` | Public .ics or webcal:// URL | Required | — |
| `minutes_before` | Minutes before event to trigger | `15` | 1–1440 |
| `display_duration_minutes` | Trigger display duration (0 = indefinite) | `0` | 0–120 |
| `timezone` | IANA timezone name | `America/Los_Angeles` | any valid IANA zone |
| `max_events` | Max upcoming events to load | `5` | 1–20 |
| `refresh_seconds` | Re-fetch interval in seconds | `300` | 60+ |

### Environment Variables

You can optionally set the calendar URL via environment variable instead of the UI:

| Variable | Description |
|----------|-------------|
| `CALENDAR_SUB_URL` | Calendar subscription URL |
| `TIMEZONE` | Default timezone |

---

## Troubleshooting

**No events showing up**
- Make sure the calendar URL is publicly accessible (not behind a login)
- Verify the URL ends in `.ics` or starts with `webcal://`
- Check that the calendar has events in the next 30 days
- Try pasting the URL directly in a browser — you should see iCalendar text

**Events are in the wrong timezone**
- Set the **Timezone** setting to match your local timezone
- All-day events always show as "All Day" regardless of timezone

**Trigger not firing**
- Check that **Minutes Before Event** is set to a value greater than 0
- The trigger fires within the configured window before each event starts
- Events that are already past will not trigger

**"Calendar URL is required" error**
- Make sure the URL field is not empty
- The URL must start with `http://`, `https://`, or `webcal://`

**Calendar not updating**
- The plugin re-fetches the calendar based on **Refresh Interval** (default: every 5 minutes)
- Reduce the interval if you need more frequent updates (minimum: 60 seconds)
- Note that the calendar host may also cache updates for some time
