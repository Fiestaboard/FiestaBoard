"""Tests for Slack Messages plugin."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Import the plugin
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from plugins.slack import SlackPlugin


@pytest.fixture
def manifest():
    """Load manifest.json for testing."""
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def plugin(manifest):
    """Create a SlackPlugin instance for testing."""
    return SlackPlugin(manifest)


class TestSlackPlugin:
    """Test cases for Slack plugin."""
    
    def test_plugin_id(self, plugin):
        """Test plugin ID matches manifest."""
        assert plugin.plugin_id == "slack"
    
    def test_fetch_data_no_token(self, plugin):
        """Test fetch_data without access token."""
        plugin.config = {}
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "Not authenticated" in result.error
    
    def test_fetch_data_no_channel(self, plugin):
        """Test fetch_data without channel ID."""
        plugin.config = {"access_token": "xoxp-test-token"}
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "No channel" in result.error
    
    @patch('plugins.slack.requests.get')
    def test_fetch_data_success(self, mock_get, plugin):
        """Test successful data fetch."""
        # Configure plugin
        plugin.config = {
            "access_token": "xoxp-test-token",
            "channel_id": "C01234567",
            "max_messages": 2,
            "show_timestamp": True
        }
        
        # Mock API responses
        mock_responses = [
            # conversations.info response
            Mock(
                status_code=200,
                json=lambda: {
                    "ok": True,
                    "channel": {"name": "general"}
                }
            ),
            # conversations.history response
            Mock(
                status_code=200,
                json=lambda: {
                    "ok": True,
                    "messages": [
                        {
                            "user": "U01234567",
                            "text": "Hello world!",
                            "ts": "1234567890.123456"
                        },
                        {
                            "user": "U01234568",
                            "text": "Test message",
                            "ts": "1234567880.123456"
                        }
                    ]
                }
            ),
            # users.info response for first user
            Mock(
                status_code=200,
                json=lambda: {
                    "ok": True,
                    "user": {
                        "name": "user1",
                        "profile": {
                            "display_name": "User One",
                            "real_name": "User One"
                        }
                    }
                }
            ),
            # users.info response for second user
            Mock(
                status_code=200,
                json=lambda: {
                    "ok": True,
                    "user": {
                        "name": "user2",
                        "profile": {
                            "display_name": "User Two",
                            "real_name": "User Two"
                        }
                    }
                }
            ),
        ]
        mock_get.side_effect = mock_responses
        
        result = plugin.fetch_data()
        
        assert result.available is True
        assert result.data is not None
        assert result.data["channel_name"] == "general"
        assert result.data["message_count"] == 2
        assert len(result.data["messages"]) == 2
        assert result.data["messages"][0]["user"] == "User One"
        assert result.data["messages"][0]["text"] == "Hello world!"
    
    @patch('plugins.slack.requests.get')
    def test_fetch_data_api_error(self, mock_get, plugin):
        """Test handling of Slack API errors."""
        plugin.config = {
            "access_token": "xoxp-test-token",
            "channel_id": "C01234567"
        }
        
        # Mock error response
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "ok": False,
                "error": "channel_not_found"
            }
        )
        
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "channel_not_found" in result.error
    
    @patch('plugins.slack.requests.get')
    def test_fetch_data_network_error(self, mock_get, plugin):
        """Test handling of network errors."""
        plugin.config = {
            "access_token": "xoxp-test-token",
            "channel_id": "C01234567"
        }
        
        # Mock network error
        mock_get.side_effect = Exception("Network error")
        
        result = plugin.fetch_data()
        
        assert result.available is False
        assert "error" in result.error.lower()
    
    def test_truncate_text(self, plugin):
        """Test text truncation."""
        short_text = "Hello"
        assert plugin._truncate_text(short_text, 10) == "Hello"
        
        long_text = "This is a very long message that needs truncation"
        truncated = plugin._truncate_text(long_text, 20)
        assert len(truncated) == 20
        assert truncated.endswith("...")
    
    def test_validate_config_valid(self, plugin):
        """Test validation of valid config."""
        config = {
            "max_messages": 5,
            "refresh_seconds": 60
        }
        errors = plugin.validate_config(config)
        assert len(errors) == 0
    
    def test_validate_config_invalid_max_messages(self, plugin):
        """Test validation with invalid max_messages."""
        config = {
            "max_messages": 0,
            "refresh_seconds": 60
        }
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("Max messages" in err for err in errors)
    
    def test_validate_config_invalid_refresh(self, plugin):
        """Test validation with invalid refresh interval."""
        config = {
            "max_messages": 5,
            "refresh_seconds": 10
        }
        errors = plugin.validate_config(config)
        assert len(errors) > 0
        assert any("Refresh interval" in err for err in errors)
    
    def test_manifest_structure(self, manifest):
        """Test manifest.json has required fields."""
        assert manifest["id"] == "slack"
        assert manifest["name"]
        assert manifest["version"]
        assert manifest["requires_oauth"] is True
        assert "oauth_config" in manifest
        assert "settings_schema" in manifest
        assert "variables" in manifest
    
    def test_oauth_config(self, manifest):
        """Test OAuth configuration in manifest."""
        oauth_config = manifest["oauth_config"]
        assert oauth_config["provider"] == "slack"
        assert "authorize_url" in oauth_config
        assert "token_url" in oauth_config
        assert "scopes" in oauth_config
        assert len(oauth_config["scopes"]) > 0
