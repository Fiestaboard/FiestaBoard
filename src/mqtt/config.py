"""MQTT configuration for Home Assistant integration.

Defines configuration dataclasses and validation for the MQTT connection
settings. All settings are opt-in and disabled by default.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# Valid entity types supported by HA MQTT Discovery
VALID_ENTITY_TYPES = ["switch", "select", "sensor", "binary_sensor", "button", "text", "number"]

# Default MQTT settings
DEFAULT_BROKER_HOST = "localhost"
DEFAULT_BROKER_PORT = 1883
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_BASE_TOPIC = "fiestaboard"
DEFAULT_INSTANCE_ID = "fiestaboard_1"


@dataclass
class MQTTConfig:
    """MQTT connection and discovery configuration.
    
    Attributes:
        enabled: Whether MQTT integration is active (default: False)
        broker_host: MQTT broker hostname or IP
        broker_port: MQTT broker port (default: 1883)
        username: Optional MQTT username for authentication
        password: Optional MQTT password for authentication
        discovery_prefix: HA discovery topic prefix (default: 'homeassistant')
        base_topic: Base topic for FiestaBoard state/commands (default: 'fiestaboard')
        instance_id: Unique instance identifier for multi-board setups
    """
    enabled: bool = False
    broker_host: str = DEFAULT_BROKER_HOST
    broker_port: int = DEFAULT_BROKER_PORT
    username: Optional[str] = None
    password: Optional[str] = None
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX
    base_topic: str = DEFAULT_BASE_TOPIC
    instance_id: str = DEFAULT_INSTANCE_ID
    
    def validate(self) -> List[str]:
        """Validate the MQTT configuration.
        
        Returns:
            List of validation error messages. Empty list means valid.
        """
        errors = []
        
        if self.enabled:
            if not self.broker_host or not self.broker_host.strip():
                errors.append("MQTT broker host is required when MQTT is enabled")
            
            if not isinstance(self.broker_port, int) or self.broker_port < 1 or self.broker_port > 65535:
                errors.append("MQTT broker port must be between 1 and 65535")
            
            if not self.instance_id or not self.instance_id.strip():
                errors.append("MQTT instance ID is required")
            
            if not self.base_topic or not self.base_topic.strip():
                errors.append("MQTT base topic is required")
            
            if not self.discovery_prefix or not self.discovery_prefix.strip():
                errors.append("MQTT discovery prefix is required")
        
        return errors
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "username": self.username,
            "password": self.password,
            "discovery_prefix": self.discovery_prefix,
            "base_topic": self.base_topic,
            "instance_id": self.instance_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MQTTConfig":
        """Create from dictionary.
        
        Args:
            data: Dictionary with configuration values.
            
        Returns:
            MQTTConfig instance with validated defaults for missing fields.
        """
        return cls(
            enabled=data.get("enabled", False),
            broker_host=data.get("broker_host", DEFAULT_BROKER_HOST),
            broker_port=data.get("broker_port", DEFAULT_BROKER_PORT),
            username=data.get("username"),
            password=data.get("password"),
            discovery_prefix=data.get("discovery_prefix", DEFAULT_DISCOVERY_PREFIX),
            base_topic=data.get("base_topic", DEFAULT_BASE_TOPIC),
            instance_id=data.get("instance_id", DEFAULT_INSTANCE_ID),
        )

    @classmethod
    def from_env(cls, env: dict) -> "MQTTConfig":
        """Create from environment variables dictionary.
        
        Args:
            env: Dictionary of environment variables (e.g., os.environ).
            
        Returns:
            MQTTConfig instance.
        """
        port_str = env.get("MQTT_BROKER_PORT", str(DEFAULT_BROKER_PORT))
        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = DEFAULT_BROKER_PORT
        
        return cls(
            enabled=env.get("MQTT_ENABLED", "false").lower() in ("true", "1", "yes"),
            broker_host=env.get("MQTT_BROKER_HOST", DEFAULT_BROKER_HOST),
            broker_port=port,
            username=env.get("MQTT_USERNAME") or None,
            password=env.get("MQTT_PASSWORD") or None,
            discovery_prefix=env.get("MQTT_DISCOVERY_PREFIX", DEFAULT_DISCOVERY_PREFIX),
            base_topic=env.get("MQTT_BASE_TOPIC", DEFAULT_BASE_TOPIC),
            instance_id=env.get("MQTT_INSTANCE_ID", DEFAULT_INSTANCE_ID),
        )
