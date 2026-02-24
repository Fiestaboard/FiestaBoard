"""Tests for MQTT Discovery payload generation.

These tests verify that FiestaBoard generates correct HA MQTT Discovery
payloads — the JSON messages that tell Home Assistant how to create
entities for the FiestaBoard device.

The payloads must conform to the HA MQTT Discovery specification:
https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
"""

import json
import pytest

from src.mqtt.config import MQTTConfig
from src.mqtt.discovery import (
    EntityDefinition,
    ENTITY_DEFINITIONS,
    VALID_ENTITY_TYPES,
    build_device_info,
    build_discovery_topic,
    build_discovery_payload,
    build_all_discovery_messages,
)


@pytest.fixture
def mqtt_config():
    """Standard MQTT config for testing."""
    return MQTTConfig(
        enabled=True,
        broker_host="192.168.1.100",
        broker_port=1883,
        discovery_prefix="homeassistant",
        base_topic="fiestaboard",
        instance_id="fiestaboard_1",
    )


@pytest.fixture
def device_info(mqtt_config):
    """Standard device info for testing."""
    return build_device_info(mqtt_config, sw_version="2.1.0", configuration_url="http://192.168.1.50:4420")


class TestEntityDefinitions:
    """Tests for the entity definition registry."""

    def test_entity_count(self):
        """FiestaBoard should expose 11 entities to HA."""
        assert len(ENTITY_DEFINITIONS) == 11

    def test_all_entity_types_valid(self):
        """All entity types must be valid HA entity types."""
        for entity in ENTITY_DEFINITIONS:
            assert entity.entity_type in VALID_ENTITY_TYPES, (
                f"Entity '{entity.object_id}' has invalid type '{entity.entity_type}'"
            )

    def test_unique_object_ids(self):
        """All entity object IDs must be unique."""
        ids = [e.object_id for e in ENTITY_DEFINITIONS]
        assert len(ids) == len(set(ids)), f"Duplicate object IDs found: {ids}"

    def test_all_entities_have_names(self):
        """All entities must have non-empty names."""
        for entity in ENTITY_DEFINITIONS:
            assert entity.name and entity.name.strip(), (
                f"Entity '{entity.object_id}' has empty name"
            )

    def test_all_entities_have_icons(self):
        """All entities must have MDI icons."""
        for entity in ENTITY_DEFINITIONS:
            assert entity.icon.startswith("mdi:"), (
                f"Entity '{entity.object_id}' icon must start with 'mdi:'"
            )

    def test_switch_entities(self):
        """Should have exactly 2 switch entities."""
        switches = [e for e in ENTITY_DEFINITIONS if e.entity_type == "switch"]
        assert len(switches) == 2
        switch_ids = {e.object_id for e in switches}
        assert "schedule_enabled" in switch_ids
        assert "display_service" in switch_ids

    def test_select_entities(self):
        """Should have exactly 2 select entities."""
        selects = [e for e in ENTITY_DEFINITIONS if e.entity_type == "select"]
        assert len(selects) == 2
        select_ids = {e.object_id for e in selects}
        assert "active_page" in select_ids
        assert "output_target" in select_ids

    def test_sensor_entities(self):
        """Should have sensor entities for current page and message."""
        sensors = [e for e in ENTITY_DEFINITIONS if e.entity_type == "sensor"]
        sensor_ids = {e.object_id for e in sensors}
        assert "current_page" in sensor_ids
        assert "current_message" in sensor_ids

    def test_binary_sensor_entities(self):
        """Should have binary sensor entities for status and silence."""
        binary = [e for e in ENTITY_DEFINITIONS if e.entity_type == "binary_sensor"]
        binary_ids = {e.object_id for e in binary}
        assert "service_status" in binary_ids
        assert "silence_mode" in binary_ids

    def test_button_entities(self):
        """Should have button entity for refresh."""
        buttons = [e for e in ENTITY_DEFINITIONS if e.entity_type == "button"]
        assert len(buttons) == 1
        assert buttons[0].object_id == "refresh_display"

    def test_text_entities(self):
        """Should have text entity for sending messages."""
        texts = [e for e in ENTITY_DEFINITIONS if e.entity_type == "text"]
        assert len(texts) == 1
        assert texts[0].object_id == "send_message"
        assert texts[0].max_length == 132  # 22 chars × 6 rows

    def test_number_entities(self):
        """Should have number entity for refresh interval."""
        numbers = [e for e in ENTITY_DEFINITIONS if e.entity_type == "number"]
        assert len(numbers) == 1
        assert numbers[0].object_id == "refresh_interval"
        assert numbers[0].min_value == 30
        assert numbers[0].max_value == 3600
        assert numbers[0].step == 30

    def test_controllable_entities_have_commands(self):
        """Entities that accept HA commands must have has_command=True."""
        controllable = {"schedule_enabled", "display_service", "active_page",
                        "output_target", "refresh_display", "send_message", "refresh_interval"}
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in controllable:
                assert entity.has_command is True, (
                    f"Entity '{entity.object_id}' should be controllable"
                )

    def test_readonly_entities_no_commands(self):
        """Read-only entities should not have commands."""
        readonly = {"current_page", "service_status", "current_message", "silence_mode"}
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in readonly:
                assert entity.has_command is False, (
                    f"Entity '{entity.object_id}' should be read-only"
                )


class TestDeviceInfo:
    """Tests for device info block generation."""

    def test_device_info_identifiers(self, mqtt_config):
        """Device identifiers must include the instance ID."""
        info = build_device_info(mqtt_config)
        assert mqtt_config.instance_id in info["identifiers"]

    def test_device_info_name(self, mqtt_config):
        """Device name must be FiestaBoard."""
        info = build_device_info(mqtt_config)
        assert info["name"] == "FiestaBoard"

    def test_device_info_manufacturer(self, mqtt_config):
        """Manufacturer must be FiestaBoard."""
        info = build_device_info(mqtt_config)
        assert info["manufacturer"] == "FiestaBoard"

    def test_device_info_sw_version(self, mqtt_config):
        """Software version must be included."""
        info = build_device_info(mqtt_config, sw_version="2.1.33")
        assert info["sw_version"] == "2.1.33"

    def test_device_info_configuration_url(self, mqtt_config):
        """Configuration URL should be included when provided."""
        info = build_device_info(mqtt_config, configuration_url="http://192.168.1.50:4420")
        assert info["configuration_url"] == "http://192.168.1.50:4420"

    def test_device_info_no_configuration_url(self, mqtt_config):
        """Configuration URL should be omitted when not provided."""
        info = build_device_info(mqtt_config)
        assert "configuration_url" not in info


class TestDiscoveryTopics:
    """Tests for MQTT discovery topic generation."""

    def test_topic_format(self, mqtt_config):
        """Discovery topic must follow HA convention: {prefix}/{type}/{node_id}/{object_id}/config."""
        entity = EntityDefinition(
            entity_type="switch", object_id="schedule_enabled",
            name="Schedule", icon="mdi:calendar-clock", has_command=True,
        )
        topic = build_discovery_topic(mqtt_config, entity)
        assert topic == "homeassistant/switch/fiestaboard_1/schedule_enabled/config"

    def test_topic_uses_config_prefix(self):
        """Topic should use the configured discovery prefix."""
        config = MQTTConfig(discovery_prefix="my_ha", instance_id="board_1")
        entity = EntityDefinition(
            entity_type="sensor", object_id="current_page",
            name="Current Page", icon="mdi:page-layout-body",
        )
        topic = build_discovery_topic(config, entity)
        assert topic.startswith("my_ha/")

    def test_topic_uses_instance_id(self):
        """Topic should include the instance ID as node_id."""
        config = MQTTConfig(instance_id="office_board")
        entity = EntityDefinition(
            entity_type="button", object_id="refresh_display",
            name="Refresh", icon="mdi:refresh", has_command=True,
        )
        topic = build_discovery_topic(config, entity)
        assert "office_board" in topic


class TestDiscoveryPayloads:
    """Tests for individual discovery payload generation."""

    def test_payload_required_fields(self, mqtt_config, device_info):
        """Every payload must have name, unique_id, state_topic, availability, and device."""
        entity = EntityDefinition(
            entity_type="sensor", object_id="current_page",
            name="Current Page", icon="mdi:page-layout-body",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "name" in payload
        assert "unique_id" in payload
        assert "state_topic" in payload
        assert "availability_topic" in payload
        assert "device" in payload

    def test_payload_unique_id_format(self, mqtt_config, device_info):
        """Unique ID must be {instance_id}_{object_id}."""
        entity = EntityDefinition(
            entity_type="switch", object_id="schedule_enabled",
            name="Schedule", icon="mdi:calendar-clock", has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["unique_id"] == "fiestaboard_1_schedule_enabled"

    def test_payload_state_topic(self, mqtt_config, device_info):
        """State topic must be {base_topic}/{object_id}/state."""
        entity = EntityDefinition(
            entity_type="sensor", object_id="current_page",
            name="Current Page", icon="mdi:page-layout-body",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["state_topic"] == "fiestaboard/current_page/state"

    def test_payload_command_topic_present(self, mqtt_config, device_info):
        """Controllable entities must have a command_topic."""
        entity = EntityDefinition(
            entity_type="switch", object_id="schedule_enabled",
            name="Schedule", icon="mdi:calendar-clock", has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "command_topic" in payload
        assert payload["command_topic"] == "fiestaboard/schedule_enabled/set"

    def test_payload_command_topic_absent(self, mqtt_config, device_info):
        """Read-only entities must NOT have a command_topic."""
        entity = EntityDefinition(
            entity_type="sensor", object_id="current_page",
            name="Current Page", icon="mdi:page-layout-body", has_command=False,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "command_topic" not in payload

    def test_payload_availability(self, mqtt_config, device_info):
        """Availability must use LWT topic with online/offline payloads."""
        entity = EntityDefinition(
            entity_type="sensor", object_id="service_status",
            name="Status", icon="mdi:heart-pulse",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["availability_topic"] == "fiestaboard/status"
        assert payload["payload_available"] == "online"
        assert payload["payload_not_available"] == "offline"

    def test_switch_payload_has_on_off(self, mqtt_config, device_info):
        """Switch payloads must include payload_on and payload_off."""
        entity = EntityDefinition(
            entity_type="switch", object_id="schedule_enabled",
            name="Schedule", icon="mdi:calendar-clock", has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["payload_on"] == "ON"
        assert payload["payload_off"] == "OFF"

    def test_select_payload_has_options(self, mqtt_config, device_info):
        """Select payloads must include options list."""
        entity = EntityDefinition(
            entity_type="select", object_id="output_target",
            name="Output Target", icon="mdi:monitor-speaker",
            has_command=True, options=["Board", "UI", "Both"],
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["options"] == ["Board", "UI", "Both"]

    def test_text_payload_has_length_limits(self, mqtt_config, device_info):
        """Text payloads must include min/max length."""
        entity = EntityDefinition(
            entity_type="text", object_id="send_message",
            name="Send Message", icon="mdi:message-draw",
            has_command=True, min_length=1, max_length=132,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["min"] == 1
        assert payload["max"] == 132

    def test_number_payload_has_range(self, mqtt_config, device_info):
        """Number payloads must include min, max, step, and unit."""
        entity = EntityDefinition(
            entity_type="number", object_id="refresh_interval",
            name="Refresh Interval", icon="mdi:timer-outline",
            has_command=True, min_value=30, max_value=3600, step=30, unit="s",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["min"] == 30
        assert payload["max"] == 3600
        assert payload["step"] == 30
        assert payload["unit_of_measurement"] == "s"

    def test_binary_sensor_device_class(self, mqtt_config, device_info):
        """Binary sensor with device_class should include it in payload."""
        entity = EntityDefinition(
            entity_type="binary_sensor", object_id="service_status",
            name="Status", icon="mdi:heart-pulse", device_class="running",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["device_class"] == "running"

    def test_invalid_entity_type_raises(self, mqtt_config, device_info):
        """Invalid entity type should raise ValueError."""
        entity = EntityDefinition(
            entity_type="invalid_type", object_id="test",
            name="Test", icon="mdi:test",
        )
        with pytest.raises(ValueError, match="Invalid entity type"):
            build_discovery_payload(mqtt_config, entity, device_info)

    def test_payload_device_info_linked(self, mqtt_config, device_info):
        """Payload must include the device info block."""
        entity = EntityDefinition(
            entity_type="sensor", object_id="current_page",
            name="Current Page", icon="mdi:page-layout-body",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["device"] == device_info

    def test_payload_json_serializable(self, mqtt_config, device_info):
        """All payloads must be JSON-serializable."""
        for entity in ENTITY_DEFINITIONS:
            payload = build_discovery_payload(mqtt_config, entity, device_info)
            serialized = json.dumps(payload)
            assert isinstance(serialized, str)
            # Verify round-trip
            deserialized = json.loads(serialized)
            assert deserialized["name"] == entity.name


class TestBuildAllDiscoveryMessages:
    """Tests for the complete discovery message generation."""

    def test_generates_all_entity_messages(self, mqtt_config):
        """Should generate one message per entity definition."""
        messages = build_all_discovery_messages(mqtt_config)
        assert len(messages) == len(ENTITY_DEFINITIONS)

    def test_messages_have_topic_and_payload(self, mqtt_config):
        """Each message must have 'topic' and 'payload' keys."""
        messages = build_all_discovery_messages(mqtt_config)
        for msg in messages:
            assert "topic" in msg
            assert "payload" in msg

    def test_all_payloads_are_valid_json(self, mqtt_config):
        """All payloads must be valid JSON strings."""
        messages = build_all_discovery_messages(mqtt_config)
        for msg in messages:
            parsed = json.loads(msg["payload"])
            assert isinstance(parsed, dict)

    def test_all_topics_start_with_prefix(self, mqtt_config):
        """All topics must start with the discovery prefix."""
        messages = build_all_discovery_messages(mqtt_config)
        for msg in messages:
            assert msg["topic"].startswith("homeassistant/")

    def test_all_topics_end_with_config(self, mqtt_config):
        """All discovery topics must end with /config."""
        messages = build_all_discovery_messages(mqtt_config)
        for msg in messages:
            assert msg["topic"].endswith("/config")

    def test_dynamic_page_names_injected(self, mqtt_config):
        """Active page entity should include provided page names as options."""
        page_names = ["Weather Dashboard", "Sports Scores", "Welcome Message"]
        messages = build_all_discovery_messages(mqtt_config, page_names=page_names)

        # Find the active_page message
        active_page_msg = None
        for msg in messages:
            payload = json.loads(msg["payload"])
            if payload.get("unique_id", "").endswith("_active_page"):
                active_page_msg = payload
                break

        assert active_page_msg is not None
        assert active_page_msg["options"] == page_names

    def test_sw_version_included(self, mqtt_config):
        """Software version should appear in device info."""
        messages = build_all_discovery_messages(mqtt_config, sw_version="2.1.33")
        payload = json.loads(messages[0]["payload"])
        assert payload["device"]["sw_version"] == "2.1.33"

    def test_configuration_url_included(self, mqtt_config):
        """Configuration URL should appear in device info when provided."""
        messages = build_all_discovery_messages(
            mqtt_config, configuration_url="http://192.168.1.50:4420"
        )
        payload = json.loads(messages[0]["payload"])
        assert payload["device"]["configuration_url"] == "http://192.168.1.50:4420"

    def test_unique_ids_across_all_entities(self, mqtt_config):
        """All unique_ids across all messages must be unique."""
        messages = build_all_discovery_messages(mqtt_config)
        unique_ids = set()
        for msg in messages:
            payload = json.loads(msg["payload"])
            uid = payload["unique_id"]
            assert uid not in unique_ids, f"Duplicate unique_id: {uid}"
            unique_ids.add(uid)

    def test_unique_topics_across_all_entities(self, mqtt_config):
        """All discovery topics must be unique."""
        messages = build_all_discovery_messages(mqtt_config)
        topics = [msg["topic"] for msg in messages]
        assert len(topics) == len(set(topics)), "Duplicate topics found"

    def test_custom_instance_id(self):
        """Custom instance ID should be reflected in all payloads."""
        config = MQTTConfig(
            enabled=True,
            instance_id="office_board",
            base_topic="office_board",
        )
        messages = build_all_discovery_messages(config)
        for msg in messages:
            payload = json.loads(msg["payload"])
            assert payload["unique_id"].startswith("office_board_")
            assert "office_board" in payload["device"]["identifiers"]
