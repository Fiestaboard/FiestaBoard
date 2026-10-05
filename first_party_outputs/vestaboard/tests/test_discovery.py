"""The Vestaboard ``discover`` hook: mDNS browse, then a subnet probe of port 7000.

Never simulate a missing dependency with ``patch("builtins.__import__")``:
``patch.dict("sys.modules", {"<name>": None})`` blocks the import on its own.
"""

from unittest.mock import MagicMock, patch

from first_party_outputs.vestaboard import discovery


class TestProbeVestaboardPort:
    """Test the _probe_vestaboard_port helper."""

    def test_returns_false_when_port_closed(self):

        # Port 1 on localhost is almost certainly not listening
        assert discovery._probe_vestaboard_port("127.0.0.1", port=1, timeout=0.2) is False

    def test_returns_false_for_unreachable_host(self):

        # A connect that times out (what a non-routable address does) reads as
        # "no board here". Mocked: the suite may not leave loopback.
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = TimeoutError("timed out")
            mock_sock_cls.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)
            assert discovery._probe_vestaboard_port("192.0.2.1", port=7000, timeout=0.2) is False

    def test_returns_true_when_connected(self):

        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value.__enter__ = MagicMock(return_value=mock_sock)
            mock_sock_cls.return_value.__exit__ = MagicMock(return_value=False)
            assert discovery._probe_vestaboard_port("10.0.0.5", port=7000) is True


class TestScanForBoards:
    """Test the discover hook."""

    def test_returns_list(self):

        # With mocked zeroconf and no real network, should return a list
        with patch.object(discovery, "local_ipv4", return_value="127.0.0.1"):
            # loopback /24 probing is skipped when IP is 127.0.0.1
            result = discovery.discover(timeout=0.1)
        assert isinstance(result, list)

    def test_returns_empty_when_no_boards(self):

        with patch.object(discovery, "local_ipv4", return_value="127.0.0.1"):
            result = discovery.discover(timeout=0.1)
        assert result == []

    def test_mdns_discovery_returns_boards(self):
        """Simulate mDNS finding a board."""

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
            patch.object(discovery, "local_ipv4", return_value="127.0.0.1"),
        ):
            result = discovery.discover(timeout=0.1)

        assert len(result) == 1
        assert result[0]["ip"] == "192.168.1.50"
        assert result[0]["port"] == 7000
        assert result[0]["source"] == "mdns"

    def test_port_probe_returns_boards(self):
        """Simulate finding a board via port probing."""

        def fake_probe(ip, port=7000, timeout=0.5):
            return ip == "10.0.0.42"

        with (
            patch.object(discovery, "_probe_vestaboard_port", side_effect=fake_probe),
            patch.object(discovery, "local_ipv4", return_value="10.0.0.1"),
            patch("zeroconf.Zeroconf", return_value=MagicMock()),
            patch("zeroconf.ServiceBrowser", return_value=MagicMock()),
            patch("time.sleep"),
        ):
            result = discovery.discover(timeout=0.1)

        ips = [b["ip"] for b in result]
        assert "10.0.0.42" in ips

    def test_deduplicates_mdns_and_probe(self):
        """Board found via both mDNS and port scan should appear once."""

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
            patch.object(discovery, "_probe_vestaboard_port", side_effect=fake_probe),
            patch.object(discovery, "local_ipv4", return_value="10.0.0.1"),
            patch("time.sleep"),
        ):
            result = discovery.discover(timeout=0.1)

        ips = [b["ip"] for b in result]
        assert ips.count("10.0.0.42") == 1

    def test_graceful_when_zeroconf_missing(self):
        """discover does not raise if zeroconf is not installed."""

        with (
            patch.dict("sys.modules", {"zeroconf": None}),
            patch.object(discovery, "local_ipv4", return_value="127.0.0.1"),
        ):
            result = discovery.discover(timeout=0.1)
        assert isinstance(result, list)
