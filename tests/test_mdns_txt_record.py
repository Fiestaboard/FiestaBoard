"""H13 PR 3: the mDNS TXT record names the hub for TV and phone discovery.

``host=`` is always the ``<hostname>.local`` name (the SRV target already says
it). ``name=`` is the install's friendly name, told only while sign-in is off:
the same rule as ``GET /discover`` (src/system/hub_identity.py). A rename or a
sign-in change re-announces the record.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import src.system.mdns as mdns_module
from src.system.mdns import MDNSService, refresh_mdns_advertisement


@pytest.fixture(autouse=True)
def reset_singleton():
    mdns_module._mdns_service = None
    yield
    mdns_module._mdns_service = None


@pytest.fixture
def general():
    """The general settings public_instance_name reads."""
    state = {"instance_name": "Kitchen"}
    manager = MagicMock(get_general=MagicMock(side_effect=lambda: dict(state)))
    with patch("src.config_manager.get_config_manager", return_value=manager):
        yield state


@pytest.fixture
def sign_in_off(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "false")


@pytest.fixture
def sign_in_on(monkeypatch):
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")


class _Info:
    """Enough of zeroconf.ServiceInfo: keeps what it was built with."""

    def __init__(self, type_, name, server, port, properties, addresses):
        self.type, self.name, self.server, self.port = type_, name, server, port
        self.properties = {k.encode(): v.encode() for k, v in properties.items()}
        self.addresses = addresses


@pytest.fixture
def zeroconf():
    zc = MagicMock()
    module = MagicMock(ServiceInfo=_Info, Zeroconf=MagicMock(return_value=zc))
    with (
        patch.dict("sys.modules", {"zeroconf": module}),
        patch("src.system.mdns._get_local_ip", return_value="192.168.1.50"),
    ):
        yield zc


def _txt(service: MDNSService) -> dict[str, str]:
    return {k.decode(): v.decode() for k, v in service._service_info.properties.items()}


def test_the_record_carries_the_host_and_the_name_while_sign_in_is_off(general, sign_in_off, zeroconf):
    service = MDNSService(hostname="fiestapi")
    assert service.start()

    assert _txt(service) == {"path": "/", "product": "FiestaBoard", "host": "fiestapi.local", "name": "Kitchen"}


def test_the_name_is_never_broadcast_while_sign_in_is_required(general, sign_in_on, zeroconf):
    service = MDNSService(hostname="fiestapi")
    assert service.start()

    assert _txt(service) == {"path": "/", "product": "FiestaBoard", "host": "fiestapi.local"}


def test_the_name_is_withheld_while_sign_in_is_undecided(general, monkeypatch, zeroconf):
    monkeypatch.delenv("FIESTABOARD_AUTH_ENABLED", raising=False)
    with patch("src.auth.service.auth_mode", return_value="undecided"):
        service = MDNSService()
        assert service.start()

    assert "name" not in _txt(service)


def test_an_unnamed_hub_has_no_name_entry(general, sign_in_off, zeroconf):
    general["instance_name"] = "   "
    service = MDNSService()
    assert service.start()

    assert "name" not in _txt(service)


def test_a_long_name_fits_one_txt_entry_without_splitting_a_character(general, sign_in_off, zeroconf):
    general["instance_name"] = "é" * 300
    service = MDNSService()
    assert service.start()

    name = _txt(service)["name"]
    assert len(("name=" + name).encode()) <= 255
    assert set(name) == {"é"} and len(name) == 100


def test_a_broken_name_lookup_still_advertises(sign_in_off, zeroconf):
    with patch("src.config_manager.get_config_manager", side_effect=RuntimeError("no config")):
        service = MDNSService(hostname="fiestapi")
        assert service.start()

    assert _txt(service) == {"path": "/", "product": "FiestaBoard", "host": "fiestapi.local"}


def test_a_rename_reannounces_the_record(general, sign_in_off, zeroconf):
    service = MDNSService()
    assert service.start()
    general["instance_name"] = "Office"

    assert service.refresh() is True

    zeroconf.update_service.assert_called_once()
    assert _txt(service)["name"] == "Office"


def test_an_unchanged_record_is_not_reannounced(general, sign_in_off, zeroconf):
    service = MDNSService()
    assert service.start()

    assert service.refresh() is False
    zeroconf.update_service.assert_not_called()


def test_turning_sign_in_on_withdraws_the_name(general, sign_in_off, zeroconf, monkeypatch):
    service = MDNSService()
    assert service.start()
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")

    assert service.refresh() is True
    assert "name" not in _txt(service)


def test_refresh_does_nothing_before_the_service_runs(general, sign_in_off):
    assert MDNSService().refresh() is False


def test_the_background_refresh_is_skipped_when_nothing_is_advertised():
    assert refresh_mdns_advertisement() is None
    mdns_module._mdns_service = MDNSService()
    assert refresh_mdns_advertisement() is None


def test_the_background_refresh_runs_on_its_own_thread(general, sign_in_off, zeroconf):
    service = mdns_module.get_mdns_service()
    assert service.start()
    general["instance_name"] = "Office"

    thread = refresh_mdns_advertisement()
    assert thread is not None
    thread.join(5)

    assert _txt(service)["name"] == "Office"


def test_a_failing_background_refresh_is_logged_not_raised(general, sign_in_off, zeroconf, caplog):
    service = mdns_module.get_mdns_service()
    assert service.start()
    general["instance_name"] = "Office"
    zeroconf.update_service.side_effect = OSError("multicast down")

    thread = refresh_mdns_advertisement()
    assert thread is not None
    thread.join(5)

    assert any("mDNS TXT" in r.getMessage() for r in caplog.records)


# ── who triggers the refresh ────────────────────────────────────────────────


def test_renaming_the_hub_schedules_a_refresh(tmp_path, monkeypatch):
    from src import config_manager as cm_module

    calls = []
    monkeypatch.setattr(mdns_module, "refresh_mdns_advertisement", lambda: calls.append("refresh"))
    manager = cm_module.ConfigManager(config_path=str(tmp_path / "config.json"))

    assert manager.set_general({"timezone": "UTC"})
    assert calls == []
    assert manager.set_general({"instance_name": "Office"})
    assert calls == ["refresh"]


def test_changing_the_sign_in_preference_schedules_a_refresh(tmp_path, monkeypatch):
    from src.auth.service import AuthService

    calls = []
    monkeypatch.setattr(mdns_module, "refresh_mdns_advertisement", lambda: calls.append("refresh"))
    service = AuthService(tmp_path / "auth.json")

    service.set_auth_preference("disabled")

    assert calls == ["refresh"]
