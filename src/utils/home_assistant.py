"""Home Assistant data source for house status information."""

import logging

import requests

logger = logging.getLogger(__name__)


class HomeAssistantSource:
    """Fetches house status from Home Assistant API."""

    def __init__(self, base_url: str, access_token: str, timeout: int = 5):
        """
        Initialize Home Assistant source.

        Args:
            base_url: Home Assistant base URL (e.g., "http://192.168.1.100:8123")
            access_token: Long-lived access token
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        self.api_url = f"{self.base_url}/api"

    def get_entity_state(self, entity_id: str) -> dict | None:
        """
        Get state of a single entity.

        Args:
            entity_id: Home Assistant entity ID (e.g., "binary_sensor.front_door")

        Returns:
            Dictionary with entity state, or None if failed
        """
        try:
            url = f"{self.api_url}/states/{entity_id}"
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get entity state for {entity_id}: {e}")
            return None

    def get_house_status(self, entities: list[dict[str, str]]) -> dict[str, dict]:
        """
        Get status for multiple entities.

        Args:
            entities: List of dicts with 'entity_id' and 'name' keys
                     Example: [{"entity_id": "binary_sensor.front_door", "name": "Front Door"}]

        Returns:
            Dictionary mapping entity names to their status info
        """
        status = {}

        for entity_config in entities:
            entity_id = entity_config.get("entity_id")
            name = entity_config.get("name", entity_id)

            if not entity_id:
                continue

            state_data = self.get_entity_state(entity_id)

            if state_data:
                state = state_data.get("state", "unknown")
                attributes = state_data.get("attributes", {})

                # Determine if open/closed, on/off, etc.
                # Common patterns:
                # - binary_sensor: "on" = open/active, "off" = closed/inactive
                # - sensor: use state directly
                # - cover: "open" = open, "closed" = closed

                status[name] = {
                    "entity_id": entity_id,
                    "state": state,
                    "attributes": attributes,
                    "friendly_name": attributes.get("friendly_name", name),
                }
            else:
                status[name] = {"entity_id": entity_id, "state": "unavailable", "error": True}

        return status

    def get_all_entities_for_context(self) -> dict[str, dict]:
        """
        Get all entity states for template context.

        Returns:
            Dict mapping entity_id to state data with attributes
        """
        try:
            url = f"{self.api_url}/states"
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            entities = response.json()

            # Transform to dict keyed by entity_id
            result = {}
            for entity in entities:
                entity_id = entity["entity_id"]
                result[entity_id] = {
                    "state": entity["state"],
                    "attributes": entity.get("attributes", {}),
                    "friendly_name": entity.get("attributes", {}).get("friendly_name", entity_id),
                }
            return result
        except Exception as e:
            logger.error(f"Failed to fetch all entities: {e}")
            return {}

    def test_connection(self) -> bool:
        """
        Test connection to Home Assistant.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.api_url}/"
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Home Assistant connection test failed: {e}")
            return False


def get_home_assistant_source() -> HomeAssistantSource | None:
    """Get configured Home Assistant source instance.

    Reads the ``plugins.home_assistant`` config (the legacy ``features.*``
    branch was retired in #1761).
    """
    from src.config_manager import get_config_manager

    plugin_cfg = get_config_manager().get_plugin_config("home_assistant") or {}
    base_url = plugin_cfg.get("base_url") or ""
    access_token = plugin_cfg.get("access_token") or ""
    timeout = plugin_cfg.get("timeout", 5)
    enabled = bool(plugin_cfg.get("enabled"))

    if not enabled:
        return None
    if not base_url or not access_token:
        logger.warning("Home Assistant enabled but URL or access token not configured")
        return None

    return HomeAssistantSource(base_url=base_url, access_token=access_token, timeout=timeout)
