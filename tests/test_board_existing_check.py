# ruff: noqa: F811 - pytest fixtures are imported from their home modules
"""H19: the setup wizard asks whether a display is already set up.

Before adding a display, the wizard checks the address (or cloud key) it is
about to save against the hub's own boards: ``POST /config/board/existing``,
read-only, answers which boards already use it, and ``POST
/config/board/test`` carries the same answer as ``existing_boards``. Hosts
compare as written (case, scheme, a trailing dot or slash aside; no DNS);
a port only distinguishes when both sides name one; secrets match but never
come back.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from tests.test_v1_contract import client  # noqa: F401 - fixture

KITCHEN_KEY = "test_local_key_kitchen"
OFFICE_CLOUD = "test_cloud_key_office"
ARRAY_TOKEN = "test_note_array_token"


@pytest.fixture
def boards(client):
    from src.settings.service import get_settings_service

    stored = get_settings_service().set_boards(
        [
            {
                "name": "Kitchen",
                "device_type": "flagship",
                "api_mode": "local",
                "host": "192.168.1.20",
                "local_api_key": KITCHEN_KEY,
            },
            {"name": "Office", "device_type": "flagship", "api_mode": "cloud", "cloud_key": OFFICE_CLOUD},
            {
                "name": "Wall",
                "output": "divoom_pixoo",
                "device_type": "flagship",
                "output_config": {"host": "pixoo.local"},
            },
            {
                "name": "Array",
                "device_type": "note_array",
                "notes_wide": 2,
                "api_mode": "local",
                "note_array_token": ARRAY_TOKEN,
                "tiles": [
                    {"row": 0, "col": 0, "host": "192.168.1.30", "local_api_key": "test_tile_a"},
                    {"row": 0, "col": 1, "host": "192.168.1.31", "port": 7001, "local_api_key": "test_tile_b"},
                ],
            },
        ]
    )
    return {board["name"]: board["id"] for board in stored.boards}


def existing(client, **body):
    response = client.post("/config/board/existing", json=body)
    assert response.status_code == 200, response.text
    return response.json()["existing"]


def names(client, **body):
    return [(row["name"], row["matched"]) for row in existing(client, **body)]


# ── by address ──────────────────────────────────────────────────────────────


def test_the_same_host_is_the_board_already_set_up(client, boards):
    rows = existing(client, host="192.168.1.20")

    assert rows == [{"board_id": boards["Kitchen"], "name": "Kitchen", "output": "vestaboard", "matched": "host"}]


@pytest.mark.parametrize("host", ["192.168.1.20 ", "http://192.168.1.20", "http://192.168.1.20/", "PIXOO.local."])
def test_a_host_compares_as_written_whatever_its_case_scheme_or_trailing_dot(client, boards, host):
    assert len(existing(client, host=host)) == 1


def test_another_host_is_not_a_duplicate(client, boards):
    assert existing(client, host="192.168.1.99") == []


def test_a_port_only_tells_two_devices_apart_when_both_name_one(client, boards):
    assert names(client, host="192.168.1.31", port=7001) == [("Array", "host")]
    assert names(client, host="192.168.1.31", port=7000) == []
    assert names(client, host="192.168.1.31") == [("Array", "host")]


def test_a_tile_of_a_note_array_counts(client, boards):
    assert names(client, host="192.168.1.30") == [("Array", "host")]


def test_another_outputs_board_on_that_address_counts(client, boards):
    """The wizard adding a Vestaboard at a Pixoo's address is told too: one address, one device."""
    assert names(client, host="pixoo.local") == [("Wall", "host")]
    assert names(client, output="divoom_pixoo", host="pixoo.local") == [("Wall", "host")]


# ── by credential ───────────────────────────────────────────────────────────


def test_the_same_cloud_key_is_the_board_already_set_up(client, boards):
    response = client.post("/config/board/existing", json={"cloud_key": OFFICE_CLOUD})

    assert [(r["name"], r["matched"]) for r in response.json()["existing"]] == [("Office", "cloud_key")]
    assert OFFICE_CLOUD not in response.text


def test_the_same_note_array_token_is_the_board_already_set_up(client, boards):
    assert names(client, note_array_token=ARRAY_TOKEN) == [("Array", "note_array_token")]


@pytest.mark.parametrize("key", ["", "***", "test_cloud_key_other"])
def test_an_empty_masked_or_other_key_matches_nothing(client, boards, key):
    assert existing(client, cloud_key=key, note_array_token=key) == []


def test_a_board_stored_with_a_masked_key_matches_no_masked_request():
    """A client echoing ``***`` back must not match a board some client once saved masked."""
    from src.config_api.existing import existing_boards

    stored = [{"id": "b1", "name": "Odd", "api_mode": "cloud", "cloud_key": "***", "note_array_token": "***"}]

    assert existing_boards(stored, cloud_key="***", note_array_token="***") == []


def test_a_board_matching_twice_is_listed_once(client, boards):
    assert names(client, host="192.168.1.30", note_array_token=ARRAY_TOKEN) == [("Array", "host")]


# ── the wizard's own board, and reading only ────────────────────────────────


def test_the_board_being_edited_is_not_its_own_duplicate(client, boards):
    assert existing(client, host="192.168.1.20", exclude_board_id=boards["Kitchen"]) == []


def test_nothing_is_written(client, boards):
    from src.settings.service import get_settings_service

    before = get_settings_service().get_board_settings().boards

    existing(client, host="192.168.1.20", cloud_key=OFFICE_CLOUD)

    assert get_settings_service().get_board_settings().boards == before


def test_an_unknown_field_is_refused(client, boards):
    assert client.post("/config/board/existing", json={"hostname": "192.168.1.20"}).status_code == 422


# ── on the connection test ──────────────────────────────────────────────────


@patch("requests.get")
def test_the_connection_test_says_which_board_already_uses_that_display(mock_get, client, boards):
    mock_get.return_value = Mock(status_code=200, json=Mock(return_value={"message": [[0] * 22] * 6}))

    body = client.post(
        "/config/board/test", json={"api_mode": "local", "local_api_key": "test_key_new", "host": "192.168.1.20"}
    ).json()

    assert body["success"] is True
    assert body["existing_boards"] == [
        {"board_id": boards["Kitchen"], "name": "Kitchen", "output": "vestaboard", "matched": "host"}
    ]


@patch("requests.get")
def test_a_new_display_has_no_existing_boards(mock_get, client, boards):
    mock_get.return_value = Mock(status_code=200, json=Mock(return_value={"message": [[0] * 22] * 6}))

    body = client.post(
        "/config/board/test", json={"api_mode": "local", "local_api_key": "test_key_new", "host": "192.168.1.77"}
    ).json()

    assert body["existing_boards"] == []


# ── who may ask ─────────────────────────────────────────────────────────────


def test_it_needs_a_signed_in_session_when_auth_is_on(boards, tmp_path, monkeypatch):
    from src.auth import service as auth_module

    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", "correct-password")
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)

    assert TestClient(app).post("/config/board/existing", json={"host": "192.168.1.20"}).status_code == 401
