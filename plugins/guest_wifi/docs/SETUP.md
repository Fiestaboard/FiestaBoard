# Guest WiFi Display Setup

This feature displays your guest WiFi credentials on the board, making it easy for guests to connect. When enabled, it takes **highest priority** and overrides all other displays.

## Quick Toggle

### Enable Guest WiFi Display

Edit your `.env` file:

```bash
GUEST_WIFI_ENABLED=true
GUEST_WIFI_SSID=YourGuestNetwork
GUEST_WIFI_PASSWORD=YourPassword
```

Then restart the service:
```bash
docker-compose restart
```

### Disable Guest WiFi Display

Edit your `.env` file:

```bash
GUEST_WIFI_ENABLED=false
```

Then restart the service:
```bash
docker-compose restart
```

## Configuration

### Required Settings

- `GUEST_WIFI_ENABLED`: Set to `true` to enable, `false` to disable
- `GUEST_WIFI_SSID`: Your guest WiFi network name
- `GUEST_WIFI_PASSWORD`: Your guest WiFi password

## Display Format

![Guest WiFi Display](./guest-wifi-display.png)

When enabled, the board will show:

```
Guest WiFi

SSID: YourGuestNetwork
Password: YourPassword
```

## Priority System

The display priority is:

1. **Guest WiFi** - Can be set as active page
2. **Weather + DateTime** - Can be set as active page

## Use Cases

### When Guests Arrive

1. Enable guest WiFi display:
   ```bash
   # Edit .env
   GUEST_WIFI_ENABLED=true
   GUEST_WIFI_SSID=GuestNetwork
   GUEST_WIFI_PASSWORD=Welcome123!
   ```

2. Restart service:
   ```bash
   docker-compose restart
   ```

3. Board immediately shows WiFi credentials

### When Guests Leave

1. Disable guest WiFi display:
   ```bash
   # Edit .env
   GUEST_WIFI_ENABLED=false
   ```

2. Restart service:
   ```bash
   docker-compose restart
   ```

3. Board returns to normal display (weather, music, etc.)

## Quick Toggle Script

You can create a simple script to toggle guest WiFi:

```bash
#!/bin/bash
# toggle_guest_wifi.sh

ENV_FILE="/path/to/.env"

if grep -q "GUEST_WIFI_ENABLED=true" "$ENV_FILE"; then
    # Disable
    sed -i '' 's/GUEST_WIFI_ENABLED=true/GUEST_WIFI_ENABLED=false/' "$ENV_FILE"
    echo "Guest WiFi disabled"
else
    # Enable
    sed -i '' 's/GUEST_WIFI_ENABLED=false/GUEST_WIFI_ENABLED=true/' "$ENV_FILE"
    echo "Guest WiFi enabled"
fi

# Restart service
docker-compose restart
```

## Security Considerations

⚠️ **Important Security Notes:**

1. **Password Visibility**: The password is displayed in plain text on the board
2. **Network Access**: Anyone who can see the board can see the credentials
3. **Best Practices**:
   - Use a separate guest network (recommended)
   - Change the guest WiFi password regularly
   - Only enable when guests are present
   - Consider using a QR code generator for more secure sharing (future enhancement)

## Troubleshooting

### Guest WiFi Not Displaying

1. **Check configuration:**
   ```bash
   grep GUEST_WIFI .env
   ```

2. **Verify enabled:**
   ```bash
   # Should show: GUEST_WIFI_ENABLED=true
   ```

3. **Check logs:**
   ```bash
   docker-compose logs | grep -i "guest\|wifi"
   ```

4. **Verify SSID and password are set:**
   ```bash
   # Both must be non-empty
   ```

### Display Shows Wrong Information

1. **Update .env file** with correct SSID/password
2. **Restart service:**
   ```bash
   docker-compose restart
   ```

### Can't Toggle On/Off

1. **Check .env file syntax** - no extra spaces or quotes
2. **Restart service** after changes
3. **Check logs** for configuration errors

## Future Enhancements

Potential improvements:
- QR code generation for WiFi credentials
- Scheduled enable/disable (e.g., enable on weekends)
- Multiple guest networks support
- Temporary password generation
- Webhook/API endpoint to toggle remotely

## Example .env Configuration

```bash
# Guest WiFi Configuration
GUEST_WIFI_ENABLED=true
GUEST_WIFI_SSID=GuestNetwork-5G
GUEST_WIFI_PASSWORD=Welcome2024!
```

