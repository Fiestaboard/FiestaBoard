# Home Assistant Integration Plan

## Overview

This document outlines the plan to expose FiestaBoard as a controllable device within Home Assistant (HA). Today, FiestaBoard has a **plugin** that *pulls* data from Home Assistant entities to display on the board. This initiative is the **reverse direction**: making FiestaBoard itself discoverable and controllable **from** Home Assistant, enabling smart home automations to control the board.

### Goals

- Expose FiestaBoard as a native device in Home Assistant
- Enable HA automations to control schedules, pages, display state, and messages
- Zero installation on the HA side (no HACS, no custom components required)
- Allow the smart home community to integrate FiestaBoard into their automations

---

## Research: Integration Approaches

Three approaches were evaluated for exposing FiestaBoard to Home Assistant:

### Option A: MQTT Discovery (✅ Recommended — Primary Approach)

**How it works:** FiestaBoard connects to an MQTT broker and publishes [Home Assistant MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) messages. HA automatically discovers FiestaBoard as a device with switches, sensors, selects, buttons, and text entities — no installation required on the HA side.

| Pros | Cons |
|------|------|
| Zero installation on HA (no HACS, no custom components) | Requires an MQTT broker (Mosquitto — very common in HA setups) |
| FiestaBoard appears as a native device automatically | Adds MQTT dependency to FiestaBoard |
| Supports all needed entity types (switch, select, sensor, button, text) | Slightly more complex than pure REST |
| Real-time state updates via MQTT pub/sub | Need to keep MQTT state in sync with FiestaBoard state |
| Well-documented, battle-tested protocol (used by Zigbee2MQTT, Tasmota, ESPHome) | |
| No HA version compatibility concerns | |

### Option B: Custom HA Integration (custom_components)

**How it works:** A Python package installed in HA's `custom_components/fiestaboard/` directory that communicates with FiestaBoard's REST API. Can be distributed via HACS or submitted to HA core.

| Pros | Cons |
|------|------|
| Richer UI integration possibilities | Requires installation on HA side |
| Can add custom dashboard cards | Must maintain compatibility with HA versions |
| Full control over entity behavior | HACS distribution or HA core submission process |
| Could add a config flow UI in HA | Separate codebase to maintain |
| | User explicitly wants to avoid HACS |

### Option C: HA REST Integration (Manual Setup)

**How it works:** Users manually configure HA's built-in [RESTful](https://www.home-assistant.io/integrations/rest/) platform to call FiestaBoard's existing API endpoints.

| Pros | Cons |
|------|------|
| Already possible today with existing API | Requires manual YAML configuration per entity |
| No code changes needed in FiestaBoard | No auto-discovery — tedious setup |
| | No real-time state updates (polling only) |
| | Poor user experience |

### Decision

**MQTT Discovery is the recommended primary approach.** It satisfies the core requirement of native HA device support without requiring any installation on the HA side. FiestaBoard publishes discovery messages, and HA automatically picks up the device. This is the same proven pattern used by Zigbee2MQTT, Tasmota, and ESPHome.

A **Custom HA Integration can be considered as a future Phase 2** for users who want deeper dashboard integration or don't run MQTT.

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

- [ ] **User documentation** — Setup guide for connecting FiestaBoard to HA via MQTT
- [ ] **Automation examples** — Curated HA automation YAML examples
- [ ] **Unit tests** — MQTT service, discovery payloads, state sync, command handling
- [ ] **Integration tests** — End-to-end MQTT flow with mock broker
- [ ] **Update README** — Add Home Assistant section to project README

### Future: Phase 6 (Optional — Custom HA Integration)

If deeper HA integration is desired beyond what MQTT Discovery provides:

- [ ] Create `custom_components/fiestaboard/` for HA
- [ ] Config flow UI for setup within HA
- [ ] Custom Lovelace dashboard card showing board preview
- [ ] Submit to Home Assistant core for native inclusion

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
| **Primary approach** | MQTT Discovery (zero install on HA side) |
| **Entities exposed** | 11 entities (2 switches, 2 selects, 3 sensors, 2 buttons, 1 text, 1 number) |
| **New dependency** | `paho-mqtt` (standard MQTT client) |
| **Configuration** | Opt-in via FiestaBoard settings, disabled by default |
| **HA compatibility** | Any HA installation with MQTT integration enabled |
| **Impact on existing users** | None — feature is opt-in, MQTT disabled by default |
| **Future expansion** | Custom HA integration for deeper dashboard features |

---

## Open Questions for Review

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

*This plan is ready for review. No implementation should begin until the approach and entity definitions are approved.*
