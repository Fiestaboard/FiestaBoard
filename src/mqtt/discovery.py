"""Home Assistant MQTT Discovery payload generation.

Builds the JSON discovery messages that tell Home Assistant about
FiestaBoard's entities (switches, sensors, selects, buttons, etc.).
When published to the MQTT broker under the `homeassistant/` prefix,
HA automatically creates the device and all entities.

References:
    - HA MQTT Discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
    - HA MQTT Switch: https://www.home-assistant.io/integrations/switch.mqtt/
    - HA MQTT Sensor: https://www.home-assistant.io/integrations/sensor.mqtt/
    - HA MQTT Select: https://www.home-assistant.io/integrations/select.mqtt/
    - HA MQTT Button: https://www.home-assistant.io/integrations/button.mqtt/
    - HA MQTT Text: https://www.home-assistant.io/integrations/text.mqtt/
    - HA MQTT Number: https://www.home-assistant.io/integrations/number.mqtt/
"""

import json
from dataclasses import dataclass, replace
from typing import Any

from src.mqtt.config import MQTTConfig

# Valid entity types supported by HA MQTT Discovery
VALID_ENTITY_TYPES = ["switch", "select", "sensor", "binary_sensor", "button", "text", "number"]


@dataclass
class EntityDefinition:
    """Definition of a single HA entity exposed via MQTT Discovery.

    Attributes:
        entity_type: HA entity type (switch, sensor, select, etc.)
        object_id: Unique object ID within the device (e.g., 'schedule_enabled')
        name: Human-readable entity name shown in HA
        icon: Material Design Icon identifier (e.g., 'mdi:calendar-clock')
        has_command: Whether this entity accepts commands from HA
        options: For select entities, the list of selectable options
        min_value: For number entities, minimum value
        max_value: For number entities, maximum value
        step: For number entities, step increment
        unit: For number/sensor entities, unit of measurement
        device_class: HA device class (e.g., 'running' for binary sensors)
        payload_on: Payload for ON state (switches/binary sensors)
        payload_off: Payload for OFF state (switches/binary sensors)
        min_length: For text entities, minimum text length
        max_length: For text entities, maximum text length
    """
    entity_type: str
    object_id: str
    name: str
    icon: str
    has_command: bool = False
    options: list[str] | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    unit: str | None = None
    device_class: str | None = None
    payload_on: str = "ON"
    payload_off: str = "OFF"
    min_length: int | None = None
    max_length: int | None = None


# All entities FiestaBoard exposes to Home Assistant
ENTITY_DEFINITIONS: list[EntityDefinition] = [
    # Switches
    EntityDefinition(
        entity_type="switch",
        object_id="schedule_enabled",
        name="Schedule",
        icon="mdi:calendar-clock",
        has_command=True,
    ),
    EntityDefinition(
        entity_type="switch",
        object_id="display_service",
        name="Display Service",
        icon="mdi:monitor",
        has_command=True,
    ),
    # Selects
    EntityDefinition(
        entity_type="select",
        object_id="active_page",
        name="Active Page",
        icon="mdi:page-layout-body",
        has_command=True,
        options=[],  # Populated dynamically from page list
    ),
    EntityDefinition(
        entity_type="select",
        object_id="output_target",
        name="Output Target",
        icon="mdi:monitor-speaker",
        has_command=True,
        options=["Board", "UI", "Both"],
    ),
    EntityDefinition(
        entity_type="select",
        object_id="transition_style",
        name="Transition Style",
        icon="mdi:transition",
        has_command=True,
        options=["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"],
    ),
    # Sensors
    EntityDefinition(
        entity_type="sensor",
        object_id="current_page",
        name="Current Page",
        icon="mdi:page-layout-body",
    ),
    EntityDefinition(
        entity_type="binary_sensor",
        object_id="service_status",
        name="Service Status",
        icon="mdi:heart-pulse",
        device_class="running",
    ),
    EntityDefinition(
        entity_type="sensor",
        object_id="current_message",
        name="Board Message",
        icon="mdi:message-text",
    ),
    EntityDefinition(
        entity_type="binary_sensor",
        object_id="silence_mode",
        name="Silence Mode",
        icon="mdi:volume-off",
    ),
    EntityDefinition(
        entity_type="sensor",
        object_id="version",
        name="Version",
        icon="mdi:tag",
    ),
    EntityDefinition(
        entity_type="sensor",
        object_id="page_count",
        name="Page Count",
        icon="mdi:file-multiple",
    ),
    # Buttons
    EntityDefinition(
        entity_type="button",
        object_id="refresh_display",
        name="Refresh Display",
        icon="mdi:refresh",
        has_command=True,
    ),
    EntityDefinition(
        entity_type="button",
        object_id="blank_board",
        name="Blank Board",
        icon="mdi:card-outline",
        has_command=True,
    ),
    # Text
    EntityDefinition(
        entity_type="text",
        object_id="send_message",
        name="Send Message",
        icon="mdi:message-draw",
        has_command=True,
        min_length=1,
        max_length=132,
    ),
    # Number
    EntityDefinition(
        entity_type="number",
        object_id="refresh_interval",
        name="Refresh Interval",
        icon="mdi:timer-outline",
        has_command=True,
        min_value=30,
        max_value=3600,
        step=30,
        unit="s",
    ),
]


def build_device_info(config: MQTTConfig, sw_version: str = "1.0.0", configuration_url: str | None = None) -> dict[str, Any]:
    """Build the HA device info block shared by all entities.

    This block appears in every discovery payload and tells HA that all
    entities belong to the same FiestaBoard device.

    Args:
        config: MQTT configuration with instance ID.
        sw_version: FiestaBoard software version string.
        configuration_url: URL to FiestaBoard web UI (e.g., 'http://192.168.1.50:4420').

    Returns:
        Device info dictionary for inclusion in discovery payloads.
    """
    device = {
        "identifiers": [config.instance_id],
        "name": "FiestaBoard",
        "manufacturer": "FiestaBoard",
        "model": "Vestaboard",
        "sw_version": sw_version,
    }
    if configuration_url:
        device["configuration_url"] = configuration_url
    return device


def build_discovery_topic(config: MQTTConfig, entity: EntityDefinition) -> str:
    """Build the MQTT topic where the discovery payload should be published.

    Format: {discovery_prefix}/{entity_type}/{instance_id}/{object_id}/config

    Args:
        config: MQTT configuration.
        entity: Entity definition.

    Returns:
        Discovery topic string (e.g., 'homeassistant/switch/fiestaboard_1/schedule_enabled/config').
    """
    return f"{config.discovery_prefix}/{entity.entity_type}/{config.instance_id}/{entity.object_id}/config"


def build_discovery_payload(
    config: MQTTConfig,
    entity: EntityDefinition,
    device_info: dict[str, Any],
) -> dict[str, Any]:
    """Build a single HA MQTT Discovery payload for an entity.

    The payload tells HA everything it needs to create the entity:
    name, state topic, command topic, availability, device linkage, etc.

    Args:
        config: MQTT configuration.
        entity: Entity definition.
        device_info: Shared device info block from build_device_info().

    Returns:
        Discovery payload dictionary ready for JSON serialization.

    Raises:
        ValueError: If entity_type is not a valid HA entity type.
    """
    if entity.entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"Invalid entity type: {entity.entity_type}. Must be one of {VALID_ENTITY_TYPES}")

    unique_id = f"{config.instance_id}_{entity.object_id}"

    payload: dict[str, Any] = {
        "name": entity.name,
        "unique_id": unique_id,
        "icon": entity.icon,
        "state_topic": f"{config.base_topic}/{entity.object_id}/state",
        "availability_topic": f"{config.base_topic}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device_info,
    }

    # Add command topic for controllable entities
    if entity.has_command:
        payload["command_topic"] = f"{config.base_topic}/{entity.object_id}/set"

    # Type-specific fields
    if entity.entity_type == "switch":
        payload["payload_on"] = entity.payload_on
        payload["payload_off"] = entity.payload_off

    elif entity.entity_type == "binary_sensor":
        payload["payload_on"] = entity.payload_on
        payload["payload_off"] = entity.payload_off
        if entity.device_class:
            payload["device_class"] = entity.device_class

    elif entity.entity_type == "select" and entity.options is not None:
        payload["options"] = entity.options

    elif entity.entity_type == "text":
        if entity.min_length is not None:
            payload["min"] = entity.min_length
        if entity.max_length is not None:
            payload["max"] = entity.max_length

    elif entity.entity_type == "number":
        if entity.min_value is not None:
            payload["min"] = entity.min_value
        if entity.max_value is not None:
            payload["max"] = entity.max_value
        if entity.step is not None:
            payload["step"] = entity.step
        if entity.unit:
            payload["unit_of_measurement"] = entity.unit

    return payload


def build_all_discovery_messages(
    config: MQTTConfig,
    sw_version: str = "1.0.0",
    configuration_url: str | None = None,
    page_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build all discovery messages for FiestaBoard.

    Generates the complete set of discovery topic/payload pairs for
    all FiestaBoard entities. Each message, when published as a retained
    MQTT message, tells HA about one entity.

    Args:
        config: MQTT configuration.
        sw_version: FiestaBoard software version.
        configuration_url: URL to FiestaBoard web UI.
        page_names: Current list of page names (for active_page select options).

    Returns:
        List of dicts, each with 'topic' and 'payload' keys.
    """
    device_info = build_device_info(config, sw_version, configuration_url)
    messages = []

    for entity in ENTITY_DEFINITIONS:
        # Inject dynamic page list into active_page entity
        if entity.object_id == "active_page" and page_names is not None:
            entity = replace(entity, options=page_names)

        topic = build_discovery_topic(config, entity)
        payload = build_discovery_payload(config, entity, device_info)

        messages.append({
            "topic": topic,
            "payload": json.dumps(payload),
        })

    return messages
