"""Tests for the platform-level trigger plumbing additions.

Covers the three platform improvements introduced for plugin authors:

1. Auto-injection of ``trigger_page_id`` into the effective settings_schema
   for plugins that declare ``supports_triggers: true``.
2. The :meth:`PluginBase.fire_trigger` synchronous helper used by webhook-
   driven plugins to submit a trigger immediately.
3. The :class:`TriggerPriority` published priority scale.
"""

import pytest

from src.plugins.base import PluginBase, PluginResult, TriggerResult
from src.plugins.manifest import (
    TRIGGER_PAGE_ID_PROPERTY,
    PluginManifest,
    _inject_trigger_page_id,
)
from src.triggers import TriggerPriority
from src.triggers.service import (
    TriggerService,
    get_trigger_service,
    reset_trigger_service,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _TriggerPlugin(PluginBase):
    """Minimal trigger-capable plugin used across tests."""

    @property
    def plugin_id(self) -> str:
        return "fire_plugin"

    def fetch_data(self) -> PluginResult:
        return PluginResult(available=True, data={})

    def check_triggers(self) -> list[TriggerResult]:
        return []


def _make_manifest(
    *,
    supports_triggers: bool = True,
    extra_properties: dict | None = None,
    plugin_id: str = "fire_plugin",
) -> dict:
    schema_properties: dict = {
        "api_key": {"type": "string", "title": "API Key"},
    }
    if extra_properties:
        schema_properties.update(extra_properties)
    return {
        "id": plugin_id,
        "name": "Fire Plugin",
        "version": "1.0.0",
        "supports_triggers": supports_triggers,
        "settings_schema": {
            "type": "object",
            "properties": schema_properties,
        },
    }


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test runs with a clean TriggerService singleton."""
    reset_trigger_service()
    yield
    reset_trigger_service()


# ---------------------------------------------------------------------------
# Gap 1 — auto-inject trigger_page_id into the effective settings_schema
# ---------------------------------------------------------------------------


class TestTriggerPageIdInjection:
    """``trigger_page_id`` should appear on every trigger-capable plugin."""

    def test_field_injected_when_supports_triggers_true(self):
        data = _make_manifest(supports_triggers=True)
        manifest = PluginManifest.from_dict(data)

        props = manifest.settings_schema["properties"]
        assert "trigger_page_id" in props
        field = props["trigger_page_id"]
        assert field["type"] == "string"
        # The page-picker widget marker is what surfaces the picker in the UI.
        assert field["ui:widget"] == "page-picker"

    def test_field_not_injected_when_supports_triggers_false(self):
        data = _make_manifest(supports_triggers=False)
        manifest = PluginManifest.from_dict(data)
        assert "trigger_page_id" not in manifest.settings_schema.get("properties", {})

    def test_author_override_wins(self):
        """If a plugin author declares ``trigger_page_id`` themselves, keep it."""
        custom = {
            "type": "string",
            "title": "Custom Picker Title",
            "description": "Where I want this thing rendered",
            "ui:widget": "page-picker",
            "default": "page-foo",
        }
        data = _make_manifest(extra_properties={"trigger_page_id": custom})
        manifest = PluginManifest.from_dict(data)
        assert manifest.settings_schema["properties"]["trigger_page_id"] == custom

    def test_injection_does_not_mutate_input_dict(self):
        """The on-disk manifest dict must remain untouched."""
        data = _make_manifest(supports_triggers=True)
        original_props = dict(data["settings_schema"]["properties"])
        PluginManifest.from_dict(data)
        assert data["settings_schema"]["properties"] == original_props
        assert "trigger_page_id" not in data["settings_schema"]["properties"]

    def test_inject_helper_handles_missing_schema(self):
        """The injector must cope with manifests that omit settings_schema."""
        enriched = _inject_trigger_page_id({})
        assert enriched["type"] == "object"
        assert "trigger_page_id" in enriched["properties"]

    def test_raw_settings_schema_carries_injected_field(self):
        """The plugin instance reads from ``manifest.raw`` — that copy must
        carry the injected field so ``plugin.get_settings_schema`` returns it."""
        data = _make_manifest(supports_triggers=True)
        manifest = PluginManifest.from_dict(data)
        raw_props = manifest.raw["settings_schema"]["properties"]
        assert "trigger_page_id" in raw_props

    def test_canonical_property_marker_constant_exposed(self):
        """``TRIGGER_PAGE_ID_PROPERTY`` is exported so other modules
        (e.g. the registry serialiser) can reference the canonical shape."""
        assert TRIGGER_PAGE_ID_PROPERTY["ui:widget"] == "page-picker"
        assert TRIGGER_PAGE_ID_PROPERTY["type"] == "string"


# ---------------------------------------------------------------------------
# Gap 2 — PluginBase.fire_trigger helper
# ---------------------------------------------------------------------------


class TestFireTrigger:
    def test_fire_trigger_enqueues_to_active_service(self):
        plugin = _TriggerPlugin(_make_manifest(supports_triggers=True))
        plugin.enabled = True

        plugin.fire_trigger(
            TriggerResult(
                triggered=True,
                trigger_id="webhook_event",
                message="Doorbell rang",
                priority=TriggerPriority.URGENT,
                duration_seconds=60,
            )
        )

        service = get_trigger_service()
        active = service.list_active_triggers()
        assert len(active) == 1
        assert active[0].trigger_id == "webhook_event"
        assert active[0].plugin_id == "fire_plugin"
        assert active[0].message == "Doorbell rang"

    def test_fire_trigger_works_from_receive_payload(self):
        """Push-driven plugins should be able to fire from receive_payload."""

        class WebhookPlugin(PluginBase):
            @property
            def plugin_id(self) -> str:
                return "fire_plugin"

            def fetch_data(self) -> PluginResult:
                return PluginResult(available=True, data={})

            def receive_payload(self, payload, headers, raw_body=b""):
                self.fire_trigger(
                    TriggerResult(
                        triggered=True,
                        trigger_id=f"event_{payload['event_id']}",
                        message=payload["message"],
                        priority=TriggerPriority.NOTABLE,
                        duration_seconds=30,
                        data=payload,
                    )
                )

        plugin = WebhookPlugin(_make_manifest(supports_triggers=True))
        plugin.enabled = True
        plugin.receive_payload(
            {"event_id": "abc123", "message": "Build failed"},
            headers={},
        )

        service = get_trigger_service()
        active = service.get_active_trigger()
        assert active is not None
        assert active.trigger_id == "event_abc123"
        assert active.data["event_id"] == "abc123"

    def test_fire_trigger_noop_when_plugin_does_not_support_triggers(self):
        """Calling fire_trigger on a non-trigger plugin must be a safe no-op."""
        plugin = _TriggerPlugin(_make_manifest(supports_triggers=False))
        plugin.enabled = True
        plugin.fire_trigger(
            TriggerResult(
                triggered=True,
                trigger_id="dropped",
                message="Should not surface",
            )
        )
        service = get_trigger_service()
        assert service.list_active_triggers() == []

    def test_fire_trigger_noop_when_not_triggered(self):
        """A TriggerResult with triggered=False must be ignored."""
        plugin = _TriggerPlugin(_make_manifest(supports_triggers=True))
        plugin.enabled = True
        plugin.fire_trigger(TriggerResult(triggered=False, trigger_id="not_yet"))
        assert get_trigger_service().list_active_triggers() == []

    def test_fire_trigger_defaults_trigger_id_to_plugin_id(self):
        """If the caller omits trigger_id we fall back to the plugin id so
        the service dict key stays stable (rather than ``""``)."""
        plugin = _TriggerPlugin(_make_manifest(supports_triggers=True))
        plugin.enabled = True
        plugin.fire_trigger(TriggerResult(triggered=True, message="No ID supplied"))
        service = get_trigger_service()
        active = service.list_active_triggers()
        assert len(active) == 1
        assert active[0].trigger_id == "fire_plugin"

    def test_fire_trigger_respects_user_suppression(self):
        """User-dismissed triggers stay suppressed even when re-fired by a
        webhook — fire_trigger delegates to ``activate_trigger`` which
        already honours the suppression list."""
        plugin = _TriggerPlugin(_make_manifest(supports_triggers=True))
        plugin.enabled = True

        trigger = TriggerResult(
            triggered=True,
            trigger_id="muted",
            message="Should be suppressed",
            priority=TriggerPriority.NOTABLE,
            duration_seconds=600,
        )
        plugin.fire_trigger(trigger)

        service = get_trigger_service()
        service.dismiss_trigger("muted", suppress=True)
        assert service.get_active_trigger() is None

        # Webhook arrives again — must remain suppressed.
        plugin.fire_trigger(trigger)
        assert service.get_active_trigger() is None


# ---------------------------------------------------------------------------
# Gap 3 — TriggerPriority published scale
# ---------------------------------------------------------------------------


class TestTriggerPriority:
    def test_documented_tiers(self):
        assert TriggerPriority.AMBIENT == 10
        assert TriggerPriority.NOTABLE == 50
        assert TriggerPriority.URGENT == 80
        assert TriggerPriority.CRITICAL == 100

    def test_ordering_holds(self):
        ordered = sorted(
            [
                TriggerPriority.URGENT,
                TriggerPriority.AMBIENT,
                TriggerPriority.CRITICAL,
                TriggerPriority.NOTABLE,
            ]
        )
        assert ordered == [
            TriggerPriority.AMBIENT,
            TriggerPriority.NOTABLE,
            TriggerPriority.URGENT,
            TriggerPriority.CRITICAL,
        ]

    def test_integer_priorities_still_supported(self):
        """The enum is a label on top of an int — raw integer ``priority``
        values continue to work for backwards compatibility."""
        trigger = TriggerResult(
            triggered=True,
            trigger_id="raw_int",
            priority=42,
            duration_seconds=30,
        )
        assert trigger.priority == 42

    def test_enum_value_usable_as_priority(self):
        """Enum values pass straight into TriggerResult.priority."""
        trigger = TriggerResult(
            triggered=True,
            trigger_id="urgent",
            priority=TriggerPriority.URGENT,
            duration_seconds=30,
        )
        # IntEnum compares equal to its integer value.
        assert trigger.priority == 80
        assert int(trigger.priority) == 80

    def test_higher_priority_wins_in_trigger_service(self):
        svc = TriggerService()
        svc.activate_trigger(
            "p1",
            TriggerResult(
                triggered=True,
                trigger_id="ambient",
                priority=TriggerPriority.AMBIENT,
                duration_seconds=60,
                message="Now playing",
            ),
        )
        svc.activate_trigger(
            "p2",
            TriggerResult(
                triggered=True,
                trigger_id="critical",
                priority=TriggerPriority.CRITICAL,
                duration_seconds=60,
                message="Smoke alarm",
            ),
        )
        active = svc.get_active_trigger()
        assert active is not None
        assert active.trigger_id == "critical"

    def test_exported_from_triggers_package(self):
        """Authors import directly from ``src.triggers``."""
        from src.triggers import TriggerPriority as Exported

        assert Exported is TriggerPriority
