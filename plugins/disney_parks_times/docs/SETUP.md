# Disney Park Queue Times – Setup Guide

Show live wait times for Disney parks and rides on your board. No API key required.

## Requirements

- None. The plugin uses the free [Queue-Times.com](https://queue-times.com/) API. You must keep the “Powered by Queue-Times.com” attribution visible when using the default display (the plugin adds it automatically).

## Configuration

1. Open the **Integrations** page in the FiestaBoard web UI.
2. Find **Disney Park Queue Times** and turn it **On**.
3. Open the plugin settings (click the plugin or the settings icon).
4. Under **Parks and rides**:
   - Click **Add park**.
   - Choose a **park** from the dropdown (e.g. Disneyland, Magic Kingdom). Only Disney parks are listed; names are shown, not IDs.
   - Use **Add ride…** to pick which rides to show. Again, only names are shown.
   - Add more parks if you want; for each park, select the rides you care about.
5. Optionally set **Refresh interval (seconds)** (default 300). Queue-Times updates about every 5 minutes, so shorter intervals won’t get newer data from the API.
6. Save.

## Supported Parks

The picker lists only Disney parks from Queue-Times (Walt Disney Attractions), including:

- Disneyland (California)
- Disney California Adventure
- Magic Kingdom, Epcot, Hollywood Studios, Animal Kingdom (Walt Disney World)
- Disneyland Paris, Walt Disney Studios Paris
- Tokyo Disneyland, Tokyo DisneySea
- Hong Kong Disneyland
- Shanghai Disney Resort

Ride lists are loaded when you select a park; pick the rides you want to display by name.

## Troubleshooting

- **No parks or rides in dropdowns** – The app fetches lists from the FiestaBoard API (which proxies Queue-Times). Ensure the API is reachable and not blocked.
- **“Failed to fetch parks/rides”** – The Queue-Times service may be temporarily unavailable. Try again later.
- **Wait times show 0 or “Closed”** – Data comes directly from Queue-Times; the plugin does not modify it. Parks may show 0 during off-hours or maintenance.

## Attribution

This plugin uses data from [Queue-Times.com](https://queue-times.com/). The default display includes “Queue-Times.com” on the board. If you build a custom template, please keep attribution visible where possible.
