# Home Assistant Integration Plan

## Overview

This document outlines the plan to expose FiestaBoard as a controllable device within Home Assistant (HA). Today, FiestaBoard has a **plugin** that *pulls* data from Home Assistant entities to display on the board. This initiative is the **reverse direction**: making FiestaBoard itself discoverable and controllable **from** Home Assistant, enabling smart home automations to control the board.

### Goals

- Expose FiestaBoard as a native device in Home Assistant
- **Automatic discovery** — FiestaBoard appears in HA with zero manual setup
- Enable HA automations to control schedules, pages, display state, and messages
- Zero installation on the HA side (no HACS, no custom components required)
- Allow the smart home community to integrate FiestaBoard into their automations

---

## Research: Integration Approaches

Four approaches were evaluated for exposing FiestaBoard to Home Assistant. The key criteria are: **auto-discovery support**, **ease of setup**, **no HA-side installation**, and **real-time state updates**.

### Option A: MQTT Discovery (✅ Recommended)

**How it works:** FiestaBoard connects to an MQTT broker and publishes [Home Assistant MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) messages. HA automatically discovers FiestaBoard as a device with switches, sensors, selects, buttons, and text entities — no installation required on the HA side.

**Why MQTT is the best approach:**

MQTT is an **open standard** (ISO/IEC 20922, OASIS standard) — it's not proprietary to Home Assistant or any vendor. It's the universal language of IoT and smart home devices. Home Assistant has first-class, built-in support for MQTT Discovery, meaning any device that speaks MQTT can be auto-discovered without custom code on the HA side.

This is the same proven pattern used by the most popular HA integrations:
- **Zigbee2MQTT** — All Zigbee devices appear via MQTT Discovery
- **Tasmota** — Smart plugs, switches, sensors auto-discovered via MQTT
- **ESPHome** — DIY sensors and controllers use MQTT Discovery
- **Frigate** — NVR camera system exposes cameras via MQTT
- **Room Assistant** — Room presence detection via MQTT

The reason all these projects chose MQTT is the same reason it's right for FiestaBoard: **it's the only approach that gives you auto-discovery + zero HA installation + real-time updates + open standard** all at once.

| Pros | Cons |
|------|------|
| ✅ **Auto-discovery** — device appears in HA automatically | Requires an MQTT broker (Mosquitto — most common HA add-on) |
| ✅ Zero installation on HA (no HACS, no custom components) | Adds `paho-mqtt` dependency to FiestaBoard |
| ✅ Open standard (ISO/IEC 20922) — not locked to any vendor | Need to keep MQTT state in sync with FiestaBoard state |
| ✅ Real-time bidirectional state updates | |
| ✅ All needed entity types supported (switch, select, sensor, button, text, number) | |
| ✅ No HA version compatibility concerns | |
| ✅ Battle-tested by Zigbee2MQTT, Tasmota, ESPHome, Frigate | |
| ✅ Lightweight — publish/subscribe is minimal overhead | |

**Is MQTT difficult to set up?** No. For FiestaBoard users:
1. Most HA users already have Mosquitto (it's the #1 HA add-on — one click to install)
2. FiestaBoard configuration is just: broker host, port, optional username/password
3. Once connected, everything is automatic — entities appear in HA within seconds

### Option B: Custom HA Integration (custom_components)

**How it works:** A Python package installed in HA's `custom_components/fiestaboard/` directory that communicates with FiestaBoard's REST API. Can be distributed via HACS or submitted to HA core.

**Why not primary:** Requires installation on the HA side (either HACS or manual file copy), requires maintaining a separate Python codebase that must stay compatible with HA's frequently-changing internal APIs, and the HA core submission process is lengthy. However, this could be a good **Phase 2** for users who want custom Lovelace cards or don't run MQTT.

| Pros | Cons |
|------|------|
| Richer UI integration (custom dashboard cards) | ❌ Requires installation on HA side |
| Config flow UI within HA | ❌ Must maintain HA version compatibility |
| Full control over entity behavior | ❌ HACS distribution or HA core submission process |
| Could pair with SSDP/Zeroconf for discovery | ❌ Separate codebase to maintain |

### Option C: SSDP / Zeroconf (Network Discovery)

**How it works:** FiestaBoard advertises itself on the local network via SSDP (UPnP) or mDNS/Zeroconf (like Apple Bonjour). HA can detect the device on the network. This is how Philips Hue, Chromecast, and Sonos are discovered.

**Why not primary:** Network discovery only tells HA "this device exists on your network." To actually *control* the device, you still need either a custom HA integration (Option B) to handle the discovered device, or MQTT (Option A) for entity control. SSDP/Zeroconf alone can't expose switches, sensors, selects, etc. — it's only a discovery mechanism, not a control protocol.

| Pros | Cons |
|------|------|
| True network-level auto-discovery | ❌ Discovery only — no control capability by itself |
| No MQTT broker needed for discovery step | ❌ Requires a custom_components integration to handle discovery |
| Same mechanism as Hue, Chromecast | ❌ More complex to implement correctly |

**Note:** SSDP/Zeroconf could be added as a **complement** to MQTT Discovery in a future phase (see Phase 6).

### Option D: HA REST Integration (Manual Setup)

**How it works:** Users manually configure HA's built-in [RESTful](https://www.home-assistant.io/integrations/rest/) platform to call FiestaBoard's existing API endpoints.

**Why not:** No auto-discovery, requires extensive manual YAML per entity, polling-only (no real-time), and poor user experience. Already possible today for power users, but not a good default path.

| Pros | Cons |
|------|------|
| Already possible today with existing API | ❌ No auto-discovery — manual YAML per entity |
| No code changes needed in FiestaBoard | ❌ No real-time state updates (polling only) |
| | ❌ Poor user experience |

### Comparison: Auto-Discovery Capabilities

| Feature | MQTT Discovery | Custom Integration | SSDP/Zeroconf | REST |
|---------|:---:|:---:|:---:|:---:|
| **Auto-discovery in HA** | ✅ Built-in | ⚠️ With config flow | ⚠️ Needs custom_components | ❌ Manual only |
| **Zero HA-side install** | ✅ | ❌ | ❌ | ✅ |
| **Real-time updates** | ✅ | ✅ | N/A | ❌ Polling |
| **Entity control** | ✅ | ✅ | ❌ Discovery only | ⚠️ Limited |
| **Open standard** | ✅ ISO/IEC 20922 | ❌ HA-specific | ✅ | ✅ |
| **Setup complexity** | Low (broker host) | Medium (install + config) | High (+ custom integration) | High (YAML per entity) |
| **Maintenance burden** | Low | High (HA API changes) | Medium | Low |

### Decision

**MQTT Discovery is the best approach for FiestaBoard.** It's the only option that checks every box: automatic discovery, zero HA-side installation, real-time bidirectional state updates, open standard, and low maintenance burden. This is the same conclusion reached by Zigbee2MQTT, Tasmota, ESPHome, and every other major third-party HA device project.

**Future phases** can add SSDP/Zeroconf for network-level discovery and/or a custom HA integration for richer dashboard features — but MQTT Discovery is the right foundation.

---

## How Auto-Discovery Works

This is how FiestaBoard becomes automatically discoverable by Home Assistant — the user experience from "plugged in" to "showing up in HA":

### The Discovery Flow

```
 FiestaBoard starts up
        │
        ▼
 ┌──────────────────┐     1. Connect to MQTT broker
 │  MQTT Service    │────────────────────────────────►┌──────────────┐
 │  (in FiestaBoard)│                                 │ MQTT Broker  │
 └──────────────────┘                                 │ (Mosquitto)  │
        │                                             └──────┬───────┘
        │  2. Publish discovery configs to                    │
        │     homeassistant/<type>/fiestaboard/<entity>/config│
        │─────────────────────────────────────────────────────►
        │                                                     │
        │  3. Publish availability: "online"                  │
        │─────────────────────────────────────────────────────►
        │                                                     │
        │  4. Publish current state for all entities          │
        │─────────────────────────────────────────────────────►
        │                                                     │
        │                      ┌──────────────────────────────┤
        │                      │  5. HA's MQTT integration    │
        │                      │     reads discovery configs  │
        │                      ▼                              │
        │               ┌─────────────┐                       │
        │               │    Home     │ 6. FiestaBoard device │
        │               │  Assistant  │    appears in HA with │
        │               │             │    all entities ready │
        │               └─────────────┘                       │
        │                      │                              │
        │  7. HA subscribes to command topics                 │
        │◄─────────────────────┴──────────────────────────────┤
        │     (e.g., user toggles switch in HA)               │
        ▼                                                     │
 FiestaBoard executes command, publishes updated state ──────►│
```

### Step-by-Step: What Happens Automatically

1. **FiestaBoard boots** and connects to the MQTT broker (host/port from settings)
2. **Discovery messages published** — FiestaBoard publishes retained JSON configs to `homeassistant/switch/fiestaboard/schedule_enabled/config`, `homeassistant/select/fiestaboard/active_page/config`, etc. These messages tell HA: "I'm a device called FiestaBoard, I have these entities, here are my state/command topics."
3. **Availability announced** — FiestaBoard publishes `"online"` to `fiestaboard/status` (with a Last Will and Testament of `"offline"` so HA knows if FiestaBoard disconnects)
4. **State published** — Current state of all entities published to their respective topics
5. **HA auto-discovers** — Home Assistant's built-in MQTT integration sees the discovery messages and **automatically creates the device and all entities** — no user action needed
6. **Device appears** — FiestaBoard shows up in HA → Settings → Devices & Services → MQTT with all switches, sensors, selects, buttons, etc. ready to use
7. **Bidirectional control** — HA subscribes to command topics. When a user toggles a switch or sends a message from HA, FiestaBoard receives the command, executes it, and publishes the updated state back

### What The User Sees in Home Assistant

After FiestaBoard connects to MQTT, the user sees:

**Settings → Devices & Services → MQTT → FiestaBoard**

```
╔══════════════════════════════════════════════════╗
║  🎪 FiestaBoard                                  ║
║  Manufacturer: FiestaBoard                       ║
║  Model: Vestaboard Flagship                      ║
║  Configuration: http://<your-ip>:4420             ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  Controls                                        ║
║  ─────────                                       ║
║  🔀 Schedule         [ON/OFF toggle]             ║
║  🖥️ Display Service   [ON/OFF toggle]             ║
║  📄 Active Page       [▾ Weather Dashboard]       ║
║  🎯 Output Target     [▾ Board]                   ║
║  💬 Send Message      [____________] [Send]       ║
║  🔄 Refresh Display   [Press]                     ║
║  ⏱️ Refresh Interval   ──●──── 300s               ║
║                                                  ║
║  Sensors                                         ║
║  ───────                                         ║
║  📄 Current Page:      Weather Dashboard          ║
║  💚 Service Status:    Running                    ║
║  💬 Board Message:     "72°F Sunny SF"            ║
║  🔇 Silence Mode:     Off                        ║
║                                                  ║
╚══════════════════════════════════════════════════╝
```

**No manual configuration needed. No YAML. No HACS install. It just appears.**

### Discovery Message Example

Here's what a single discovery message looks like (FiestaBoard publishes this to the broker, and HA reads it automatically):

**Topic:** `homeassistant/switch/fiestaboard/schedule_enabled/config`

```json
{
  "name": "Schedule",
  "unique_id": "fiestaboard_1_schedule_enabled",
  "icon": "mdi:calendar-clock",
  "state_topic": "fiestaboard/schedule_enabled/state",
  "command_topic": "fiestaboard/schedule_enabled/set",
  "payload_on": "ON",
  "payload_off": "OFF",
  "availability_topic": "fiestaboard/status",
  "payload_available": "online",
  "payload_not_available": "offline",
  "device": {
    "identifiers": ["fiestaboard_1"],
    "name": "FiestaBoard",
    "manufacturer": "FiestaBoard",
    "model": "Vestaboard Flagship",
    "sw_version": "1.0.0",
    "configuration_url": "http://<your-fiestaboard-ip>:4420"
  }
}
```

HA reads this and automatically creates `switch.fiestaboard_schedule` — subscribes to the state topic, knows where to send commands, links it to the FiestaBoard device, and makes it available in automations and dashboards.

---

## Architecture

### System Diagram

```
┌─────────────────────┐       MQTT        ┌──────────────────┐
│                     │◄─────────────────►│                  │
│    FiestaBoard      │   publish/sub     │   MQTT Broker    │
│   (Python/FastAPI)  │                   │   (Mosquitto)    │
│                     │                   │                  │
│  ┌───────────────┐  │                   └────────┬─────────┘
│  │ MQTT Service  │  │                            │
│  │ (new module)  │  │                            │ MQTT
│  └───────────────┘  │                            │
│         ▲           │                   ┌────────▼─────────┐
│         │           │                   │                  │
│  ┌──────┴────────┐  │                   │  Home Assistant  │
│  │ API Server    │  │                   │  (auto-discover) │
│  │ Display Svc   │  │                   │                  │
│  │ Schedule Svc  │  │                   │  ┌────────────┐  │
│  └───────────────┘  │                   │  │ FiestaBoard│  │
│                     │                   │  │  Device    │  │
└─────────────────────┘                   │  └────────────┘  │
                                          └──────────────────┘
```

### MQTT Topic Structure

```
homeassistant/                          # HA discovery prefix
├── switch/fiestaboard/                 # Switch entities
│   ├── schedule_enabled/config         # Discovery payload
│   └── display_service/config          # Discovery payload
├── select/fiestaboard/
│   └── active_page/config              # Page selector
├── sensor/fiestaboard/
│   ├── current_page/config             # Currently displayed page
│   ├── service_status/config           # Running/stopped
│   └── current_message/config          # What's on the board
├── button/fiestaboard/
│   ├── refresh_display/config          # Force refresh
│   └── send_welcome/config             # Test board connection
├── text/fiestaboard/
│   └── send_message/config             # Send custom text
└── number/fiestaboard/
    └── refresh_interval/config         # Polling interval

fiestaboard/                            # State & command topics
├── status                              # Online/offline (LWT)
├── state                               # JSON state of all entities
├── schedule_enabled/
│   ├── state                           # "ON" / "OFF"
│   └── set                             # Command topic
├── display_service/
│   ├── state                           # "ON" / "OFF"
│   └── set                             # Command topic
├── active_page/
│   ├── state                           # Current page name
│   └── set                             # Command topic
├── current_page/state                  # Sensor: current page name
├── service_status/state                # Sensor: "running" / "stopped"
├── current_message/state               # Sensor: board content summary
├── refresh_display/set                 # Button command
├── send_welcome/set                    # Button command
├── send_message/
│   ├── state                           # Last sent message
│   └── set                             # Command topic
└── refresh_interval/
    ├── state                           # Current interval (seconds)
    └── set                             # Command topic
```

---

## Entity Definitions

### Device Registration

FiestaBoard registers itself as a single device in HA via MQTT discovery:

```json
{
  "identifiers": ["fiestaboard_{instance_id}"],
  "name": "FiestaBoard",
  "manufacturer": "FiestaBoard",
  "model": "Vestaboard Flagship / Note",
  "sw_version": "1.x.x",
  "configuration_url": "http://{fiestaboard_host}:4420"
}
```

### Entity: Schedule Enable/Disable (Switch)

| Property | Value |
|----------|-------|
| **Entity ID** | `switch.fiestaboard_schedule` |
| **Name** | Schedule |
| **Icon** | `mdi:calendar-clock` |
| **FiestaBoard API** | `PUT /schedules/enabled` with `{"enabled": true/false}` |
| **State Source** | `GET /schedules/enabled` |
| **Use Case** | HA automation: "Disable schedule on holidays" |

### Entity: Display Service (Switch)

| Property | Value |
|----------|-------|
| **Entity ID** | `switch.fiestaboard_display_service` |
| **Name** | Display Service |
| **Icon** | `mdi:monitor` |
| **FiestaBoard API** | `POST /start` (ON) / `POST /stop` (OFF) |
| **State Source** | `GET /status` → `running` field |
| **Use Case** | HA automation: "Turn off board when everyone leaves home" |

### Entity: Active Page (Select)

| Property | Value |
|----------|-------|
| **Entity ID** | `select.fiestaboard_active_page` |
| **Name** | Active Page |
| **Icon** | `mdi:page-layout-body` |
| **Options** | Dynamically populated from `GET /pages` (page names) |
| **FiestaBoard API** | `PUT /settings/active-page` with `{"page_id": "..."}` |
| **State Source** | Active page name from status/schedule resolution |
| **Use Case** | HA automation: "Show weather page when it's raining" |

### Entity: Current Page (Sensor)

| Property | Value |
|----------|-------|
| **Entity ID** | `sensor.fiestaboard_current_page` |
| **Name** | Current Page |
| **Icon** | `mdi:page-layout-body` |
| **State** | Name of the currently displayed page |
| **Attributes** | `page_id`, `page_type`, `device_type` |
| **Use Case** | HA dashboard: see what's currently on the board |

### Entity: Service Status (Binary Sensor)

| Property | Value |
|----------|-------|
| **Entity ID** | `binary_sensor.fiestaboard_service_status` |
| **Name** | Service Status |
| **Icon** | `mdi:heart-pulse` |
| **Device Class** | `running` |
| **State** | ON (running) / OFF (stopped) |
| **Use Case** | HA alert: "Notify me if FiestaBoard goes offline" |

### Entity: Board Message (Sensor)

| Property | Value |
|----------|-------|
| **Entity ID** | `sensor.fiestaboard_message` |
| **Name** | Board Message |
| **Icon** | `mdi:message-text` |
| **State** | Summary/preview of current board content |
| **Attributes** | `last_updated`, `source` (manual/schedule/page) |
| **Use Case** | HA dashboard: show current board text, HA TTS announcements |

### Entity: Send Message (Text)

| Property | Value |
|----------|-------|
| **Entity ID** | `text.fiestaboard_send_message` |
| **Name** | Send Message |
| **Icon** | `mdi:message-draw` |
| **Min Length** | 1 |
| **Max Length** | 132 (22 chars × 6 rows for Flagship) |
| **FiestaBoard API** | `POST /send-message` with `{"text": "..."}` |
| **Use Case** | HA automation: "Display 'Welcome Home!' when front door opens" |

### Entity: Refresh Display (Button)

| Property | Value |
|----------|-------|
| **Entity ID** | `button.fiestaboard_refresh` |
| **Name** | Refresh Display |
| **Icon** | `mdi:refresh` |
| **FiestaBoard API** | `POST /refresh` |
| **Use Case** | HA automation: "Refresh board when weather data updates" |

### Entity: Output Target (Select)

| Property | Value |
|----------|-------|
| **Entity ID** | `select.fiestaboard_output_target` |
| **Name** | Output Target |
| **Icon** | `mdi:monitor-speaker` |
| **Options** | `["Board", "UI", "Both"]` |
| **FiestaBoard API** | `PUT /settings/output` with `{"target": "..."}` |
| **State Source** | `GET /settings/output` → `effective_target` |
| **Use Case** | HA automation: "Switch to UI-only mode during quiet hours" |

### Entity: Silence Mode (Binary Sensor)

| Property | Value |
|----------|-------|
| **Entity ID** | `binary_sensor.fiestaboard_silence_mode` |
| **Name** | Silence Mode |
| **Icon** | `mdi:volume-off` |
| **State** | ON (silence active) / OFF (normal) |
| **Use Case** | HA dashboard: verify quiet hours are active |

### Entity: Refresh Interval (Number)

| Property | Value |
|----------|-------|
| **Entity ID** | `number.fiestaboard_refresh_interval` |
| **Name** | Refresh Interval |
| **Icon** | `mdi:timer-outline` |
| **Unit** | seconds |
| **Min/Max** | 30 / 3600 |
| **Step** | 30 |
| **FiestaBoard API** | `PUT /settings/polling` |
| **Use Case** | HA automation: "Increase refresh rate during market hours" |

---

## Automation Examples

Once integrated, HA users could create automations like:

### Example 1: Welcome Home Message
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

### Example 2: Show Weather During Rain
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

### Example 3: Disable Board at Night
```yaml
automation:
  - alias: "Turn Off Board at Bedtime"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.fiestaboard_display_service
```

### Example 4: Sports Score Alert
```yaml
automation:
  - alias: "Switch to Sports During Game"
    trigger:
      - platform: state
        entity_id: sensor.nfl_game_status
        to: "in_progress"
    action:
      - service: select.select_option
        target:
          entity_id: select.fiestaboard_active_page
        data:
          option: "Sports Scores"
      - service: number.set_value
        target:
          entity_id: number.fiestaboard_refresh_interval
        data:
          value: 60
```

### Example 5: Dashboard Display
```yaml
# Show current board content on HA dashboard
type: entities
entities:
  - entity: sensor.fiestaboard_current_page
  - entity: sensor.fiestaboard_message
  - entity: binary_sensor.fiestaboard_service_status
  - entity: switch.fiestaboard_schedule
  - entity: select.fiestaboard_active_page
```

---

## Implementation Plan

### Phase 1: MQTT Service Core (Backend)

**New module: `src/mqtt/`**

Create the MQTT client service that connects to a broker and manages pub/sub:

- [ ] **`src/mqtt/__init__.py`** — Package init
- [ ] **`src/mqtt/client.py`** — MQTT client wrapper (connect, publish, subscribe, reconnect, LWT)
- [ ] **`src/mqtt/discovery.py`** — Build and publish HA MQTT Discovery payloads for all entities
- [ ] **`src/mqtt/entities.py`** — Entity definitions (maps FiestaBoard state → MQTT topics/payloads)
- [ ] **`src/mqtt/state.py`** — State sync manager (polls FiestaBoard state, publishes changes to MQTT)
- [ ] **`src/mqtt/commands.py`** — Command handler (subscribes to command topics, calls FiestaBoard API internally)

**Dependencies:**
- [ ] Add `paho-mqtt` Python package (the standard MQTT client library)

**Configuration (`.env` additions):**
```env
# Home Assistant MQTT Integration (optional — off by default)
MQTT_ENABLED=false
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_DISCOVERY_PREFIX=homeassistant
MQTT_BASE_TOPIC=fiestaboard
MQTT_INSTANCE_ID=fiestaboard_1
```

### Phase 2: Entity Implementation

Implement each entity type with proper state sync and command handling:

- [ ] **Switch: Schedule Enable/Disable** — Pub state on change, sub to command, call `PUT /schedules/enabled`
- [ ] **Switch: Display Service** — Pub running state, sub to command, call `POST /start` or `POST /stop`
- [ ] **Select: Active Page** — Pub current page, publish options list on page CRUD, sub to command
- [ ] **Sensor: Current Page** — Pub page name + attributes on display change
- [ ] **Binary Sensor: Service Status** — Pub on status change (heartbeat-based)
- [ ] **Sensor: Board Message** — Pub content summary on each display update
- [ ] **Text: Send Message** — Sub to command, call `POST /send-message`
- [ ] **Button: Refresh Display** — Sub to command, call `POST /refresh`
- [ ] **Select: Output Target** — Pub current target, sub to command
- [ ] **Binary Sensor: Silence Mode** — Pub silence state on change
- [ ] **Number: Refresh Interval** — Pub current interval, sub to command

### Phase 3: Integration with Existing Services

Wire the MQTT service into FiestaBoard's existing event flow:

- [ ] **Display Service hooks** — Publish state updates when display changes (page switch, content update)
- [ ] **Schedule Service hooks** — Publish state when schedule enable/disable changes
- [ ] **API Server hooks** — Publish state when settings change via UI/API
- [ ] **Startup/shutdown** — Start MQTT service with FiestaBoard, publish LWT for availability
- [ ] **Reconnection logic** — Handle MQTT broker disconnects gracefully with exponential backoff

### Phase 4: Configuration UI

Add MQTT configuration to the FiestaBoard web UI:

- [ ] **Settings page section** — MQTT broker connection settings (host, port, credentials)
- [ ] **Enable/disable toggle** — Turn MQTT integration on/off
- [ ] **Connection test button** — Verify broker connectivity
- [ ] **Status indicator** — Show MQTT connection status in the UI
- [ ] **Entity preview** — Show which entities will be exposed to HA

### Phase 5: Documentation & Testing

- [x] **User documentation** — Setup guide at `docs-site/docs/integrations/home-assistant-control.md`
- [ ] **Automation examples** — Curated HA automation YAML examples (included in user docs)
- [x] **Unit tests: Config** — `tests/test_mqtt_config.py` — 33 tests for MQTTConfig (defaults, validation, serialization, env loading)
- [x] **Unit tests: Discovery** — `tests/test_mqtt_discovery.py` — 47 tests for discovery payloads, entity definitions, topic generation, device info
- [ ] **Unit tests: Client** — `tests/test_mqtt_client.py` — MQTT client wrapper (connect, publish, subscribe, reconnect, LWT)
- [ ] **Unit tests: State sync** — `tests/test_mqtt_state.py` — State synchronization between FiestaBoard and MQTT
- [ ] **Unit tests: Commands** — `tests/test_mqtt_commands.py` — Command handling from HA to FiestaBoard
- [ ] **Integration tests** — End-to-end MQTT flow with mock broker
- [ ] **Update README** — Add Home Assistant section to project README

---

## Testing Strategy

The MQTT module (`src/mqtt/`) follows the same testing patterns as the rest of FiestaBoard: **pytest** with `unittest.mock`, organized in `tests/test_mqtt_*.py`, and run by the standard `pytest` command configured in `pyproject.toml`.

### Test Structure

The MQTT integration is tested at three levels:

```
tests/
├── test_mqtt_config.py        ← Config validation, serialization, env loading (33 tests)
├── test_mqtt_discovery.py     ← Discovery payloads, entity definitions, topics (47 tests)
├── test_mqtt_client.py        ← Client wrapper: connect, publish, subscribe, LWT (planned)
├── test_mqtt_state.py         ← State sync: FiestaBoard state → MQTT topics (planned)
└── test_mqtt_commands.py      ← Command handling: MQTT commands → FiestaBoard API (planned)
```

### How It Fits Into the Existing Test Suite

The MQTT module is **not a separate package** — it's a standard Python module in `src/mqtt/` with tests in `tests/`, exactly like every other FiestaBoard module:

| Module | Source | Tests | Pattern |
|--------|--------|-------|---------|
| Settings | `src/settings/` | `tests/test_output.py` | Dataclass + service + API endpoint tests |
| Schedules | `src/schedules/` | `tests/test_schedules_*.py` | Model, storage, service, midnight rollover |
| Templates | `src/templates/` | `tests/test_templates.py` | Engine logic, variable resolution |
| **MQTT** | **`src/mqtt/`** | **`tests/test_mqtt_*.py`** | **Config, discovery, client, state, commands** |

Running the MQTT tests:
```bash
# Run just the MQTT tests
pytest tests/test_mqtt_config.py tests/test_mqtt_discovery.py -v

# Run all tests (MQTT tests included automatically)
pytest tests/ -v

# Run all tests including plugin tests
pytest
```

### What Each Test File Covers

**`test_mqtt_config.py`** (33 tests) — Configuration layer:
- Default values (disabled by default, standard ports, standard topics)
- Validation rules (required fields when enabled, port range, non-empty strings)
- Serialization round-trip (`to_dict` / `from_dict`)
- Environment variable loading (`from_env` with various truthy/falsy values)

**`test_mqtt_discovery.py`** (47 tests) — Discovery payload correctness:
- Entity registry (count, types, uniqueness, required fields)
- Device info block (identifiers, name, manufacturer, version, URL)
- Discovery topic format (`{prefix}/{type}/{node_id}/{object_id}/config`)
- Per-entity payload structure (state_topic, command_topic, availability)
- Type-specific fields (switch on/off, select options, text length, number range)
- Full message generation (all entities, JSON validity, dynamic page list)

**`test_mqtt_client.py`** (planned) — MQTT client wrapper:
- Connection lifecycle (connect, disconnect, reconnect with backoff)
- Publish with retain flag
- Subscribe to command topics
- Last Will and Testament (LWT) setup
- Graceful degradation when broker is unavailable

**`test_mqtt_state.py`** (planned) — State synchronization:
- FiestaBoard state changes → MQTT state topic updates
- Retained message behavior
- Polling fallback for missed events

**`test_mqtt_commands.py`** (planned) — Command handling:
- MQTT command → FiestaBoard API call mapping
- Invalid command handling
- State update after command execution

### Dependency: `paho-mqtt`

The `paho-mqtt` package is the only new dependency. It's added to `pyproject.toml` as an **optional dependency** (not a hard requirement), so:
- Users who don't enable MQTT don't need it installed
- Tests that test config/discovery logic don't need `paho-mqtt` (they test our code, not the MQTT library)
- Tests that test the client wrapper mock `paho-mqtt` — no real broker needed
- Integration tests (future) can use a mock MQTT broker in-memory

### CI/CD Integration

The MQTT tests run in the same CI pipeline as all other tests:
- `pytest tests/` already picks up `test_mqtt_*.py` files automatically
- No special CI configuration needed
- No MQTT broker needed in CI (all broker interactions are mocked)
- Coverage is tracked alongside existing modules via `pytest-cov`

### Future: Phase 6 (Optional — Enhanced Discovery & Custom HA Integration)

Add complementary discovery methods and deeper HA integration:

- [ ] **SSDP/Zeroconf advertisement** — Advertise FiestaBoard via mDNS (`_fiestaboard._tcp.local`) so it's discoverable on the local network even before MQTT is configured. This is how ESPHome devices are found on the network. Combined with a custom integration, this could enable "click to add" in HA's integrations page.
- [ ] **Custom HA Integration (`custom_components/fiestaboard/`)** — For users who want deeper integration:
  - Config flow UI for setup within HA
  - Custom Lovelace dashboard card showing a live board preview
  - Native HA discovery via SSDP/Zeroconf handler
- [ ] **Submit to Home Assistant core** — Apply for native inclusion in HA (long process, but ultimate goal for seamless UX)

---

## Configuration UX

### First-Time Setup Flow

1. User enables MQTT integration in FiestaBoard settings
2. User enters MQTT broker details (host, port, optional credentials)
3. FiestaBoard tests the connection
4. On success, FiestaBoard publishes discovery messages
5. FiestaBoard device appears automatically in HA → Settings → Devices
6. All entities are immediately available for automations and dashboards

### For Users Without MQTT

Users who don't run an MQTT broker can:
- Install Mosquitto add-on in HA (one-click from add-on store)
- Use any existing MQTT broker on their network
- The feature is **opt-in** and disabled by default — no impact on non-HA users

---

## Technical Considerations

### State Synchronization

FiestaBoard must keep MQTT state in sync with actual state. Two approaches:

1. **Event-driven** (preferred): Hook into existing service events and publish on change
2. **Polling fallback**: Periodic state check (every 10s) to catch any missed events

The implementation should use event-driven as primary with a polling safety net.

### Retained Messages

All state topics should use MQTT retained messages so that HA gets the current state immediately on connect/reconnect, rather than waiting for the next state change.

### Last Will and Testament (LWT)

FiestaBoard should set an MQTT LWT message so HA knows when FiestaBoard goes offline:
- **LWT Topic:** `fiestaboard/status`
- **LWT Payload:** `offline`
- **On Connect:** Publish `online` to same topic

### Dynamic Page List

The Active Page select entity needs to update its options when pages are created/deleted. This requires republishing the discovery payload with updated options whenever the page list changes.

### Thread Safety

The MQTT service runs in its own thread. All interactions with FiestaBoard services must be thread-safe. The existing `DisplayService` already uses thread-safe patterns that can be followed.

### Graceful Degradation

If MQTT is enabled but the broker is unavailable:
- FiestaBoard continues to operate normally
- MQTT service retries connection with exponential backoff
- Warning displayed in FiestaBoard UI
- No impact on board display or web UI functionality

---

## Dependency

| Package | Version | Purpose | License |
|---------|---------|---------|---------|
| `paho-mqtt` | ≥2.0.0 | MQTT client library | EPL-2.0 / EDL-1.0 |

This is the standard Python MQTT client library, widely used and well-maintained by the Eclipse Foundation.

---

## Summary

| Aspect | Decision |
|--------|----------|
| **Primary approach** | MQTT Discovery (zero install on HA side, automatic discovery) |
| **Auto-discovery** | ✅ Yes — FiestaBoard appears automatically in HA Devices via MQTT Discovery |
| **HA-side installation** | None required — MQTT integration is built into HA core |
| **Protocol** | MQTT (open standard, ISO/IEC 20922) |
| **Entities exposed** | 11 entities (2 switches, 2 selects, 3 sensors, 2 buttons, 1 text, 1 number) |
| **New dependency** | `paho-mqtt` (standard Python MQTT client) |
| **Configuration** | Opt-in via FiestaBoard settings, disabled by default |
| **HA compatibility** | Any HA installation with MQTT integration enabled |
| **Impact on existing users** | None — feature is opt-in, MQTT disabled by default |
| **Future expansion** | SSDP/Zeroconf for network discovery, custom HA integration for dashboard cards |

---

## Open Questions for Review

### Resolved by Research

- **✅ Is MQTT the best approach?** — Yes. MQTT Discovery is the only approach that provides auto-discovery + zero HA-side installation + real-time state updates + open standard. It's the same approach chosen by Zigbee2MQTT, Tasmota, ESPHome, and Frigate. See the comparison table in the Research section.

- **✅ Can FiestaBoard be auto-discovered?** — Yes. MQTT Discovery makes FiestaBoard appear automatically in HA → Settings → Devices & Services → MQTT. No manual YAML, no HACS, no custom components needed. See the "How Auto-Discovery Works" section for the complete flow.

### Remaining Questions

1. **Instance naming**: Should multiple FiestaBoard instances be supported (e.g., `fiestaboard_living_room`, `fiestaboard_office`)? The plan supports this via `MQTT_INSTANCE_ID`.

2. **Board-specific entities**: For multi-board setups (Flagship + Note), should each board get its own set of entities, or is one device with a board selector sufficient?

3. **Message format**: For the "Board Message" sensor, should we expose the raw character array, a text representation, or both?

4. **Additional entities**: Are there other FiestaBoard features that should be exposed? Candidates:
   - Transition strategy (select)
   - Individual schedule entries (switches to enable/disable each)
   - Plugin data as sensors (weather temp, stock prices, etc.)
   - Board brightness (if hardware supports it)

5. **MQTT broker default**: Should FiestaBoard default to `homeassistant.local:1883` (common HA address) or require explicit configuration?

6. **Security**: Should we support MQTT over TLS (`mqtts://`) from the start, or add it later?

---

---

## Phase 2 Roadmap: Custom HA Integration

The current MQTT Discovery approach is the right foundation and covers the primary use case well. A future Phase 2 could add a **custom Home Assistant integration** (`custom_components/fiestaboard/`) for users who want deeper integration. This would be a separate project.

### What a custom integration would enable

- **SSDP/Zeroconf auto-discovery**: FiestaBoard advertises itself on the local network; HA detects it without the user needing to know the IP address or configure MQTT. No broker required for discovery.
- **Config flow UI inside HA**: A guided setup wizard in the HA Devices & Services screen (same as Hue, Chromecast, etc.) — the user clicks "+ Add Integration" and FiestaBoard appears in the list.
- **Custom Lovelace dashboard cards**: A live board preview card (showing a simulation of the split-flap display), quick-send controls, and a schedule overview — not possible with generic entity cards.
- **Device-level brand image**: The FiestaBoard logo appears automatically on the device page without the user needing to set it manually.
- **HACS distribution**: One-click install from HACS (Home Assistant Community Store), the standard distribution channel for custom integrations.

### What it costs

- A **separate Python codebase** that must stay compatible with HA's rapidly-changing internal APIs (HA regularly makes breaking changes to custom integration APIs).
- **Installation on the HA side** — HACS or manual `custom_components/` file copy. Not zero-install.
- **HACS or HA Core submission process** — HACS listing requires a public repo and a review; HA Core submission is a multi-month process with strict requirements.
- **Ongoing maintenance burden** — HA's `config_entries`, `entity`, and `coordinator` APIs change with nearly every major release.

### Recommendation

Build Phase 2 only after:
1. The MQTT integration has been tested in production with real users
2. There is clear demand for features that MQTT cannot provide (primarily: custom Lovelace cards, network-level auto-discovery without a broker)
3. The team has capacity to maintain a separate Python codebase against HA's release cycle

Until then, improving the MQTT experience (better defaults, Setup UI in FiestaBoard, documentation) delivers the most value per engineering hour.

*This plan is complete. The MQTT Discovery implementation is live. Phase 2 items above are not scheduled.*
