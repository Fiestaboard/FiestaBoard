"""Home Assistant plugin for FiestaBoard.

Displays entity states from Home Assistant with dynamic entity access.
Supports two data modes:

1. **REST polling** (default) — periodically calls the HA REST API.
2. **MQTT Statestream** — subscribes to HA's MQTT Statestream integration
   for real-time entity updates pushed over MQTT.  When enabled the plugin
   receives state changes instantly instead of waiting for the next poll
   cycle, significantly reducing latency and HA server load.  Falls back
   to REST polling if the MQTT connection is lost.
"""

from typing import Any, Dict, List, Optional
import logging
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class HomeAssistantPlugin(PluginBase):
    """Home Assistant integration plugin.
    
    Fetches entity states from Home Assistant API or via MQTT Statestream.
    Supports dynamic entity access via template variables.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the home assistant plugin."""
        super().__init__(manifest)
        self._cache: Optional[Dict[str, Any]] = None
        self._all_entities: Optional[Dict[str, Dict]] = None
        self._mqtt_listener: Optional["HAStateStreamListener"] = None
    
    @property
    def plugin_id(self) -> str:
        return "home_assistant"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate home assistant configuration."""
        errors = []
        mqtt_enabled = config.get("mqtt_statestream", False)
        
        if not mqtt_enabled:
            if not config.get("base_url"):
                errors.append("Home Assistant URL is required")
            if not config.get("access_token"):
                errors.append("Access token is required")
        
        return errors
    
    # ------------------------------------------------------------------
    # MQTT Statestream lifecycle
    # ------------------------------------------------------------------

    def _ensure_mqtt_listener(self) -> bool:
        """Start the MQTT statestream listener if configured and not running.

        Returns True when the listener is connected, False otherwise.
        """
        if not self.config.get("mqtt_statestream", False):
            return False

        if self._mqtt_listener is not None and self._mqtt_listener.is_connected():
            return True

        # Lazy import to avoid hard dependency at module level
        from .mqtt_listener import HAStateStreamListener

        if self._mqtt_listener is None:
            self._mqtt_listener = HAStateStreamListener(self.config)

        if not self._mqtt_listener.is_connected():
            self._mqtt_listener.start()

        return self._mqtt_listener.is_connected()

    def _stop_mqtt_listener(self) -> None:
        """Stop and discard the MQTT statestream listener."""
        if self._mqtt_listener is not None:
            self._mqtt_listener.stop()
            self._mqtt_listener = None

    # ------------------------------------------------------------------
    # REST helpers (unchanged)
    # ------------------------------------------------------------------

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        token = self.config.get("access_token", "")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def _get_api_url(self) -> str:
        """Get API base URL."""
        base_url = self.config.get("base_url", "").rstrip('/')
        return f"{base_url}/api"
    
    def test_connection(self) -> bool:
        """Test connection to Home Assistant."""
        try:
            timeout = self.config.get("timeout", 5)
            response = requests.get(
                f"{self._get_api_url()}/",
                headers=self._get_headers(),
                timeout=timeout
            )
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Home Assistant connection test failed: {e}")
            return False
    
    def _get_entity_state(self, entity_id: str) -> Optional[Dict]:
        """Get state of a single entity."""
        try:
            timeout = self.config.get("timeout", 5)
            response = requests.get(
                f"{self._get_api_url()}/states/{entity_id}",
                headers=self._get_headers(),
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Failed to get entity {entity_id}: {e}")
            return None
    
    def _fetch_all_entities(self) -> Dict[str, Dict]:
        """Fetch all entity states for template context."""
        try:
            timeout = self.config.get("timeout", 5)
            response = requests.get(
                f"{self._get_api_url()}/states",
                headers=self._get_headers(),
                timeout=timeout
            )
            response.raise_for_status()
            entities = response.json()
            
            # Transform to dict keyed by entity_id
            result = {}
            for entity in entities:
                entity_id = entity["entity_id"]
                # Store with both full id and dotted notation
                result[entity_id] = {
                    "state": entity["state"],
                    "attributes": entity.get("attributes", {}),
                    "friendly_name": entity.get("attributes", {}).get("friendly_name", entity_id)
                }
            return result
        except Exception as e:
            logger.error(f"Failed to fetch all entities: {e}")
            return {}

    # ------------------------------------------------------------------
    # Core data fetch
    # ------------------------------------------------------------------
    
    def fetch_data(self) -> PluginResult:
        """Fetch home assistant data.

        When MQTT statestream mode is active and connected, entity data is
        read directly from the listener's in-memory cache — no REST call is
        made.  If the listener is not connected (yet), the plugin falls back
        to REST polling transparently.
        """
        mqtt_mode = self.config.get("mqtt_statestream", False)

        # --- MQTT Statestream path ---
        if mqtt_mode:
            mqtt_connected = self._ensure_mqtt_listener()
            if mqtt_connected and self._mqtt_listener is not None:
                return self._build_result_from_mqtt()

            # Not connected yet — fall back to REST if credentials are present
            logger.debug("Statestream not connected; falling back to REST")
            if not self.config.get("base_url") or not self.config.get("access_token"):
                # No REST credentials to fall back on — report the MQTT state
                return PluginResult(
                    available=True,
                    data={
                        "connected": "Waiting",
                        "entity_count": 0,
                        "data_source": "mqtt_statestream",
                        "entities": {},
                    },
                )

        # --- REST polling path ---
        base_url = self.config.get("base_url")
        access_token = self.config.get("access_token")
        
        if not base_url or not access_token:
            return PluginResult(
                available=False,
                error="Home Assistant not configured"
            )
        
        # Test connection
        if not self.test_connection():
            return PluginResult(
                available=False,
                error="Failed to connect to Home Assistant"
            )
        
        try:
            # Fetch all entities for dynamic access
            all_entities = self._fetch_all_entities()
            self._all_entities = all_entities
            
            # Build result data structure
            # Include all entities in a flat structure for template access
            data = {
                "connected": "Yes",
                "entity_count": len(all_entities),
                "data_source": "rest",
            }
            
            # Add each entity to data for template access
            # Convert entity_id dots to nested structure
            # e.g., sensor.temperature -> data["sensor.temperature"] = {...}
            for entity_id, entity_data in all_entities.items():
                data[entity_id] = {
                    "state": entity_data["state"],
                    "friendly_name": entity_data["friendly_name"],
                    **entity_data.get("attributes", {})
                }
            
            # Also fetch configured entities specifically
            entities_config = self.config.get("entities", [])
            configured_entities = {}
            
            for entity_conf in entities_config:
                entity_id = entity_conf.get("entity_id")
                name = entity_conf.get("name", entity_id)
                
                if entity_id and entity_id in all_entities:
                    configured_entities[name] = {
                        "entity_id": entity_id,
                        "state": all_entities[entity_id]["state"],
                        "friendly_name": all_entities[entity_id]["friendly_name"],
                    }
            
            data["entities"] = configured_entities
            
            self._cache = data
            return PluginResult(available=True, data=data)
            
        except Exception as e:
            logger.exception("Error fetching Home Assistant data")
            return PluginResult(available=False, error=str(e))

    # ------------------------------------------------------------------
    # MQTT result builder
    # ------------------------------------------------------------------

    def _build_result_from_mqtt(self) -> PluginResult:
        """Build a PluginResult using the MQTT listener's entity cache."""
        assert self._mqtt_listener is not None
        all_entities = self._mqtt_listener.get_entities()
        self._all_entities = all_entities

        data = {
            "connected": "Yes",
            "entity_count": len(all_entities),
            "data_source": "mqtt_statestream",
        }

        for entity_id, entity_data in all_entities.items():
            data[entity_id] = {
                "state": entity_data.get("state", ""),
                "friendly_name": entity_data.get("friendly_name", entity_id),
                **entity_data.get("attributes", {}),
            }

        # Resolve configured entities
        entities_config = self.config.get("entities", [])
        configured_entities = {}
        for entity_conf in entities_config:
            entity_id = entity_conf.get("entity_id")
            name = entity_conf.get("name", entity_id)
            if entity_id and entity_id in all_entities:
                configured_entities[name] = {
                    "entity_id": entity_id,
                    "state": all_entities[entity_id].get("state", ""),
                    "friendly_name": all_entities[entity_id].get("friendly_name", entity_id),
                }
        data["entities"] = configured_entities

        self._cache = data
        return PluginResult(available=True, data=data)

    # ------------------------------------------------------------------
    # Entity access
    # ------------------------------------------------------------------
    
    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Get a specific entity's data (for dynamic template access)."""
        # Try MQTT listener first
        if self._mqtt_listener is not None and self._mqtt_listener.is_connected():
            entity = self._mqtt_listener.get_entity(entity_id)
            if entity is not None:
                return entity

        if self._all_entities and entity_id in self._all_entities:
            return self._all_entities[entity_id]
        
        # Fallback to direct fetch
        return self._get_entity_state(entity_id)
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted display."""
        if not self._cache:
            result = self.fetch_data()
            if not result.available:
                return None
        
        data = self._cache
        entities = data.get("entities", {})
        lines = ["HOME ASSISTANT".center(22), ""]
        
        for name, entity_data in list(entities.items())[:4]:
            state = entity_data.get("state", "?")
            line = f"{name}: {state}"
            lines.append(line[:22])
        
        while len(lines) < 6:
            lines.append("")
        
        return lines[:6]

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """Restart MQTT listener when statestream settings change."""
        mqtt_keys = {
            "mqtt_statestream",
            "statestream_base_topic",
            "statestream_broker_host",
            "statestream_broker_port",
            "statestream_broker_username",
            "statestream_broker_password",
        }
        old_mqtt = {k: old_config.get(k) for k in mqtt_keys}
        new_mqtt = {k: new_config.get(k) for k in mqtt_keys}

        if old_mqtt != new_mqtt:
            self._stop_mqtt_listener()

    def cleanup(self) -> None:
        """Stop MQTT listener when plugin is disabled."""
        self._stop_mqtt_listener()


# Export the plugin class
Plugin = HomeAssistantPlugin

