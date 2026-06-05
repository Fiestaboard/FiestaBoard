"""Tests for mDNS/Bonjour service (src.system.mdns)."""

from unittest.mock import MagicMock, patch

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

        with patch("zeroconf.Zeroconf", return_value=mock_zc), patch("zeroconf.ServiceInfo", mock_si_cls):
            svc = MDNSService(hostname="testboard", port=4420)
            result = svc.start()

        assert result is True
        assert svc.is_running is True
        mock_zc.register_service.assert_called_once()

    def test_start_idempotent(self):
        from src.system.mdns import MDNSService

        mock_zc = MagicMock()
        with patch("zeroconf.Zeroconf", return_value=mock_zc), patch("zeroconf.ServiceInfo", MagicMock()):
            svc = MDNSService()
            svc.start()
            svc.start()  # second call should be a no-op

        # Only registered once
        assert mock_zc.register_service.call_count == 1

    def test_stop_unregisters_service(self):
        from src.system.mdns import MDNSService

        mock_zc = MagicMock()
        with patch("zeroconf.Zeroconf", return_value=mock_zc), patch("zeroconf.ServiceInfo", MagicMock()):
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
            mock_sock.return_value.__enter__ = MagicMock(side_effect=OSError("no network"))
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
        from src.system.mdns import get_mdns_service, start_mdns

        with patch("zeroconf.Zeroconf", return_value=MagicMock()), patch("zeroconf.ServiceInfo", MagicMock()):
            result = start_mdns()

        assert result is True
        assert get_mdns_service().is_running is True
        self._reset()

    def test_stop_mdns_when_not_started(self):
        self._reset()
        from src.system.mdns import stop_mdns

        stop_mdns()  # should not raise
        self._reset()


# ---------- Board scanning / discovery tests ----------


class TestProbeVestaboardPort:
    """Test the _probe_vestaboard_port helper."""

    def test_returns_false_when_port_closed(self):
        from src.system.mdns import _probe_vestaboard_port

        # Port 1 on localhost is almost certainly not listening
        assert _probe_vestaboard_port("127.0.0.1", port=1, timeout=0.2) is False

    def test_returns_false_for_unreachable_host(self):
        from src.system.mdns import _probe_vestaboard_port

        # Non-routable address should fail quickly
        assert _probe_vestaboard_port("192.0.2.1", port=7000, timeout=0.2) is False

    def test_returns_true_when_connected(self):
        from src.system.mdns import _probe_vestaboard_port

        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)
            assert _probe_vestaboard_port("10.0.0.5", port=7000) is True


class TestScanForBoards:
    """Test the scan_for_boards function."""

    def test_returns_list(self):
        from src.system.mdns import scan_for_boards

        # With mocked zeroconf and no real network, should return a list
        with patch("src.system.mdns._get_local_ip", return_value="127.0.0.1"):
            # loopback /24 probing is skipped when IP is 127.0.0.1
            result = scan_for_boards(timeout=0.1)
        assert isinstance(result, list)

    def test_returns_empty_when_no_boards(self):
        from src.system.mdns import scan_for_boards

        with patch("src.system.mdns._get_local_ip", return_value="127.0.0.1"):
            result = scan_for_boards(timeout=0.1)
        assert result == []

    def test_mdns_discovery_returns_boards(self):
        """Simulate mDNS finding a board."""
        from src.system.mdns import scan_for_boards

        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ["192.168.1.50"]
        mock_info.port = 7000
        mock_info.server = "vestaboard-abc.local."

        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = mock_info

        def fake_browser(zc, stype, listener):
            # Simulate discovering a service immediately
            listener.add_service(zc, stype, "Vestaboard._vestaboard._tcp.local.")
            return MagicMock()

        with (
            patch("zeroconf.Zeroconf", return_value=mock_zc),
            patch("zeroconf.ServiceBrowser", side_effect=fake_browser),
            patch("time.sleep"),
            patch("src.system.mdns._get_local_ip", return_value="127.0.0.1"),
        ):
            result = scan_for_boards(timeout=0.1)

        assert len(result) == 1
        assert result[0]["ip"] == "192.168.1.50"
        assert result[0]["port"] == 7000
        assert result[0]["source"] == "mdns"

    def test_port_probe_returns_boards(self):
        """Simulate finding a board via port probing."""
        from src.system.mdns import scan_for_boards

        def fake_probe(ip, port=7000, timeout=0.5):
            return ip == "10.0.0.42"

        with (
            patch("src.system.mdns._probe_vestaboard_port", side_effect=fake_probe),
            patch("src.system.mdns._get_local_ip", return_value="10.0.0.1"),
            patch("zeroconf.Zeroconf", return_value=MagicMock()),
            patch("zeroconf.ServiceBrowser", return_value=MagicMock()),
            patch("time.sleep"),
        ):
            result = scan_for_boards(timeout=0.1)

        ips = [b["ip"] for b in result]
        assert "10.0.0.42" in ips

    def test_deduplicates_mdns_and_probe(self):
        """Board found via both mDNS and port scan should appear once."""
        from src.system.mdns import scan_for_boards

        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ["10.0.0.42"]
        mock_info.port = 7000
        mock_info.server = "board.local."

        mock_zc = MagicMock()
        mock_zc.get_service_info.return_value = mock_info

        def fake_browser(zc, stype, listener):
            listener.add_service(zc, stype, "Board._vestaboard._tcp.local.")
            return MagicMock()

        def fake_probe(ip, port=7000, timeout=0.5):
            return ip == "10.0.0.42"

        with (
            patch("zeroconf.Zeroconf", return_value=mock_zc),
            patch("zeroconf.ServiceBrowser", side_effect=fake_browser),
            patch("src.system.mdns._probe_vestaboard_port", side_effect=fake_probe),
            patch("src.system.mdns._get_local_ip", return_value="10.0.0.1"),
            patch("time.sleep"),
        ):
            result = scan_for_boards(timeout=0.1)

        ips = [b["ip"] for b in result]
        assert ips.count("10.0.0.42") == 1

    def test_graceful_when_zeroconf_missing(self):
        """scan_for_boards should not raise if zeroconf is not installed."""
        from src.system.mdns import scan_for_boards

        with (
            patch("builtins.__import__", side_effect=ImportError("no zeroconf")),
            patch("src.system.mdns._get_local_ip", return_value="127.0.0.1"),
        ):
            result = scan_for_boards(timeout=0.1)
        assert isinstance(result, list)
