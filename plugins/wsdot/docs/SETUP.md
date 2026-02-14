# WSDOT Ferries Setup Guide

Display Washington State Ferries schedules, vessel names, car spots remaining, and alerts on your FiestaBoard.

## What You Get

- Today's scheduled departure times (both directions for each route)
- Actual departure times when available
- Ferry names (Wenatchee, Tacoma, etc.) per sailing
- Number of car spots remaining for upcoming sailings
- Terminal wait times and service alerts

## Prerequisites

- A **free** WSDOT API Access Code (no payment required)

## Quick Setup

### 1. Get Your API Access Code

1. Go to [WSDOT Traveler Information API](https://www.wsdot.wa.gov/traffic/api/)
2. Find the line: *"To use WSDL services you must be assigned an Access Code. Please enter your email address to receive your code."*
3. Enter your email and submit. WSDOT will email you an API Access Code.
4. Copy the code (you will paste it into FiestaBoard).

### 2. Find Ferry Route IDs

The plugin needs one or more **route IDs** (numbers). You can get them from the WSF API or use these common ones:

| Route | Route ID |
|-------|----------|
| Seattle – Bainbridge Island | 1 |
| Seattle – Bremerton | 2 |
| Fauntleroy – Vashon – Southworth | 3 |
| Point Defiance – Tahlequah | 4 |
| Anacortes – San Juan Islands | 5 |
| Anacortes – Sidney B.C. | 6 |
| Mukilteo – Clinton | 7 |
| Port Townsend – Keystone | 8 |
| Edmonds – Kingston | 9 |

To see the current list for today, call (after you have an access code):

`https://www.wsdot.wa.gov/Ferries/API/Schedule/rest/routes/YYYY-MM-DD?apiaccesscode=YOUR_CODE`

Use the date for today in `YYYY-MM-DD` format. The response lists routes with their IDs.

### 3. Configure the Plugin

In the FiestaBoard web UI:

1. Go to **Integrations** and enable **WSDOT**.
2. Click **Configure**.
3. Enter your **WSDOT API Access Code** (from step 1).
4. Add one or more **Ferry Routes**:
   - For each route, set **Route ID** to one of the numbers in the table (e.g. `7` for Mukilteo–Clinton).
5. Optionally set **Refresh Interval** (default 120 seconds; minimum 60).
6. Click **Save**.

### 4. Use in Templates

Available variables (use the `wsdot` plugin key in your template):

- `{wsdot.formatted}` – One-line summary for the first route
- `{wsdot.route_count}` – Number of routes
- `{wsdot.has_alerts}` – Whether there are alerts
- `{wsdot.routes}` – Array of routes; each has `route_name`, `formatted`, `departures_ab`, `departures_ba`, `wait_time_minutes`, etc.
- `{wsdot.alerts}` – Array of alerts with `headline` and `alert_text`

Example (simple):

```
{wsdot.formatted}
```

Example (loop routes):

```
{% for route in wsdot.routes %}
{{ route.route_name }}: {{ route.formatted }}
{% endfor %}
```

## Configuration Reference

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| API Access Code | string | Yes | Free code from WSDOT (email registration) |
| Ferry Routes | array | Yes | Up to 4 items, each with `route_id` (integer) |
| Refresh Interval | integer | No | Seconds between fetches (default 120, min 60) |

## Environment Variable

You can set the API access code via environment variable instead of the UI:

- `WSDOT_API_ACCESS_CODE` – Your WSDOT API access code

If both are set, the UI value is used when the plugin runs.

## Troubleshooting

**Plugin shows "Not Available"**

- Ensure your API Access Code is correct and that you’ve enabled the plugin.
- Check that at least one route is configured with a valid `route_id`.

**No departures or "No data" for a route**

- Confirm the route runs today (some routes are seasonal or have different schedules).
- Verify the route ID: call the `/routes/{date}` endpoint (see step 2) to see valid IDs for that date.

**Data not updating**

- Increase the refresh interval if you hit rate limits, or decrease it for more frequent updates (minimum 60 seconds).

## API Limits

WSDOT provides the API for free. Use a reasonable refresh interval (e.g. 120 seconds) to avoid excessive requests.

## Support

- WSDOT Traveler API: [https://www.wsdot.wa.gov/traffic/api/](https://www.wsdot.wa.gov/traffic/api/)
- FiestaBoard: [GitHub](https://github.com/FiestaBoard/FiestaBoard)
