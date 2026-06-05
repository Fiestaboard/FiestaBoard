"""Unit tests for src.network.wifi.WiFiService.

All subprocess calls are mocked — these tests never touch real
NetworkManager.
"""

from __future__ import annotations

import asyncio
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.network import wifi
from src.network.wifi import WiFiError, WiFiService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _force_available(svc: WiFiService) -> None:
    """Skip the env/binary/dbus probe so tests can run anywhere."""
    svc._cached_capability = wifi.WiFiCapability(available=True)


def _mock_completed(stdout: str = "", returncode: int = 0) -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.stdout = stdout
    m.stderr = ""
    m.returncode = returncode
    return m


# ---------------------------------------------------------------------------
# capability()
# ---------------------------------------------------------------------------


class TestCapability:
    def test_unavailable_off_pi(self, monkeypatch):
        monkeypatch.delenv("FIESTABOARD_PROFILE", raising=False)
        svc = WiFiService()
        cap = svc.capability()
        assert cap.available is False
        assert "FiestaPi" in (cap.reason or "")

    def test_unavailable_when_nmcli_missing(self, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
        with patch("src.network.wifi.shutil.which", return_value=None):
            svc = WiFiService()
            cap = svc.capability()
        assert cap.available is False
        assert "nmcli" in (cap.reason or "")

    def test_unavailable_when_dbus_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
        with patch("src.network.wifi.shutil.which", return_value="/usr/bin/nmcli"):
            with patch("src.network.wifi.Path") as mock_path:
                # is_available branch uses Path(...).exists()
                p = MagicMock()
                p.exists.return_value = False
                mock_path.return_value = p
                svc = WiFiService()
                cap = svc.capability()
        assert cap.available is False
        assert "D-Bus" in (cap.reason or "")

    def test_available(self, monkeypatch):
        monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
        with (
            patch("src.network.wifi.shutil.which", return_value="/usr/bin/nmcli"),
            patch("src.network.wifi.Path") as mock_path,
        ):
            p = MagicMock()
            p.exists.return_value = True
            mock_path.return_value = p
            svc = WiFiService()
            cap = svc.capability()
        assert cap.available is True
        assert cap.reason is None

    def test_capability_cached(self, monkeypatch):
        """Second call must not re-run the env/binary check."""
        monkeypatch.delenv("FIESTABOARD_PROFILE", raising=False)
        svc = WiFiService()
        first = svc.capability()
        # Even if env flips after the first call, the cached answer stands.
        monkeypatch.setenv("FIESTABOARD_PROFILE", "pi")
        second = svc.capability()
        assert first is second


# ---------------------------------------------------------------------------
# _require_available
# ---------------------------------------------------------------------------


class TestRequireAvailable:
    def test_raises_when_unavailable(self, monkeypatch):
        monkeypatch.delenv("FIESTABOARD_PROFILE", raising=False)
        svc = WiFiService()
        with pytest.raises(WiFiError):
            svc._require_available()


# ---------------------------------------------------------------------------
# _run_nmcli
# ---------------------------------------------------------------------------


class TestRunNmcli:
    def test_success_returns_stdout(self):
        svc = WiFiService()
        _force_available(svc)
        with patch("src.network.wifi.subprocess.run", return_value=_mock_completed("hello\n")):
            assert svc._run_nmcli(["--version"]) == "hello\n"

    def test_missing_binary_raises(self):
        svc = WiFiService()
        _force_available(svc)
        with patch("src.network.wifi.subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(WiFiError):
                svc._run_nmcli(["--version"])

    def test_timeout_raises(self):
        svc = WiFiService()
        _force_available(svc)
        exc = subprocess.TimeoutExpired(cmd=["nmcli"], timeout=1)
        with patch("src.network.wifi.subprocess.run", side_effect=exc):
            with pytest.raises(WiFiError, match="timed out"):
                svc._run_nmcli(["--version"], timeout=1)

    def test_nonzero_exit_surfaces_stderr(self):
        svc = WiFiService()
        _force_available(svc)
        err = subprocess.CalledProcessError(returncode=4, cmd=["nmcli"], output="", stderr="not authorized")
        with patch("src.network.wifi.subprocess.run", side_effect=err):
            with pytest.raises(WiFiError, match="not authorized"):
                svc._run_nmcli(["connection", "up", "wifi"])


# ---------------------------------------------------------------------------
# _redact_args
# ---------------------------------------------------------------------------


class TestRedactArgs:
    def test_psk_value_redacted(self):
        redacted = wifi._redact_args(["nmcli", "connection", "add", "wifi-sec.psk", "hunter2", "ssid", "x"])
        assert "hunter2" not in redacted
        assert "***" in redacted

    def test_password_value_redacted(self):
        redacted = wifi._redact_args(["nmcli", "password", "secret"])
        assert "secret" not in redacted

    def test_no_secret_unchanged(self):
        args = ["nmcli", "connection", "show", "--active"]
        assert wifi._redact_args(args) == args


# ---------------------------------------------------------------------------
# _parse_terse
# ---------------------------------------------------------------------------


class TestParseTerse:
    def test_simple_fields(self):
        assert WiFiService._parse_terse("a:b:c") == ["a", "b", "c"]

    def test_escaped_colon_preserved_in_ssid(self):
        # nmcli escapes a colon inside an SSID as `\:` so a naive split
        # on `:` would corrupt it.
        assert WiFiService._parse_terse(r"foo\:bar:WPA2:70") == ["foo:bar", "WPA2", "70"]

    def test_empty_fields(self):
        assert WiFiService._parse_terse("::42") == ["", "", "42"]


# ---------------------------------------------------------------------------
# scan()
# ---------------------------------------------------------------------------


class TestScan:
    def test_dedupe_by_ssid_keeps_strongest(self):
        svc = WiFiService()
        _force_available(svc)
        # Same SSID twice (different APs / channels) — keep signal=80, drop 40.
        nmcli_out = "*:HomeNet:80:WPA2\n:HomeNet:40:WPA2\n:GuestNet:55:WPA2\n"
        with patch.object(svc, "_run_nmcli", return_value=nmcli_out):
            results = svc.scan()
        ssids = {n.ssid: n for n in results}
        assert set(ssids.keys()) == {"HomeNet", "GuestNet"}
        assert ssids["HomeNet"].signal == 80
        assert ssids["HomeNet"].in_use is True
        # Sorted descending by signal.
        assert results[0].signal >= results[-1].signal

    def test_skips_hidden_ssids(self):
        svc = WiFiService()
        _force_available(svc)
        # nmcli reports hidden APs with an empty SSID column.
        with patch.object(svc, "_run_nmcli", return_value=":hidden_ap_row::WPA2\n"):
            results = svc.scan()
        # The empty SSID row should be discarded.
        assert not any(n.ssid == "" for n in results)


# ---------------------------------------------------------------------------
# saved_networks()
# ---------------------------------------------------------------------------


class TestSavedNetworks:
    def test_filters_to_wifi_profiles(self):
        svc = WiFiService()
        _force_available(svc)
        out = "HomeNet:802-11-wireless:yes\nWired connection 1:802-3-ethernet:yes\nHotel WiFi:802-11-wireless:no\n"
        with patch.object(svc, "_run_nmcli", return_value=out):
            saved = svc.saved_networks()
        names = {s.name for s in saved}
        assert names == {"HomeNet", "Hotel WiFi"}
        # autoconnect flag preserved.
        flags = {s.name: s.autoconnect for s in saved}
        assert flags["HomeNet"] is True
        assert flags["Hotel WiFi"] is False


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------


class TestStatus:
    def test_not_connected(self):
        svc = WiFiService()
        _force_available(svc)
        # No active wifi connection → connected=False, no IP/SSID.
        with (
            patch.object(svc, "_run_nmcli", return_value="Wired:802-3-ethernet:eth0\n"),
            patch("src.network.wifi.check_internet_connectivity", return_value={"ok": True}),
        ):
            status = svc.status()
        assert status.connected is False
        assert status.ssid is None
        assert status.ip_address is None
        assert status.internet_reachable is True

    def test_connected_with_ip(self):
        svc = WiFiService()
        _force_available(svc)

        active_out = "HomeNet:802-11-wireless:wlan0\n"
        detail_out = "IP4.ADDRESS[1]:192.168.1.42/24\nIP4.GATEWAY:192.168.1.1\n"
        scan_out = "*:HomeNet:75\n"

        # Return different stdout per call: 1st = connection.show --active,
        # 2nd = connection.show <name> details, 3rd = device wifi list.
        outputs = iter([active_out, detail_out, scan_out])
        with (
            patch.object(svc, "_run_nmcli", side_effect=lambda *a, **kw: next(outputs)),
            patch("src.network.wifi.check_internet_connectivity", return_value={"ok": True}),
        ):
            status = svc.status()
        assert status.connected is True
        assert status.ssid == "HomeNet"
        assert status.ip_address == "192.168.1.42"
        assert status.gateway == "192.168.1.1"
        assert status.signal == 75


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    def test_connect_happy_path(self):
        svc = WiFiService()
        _force_available(svc)

        # connect() calls _run_nmcli several times: delete (may fail),
        # add, up. Then it calls _run_nm_online and status().
        with (
            patch.object(svc, "_run_nmcli") as run,
            patch.object(svc, "_run_nm_online", return_value=True),
            patch.object(
                svc,
                "status",
                return_value=wifi.WiFiStatus(
                    connected=True,
                    ssid="HomeNet",
                    ip_address="192.168.1.42",
                    gateway="192.168.1.1",
                    signal=80,
                    internet_reachable=True,
                ),
            ),
        ):
            run.return_value = ""
            result = asyncio.run(svc.connect(ssid="HomeNet", password="hunter2"))
        assert result.connectivity_confirmed is True
        assert result.status.ssid == "HomeNet"
        # The PSK must be inside the add call args list.
        all_args = [c.args[0] for c in run.call_args_list]
        add_call = next(a for a in all_args if "add" in a)
        assert "wifi-sec.psk" in add_call
        assert "hunter2" in add_call

    def test_connect_without_internet_warns(self):
        svc = WiFiService()
        _force_available(svc)
        with (
            patch.object(svc, "_run_nmcli", return_value=""),
            patch.object(svc, "_run_nm_online", return_value=False),
            patch.object(
                svc,
                "status",
                return_value=wifi.WiFiStatus(
                    connected=True, ssid="HomeNet", ip_address=None, gateway=None, signal=None, internet_reachable=False
                ),
            ),
        ):
            result = asyncio.run(svc.connect(ssid="HomeNet", password="x"))
        assert result.connectivity_confirmed is False
        assert "could not verify" in result.message.lower()

    def test_connect_failure_cleans_up_profile(self):
        svc = WiFiService()
        _force_available(svc)

        calls: list[list[str]] = []

        def fake_run(args, timeout=10):
            calls.append(list(args))
            # The first delete (pre-add cleanup) succeeds.
            # The add succeeds. The `up` fails. The post-failure delete
            # also succeeds.
            if args[:2] == ["connection", "up"]:
                raise WiFiError("auth failed")
            return ""

        with patch.object(svc, "_run_nmcli", side_effect=fake_run):
            with pytest.raises(WiFiError, match="Could not join"):
                asyncio.run(svc.connect(ssid="HomeNet", password="bad"))

        # Two deletes: the pre-add idempotent one + the post-failure cleanup.
        delete_calls = [c for c in calls if c[:2] == ["connection", "delete"]]
        assert len(delete_calls) == 2

    def test_connect_requires_ssid(self):
        svc = WiFiService()
        _force_available(svc)
        with pytest.raises(WiFiError):
            asyncio.run(svc.connect(ssid=""))


# ---------------------------------------------------------------------------
# disconnect() / forget()
# ---------------------------------------------------------------------------


class TestDisconnectForget:
    def test_disconnect_raises_when_no_wifi_active(self):
        svc = WiFiService()
        _force_available(svc)
        with patch.object(svc, "_run_nmcli", return_value="Wired:802-3-ethernet\n"):
            with pytest.raises(WiFiError, match="No active WiFi"):
                asyncio.run(svc.disconnect())

    def test_disconnect_brings_down_wifi_connection(self):
        svc = WiFiService()
        _force_available(svc)

        active = "HomeNet:802-11-wireless\n"
        outputs = iter([active, ""])  # show --active, then `connection down`
        with (
            patch.object(svc, "_run_nmcli", side_effect=lambda *a, **kw: next(outputs)),
            patch.object(
                svc,
                "status",
                return_value=wifi.WiFiStatus(
                    connected=False, ssid=None, ip_address=None, gateway=None, signal=None, internet_reachable=False
                ),
            ),
        ):
            status = asyncio.run(svc.disconnect())
        assert status.connected is False

    def test_forget_requires_name(self):
        svc = WiFiService()
        _force_available(svc)
        with pytest.raises(WiFiError):
            asyncio.run(svc.forget(""))

    def test_forget_calls_nmcli_delete(self):
        svc = WiFiService()
        _force_available(svc)
        with patch.object(svc, "_run_nmcli", return_value="") as run:
            asyncio.run(svc.forget("HomeNet"))
        assert run.call_args.args[0] == ["connection", "delete", "HomeNet"]


# ---------------------------------------------------------------------------
# get_wifi_service singleton
# ---------------------------------------------------------------------------


def test_singleton_returns_same_instance():
    wifi._service = None  # reset for the test
    a = wifi.get_wifi_service()
    b = wifi.get_wifi_service()
    assert a is b
