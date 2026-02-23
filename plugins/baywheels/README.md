# Bay Wheels Plugin

![Bay Wheels Display](./docs/baywheels-display.png)

Display Bay Wheels bike share availability with electric and classic bike counts.

**→ [Setup Guide](./docs/SETUP.md)** - Configuration and station setup

## Overview

The Bay Wheels plugin fetches real-time bike availability from the Bay Wheels GBFS feed, showing electric and classic bike counts at your selected stations.

## Features

- Electric and classic bike counts
- Multiple station monitoring
- Color-coded availability status
- Aggregate statistics
- No API key required!

## Template Variables

### Primary Station (First)

```
{{baywheels.electric_bikes}}      # Electric bikes available
{{baywheels.classic_bikes}}       # Classic bikes available
{{baywheels.num_bikes_available}} # Total bikes
{{baywheels.station_name}}        # Station name
{{baywheels.is_renting}}          # "Yes" or "No"
{{baywheels.status_color}}        # Color tile
```

### Aggregate Stats

```
{{baywheels.total_electric}}      # Total e-bikes across all stations
{{baywheels.total_classic}}       # Total classic bikes
{{baywheels.total_bikes}}         # Total all bikes
{{baywheels.station_count}}       # Number of tracked stations
```

### Best Station

```
{{baywheels.best_station_name}}     # Name of station with most e-bikes
{{baywheels.best_station_electric}} # E-bike count at best station
```

### Individual Stations (Array)

```
{{baywheels.stations.0.station_name}}    # First station name
{{baywheels.stations.0.electric_bikes}}  # First station e-bikes
{{baywheels.stations.0.classic_bikes}}   # First station classic
{{baywheels.stations.0.status_color}}    # First station color

{{baywheels.stations.1.station_name}}    # Second station name
{{baywheels.stations.1.electric_bikes}}  # Second station e-bikes
```

## Example Templates

### Single Station

```
{center}BAY WHEELS
{{baywheels.station_name}}
Electric: {{baywheels.electric_bikes}}
Classic: {{baywheels.classic_bikes}}
```

### Multiple Stations

```
{center}BIKES NEARBY
{{baywheels.stations.0.station_name}}: {{baywheels.stations.0.electric_bikes}}E
{{baywheels.stations.1.station_name}}: {{baywheels.stations.1.electric_bikes}}E
{{baywheels.stations.2.station_name}}: {{baywheels.stations.2.electric_bikes}}E
TOTAL: {{baywheels.total_electric}}E
```

### With Color

```
{center}BAY WHEELS
{{baywheels.stations.0.status_color}} {{baywheels.stations.0.station_name}}
E:{{baywheels.stations.0.electric_bikes}} C:{{baywheels.stations.0.classic_bikes}}
```

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| enabled | boolean | false | Enable/disable the plugin |
| station_ids | array | - | Bay Wheels station IDs to monitor |
| refresh_seconds | integer | 60 | Update interval |

## Finding Station IDs

Use the station search feature in the UI to find stations near you by address or coordinates.

## Color Indicators

- **Green**: > 5 electric bikes
- **Yellow**: 2-5 electric bikes
- **Red**: < 2 electric bikes

## Author

FiestaBoard Team

