"""Core drives transitions: ``OutputRuntime.render`` and ``NativeTransition``.

Transition driving moved out of the board clients' ``render()`` into the
board's :class:`~src.outputs.runtime.OutputRuntime`. The runtime decides,
per write:

- a **native** transition (the device animates itself) is a
  :class:`~src.outputs.transitions.NativeTransition`, forwarded only to a
  driver that declares the strategy; a driver that declares none (RW Cloud,
  note-array Cloud, virtual) gets a plain write, exactly as those drivers
  always ignored the parameters;
- a ``plugin:<id>`` transition is driven frame by frame by the runtime's
  :class:`~src.transitions.TransitionRunner`, under the runtime's cancel
  token, through the driver's plain send — gated by the beta flag and by
  the driver's declared ``animation`` capability.

The drivers' ``render()`` stays as a thin delegate, so every caller and the
wire goldens see the same calls and bytes as before.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, Mock

import pytest

from src.main import BoardRuntime
from src.outputs import OutputDriver, OutputRuntime
from src.outputs.transitions import NATIVE_STRATEGIES, VALID_STRATEGIES, NativeTransition
from src.send_outcome import SendOutcome
from tests.first_party_drivers import cloud_driver, local_driver, note_array_cloud_driver, panel_driver, tiles_driver


def _grid(fill: int = 0) -> list[list[int]]:
    return [[fill] * 22 for _ in range(6)]


def _driver(*, natives: frozenset[str] = frozenset(VALID_STRATEGIES), animation: str = "stream") -> Mock:
    driver = Mock(spec=OutputDriver)
    driver.native_transitions = natives
    driver.animation = animation
    driver.min_send_interval_ms = 0
    driver.last_send_throttled = False
    driver.last_send_retry_after = None
    driver.send_characters.return_value = (True, True)
    return driver


class _RecordingRunner:
    """Captures what the runtime hands the runner, then sends one frame + the snap."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.on_run = lambda: None

    def run(self, *, plugin_id, to_grid, board_client, cancel_event, device_type, from_grid=None, config=None):
        self.on_run()
        self.calls.append(
            {
                "plugin_id": plugin_id,
                "board_client": board_client,
                "cancel_event": cancel_event,
                "min_send_interval_ms": board_client.min_send_interval_ms,
            }
        )
        board_client.send_characters(_grid(9), strategy=None, force=True)
        return board_client.send_characters(to_grid, strategy=None, force=True)


# --- the native transition value --------------------------------------------


class TestNativeTransition:
    def test_no_parameters_is_no_native_transition(self):
        assert NativeTransition.of(None, None, None) is None

    def test_parameters_are_kept_as_given(self):
        native = NativeTransition.of("column", 250, 2)
        assert (native.strategy, native.step_interval_ms, native.step_size) == ("column", 250, 2)

    def test_a_step_parameter_alone_is_still_a_native_request(self):
        assert NativeTransition.of(None, 100, None) == NativeTransition(None, 100, None)

    def test_the_core_vocabulary_is_the_vestaboard_strategy_list(self):
        assert frozenset(VALID_STRATEGIES) == NATIVE_STRATEGIES


# --- what each driver declares ----------------------------------------------


def _drivers() -> dict[str, object]:
    return {
        "vestaboard-local": local_driver("test_key", "192.0.2.10"),
        "vestaboard-rw-cloud": cloud_driver("test_key"),
        "vestaboard-note-array-cloud": note_array_cloud_driver("test_token", 2, 1),
        "note-array-local": tiles_driver(
            [{"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "test_key"}], 1, 1
        ),
        "virtual": panel_driver("flagship"),
    }


class TestDriverDeclarations:
    @pytest.mark.parametrize("kind", ["vestaboard-local", "note-array-local"])
    def test_local_vestaboard_hardware_declares_every_native_strategy(self, kind):
        assert _drivers()[kind].native_transitions == frozenset(VALID_STRATEGIES)

    @pytest.mark.parametrize("kind", ["vestaboard-rw-cloud", "vestaboard-note-array-cloud", "virtual"])
    def test_cloud_and_virtual_declare_no_native_strategy(self, kind):
        assert _drivers()[kind].native_transitions == frozenset()

    @pytest.mark.parametrize("kind", [k for k in _drivers() if "cloud" not in k])
    def test_every_local_driver_animates_frame_at_a_time(self, kind):
        assert _drivers()[kind].animation == "stream"

    @pytest.mark.parametrize("kind", ["vestaboard-rw-cloud", "vestaboard-note-array-cloud"])
    def test_a_cloud_vestaboard_snaps_frame_driven_transitions(self, kind):
        # One message per 15 s: the Vestaboard plugin (1.5.0) declares "none".
        assert _drivers()[kind].animation == "none"


# --- native routing -----------------------------------------------------------


class TestNativeRouting:
    def test_a_declared_strategy_reaches_the_driver(self):
        driver = _driver()
        OutputRuntime("b1").render(driver, _grid(1), strategy="column", step_interval_ms=250, step_size=2)
        driver.send_characters.assert_called_once_with(
            _grid(1), strategy="column", step_interval_ms=250, step_size=2, force=False
        )

    def test_a_driver_with_no_native_strategies_gets_a_plain_write(self):
        driver = _driver(natives=frozenset())
        OutputRuntime("b1").render(driver, _grid(1), strategy="column", step_interval_ms=250, step_size=2)
        driver.send_characters.assert_called_once_with(
            _grid(1), strategy=None, step_interval_ms=None, step_size=None, force=False
        )

    @pytest.mark.parametrize("natives", [frozenset(VALID_STRATEGIES), frozenset()], ids=["declares", "declares-none"])
    def test_an_unknown_strategy_is_left_for_the_driver_to_refuse(self, natives):
        # Every driver has always refused an unknown name (an unvalidated page
        # override); the runtime must not turn that into a silent plain write.
        driver = _driver(natives=natives)
        OutputRuntime("b1").render(driver, _grid(1), strategy="sideways")
        driver.send_characters.assert_called_once_with(
            _grid(1), strategy="sideways", step_interval_ms=None, step_size=None, force=False
        )

    def test_with_outcome_is_forwarded_only_when_asked(self):
        driver = _driver()
        OutputRuntime("b1").render(driver, _grid(1), with_outcome=True)
        assert driver.send_characters.call_args.kwargs["with_outcome"] is True


# --- plugin transitions ---------------------------------------------------------


class TestPluginDriving:
    def test_the_runtime_runs_its_runner_under_its_own_cancel_token(self):
        runtime = OutputRuntime("b1")
        runner = _RecordingRunner()
        current: list[threading.Event] = []
        runner.on_run = lambda: current.append(runtime.cancel_event)
        runtime.transition_runner = runner
        runtime.render(_driver(), _grid(2), strategy="plugin:wipe", plugins_enabled=lambda: True)

        assert runner.calls[0]["plugin_id"] == "wipe"
        # The token the runner watches is the run's — the one preempt() signals.
        assert runner.calls[0]["cancel_event"] is current[0]
        runtime.preempt()
        assert current[0].is_set()

    def test_frames_go_through_the_drivers_plain_send(self):
        runtime = OutputRuntime("b1")
        runtime.transition_runner = _RecordingRunner()
        driver = _driver()
        result = runtime.render(driver, _grid(2), strategy="plugin:wipe", plugins_enabled=lambda: True)

        assert result == (True, True)
        assert [c.args[0] for c in driver.send_characters.call_args_list] == [_grid(9), _grid(2)]
        for call in driver.send_characters.call_args_list:
            assert call.kwargs == {"strategy": None, "force": True}

    def test_the_runner_reads_the_drivers_declared_floor(self):
        runtime = OutputRuntime("b1")
        runner = _RecordingRunner()
        runtime.transition_runner = runner
        driver = _driver()
        driver.min_send_interval_ms = 15000
        runtime.render(driver, _grid(2), strategy="plugin:wipe", plugins_enabled=lambda: True)
        assert runner.calls[0]["min_send_interval_ms"] == 15000

    def test_beta_off_snaps_to_the_target_without_running_the_plugin(self):
        runtime = OutputRuntime("b1")
        runner = _RecordingRunner()
        runtime.transition_runner = runner
        driver = _driver()
        runtime.render(driver, _grid(2), strategy="plugin:wipe", force=True, plugins_enabled=lambda: False)
        assert runner.calls == []
        driver.send_characters.assert_called_once_with(_grid(2), strategy=None, force=True)

    def test_a_driver_that_cannot_animate_snaps_to_the_target(self):
        runtime = OutputRuntime("b1")
        runner = _RecordingRunner()
        runtime.transition_runner = runner
        driver = _driver(animation="none")
        runtime.render(driver, _grid(2), strategy="plugin:wipe", plugins_enabled=lambda: True)
        assert runner.calls == []
        driver.send_characters.assert_called_once_with(_grid(2), strategy=None, force=False)

    def test_the_outcome_carries_the_runs_own_throttle_verdict(self):
        runtime = OutputRuntime("b1")
        runtime.transition_runner = _RecordingRunner()
        driver = _driver()
        driver.min_send_interval_ms = 15000
        sends = iter([(True, True), (True, False)])

        def send(grid, strategy=None, force=False):
            result = next(sends)
            # The snap (second send) is dropped by the floor.
            driver.last_send_throttled = result == (True, False)
            driver.last_send_retry_after = 12 if driver.last_send_throttled else None
            return result

        driver.send_characters.side_effect = send
        outcome = runtime.render(
            driver, _grid(2), strategy="plugin:wipe", with_outcome=True, plugins_enabled=lambda: True
        )
        # (_RecordingRunner answers with the snap's own pair.)
        assert outcome == SendOutcome(True, False, throttled=True, retry_after_seconds=12, floor_seconds=15)


# --- the runner lives on the runtime ----------------------------------------


class TestRunnerOwnership:
    def test_a_clients_runner_is_its_runtimes_runner(self):
        client = panel_driver("flagship")
        runtime = OutputRuntime("b1")
        client.set_output_runtime(runtime)
        runner = MagicMock()
        client.set_transition_runner(runner)
        assert runtime.transition_runner is runner

    def test_binding_carries_a_runner_attached_before_the_bind(self):
        # The engine attaches the runner, then BoardRuntime binds the client.
        client = panel_driver("flagship")
        runner = MagicMock()
        client.set_transition_runner(runner)
        rt = BoardRuntime(client=client, board_id="b1")
        assert rt.output.transition_runner is runner
