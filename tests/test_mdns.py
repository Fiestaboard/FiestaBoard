"""Tests for mDNS/Bonjour service (src.system.mdns)."""

import pytest
import socket
from unittest.mock import patch, MagicMock


# ---------- MDNSService unit tests ----------

class TestMDNSServiceInit:
    """Test MDNSService initialisation and default values."""

    def test_default_hostname(self):
        from src.system.mdns import MDNSService
        svc = MDNSService()
        assert svc.hostname == "fiestaboard"

    def test_default_port(self):
        from src.system.mdns import MDNSService
        svc = MDNSService()
        assert svc.port == 4420

    def test_custom_hostname(self):
        from src.system.mdns import MDNSService
        svc = MDNSService(hostname="myboard")
        assert svc.hostname == "myboard"

    def test_custom_port(self):
        from src.system.mdns import MDNSService
        svc = MDNSService(port=8080)
        assert svc.port == 8080

    def test_hostname_from_env(self):
        from src.system.mdns import MDNSService
        with patch.dict("os.environ", {"MDNS_HOSTNAME": "envboard"}):
            svc = MDNSService()
        assert svc.hostname == "envboard"

    def test_port_from_env(self):
        from src.system.mdns import MDNSService
        with patch.dict("os.environ", {"MDNS_PORT": "9090"}):
            svc = MDNSService()
        assert svc.port == 9090

    def test_explicit_overrides_env(self):
        from src.system.mdns import MDNSService
        with patch.dict("os.environ", {"MDNS_HOSTNAME": "envboard"}):
            svc = MDNSService(hostname="explicit")
        assert svc.hostname == "explicit"


class TestMDNSServiceLocalUrl:
    """Test the local_url property."""

    def test_default_url(self):
        from src.system.mdns import MDNSService
        svc = MDNSService()
        assert svc.local_url == "http://fiestaboard.local:4420"

    def test_port_80_omits_port(self):
        from src.system.mdns import MDNSService
        svc = MDNSService(port=80)
        assert svc.local_url == "http://fiestaboard.local"

    def test_custom_hostname_in_url(self):
        from src.system.mdns import MDNSService
        svc = MDNSService(hostname="myboard", port=4420)
        assert svc.local_url == "http://myboard.local:4420"


class TestMDNSServiceLifecycle:
    """Test start / stop with a mocked zeroconf backend."""

    def test_start_registers_service(self):
        from src.system.mdns import MDNSService

        mock_zc = MagicMock()
        mock_si_cls = MagicMock()

        with patch("zeroconf.Zeroconf", return_value=mock_zc), \
             patch("zeroconf.ServiceInfo", mock_si_cls):
            svc = MDNSService(hostname="testboard", port=4420)
            result = svc.start()

        assert result is True
        assert svc.is_running is True
        mock_zc.register_service.assert_called_once()

    def test_start_idempotent(self):
        from src.system.mdns import MDNSService

        mock_zc = MagicMock()
        with patch("zeroconf.Zeroconf", return_value=mock_zc), \
             patch("zeroconf.ServiceInfo", MagicMock()):
            svc = MDNSService()
            svc.start()
            svc.start()  # second call should be a no-op

        # Only registered once
        assert mock_zc.register_service.call_count == 1

    def test_stop_unregisters_service(self):
        from src.system.mdns import MDNSService

        mock_zc = MagicMock()
        with patch("zeroconf.Zeroconf", return_value=mock_zc), \
             patch("zeroconf.ServiceInfo", MagicMock()):
            svc = MDNSService()
            svc.start()
            svc.stop()

        assert svc.is_running is False
        mock_zc.unregister_service.assert_called_once()
        mock_zc.close.assert_called_once()

    def test_stop_when_not_started(self):
        """Calling stop on an un-started service should not raise."""
        from src.system.mdns import MDNSService
        svc = MDNSService()
        svc.stop()  # should not raise
        assert svc.is_running is False

    def test_start_handles_import_error(self):
        """If zeroconf is not installed, start returns False gracefully."""
        from src.system.mdns import MDNSService

        svc = MDNSService()
        with patch.dict("sys.modules", {"zeroconf": None}):
            # Force ImportError by patching the import inside start()
            with patch("builtins.__import__", side_effect=ImportError("no zeroconf")):
                result = svc.start()

        assert result is False
        assert svc.is_running is False

    def test_start_handles_generic_exception(self):
        """If zeroconf raises during registration, start returns False."""
        from src.system.mdns import MDNSService

        with patch("zeroconf.Zeroconf", side_effect=OSError("Network error")):
            svc = MDNSService()
            result = svc.start()

        assert result is False
        assert svc.is_running is False


class TestGetLocalIp:
    """Test the _get_local_ip helper."""

    def test_returns_string(self):
        from src.system.mdns import _get_local_ip
        ip = _get_local_ip()
        assert isinstance(ip, str)

    def test_fallback_on_error(self):
        from src.system.mdns import _get_local_ip
        with patch("socket.socket") as mock_sock:
            mock_sock.return_value.__enter__ = MagicMock(
                side_effect=OSError("no network")
            )
            mock_sock.return_value.__exit__ = MagicMock(return_value=False)
            ip = _get_local_ip()
        assert ip == "127.0.0.1"


class TestModuleSingletonHelpers:
    """Test get_mdns_service / start_mdns / stop_mdns."""

    def _reset(self):
        import src.system.mdns as mod
        mod._mdns_service = None

    def test_get_mdns_service_singleton(self):
        self._reset()
        from src.system.mdns import get_mdns_service
        s1 = get_mdns_service()
        s2 = get_mdns_service()
        assert s1 is s2
        self._reset()

    def test_start_mdns_calls_start(self):
        self._reset()
        from src.system.mdns import start_mdns, get_mdns_service

        with patch("zeroconf.Zeroconf", return_value=MagicMock()), \
             patch("zeroconf.ServiceInfo", MagicMock()):
            result = start_mdns()

        assert result is True
        assert get_mdns_service().is_running is True
        self._reset()

    def test_stop_mdns_when_not_started(self):
        self._reset()
        from src.system.mdns import stop_mdns
        stop_mdns()  # should not raise
        self._reset()
