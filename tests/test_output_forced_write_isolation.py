"""A timed-out writer must not change a later write's dedupe-bypass flag."""

import threading
import unittest

from src.outputs.breaker import output_breakers
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult


class BarrierOutput(OutputPluginBase):
    plugin_id = "qa_forced_output"

    def __init__(self):
        super().__init__("qa-board", {})
        self.budget_ms = 50
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release_first = threading.Event()
        self.first_thread = None
        self.observed = {}
        self.calls = 0
        self.shown = [[42]]
        self.sent = []

    def capabilities(self):
        return OutputCapabilities(
            technology="led_matrix", delivery="push", animation="none",
            native_transitions=frozenset(),
            write_timeout_ms=self.budget_ms,
        )

    def device_key(self):
        return "qa-forced-output"

    def write(self, frame, *, native, cancel):
        self.calls += 1
        if self.calls == 1:
            self.first_thread = threading.current_thread()
            self.first_started.set()
            if not self.release_first.wait(5):
                raise AssertionError("test did not release the timed-out writer")
            self.observed["old_force"] = self.forced
            self.observed["old_cancelled"] = cancel.cancelled
            # A slow but cooperative writer notices cancellation before I/O.
            return WriteResult(False, False)
        self.second_started.set()
        # Join the actual old output thread, including core's finally block.
        # Thus its cleanup has definitely finished before the new dedupe check.
        self.first_thread.join(3)
        if self.first_thread.is_alive():
            raise AssertionError("old output thread did not finish")
        self.observed["new_force"] = self.forced
        self.observed["new_cancelled"] = cancel.cancelled
        if frame == self.shown and not self.forced:
            return WriteResult(True, False)
        self.shown = [list(row) for row in frame]
        self.sent.append(self.shown)
        return WriteResult(True, True)


class ForcedWriteIsolation(unittest.TestCase):
    def setUp(self):
        output_breakers().clear()
        self.addCleanup(output_breakers().clear)

    def overlap(self, old_force, new_force):
        plugin = BarrierOutput()
        driver = OutputPluginDriver(plugin)
        self.addCleanup(driver.close)
        self.addCleanup(plugin.release_first.set)
        old = driver.send_characters([[43]], force=old_force, with_outcome=True)
        self.assertTrue(plugin.first_started.is_set())
        self.assertEqual((old.success, old.was_sent), (False, False))
        self.assertIn("did not finish", driver.last_write_error)
        self.assertIsNone(driver._frames.last_frame)
        plugin.budget_ms = 4000
        result = {}
        target = [[42]] if new_force else [[44]]

        def send_new():
            result["outcome"] = driver.send_characters(target, force=new_force, with_outcome=True)

        caller = threading.Thread(target=send_new)
        caller.start()
        try:
            self.assertTrue(plugin.second_started.wait(3), "new write did not start")
        finally:
            plugin.release_first.set()
            caller.join(5)
        self.assertFalse(caller.is_alive())
        self.assertFalse(plugin.first_thread.is_alive())
        # These are protocol/observable-dedupe expectations, not flag text checks.
        with self.subTest(boundary="old write keeps its own force mode"):
            self.assertEqual(plugin.observed["old_force"], old_force)
        with self.subTest(boundary="old cleanup cannot change new mode"):
            self.assertEqual(plugin.observed["new_force"], new_force)
        self.assertTrue(plugin.observed["old_cancelled"])
        self.assertFalse(plugin.observed["new_cancelled"])
        with self.subTest(boundary="target actually resent"):
            outcome = result["outcome"]
            self.assertEqual((outcome.success, outcome.was_sent), (True, True))
            self.assertEqual(plugin.sent, [target])
        self.assertEqual(driver._frames.last_frame, target)
        self.assertIsNone(driver.last_write_error)
        self.assertFalse(plugin.forced)

    def test_late_normal_cleanup_cannot_suppress_forced_resend(self):
        self.overlap(False, True)

    def test_new_normal_write_does_not_change_old_forced_mode(self):
        self.overlap(True, False)

    def test_late_forced_cleanup_cannot_suppress_another_forced_resend(self):
        self.overlap(True, True)

    def test_serial_modes_and_other_instance_remain_independent(self):
        for initialize_base in (False, True):
            with self.subTest(initialize_base=initialize_base):
                class RecordingOutput(OutputPluginBase):
                    plugin_id = "qa_recording_output"

                    def __init__(self, initialize_base=initialize_base):
                        if initialize_base:
                            super().__init__("qa-recording", {})
                        self.modes = []
                        self.other = None

                    def capabilities(self):
                        return OutputCapabilities(
                            technology="led_matrix", delivery="push", animation="none",
                            native_transitions=frozenset(),
                        )

                    def device_key(self):
                        return "qa-recording-output"

                    def write(self, frame, *, native, cancel):
                        self.modes.append((self.forced, self.other.forced))
                        return WriteResult(True, True)

                plugin = RecordingOutput()
                plugin.other = RecordingOutput()
                driver = OutputPluginDriver(plugin)
                self.addCleanup(driver.close)
                self.assertFalse(plugin.forced)
                self.assertTrue(driver.send_characters([[1]], force=True)[1])
                self.assertTrue(driver.send_characters([[2]], force=False)[1])
                self.assertEqual(plugin.modes, [(True, False), (False, False)])
                self.assertFalse(plugin.forced)

    def test_inline_failure_clears_force_on_the_calling_thread(self):
        class RaisingOutput(BarrierOutput):
            def write(self, frame, *, native, cancel):
                if not self.forced:
                    raise AssertionError("forced flag was not bound during write")
                raise ValueError("synthetic write failure")

        plugin = RaisingOutput()
        driver = OutputPluginDriver(plugin, first_party=True)
        self.addCleanup(driver.close)
        with self.assertRaisesRegex(ValueError, "synthetic write failure"):
            driver.send_characters([[1]], force=True)
        self.assertFalse(plugin.forced)


if __name__ == "__main__":
    unittest.main()
