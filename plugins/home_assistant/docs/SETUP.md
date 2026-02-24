# Home Assistant Integration Setup

This guide will help you integrate your Home Assistant server to display house status on your board.

## Overview

The Home Assistant integration displays real-time status of your home's sensors and devices, such as:
- Door sensors (open/closed)
- Garage doors (open/closed)
- Locks (locked/unlocked)
- And any other Home Assistant entities

## Prerequisites

1. **Home Assistant server** running and accessible
2. **Long-lived access token** from Home Assistant
3. **Entity IDs** of the devices you want to monitor

## Step 1: Get Home Assistant Access Token

1. **Log into Home Assistant** web interface
2. Go to your **profile** (click your username in the bottom left)
3. Scroll down to **Long-lived access tokens**
4. Click **Create Token**
5. Give it a name (e.g., "FiestaBoard Display")
6. **Copy the token** - you'll need it for configuration

⚠️ **Important**: The token is only shown once. Save it securely!

## Step 2: Find Your Entity IDs

You need to find the entity IDs for the devices you want to display.

### Method 1: Via Home Assistant UI

1. Go to **Settings** → **Devices & Services**
2. Click on a device
3. Click on an entity
4. The entity ID is shown at the top (e.g., `binary_sensor.front_door`)

### Method 2: Via Developer Tools

1. Go to **Settings** → **Developer Tools** → **States**
2. Browse or search for your entities
3. Entity IDs are shown in the list

### Common Entity Types

- **Binary Sensors**: `binary_sensor.front_door`, `binary_sensor.garage_door`
- **Covers**: `cover.garage_door`, `cover.front_door`
- **Locks**: `lock.front_door`, `lock.back_door`
- **Sensors**: `sensor.temperature`, `sensor.humidity`

## Step 3: Configure the Service

Edit your `.env` file:

```bash
# Home Assistant Configuration
HOME_ASSISTANT_ENABLED=true
HOME_ASSISTANT_BASE_URL=http://192.168.1.100:8123
HOME_ASSISTANT_ACCESS_TOKEN=your_long_lived_access_token_here
HOME_ASSISTANT_ENTITIES=[{"entity_id": "binary_sensor.front_door", "name": "Front Door"}, {"entity_id": "cover.garage_door", "name": "Garage"}]
HOME_ASSISTANT_TIMEOUT=5
HOME_ASSISTANT_REFRESH_SECONDS=30
```

### Configuration Options

- `HOME_ASSISTANT_ENABLED`: Set to `true` to enable
- `HOME_ASSISTANT_BASE_URL`: Your Home Assistant URL (e.g., `http://192.168.1.100:8123`)
- `HOME_ASSISTANT_ACCESS_TOKEN`: Your long-lived access token
- `HOME_ASSISTANT_ENTITIES`: JSON array of entities to monitor
  - Each entity needs `entity_id` and `name`
  - `name` is what will be displayed on board
- `HOME_ASSISTANT_TIMEOUT`: API request timeout (default: 5 seconds)
- `HOME_ASSISTANT_REFRESH_SECONDS`: How often to check status (default: 30 seconds)

### Entity Configuration Format

The `HOME_ASSISTANT_ENTITIES` is a JSON array. Example:

```json
[
  {"entity_id": "binary_sensor.front_door", "name": "Front Door"},
  {"entity_id": "cover.garage_door", "name": "Garage"},
  {"entity_id": "lock.back_door", "name": "Back Door"},
  {"entity_id": "binary_sensor.window_living_room", "name": "Living Room Window"}
]
```

**In .env file** (all on one line, no line breaks):
```bash
HOME_ASSISTANT_ENTITIES=[{"entity_id": "binary_sensor.front_door", "name": "Front Door"}, {"entity_id": "cover.garage_door", "name": "Garage"}]
```

## Step 4: Test Connection

Before deploying, test the connection:

```python
# Test script
import requests

base_url = "http://192.168.1.100:8123"
token = "your_token_here"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# Test API connection
response = requests.get(f"{base_url}/api/", headers=headers)
print(f"Connection: {response.status_code}")

# Test entity access
entity_id = "binary_sensor.front_door"
response = requests.get(f"{base_url}/api/states/{entity_id}", headers=headers)
print(f"Entity state: {response.json()}")
```

## Step 5: Restart Service

After configuring, restart your Docker service:

```bash
docker-compose restart
docker-compose logs -f | grep -i "home\|assistant"
```

## Display Format

![Home Assistant Display](./home-assistant-display.png)

The board will show:

```
House Status
Front Door: closed [G]
Garage: open [R]
Back Door: locked [G]
```

### Status Indicators

- `[G]` = Green/Good (closed, locked, secure)
- `[R]` = Red/Attention (open, unlocked, needs attention)
- `[?]` = Unknown/Unavailable

### State Mapping

The system automatically maps states:

- **Binary Sensors**: `on` = [R], `off` = [G]
- **Covers**: `open` = [R], `closed` = [G]
- **Locks**: `unlocked` = [R], `locked` = [G]

## Priority System

Display priority order:

1. **Guest WiFi** (highest) - When enabled
2. **Home Assistant** - Can be set as active page
3. **Weather + DateTime** - Can be set as active page

You can select which page is active from the Pages UI.

## Troubleshooting

### "Connection test failed"

1. **Check Home Assistant URL:**
   ```bash
   curl http://192.168.1.100:8123/api/
   ```

2. **Verify access token:**
   - Make sure token is correct
   - Check token hasn't expired
   - Verify token has proper permissions

3. **Check network connectivity:**
   - Can Docker container reach Home Assistant?
   - Is Home Assistant firewall blocking requests?

### "Entity not found" or "unavailable"

1. **Verify entity ID:**
   - Check entity exists in Home Assistant
   - Use Developer Tools → States to verify

2. **Check entity type:**
   - Some entities may need different state interpretation
   - Check entity attributes in Home Assistant

3. **Test entity directly:**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
        http://192.168.1.100:8123/api/states/binary_sensor.front_door
   ```

### Status shows wrong state

1. **Check entity state in Home Assistant:**
   - Go to Developer Tools → States
   - Verify actual state value

2. **State mapping:**
   - The system maps common states automatically
   - Unusual states may show as `[?]`

### Display not updating

1. **Check refresh interval:**
   - Default is 30 seconds
   - Increase if needed: `HOME_ASSISTANT_REFRESH_SECONDS=60`

2. **Check logs:**
   ```bash
   docker-compose logs | grep -i "home\|assistant"
   ```

3. **Set as active page:**
   - Go to Pages in the web UI
   - Select your Home Assistant page as active
   - Content will refresh automatically

## Advanced Configuration

### Multiple Entities

You can monitor as many entities as you want (within the 6-row limit):

```json
[
  {"entity_id": "binary_sensor.front_door", "name": "Front Door"},
  {"entity_id": "binary_sensor.back_door", "name": "Back Door"},
  {"entity_id": "cover.garage_door", "name": "Garage"},
  {"entity_id": "lock.front_door", "name": "Front Lock"},
  {"entity_id": "binary_sensor.window_1", "name": "Window 1"},
  {"entity_id": "binary_sensor.window_2", "name": "Window 2"}
]
```

### Custom Names

Use friendly names for display:

```json
[
  {"entity_id": "binary_sensor.front_door", "name": "Front Door"},
  {"entity_id": "cover.garage_door", "name": "Garage Door"},
  {"entity_id": "lock.back_door", "name": "Back Door Lock"}
]
```

### Different Refresh Rates

Adjust refresh rate based on your needs:

- **Fast updates**: `HOME_ASSISTANT_REFRESH_SECONDS=10` (every 10 seconds)
- **Normal**: `HOME_ASSISTANT_REFRESH_SECONDS=30` (every 30 seconds)
- **Slow**: `HOME_ASSISTANT_REFRESH_SECONDS=60` (every minute)

## Security Notes

⚠️ **Important Security Considerations:**

1. **Access Token**: Keep your long-lived access token secure
2. **Network**: Consider using HTTPS if Home Assistant supports it
3. **Permissions**: The token should have read-only access to states
4. **Firewall**: Restrict access to Home Assistant API if possible

## Example Configuration

Complete example `.env` configuration:

```bash
# Home Assistant Configuration
HOME_ASSISTANT_ENABLED=true
HOME_ASSISTANT_BASE_URL=http://192.168.1.100:8123
HOME_ASSISTANT_ACCESS_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGc...
HOME_ASSISTANT_ENTITIES=[{"entity_id": "binary_sensor.front_door", "name": "Front Door"}, {"entity_id": "cover.garage_door", "name": "Garage"}, {"entity_id": "lock.back_door", "name": "Back Door"}]
HOME_ASSISTANT_TIMEOUT=5
HOME_ASSISTANT_REFRESH_SECONDS=30
```

## Next Steps

Once configured:
- ✅ Monitor logs to verify connection
- ✅ Check board for house status display
- ✅ Adjust entity list as needed
- ✅ Fine-tune refresh rates

## References

- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)
- [Home Assistant Long-lived Access Tokens](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-tokens)

