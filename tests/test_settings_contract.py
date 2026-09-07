"""Value-level contract goldens for the /settings API (Phase 2 §2, Task 8).

These are deliberately *values*, not shapes. The shape corpus records key sets
and type names, so it cannot see a status code that moved, an error string that
stopped naming the missing resource, or a boolean field that silently started
accepting ``"yes"`` — the class of regression Phase 1's masking bug proved
shape goldens miss.

Every assertion below is a promise this domain makes to the web client. This
file is recorded against the **unconverted** handlers, immediately after the
pure move that created ``src/settings/routes.py`` and before any conventions
work. It must pass here. The conversion commits that follow re-pin only what
they deliberately change, each with a comment naming the change; anything
without such a comment is a promise the conversion kept.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


def _primary_board_id(client: TestClient) -> str:
    boards = client.get("/settings/board").json()["boards"]
    assert boards, "the default install always seeds one board"
    return boards[0]["id"]


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


class TestMqtt:
    def test_get_returns_the_masked_mqtt_block_with_its_defaults(self, client):
        body = client.get("/settings/mqtt").json()
        assert body == {
            "enabled": False,
            "broker_host": "localhost",
            "broker_port": 1883,
            "username": "",
            "password": "",
            "external_url": "",
        }

    def test_put_persists_the_broker_host_and_echoes_the_masked_block(self, client):
        with patch("src.api_server._apply_mqtt_config") as apply_mqtt:
            response = client.put(
                "/settings/mqtt",
                json={"enabled": False, "broker_host": "mqtt.example.com", "password": "s3cret"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["broker_host"] == "mqtt.example.com"
        # The password never round-trips in the clear.
        assert body["password"] == "***"
        assert apply_mqtt.call_count == 1
        assert client.get("/settings/mqtt").json()["broker_host"] == "mqtt.example.com"


# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------


class TestAiProviders:
    def test_get_returns_the_empty_provider_block(self, client):
        assert client.get("/settings/ai").json() == {
            "enabled": False,
            "providers": [],
            "default_provider_id": None,
        }

    def test_put_persists_enabled_and_returns_the_masked_block(self, client):
        body = client.put("/settings/ai", json={"enabled": True}).json()
        assert body["enabled"] is True
        assert client.get("/settings/ai").json()["enabled"] is True

    def test_put_rejects_a_non_object_body(self, client):
        response = client.put("/settings/ai", json=["not", "an", "object"])
        # CHANGED (conventions, typed_body): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "Body must be a JSON object."}.
        assert response.status_code == 422

    def test_test_endpoint_400s_when_no_provider_is_configured(self, client):
        response = client.post("/settings/ai/test", json={})
        assert response.status_code == 400
        assert response.json() == {"detail": "No AI providers are configured."}

    def test_test_endpoint_404s_for_an_unknown_provider_id(self, client):
        client.put(
            "/settings/ai",
            json={
                "enabled": True,
                "providers": [{"id": "p1", "name": "P1", "base_url": "https://example.invalid", "api_key": "k"}],
                "default_provider_id": "p1",
            },
        )
        response = client.post("/settings/ai/test", json={"provider_id": "nope"})
        assert response.status_code == 404
        assert response.json() == {"detail": "AI provider 'nope' not found."}


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


class TestTransitions:
    def test_get_returns_the_defaults_and_the_full_strategy_list(self, client):
        assert client.get("/settings/transitions").json() == {
            "strategy": None,
            "step_interval_ms": None,
            "step_size": None,
            "available_strategies": [
                "column",
                "reverse-column",
                "edges-to-center",
                "row",
                "diagonal",
                "random",
            ],
        }

    def test_put_returns_the_saved_transition_settings(self, client):
        response = client.put("/settings/transitions", json={"strategy": "column", "step_size": 2})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare TransitionSettings,
        # was {"status": "success", "settings": {...}}.
        assert response.json() == {"strategy": "column", "step_interval_ms": None, "step_size": 2}

    def test_put_400s_on_an_unknown_strategy_naming_the_valid_set(self, client):
        response = client.put("/settings/transitions", json={"strategy": "nope"})
        assert response.status_code == 400
        assert response.json() == {
            "detail": (
                "Invalid strategy: nope. Must be one of "
                "['column', 'reverse-column', 'edges-to-center', 'row', 'diagonal', 'random'] "
                "or 'plugin:<id>'"
            )
        }


# ---------------------------------------------------------------------------
# Output target
# ---------------------------------------------------------------------------


class TestOutput:
    def test_get_returns_target_effective_target_and_available_targets(self, client):
        assert client.get("/settings/output").json() == {
            "target": "board",
            "effective_target": "board",
            "available_targets": ["ui", "board", "both"],
        }

    def test_put_returns_the_saved_output_settings(self, client):
        response = client.put("/settings/output", json={"target": "ui"})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare OutputSettings.
        assert response.json() == {"target": "ui"}
        assert client.get("/settings/output").json()["target"] == "ui"

    def test_put_without_target_is_rejected(self, client):
        response = client.put("/settings/output", json={})
        # CHANGED (conventions, typed_body): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "target parameter required"}.
        assert response.status_code == 422

    def test_put_400s_on_an_unknown_target_naming_the_valid_set(self, client):
        response = client.put("/settings/output", json={"target": "nope"})
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid target: nope. Must be one of ['ui', 'board', 'both']"}


# ---------------------------------------------------------------------------
# Active page
# ---------------------------------------------------------------------------


class TestActivePage:
    def test_get_returns_all_four_keys_with_nulls_when_nothing_is_active(self, client):
        assert client.get("/settings/active-page").json() == {
            "page_id": None,
            "resolved_page_id": None,
            "resolved_next_check_seconds": None,
            "board_id": None,
        }

    def test_put_null_clears_the_selection_and_reports_no_send(self, client):
        response = client.put("/settings/active-page", json={"page_id": None})
        assert response.status_code == 200
        # CHANGED (conventions): "status" dropped, and "warnings" is now
        # always present — it used to be omitted whenever the list was empty,
        # so "no warnings" and "this build does not report warnings" were the
        # same payload.
        assert response.json() == {
            "page_id": None,
            "sent_to_board": False,
            "paused": False,
            "board_id": None,
            "error": None,
            "warnings": [],
        }

    def test_put_404s_for_an_unknown_page_naming_it(self, client):
        response = client.put("/settings/active-page", json={"page_id": "nope"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Page not found: nope"}

    def test_put_404s_for_an_unknown_board(self, client):
        response = client.put("/settings/active-page", json={"page_id": None, "board_id": "nope"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Board not found: nope"}


# ---------------------------------------------------------------------------
# Temporary override
# ---------------------------------------------------------------------------


class TestTemporaryOverride:
    def test_get_returns_every_key_nulled_when_no_override_is_active(self, client):
        assert client.get("/settings/temporary-override").json() == {
            "active": False,
            "page_id": None,
            "expires_at": None,
            "remaining_seconds": None,
            "revert_mode": None,
            "revert_page_id": None,
            "template": None,
            "line_metadata": None,
            "device_type": None,
            "notes_wide": None,
            "notes_tall": None,
        }

    def test_post_422s_when_neither_page_id_nor_template_is_supplied(self, client):
        response = client.post("/settings/temporary-override", json={})
        assert response.status_code == 422
        assert response.json() == {"detail": "Either page_id or template is required"}

    def test_post_422s_when_both_page_id_and_template_are_supplied(self, client):
        response = client.post(
            "/settings/temporary-override",
            json={"page_id": "p", "template": ["A"]},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Supply either page_id or template, not both"}

    def test_post_404s_for_an_unknown_page_naming_it(self, client):
        response = client.post("/settings/temporary-override", json={"page_id": "nope"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Page not found: nope"}

    def test_post_inline_template_activates_and_echoes_the_content(self, client):
        response = client.post(
            "/settings/temporary-override",
            json={"template": ["HELLO"], "device_type": "flagship", "duration_minutes": 5},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["active"] is True
        assert body["template"] == ["HELLO"]
        assert body["device_type"] == "flagship"
        assert body["page_id"] is None
        assert body["revert_mode"] == "schedule"
        assert body["expires_at"] is not None
        assert 0 < body["remaining_seconds"] <= 300

    def test_post_422s_on_an_out_of_range_duration(self, client):
        response = client.post(
            "/settings/temporary-override",
            json={"template": ["HI"], "duration_minutes": 9999},
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "duration_minutes must be between 1 and 480"}

    def test_delete_reports_the_revert_mode_of_the_override_it_cancelled(self, client):
        client.post("/settings/temporary-override", json={"template": ["HI"]})
        response = client.delete("/settings/temporary-override")
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): "status": "cleared" dropped —
        # a 200 already says the override was cleared.
        assert response.json() == {"revert_mode": "schedule"}
        assert client.get("/settings/temporary-override").json()["active"] is False

    def test_delete_with_no_active_override_reports_a_null_revert_mode(self, client):
        response = client.delete("/settings/temporary-override")
        assert response.status_code == 200
        assert response.json() == {"revert_mode": None}


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


class TestPolling:
    def test_get_returns_the_three_intervals_with_their_defaults(self, client):
        assert client.get("/settings/polling").json() == {
            "interval_seconds": 15,
            "board_read_interval_local": 30,
            "board_read_interval_cloud": 180,
        }

    def test_put_returns_the_saved_intervals_and_the_restart_hint(self, client):
        response = client.put("/settings/polling", json={"interval_seconds": 60})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the settings are inlined and
        # "status" dropped. requires_restart survives — it is real
        # information about the write, not an envelope.
        assert response.json() == {
            "interval_seconds": 60,
            "board_read_interval_local": 30,
            "board_read_interval_cloud": 180,
            "requires_restart": True,
        }

    def test_put_without_interval_seconds_does_not_require_a_restart(self, client):
        response = client.put("/settings/polling", json={"board_read_interval_local": 45})
        assert response.status_code == 200
        assert response.json()["requires_restart"] is False
        assert response.json()["board_read_interval_local"] == 45

    def test_put_400s_below_the_minimum_polling_interval(self, client):
        response = client.put("/settings/polling", json={"interval_seconds": 1})
        assert response.status_code == 400
        assert response.json() == {"detail": "Polling interval must be at least 10 seconds"}


# ---------------------------------------------------------------------------
# Board settings
# ---------------------------------------------------------------------------


class TestBoardSettings:
    def test_get_returns_board_type_boards_and_devices(self, client):
        body = client.get("/settings/board").json()
        assert body["board_type"] == "black"
        assert body["devices"] == ["flagship"]
        assert len(body["boards"]) == 1
        assert body["boards"][0]["device_type"] == "flagship"
        assert body["boards"][0]["paused"] is False

    def test_put_devices_returns_the_saved_board_settings(self, client):
        response = client.put("/settings/board", json={"devices": ["flagship", "note"]})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare BoardSettings, was
        # {"status": "success", "settings": {...}}.
        assert response.json()["devices"] == ["flagship", "note"]

    def test_put_board_type_returns_the_saved_board_settings(self, client):
        response = client.put("/settings/board", json={"board_type": "white"})
        assert response.status_code == 200
        assert response.json()["board_type"] == "white"

    def test_put_with_no_recognised_key_is_a_400(self, client):
        response = client.put("/settings/board", json={})
        assert response.status_code == 400
        assert response.json() == {"detail": "One of board_type, devices, or boards is required"}

    def test_put_with_a_non_list_devices_value_is_rejected(self, client):
        response = client.put("/settings/board", json={"devices": "flagship"})
        # CHANGED (conventions, typed_body): the request model owns the
        # list-shape check, so FastAPI's 422 replaces the hand-rolled 400
        # {"detail": "devices must be a list"}.
        assert response.status_code == 422

    def test_add_appends_a_board_and_returns_the_whole_board_settings(self, client):
        response = client.post("/settings/board/add", json={"device_type": "note"})
        # CHANGED (conventions, status codes): a create answers 201 with the
        # bare BoardSettings, was 200 + {"status": "success", "settings": ...}.
        assert response.status_code == 201
        boards = response.json()["boards"]
        assert len(boards) == 2
        assert boards[1]["device_type"] == "note"
        assert boards[1]["name"] == "My Board 2"

    def test_add_without_a_device_type_is_rejected(self, client):
        response = client.post("/settings/board/add", json={})
        # CHANGED (conventions, typed_body): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "device_type is required"}.
        assert response.status_code == 422

    def test_delete_removes_the_board_and_returns_the_remaining_settings(self, client):
        added = client.post("/settings/board/add", json={"device_type": "note"}).json()
        board_id = added["boards"][1]["id"]
        response = client.delete(f"/settings/board/{board_id}")
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare BoardSettings.
        assert [b["id"] for b in response.json()["boards"]] == [added["boards"][0]["id"]]

    def test_delete_400s_for_an_unknown_board(self, client):
        # A second board first: with only one board the "last board" guard
        # fires before the id is ever looked up.
        client.post("/settings/board/add", json={"device_type": "note"})
        response = client.delete("/settings/board/nope")
        assert response.status_code == 400
        assert response.json() == {"detail": "Board with ID 'nope' not found"}

    def test_delete_400s_on_the_last_remaining_board(self, client):
        response = client.delete(f"/settings/board/{_primary_board_id(client)}")
        assert response.status_code == 400
        assert response.json() == {"detail": "Cannot remove the last board. At least one board is required."}

    def test_delete_409s_when_a_fiestapanel_still_references_the_board(self, client):
        panel = client.post("/panels", json={"name": "Kitchen"})
        assert panel.status_code == 201, panel.text
        # Bare Panel since the panels slice (#1913) unwrapped its envelope.
        board_id = panel.json()["board_id"]
        response = client.delete(f"/settings/board/{board_id}")
        assert response.status_code == 409
        assert response.json() == {
            "detail": ("Board is in use by FiestaPanel 'Kitchen'. Delete the panel in Settings → FiestaPanel instead.")
        }


# ---------------------------------------------------------------------------
# Board pause
# ---------------------------------------------------------------------------


class TestBoardPause:
    def test_pause_returns_the_new_state_and_the_board_settings(self, client):
        board_id = _primary_board_id(client)
        response = client.post(f"/settings/board/{board_id}/pause", json={"paused": True})
        assert response.status_code == 200
        body = response.json()
        # CHANGED (conventions, bare bodies): "status" dropped, and the
        # generic "settings" key renamed to "board_settings" so the payload
        # names what it carries.
        assert body["board_id"] == board_id
        assert body["paused"] is True
        assert body["board_settings"]["boards"][0]["paused"] is True

    def test_pause_404s_for_an_unknown_board(self, client):
        response = client.post("/settings/board/nope/pause", json={"paused": True})
        assert response.status_code == 404
        assert response.json() == {"detail": "Board not found: nope"}

    def test_pause_without_the_paused_field_is_a_422(self, client):
        response = client.post(f"/settings/board/{_primary_board_id(client)}/pause", json={})
        # CHANGED (conventions, typed_body): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "paused is required"}.
        assert response.status_code == 422

    def test_pause_refuses_a_non_boolean_paused_value(self, client):
        board_id = _primary_board_id(client)
        response = client.post(f"/settings/board/{board_id}/pause", json={"paused": "yes"})
        # CHANGED (conventions, StrictBool): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "paused must be a boolean"}. The second
        # assertion is the point of the change: a plain `bool` field would
        # have coerced "yes" to True and paused the board at 200.
        assert response.status_code == 422
        assert client.get("/settings/board").json()["boards"][0]["paused"] is False

    @pytest.mark.parametrize("truthy", ["on", 1, "1", "true"])
    def test_pause_never_coerces_a_truthy_non_boolean(self, client, truthy):
        board_id = _primary_board_id(client)
        response = client.post(f"/settings/board/{board_id}/pause", json={"paused": truthy})
        assert response.status_code == 422, f"{truthy!r} was coerced to a boolean"
        assert client.get("/settings/board").json()["boards"][0]["paused"] is False


# ---------------------------------------------------------------------------
# Board detect-size / identify
# ---------------------------------------------------------------------------


class TestBoardDetectSize:
    def test_404s_for_an_unknown_board(self, client):
        response = client.post("/settings/board/nope/detect-size")
        assert response.status_code == 404
        assert response.json() == {"detail": "Board nope not found"}

    def test_400s_when_the_board_has_no_credentials(self, client):
        board_id = _primary_board_id(client)
        response = client.post(f"/settings/board/{board_id}/detect-size")
        assert response.status_code == 400
        assert response.json() == {"detail": f"Board {board_id} is not configured (missing credentials)"}

    def test_422s_when_the_board_returns_no_layout(self, client):
        board_id = _primary_board_id(client)
        board_client = Mock()
        board_client.read_current_message.return_value = None
        with patch("src.api_server.board_client_from_board_dict", return_value=board_client):
            response = client.post(f"/settings/board/{board_id}/detect-size")
        assert response.status_code == 422
        assert response.json() == {"detail": f"Board {board_id} returned no layout — board may be blank or unreachable"}

    def test_classifies_a_flagship_grid(self, client):
        board_id = _primary_board_id(client)
        board_client = Mock()
        board_client.read_current_message.return_value = [[0] * 22 for _ in range(6)]
        with patch("src.api_server.board_client_from_board_dict", return_value=board_client):
            response = client.post(f"/settings/board/{board_id}/detect-size")
        assert response.status_code == 200
        body = response.json()
        assert body["device_type"] == "flagship"
        assert body["rows"] == 6
        assert body["cols"] == 22


class TestBoardIdentify:
    def test_404s_for_an_unknown_board(self, client):
        response = client.post("/settings/board/nope/identify", json={"target": "tile"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Board nope not found"}

    def test_400s_when_the_board_is_not_a_local_note_array(self, client):
        board_id = _primary_board_id(client)
        response = client.post(f"/settings/board/{board_id}/identify", json={"target": "tile"})
        assert response.status_code == 400
        assert response.json() == {"detail": "Identify is only available for note arrays in local API mode"}


# ---------------------------------------------------------------------------
# Display / location
# ---------------------------------------------------------------------------


class TestDisplay:
    def test_get_returns_the_four_display_preferences(self, client):
        assert client.get("/settings/display").json() == {
            "reduce_motion": False,
            "board_animations": "on",
            "site_animations": "on",
            "board_flap_speed": "standard",
        }

    def test_put_returns_the_saved_display_settings(self, client):
        response = client.put("/settings/display", json={"reduce_motion": True})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare DisplaySettings.
        assert response.json() == {
            "reduce_motion": True,
            "board_animations": "on",
            "site_animations": "on",
            "board_flap_speed": "standard",
        }


class TestLocation:
    def test_get_returns_null_coordinates_before_configuration(self, client):
        assert client.get("/settings/location").json() == {"latitude": None, "longitude": None}

    def test_put_returns_the_saved_coordinates(self, client):
        response = client.put("/settings/location", json={"latitude": 40.7128, "longitude": -74.006})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare LocationSettings.
        assert response.json() == {"latitude": 40.7128, "longitude": -74.006}

    def test_sun_times_report_not_configured_before_coordinates_are_set(self, client):
        assert client.get("/settings/location/sun-times").json() == {
            "sunrise": None,
            "sunset": None,
            "location_configured": False,
        }

    def test_sun_times_400_on_a_malformed_date(self, client):
        # The date is only parsed once a location exists; without one the
        # handler short-circuits to location_configured=False at 200.
        client.put("/settings/location", json={"latitude": 40.7128, "longitude": -74.006})
        response = client.get("/settings/location/sun-times?date=bogus")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid date format. Use YYYY-MM-DD."}

    def test_sun_times_week_returns_seven_days_for_a_configured_location(self, client):
        client.put("/settings/location", json={"latitude": 40.7128, "longitude": -74.006})
        body = client.get("/settings/location/sun-times-week?week_start=2026-01-05").json()
        assert body["location_configured"] is True
        assert sorted(body["dates"]) == [
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-10",
            "2026-01-11",
        ]
        assert set(body["dates"]["2026-01-05"]) == {"sunrise", "sunset"}

    def test_sun_times_week_reports_not_configured_with_an_empty_map(self, client):
        assert client.get("/settings/location/sun-times-week?week_start=2026-01-05").json() == {
            "location_configured": False,
            "dates": {},
        }

    def test_sun_times_week_400_on_a_malformed_start(self, client):
        client.put("/settings/location", json={"latitude": 40.7128, "longitude": -74.006})
        response = client.get("/settings/location/sun-times-week?week_start=bogus")
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid week_start format. Use YYYY-MM-DD."}


# ---------------------------------------------------------------------------
# Beta
# ---------------------------------------------------------------------------


class TestBeta:
    def test_get_reports_the_settings_and_the_cert_status(self, client):
        with (
            patch("src.system.update_service._updater_token", return_value=""),
            patch("src.system.update_service._updater_probe", return_value=False),
        ):
            body = client.get("/settings/beta").json()
        assert body["settings"]["https_enabled"] is False
        assert body["https"]["cert_present"] is False
        assert body["https"]["updater_available"] is False

    def test_put_returns_the_settings_the_status_and_the_restart_hint(self, client):
        with (
            patch("src.system.update_service._updater_token", return_value=""),
            patch("src.system.update_service._updater_probe", return_value=False),
        ):
            response = client.put("/settings/beta", json={"transition_plugins_enabled": True})
        assert response.status_code == 200
        body = response.json()
        # CHANGED (conventions, bare bodies): "status" dropped. There is no
        # "cert_error" key any more either — a certificate failure is now a
        # 500, so a 200 body never has to carry one.
        assert body["settings"]["transition_plugins_enabled"] is True
        assert body["restart_required"] is False
        assert "cert_error" not in body

    def test_put_enabling_https_generates_a_cert_and_asks_for_a_restart(self, client):
        with (
            patch("src.system.https_certs.generate_cert", return_value=("c", "k")) as generate,
            patch("src.system.update_service._updater_token", return_value=""),
            patch("src.system.update_service._updater_probe", return_value=False),
        ):
            response = client.put("/settings/beta", json={"https_enabled": True})
        assert response.status_code == 200
        assert generate.call_count == 1
        assert response.json()["restart_required"] is True

    def test_put_500s_when_certificate_generation_fails(self, client):
        with (
            patch("src.system.https_certs.generate_cert", side_effect=OSError("boom")),
            patch("src.system.update_service._updater_token", return_value=""),
            patch("src.system.update_service._updater_probe", return_value=False),
        ):
            response = client.put("/settings/beta", json={"https_enabled": True})
        # CHANGED (conventions, no_200_on_failure): was 200 with
        # {"status": "warning", "cert_error": "..."} — the user asked for
        # HTTPS, did not get it, and the API answered success. The preference
        # is still persisted before the raise (asserted below), so the next
        # container start honours the choice.
        assert response.status_code == 500
        assert response.json() == {"detail": "Certificate generation failed — check the server logs for details."}
        with (
            patch("src.system.update_service._updater_token", return_value=""),
            patch("src.system.update_service._updater_probe", return_value=False),
        ):
            assert client.get("/settings/beta").json()["settings"]["https_enabled"] is True


# ---------------------------------------------------------------------------
# Plugin settings
# ---------------------------------------------------------------------------


class TestPluginSettings:
    def test_get_returns_the_plugin_settings(self, client):
        # CHANGED (conventions, bare bodies): the bare PluginSettings, was
        # {"settings": {...}}.
        assert client.get("/settings/plugins").json() == {"auto_update": True}

    def test_put_returns_the_saved_plugin_settings(self, client):
        response = client.put("/settings/plugins", json={"auto_update": False})
        assert response.status_code == 200
        # CHANGED (conventions, bare bodies): the bare PluginSettings.
        assert response.json() == {"auto_update": False}
        assert client.get("/settings/plugins").json() == {"auto_update": False}

    def test_put_refuses_a_non_boolean_auto_update(self, client):
        response = client.put("/settings/plugins", json={"auto_update": "yes"})
        # CHANGED (conventions, StrictBool): was a 200 that reached
        # bool("yes") -> True and silently enabled background plugin updates.
        assert response.status_code == 422
        assert client.get("/settings/plugins").json() == {"auto_update": True}


# ---------------------------------------------------------------------------
# Silence schedule
# ---------------------------------------------------------------------------


class TestSilenceSchedule:
    BASE = {"enabled": True, "start_time": "04:00+00:00", "end_time": "05:00+00:00"}

    def test_put_persists_the_install_wide_schedule_and_returns_it(self, client):
        response = client.put("/settings/silence-schedule", json=self.BASE)
        assert response.status_code == 200
        body = response.json()
        # CHANGED (conventions, bare bodies): "status" dropped; the resolved
        # config and the layer it was written to are the payload.
        assert body["board_id"] is None
        assert body["config"]["enabled"] is True
        assert body["config"]["start_time"] == "04:00+00:00"
        assert body["config"]["end_time"] == "05:00+00:00"
        assert body["config"]["mode"] == "freeze"
        assert body["config"]["indicator_text"] == "SNOOZING"
        assert body["config"]["indicator_position"] == "center"
        assert body["config"]["page_id"] is None

    def test_put_400s_when_mode_is_page_without_a_page_id(self, client):
        response = client.put("/settings/silence-schedule", json={**self.BASE, "mode": "page"})
        assert response.status_code == 400
        assert response.json() == {"detail": "page_id is required when mode is 'page'"}

    def test_put_404s_for_an_unknown_board(self, client):
        response = client.put("/settings/silence-schedule", json={**self.BASE, "board_id": "nope"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Board not found: nope"}

    def test_put_normalises_the_indicator_text_to_uppercase(self, client):
        body = client.put(
            "/settings/silence-schedule",
            json={**self.BASE, "mode": "indicator", "indicator_text": "  back soon  "},
        ).json()
        assert body["config"]["indicator_text"] == "BACK SOON"
        assert body["config"]["mode"] == "indicator"

    def test_put_falls_back_to_center_for_an_unknown_indicator_position(self, client):
        body = client.put(
            "/settings/silence-schedule",
            json={**self.BASE, "indicator_position": "sideways"},
        ).json()
        assert body["config"]["indicator_position"] == "center"


# ---------------------------------------------------------------------------
# HDMI kiosk
# ---------------------------------------------------------------------------


class TestHdmiKiosk:
    def test_get_reports_unsupported_off_a_fiestapi_install(self, client):
        with patch("src.system.update_service._fiestaboard_profile", return_value="docker"):
            body = client.get("/settings/hdmi-kiosk").json()
        # CHANGED (conventions): "enabled" is now always present, null when
        # the platform cannot report one, rather than absent in this branch.
        assert body == {"supported": False, "status": "unsupported", "enabled": None}

    def test_get_passes_through_the_sidecar_status(self, client):
        sidecar = Mock(status_code=200)
        sidecar.json.return_value = {"status": "enabled", "enabled": True}
        with (
            patch("src.system.update_service._fiestaboard_profile", return_value="pi"),
            patch("src.system.update_service._updater_probe", return_value=True),
            patch("src.settings.routes.requests.get", return_value=sidecar),
        ):
            body = client.get("/settings/hdmi-kiosk").json()
        assert body == {"supported": True, "status": "enabled", "enabled": True}

    def test_post_400s_off_a_fiestapi_install(self, client):
        with patch("src.system.update_service._fiestaboard_profile", return_value="docker"):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 400
        assert response.json() == {
            "detail": "HDMI kiosk controls are only available on FiestaPi installs with the updater sidecar"
        }

    def test_post_without_enabled_is_rejected(self, client):
        response = client.post("/settings/hdmi-kiosk", json={})
        # CHANGED (conventions, typed_body): FastAPI's 422 replaces the
        # hand-rolled 400 {"detail": "enabled (boolean) is required"}.
        assert response.status_code == 422

    def test_post_refuses_a_non_boolean_enabled_value(self, client):
        response = client.post("/settings/hdmi-kiosk", json={"enabled": "yes"})
        # CHANGED (conventions, StrictBool): "yes" must not become True and
        # install a kiosk. 422 replaces the hand-rolled 400.
        assert response.status_code == 422

    def test_post_409s_when_the_sidecar_predates_the_hdmi_verbs(self, client):
        with (
            patch("src.system.update_service._fiestaboard_profile", return_value="pi"),
            patch("src.system.update_service._updater_probe", return_value=True),
            patch("src.system.update_service._updater_token", return_value="tok"),
            patch("src.settings.routes.requests.post", return_value=Mock(status_code=404)),
        ):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 409
        assert response.json() == {
            "detail": (
                "The updater sidecar on this Pi is too old for HDMI controls — "
                "reboot the Pi to update it, then try again"
            )
        }

    def test_post_returns_the_queued_action_when_the_sidecar_accepts(self, client):
        accepted = Mock(status_code=202)
        accepted.json.side_effect = ValueError("no body")
        with (
            patch("src.system.update_service._fiestaboard_profile", return_value="pi"),
            patch("src.system.update_service._updater_probe", return_value=True),
            patch("src.system.update_service._updater_token", return_value="tok"),
            patch("src.settings.routes.requests.post", return_value=accepted),
        ):
            response = client.post("/settings/hdmi-kiosk", json={"enabled": True})
        assert response.status_code == 200
        assert response.json() == {"status": "queued", "action": "hdmi_enable"}


# ---------------------------------------------------------------------------
# GET /settings/all — the aggregate the settings page loads
# ---------------------------------------------------------------------------


class TestAllSettings:
    def test_aggregates_every_block_the_settings_page_reads(self, client):
        body = client.get("/settings/all").json()
        assert set(body) == {
            "general",
            "silence_schedule",
            "polling",
            "transitions",
            "output",
            "board",
            "mqtt",
            "display",
            "location",
            "beta",
            "plugins",
            "status",
        }
        assert body["polling"]["interval_seconds"] == 15
        assert body["output"]["target"] == "board"
        assert body["transitions"]["available_strategies"] == [
            "column",
            "reverse-column",
            "edges-to-center",
            "row",
            "diagonal",
            "random",
        ]
        assert body["mqtt"]["password"] == ""
        assert body["display"]["board_flap_speed"] == "standard"
        assert body["location"] == {"latitude": None, "longitude": None}
        assert body["plugins"] == {"auto_update": True}
        assert body["status"] == {"running": False}
        assert body["silence_schedule"]["config"]["mode"] == "freeze"

    def test_reflects_a_write_made_through_a_sibling_endpoint(self, client):
        client.put("/settings/output", json={"target": "both"})
        assert client.get("/settings/all").json()["output"]["target"] == "both"
