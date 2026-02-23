# Home Assistant Plugin

![Home Assistant Display](./docs/home-assistant-display.png)

Display entity states from your Home Assistant instance.

**→ [Setup Guide](./docs/SETUP.md)** - Access token setup and configuration

## Overview

The Home Assistant plugin connects to your Home Assistant instance and allows you to display any entity state on your board. It supports dynamic entity access, so you can reference any entity by its ID.

## Features

- Connect to any Home Assistant instance
- Display any entity state
- Dynamic entity access in templates
- Support for sensors, binary sensors, switches, and more
- Configurable entity list

## Quick Setup

For detailed setup instructions including access token creation, see the **[Setup Guide](./docs/SETUP.md)**.

## Template Variables

### Status

```
{{home_assistant.connected}}      # "Yes" or connection status
{{home_assistant.entity_count}}   # Number of entities
```

### Dynamic Entity Access

Access ANY entity using its full entity_id:

```
{{home_assistant.sensor.temperature.state}}
{{home_assistant.binary_sensor.front_door.state}}
{{home_assistant.light.living_room.state}}
{{home_assistant.switch.fan.state}}
{{home_assistant.climate.thermostat.state}}
```

### Configured Entities

If you configure entities with display names:

```
{{home_assistant.entities.Temperature.state}}
{{home_assistant.entities.Front Door.state}}
```

## Example Templates

### Basic Sensors

```
{center}HOME STATUS
Temp: {{home_assistant.sensor.temperature.state}}°
Door: {{home_assistant.binary_sensor.front_door.state}}
Lights: {{home_assistant.light.living_room.state}}
```

### Smart Home Dashboard

```
{center}HOME
Indoor: {{home_assistant.sensor.indoor_temp.state}}°
Outdoor: {{home_assistant.sensor.outdoor_temp.state}}°
Garage: {{home_assistant.cover.garage_door.state}}
Alarm: {{home_assistant.alarm_control_panel.home.state}}
```

### Door/Window Status

```
{center}SECURITY
Front: {{home_assistant.binary_sensor.front_door.state}}
Back: {{home_assistant.binary_sensor.back_door.state}}
Garage: {{home_assistant.binary_sensor.garage.state}}
Windows: {{home_assistant.binary_sensor.windows.state}}
```

## Configuration

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| enabled | boolean | No | Enable/disable the plugin |
| base_url | string | Yes | HA URL (e.g., http://192.168.1.100:8123) |
| access_token | string | Yes | Long-lived access token |
| entities | array | No | Specific entities to monitor |
| timeout | integer | No | Request timeout (default: 5) |
| refresh_seconds | integer | No | Update interval (default: 30) |

### Entity Configuration

Configure specific entities with friendly names:

```json
{
  "entities": [
    {"entity_id": "sensor.temperature", "name": "Temp"},
    {"entity_id": "binary_sensor.front_door", "name": "Front"}
  ]
}
```

## Entity States

Common entity state values:

| Entity Type | States |
|------------|--------|
| binary_sensor | on, off |
| sensor | numeric or text value |
| light | on, off |
| switch | on, off |
| cover | open, closed, opening, closing |
| lock | locked, unlocked |
| climate | heat, cool, auto, off |

## Color Rules

You can apply colors based on entity states:

- **on** → Green
- **off** → Red
- **open** → Orange
- **closed** → Green
- **unavailable** → Red

## Security Notes

- Access token should be kept secure
- Use HTTPS when possible for external access
- Token has full API access - treat it like a password

## Troubleshooting

### Connection Failed

1. Verify Home Assistant URL is correct
2. Check network connectivity
3. Ensure port is open (usually 8123)
4. Verify access token is valid

### Entity Not Found

1. Check entity_id spelling exactly
2. Verify entity exists in HA Developer Tools → States
3. Some entities may be hidden by default

## Author

FiestaBoard Team

