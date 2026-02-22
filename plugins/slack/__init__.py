"""
Slack Messages Plugin for FiestaBoard.

Displays recent messages from Slack channels using OAuth authentication.
"""

import logging
import os
from typing import Any, Dict, List
from datetime import datetime
import requests

from src.plugins.base import PluginBase, PluginResult

logger = logging.getLogger(__name__)


class SlackPlugin(PluginBase):
    """Slack messages plugin implementation.
    
    Fetches recent messages from a configured Slack channel using OAuth.
    """
    
    def __init__(self, manifest: Dict[str, Any]):
        """Initialize plugin with user cache."""
        super().__init__(manifest)
        self._user_cache: Dict[str, str] = {}  # Cache user_id -> display_name
    
    @property
    def plugin_id(self) -> str:
        """Return the plugin ID matching manifest.json."""
        return "slack"
    
    def fetch_data(self) -> PluginResult:
        """
        Fetch recent messages from Slack channel.
        
        Returns:
            PluginResult with message data or error.
        """
        access_token = self.config.get("access_token")
        channel_id = self.config.get("channel_id")
        max_messages = self.config.get("max_messages", 5)
        show_timestamp = self.config.get("show_timestamp", True)
        
        if not access_token:
            return PluginResult(
                available=False,
                error="Not authenticated. Please complete OAuth flow."
            )
        
        if not channel_id:
            return PluginResult(
                available=False,
                error="No channel selected. Please configure a channel."
            )
        
        try:
            # Fetch channel info
            channel_info = self._get_channel_info(access_token, channel_id)
            channel_name = channel_info.get("name", "Unknown")
            
            # Fetch recent messages
            messages = self._fetch_messages(access_token, channel_id, max_messages)
            
            # Format messages
            formatted_messages = []
            for msg in messages:
                user_name = self._get_user_name(access_token, msg.get("user", ""))
                text = msg.get("text", "")
                timestamp = msg.get("ts", "")
                
                # Format timestamp
                time_str = ""
                if show_timestamp and timestamp:
                    try:
                        dt = datetime.fromtimestamp(float(timestamp))
                        time_str = dt.strftime("%I:%M %p")
                    except (ValueError, TypeError):
                        time_str = ""
                
                # Truncate text to fit board
                text_truncated = self._truncate_text(text, 66)
                
                formatted_messages.append({
                    "user": user_name[:22],
                    "text": text_truncated,
                    "time": time_str[:22],
                    "formatted": f"{user_name[:22]}: {text_truncated}"
                })
            
            # Prepare result data
            data = {
                "channel_name": channel_name[:22],
                "message_count": len(formatted_messages),
                "status": f"{len(formatted_messages)} msg" if len(formatted_messages) != 1 else "1 msg",
                "messages": formatted_messages
            }
            
            # Add last message info if available
            if formatted_messages:
                data["last_message_text"] = formatted_messages[0]["text"]
                data["last_message_user"] = formatted_messages[0]["user"]
                data["last_message_time"] = formatted_messages[0]["time"]
            else:
                data["last_message_text"] = "No messages"
                data["last_message_user"] = ""
                data["last_message_time"] = ""
            
            return PluginResult(
                available=True,
                data=data
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Slack data: {e}", exc_info=True)
            return PluginResult(
                available=False,
                error=f"Network error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error fetching Slack data: {e}", exc_info=True)
            return PluginResult(
                available=False,
                error=str(e)
            )
    
    def _get_channel_info(self, access_token: str, channel_id: str) -> Dict[str, Any]:
        """Get channel information from Slack API."""
        url = "https://slack.com/api/conversations.info"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"channel": channel_id}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            raise Exception(f"Slack API error: {error}")
        
        return data.get("channel", {})
    
    def _fetch_messages(self, access_token: str, channel_id: str, limit: int) -> List[Dict[str, Any]]:
        """Fetch recent messages from a Slack channel."""
        url = "https://slack.com/api/conversations.history"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "channel": channel_id,
            "limit": limit
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if not data.get("ok"):
            error = data.get("error", "Unknown error")
            raise Exception(f"Slack API error: {error}")
        
        return data.get("messages", [])
    
    def _get_user_name(self, access_token: str, user_id: str) -> str:
        """Get user display name from Slack API with caching."""
        if not user_id:
            return "Unknown"
        
        # Check cache first
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        
        try:
            url = "https://slack.com/api/users.info"
            headers = {"Authorization": f"Bearer {access_token}"}
            params = {"user": user_id}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("ok") and data.get("user"):
                user = data["user"]
                # Prefer display name, fall back to real name or username
                display_name = (
                    user.get("profile", {}).get("display_name") or
                    user.get("profile", {}).get("real_name") or
                    user.get("name") or
                    "Unknown"
                )
                # Cache the result
                self._user_cache[user_id] = display_name
                return display_name
        except Exception as e:
            logger.debug(f"Could not fetch user name for {user_id}: {e}")
        
        # Cache unknown users too to avoid repeated failures
        self._user_cache[user_id] = "Unknown"
        return "Unknown"
    
    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max length with ellipsis if needed."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate plugin configuration.
        
        Args:
            config: The configuration dictionary to validate
            
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        max_messages = config.get("max_messages", 5)
        if not isinstance(max_messages, int) or max_messages < 1 or max_messages > 20:
            errors.append("Max messages must be between 1 and 20")
        
        refresh_seconds = config.get("refresh_seconds", 60)
        if not isinstance(refresh_seconds, int) or refresh_seconds < 30:
            errors.append("Refresh interval must be at least 30 seconds")
        
        return errors
    
    def cleanup(self) -> None:
        """Cleanup when plugin is disabled."""
        # Clear user cache on cleanup
        self._user_cache.clear()
        logger.info(f"Plugin {self.plugin_id} cleanup")
