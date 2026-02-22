# Stardate Plugin Setup

The Stardate plugin requires no API keys or external services. It works out of the box!

## Configuration

The plugin has one optional setting:

### Timezone (Optional)

Set the timezone for calculating the current date. This affects which day is used for the stardate calculation.

- **Default**: `America/Los_Angeles`
- **Format**: IANA timezone name (e.g., `America/New_York`, `Europe/London`, `Asia/Tokyo`)

## Configuration Example

In your board configuration:

```json
{
  "stardate": {
    "enabled": true,
    "timezone": "America/Los_Angeles"
  }
}
```

## Using in Templates

The plugin provides a single variable:

- `{{stardate}}` - The current TNG-era stardate (e.g., `-296854.8`)

### Example Template

```
──────────────────────
    STARDATE
  {{stardate}}
──────────────────────
```

### Sample Output

```
──────────────────────
    STARDATE
   -296854.8
──────────────────────
```

## Understanding Negative Stardates

You'll notice the stardate is **negative**. This is correct!

According to Star Trek: The Next Generation canon:
- **Stardate 0** = January 1, 2323
- **TNG Season 1** (2364) = Stardate 41xxx
- **Present day** (2026) = Stardate -296xxx

We're living approximately **297 years before stardate 0**, so negative values are accurate to the Star Trek timeline.

When the year 2323 arrives, stardates will reach 0. By 2364, they'll be at 41xxx, matching the TNG era!

## Troubleshooting

### Invalid Timezone Error

If you see a timezone error, verify you're using a valid IANA timezone name. You can find a list at:
https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

### Wrong Date

If the stardate seems incorrect for your location, check your timezone setting. The stardate is calculated based on the current date in your configured timezone.
