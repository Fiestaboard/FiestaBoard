"""The network hint (``hint_host``): the browser's LAN address reaches a scan.

FiestaBoard runs in Docker bridge mode by default, so the container's own
address (``172.x``) names a container network, not the LAN a device is on.
The web UI sends the address the user opened FiestaBoard at as the generic
``hint_host`` action input; core accepts it on any action, hands it to a
``discover`` hook that takes ``hint`` (an older ``discover(timeout)`` keeps
working), and keeps it from custom actions that do not declare it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.outputs.actions import _checked_input
from src.outputs.errors import InvalidActionInputError
from src.outputs.hooks import HINT_HOST, OutputActionSpec, OutputHooks, call_discover, lan_hint
from src.outputs.plugin_base import OutputPluginBase
from src.plugins.loader import PluginLoader

# --- what counts as a hint ------------------------------------------------------------------


@pytest.mark.parametrize("address", ["192.168.1.20", "10.0.0.5", "172.16.4.2", "172.31.255.1", "169.254.10.1"])
def test_a_private_or_link_local_ipv4_address_is_a_hint(address):
    assert lan_hint(address) == address


@pytest.mark.parametrize(
    "value",
    ["127.0.0.1", "8.8.8.8", "172.32.0.1", "fiestaboard.local", "localhost", "::1", "192.168.1", "", None, 42],
)
def test_anything_else_is_not_a_hint(value):
    assert lan_hint(value) is None


# --- handing the hint to a discover hook ------------------------------------------------------


def test_a_hook_that_takes_hint_is_handed_it():
    seen = []

    def discover(timeout, hint=None):
        seen.append((timeout, hint))
        return []

    call_discover(discover, 3.0, "192.168.1.20")
    assert seen == [(3.0, "192.168.1.20")]


def test_a_hook_taking_keyword_arguments_is_handed_it():
    seen = []

    def discover(timeout, **kwargs):
        seen.append(kwargs)
        return []

    call_discover(discover, 3.0, "192.168.1.20")
    assert seen == [{"hint": "192.168.1.20"}]


def test_a_hook_written_before_the_hint_is_called_with_the_timeout_alone():
    legacy = mock.Mock(spec=lambda timeout: [], return_value=[{"ip": "192.0.2.1", "port": 80}])
    assert call_discover(legacy, 3.0, "192.168.1.20") == [{"ip": "192.0.2.1", "port": 80}]
    legacy.assert_called_once_with(3.0)


def test_no_hint_calls_the_hook_with_the_timeout_alone():
    seen = []

    def discover(timeout, hint="unset"):
        seen.append(hint)
        return []

    call_discover(discover, 3.0, None)
    assert seen == ["unset"]


class _Hinted(OutputPluginBase):
    seen: list = []

    @classmethod
    def discover(cls, timeout, hint=None):
        cls.seen.append((timeout, hint))
        return [{"ip": "192.168.1.30", "port": 80}]


def test_the_default_discover_action_hands_the_hint_input_to_the_hook():
    _Hinted.seen = []
    outcome = _Hinted.handle_action(
        SimpleNamespace(action="discover", inputs={"timeout": 2, HINT_HOST: "192.168.1.20"})
    )
    assert _Hinted.seen == [(2.0, "192.168.1.20")]
    assert outcome.devices == ({"ip": "192.168.1.30", "port": 80},)


def test_the_default_discover_action_without_a_hint_hands_none():
    _Hinted.seen = []
    _Hinted.handle_action(SimpleNamespace(action="discover", inputs={}))
    assert _Hinted.seen == [(4.0, None)]


def test_discover_devices_hands_the_hint_to_the_registered_hook():
    from src.outputs import registry

    hook = mock.Mock(return_value=[])

    def discover(timeout, hint=None):
        return hook(timeout, hint)

    definition = SimpleNamespace(hooks=OutputHooks(discover=discover))
    with mock.patch.object(registry, "output_registry", return_value={"x": definition}):
        registry.discover_devices("x", 2.0, hint="10.1.2.3")
        registry.discover_devices("x", 2.0, hint="8.8.8.8")
    assert hook.call_args_list == [mock.call(2.0, "10.1.2.3"), mock.call(2.0, None)]


# --- the action input check -------------------------------------------------------------------

_TIMEOUT_ONLY = {"type": "object", "properties": {"timeout": {"type": "number"}}, "additionalProperties": False}


def test_discover_without_an_input_schema_accepts_the_hint():
    spec = OutputActionSpec(id="discover", label="Scan")
    assert _checked_input(spec, {HINT_HOST: "192.168.1.20"}) == {HINT_HOST: "192.168.1.20"}


def test_discover_whose_schema_does_not_declare_the_hint_still_receives_it():
    spec = OutputActionSpec(id="discover", label="Scan", input_schema=_TIMEOUT_ONLY)
    assert _checked_input(spec, {"timeout": 3, HINT_HOST: "10.0.0.9"}) == {"timeout": 3, HINT_HOST: "10.0.0.9"}


@pytest.mark.parametrize("bad", ["8.8.8.8", "fiestaboard.local", "127.0.0.1", 7])
def test_a_hint_that_is_not_a_private_ipv4_address_is_refused(bad):
    spec = OutputActionSpec(id="discover", label="Scan")
    with pytest.raises(InvalidActionInputError, match=HINT_HOST):
        _checked_input(spec, {HINT_HOST: bad})


def test_an_empty_hint_is_ignored():
    spec = OutputActionSpec(id="discover", label="Scan")
    assert _checked_input(spec, {HINT_HOST: ""}) == {}


def test_a_custom_action_that_does_not_declare_the_hint_never_sees_it():
    spec = OutputActionSpec(id="pair", label="Pair")
    assert _checked_input(spec, {HINT_HOST: "192.168.1.20"}) == {}


def test_a_custom_action_that_declares_the_hint_receives_it_as_its_schema_checks_it():
    schema = {"type": "object", "properties": {"subnet": {"type": "string"}, HINT_HOST: {"type": "string"}}}
    spec = OutputActionSpec(id="find_pixoo", label="Find", input_schema=schema)
    inputs = {"subnet": "192.168.1.0/24", HINT_HOST: "192.168.1.20"}
    assert _checked_input(spec, dict(inputs)) == inputs


# --- through the action route -----------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "plugins" / "recording_output"
PLUGIN_ID = "recording_output"


@pytest.fixture
def bundled(tmp_path):
    root = tmp_path / "plugins"
    target = root / PLUGIN_ID
    shutil.copytree(FIXTURE, target, ignore=shutil.ignore_patterns("__pycache__"))
    path = target / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["output"]["actions"] = [{"id": "discover", "label": "Find signs"}]
    path.write_text(json.dumps(manifest), "utf-8")
    loader = PluginLoader(plugins_dir=root, external_dirs=[])
    assert loader.load_plugin(PLUGIN_ID) is not None, loader.load_errors
    yield loader
    loader.unload_plugin(PLUGIN_ID)


def test_the_draft_discover_route_hands_the_browsers_address_to_the_hook(bundled):
    import sys

    from src.api_server import app

    plugin_class = sys.modules[f"plugins.{PLUGIN_ID}"].RecordingOutput
    seen = []

    def discover(cls, timeout, hint=None):
        seen.append(hint)
        return [{"ip": "192.168.1.30", "port": 80}]

    with mock.patch.object(plugin_class, "discover", classmethod(discover)):
        resp = TestClient(app).post(
            f"/outputs/{PLUGIN_ID}/actions/discover",
            json={"output_config": {"host": "192.0.2.50"}, "input": {HINT_HOST: "192.168.1.20"}},
        )
    assert resp.status_code == 200, resp.text
    assert seen == ["192.168.1.20"]
    assert [d["ip"] for d in resp.json()["devices"]] == ["192.168.1.30"]


def test_the_vestaboard_scan_is_handed_the_browsers_network():
    """The pinned Vestaboard plugin probes the hint's network: its scan
    suffers in bridge mode as every other output's does."""
    from src.api_server import app

    with mock.patch("plugins.vestaboard.discovery.discover", return_value=[]) as scan:
        resp = TestClient(app).post(
            "/outputs/vestaboard/actions/discover", json={"input": {"timeout": 2, HINT_HOST: "192.168.1.20"}}
        )
    assert resp.status_code == 200, resp.text
    scan.assert_called_once_with(2.0, hint="192.168.1.20")


# --- what a found device fills ----------------------------------------------------------------

_PIXOO_SHAPED = {
    "ip": "192.168.1.30",
    "port": 80,
    "host": "192.168.1.30",
    "label": "Pixoo 64 at 192.168.1.30",
    "hostname": "Pixoo 64",
    "mac": "a1b2c3d4e5f6",
}


def _discover_through_the_route(found):
    import sys

    from src.api_server import app

    plugin_class = sys.modules[f"plugins.{PLUGIN_ID}"].RecordingOutput
    with mock.patch.object(plugin_class, "discover", classmethod(lambda cls, timeout, hint=None: found)):
        resp = TestClient(app).post(f"/outputs/{PLUGIN_ID}/actions/discover", json={"input": {}})
    assert resp.status_code == 200, resp.text
    return resp.json()["devices"]


def test_a_found_devices_own_settings_fields_reach_the_picker(bundled):
    """A device-picker bound with ``value_key: "host"`` reads the address the
    plugin put under ``host``, and picking it also fills ``mac``."""
    (device,) = _discover_through_the_route([_PIXOO_SHAPED])
    assert device["fields"] == {"host": "192.168.1.30", "mac": "a1b2c3d4e5f6"}
    assert (device["ip"], device["port"], device["label"]) == ("192.168.1.30", 80, "Pixoo 64 at 192.168.1.30")


def test_only_scalar_device_fields_are_carried(bundled):
    (device,) = _discover_through_the_route([{**_PIXOO_SHAPED, "mac": None, "extra": {"nested": 1}, "tags": ["a"]}])
    assert device["fields"] == {"host": "192.168.1.30"}


def test_a_device_with_only_the_core_keys_fills_nothing_else(bundled):
    (device,) = _discover_through_the_route([{"ip": "192.168.1.31", "port": 7000, "hostname": "vb.local"}])
    assert device["fields"] == {}
