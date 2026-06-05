"""MQTT integration for Home Assistant auto-discovery.

This module provides MQTT-based integration with Home Assistant,
allowing FiestaBoard to be automatically discovered and controlled
as a native HA device via MQTT Discovery protocol.

The module is opt-in and disabled by default. When enabled, FiestaBoard
connects to an MQTT broker and publishes Home Assistant MQTT Discovery
messages, making it appear as a device in HA with zero configuration
on the HA side.

References:
    - MQTT protocol: ISO/IEC 20922 (OASIS standard)
    - HA MQTT Discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
    - paho-mqtt client: https://github.com/eclipse/paho.mqtt.python
"""

from .client import MQTTClient, get_mqtt_client, set_mqtt_client_instance
from .config import MQTTConfig

__all__ = [
    "MQTTClient",
    "MQTTConfig",
    "get_mqtt_client",
    "set_mqtt_client_instance",
]
