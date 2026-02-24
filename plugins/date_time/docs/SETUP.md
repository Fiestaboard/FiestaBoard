# Date & Time Plugin Setup Guide

The Date & Time plugin displays the current date and time on your board with comprehensive formatting options. This is one of the simplest plugins - no API key required!

![Date & Time Display](./date-time-display.png)

## Overview

**What it does:**
- Displays current time in 12-hour or 24-hour format
- Shows current date in multiple formats (ISO, US format)
- Day of the week (full name)
- Month in various formats (full name, abbreviation, number)
- Timezone-aware with configurable timezone
- All date components available separately (day, month, year)

**Prerequisites:**
- ✅ None - works out of the box!

## Quick Setup

### 1. Enable the Plugin

In the FiestaBoard web UI:
1. Go to **Integrations**
2. Find **Date & Time** and toggle it **On**

That's it! The plugin is ready to use.

### 2. Configure Timezone (Optional)

The default timezone is `America/Los_Angeles`. To change it:

**Via Web UI (Recommended):**
1. Go to **Integrations** → **Date & Time**
2. Click the **Configure** button
3. In the **Timezone** field:
   - Start typing to see autocomplete suggestions
   - Use arrow keys (↑↓) to navigate through options
   - Press Enter to select
   - Invalid timezones will show an error message
4. Click **Save Changes**

**Via Environment Variable:**
```bash
TIMEZONE=America/New_York
```

### 3. Use in Templates

The plugin provides a comprehensive set of template variables:

#### Time Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.time}}` | 24-hour format | `14:30` |
| `{{date_time.time_24h}}` | 24-hour format (explicit) | `14:30` |
| `{{date_time.time_12h}}` | 12-hour format with AM/PM | `2:30 PM` |
| `{{date_time.hour}}` | Hour (0-23) | `14` |
| `{{date_time.minute}}` | Minute (00-59) | `30` |

#### Date Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.date}}` | ISO format | `2025-01-15` |
| `{{date_time.date_us}}` | US format MM/DD/YYYY | `01/15/2025` |
| `{{date_time.date_us_short}}` | US format MM/DD/YY | `01/15/25` |
| `{{date_time.datetime}}` | Full datetime | `2025-01-15 14:30` |

#### Day Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.day_of_week}}` | Full day name | `Wednesday` |
| `{{date_time.day}}` | Day of month (1-31) | `15` |

#### Month Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.month}}` | Full month name | `January` |
| `{{date_time.month_abbr}}` | 3-letter abbreviation | `Jan` |
| `{{date_time.month_number}}` | Month number (1-12) | `1` |
| `{{date_time.month_number_padded}}` | Month number (01-12) | `01` |

#### Year Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.year}}` | Current year | `2025` |

#### Timezone Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{{date_time.timezone}}` | Full timezone name | `America/Los_Angeles` |
| `{{date_time.timezone_abbr}}` | Timezone abbreviation | `PST` |

## Example Templates

### Simple 24-Hour Clock

```
{center}{{date_time.time_24h}}
```

### Simple 12-Hour Clock

```
{center}{{date_time.time_12h}}
```

### Full Date Display

```
{center}{{date_time.day_of_week}}
{{date_time.date}}
{{date_time.time_12h}}
```

### US Date Format

```
{center}{{date_time.date_us}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Classic Format

```
{center}{{date_time.month}} {{date_time.day}}, {{date_time.year}}
{{date_time.time_12h}} {{date_time.timezone_abbr}}
```

### Compact Format

```
{center}{{date_time.month_abbr}} {{date_time.day}}
{{date_time.time_12h}}
```

### Date Components

```
{center}{{date_time.month_number_padded}}/{{date_time.day}}/{{date_time.year}}
{{date_time.day_of_week}}
```

## Timezone Reference

Common timezone values (use the autocomplete picker in the UI for the full list):

- `America/Los_Angeles` - Pacific Time (default)
- `America/Denver` - Mountain Time
- `America/Chicago` - Central Time
- `America/New_York` - Eastern Time
- `Europe/London` - UK Time
- `Europe/Paris` - Central European Time
- `Asia/Tokyo` - Japan Time
- `Australia/Sydney` - Australian Eastern Time

For a complete list, see [IANA Time Zone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).

## Timezone Picker Features

The timezone configuration field includes:

- **Autocomplete**: Type to filter timezones in real-time
- **Arrow Key Navigation**: Use ↑↓ keys to navigate through filtered results
- **Enter to Select**: Press Enter to select the highlighted timezone
- **Validation**: Shows error message if an invalid timezone is entered
- **Keyboard Shortcuts**: Escape to close dropdown, Enter to select

## Troubleshooting

**Issue: Wrong time displayed**
- Check your timezone setting is correct
- Ensure the timezone string is valid (case-sensitive)
- Use the autocomplete picker to ensure you're using a valid IANA timezone

**Issue: Time not updating**
- Verify the plugin is enabled in Integrations
- Check that your page template includes date_time variables
- Ensure the board refresh interval is configured

**Issue: Invalid timezone error**
- Make sure you're using a valid IANA timezone name
- Use the autocomplete picker to select from the list of valid timezones
- Check for typos in the timezone string
