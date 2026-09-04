---
sidebar_position: 4
description: "Make FiestaBoard automatically discoverable by Home Assistant via MQTT Discovery. Control your board from HA automations."
keywords: [FiestaBoard Home Assistant, MQTT Discovery, home automation, smart home control, Vestaboard automation]
---

# Home Assistant Control (MQTT)

Make FiestaBoard appear as a native device in Home Assistant — control your board from HA automations and dashboards.

## Overview

This feature lets Home Assistant **automatically discover** your FiestaBoard and expose it as a controllable device. Once connected, you can:

- Turn the schedule on/off from HA
- Switch active pages from HA automations
- Navigate pages sequentially with Next/Previous page buttons
- Send messages to the board when events happen (doorbell, weather alerts, etc.)
- Blank the board or refresh the display remotely
- Change the transition animation style
- See board status, current page, version, and page count on your HA dashboard
- Start/stop the display service remotely
- Monitor device diagnostics (uptime, API mode, active plugins, last display update, output target)
- Trigger automations when the board content changes, pages switch, or settings change (via event entities)
- Track when the board was last updated via a `timestamp` sensor for HA history/statistics

**No installation needed on the Home Assistant side.** FiestaBoard uses [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) — the same protocol used by Zigbee2MQTT, Tasmota, and ESPHome — so your board appears automatically in HA.

## Prerequisites

Before setting up, you need:

1. **A running FiestaBoard instance** (v2.2+ when this feature ships)
2. **Home Assistant** with the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) enabled
3. **An MQTT broker** accessible from both FiestaBoard and Home Assistant

:::tip First time connecting?
See the [Connecting to Home Assistant via MQTT](/docs/setup/home-assistant-mqtt) guide for a step-by-step walkthrough of broker setup, HA MQTT integration configuration, and FiestaBoard configuration.
:::

### About the MQTT Broker

An MQTT broker relays messages between FiestaBoard and Home Assistant. The most common setup:

- **Mosquitto add-on** — If you run Home Assistant OS or Supervised, install the [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto) from the HA Add-on Store (Settings → Add-ons → Mosquitto broker). This is a one-click install and the most popular HA add-on.
- **Existing broker** — If you already have an MQTT broker on your network (common if you use Zigbee2MQTT, Tasmota, or other IoT devices), you can reuse it.
- **Standalone Mosquitto** — You can run Mosquitto on any machine. See the [Eclipse Mosquitto documentation](https://mosquitto.org/documentation/) for installation instructions.

:::info
Most Home Assistant users already have an MQTT broker. If you use Zigbee2MQTT, Tasmota, ESPHome, or Frigate, you already have one.
:::

## Setup

### Step 1: Enable MQTT in FiestaBoard

1. Open **FiestaBoard** at `http://<your-fiestaboard-ip>:4420`
2. Go to **Settings**
3. Find the **Home Assistant (MQTT)** section
4. Toggle **Enable MQTT** on
5. Enter your MQTT broker details:

| Setting | Description | Example |
|---------|-------------|---------|
| **Broker Host** | Hostname or IP of your MQTT broker | `192.168.1.100` or `homeassistant.local` |
| **Broker Port** | MQTT broker port (standard: 1883) | `1883` |
| **Username** | MQTT username (if broker requires auth) | `mqtt_user` |
| **Password** | MQTT password (if broker requires auth) | `mqtt_pass` |

1. Click **Save** — FiestaBoard will connect to the broker and publish discovery messages

### Step 2: Verify in Home Assistant

1. Open **Home Assistant**
2. Go to **Settings → Devices & Services → MQTT**
3. Look for a device named **FiestaBoard**
4. Click it to see all available controls and sensors

That's it. FiestaBoard is now controllable from Home Assistant.

:::tip
If FiestaBoard doesn't appear, check:

- The MQTT broker is running and reachable from both FiestaBoard and HA
- The MQTT integration is enabled in HA (Settings → Devices & Services → Add Integration → MQTT)
- FiestaBoard shows "MQTT Connected" in its Settings page

:::

## What You Get in Home Assistant

Once connected, FiestaBoard appears as a device with **24 entities** — controls, sensors, diagnostics, and events:

### Controls (you can change these from HA)

| Entity | Type | Description |
|--------|------|-------------|
| **Schedule** | Switch | Turn the FiestaBoard schedule on/off |
| **Display Service** | Switch | Start/stop the FiestaBoard display service |
| **Active Page** | Select | Choose which page to display (dynamically populated from your pages) |
| **Transition Style** | Select | Board transition animation (column, reverse-column, edges-to-center, row, diagonal, random) |
| **Send Message** | Text | Send a text message to the board (up to 132 characters) |
| **Refresh Display** | Button | Force a display refresh |
| **Blank Board** | Button | Clear the board display (all blank) |
| **Next Page** | Button | Navigate to the next page in the page list (wraps around) |
| **Previous Page** | Button | Navigate to the previous page in the page list (wraps around) |
| **Refresh Interval** | Number | Set how often the board refreshes (30–3600 seconds). *Categorized as config.* |

**Send Message formatting:** text longer than the board width word-wraps onto
the following rows automatically, sized to your board's real geometry (6 rows ×
22 columns on Flagship, 3 × 15 on Note). Width is counted in flaps, so a colour
marker like `{red}` costs one tile, not five characters. A word wider than the
board is split across rows rather than cut off. Lines beyond the board's row
count are dropped.

The text entity is single-line, so to force a line break type the literal
two-character sequence `\n` where you want the break (e.g. `TACO\nTUESDAY`) —
wrapping still fills within those breaks. If your text needs a real backslash
before an `n`, double it: `C:\\new` renders as `C:\new`. Any other backslash
(`C:\temp`) is left alone. This escape applies only to the plain-string
payload the text entity publishes; a JSON payload such as
`{"message": "TACO\nTUESDAY", "board": "Kitchen"}` can carry a real newline and
is never rewritten.

### Sensors (read-only status from FiestaBoard)

| Entity | Type | Description |
|--------|------|-------------|
| **Current Page** | Sensor | Name of the page currently displayed. *Includes JSON attributes (page_id, page_index).* |
| **Board Message** | Sensor | Summary of what's currently on the board |
| **Silence Mode** | Binary Sensor | Whether silence/quiet hours are active |
| **Page Count** | Sensor | Number of pages configured *(state_class: measurement)* |

### Diagnostics (device health and info, grouped separately in HA)

These entities are tagged with `entity_category: diagnostic` so Home Assistant groups them in the **Diagnostic** section of the device page, keeping your main dashboard clean.

| Entity | Type | Description |
|--------|------|-------------|
| **Service Status** | Binary Sensor | Whether FiestaBoard is running *(device_class: running)* |
| **Version** | Sensor | FiestaBoard software version |
| **Uptime** | Sensor | How long FiestaBoard has been running *(device_class: duration, unit: seconds)* |
| **Board API Mode** | Sensor | Whether the board is using Local API or Cloud API |
| **Active Plugins** | Sensor | Number of enabled plugins *(state_class: measurement)* |
| **Last Display Update** | Sensor | ISO timestamp of when the board content was last changed *(device_class: timestamp)* |
| **Output Target** | Sensor | Current output mode: `ui`, `board`, or `both` |

### Events (trigger automations when things happen)

FiestaBoard publishes [MQTT event entities](https://www.home-assistant.io/integrations/event.mqtt/) that let you build automations based on board activity — no polling required.

| Entity | Event Types | Description |
|--------|------------|-------------|
| **Display Updated** | `message_sent`, `page_refreshed`, `board_blanked`, `page_navigated` | Fires when the board content changes |
| **Page Changed** | `page_switched` | Fires when the active page changes |
| **Settings Changed** | `schedule_toggled`, `service_toggled`, `silence_mode_changed` | Fires when schedule, display service, or silence mode state changes |

All events include a `timestamp` field with the UTC ISO 8601 time of the event.

## Automation Examples

### Send a Welcome Home Message

When someone arrives home, display a welcome message on the board:

```yaml
automation:
  - alias: "Welcome Home Board Message"
    trigger:
      - platform: state
        entity_id: person.john
        to: "home"
    action:
      - service: text.set_value
        target:
          entity_id: text.fiestaboard_send_message
        data:
          value: "Welcome Home John!"
```

### Show Weather Page When Raining

Automatically switch to the weather page when rain is detected:

```yaml
automation:
  - alias: "Show Weather When Raining"
    trigger:
      - platform: state
        entity_id: weather.home
        attribute: condition
        to: "rainy"
    action:
      - service: select.select_option
        target:
          entity_id: select.fiestaboard_active_page
        data:
          option: "Weather Dashboard"
```

### Blank the Board at Bedtime

Clear the board at night and restart in the morning:

```yaml
automation:
  - alias: "Blank Board at Bedtime"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.fiestaboard_blank_board
  - alias: "Turn On Board in Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.fiestaboard_display_service
```

### Log Board Updates (using events)

Use the **Display Updated** event entity to log or react when the board content changes:

```yaml
automation:
  - alias: "Log Board Message Sent"
    trigger:
      - platform: state
        entity_id: event.fiestaboard_display_updated
        attribute: event_type
        to: "message_sent"
    action:
      - service: logbook.log
        data:
          name: "FiestaBoard"
          message: "A new message was sent to the board"
```

### Notify When Page Changes (using events)

Get a notification when someone switches the active page:

```yaml
automation:
  - alias: "Notify on Page Change"
    trigger:
      - platform: state
        entity_id: event.fiestaboard_page_changed
    action:
      - service: notify.mobile_app
        data:
          title: "FiestaBoard"
          message: "Page changed to {{ trigger.to_state.attributes.page_name }}"
```

### Cycle Pages Every Hour

Use the Next Page button to rotate through your pages on a schedule:

```yaml
automation:
  - alias: "Cycle Pages Hourly"
    trigger:
      - platform: time_pattern
        minutes: 0
    action:
      - service: button.press
        target:
          entity_id: button.fiestaboard_next_page
```

### React to Silence Mode Changes (using events)

Turn off smart lights when silence mode activates (e.g., at bedtime):

```yaml
automation:
  - alias: "Silence Mode Bedtime"
    trigger:
      - platform: state
        entity_id: event.fiestaboard_settings_changed
        attribute: event_type
        to: "silence_mode_changed"
    condition:
      - condition: state
        entity_id: binary_sensor.fiestaboard_silence_mode
        state: "on"
    action:
      - service: light.turn_off
        target:
          entity_id: light.living_room
```

### Display on HA Dashboard

Add FiestaBoard status and controls to your HA dashboard:

```yaml
type: entities
title: FiestaBoard
entities:
  - entity: binary_sensor.fiestaboard_service_status
  - entity: sensor.fiestaboard_current_page
  - entity: sensor.fiestaboard_board_message
  - entity: sensor.fiestaboard_page_count
  - entity: switch.fiestaboard_schedule
  - entity: switch.fiestaboard_display_service
  - entity: select.fiestaboard_active_page
  - entity: button.fiestaboard_next_page
  - entity: button.fiestaboard_previous_page
  - entity: select.fiestaboard_transition_style
  - entity: number.fiestaboard_refresh_interval
```

:::tip Diagnostics on their own card
Diagnostic entities (version, uptime, API mode, active plugins) are automatically grouped under the **Diagnostic** section on the device page in HA. You can also add them to a separate dashboard card:

```yaml
type: entities
title: FiestaBoard Diagnostics
entities:
  - entity: sensor.fiestaboard_version
  - entity: sensor.fiestaboard_uptime
  - entity: sensor.fiestaboard_board_api_mode
  - entity: sensor.fiestaboard_active_plugins
  - entity: sensor.fiestaboard_last_display_update
  - entity: sensor.fiestaboard_output_target
```

:::

## Configuration Reference

### Environment Variables

You can also configure MQTT via environment variables (useful for Docker):

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_ENABLED` | `false` | Enable MQTT integration |
| `MQTT_BROKER_HOST` | `localhost` | MQTT broker hostname or IP |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | *(empty)* | MQTT username |
| `MQTT_PASSWORD` | *(empty)* | MQTT password |
| `MQTT_DISCOVERY_PREFIX` | `homeassistant` | HA discovery topic prefix |
| `MQTT_BASE_TOPIC` | `fiestaboard` | Base topic for state and commands |
| `MQTT_INSTANCE_ID` | `fiestaboard_1` | Unique ID (for multi-board setups) |
| `FIESTABOARD_EXTERNAL_URL` | *(empty)* | URL shown as the "Visit" link on the HA device page (e.g. `http://192.168.1.50:4420`). When not set, no link appears. |

### Docker Compose Example

```yaml
services:
  fiestaboard:
    image: fiestaboard/fiestaboard:latest
    ports:
      - "4420:4420"
    environment:
      - MQTT_ENABLED=true
      - MQTT_BROKER_HOST=192.168.1.100
      - MQTT_BROKER_PORT=1883
      - MQTT_USERNAME=mqtt_user
      - MQTT_PASSWORD=mqtt_pass
      - FIESTABOARD_EXTERNAL_URL=http://192.168.1.50:4420
```

### Multiple FiestaBoards

If you have more than one FiestaBoard, give each a unique instance ID:

```env
# Living room board
MQTT_INSTANCE_ID=fiestaboard_living_room
MQTT_BASE_TOPIC=fiestaboard_living_room

# Office board
MQTT_INSTANCE_ID=fiestaboard_office
MQTT_BASE_TOPIC=fiestaboard_office
```

Each board appears as a separate device in Home Assistant.

## How It Works

FiestaBoard uses [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) — the same mechanism used by Zigbee2MQTT, Tasmota, ESPHome, and Frigate. Here's the flow:

1. FiestaBoard connects to the MQTT broker
2. It publishes **discovery messages** to topics under `homeassistant/` — these tell HA what entities to create, including entity categories (diagnostic, config) and sensor classes
3. It publishes an **availability message** (`online`) so HA knows the board is connected
4. It publishes **current state** for all entities, plus **JSON attributes** for entities that carry extra metadata (e.g., the current page's ID and index)
5. Home Assistant reads the discovery messages and **automatically creates the device** with all entities, properly categorized in the UI
6. When you interact with an entity in HA (toggle a switch, send a message), HA publishes a **command** to the MQTT broker
7. FiestaBoard receives the command, executes it, publishes the **updated state** back, and fires relevant **events** (e.g., `display_updated`, `page_changed`)

All state messages are **retained** — if HA restarts, it immediately gets the current state without waiting for a change.

FiestaBoard sets a **Last Will and Testament (LWT)** — if FiestaBoard disconnects unexpectedly, the broker automatically publishes `offline` so HA knows the board is down.

### Entity Categories

FiestaBoard properly categorizes entities using Home Assistant's `entity_category` system:

- **No category** — Main controls and sensors (Schedule, Active Page, Send Message, etc.) — shown prominently in dashboards
- **Diagnostic** — Device health info (Version, Uptime, API Mode, Active Plugins, Service Status) — grouped in the Diagnostic section on the device page
- **Config** — Settings (Refresh Interval) — grouped in the Configuration section

## Troubleshooting

### FiestaBoard Not Appearing in HA

1. **Check MQTT broker connectivity** — Verify FiestaBoard can reach the broker (check FiestaBoard Settings page for connection status)
2. **Check HA MQTT integration** — Go to HA → Settings → Devices & Services and ensure the MQTT integration is configured and connected to the same broker
3. **Check broker logs** — Look at the Mosquitto broker logs for connection/authentication errors
4. **Restart discovery** — Disable and re-enable MQTT in FiestaBoard settings to republish discovery messages

### Entities Showing "Unavailable"

- FiestaBoard may have disconnected — check the FiestaBoard service is running
- Check the MQTT broker is running
- The LWT message marks the board as offline if the connection drops

### Commands Not Working

- Verify the MQTT broker allows publish/subscribe from both HA and FiestaBoard
- Check that HA's MQTT integration is configured with the correct broker credentials
- Check FiestaBoard logs for command processing errors

### A Command Stopped Working After Renaming a Board

Command payloads can target a specific board with a `board` field, which
accepts either the board's id or its display name:

```json
{ "board": "Kitchen", "page_id": "weather" }
```

Display names are editable in **Settings → Boards**, so renaming a board
breaks every automation that targets it by the old name — FiestaBoard cannot
rewrite payloads that live in your Home Assistant config. When this happens
the log records:

```text
MQTT: resolved board by name 'Kitchen'; renaming this board will break it. Target the board id 'b1' instead.
```

Target the board **id** instead. Ids never change, and they are what the
discovery topics already use, so renaming a board never orphans its HA
entities — only name-based `board` refs in your own automations.

## Branding

### Entity Icons

Each entity in HA shows a Material Design Icon that reflects its role:

| Entity | Icon | Reasoning |
|--------|------|-----------|
| Schedule | `mdi:calendar-clock` | Scheduled content delivery |
| Display Service | `mdi:television-play` | The board as an active display |
| Active Page | `mdi:bookmark` | The page queued for display |
| Transition Style | `mdi:animation-play` | Animated flip between pages |
| Current Page | `mdi:eye` | What is visible on the board right now |
| Board Message | `mdi:text` | The text content on the board |
| Silence Mode | `mdi:volume-off` | Quiet hours: no updates |
| Blank Board | `mdi:rectangle-outline` | Clear/empty board face |
| Send Message | `mdi:send` | Push text to the board |
| Next Page | `mdi:page-next` | Navigate to the next page |
| Previous Page | `mdi:page-previous` | Navigate to the previous page |
| Uptime | `mdi:clock-outline` | How long the service has been running |
| Board API Mode | `mdi:api` | Local or Cloud API connection |
| Active Plugins | `mdi:puzzle` | Number of enabled data sources |
| Last Display Update | `mdi:clock-check-outline` | When the board was last updated |
| Output Target | `mdi:monitor-speaker` | Where output is sent (ui/board/both) |
| Display Updated | `mdi:update` | Board content changed event |
| Page Changed | `mdi:book-open-page-variant` | Active page switched event |
| Settings Changed | `mdi:cog` | Schedule/service/silence state changed |

### Device Image

MQTT Discovery does not support setting a device-level image directly. To add a FiestaBoard logo to the device page in HA:

1. Go to **Settings → Devices & Services → MQTT**
2. Click on the **FiestaBoard** device
3. Click the **pencil (edit)** icon in the top-right corner
4. Under **Icon**, click the camera/image icon and upload the FiestaBoard logo
   - The logo is served from your FiestaBoard instance at `http://<your-fiestaboard-ip>:4420/logo.png`

This is saved locally in HA and persists across restarts.

## FAQ

### Do I need to install anything in Home Assistant?

No. FiestaBoard uses MQTT Discovery, which is built into Home Assistant's MQTT integration. No custom components, no HACS, no YAML configuration needed.

### What if I don't have an MQTT broker?

The easiest option is to install the [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto) in Home Assistant (one click from the Add-on Store). Alternatively, you can run [Mosquitto](https://mosquitto.org/) on any machine on your network.

### Is MQTT secure?

MQTT supports username/password authentication. For additional security, you can configure your broker to use TLS encryption (port 8883). FiestaBoard sends credentials securely to the broker.

### Does this affect FiestaBoard if I don't use Home Assistant?

No. MQTT integration is **disabled by default** and completely opt-in. If you don't enable it, there's zero impact on FiestaBoard's behavior or performance.

### What is MQTT?

[MQTT](https://mqtt.org/) is an open standard messaging protocol (ISO/IEC 20922) designed for IoT devices. It's lightweight, reliable, and the most widely used protocol for smart home device communication. It's used by Zigbee2MQTT, Tasmota, ESPHome, Frigate, and hundreds of other smart home projects.

## Related

- [Home Assistant Plugin](/docs/plugins/home-assistant) — Display HA entity states *on* your board (the reverse direction)
- [Plugins Overview](/docs/plugins/overview) — See all available plugins
