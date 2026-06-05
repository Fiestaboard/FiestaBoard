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
    ENTITY_DEFINITIONS,
    VALID_ENTITY_TYPES,
    EntityDefinition,
    build_all_discovery_messages,
    build_device_info,
    build_discovery_payload,
    build_discovery_topic,
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
        """FiestaBoard should expose 24 entities to HA."""
        assert len(ENTITY_DEFINITIONS) == 24

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
            assert entity.name and entity.name.strip(), f"Entity '{entity.object_id}' has empty name"

    def test_all_entities_have_icons(self):
        """All entities must have MDI icons."""
        for entity in ENTITY_DEFINITIONS:
            assert entity.icon.startswith("mdi:"), f"Entity '{entity.object_id}' icon must start with 'mdi:'"

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
        assert "transition_style" in select_ids

    def test_sensor_entities(self):
        """Should have sensor entities for current page, message, version, page count, and diagnostics."""
        sensors = [e for e in ENTITY_DEFINITIONS if e.entity_type == "sensor"]
        sensor_ids = {e.object_id for e in sensors}
        assert "current_page" in sensor_ids
        assert "current_message" in sensor_ids
        assert "version" in sensor_ids
        assert "page_count" in sensor_ids
        assert "uptime" in sensor_ids
        assert "board_api_mode" in sensor_ids
        assert "active_plugins" in sensor_ids
        assert "last_display_update" in sensor_ids
        assert "output_target" in sensor_ids

    def test_binary_sensor_entities(self):
        """Should have binary sensor entities for status and silence."""
        binary = [e for e in ENTITY_DEFINITIONS if e.entity_type == "binary_sensor"]
        binary_ids = {e.object_id for e in binary}
        assert "service_status" in binary_ids
        assert "silence_mode" in binary_ids

    def test_button_entities(self):
        """Should have button entities for refresh, blank board, and page navigation."""
        buttons = [e for e in ENTITY_DEFINITIONS if e.entity_type == "button"]
        assert len(buttons) == 4
        button_ids = {e.object_id for e in buttons}
        assert "refresh_display" in button_ids
        assert "blank_board" in button_ids
        assert "next_page" in button_ids
        assert "previous_page" in button_ids

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
        controllable = {e.object_id for e in ENTITY_DEFINITIONS if e.has_command}
        # Verify we have a reasonable number of controllable entities
        assert len(controllable) >= 5, "Should have at least 5 controllable entities"
        for entity in ENTITY_DEFINITIONS:
            if entity.has_command:
                assert entity.object_id in controllable

    def test_readonly_entities_no_commands(self):
        """Read-only entities should not have commands."""
        readonly = {e.object_id for e in ENTITY_DEFINITIONS if not e.has_command}
        # Verify we have some read-only entities
        assert len(readonly) >= 2, "Should have at least 2 read-only entities"
        for entity in ENTITY_DEFINITIONS:
            if not entity.has_command:
                assert entity.object_id in readonly

    def test_blank_board_entity(self):
        """Blank board button should exist and be controllable."""
        blank = [e for e in ENTITY_DEFINITIONS if e.object_id == "blank_board"]
        assert len(blank) == 1
        assert blank[0].entity_type == "button"
        assert blank[0].has_command is True

    def test_version_sensor(self):
        """Version sensor should be read-only."""
        version = [e for e in ENTITY_DEFINITIONS if e.object_id == "version"]
        assert len(version) == 1
        assert version[0].entity_type == "sensor"
        assert version[0].has_command is False

    def test_page_count_sensor(self):
        """Page count sensor should be read-only."""
        page_count = [e for e in ENTITY_DEFINITIONS if e.object_id == "page_count"]
        assert len(page_count) == 1
        assert page_count[0].entity_type == "sensor"
        assert page_count[0].has_command is False

    def test_transition_style_entity(self):
        """Transition style select should have valid animation options."""
        transition = [e for e in ENTITY_DEFINITIONS if e.object_id == "transition_style"]
        assert len(transition) == 1
        assert transition[0].entity_type == "select"
        assert transition[0].has_command is True
        assert "column" in transition[0].options
        assert "random" in transition[0].options
        assert len(transition[0].options) == 6


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
            entity_type="switch",
            object_id="schedule_enabled",
            name="Schedule",
            icon="mdi:calendar-clock",
            has_command=True,
        )
        topic = build_discovery_topic(mqtt_config, entity)
        assert topic == "homeassistant/switch/fiestaboard_1/schedule_enabled/config"

    def test_topic_uses_config_prefix(self):
        """Topic should use the configured discovery prefix."""
        config = MQTTConfig(discovery_prefix="my_ha", instance_id="board_1")
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="current_page",
            name="Current Page",
            icon="mdi:page-layout-body",
        )
        topic = build_discovery_topic(config, entity)
        assert topic.startswith("my_ha/")

    def test_topic_uses_instance_id(self):
        """Topic should include the instance ID as node_id."""
        config = MQTTConfig(instance_id="office_board")
        entity = EntityDefinition(
            entity_type="button",
            object_id="refresh_display",
            name="Refresh",
            icon="mdi:refresh",
            has_command=True,
        )
        topic = build_discovery_topic(config, entity)
        assert "office_board" in topic


class TestDiscoveryPayloads:
    """Tests for individual discovery payload generation."""

    def test_payload_required_fields(self, mqtt_config, device_info):
        """Every payload must have name, unique_id, state_topic, availability, and device."""
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="current_page",
            name="Current Page",
            icon="mdi:page-layout-body",
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
            entity_type="switch",
            object_id="schedule_enabled",
            name="Schedule",
            icon="mdi:calendar-clock",
            has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["unique_id"] == "fiestaboard_1_schedule_enabled"

    def test_payload_state_topic(self, mqtt_config, device_info):
        """State topic must be {base_topic}/{object_id}/state."""
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="current_page",
            name="Current Page",
            icon="mdi:page-layout-body",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["state_topic"] == "fiestaboard/current_page/state"

    def test_payload_command_topic_present(self, mqtt_config, device_info):
        """Controllable entities must have a command_topic."""
        entity = EntityDefinition(
            entity_type="switch",
            object_id="schedule_enabled",
            name="Schedule",
            icon="mdi:calendar-clock",
            has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "command_topic" in payload
        assert payload["command_topic"] == "fiestaboard/schedule_enabled/set"

    def test_payload_command_topic_absent(self, mqtt_config, device_info):
        """Read-only entities must NOT have a command_topic."""
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="current_page",
            name="Current Page",
            icon="mdi:page-layout-body",
            has_command=False,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "command_topic" not in payload

    def test_payload_availability(self, mqtt_config, device_info):
        """Availability must use LWT topic with online/offline payloads."""
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="service_status",
            name="Status",
            icon="mdi:heart-pulse",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["availability_topic"] == "fiestaboard/status"
        assert payload["payload_available"] == "online"
        assert payload["payload_not_available"] == "offline"

    def test_switch_payload_has_on_off(self, mqtt_config, device_info):
        """Switch payloads must include payload_on and payload_off."""
        entity = EntityDefinition(
            entity_type="switch",
            object_id="schedule_enabled",
            name="Schedule",
            icon="mdi:calendar-clock",
            has_command=True,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["payload_on"] == "ON"
        assert payload["payload_off"] == "OFF"

    def test_select_payload_has_options(self, mqtt_config, device_info):
        """Select payloads must include options list."""
        entity = EntityDefinition(
            entity_type="select",
            object_id="transition_style",
            name="Transition Style",
            icon="mdi:transition",
            has_command=True,
            options=["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"],
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["options"] == ["column", "reverse-column", "edges-to-center", "row", "diagonal", "random"]

    def test_text_payload_has_length_limits(self, mqtt_config, device_info):
        """Text payloads must include min/max length."""
        entity = EntityDefinition(
            entity_type="text",
            object_id="send_message",
            name="Send Message",
            icon="mdi:message-draw",
            has_command=True,
            min_length=1,
            max_length=132,
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["min"] == 1
        assert payload["max"] == 132

    def test_number_payload_has_range(self, mqtt_config, device_info):
        """Number payloads must include min, max, step, and unit."""
        entity = EntityDefinition(
            entity_type="number",
            object_id="refresh_interval",
            name="Refresh Interval",
            icon="mdi:timer-outline",
            has_command=True,
            min_value=30,
            max_value=3600,
            step=30,
            unit="s",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["min"] == 30
        assert payload["max"] == 3600
        assert payload["step"] == 30
        assert payload["unit_of_measurement"] == "s"

    def test_binary_sensor_device_class(self, mqtt_config, device_info):
        """Binary sensor with device_class should include it in payload."""
        entity = EntityDefinition(
            entity_type="binary_sensor",
            object_id="service_status",
            name="Status",
            icon="mdi:heart-pulse",
            device_class="running",
        )
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["device_class"] == "running"

    def test_invalid_entity_type_raises(self, mqtt_config, device_info):
        """Invalid entity type should raise ValueError."""
        entity = EntityDefinition(
            entity_type="invalid_type",
            object_id="test",
            name="Test",
            icon="mdi:test",
        )
        with pytest.raises(ValueError, match="Invalid entity type"):
            build_discovery_payload(mqtt_config, entity, device_info)

    def test_payload_device_info_linked(self, mqtt_config, device_info):
        """Payload must include the device info block."""
        entity = EntityDefinition(
            entity_type="sensor",
            object_id="current_page",
            name="Current Page",
            icon="mdi:page-layout-body",
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
        messages = build_all_discovery_messages(mqtt_config, configuration_url="http://192.168.1.50:4420")
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


class TestEntityCategorySupport:
    """Tests for entity_category field in discovery payloads."""

    def test_diagnostic_entities_tagged(self, mqtt_config, device_info):
        """Diagnostic entities must have entity_category='diagnostic' in payload."""
        diagnostic_ids = {
            "service_status",
            "version",
            "uptime",
            "board_api_mode",
            "active_plugins",
            "last_display_update",
            "output_target",
        }
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in diagnostic_ids:
                payload = build_discovery_payload(mqtt_config, entity, device_info)
                assert payload.get("entity_category") == "diagnostic", (
                    f"Entity '{entity.object_id}' should have entity_category='diagnostic'"
                )

    def test_config_entities_tagged(self, mqtt_config, device_info):
        """Config entities must have entity_category='config' in payload."""
        config_ids = {"refresh_interval"}
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in config_ids:
                payload = build_discovery_payload(mqtt_config, entity, device_info)
                assert payload.get("entity_category") == "config", (
                    f"Entity '{entity.object_id}' should have entity_category='config'"
                )

    def test_non_categorized_entities_no_category(self, mqtt_config, device_info):
        """Entities without a category must NOT include entity_category."""
        uncategorized = {
            "schedule_enabled",
            "display_service",
            "active_page",
            "transition_style",
            "current_page",
            "current_message",
            "silence_mode",
            "page_count",
            "refresh_display",
            "blank_board",
            "send_message",
            "next_page",
            "previous_page",
        }
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in uncategorized:
                payload = build_discovery_payload(mqtt_config, entity, device_info)
                assert "entity_category" not in payload, f"Entity '{entity.object_id}' should not have entity_category"


class TestSensorClassSupport:
    """Tests for device_class and state_class in sensor discovery payloads."""

    def test_uptime_sensor_has_duration_class(self, mqtt_config, device_info):
        """Uptime sensor should have device_class='duration' and unit='s'."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "uptime")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["device_class"] == "duration"
        assert payload["state_class"] == "total_increasing"
        assert payload["unit_of_measurement"] == "s"

    def test_page_count_state_class(self, mqtt_config, device_info):
        """Page count sensor should have state_class='measurement'."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "page_count")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["state_class"] == "measurement"

    def test_active_plugins_state_class(self, mqtt_config, device_info):
        """Active plugins sensor should have state_class='measurement'."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "active_plugins")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["state_class"] == "measurement"

    def test_version_no_state_class(self, mqtt_config, device_info):
        """Version sensor should NOT have state_class (it's text)."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "version")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "state_class" not in payload


class TestJsonAttributesSupport:
    """Tests for json_attributes_topic in discovery payloads."""

    def test_current_page_has_attributes_topic(self, mqtt_config, device_info):
        """Current page sensor should include json_attributes_topic."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "current_page")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "json_attributes_topic" in payload
        assert payload["json_attributes_topic"] == "fiestaboard/current_page/attributes"

    def test_entities_without_attributes(self, mqtt_config, device_info):
        """Entities without json_attributes should not have json_attributes_topic."""
        no_attrs = {"schedule_enabled", "version", "page_count"}
        for entity in ENTITY_DEFINITIONS:
            if entity.object_id in no_attrs:
                payload = build_discovery_payload(mqtt_config, entity, device_info)
                assert "json_attributes_topic" not in payload, (
                    f"Entity '{entity.object_id}' should not have json_attributes_topic"
                )


class TestEventEntitySupport:
    """Tests for MQTT event entity discovery payloads."""

    def test_event_type_is_valid(self):
        """Event must be in VALID_ENTITY_TYPES."""
        assert "event" in VALID_ENTITY_TYPES

    def test_event_entities_exist(self):
        """Should have event entities for display_updated, page_changed, and settings_changed."""
        events = [e for e in ENTITY_DEFINITIONS if e.entity_type == "event"]
        assert len(events) == 3
        event_ids = {e.object_id for e in events}
        assert "display_updated" in event_ids
        assert "page_changed" in event_ids
        assert "settings_changed" in event_ids

    def test_display_updated_event_types(self, mqtt_config, device_info):
        """display_updated event should declare its event types."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "display_updated")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["event_types"] == ["message_sent", "page_refreshed", "board_blanked", "page_navigated"]

    def test_page_changed_event_types(self, mqtt_config, device_info):
        """page_changed event should declare its event types."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "page_changed")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["event_types"] == ["page_switched"]

    def test_event_payload_has_state_topic(self, mqtt_config, device_info):
        """Event entities must have a state_topic for receiving event data."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "display_updated")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["state_topic"] == "fiestaboard/display_updated/state"

    def test_event_entity_no_command_topic(self, mqtt_config, device_info):
        """Event entities should not have command_topic (events are read-only)."""
        for entity in ENTITY_DEFINITIONS:
            if entity.entity_type == "event":
                payload = build_discovery_payload(mqtt_config, entity, device_info)
                assert "command_topic" not in payload


class TestDiagnosticSensors:
    """Tests for the new diagnostic sensor entity definitions."""

    def test_uptime_sensor(self):
        """Uptime sensor should be a diagnostic sensor with duration class."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "uptime")
        assert entity.entity_type == "sensor"
        assert entity.entity_category == "diagnostic"
        assert entity.device_class == "duration"
        assert entity.state_class == "total_increasing"
        assert entity.unit == "s"
        assert entity.has_command is False

    def test_board_api_mode_sensor(self):
        """Board API mode sensor should be a diagnostic sensor."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "board_api_mode")
        assert entity.entity_type == "sensor"
        assert entity.entity_category == "diagnostic"
        assert entity.has_command is False

    def test_active_plugins_sensor(self):
        """Active plugins sensor should be a diagnostic sensor with measurement class."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "active_plugins")
        assert entity.entity_type == "sensor"
        assert entity.entity_category == "diagnostic"
        assert entity.state_class == "measurement"
        assert entity.has_command is False

    def test_last_display_update_sensor(self):
        """Last display update sensor should be a diagnostic sensor with timestamp class."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "last_display_update")
        assert entity.entity_type == "sensor"
        assert entity.entity_category == "diagnostic"
        assert entity.device_class == "timestamp"
        assert entity.has_command is False

    def test_output_target_sensor(self):
        """Output target sensor should be a diagnostic sensor."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "output_target")
        assert entity.entity_type == "sensor"
        assert entity.entity_category == "diagnostic"
        assert entity.has_command is False


class TestNavigationButtons:
    """Tests for next_page and previous_page button entities."""

    def test_next_page_button(self):
        """Next page button should be controllable."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "next_page")
        assert entity.entity_type == "button"
        assert entity.has_command is True
        assert entity.icon == "mdi:page-next"

    def test_previous_page_button(self):
        """Previous page button should be controllable."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "previous_page")
        assert entity.entity_type == "button"
        assert entity.has_command is True
        assert entity.icon == "mdi:page-previous"


class TestSettingsChangedEvent:
    """Tests for the settings_changed event entity."""

    def test_settings_changed_event_exists(self):
        """settings_changed event should exist."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "settings_changed")
        assert entity.entity_type == "event"

    def test_settings_changed_event_types(self, mqtt_config, device_info):
        """settings_changed event should declare schedule, service, and silence event types."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "settings_changed")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "schedule_toggled" in payload["event_types"]
        assert "service_toggled" in payload["event_types"]
        assert "silence_mode_changed" in payload["event_types"]

    def test_settings_changed_no_command_topic(self, mqtt_config, device_info):
        """settings_changed event should not have command_topic."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "settings_changed")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert "command_topic" not in payload


class TestTransitionStrategySourceOfTruth:
    """Tests that transition strategies come from a single source of truth."""

    def test_transition_options_match_board_client(self):
        """Transition style options must match VALID_STRATEGIES from board_client."""
        from src.board_client import VALID_STRATEGIES

        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "transition_style")
        assert entity.options == list(VALID_STRATEGIES)

    def test_last_display_update_has_timestamp_class(self, mqtt_config, device_info):
        """last_display_update sensor should have device_class='timestamp'."""
        entity = next(e for e in ENTITY_DEFINITIONS if e.object_id == "last_display_update")
        payload = build_discovery_payload(mqtt_config, entity, device_info)
        assert payload["device_class"] == "timestamp"
