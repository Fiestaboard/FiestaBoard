"""Core polls output devices that cannot read back but can say they restarted.

A Divoom Pixoo loses FiestaBoard's frame when it reboots and falls back to its
own clock face. It has no read-back, so the board-state poll cannot see that,
and both dedupe layers (the runtime's page content and the driver's frame
cache) still believe the page is up: an unchanged page was never sent again.
A device that came back on a new DHCP address was worse — every write went to
the old one until someone re-ran the settings lookup.

``OutputPluginBase.poll_device`` lets the output report either; core re-sends
the board's content and saves the new settings.
"""

from __future__ import annotations

import threading
from unittest.mock import Mock, patch

from src.main import BoardRuntime, DisplayService
from src.outputs.breaker import output_breakers
from src.outputs.hooks import DevicePoll, ReadBack
from src.outputs.plugin_base import OutputPluginBase
from src.outputs.plugin_driver import OutputPluginDriver
from src.outputs.registry import OutputCapabilities
from src.send_outcome import WriteResult

GRID = [[1] * 16 for _ in range(10)]


class Panel(OutputPluginBase):
    """An LED panel with no read-back; ``news`` is what its next poll reports."""

    plugin_id = "acme_panel"

    def __init__(self, board_id="b1", config=None):
        super().__init__(board_id, config or {})
        self.news: DevicePoll | None = None
        self.polls = 0
        self.writes = 0

    def capabilities(self) -> OutputCapabilities:
        return OutputCapabilities(
            technology="led_matrix",
            delivery="push",
            animation="stream",
            native_transitions=frozenset(),
            read_back=ReadBack(supported=False, cost="cheap", suggested_interval_s=30),
        )

    def device_key(self) -> str:
        return "acme:192.0.2.10"

    def write(self, frame, *, native, cancel):
        self.writes += 1
        return WriteResult(True, True)

    def poll_device(self):
        self.polls += 1
        return self.news


class Silent(Panel):
    """An output that does not override the hook."""

    poll_device = OutputPluginBase.poll_device


class TestDriverPollDevice:
    def test_relays_the_plugins_news(self):
        plugin = Panel()
        plugin.news = DevicePoll(restarted=True)

        assert OutputPluginDriver(plugin).poll_device() == DevicePoll(restarted=True)

    def test_a_plugin_without_the_hook_is_never_asked(self):
        assert OutputPluginDriver(Silent()).poll_device() is None

    def test_skips_the_poll_while_a_write_holds_the_send_lock(self):
        plugin = Panel()
        plugin.news = DevicePoll(restarted=True)
        driver = OutputPluginDriver(plugin)
        held, release = threading.Event(), threading.Event()

        def writer():
            with driver._output_runtime.send_lock:
                held.set()
                release.wait(5)

        thread = threading.Thread(target=writer)
        thread.start()
        held.wait(5)
        try:
            assert driver.poll_device() is None
            assert plugin.polls == 0
        finally:
            release.set()
            thread.join()

    def test_a_raising_plugin_reports_nothing(self):
        plugin = Panel()
        plugin.poll_device = Mock(side_effect=RuntimeError("boom"))

        assert OutputPluginDriver(plugin).poll_device() is None

    def test_an_answer_that_is_not_a_device_poll_is_ignored(self):
        plugin = Panel()
        plugin.news = {"restarted": True}

        assert OutputPluginDriver(plugin).poll_device() is None

    def test_news_closes_the_devices_breaker(self):
        """Writes failed while the device booted; it answering now must not
        leave the re-send refused for the rest of the cool-down."""
        plugin = Panel()
        driver = OutputPluginDriver(plugin)
        key = driver._breaker_key()
        for _ in range(5):
            output_breakers().record_failure(key, "booting", 1000.0)
        assert output_breakers().state(key, 1000.0).open

        plugin.news = DevicePoll(restarted=True)
        driver.poll_device()

        assert output_breakers().state(key, 1000.0) is None

    def test_no_news_leaves_the_breaker_alone(self):
        plugin = Panel()
        driver = OutputPluginDriver(plugin)
        key = driver._breaker_key()
        for _ in range(5):
            output_breakers().record_failure(key, "unreachable", 1000.0)

        driver.poll_device()

        assert output_breakers().state(key, 1000.0).open


def _service_with(client, board_id="pixoo-1", *, paused=False):
    svc = DisplayService()
    rt = BoardRuntime(client, board_id)
    rt.last_active_page_content = "SHOWN"
    rt.last_active_page_id = "page-1"
    svc.runtimes = {board_id: rt}
    settings = Mock()
    settings.is_paused.return_value = paused
    return svc, rt, settings


class TestServicePollOutputDevices:
    def test_a_restart_makes_the_next_pass_resend_the_page(self):
        client = Mock()
        client.poll_device.return_value = DevicePoll(restarted=True)
        svc, rt, settings = _service_with(client)

        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_output_devices()

        assert rt.last_active_page_content is None
        assert rt.last_active_page_id is None
        client.clear_cache.assert_called_once()
        settings.update_board_output_config.assert_not_called()

    def test_a_moved_device_saves_its_new_settings_and_resends(self):
        client = Mock()
        client.poll_device.return_value = DevicePoll(config={"host": "192.0.2.23"})
        svc, rt, settings = _service_with(client)

        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_output_devices()

        settings.update_board_output_config.assert_called_once_with("pixoo-1", {"host": "192.0.2.23"})
        assert rt.last_active_page_content is None
        client.clear_cache.assert_called_once()

    def test_no_news_keeps_the_dedupe(self):
        client = Mock()
        client.poll_device.return_value = None
        svc, rt, settings = _service_with(client)

        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_output_devices()

        assert rt.last_active_page_content == "SHOWN"
        client.clear_cache.assert_not_called()

    def test_a_paused_board_is_never_polled(self):
        client = Mock()
        client.poll_device.return_value = DevicePoll(restarted=True)
        svc, rt, settings = _service_with(client, paused=True)

        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_output_devices()

        client.poll_device.assert_not_called()
        assert rt.last_active_page_content == "SHOWN"

    def test_end_to_end_a_reboot_resends_an_unchanged_page(self):
        """Through a real driver: after the device reports a restart, the
        same frame the driver already sent goes to the device again."""
        plugin = Panel()
        driver = OutputPluginDriver(plugin)
        assert driver.send_characters(GRID) == (True, True)
        assert driver.send_characters(GRID)[1] is False  # deduped: already shown
        svc, _rt, settings = _service_with(driver)

        plugin.news = DevicePoll(restarted=True)
        with patch("src.main.get_settings_service", return_value=settings):
            svc._poll_output_devices()

        assert driver.send_characters(GRID) == (True, True)
        assert plugin.writes == 2

    def test_the_board_poll_loop_runs_the_device_poll(self):
        svc = DisplayService()
        svc.running = True

        def one_pass():
            svc.running = False

        with (
            patch.object(svc, "_poll_output_devices") as poll_devices,
            patch.object(svc, "_poll_board_state_once", side_effect=one_pass),
            patch.object(svc, "_get_board_read_interval", return_value=0),
        ):
            svc._board_poll_loop()

        poll_devices.assert_called_once_with()
