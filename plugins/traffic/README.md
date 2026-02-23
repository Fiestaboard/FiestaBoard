# Traffic Plugin

![Traffic Display](./docs/traffic-display.png)

Display commute times and traffic conditions using Google Routes API.

**→ [Setup Guide](./docs/SETUP.md)** - API key registration and route configuration

## Overview

The Traffic plugin fetches real-time commute times from Google Routes API, showing drive times with traffic delays for multiple routes.

## Features

- Real-time drive time estimates
- Traffic delay calculations
- Multiple route monitoring
- Color-coded traffic status

## Quick Setup

For detailed setup instructions including API key registration, see the **[Setup Guide](./docs/SETUP.md)**.

## Template Variables

### Primary Route (First)

```
{{traffic.duration_minutes}}  # Total drive time (e.g., "25")
{{traffic.delay_minutes}}     # Delay due to traffic (e.g., "5")
{{traffic.traffic_status}}    # LIGHT, MODERATE, or HEAVY
{{traffic.traffic_color}}     # Color tile
{{traffic.destination_name}}  # Display name (e.g., "WORK")
{{traffic.formatted}}         # Pre-formatted line
```

### Aggregates

```
{{traffic.route_count}}       # Number of routes
{{traffic.worst_delay}}       # Longest delay (minutes)
```

### Individual Routes (Array)

```
{{traffic.routes.0.destination_name}}   # First route name
{{traffic.routes.0.duration_minutes}}   # First route time
{{traffic.routes.0.delay_minutes}}      # First route delay
{{traffic.routes.0.formatted}}          # First route formatted

{{traffic.routes.1.destination_name}}   # Second route name
{{traffic.routes.1.formatted}}          # Second route formatted
```

## Example Templates

### Single Route

```
{center}COMMUTE
{{traffic.destination_name}}
{{traffic.duration_minutes}} minutes
{{traffic.traffic_status}}
```

### Multiple Routes

```
{center}TRAFFIC
{{traffic.routes.0.formatted}}
{{traffic.routes.1.formatted}}
{{traffic.routes.2.formatted}}
```

### With Color

```
{center}COMMUTE
{{traffic.traffic_color}} {{traffic.destination_name}}
TIME: {{traffic.duration_minutes}}m
DELAY: +{{traffic.delay_minutes}}m
```

## Configuration

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| enabled | boolean | No | Enable/disable the plugin |
| api_key | string | Yes | Google Routes API key |
| routes | array | Yes | Routes to monitor (max 4) |
| refresh_seconds | integer | No | Update interval (default: 300) |

### Route Configuration

Each route requires:
- `origin`: Starting address or lat,lng
- `destination`: Ending address or lat,lng
- `destination_name`: Short name for display

## Traffic Status Colors

- **Green (LIGHT)**: Normal traffic
- **Yellow (MODERATE)**: 20%+ slower than normal
- **Red (HEAVY)**: 50%+ slower than normal

## Author

FiestaBoard Team

