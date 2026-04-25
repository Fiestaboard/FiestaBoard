"""MQTT client for Home Assistant discovery and control.

Connects to an MQTT broker, publishes discovery payloads and state,
subscribes to command topics, and runs a periodic state sync.
"""

import logging
import threading
import time
from typing import Optional

from .config import MQTTConfig
from .discovery import build_all_discovery_messages

logger = logging.getLogger(__name__)

# Lazy import so tests can patch before import
def _get_paho_client():
    import paho.mqtt.client as mqtt_client
    return mqtt_client


class MQTTClient:
    """MQTT client that publishes HA discovery and state, and handles commands."""

    def __init__(self, config: MQTTConfig):
        self.config = config
        self._client = None
        self._state_publisher = None
        self._command_handler = None
        self._sync_thread: Optional[threading.Thread] = None
        self._sync_interval = 30
        self._running = False
        self._connected = False

    def set_state_publisher(self, publisher: "StatePublisher") -> None:
        """Set the state publisher (called from state module to avoid circular import)."""
        self._state_publisher = publisher

    def set_command_handler(self, handler: "CommandHandler") -> None:
        """Set the command handler (called from commands module)."""
        self._command_handler = handler

    def start(self) -> None:
        """Connect to the broker and start the client loop."""
        if self._running:
            logger.warning("MQTT client already running")
            return
        errors = self.config.validate()
        if errors:
            logger.error("MQTT config invalid: %s", errors)
            return
        paho = _get_paho_client()
        client_id = f"{self.config.instance_id}_{int(time.time())}"
        self._client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=paho.MQTTv311,
        )
        if self.config.username:
            self._client.username_pw_set(self.config.username, self.config.password or "")
        # Last Will: if we disconnect unexpectedly, broker publishes offline
        will_topic = f"{self.config.base_topic}/status"
        self._client.will_set(
            will_topic,
            payload="offline",
            qos=1,
            retain=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        try:
            self._client.connect_async(
                self.config.broker_host,
                self.config.broker_port,
                keepalive=60,
            )
            self._client.loop_start()
            self._running = True
            logger.info(
                "MQTT client started (broker=%s:%s)",
                self.config.broker_host,
                self.config.broker_port,
            )
        except Exception as e:
            logger.error("MQTT connect failed: %s", e)
            self._running = False
            return
        # Start periodic state sync
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()

    def stop(self) -> None:
        """Publish offline, disconnect, and stop the client."""
        self._running = False
        if self._client and self._connected:
            try:
                self.publish_state_raw(f"{self.config.base_topic}/status", "offline", retain=True)
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as e:
                logger.debug("MQTT disconnect: %s", e)
        self._client = None
        self._connected = False
        logger.info("MQTT client stopped")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            logger.warning("MQTT connect failed with reason_code=%s", reason_code)
            return
        self._connected = True
        logger.info("MQTT connected to broker")
        self._publish_discovery()
        self.publish_state_raw(f"{self.config.base_topic}/status", "online", retain=True)
        # Subscribe to all command topics: fiestaboard/+/set
        subscribe_topic = f"{self.config.base_topic}/+/set"
        client.subscribe(subscribe_topic, qos=1)
        logger.debug("Subscribed to %s", subscribe_topic)
        if self._state_publisher:
            try:
                self._state_publisher.gather_and_publish()
            except Exception as e:
                logger.warning("Initial state publish failed: %s", e)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        self._connected = False
        if reason_code != 0:
            logger.info("MQTT disconnected (reason_code=%s), will reconnect via paho", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8") if msg.payload else ""
            # Topic format: {base_topic}/{object_id}/set
            prefix = f"{self.config.base_topic}/"
            suffix = "/set"
            if topic.startswith(prefix) and topic.endswith(suffix):
                object_id = topic[len(prefix) : -len(suffix)]
                if self._command_handler:
                    self._command_handler.handle(object_id, payload)
                else:
                    logger.warning("MQTT command received but no command handler set")
        except Exception as e:
            logger.exception("Error handling MQTT message: %s", e)

    def _publish_discovery(self) -> None:
        """Publish all HA discovery messages (retained)."""
        try:
            import src as src_pkg
            sw_version = getattr(src_pkg, "__version__", "1.0.0")
        except Exception:
            sw_version = "1.0.0"
        configuration_url = self.config.external_url or None
        page_names = None
        try:
            from src.pages.service import get_page_service
            pages = get_page_service().list_pages()
            page_names = [p.name for p in pages]
        except Exception:
            logger.debug("Could not retrieve page names for MQTT discovery")
        messages = build_all_discovery_messages(
            self.config,
            sw_version=sw_version,
            configuration_url=configuration_url,
            page_names=page_names or [],
        )
        for msg in messages:
            self._client.publish(
                msg["topic"],
                msg["payload"],
                qos=1,
                retain=True,
            )
        logger.info("Published %d MQTT discovery messages", len(messages))

    def publish_state(self, object_id: str, value: str) -> None:
        """Publish state for an entity (e.g. schedule_enabled -> ON)."""
        topic = f"{self.config.base_topic}/{object_id}/state"
        self.publish_state_raw(topic, value, retain=True)

    def publish_attributes(self, object_id: str, json_payload: str) -> None:
        """Publish JSON attributes for an entity (e.g. current_page -> {"page_id": "..."})."""
        topic = f"{self.config.base_topic}/{object_id}/attributes"
        self.publish_state_raw(topic, json_payload, retain=True)

    def publish_state_raw(self, topic: str, payload: str, retain: bool = True) -> None:
        """Publish a state payload to a topic."""
        if not self._client or not self._connected:
            return
        try:
            self._client.publish(topic, payload, qos=1, retain=retain)
        except Exception as e:
            logger.debug("MQTT publish failed: %s", e)

    def _sync_loop(self) -> None:
        """Background thread: periodically publish state updates."""
        while self._running:
            time.sleep(self._sync_interval)
            if not self._running or not self._connected:
                continue
            if self._state_publisher:
                try:
                    self._state_publisher.gather_and_publish()
                except Exception as e:
                    logger.debug("State sync failed: %s", e)

    def is_connected(self) -> bool:
        return self._connected

    def is_running(self) -> bool:
        return self._running


# Singleton instance (set when client is started from lifespan)
_mqtt_client_instance: Optional["MQTTClient"] = None


def get_mqtt_client() -> Optional["MQTTClient"]:
    """Return the running MQTT client instance, or None if not started."""
    return _mqtt_client_instance


def set_mqtt_client_instance(client: Optional["MQTTClient"]) -> None:
    """Set the global MQTT client instance (used by lifespan)."""
    global _mqtt_client_instance
    _mqtt_client_instance = client


# Forward references for type hints
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .state import StatePublisher
    from .commands import CommandHandler
