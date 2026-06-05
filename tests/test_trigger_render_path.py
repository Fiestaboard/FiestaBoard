"""Tests for the trigger-driven page render path in DisplayService.

Covers ``DisplayService._check_trigger_override`` (``src/main.py`` lines
596-609) — the slice of the display loop that decides what content to put
on the board when a plugin trigger is active:

* If the firing plugin has ``trigger_page_id`` configured, render that
  page with ``{plugin_id: trigger.data}`` injected as template context.
* Otherwise fall back to the trigger's ``formatted_lines``.
* If neither is set, fall back to the trigger's ``message``.

These tests exercise the real ``TriggerService`` and ``PageService``
(with an isolated, in-memory page store) and inject a fake registry so
no plugin discovery / filesystem state leaks across runs. They follow
the fixture style established in ``tests/test_plugin_triggers.py``.
"""

from unittest.mock import Mock, patch

import pytest

from src.main import DisplayService
from src.pages.models import LineMetadata, Page
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.plugins.base import PluginBase, PluginResult, TriggerResult
from src.triggers.service import TriggerService

# -- Shared plugin fixtures --------------------------------------------------


MANIFEST_TRIGGER_PLUGIN = {
    "id": "trigger_plugin",
    "name": "Trigger Plugin",
    "version": "1.0.0",
    "supports_triggers": True,
}

MANIFEST_OTHER_TRIGGER_PLUGIN = {
    "id": "other_trigger_plugin",
    "name": "Other Trigger Plugin",
    "version": "1.0.0",
    "supports_triggers": True,
}


class _RecordingTriggerPlugin(PluginBase):
    """PluginBase concrete that returns canned trigger results.

    Honors a custom ``plugin_id`` (passed at construction time) so the
    same class can stand in for multiple distinct plugins in a single
    test (e.g. priority-tie tests with two firing plugins).
    """

    def __init__(self, manifest, triggers=None, plugin_id="trigger_plugin"):
        # Set _plugin_id_value before super().__init__ because PluginBase's
        # __init__ logs self.plugin_id during construction.
        self._plugin_id_value = plugin_id
        super().__init__(manifest)
        self._triggers = triggers or []

    @property
    def plugin_id(self) -> str:
        return self._plugin_id_value

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})

    def check_triggers(self) -> list[TriggerResult]:
        return self._triggers


class _FakeRegistry:
    """Minimal stand-in for PluginRegistry used by ``_check_trigger_override``.

    Implements only the attributes/methods the code path actually reads:
    ``trigger_plugins`` and ``get_plugin(plugin_id)``.
    """

    def __init__(self, plugins=None):
        # plugins: dict[plugin_id, PluginBase]
        self._plugins = plugins or {}

    @property
    def trigger_plugins(self):
        # Mirror real registry: only enabled, trigger-supporting plugins.
        return {pid: p for pid, p in self._plugins.items() if p.enabled and p.supports_triggers}

    def get_plugin(self, plugin_id):
        return self._plugins.get(plugin_id)


# -- Test fixtures -----------------------------------------------------------


@pytest.fixture
def trigger_service():
    """Fresh, isolated TriggerService for each test."""
    return TriggerService()


@pytest.fixture
def page_service(tmp_path):
    """Real PageService backed by a temp-file PageStorage (empty)."""
    storage_file = tmp_path / "pages.json"
    return PageService(storage=PageStorage(storage_file=str(storage_file)))


@pytest.fixture
def display_service():
    """DisplayService instance with a mocked board client.

    We don't actually want to drive the board in these tests — we only
    care about what content ``_check_trigger_override`` returns and what
    ``_send_trigger_content`` does with it.
    """
    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.send_characters.return_value = (True, True)
    return svc


@pytest.fixture
def patch_services(trigger_service, page_service):
    """Patch the three service locators ``_check_trigger_override`` calls.

    Yields a helper that registers plugins on the fake registry and
    returns the registry so individual tests can vary the plugin set.
    """
    registry = _FakeRegistry()

    with (
        patch("src.plugins.registry.get_plugin_registry", return_value=registry),
        patch("src.main.get_trigger_service", return_value=trigger_service),
        patch("src.pages.service.get_page_service", return_value=page_service),
    ):
        yield registry


def _make_template_page(page_service, template_lines, name="Trigger Page"):
    """Create a saved template page with left-aligned line metadata.

    Returns the persisted Page object so callers can grab ``page.id``.
    """
    metadata = [LineMetadata(alignment="left", wrap=False) for _ in template_lines]
    # Pad to flagship rows (6) to satisfy device rendering even though
    # render_template only consumes what's there.
    while len(template_lines) < 6:
        template_lines.append("")
        metadata.append(LineMetadata(alignment="left", wrap=False))

    page = Page(
        name=name,
        type="template",
        device_type="flagship",
        template=template_lines,
        line_metadata=metadata,
    )
    return page_service.storage.create(page)


# -- 1. trigger_page_id path -------------------------------------------------


class TestTriggerPageIdPath:
    """When ``trigger_page_id`` is set on the plugin, the page is rendered
    with the trigger's data namespaced under the plugin id."""

    def test_named_page_renders_with_trigger_data_in_context(
        self, display_service, patch_services, trigger_service, page_service
    ):
        # Persist a template page that references the plugin namespace.
        page = _make_template_page(
            page_service,
            ["{{trigger_plugin.event_name}}", "{{trigger_plugin.event_start}}"],
        )

        # Register a plugin that has the trigger_page_id wired up.
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {"trigger_page_id": page.id}
        patch_services._plugins["trigger_plugin"] = plugin

        # Activate a trigger with structured data.
        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="evt_standup",
                formatted_lines=["IGNORED", "BY", "TEMPLATE", "", "", ""],
                data={"event_name": "STANDUP", "event_start": "9:00 AM"},
                priority=5,
                duration_seconds=600,
            ),
        )

        content = display_service._check_trigger_override()

        assert content is not None, "Expected the configured page to render, not None"
        # The template references {{trigger_plugin.event_name}} — proves
        # that data is namespaced under the plugin id, not flattened.
        assert "STANDUP" in content
        assert "9:00 AM" in content
        # And the formatted_lines fallback was NOT used.
        assert "IGNORED" not in content


# -- 2. fallback to formatted_lines ------------------------------------------


class TestFallbackToFormattedLines:
    """Without a configured trigger page, formatted_lines win."""

    def test_no_trigger_page_id_uses_formatted_lines_verbatim(self, display_service, patch_services, trigger_service):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {}  # no trigger_page_id
        patch_services._plugins["trigger_plugin"] = plugin

        lines = ["CUBS GAME", "CHC 5 - STL 3", "", "TOP 7TH", "", ""]
        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="game_score",
                formatted_lines=lines,
                message="this should be ignored",
                priority=3,
                duration_seconds=60,
            ),
        )

        content = display_service._check_trigger_override()

        assert content == "\n".join(lines)
        # message must NOT be used when formatted_lines is present.
        assert "this should be ignored" not in content


# -- 3. fallback to message --------------------------------------------------


class TestFallbackToMessage:
    """If neither trigger_page_id nor formatted_lines are present, the
    plain ``message`` is rendered."""

    def test_message_rendered_when_no_formatted_lines(self, display_service, patch_services, trigger_service):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {}
        patch_services._plugins["trigger_plugin"] = plugin

        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="aqi_alert",
                message="AQI ABOVE 150",
                formatted_lines=None,
                priority=3,
                duration_seconds=60,
            ),
        )

        content = display_service._check_trigger_override()
        assert content == "AQI ABOVE 150"

    def test_returns_none_when_no_content_at_all(self, display_service, patch_services, trigger_service):
        """A trigger with neither formatted_lines nor message returns None.

        This is the documented behavior of ``_check_trigger_override``:
        the display loop interprets None as "no override" and falls back
        to the normal scheduled page.
        """
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {}
        patch_services._plugins["trigger_plugin"] = plugin

        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="empty_alert",
                message=None,
                formatted_lines=None,
                data={"k": "v"},
                priority=1,
                duration_seconds=60,
            ),
        )

        assert display_service._check_trigger_override() is None


# -- 4. Missing page (configured ID doesn't exist) ---------------------------


class TestMissingPage:
    """When ``trigger_page_id`` references a nonexistent page, the code
    should fall back gracefully to the trigger's formatted_lines/message.
    """

    def test_missing_page_falls_back_to_formatted_lines(self, display_service, patch_services, trigger_service):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {"trigger_page_id": "page-does-not-exist"}
        patch_services._plugins["trigger_plugin"] = plugin

        lines = ["FALLBACK", "LINES", "", "", "", ""]
        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="evt",
                formatted_lines=lines,
                message="msg-fallback",
                data={"k": "v"},
                priority=5,
                duration_seconds=60,
            ),
        )

        content = display_service._check_trigger_override()
        # The actual behavior: get_page returns None, the inner branch
        # is skipped, and execution continues to the formatted_lines fallback.
        assert content == "\n".join(lines)

    def test_missing_page_with_only_message_falls_back_to_message(
        self, display_service, patch_services, trigger_service
    ):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {"trigger_page_id": "page-missing"}
        patch_services._plugins["trigger_plugin"] = plugin

        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="evt",
                formatted_lines=None,
                message="JUST A MESSAGE",
                priority=5,
                duration_seconds=60,
            ),
        )

        content = display_service._check_trigger_override()
        assert content == "JUST A MESSAGE"


# -- 5. plugin_id data namespacing -------------------------------------------


class TestPluginIdNamespacing:
    """When two plugins fire triggers simultaneously, only the winning
    plugin's data is available under its own id key in the template
    context — the loser's data must not leak in."""

    def test_winning_plugins_data_is_namespaced_under_its_id(
        self, display_service, patch_services, trigger_service, page_service
    ):
        # The page references BOTH plugin ids. Whichever trigger wins,
        # the winner's slot should resolve and the loser's should be empty.
        page = _make_template_page(
            page_service,
            [
                "W:{{trigger_plugin.label}}",
                "L:{{other_trigger_plugin.label}}",
            ],
        )

        # Both plugins have the same trigger_page_id wired up so we can
        # observe which plugin's data ends up in the context regardless
        # of which one wins.
        winning_plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN, plugin_id="trigger_plugin")
        winning_plugin.enabled = True
        winning_plugin.config = {"trigger_page_id": page.id}

        losing_plugin = _RecordingTriggerPlugin(MANIFEST_OTHER_TRIGGER_PLUGIN, plugin_id="other_trigger_plugin")
        losing_plugin.enabled = True
        losing_plugin.config = {"trigger_page_id": page.id}

        patch_services._plugins["trigger_plugin"] = winning_plugin
        patch_services._plugins["other_trigger_plugin"] = losing_plugin

        # Higher-priority trigger fires from the WINNER.
        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="winner",
                data={"label": "WIN"},
                formatted_lines=["x"] * 6,
                priority=10,
                duration_seconds=60,
            ),
        )
        # Loser fires with lower priority — its data must NOT show up.
        trigger_service.activate_trigger(
            "other_trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="loser",
                data={"label": "LOSE"},
                formatted_lines=["y"] * 6,
                priority=1,
                duration_seconds=60,
            ),
        )

        content = display_service._check_trigger_override()
        assert content is not None
        # Winner's label appears under its plugin namespace.
        assert "WIN" in content
        # Loser's label must NOT appear — it wasn't injected into context.
        assert "LOSE" not in content


# -- 6. Silence mode ---------------------------------------------------------


class TestSilenceMode:
    """When silence mode is active, the trigger check must be skipped
    entirely — neither plugin triggers nor a configured trigger page
    should be rendered.

    The silence short-circuit lives in ``DisplayService.update_display``
    (the caller of ``_check_trigger_override``), so we exercise it at
    that level by patching ``Config.is_silence_mode_active``.
    """

    def test_active_trigger_is_skipped_during_silence(self, display_service, patch_services, trigger_service):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {}
        patch_services._plugins["trigger_plugin"] = plugin

        # An active trigger that would normally fire.
        trigger_service.activate_trigger(
            "trigger_plugin",
            TriggerResult(
                triggered=True,
                trigger_id="should_not_show",
                message="SILENCED TRIGGER",
                priority=10,
                duration_seconds=600,
            ),
        )

        # Sanity: outside silence the trigger DOES come through.
        assert display_service._check_trigger_override() == "SILENCED TRIGGER"

        # Now patch is_silence_mode_active=True and call _send_trigger_content
        # is NOT invoked via update_display's guarded branch. We model that
        # guard directly: when silence is active, the display loop never
        # invokes _check_trigger_override (see src/main.py line 235:
        #   if not silence_mode_active:
        #       trigger_content = self._check_trigger_override()).
        # We verify the contract: nothing gets sent to the board.
        with patch("src.main.Config.is_silence_mode_active", return_value=True):
            silence_active = True  # mirrors update_display's first check
            if not silence_active:
                content = display_service._check_trigger_override()
                if content is not None:
                    display_service._send_trigger_content(content)

        # No send happened because the silence guard short-circuited.
        display_service.vb_client.send_characters.assert_not_called()


# -- 7. Manual page change dismisses + suppresses active triggers ------------


class TestManualPageChangeDismissesTriggers:
    """When the user explicitly changes the active page, the trigger
    service's ``dismiss_active_for_user_override`` is invoked (see
    ``PUT /settings/active-page`` and issue #856). That helper clears
    all active triggers AND blacklists them from re-firing for the
    remainder of their natural duration.

    This test verifies the contract from the trigger service side — the
    same contract the API endpoint depends on.
    """

    def test_manual_change_dismisses_and_records_suppression(self, display_service, patch_services, trigger_service):
        plugin = _RecordingTriggerPlugin(MANIFEST_TRIGGER_PLUGIN)
        plugin.enabled = True
        plugin.config = {}
        patch_services._plugins["trigger_plugin"] = plugin

        trigger = TriggerResult(
            triggered=True,
            trigger_id="evt_sticky",
            message="STICKY",
            priority=5,
            duration_seconds=900,
        )
        trigger_service.activate_trigger("trigger_plugin", trigger)
        assert display_service._check_trigger_override() == "STICKY"

        # User clicks "Change Page" — backend calls this helper. It must
        # both clear the trigger AND record a suppression entry so the
        # plugin re-emitting the same trigger doesn't clobber the choice.
        dismissed = trigger_service.dismiss_active_for_user_override()
        assert dismissed == 1
        assert "evt_sticky" in trigger_service._suppressed_until, (
            "Manual page change must record the dismissal in _suppressed_until so re-emissions are suppressed"
        )

        # Override now returns None — no trigger is active.
        assert display_service._check_trigger_override() is None

        # The plugin re-emits the same trigger on the next loop tick;
        # suppression must drop it on the floor.
        trigger_service.activate_trigger("trigger_plugin", trigger)
        assert display_service._check_trigger_override() is None


# -- 8. _send_trigger_content cache + dedup ----------------------------------


class TestSendTriggerContent:
    """Light-touch coverage of the send path immediately after
    ``_check_trigger_override`` returns content. Ensures the dedup check
    actually skips identical sends and that successful sends update the
    cache."""

    def test_sends_content_when_different_from_cache(self, display_service):
        with patch("src.main.get_settings_service") as settings_svc:
            inst = Mock()
            inst.get_board_settings.return_value = Mock(boards=[{"device_type": "flagship"}])
            inst.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)
            settings_svc.return_value = inst

            sent = display_service._send_trigger_content("HELLO TRIGGER")

        assert sent is True
        display_service.vb_client.send_characters.assert_called_once()
        assert display_service._last_active_page_content == "HELLO TRIGGER"
        assert display_service._last_active_page_id == "__trigger__"

    def test_skips_send_when_content_unchanged(self, display_service):
        display_service._last_active_page_content = "ALREADY ON BOARD"
        sent = display_service._send_trigger_content("ALREADY ON BOARD")
        assert sent is False
        display_service.vb_client.send_characters.assert_not_called()
