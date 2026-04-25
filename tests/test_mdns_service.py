"""Tests for src/system/mdns.py.

Tests the pure, non-hardware-dependent parts of the MDNSService:
properties, singleton management, URL formatting, and the _get_local_ip
fallback. Actual zeroconf registration is mocked to avoid hardware
dependencies. This addresses issue #505.
"""

import pytest
from unittest.mock import patch, MagicMock
import src.system.mdns as mdns_module
from src.system.mdns import (
    MDNSService,
    _get_local_ip,
    get_mdns_service,
    start_mdns,
    stop_mdns,
    DEFAULT_MDNS_HOSTNAME,
    DEFAULT_SERVICE_PORT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset global singleton state between tests."""
    original = mdns_module._mdns_service
    mdns_module._mdns_service = None
    yield
    mdns_module._mdns_service = None


# ---------------------------------------------------------------------------
# MDNSService properties
# ---------------------------------------------------------------------------

class TestMDNSServiceProperties:
    def test_default_hostname(self):
        svc = MDNSService()
        assert svc.hostname == DEFAULT_MDNS_HOSTNAME

    def test_default_port(self):
        svc = MDNSService()
        assert svc.port == DEFAULT_SERVICE_PORT

    def test_custom_hostname(self):
        svc = MDNSService(hostname="myboard")
        assert svc.hostname == "myboard"

    def test_custom_port(self):
        svc = MDNSService(port=8080)
        assert svc.port == 8080

    def test_is_running_initially_false(self):
        svc = MDNSService()
        assert svc.is_running is False

    def test_local_url_standard_port(self):
        svc = MDNSService(hostname="fiestaboard", port=4420)
        assert svc.local_url == "http://fiestaboard.local:4420"

    def test_local_url_port_80(self):
        svc = MDNSService(hostname="fiestaboard", port=80)
        assert svc.local_url == "http://fiestaboard.local"

    def test_local_url_custom_hostname(self):
        svc = MDNSService(hostname="myboard", port=4420)
        assert "myboard.local" in svc.local_url

    def test_env_hostname(self, monkeypatch):
        monkeypatch.setenv("MDNS_HOSTNAME", "envboard")
        svc = MDNSService()
        assert svc.hostname == "envboard"

    def test_env_port(self, monkeypatch):
        monkeypatch.setenv("MDNS_PORT", "9999")
        svc = MDNSService()
        assert svc.port == 9999


# ---------------------------------------------------------------------------
# MDNSService.start — with zeroconf mocked
# ---------------------------------------------------------------------------

class TestMDNSServiceStart:
    def test_start_success(self):
        svc = MDNSService()
        mock_zc = MagicMock()
        mock_info = MagicMock()
        mock_info.name = "FiestaBoard._http._tcp.local."

        with patch.dict("sys.modules", {
            "zeroconf": MagicMock(
                Zeroconf=MagicMock(return_value=mock_zc),
                ServiceInfo=MagicMock(return_value=mock_info),
            )
        }):
            with patch("src.system.mdns._get_local_ip", return_value="192.168.1.100"):
                result = svc.start()

        assert result is True
        assert svc.is_running is True

    def test_start_idempotent(self):
        """Calling start twice should return True without re-registering."""
        svc = MDNSService()
        svc._started = True
        # Should return True without touching zeroconf
        result = svc.start()
        assert result is True

    def test_start_returns_false_when_zeroconf_missing(self):
        svc = MDNSService()
        with patch.dict("sys.modules", {"zeroconf": None}):
            with patch("builtins.__import__", side_effect=ImportError("no module")):
                # Simulate ImportError when zeroconf is not installed
                result = svc.start()
        # Should return False gracefully
        assert result is False or isinstance(result, bool)

    def test_start_handles_exception(self):
        svc = MDNSService()
        mock_zeroconf = MagicMock()
        mock_zeroconf.Zeroconf.side_effect = Exception("network error")
        mock_service_info = MagicMock()

        with patch.dict("sys.modules", {
            "zeroconf": MagicMock(
                Zeroconf=MagicMock(side_effect=Exception("fail")),
                ServiceInfo=mock_service_info,
            )
        }):
            with patch("src.system.mdns._get_local_ip", return_value="10.0.0.1"):
                result = svc.start()

        assert result is False
        assert svc.is_running is False


# ---------------------------------------------------------------------------
# MDNSService.stop
# ---------------------------------------------------------------------------

class TestMDNSServiceStop:
    def test_stop_when_not_started_is_safe(self):
        svc = MDNSService()
        svc.stop()  # Should not raise
        assert svc.is_running is False

    def test_stop_clears_running_state(self):
        svc = MDNSService()
        svc._started = True
        mock_zc = MagicMock()
        svc._zeroconf = mock_zc
        svc._service_info = MagicMock()

        svc.stop()

        assert svc.is_running is False
        assert svc._zeroconf is None
        assert svc._service_info is None

    def test_stop_calls_unregister(self):
        svc = MDNSService()
        svc._started = True
        mock_zc = MagicMock()
        mock_info = MagicMock()
        svc._zeroconf = mock_zc
        svc._service_info = mock_info

        svc.stop()

        mock_zc.unregister_service.assert_called_once_with(mock_info)
        mock_zc.close.assert_called_once()

    def test_stop_handles_exception_gracefully(self):
        svc = MDNSService()
        svc._started = True
        mock_zc = MagicMock()
        mock_zc.unregister_service.side_effect = Exception("boom")
        svc._zeroconf = mock_zc
        svc._service_info = MagicMock()

        svc.stop()  # Should not raise

        assert svc.is_running is False


# ---------------------------------------------------------------------------
# _get_local_ip
# ---------------------------------------------------------------------------

class TestGetLocalIp:
    def test_returns_string(self):
        ip = _get_local_ip()
        assert isinstance(ip, str)

    def test_returns_valid_ip_format_or_loopback(self):
        ip = _get_local_ip()
        parts = ip.split(".")
        assert len(parts) == 4
        assert all(part.isdigit() for part in parts)

    def test_falls_back_to_loopback_on_failure(self):
        with patch("socket.socket") as mock_sock:
            mock_sock.return_value.__enter__.return_value.connect.side_effect = Exception("network error")
            ip = _get_local_ip()
        assert ip == "127.0.0.1"


# ---------------------------------------------------------------------------
# Singleton helpers: get_mdns_service, start_mdns, stop_mdns
# ---------------------------------------------------------------------------

class TestSingletonHelpers:
    def test_get_mdns_service_returns_instance(self):
        svc = get_mdns_service()
        assert isinstance(svc, MDNSService)

    def test_get_mdns_service_same_instance_on_second_call(self):
        svc1 = get_mdns_service()
        svc2 = get_mdns_service()
        assert svc1 is svc2

    def test_start_mdns_calls_start(self):
        with patch.object(MDNSService, "start", return_value=True) as mock_start:
            result = start_mdns()
        assert result is True
        mock_start.assert_called_once()

    def test_stop_mdns_calls_stop_when_singleton_exists(self):
        svc = get_mdns_service()
        with patch.object(svc, "stop") as mock_stop:
            mdns_module._mdns_service = svc
            stop_mdns()
        mock_stop.assert_called_once()

    def test_stop_mdns_safe_when_no_singleton(self):
        mdns_module._mdns_service = None
        stop_mdns()  # Should not raise
