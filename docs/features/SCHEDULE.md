# Schedule Feature

## Overview

The Schedule feature allows you to automate page rotation based on time and day of the week. Instead of manually selecting which page displays on your FiestaBoard, you can create a schedule that automatically switches pages at specified times.

## Features

### Time-Based Rotation
- Schedule pages to display at specific times
- 15-minute time granularity (9:00 AM, 9:15 AM, 9:30 AM, etc.)
- Times displayed in browser's local timezone

### Day Patterns
- **All Days**: Schedule applies every day
- **Weekdays**: Monday through Friday only
- **Weekends**: Saturday and Sunday only
- **Custom**: Select specific days of the week

### Schedule Validation
- **Overlap Detection**: Automatically detects when multiple schedules conflict for the same time slot
- **Gap Detection**: Identifies periods where no schedule is active
- **Real-time Feedback**: Visual warnings shown when conflicts or gaps are detected

### Default Page
- Set a default page to display during schedule gaps
- Helps ensure your board always shows content
- Optional - can be left unset if you prefer gaps

## How It Works

### Schedule Mode

The system has two modes:

1. **Manual Mode** (default): You manually select which page displays
2. **Schedule Mode**: The system automatically shows pages based on your schedule

Toggle between modes on the Schedule page.

### Active Page Resolution

When Schedule Mode is enabled:

1. System checks current time and day
2. Finds all enabled schedules that match current time/day
3. If multiple matches (shouldn't happen with validation), uses most recently created
4. If no match, displays the default page
5. If no match and no default page, shows a warning

The system checks for schedule updates at your configured refresh interval (default: 300 seconds), so page switches may be delayed by up to one refresh cycle.

## Known Limitations

### 1. Midnight Boundary

**Supported**: Schedules can span midnight (e.g., 23:00-01:00). When the end time is earlier than the start time, the system treats it as a midnight rollover and handles it automatically.

### 2. Timezone Handling

**Current Behavior**: 
- Schedule times are stored in 24-hour `HH:MM` format without timezone
- UI displays times in browser's local timezone
- Backend uses server's local time for matching

**Implication**: If you access the UI from different timezones, the displayed times are always in your browser's timezone, but the schedule executes based on the server's timezone.

**Best Practice**: Set up schedules from a device in the same timezone as your FiestaBoard server.

### 3. Switch Delay

**Limitation**: Pages switch up to one refresh interval after the scheduled time (default interval: 300 seconds)

**Why**: The display service checks at the configured refresh interval to balance responsiveness with server load

**Example**: With default 300-second refresh, a schedule set for `09:00:00` might not switch until the next refresh cycle (e.g. up to ~5 minutes later)

**Status**: This is acceptable for most use cases (digital signage, dashboards)

### 4. Real-Time Sync

**Limitation**: Changes to schedules on one device don't immediately appear on other devices

**Why**: React Query caching - each client has its own cache with 60-second refetch interval

**Workaround**: Refresh the page on other devices, or wait up to 60 seconds for automatic refresh

### 5. Performance with Many Schedules

**Tested**: Up to ~20 schedules perform well

**Theoretical Limit**: Gap detection algorithm loops through all days × all schedules

**Recommendation**: Keep schedules under 50 total entries for optimal performance

**Future**: May optimize gap detection with better algorithms if needed

## Testing Coverage

### Backend (92% coverage, 68 tests)
- Time validation and parsing
- Day pattern matching
- Active page resolution at various times
- Overlap detection across all scenarios
- Gap detection
- CRUD operations
- Storage persistence

### Frontend (Manual testing only)
- Form validation - manually tested
- UI flows - manually tested
- Real-time switching - needs integration test
- E2E tests - not yet implemented

### Known Testing Gaps
1. No E2E tests for full user flows
2. No automated tests for schedule switching at exact times
3. No performance benchmarks for many schedules
4. No timezone edge case testing

## API Reference

### Endpoints

```
GET    /schedules              # List all schedules
POST   /schedules              # Create schedule
GET    /schedules/{id}         # Get schedule by ID
PUT    /schedules/{id}         # Update schedule
DELETE /schedules/{id}         # Delete schedule
GET    /schedules/active/page  # Get current active page ID
GET    /schedules/validate     # Get overlap/gap validation
GET    /schedules/default-page # Get default page ID
POST   /schedules/default-page # Set default page ID
GET    /schedules/enabled      # Check if schedule mode enabled
POST   /schedules/enabled      # Enable/disable schedule mode
```

### Models

#### ScheduleEntry
```python
{
  "id": str,              # Unique identifier
  "page_id": str,         # Page to display
  "start_time": str,      # HH:MM format (e.g., "09:00")
  "end_time": str,        # HH:MM format, exclusive (e.g., "17:00")
  "day_pattern": str,     # "all" | "weekdays" | "weekends" | "custom"
  "custom_days": [str],   # ["monday", "tuesday", ...] if pattern is "custom"
  "enabled": bool,        # Whether schedule is active
  "created_at": str,      # ISO timestamp
  "updated_at": str       # ISO timestamp
}
```

#### ScheduleValidationResult
```python
{
  "overlaps": [
    {
      "schedule1_id": str,
      "schedule2_id": str,
      "conflict_description": str
    }
  ],
  "gaps": [
    {
      "day": str,           # "monday", "tuesday", etc.
      "start_time": str,    # HH:MM
      "end_time": str       # HH:MM
    }
  ]
}
```

## Best Practices

### 1. Start Simple
Begin with a few schedules covering major time blocks (morning, afternoon, evening) rather than trying to fill every minute.

### 2. Use Default Page
Always set a default page to handle gaps, especially during initial setup.

### 3. Check Validation
After creating schedules, review the validation warnings on the Schedule page to catch overlaps or unexpected gaps.

### 4. Test Before Enabling
Create your schedules in Manual Mode first, then switch to Schedule Mode once you're confident they're correct.

### 5. Monitor First Day
Watch your board for the first full day after enabling schedules to ensure pages switch as expected.

### 6. Keep It Consistent
Use consistent day patterns (e.g., all weekday schedules use same times) for easier maintenance.

## Troubleshooting

### Page Not Switching

**Check**:
1. Is Schedule Mode enabled? (Toggle on Schedule page)
2. Is the schedule enabled? (Individual schedule toggle)
3. Does the current time/day match the schedule?
4. Are there overlapping schedules causing conflicts?
5. Wait up to 60 seconds for the next poll

### "Schedule gap" Warning

**Cause**: No schedule matches current time, and no default page is set

**Fix**: 
- Set a default page, or
- Create schedules to cover the gap

### Overlapping Schedules

**Cause**: Two or more schedules are active at the same time/day

**Fix**: Edit schedules to remove time overlap, or disable one schedule

### Wrong Timezone

**Cause**: Browser timezone doesn't match server timezone

**Fix**: Access UI from a device in the same timezone as the FiestaBoard

## Future Enhancements

Potential improvements for future versions:

- [ ] Explicit timezone selection in settings
- [ ] Real-time schedule switching (WebSocket updates)
- [ ] Calendar view for visualizing schedules
- [ ] Schedule templates (e.g., "Business hours", "24/7")
- [ ] Recurring exceptions (e.g., "Skip holidays")
- [ ] Schedule history and analytics
- [ ] Bulk edit operations
- [ ] Import/export schedules
- [ ] Multi-board schedule sync

## Related Documentation

- [Plugin Development](../development/PLUGIN_DEVELOPMENT.md) - Create data sources for pages
- [Local Development](../setup/LOCAL_DEVELOPMENT.md) - Set up development environment
