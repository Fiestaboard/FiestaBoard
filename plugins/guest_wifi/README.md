# Guest WiFi Plugin

![Guest WiFi Display](./docs/guest-wifi-display.png)

Display guest WiFi credentials on your board.

**→ [Setup Guide](./docs/SETUP.md)** - Configuration instructions

## Overview

The Guest WiFi plugin displays your guest network name and password, making it easy for visitors to connect.

## Template Variables

```
{{guest_wifi.ssid}}       # Network name
{{guest_wifi.password}}   # Network password
```

## Example Templates

### Simple Display

```
{center}GUEST WIFI
NETWORK: {{guest_wifi.ssid}}
PASSWORD: {{guest_wifi.password}}
```

### Centered

```
{center}WIFI INFO
{center}{{guest_wifi.ssid}}
{center}{{guest_wifi.password}}
```

## Configuration

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| enabled | boolean | No | Enable/disable the plugin |
| ssid | string | Yes | Your guest WiFi network name (max 22 chars) |
| password | string | Yes | Your guest WiFi password (max 22 chars) |

## Security Note

Be mindful that the password will be visible on your board. Only use this for guest networks that you're comfortable sharing publicly.

## Author

FiestaBoard Team

