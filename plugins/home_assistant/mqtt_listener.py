"""MQTT Statestream listener for Home Assistant plugin.

Subscribes to Home Assistant's MQTT Statestream integration topics and
maintains a real-time cache of entity states.  When HA publishes a state
change to the broker, this listener picks it up instantly — removing the
need for REST API polling.

Home Assistant Statestream topic format:
    {base_topic}/{domain}/{object_id}/state       → entity state value
    {base_topic}/{domain}/{object_id}/{attribute}  → entity attribute value

References:
    https://www.home-assistant.io/integrations/mqtt_statestream/
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _import_paho():
    """Lazy-import paho so tests can patch before first import."""
    import paho.mqtt.client as mqtt_client
    return mqtt_client


class HAStateStreamListener:
    """Subscribe to HA Statestream MQTT topics and keep entity state in memory.

    Thread-safe: the internal entity store is guarded by a lock so that the
    main plugin thread can read it while the MQTT callback thread writes.
    """

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._client: Any = None
        self._connected = False
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Connect to the MQTT broker and subscribe to statestream topics.

        Returns:
            True if the client was started successfully, False otherwise.
        """
        if self._running:
            logger.debug("Statestream listener already running")
            return True

        broker_host = self._resolve_broker_host()
        broker_port = self._resolve_broker_port()
        if not broker_host:
            logger.error("Statestream: no MQTT broker host configured")
            return False

        try:
            paho = _import_paho()
        except ImportError:
            logger.error("paho-mqtt is not installed — cannot start statestream listener")
            return False

        client_id = f"fiestaboard_ha_statestream_{int(time.time())}"
        try:
            self._client = paho.Client(
                callback_api_version=paho.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=paho.MQTTv311,
            )
        except Exception:
            # Fallback for older paho-mqtt without CallbackAPIVersion
            self._client = paho.Client(client_id=client_id)

        username = self._config.get(
            "statestream_broker_username",
            os.environ.get("MQTT_USERNAME") or None,
        )
        password = self._config.get(
            "statestream_broker_password",
            os.environ.get("MQTT_PASSWORD") or None,
        )
        if username:
            self._client.username_pw_set(username, password or "")

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        try:
            self._client.connect_async(broker_host, broker_port, keepalive=60)
            self._client.loop_start()
            self._running = True
            logger.info(
                "Statestream listener started (broker=%s:%s)",
                broker_host,
                broker_port,
            )
            return True
        except Exception as exc:
            logger.error("Statestream listener connect failed: %s", exc)
            self._running = False
            return False

    def stop(self) -> None:
        """Disconnect from the broker and release resources."""
        self._running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:
                logger.debug("Statestream disconnect: %s", exc)
        self._client = None
        self._connected = False
        logger.info("Statestream listener stopped")

    def is_connected(self) -> bool:
        """Return True when the MQTT connection is active."""
        return self._connected

    def get_entities(self) -> Dict[str, Dict[str, Any]]:
        """Return a deep-enough snapshot of the current entity store.

        Both the outer dict and each entity dict are copied so that callers
        can mutate the snapshot without affecting internal state.
        """
        with self._lock:
            return {
                eid: {
                    "state": edata.get("state", ""),
                    "attributes": dict(edata.get("attributes", {})),
                    "friendly_name": edata.get("friendly_name", eid),
                }
                for eid, edata in self._entities.items()
            }

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Return cached data for a single entity, or None."""
        with self._lock:
            return self._entities.get(entity_id)

    @property
    def entity_count(self) -> int:
        """Return the number of entities currently tracked."""
        with self._lock:
            return len(self._entities)

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """Called when the broker accepts the connection."""
        # reason_code may be an int or a ReasonCode depending on paho version
        rc = int(reason_code) if reason_code is not None else 0
        if rc != 0:
            logger.warning("Statestream connect failed (rc=%s)", rc)
            return
        self._connected = True
        base_topic = self._resolve_base_topic()
        subscribe_topic = f"{base_topic}/+/+/+"
        client.subscribe(subscribe_topic, qos=0)
        logger.info("Statestream subscribed to %s", subscribe_topic)

    def _on_disconnect(self, client, userdata, disconnect_flags=None, reason_code=None, properties=None):
        """Called when the broker disconnects."""
        self._connected = False
        rc = int(reason_code) if reason_code is not None else 0
        if rc != 0:
            logger.info("Statestream disconnected (rc=%s), will reconnect", rc)

    def _on_message(self, client, userdata, msg):
        """Process an incoming statestream message.

        Expected topic format:
            {base_topic}/{domain}/{object_id}/{field}

        where *field* is ``state`` or an attribute name (e.g.
        ``friendly_name``, ``unit_of_measurement``).
        """
        try:
            base_topic = self._resolve_base_topic()
            topic: str = msg.topic
            payload = msg.payload.decode("utf-8") if msg.payload else ""

            # Strip the base prefix to get domain/object_id/field
            prefix = f"{base_topic}/"
            if not topic.startswith(prefix):
                return
            remainder = topic[len(prefix):]
            parts = remainder.split("/", 2)
            if len(parts) != 3:
                return

            domain, object_id, field = parts
            entity_id = f"{domain}.{object_id}"

            with self._lock:
                if entity_id not in self._entities:
                    self._entities[entity_id] = {
                        "state": "",
                        "attributes": {},
                        "friendly_name": entity_id,
                    }
                entity = self._entities[entity_id]

                if field == "state":
                    entity["state"] = payload
                elif field == "friendly_name":
                    entity["friendly_name"] = payload
                    entity["attributes"]["friendly_name"] = payload
                else:
                    entity["attributes"][field] = payload

        except Exception as exc:
            logger.debug("Statestream message error: %s", exc)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_broker_host(self) -> str:
        """Resolve broker host from plugin config, then env, then default."""
        return (
            self._config.get("statestream_broker_host")
            or os.environ.get("MQTT_BROKER_HOST")
            or ""
        )

    def _resolve_broker_port(self) -> int:
        """Resolve broker port from plugin config, then env, then default."""
        port = self._config.get("statestream_broker_port")
        if port is not None:
            try:
                return int(port)
            except (ValueError, TypeError):
                pass
        env_port = os.environ.get("MQTT_BROKER_PORT")
        if env_port:
            try:
                return int(env_port)
            except (ValueError, TypeError):
                pass
        return 1883

    def _resolve_base_topic(self) -> str:
        """Resolve the statestream base topic."""
        return self._config.get("statestream_base_topic", "homeassistant/statestream")
