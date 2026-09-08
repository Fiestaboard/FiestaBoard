"""Value-level contract goldens for the /config API (Phase 2 §2, Task 8 slice).

These are deliberately *values*, not shapes. ``tests/golden/responses/`` records
key sets and type names, so it cannot see a credential that stopped being
masked, a ``host`` echoed back from the wrong board, or a first-run verdict that
flipped — exactly the class of regression the Phase 1 masking bug proved shape
goldens miss.

Every assertion below is a promise this domain makes to the web client (the
setup wizard, Settings → Boards, Settings → General) and to the deprecated
``/config/board`` shim's outside callers.

Recorded against the **unconverted** trunk first: every assertion below passed
before the conventions pass touched a line of ``/config``. That is what makes
it a contract golden rather than a description of whatever the new code happens
to do.

What the conventions pass deliberately changed, and nothing else:

* ``PUT /config/general`` answers 200 with the **bare** general config (was
  ``{"status": "success", "general": {...}}``) — conventions doc, "Bare
  bodies". No web consumer read that body; both call sites invalidate a query
  instead.
* ``PUT /config/general`` now rejects a non-numeric ``refresh_interval_seconds``
  with 422 instead of storing the string. The endpoint took a bare ``dict``
  body and handed it straight to the store, so ``"soon"`` persisted and then
  broke every consumer that did arithmetic on it.
* ``PUT /config/board`` and ``PUT /config/general`` reject a body whose field
  types are wrong (422) rather than persisting them, now that both take
  Pydantic models instead of ``dict``.

Deliberately NOT changed:

* ``GET`` / ``PUT`` / ``DELETE /config/board`` keep their legacy wire shapes.
  They are a *deprecation shim* (issue #1760) whose entire purpose is wire
  stability for callers that have not migrated to ``/settings/board``;
  unwrapping their envelopes would break the thing the shim exists to protect.
* ``GET /config/validate`` keeps ``{"valid": ..., "is_first_run": ...}``. It is
  a verdict endpoint, not a failure report: ``valid: false`` is the answer the
  wizard asked for, at 200.
* ``POST /config/board/test`` and ``POST /config/board/enable-local-api`` keep
  the declared ``success``-at-200 probe contract Task 10a landed (#1887).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

LOCAL_KEY = "test_local_key_contract"
LOCAL_HOST = "192.0.2.50"


@pytest.fixture(autouse=True)
def _no_credential_env(monkeypatch):
    """Pin these contracts to disk, not to the runner's environment.

    CI exports ``BOARD_READ_WRITE_KEY=test_key`` for the platform job, and the
    #1761 read-time overlay folds it into the board config. That makes a
    "fresh install" read as configured — `cloud_key` comes back masked as
    ``***`` instead of empty and `is_first_run` is False — so these tests pass
    locally and fail in CI. Same fixture as
    ``tests/test_config_manager.py::reset_singleton``.
    """
    for name in (
        "BOARD_READ_WRITE_KEY",
        "FB_READ_WRITE_KEY",
        "BOARD_LOCAL_API_KEY",
        "FB_LOCAL_API_KEY",
        "BOARD_HOST",
        "FB_HOST",
        "WEATHER_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def data_dir(_isolated_data_dir):
    return _isolated_data_dir


@pytest.fixture
def client(data_dir):
    """A TestClient whose services all resolve into this test's temp data dir."""
    from src.api_server import app

    return TestClient(app)


def _settings_on_disk(data_dir) -> dict:
    """The unmasked settings store. ``GET /settings/board`` masks credentials,
    so only the file can prove a key survived a write."""
    return json.loads((data_dir / "settings.json").read_text())


def _stored_board(data_dir) -> dict:
    return _settings_on_disk(data_dir)["board"]["boards"][0]


def _configure_board(client: TestClient, **fields) -> dict:
    body = {"api_mode": "local", "host": LOCAL_HOST, "local_api_key": LOCAL_KEY}
    body.update(fields)
    response = client.put("/config/board", json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# GET /config — the summary the dashboard header reads
# ---------------------------------------------------------------------------


def test_config_summary_reports_the_primary_board_connection_by_value(client):
    _configure_board(client)
    body = client.get("/config").json()

    assert body["board_api_mode"] == "local"
    assert body["board_host"] == LOCAL_HOST
    assert body["board_key_set"] is True
    # The summary is explicitly "without sensitive keys" — the credential
    # itself must never appear, masked or otherwise.
    assert LOCAL_KEY not in json.dumps(body)


def test_config_summary_reports_no_key_set_on_a_fresh_install(client):
    body = client.get("/config").json()

    assert body["board_key_set"] is False
    assert body["board_host"] == ""


def test_config_summary_reports_the_configured_timezone(client):
    client.put("/config/general", json={"timezone": "America/New_York"})
    assert client.get("/config").json()["timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# GET /config/full — the masking round-trip
# ---------------------------------------------------------------------------


def test_full_config_masks_a_stored_credential_without_destroying_it(client, data_dir):
    """The proof case: masking is a *view*, never a write.

    A shape golden sees ``str`` on both sides of this and notices nothing.
    """
    from src.config_manager import get_config_manager

    get_config_manager().set_board({"local_api_key": "sk-do-not-leak", "host": LOCAL_HOST})

    body = client.get("/config/full").json()
    assert body["board"]["local_api_key"] == "***"
    assert body["board"]["host"] == LOCAL_HOST

    on_disk = json.loads((data_dir / "config.json").read_text())
    assert on_disk["board"]["local_api_key"] == "sk-do-not-leak"


def test_full_config_leaves_an_unset_credential_empty_rather_than_masked(client):
    """``***`` must mean "a value is set" — masking an empty string would make
    a blank credential indistinguishable from a configured one."""
    body = client.get("/config/full").json()
    assert body["board"]["local_api_key"] == ""


# ---------------------------------------------------------------------------
# GET/PUT/DELETE /config/board — the deprecated shim over the settings store
# ---------------------------------------------------------------------------


def test_get_board_config_masks_credentials_and_echoes_the_host(client):
    _configure_board(client)
    body = client.get("/config/board").json()

    assert body["api_modes"] == ["local", "cloud"]
    assert body["config"]["local_api_key"] == "***"
    assert body["config"]["cloud_key"] == ""
    assert body["config"]["note_array_token"] == ""
    assert body["config"]["host"] == LOCAL_HOST
    assert body["config"]["api_mode"] == "local"


def test_get_board_config_reports_the_live_transition_settings(client):
    """The legacy board view splices in the transition settings the runtime
    actually uses — not the vestigial config.json copy."""
    client.put(
        "/settings/transitions",
        json={"strategy": "column", "step_interval_ms": 123, "step_size": 2},
    )
    body = client.get("/config/board").json()

    assert body["config"]["transition_strategy"] == "column"
    assert body["config"]["transition_interval_ms"] == 123
    assert body["config"]["transition_step_size"] == 2


def test_update_board_config_persists_to_the_settings_board_store(client, data_dir):
    _configure_board(client)

    assert _stored_board(data_dir)["host"] == LOCAL_HOST
    assert _stored_board(data_dir)["local_api_key"] == LOCAL_KEY


def test_update_board_config_only_writes_the_fields_the_caller_sent(client, data_dir):
    """Partial update semantics, pinned by value.

    The handler copies exactly the keys present in the body. A conversion that
    materialised absent fields as ``None`` would blank the stored key on any
    host-only save — the wizard does exactly that.
    """
    _configure_board(client)
    client.put("/config/board", json={"host": "192.0.2.77"})

    assert _stored_board(data_dir)["host"] == "192.0.2.77"
    assert _stored_board(data_dir)["local_api_key"] == LOCAL_KEY


def test_update_board_config_treats_a_masked_credential_as_no_change(client, data_dir):
    _configure_board(client)
    client.put("/config/board", json={"local_api_key": "***"})

    assert _stored_board(data_dir)["local_api_key"] == LOCAL_KEY


def test_update_board_config_ignores_fields_outside_the_legacy_connection_set(client, data_dir):
    """``name`` is not a legacy connection field, so the shim must drop it —
    otherwise the deprecated endpoint becomes a back door into board metadata.
    """
    _configure_board(client)
    before = _stored_board(data_dir)["name"]

    client.put("/config/board", json={"host": LOCAL_HOST, "name": "Renamed By Shim"})

    assert _stored_board(data_dir)["name"] == before


def test_board_config_shim_advertises_its_successor(client):
    for response in (
        client.get("/config/board"),
        client.put("/config/board", json={"host": LOCAL_HOST}),
    ):
        assert response.headers["Deprecation"] == "true"
        assert response.headers["Link"] == '</settings/board>; rel="successor-version"'


def test_reset_board_config_clears_the_credentials_it_reports_clearing(client, data_dir):
    _configure_board(client)
    response = client.delete("/config/board")

    assert response.status_code == 200
    assert response.json()["status"] == "reset"

    board = client.get("/config/board").json()["config"]
    assert board["host"] == ""
    assert board["local_api_key"] == ""
    assert _stored_board(data_dir)["local_api_key"] == ""


# ---------------------------------------------------------------------------
# GET /config/validate — the wizard gate
# ---------------------------------------------------------------------------


def test_validate_names_every_missing_local_field_on_a_fresh_install(client):
    body = client.get("/config/validate").json()

    assert body["is_first_run"] is True
    assert body["missing_fields"] == ["board.local_api_key", "board.host"]


def test_validate_names_the_missing_cloud_key_in_cloud_mode(client):
    from src.config_manager import get_config_manager

    get_config_manager().set_board({"api_mode": "cloud", "cloud_key": ""})
    body = client.get("/config/validate").json()

    assert body["is_first_run"] is True
    assert body["missing_fields"] == ["board.cloud_key"]


def test_validate_clears_first_run_once_a_board_is_configured(client):
    _configure_board(client)
    body = client.get("/config/validate").json()

    assert body["is_first_run"] is False
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["missing_fields"] == []


def test_validate_reports_a_partly_configured_board_as_misconfigured_not_first_run(client):
    """#1813: a board with *some* connection detail must never bounce an
    existing install back into the setup wizard."""
    client.put("/config/board", json={"host": LOCAL_HOST})
    assert client.get("/config/validate").json()["is_first_run"] is False


# ---------------------------------------------------------------------------
# POST /config/board/scan
# ---------------------------------------------------------------------------


def test_scan_returns_the_discovered_boards_verbatim(client):
    discovered = [{"ip": "192.0.2.10", "port": 7000, "hostname": "vestaboard.local", "source": "mdns"}]
    with patch("src.system.mdns.scan_for_boards", return_value=discovered) as scan:
        body = client.post("/config/board/scan", json={"timeout": 2.5}).json()

    assert body["boards"] == discovered
    assert scan.call_args.kwargs["timeout"] == 2.5


def test_scan_clamps_the_timeout_into_the_supported_window(client):
    with patch("src.system.mdns.scan_for_boards", return_value=[]) as scan:
        client.post("/config/board/scan", json={"timeout": 900})
        assert scan.call_args.kwargs["timeout"] == 15.0

        client.post("/config/board/scan", json={"timeout": 0.1})
        assert scan.call_args.kwargs["timeout"] == 1.0


def test_scan_defaults_to_a_four_second_sweep_when_no_body_is_sent(client):
    with patch("src.system.mdns.scan_for_boards", return_value=[]) as scan:
        assert client.post("/config/board/scan").status_code == 200
    assert scan.call_args.kwargs["timeout"] == 4.0


# ---------------------------------------------------------------------------
# GET/PUT /config/general
# ---------------------------------------------------------------------------


GENERAL_FIELDS = {
    "timezone": "Europe/Berlin",
    "refresh_interval_seconds": 42,
    "output_target": "ui",
    "instance_name": "Contract Fixture",
    "time_format": "24h",
    "date_format": "YYYY-MM-DD",
    "welcome_message": "HELLO CONTRACT",
}


def test_general_config_round_trips_every_documented_field(client):
    client.put("/config/general", json=GENERAL_FIELDS)
    body = client.get("/config/general").json()

    for key, value in GENERAL_FIELDS.items():
        assert body[key] == value, key


def test_update_general_config_leaves_unsent_fields_alone(client):
    client.put("/config/general", json=GENERAL_FIELDS)
    client.put("/config/general", json={"timezone": "UTC"})
    body = client.get("/config/general").json()

    assert body["timezone"] == "UTC"
    assert body["instance_name"] == "Contract Fixture"
    assert body["welcome_message"] == "HELLO CONTRACT"


def test_update_general_config_rebuilds_the_time_service_on_a_timezone_change(client):
    """#1273: schedule rotations resolve "now" through a cached TimeService
    that reads the timezone once at construction."""
    from src.time_service import get_time_service

    client.put("/config/general", json={"timezone": "UTC"})
    assert get_time_service().default_timezone == "UTC"

    client.put("/config/general", json={"timezone": "Europe/Berlin"})
    assert get_time_service().default_timezone == "Europe/Berlin"


def test_update_general_config_does_not_rebuild_the_clock_for_an_unrelated_field(client):
    from src.time_service import get_time_service

    client.put("/config/general", json={"timezone": "UTC"})
    before = get_time_service()

    client.put("/config/general", json={"instance_name": "No Clock Churn"})
    assert get_time_service() is before


def test_update_general_config_answers_with_the_saved_config_not_an_envelope(client):
    """Deliberate change: was ``{"status": "success", "general": {...}}``."""
    response = client.put("/config/general", json={"timezone": "Europe/Berlin"})

    assert response.status_code == 200
    body = response.json()
    assert "status" not in body
    assert body["timezone"] == "Europe/Berlin"
    assert body["instance_name"] == client.get("/config/general").json()["instance_name"]


def test_update_general_config_rejects_a_non_numeric_refresh_interval(client):
    """Deliberate change: the bare-dict body used to persist ``"soon"``."""
    response = client.put("/config/general", json={"refresh_interval_seconds": "soon"})

    assert response.status_code == 422
    assert client.get("/config/general").json()["refresh_interval_seconds"] != "soon"


def test_update_general_config_still_accepts_a_numeric_string_interval(client):
    """Tightening the type must not break a caller sending ``"120"``."""
    assert client.put("/config/general", json={"refresh_interval_seconds": "120"}).status_code == 200
    assert client.get("/config/general").json()["refresh_interval_seconds"] == 120


def test_update_board_config_rejects_a_non_string_host(client):
    """Deliberate change: the bare-dict body used to persist ``{"host": 1}``."""
    response = client.put("/config/board", json={"host": 1})

    assert response.status_code == 422


def test_update_general_config_reports_a_failed_write_as_a_server_error(client):
    from src.config_manager import get_config_manager

    with patch.object(type(get_config_manager()), "set_general", return_value=False):
        response = client.put("/config/general", json={"timezone": "UTC"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to update general configuration"


# ---------------------------------------------------------------------------
# The two probe endpoints — declared verdict at 200, preconditions at 4xx
# ---------------------------------------------------------------------------


def test_board_test_rejects_a_missing_credential_as_a_precondition_failure(client):
    response = client.post("/config/board/test", json={"api_mode": "local", "host": LOCAL_HOST})

    assert response.status_code == 400
    assert response.json()["detail"] == "Local API key is required"


def test_board_test_refuses_a_host_it_will_not_probe(client):
    response = client.post(
        "/config/board/test",
        json={"api_mode": "local", "local_api_key": "k", "host": "http://evil.example.com/x"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "host must be a bare IP address or hostname"


def test_board_test_reports_an_upstream_rejection_as_a_verdict_at_200(client):
    """The probe's declared job is to report what the board said."""
    import requests

    with patch.object(requests, "get") as mock_get:
        mock_get.return_value.status_code = 401
        response = client.post(
            "/config/board/test",
            json={"api_mode": "local", "local_api_key": "wrong", "host": "192.0.2.10"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "HTTP 401"
    assert body["troubleshooting"]


def test_board_test_reports_a_working_board_with_its_mode(client):
    import requests

    with patch.object(requests, "get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"currentMessage": None}
        response = client.post(
            "/config/board/test",
            json={"api_mode": "local", "local_api_key": "right", "host": "192.0.2.10"},
        )

    body = response.json()
    assert body["success"] is True
    assert body["api_mode"] == "local"
    # response_model_exclude_none: a successful probe carries no error fields.
    assert "error" not in body
    assert "troubleshooting" not in body


def test_enable_local_api_rejects_a_public_host_before_contacting_it(client):
    response = client.post(
        "/config/board/enable-local-api",
        json={"host": "93.184.216.34", "enablement_token": "t"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "host must resolve to a local/private IPv4 address"


def test_enable_local_api_reports_a_rejected_token_as_a_verdict_at_200(client):
    import requests

    with patch.object(requests, "post") as mock_post:
        mock_post.return_value.status_code = 401
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "bad"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "HTTP 401: Unauthorized"


def test_enable_local_api_returns_the_key_the_board_issued(client):
    import requests

    with patch.object(requests, "post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"apiKey": "issued-key-123"}
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "good"},
        )

    body = response.json()
    assert body["success"] is True
    assert body["api_key"] == "issued-key-123"


# ---------------------------------------------------------------------------
# The verdict branches the two probes answer at 200, and the preconditions
# they answer at 4xx.
#
# Pinned by value ahead of the router→service move (#1934) so that "the same
# tests still pass" is evidence the move changed nothing. Every message below
# was recorded from the unmodified tree; none of these branches had a value
# pin before.
# ---------------------------------------------------------------------------


def test_enable_local_api_rejects_an_empty_host_before_contacting_anything(client):
    response = client.post("/config/board/enable-local-api", json={"host": "", "enablement_token": "t"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Board IP address is required"


def test_enable_local_api_rejects_an_empty_token_before_contacting_anything(client):
    response = client.post("/config/board/enable-local-api", json={"host": "192.168.1.10", "enablement_token": ""})

    assert response.status_code == 400
    assert response.json()["detail"] == "Enablement token is required"


def test_enable_local_api_reports_an_unreachable_board_as_a_verdict_at_200(client):
    import requests

    with patch.object(requests, "post", side_effect=requests.exceptions.ConnectionError("refused")):
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "t"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Connection error"
    assert body["message"] == (
        "Could not connect to board. Please check the IP address and ensure the board is on the same network."
    )


def test_enable_local_api_reports_a_timeout_as_a_verdict_at_200(client):
    import requests

    with patch.object(requests, "post", side_effect=requests.exceptions.Timeout("slow")):
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "t"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "Timeout"
    assert body["message"] == "Connection timed out. Please check the IP address and try again."


def test_enable_local_api_reports_a_200_without_an_api_key_as_a_failed_exchange(client):
    import requests

    with patch.object(requests, "post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "t"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Received response but no API key was provided"
    assert body["error"] == "Board response did not include an apiKey"


def test_enable_local_api_quotes_an_unexpected_board_status_in_its_verdict(client):
    import requests

    with patch.object(requests, "post") as mock_post:
        mock_post.return_value.status_code = 500
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "t"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["message"] == "Board returned an error (HTTP 500)"
    assert body["error"] == "HTTP 500"


def test_enable_local_api_reports_an_unanticipated_failure_as_a_generic_500(client):
    """The detail stays generic — the exception belongs in the log (#1887)."""
    import requests

    with patch.object(requests, "post", side_effect=RuntimeError("secret internal detail")):
        response = client.post(
            "/config/board/enable-local-api",
            json={"host": "192.168.1.10", "enablement_token": "t"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enable local API."


def test_validate_drops_the_legacy_board_errors_once_a_board_instance_is_configured(client):
    """The multi-board override clears *board* errors only.

    A non-board validation error must survive, and ``valid`` is recomputed
    from what is left — the branch at the end of the first-run determination.
    """
    from src.config_manager import get_config_manager

    _configure_board(client)
    with patch.object(
        get_config_manager(),
        "validate",
        return_value=(False, ["Board host is not set", "Timezone is not a known IANA name"]),
    ):
        body = client.get("/config/validate").json()

    assert body["is_first_run"] is False
    assert body["errors"] == ["Timezone is not a known IANA name"]
    assert body["valid"] is False
