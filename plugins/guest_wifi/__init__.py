"""Guest WiFi plugin for FiestaBoard.

Displays guest WiFi credentials on your board.
"""

from typing import Any, Dict, List, Optional
import logging

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class GuestWifiPlugin(PluginBase):
    """Guest WiFi credentials plugin.
    
    Displays configured SSID and password for guest access.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize the guest wifi plugin."""
        super().__init__(manifest)
    
    @property
    def plugin_id(self) -> str:
        return "guest_wifi"
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate guest wifi configuration."""
        errors = []
        
        if not config.get("ssid"):
            errors.append("SSID is required")
        elif len(config["ssid"]) > 22:
            errors.append("SSID must be 22 characters or less")
        
        if not config.get("password"):
            errors.append("Password is required")
        elif len(config["password"]) > 22:
            errors.append("Password must be 22 characters or less")
        
        return errors
    
    def fetch_data(self) -> PluginResult:
        """Fetch guest wifi data (from config)."""
        ssid = self.config.get("ssid", "")
        password = self.config.get("password", "")
        
        if not ssid or not password:
            return PluginResult(
                available=False,
                error="Guest WiFi not configured"
            )
        
        data = {
            "ssid": ssid,
            "password": password,
        }
        
        return PluginResult(
            available=True,
            data=data
        )
    
    def get_formatted_display(self) -> Optional[List[str]]:
        """Return default formatted guest wifi display."""
        result = self.fetch_data()
        if not result.available or not result.data:
            return None
        
        data = result.data
        lines = [
            "GUEST WIFI".center(22),
            "",
            f"NETWORK: {data['ssid']}"[:22],
            "",
            f"PASSWORD: {data['password']}"[:22],
            "",
        ]
        
        return lines


# Export the plugin class
Plugin = GuestWifiPlugin

