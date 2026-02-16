---
sidebar_position: 7
description: "Show real-time public transit arrivals including SF Muni on your split-flap display with FiestaBoard."
keywords: [FiestaBoard transit plugin, SF Muni, public transit, bus arrivals, train times, split-flap transit]
---

# Transit Plugins

FiestaBoard includes several transit-focused plugins for tracking public transportation.

## SF Muni Transit

Display San Francisco Muni bus and rail arrival predictions.

### Setup

1. Register for a free API key at [511.org](https://511.org/open-data/token)
2. Add to `.env`:

```bash
MUNI_API_KEY=your_511_api_key_here
```

3. Enable the Muni plugin in the Web UI **Integrations** page
4. Configure your stops and routes

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{muni.arrivals}` | Formatted arrival times | `N JUDAH 5 12 MIN` |

### Features

- Multi-line, multi-route support
- Real-time arrival predictions
- Configurable stop selection

---

## WSDOT Ferries

Display Washington State Ferry schedules, vessel names, car availability, and alerts.

### Setup

1. Request a free API key at [wsdot.wa.gov/traffic/api](https://wsdot.wa.gov/traffic/api/)
2. Add to `.env`:

```bash
WSDOT_API_KEY=your_wsdot_key_here
```

3. Enable the WSDOT plugin in the Web UI
4. Select your ferry route

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{wsdot.schedule}` | Ferry schedule display | `BAINBRIDGE 3:20 PM` |

### Features

- Departure times and vessel names
- Car spot availability
- Service alerts

---

## Bay Wheels

Track Bay Area bike share (Lyft) availability at nearby stations. **No API key required.**

### Setup

1. Enable the Bay Wheels plugin in the Web UI
2. Configure your preferred station

### Available Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `{baywheels.availability}` | Bike availability | `EBIKES 5 CLASSIC 3` |

### Features

- E-bike and classic bike counts
- Real-time station availability
- No authentication required

---

## Example Transit Page

Combine multiple transit plugins on a single page:

```
┌──────────────────────┐
│  TRANSIT             │
│  N JUDAH   5  12 MIN │
│  38 GEARY  3   8 MIN │
│  EBIKES  5  CLASSIC 3│
│  FERRY BAINBRIDGE    │
│  DEPARTS    3:20 PM  │
└──────────────────────┘
```

## Next Steps

- [Plugins Overview](/docs/plugins/overview) — See all available plugins
- [API Keys](/docs/setup/api-keys) — Getting transit API keys
