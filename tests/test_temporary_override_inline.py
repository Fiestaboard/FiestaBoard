"""Tests for inline (one-off) temporary overrides — issue #1787.

A temporary override may now carry either a saved ``page_id`` OR inline
``template`` content that was never persisted as a Page. Inline overrides are
also allowed to be *indefinite* (no ``expires_at``), because in manual mode a
one-off message that silently vanishes after N minutes is not what the user
asked for.

Covers the service layer: round-trip, indefinite expiry semantics,
exactly-one-of validation, restart survival, and the v1 -> v2 settings
migration.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.settings.service import (
    CURRENT_SETTINGS_SCHEMA_VERSION,
    SettingsService,
    TemporaryOverride,
    _migrate_v1_to_v2,
)


@pytest.fixture
def tmp_settings_file(tmp_path):
    return tmp_path / "settings.json"


# ---------------------------------------------------------------------------
# Inline round-trip
# ---------------------------------------------------------------------------


class TestInlineOverrideRoundTrip:
    def test_inline_override_round_trips_through_to_dict_and_from_dict(self):
        override = TemporaryOverride(
            template=["HELLO", "WORLD"],
            line_metadata=[{"alignment": "center", "wrap": False}],
            device_type="note",
            revert_mode="schedule",
        )
        restored = TemporaryOverride.from_dict(override.to_dict())
        assert restored.template == ["HELLO", "WORLD"]
        assert restored.line_metadata == [{"alignment": "center", "wrap": False}]
        assert restored.device_type == "note"
        assert restored.page_id is None

    def test_inline_override_is_stored_and_read_back_by_the_service(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        svc.set_temporary_override(TemporaryOverride(template=["ONE OFF"], device_type="flagship"))
        result = svc.get_temporary_override()
        assert result is not None
        assert result.template == ["ONE OFF"]
        assert result.page_id is None

    def test_is_inline_distinguishes_the_two_forms(self):
        assert TemporaryOverride(template=["HI"]).is_inline is True
        assert TemporaryOverride(page_id="p1").is_inline is False


# ---------------------------------------------------------------------------
# Indefinite overrides (expires_at is None)
# ---------------------------------------------------------------------------


class TestIndefiniteOverride:
    def test_override_without_expiry_never_expires(self):
        assert TemporaryOverride(template=["FOREVER"]).is_expired() is False

    def test_override_without_expiry_has_no_remaining_seconds(self):
        assert TemporaryOverride(template=["FOREVER"]).remaining_seconds() is None

    def test_indefinite_override_is_still_live_after_a_service_restart(self, tmp_settings_file):
        svc1 = SettingsService(settings_file=str(tmp_settings_file))
        svc1.set_temporary_override(TemporaryOverride(template=["STILL HERE"], device_type="flagship"))
        svc2 = SettingsService(settings_file=str(tmp_settings_file))
        result = svc2.get_temporary_override()
        assert result is not None
        assert result.template == ["STILL HERE"]
        assert result.expires_at is None

    def test_expiring_inline_override_still_expires(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        svc._temporary_override = TemporaryOverride(template=["GONE"], expires_at=past)
        assert svc.get_temporary_override() is None

    def test_consume_does_not_clear_an_indefinite_override(self, tmp_settings_file):
        svc = SettingsService(settings_file=str(tmp_settings_file))
        svc.set_temporary_override(TemporaryOverride(template=["KEEP ME"]))
        result = svc.consume_temporary_override()
        assert result is not None
        assert result.is_expired() is False
        assert svc._temporary_override is not None


# ---------------------------------------------------------------------------
# Exactly-one-of validation
# ---------------------------------------------------------------------------


class TestExactlyOneOfValidation:
    def test_supplying_both_page_id_and_template_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            TemporaryOverride(page_id="p1", template=["HI"])

    def test_supplying_neither_page_id_nor_template_raises(self):
        with pytest.raises(ValueError, match="exactly one"):
            TemporaryOverride()

    def test_empty_template_list_counts_as_no_content(self):
        with pytest.raises(ValueError, match="exactly one"):
            TemporaryOverride(template=[])

    def test_corrupt_stored_override_is_discarded_rather_than_crashing(self, tmp_settings_file):
        tmp_settings_file.write_text(
            json.dumps(
                {
                    "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION,
                    "temporary_override": {"revert_mode": "schedule"},
                }
            )
        )
        svc = SettingsService(settings_file=str(tmp_settings_file))
        assert svc.get_temporary_override() is None


# ---------------------------------------------------------------------------
# Settings schema migration v1 -> v2
# ---------------------------------------------------------------------------


class TestSettingsMigrationV1ToV2:
    def test_schema_version_is_at_least_2(self):
        assert CURRENT_SETTINGS_SCHEMA_VERSION >= 2

    def test_migration_backfills_the_inline_fields_on_a_stored_override(self):
        data = {
            "temporary_override": {
                "page_id": "p1",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "revert_mode": "schedule",
                "revert_page_id": None,
            }
        }
        changed = _migrate_v1_to_v2(data)
        assert changed == 1
        override = data["temporary_override"]
        assert override["template"] is None
        assert override["line_metadata"] is None
        assert override["device_type"] is None
        # The page_id form is untouched
        assert override["page_id"] == "p1"

    def test_migration_is_idempotent(self):
        data = {
            "temporary_override": {
                "page_id": "p1",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "revert_mode": "schedule",
                "revert_page_id": None,
            }
        }
        _migrate_v1_to_v2(data)
        snapshot = json.dumps(data, sort_keys=True)
        assert _migrate_v1_to_v2(data) == 0
        assert json.dumps(data, sort_keys=True) == snapshot

    def test_migration_is_a_noop_without_a_stored_override(self):
        data = {"temporary_override": None}
        assert _migrate_v1_to_v2(data) == 0

    def test_a_v1_settings_file_loads_its_override_after_migration(self, tmp_settings_file):
        future = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        tmp_settings_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "temporary_override": {
                        "page_id": "legacy-page",
                        "expires_at": future,
                        "revert_mode": "blank",
                        "revert_page_id": None,
                    },
                }
            )
        )
        svc = SettingsService(settings_file=str(tmp_settings_file))
        result = svc.get_temporary_override()
        assert result is not None
        assert result.page_id == "legacy-page"
        assert result.template is None
        stored = json.loads(tmp_settings_file.read_text())
        assert stored["schema_version"] == CURRENT_SETTINGS_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# API: POST/GET /settings/temporary-override with inline content
# ---------------------------------------------------------------------------


@pytest.fixture
def settings_service(tmp_settings_file):
    return SettingsService(settings_file=str(tmp_settings_file))


@pytest.fixture
def client(settings_service):
    """TestClient with the settings + page service singletons patched.

    A page with id ``page-001`` exists so the legacy page_id form still works.
    """
    from unittest.mock import MagicMock, patch

    from fastapi.testclient import TestClient

    from src.api_server import app

    page_mock = MagicMock()
    page_mock.id = "page-001"
    page_mock.name = "Test Page"
    page_service_mock = MagicMock()
    page_service_mock.get_page.side_effect = lambda pid: page_mock if pid == "page-001" else None

    with (
        patch("src.api_server.get_settings_service", return_value=settings_service),
        patch("src.settings.service.get_settings_service", return_value=settings_service),
        patch("src.api_server.get_page_service", return_value=page_service_mock),
        patch("src.api_server.get_collection_service") as mock_cs,
    ):
        mock_cs.return_value.get_collection.return_value = None
        yield TestClient(app), settings_service


class TestPostInlineOverride:
    def test_inline_template_without_duration_creates_an_indefinite_override(self, client):
        api, svc = client
        r = api.post("/settings/temporary-override", json={"template": ["HELLO", "WORLD"]})
        assert r.status_code == 200
        data = r.json()
        assert data["active"] is True
        assert data["page_id"] is None
        assert data["template"] == ["HELLO", "WORLD"]
        assert data["expires_at"] is None
        assert data["remaining_seconds"] is None
        stored = svc.get_temporary_override()
        assert stored is not None
        assert stored.template == ["HELLO", "WORLD"]

    def test_inline_template_with_duration_still_expires(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"template": ["BYE"], "duration_minutes": 5})
        assert r.status_code == 200
        data = r.json()
        assert data["expires_at"] is not None
        assert 280 < data["remaining_seconds"] <= 300

    def test_inline_template_carries_line_metadata_and_device_type(self, client):
        api, svc = client
        r = api.post(
            "/settings/temporary-override",
            json={
                "template": ["CENTERED"],
                "line_metadata": [{"alignment": "center", "wrap": False}],
                "device_type": "note",
            },
        )
        assert r.status_code == 200
        assert r.json()["device_type"] == "note"
        stored = svc.get_temporary_override()
        assert stored is not None
        assert stored.line_metadata == [{"alignment": "center", "wrap": False}]
        assert stored.device_type == "note"

    def test_both_page_id_and_template_returns_422(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"page_id": "page-001", "template": ["HI"]})
        assert r.status_code == 422

    def test_neither_page_id_nor_template_returns_422(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"duration_minutes": 5})
        assert r.status_code == 422

    def test_empty_template_returns_422(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"template": []})
        assert r.status_code == 422

    def test_non_string_template_lines_return_422(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"template": ["OK", 7]})
        assert r.status_code == 422

    def test_invalid_device_type_returns_422(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"template": ["HI"], "device_type": "billboard"})
        assert r.status_code == 422

    def test_page_id_form_without_duration_is_now_indefinite(self, client):
        api, _ = client
        r = api.post("/settings/temporary-override", json={"page_id": "page-001"})
        assert r.status_code == 200
        assert r.json()["expires_at"] is None

    def test_get_exposes_the_inline_form(self, client):
        api, _ = client
        api.post("/settings/temporary-override", json={"template": ["SHOW ME"], "device_type": "flagship"})
        r = api.get("/settings/temporary-override")
        assert r.status_code == 200
        data = r.json()
        assert data["active"] is True
        assert data["template"] == ["SHOW ME"]
        assert data["device_type"] == "flagship"
        assert data["remaining_seconds"] is None

    def test_active_schedule_payload_exposes_the_inline_form(self, client):
        api, _ = client
        api.post("/settings/temporary-override", json={"template": ["INLINE"]})
        r = api.get("/schedules/active/page")
        assert r.status_code == 200
        payload = r.json()["temporary_override"]
        assert payload["active"] is True
        assert payload["template"] == ["INLINE"]
        assert payload["remaining_seconds"] is None

    def test_clearing_an_inline_override_works(self, client):
        api, svc = client
        api.post("/settings/temporary-override", json={"template": ["TRANSIENT"]})
        r = api.delete("/settings/temporary-override")
        assert r.status_code == 200
        assert svc.get_temporary_override() is None


# ---------------------------------------------------------------------------
# Display loop renders inline content without any persisted page
# ---------------------------------------------------------------------------


@pytest.fixture
def display_service():
    from unittest.mock import Mock

    from src.main import DisplayService

    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.render.return_value = (True, True)
    return svc


def _display_loop_mocks(override):
    """Settings/page/schedule mocks for one un-silenced, un-paused primary tick."""
    from unittest.mock import Mock

    from src.displays.service import DisplayResult

    settings = Mock()
    settings.is_paused.return_value = False
    settings.is_schedule_enabled.return_value = False
    settings.get_active_page_id.return_value = None
    settings.consume_temporary_override.return_value = override
    settings.get_board_settings.return_value = Mock(boards=[{"device_type": "flagship"}])
    settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)

    page_service = Mock()
    # Nothing is persisted: any get_page/preview_page lookup means the loop
    # went down the saved-page path instead of rendering the inline content.
    page_service.get_page.return_value = None
    page_service.preview_page.return_value = None
    page_service.list_pages.return_value = []
    page_service.render_page.return_value = DisplayResult(
        display_type="page:template",
        formatted="ONE OFF",
        raw={},
        available=True,
    )

    config = Mock()
    config.is_silence_mode_active.return_value = False

    return settings, page_service, config


class TestDisplayLoopRendersInlineOverride:
    def _run(self, display_service, override):
        from unittest.mock import patch

        settings, page_service, config = _display_loop_mocks(override)
        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(display_service, "_check_trigger_override", return_value=None),
        ):
            sent = display_service.check_and_send_active_page()
        return sent, page_service

    def test_inline_override_is_rendered_and_sent(self, display_service):
        override = TemporaryOverride(template=["ONE OFF"], device_type="flagship")
        sent, page_service = self._run(display_service, override)

        assert sent is True
        page_service.render_page.assert_called_once()
        rendered_page = page_service.render_page.call_args[0][0]
        assert rendered_page.template == ["ONE OFF"]
        assert rendered_page.type == "template"
        display_service.vb_client.render.assert_called_once()

    def test_inline_override_never_touches_the_page_store(self, display_service):
        override = TemporaryOverride(template=["ONE OFF"], device_type="flagship")
        _, page_service = self._run(display_service, override)

        page_service.get_page.assert_not_called()
        page_service.preview_page.assert_not_called()

    def test_inline_override_is_sized_to_its_own_device_type(self, display_service):
        override = TemporaryOverride(template=["NOTE ONE OFF"], device_type="note")
        self._run(display_service, override)

        board_array = display_service.vb_client.render.call_args[0][0]
        assert len(board_array) == 3
        assert all(len(row) == 15 for row in board_array)

    def test_inline_line_metadata_reaches_the_rendered_page(self, display_service):
        override = TemporaryOverride(
            template=["CENTERED"],
            line_metadata=[{"alignment": "center", "wrap": False}],
            device_type="flagship",
        )
        _, page_service = self._run(display_service, override)

        rendered_page = page_service.render_page.call_args[0][0]
        assert rendered_page.line_metadata is not None
        assert rendered_page.line_metadata[0].alignment == "center"

    def test_indefinite_inline_override_does_not_trigger_revert(self, display_service):
        """An override with no expiry must never take the expiry/revert branch."""
        from unittest.mock import patch

        override = TemporaryOverride(template=["FOREVER"], revert_mode="blank")
        settings, page_service, config = _display_loop_mocks(override)
        with (
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(display_service, "_check_trigger_override", return_value=None),
            patch.object(display_service, "_send_blank_board") as blank,
        ):
            display_service.check_and_send_active_page()

        blank.assert_not_called()
        page_service.render_page.assert_called_once()
