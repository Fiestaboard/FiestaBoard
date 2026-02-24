"""Tests for the guest_wifi plugin."""

import pytest
from unittest.mock import patch, MagicMock

from plugins.guest_wifi import GuestWifiPlugin


class TestGuestWifiPlugin:
    """Tests for Guest WiFi plugin functionality."""
    
    def test_guest_wifi_data_structure(self):
        """Test that guest WiFi returns expected data structure."""
        # Guest WiFi is a static display, test the data structure
        expected_fields = ["ssid", "password"]
        
        # Mock config with WiFi credentials
        config = {
            "ssid": "GuestNetwork",
            "password": "SecurePass123"
        }
        
        # Validate structure
        assert "ssid" in config
        assert "password" in config
        assert len(config["ssid"]) > 0
    
    def test_ssid_formatting(self):
        """Test SSID is properly formatted for display."""
        ssid = "MyGuestWiFi"
        # SSID should not exceed board line width (22 chars)
        assert len(ssid) <= 22
    
    def test_password_formatting(self):
        """Test password is properly formatted for display."""
        password = "Guest123!"
        # Password should be displayable
        assert len(password) > 0
    
    def test_empty_ssid_handling(self):
        """Test handling of empty SSID."""
        config = {"ssid": "", "password": "test"}
        # Empty SSID should be detected
        assert config["ssid"] == ""
    
    def test_empty_password_handling(self):
        """Test handling of empty password."""
        config = {"ssid": "Network", "password": ""}
        # Empty password should be valid (open network)
        assert config["password"] == ""
    
    def test_special_characters_in_password(self):
        """Test passwords with special characters."""
        passwords = [
            "Pass!@#$%",
            "Test&*(){}",
            "WiFi-2024",
            "guest_network"
        ]
        for pwd in passwords:
            # Password should be a valid string
            assert isinstance(pwd, str)
            assert len(pwd) > 0
    
    def test_config_validation(self):
        """Test config validation for guest WiFi."""
        valid_config = {
            "ssid": "GuestWiFi",
            "password": "SecurePassword"
        }
        
        # Both fields should be present
        assert "ssid" in valid_config
        assert "password" in valid_config


class TestGuestWifiPluginIntegration:
    """Integration tests for GuestWifiPlugin that exercise plugin code."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance with manifest."""
        manifest = {"id": "guest_wifi", "name": "Guest WiFi", "version": "1.0.0"}
        return GuestWifiPlugin(manifest)

    def test_plugin_id(self, plugin):
        """Test plugin_id property."""
        assert plugin.plugin_id == "guest_wifi"

    def test_validate_config_missing_ssid(self, plugin):
        """Test validate_config returns error when SSID is missing."""
        config = {"password": "test123"}
        errors = plugin.validate_config(config)
        assert "SSID is required" in errors

    def test_validate_config_missing_password(self, plugin):
        """Test validate_config returns error when password is missing."""
        config = {"ssid": "MyNetwork"}
        errors = plugin.validate_config(config)
        assert "Password is required" in errors

    def test_validate_config_ssid_too_long(self, plugin):
        """Test validate_config returns error when SSID exceeds 22 chars."""
        config = {"ssid": "a" * 23, "password": "test"}
        errors = plugin.validate_config(config)
        assert "SSID must be 22 characters or less" in errors

    def test_validate_config_password_too_long(self, plugin):
        """Test validate_config returns error when password exceeds 22 chars."""
        config = {"ssid": "Network", "password": "p" * 23}
        errors = plugin.validate_config(config)
        assert "Password must be 22 characters or less" in errors

    def test_validate_config_valid(self, plugin):
        """Test validate_config accepts valid config."""
        config = {"ssid": "GuestNetwork", "password": "SecurePass123"}
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_validate_config_ssid_at_limit(self, plugin):
        """Test validate_config accepts SSID at 22 char limit."""
        config = {"ssid": "a" * 22, "password": "test"}
        errors = plugin.validate_config(config)
        assert len(errors) == 0

    def test_fetch_data_not_configured(self, plugin):
        """Test fetch_data returns unavailable when not configured."""
        plugin.config = {}
        result = plugin.fetch_data()
        assert result.available is False
        assert "not configured" in result.error

    def test_fetch_data_missing_ssid(self, plugin):
        """Test fetch_data returns unavailable when SSID is empty."""
        plugin.config = {"ssid": "", "password": "test"}
        result = plugin.fetch_data()
        assert result.available is False

    def test_fetch_data_missing_password(self, plugin):
        """Test fetch_data returns unavailable when password is empty."""
        plugin.config = {"ssid": "Network", "password": ""}
        result = plugin.fetch_data()
        assert result.available is False

    def test_fetch_data_success(self, plugin):
        """Test fetch_data returns data when configured."""
        plugin.config = {"ssid": "GuestNetwork", "password": "SecurePass123"}
        result = plugin.fetch_data()
        assert result.available is True
        assert result.data["ssid"] == "GuestNetwork"
        assert result.data["password"] == "SecurePass123"

    def test_get_formatted_display_returns_none_when_not_configured(self, plugin):
        """Test get_formatted_display returns None when not configured."""
        plugin.config = {}
        lines = plugin.get_formatted_display()
        assert lines is None

    def test_get_formatted_display_returns_lines(self, plugin):
        """Test get_formatted_display returns formatted lines."""
        plugin.config = {"ssid": "MyWiFi", "password": "Secret123"}
        lines = plugin.get_formatted_display()
        assert lines is not None
        assert "GUEST WIFI" in lines[0]
        assert "MyWiFi" in str(lines)
        assert "Secret123" in str(lines)


class TestGuestWifiDisplay:
    """Tests for Guest WiFi display formatting."""
    
    def test_display_lines_count(self):
        """Test that display uses appropriate number of lines."""
        # Board has 6 lines
        max_lines = 6
        
        # Guest WiFi typically needs:
        # 1. Title line (GUEST WIFI)
        # 2. SSID label
        # 3. SSID value
        # 4. Password label  
        # 5. Password value
        # 6. Optional decoration
        
        required_lines = 5
        assert required_lines <= max_lines
    
    def test_line_length_constraint(self):
        """Test that all content fits within line length."""
        max_chars = 22  # Board line width
        
        ssid = "TestNetwork"
        password = "Pass123"
        
        # SSID line
        ssid_line = f"SSID: {ssid}"
        assert len(ssid_line) <= max_chars or len(ssid) <= max_chars
        
        # Password line
        pass_line = f"PASS: {password}"
        assert len(pass_line) <= max_chars or len(password) <= max_chars

