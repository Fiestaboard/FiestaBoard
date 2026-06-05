"""Tests for MQTT configuration."""

from src.mqtt.config import (
    DEFAULT_BASE_TOPIC,
    DEFAULT_BROKER_HOST,
    DEFAULT_BROKER_PORT,
    DEFAULT_DISCOVERY_PREFIX,
    DEFAULT_INSTANCE_ID,
    MQTTConfig,
)


class TestMQTTConfigDefaults:
    """Tests for MQTTConfig default values."""

    def test_disabled_by_default(self):
        """MQTT must be disabled by default — no impact on non-HA users."""
        config = MQTTConfig()
        assert config.enabled is False

    def test_default_broker_host(self):
        """Default broker host is localhost."""
        config = MQTTConfig()
        assert config.broker_host == "localhost"

    def test_default_broker_port(self):
        """Default MQTT port is 1883 (standard MQTT port)."""
        config = MQTTConfig()
        assert config.broker_port == 1883

    def test_default_discovery_prefix(self):
        """Default discovery prefix is 'homeassistant' (HA standard)."""
        config = MQTTConfig()
        assert config.discovery_prefix == "homeassistant"

    def test_default_base_topic(self):
        """Default base topic is 'fiestaboard'."""
        config = MQTTConfig()
        assert config.base_topic == "fiestaboard"

    def test_default_instance_id(self):
        """Default instance ID is 'fiestaboard_1'."""
        config = MQTTConfig()
        assert config.instance_id == "fiestaboard_1"

    def test_no_credentials_by_default(self):
        """No username/password by default."""
        config = MQTTConfig()
        assert config.username is None
        assert config.password is None


class TestMQTTConfigValidation:
    """Tests for MQTTConfig validation."""

    def test_disabled_config_always_valid(self):
        """When disabled, config is always valid regardless of other fields."""
        config = MQTTConfig(enabled=False, broker_host="", broker_port=0)
        errors = config.validate()
        assert len(errors) == 0

    def test_valid_enabled_config(self):
        """A properly configured enabled config should have no errors."""
        config = MQTTConfig(
            enabled=True,
            broker_host="192.168.1.100",
            broker_port=1883,
            instance_id="fiestaboard_1",
        )
        errors = config.validate()
        assert len(errors) == 0

    def test_empty_broker_host_invalid(self):
        """Empty broker host is invalid when enabled."""
        config = MQTTConfig(enabled=True, broker_host="")
        errors = config.validate()
        assert any("broker host" in e.lower() for e in errors)

    def test_whitespace_broker_host_invalid(self):
        """Whitespace-only broker host is invalid when enabled."""
        config = MQTTConfig(enabled=True, broker_host="   ")
        errors = config.validate()
        assert any("broker host" in e.lower() for e in errors)

    def test_port_zero_invalid(self):
        """Port 0 is invalid."""
        config = MQTTConfig(enabled=True, broker_port=0)
        errors = config.validate()
        assert any("port" in e.lower() for e in errors)

    def test_port_negative_invalid(self):
        """Negative port is invalid."""
        config = MQTTConfig(enabled=True, broker_port=-1)
        errors = config.validate()
        assert any("port" in e.lower() for e in errors)

    def test_port_too_high_invalid(self):
        """Port > 65535 is invalid."""
        config = MQTTConfig(enabled=True, broker_port=70000)
        errors = config.validate()
        assert any("port" in e.lower() for e in errors)

    def test_valid_port_range(self):
        """Valid port range: 1-65535."""
        for port in [1, 1883, 8883, 65535]:
            config = MQTTConfig(enabled=True, broker_port=port)
            errors = config.validate()
            assert not any("port" in e.lower() for e in errors), f"Port {port} should be valid"

    def test_empty_instance_id_invalid(self):
        """Empty instance ID is invalid when enabled."""
        config = MQTTConfig(enabled=True, instance_id="")
        errors = config.validate()
        assert any("instance id" in e.lower() for e in errors)

    def test_empty_base_topic_invalid(self):
        """Empty base topic is invalid when enabled."""
        config = MQTTConfig(enabled=True, base_topic="")
        errors = config.validate()
        assert any("base topic" in e.lower() for e in errors)

    def test_empty_discovery_prefix_invalid(self):
        """Empty discovery prefix is invalid when enabled."""
        config = MQTTConfig(enabled=True, discovery_prefix="")
        errors = config.validate()
        assert any("discovery prefix" in e.lower() for e in errors)

    def test_with_credentials(self):
        """Config with credentials should be valid."""
        config = MQTTConfig(
            enabled=True,
            broker_host="broker.local",
            username="mqtt_user",
            password="mqtt_pass",
        )
        errors = config.validate()
        assert len(errors) == 0


class TestMQTTConfigSerialization:
    """Tests for MQTTConfig to_dict / from_dict."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = MQTTConfig(
            enabled=True,
            broker_host="192.168.1.100",
            broker_port=1883,
            username="user",
            password="pass",
        )
        d = config.to_dict()
        assert d["enabled"] is True
        assert d["broker_host"] == "192.168.1.100"
        assert d["broker_port"] == 1883
        assert d["username"] == "user"
        assert d["password"] == "pass"

    def test_from_dict(self):
        """Test creation from dictionary."""
        d = {
            "enabled": True,
            "broker_host": "mqtt.local",
            "broker_port": 8883,
            "instance_id": "board_living_room",
        }
        config = MQTTConfig.from_dict(d)
        assert config.enabled is True
        assert config.broker_host == "mqtt.local"
        assert config.broker_port == 8883
        assert config.instance_id == "board_living_room"

    def test_from_dict_defaults(self):
        """Missing fields in dict should use defaults."""
        config = MQTTConfig.from_dict({})
        assert config.enabled is False
        assert config.broker_host == DEFAULT_BROKER_HOST
        assert config.broker_port == DEFAULT_BROKER_PORT
        assert config.discovery_prefix == DEFAULT_DISCOVERY_PREFIX
        assert config.base_topic == DEFAULT_BASE_TOPIC
        assert config.instance_id == DEFAULT_INSTANCE_ID

    def test_roundtrip(self):
        """to_dict then from_dict should produce equivalent config."""
        original = MQTTConfig(
            enabled=True,
            broker_host="test.local",
            broker_port=8883,
            username="admin",
            password="secret",
            discovery_prefix="ha",
            base_topic="fb",
            instance_id="fb_office",
        )
        restored = MQTTConfig.from_dict(original.to_dict())
        assert restored.enabled == original.enabled
        assert restored.broker_host == original.broker_host
        assert restored.broker_port == original.broker_port
        assert restored.username == original.username
        assert restored.password == original.password
        assert restored.discovery_prefix == original.discovery_prefix
        assert restored.base_topic == original.base_topic
        assert restored.instance_id == original.instance_id


class TestMQTTConfigFromEnv:
    """Tests for MQTTConfig.from_env() — environment variable loading."""

    def test_from_env_defaults(self):
        """Empty env dict should produce default config."""
        config = MQTTConfig.from_env({})
        assert config.enabled is False
        assert config.broker_host == DEFAULT_BROKER_HOST
        assert config.broker_port == DEFAULT_BROKER_PORT

    def test_from_env_enabled_true(self):
        """MQTT_ENABLED=true should enable MQTT."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": "true"})
        assert config.enabled is True

    def test_from_env_enabled_yes(self):
        """MQTT_ENABLED=yes should enable MQTT."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": "yes"})
        assert config.enabled is True

    def test_from_env_enabled_1(self):
        """MQTT_ENABLED=1 should enable MQTT."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": "1"})
        assert config.enabled is True

    def test_from_env_enabled_case_insensitive(self):
        """MQTT_ENABLED should be case-insensitive."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": "TRUE"})
        assert config.enabled is True

    def test_from_env_disabled_false(self):
        """MQTT_ENABLED=false should keep MQTT disabled."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": "false"})
        assert config.enabled is False

    def test_from_env_full_config(self):
        """Full environment configuration."""
        env = {
            "MQTT_ENABLED": "true",
            "MQTT_BROKER_HOST": "192.168.1.50",
            "MQTT_BROKER_PORT": "8883",
            "MQTT_USERNAME": "mqtt_user",
            "MQTT_PASSWORD": "mqtt_pass",
            "MQTT_DISCOVERY_PREFIX": "ha_discovery",
            "MQTT_BASE_TOPIC": "my_board",
            "MQTT_INSTANCE_ID": "fiestaboard_office",
        }
        config = MQTTConfig.from_env(env)
        assert config.enabled is True
        assert config.broker_host == "192.168.1.50"
        assert config.broker_port == 8883
        assert config.username == "mqtt_user"
        assert config.password == "mqtt_pass"
        assert config.discovery_prefix == "ha_discovery"
        assert config.base_topic == "my_board"
        assert config.instance_id == "fiestaboard_office"

    def test_from_env_invalid_port_uses_default(self):
        """Invalid port string should fall back to default."""
        config = MQTTConfig.from_env({"MQTT_BROKER_PORT": "not_a_number"})
        assert config.broker_port == DEFAULT_BROKER_PORT

    def test_from_env_empty_username_becomes_none(self):
        """Empty MQTT_USERNAME should become None."""
        config = MQTTConfig.from_env({"MQTT_USERNAME": ""})
        assert config.username is None

    def test_from_env_none_enabled_value(self):
        """Explicit None for MQTT_ENABLED should not crash."""
        config = MQTTConfig.from_env({"MQTT_ENABLED": None})
        assert config.enabled is False

    def test_from_env_none_broker_port_uses_default(self):
        """Explicit None for MQTT_BROKER_PORT should use default."""
        config = MQTTConfig.from_env({"MQTT_BROKER_PORT": None})
        assert config.broker_port == DEFAULT_BROKER_PORT

    def test_from_dict_string_port_converted(self):
        """String broker_port in dict should be converted to int."""
        config = MQTTConfig.from_dict({"broker_port": "8883"})
        assert config.broker_port == 8883
        assert isinstance(config.broker_port, int)

    def test_from_dict_invalid_port_uses_default(self):
        """Invalid broker_port string in dict should fall back to default."""
        config = MQTTConfig.from_dict({"broker_port": "not_a_number"})
        assert config.broker_port == DEFAULT_BROKER_PORT
