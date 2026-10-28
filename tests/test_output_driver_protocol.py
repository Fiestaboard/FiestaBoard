"""The ``OutputDriver`` Protocol: every board's driver conforms to one seam.

Pins three things:

1. Conformance — the first-party outputs' drivers (Vestaboard local, RW
   Cloud, note-array Cloud and local tiles; FiestaPanel), each the
   ``OutputPluginDriver`` around the output's plugin, are ``OutputDriver``
   instances, and the driver's method signatures match the Protocol's (no
   ``with_outcome``-style drift, #2119).
2. Mockability — ``Mock(spec=OutputDriver)`` exposes exactly the Protocol,
   so a test double cannot quietly lean on a private attribute.
3. The private-peek ratchet — code outside the client modules that reads a
   board client's private attributes is counted. The count may only go
   down; later layers of the output-plugin program drive it to zero.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.outputs import OutputDriver
from src.outputs.plugin_driver import OutputPluginDriver
from tests.first_party_drivers import (
    cloud_driver,
    local_driver,
    note_array_cloud_driver,
    panel_driver,
    tiles_driver,
)

REPO = Path(__file__).resolve().parents[1]

# The seam, as inventoried from callers outside the client modules. Adding a
# member is a contract change for every future output — do it on purpose.
EXPECTED_SURFACE = {
    "use_cloud",
    "is_virtual",
    "skip_unchanged",
    "last_send_throttled",
    "last_send_retry_after",
    "min_send_interval_ms",
    # Read by the runtime to drive transitions (refactor/output-runtime-transitions).
    "native_transitions",
    "animation",
    "send_characters",
    "render",
    "set_transition_runner",
    "set_output_runtime",
    "device_key",
    "read_current_message",
    "clear_cache",
    "get_cache_status",
    "test_connection",
    # What core asks the driver instead of knowing the device
    # (refactor/vestaboard-behind-hooks): the structured probe, the
    # read-back capability the poll interval is chosen by, and the MQTT label.
    "check_connection",
    "read_back",
    "connection_label",
}

PROTOCOL_METHODS = sorted(
    name for name in EXPECTED_SURFACE if inspect.isfunction(inspect.getattr_static(OutputDriver, name))
)


def _protocol_members() -> set[str]:
    return {
        name
        for name, value in vars(OutputDriver).items()
        if not name.startswith("_") and (inspect.isfunction(value) or isinstance(value, property))
    }


def _clients() -> dict[str, object]:
    return {
        "vestaboard-local": local_driver("test_key", "192.0.2.10"),
        "vestaboard-rw-cloud": cloud_driver("test_key"),
        "vestaboard-note-array-cloud": note_array_cloud_driver("test_token", 2, 1),
        "note-array-local": tiles_driver(
            [{"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "test_key"}], 1, 1
        ),
        "virtual": panel_driver("flagship"),
    }


CLIENT_IDS = list(_clients())


class TestProtocolSurface:
    def test_surface_is_exactly_the_inventoried_caller_surface(self):
        assert _protocol_members() == EXPECTED_SURFACE

    def test_send_text_and_would_send_are_not_part_of_the_seam(self):
        # Nothing outside the clients calls either; the plugin contract drops send_text.
        assert "send_text" not in _protocol_members()
        assert "would_send" not in _protocol_members()


class TestClientsConform:
    @pytest.mark.parametrize("kind", CLIENT_IDS)
    def test_client_is_an_output_driver(self, kind):
        assert isinstance(_clients()[kind], OutputDriver)

    @pytest.mark.parametrize("cls", [OutputPluginDriver])
    @pytest.mark.parametrize("method", PROTOCOL_METHODS)
    def test_method_signature_matches_the_protocol(self, cls, method):
        def shape(fn):
            return [(p.name, p.kind, p.default) for p in inspect.signature(fn).parameters.values()]

        assert shape(getattr(cls, method)) == shape(getattr(OutputDriver, method))

    @pytest.mark.parametrize("kind", ["note-array-local", "virtual"])
    def test_unfloored_clients_report_no_floor_and_no_throttle(self, kind):
        client = _clients()[kind]
        assert client.min_send_interval_ms == 0
        assert client.last_send_throttled is False

    @pytest.mark.parametrize(
        "kind", ["vestaboard-local", "vestaboard-rw-cloud", "vestaboard-note-array-cloud", "note-array-local"]
    )
    def test_hardware_clients_are_not_virtual(self, kind):
        assert _clients()[kind].is_virtual is False

    def test_virtual_client_is_virtual(self):
        assert _clients()["virtual"].is_virtual is True


class TestMockSpec:
    def test_mock_spec_exposes_every_protocol_member(self):
        double = Mock(spec=OutputDriver)
        for name in EXPECTED_SURFACE:
            assert hasattr(double, name), name

    @pytest.mark.parametrize(
        "name", ["_last_characters", "_cancel_transition", "_last_sent_at", "send_text", "would_send", "host"]
    )
    def test_mock_spec_refuses_anything_outside_the_protocol(self, name):
        with pytest.raises(AttributeError):
            getattr(Mock(spec=OutputDriver), name)

    def test_mock_spec_is_an_output_driver(self):
        assert isinstance(Mock(spec=OutputDriver), OutputDriver)


# --- private-peek ratchet ---------------------------------------------------

# Every board's driver is the output-plugin adapter now (Phase 4): its
# private state is what nothing outside it may read.
CLIENT_MODULES = {
    REPO / "src" / "outputs" / "plugin_driver.py",
}

# A receiver whose last name is ``client`` / ``*_client`` (``rt.client``,
# ``board_client``, ``vb_client``, ``self.vb_client`` …).
_CLIENT_RECEIVER = re.compile(r"(^|_)client$")

# Peeks at board-client private attributes outside the client modules.
# Lower this when a layer removes one; it must never go up. The frame-dedupe
# layer moved the last six (the dedupe cache, external-write detection, the
# post-send refresh baseline, the transition's starting grid and the panel's
# send time) onto the OutputRuntime.
MAX_PRIVATE_PEEKS = 0


def _private_client_names() -> set[str]:
    """Every single-underscore attribute or method the client modules define on ``self``/classes."""
    names: set[str] = set()
    for path in CLIENT_MODULES:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and node.attr.startswith("_")
                and not node.attr.startswith("__")
            ):
                names.add(node.attr)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, ast.FunctionDef)
                        and item.name.startswith("_")
                        and not item.name.startswith("__")
                    ):
                        names.add(item.name)
    return names


def _receiver_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_client_receiver(node: ast.AST) -> bool:
    name = _receiver_name(node)
    return name is not None and name != "self" and bool(_CLIENT_RECEIVER.search(name))


def _private_peeks(roots: list[Path] | None = None) -> list[str]:
    private = _private_client_names()
    found: list[str] = []
    for root in roots if roots is not None else [REPO / "src", REPO / "plugins"]:
        for path in sorted(root.rglob("*.py")):
            if path in CLIENT_MODULES or "tests" in path.relative_to(root).parts:
                continue
            tree = ast.parse(path.read_text())
            rel = path.relative_to(root.parent)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in private and _is_client_receiver(node.value):
                    found.append(f"{rel}:{node.lineno} .{node.attr}")
                elif (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"getattr", "setattr", "hasattr"}
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in private
                    and _is_client_receiver(node.args[0])
                ):
                    found.append(f"{rel}:{node.lineno} {node.func.id}({node.args[1].value!r})")
    return found


def test_private_client_peeks_never_increase():
    peeks = _private_peeks()
    listing = "\n  ".join(peeks)
    assert len(peeks) <= MAX_PRIVATE_PEEKS, (
        f"{len(peeks)} private board-client peeks outside the client modules (max {MAX_PRIVATE_PEEKS}). "
        f"Add what you need to OutputDriver instead of reaching past it:\n  {listing}"
    )
    assert len(peeks) == MAX_PRIVATE_PEEKS, (
        f"Only {len(peeks)} private peeks remain — lower MAX_PRIVATE_PEEKS to {len(peeks)} "
        f"so the ratchet holds:\n  {listing}"
    )


def test_ratchet_scanner_sees_a_known_peek(tmp_path):
    """Guard the scanner itself: at zero, an empty walk would pass vacuously.

    The repo has no peeks left, so the scanner is pointed at a planted one.
    """
    assert "_output_runtime" in _private_client_names()
    assert "_frames" in _private_client_names()
    planted = tmp_path / "src" / "planted.py"
    planted.parent.mkdir()
    planted.write_text(
        "def peek(rt, board_client):\n"
        "    rt.client._frames\n"
        "    return getattr(board_client, '_output_runtime', None)\n"
    )
    assert len(_private_peeks([planted.parent])) == 2, "the ratchet scanner missed a planted peek"
