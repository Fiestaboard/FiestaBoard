"""MQTT collection selection and hands-off board pause regressions."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.collections.models import CollectionCreate, CollectionUpdate, TimeModeConfig
from src.collections.service import CollectionService
from src.collections.storage import CollectionStorage
from src.mqtt.client import MQTTClient
from src.mqtt.commands import CommandHandler
from src.mqtt.config import MQTTConfig
from src.mqtt.state import StatePublisher
from src.pages.models import PageCreate
from src.pages.service import PageService
from src.pages.storage import PageStorage
from src.settings.service import CURRENT_SETTINGS_SCHEMA_VERSION, SettingsService


@pytest.fixture
def controls(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": CURRENT_SETTINGS_SCHEMA_VERSION,
                "board": {
                    "boards": [
                        {"id": "primary", "name": "Lobby", "device_type": "flagship"},
                        {"id": "secondary", "name": "Kitchen", "device_type": "flagship"},
                    ]
                },
                "output": {"target": "both"},
            }
        )
    )
    settings = SettingsService(str(settings_path))
    pages = PageService(PageStorage(str(tmp_path / "pages.json")))
    page = pages.create_page(PageCreate(name="Weather", type="template", template=["SUNNY"]))
    collections = CollectionService(CollectionStorage(str(tmp_path / "collections.json")))
    collection = collections.create_collection(CollectionCreate(name="Morning", page_ids=[page.id]))
    client = MQTTClient(MQTTConfig(enabled=True, broker_host="test", instance_id="test"))
    client._client = MagicMock()  # Only the outbound broker transport is fake.
    client._connected = True
    publisher = StatePublisher(client)
    client.set_state_publisher(publisher)
    handler = CommandHandler(client)
    with (
        patch("src.settings.service.get_settings_service", return_value=settings),
        patch("src.pages.service.get_page_service", return_value=pages),
        patch("src.collections.service.get_collection_service", return_value=collections),
        patch("src.api_server.peek_service", return_value=None),
        patch("src.config.Config.is_silence_mode_active", return_value=False),
    ):
        yield SimpleNamespace(
            settings=settings,
            pages=pages,
            page=page,
            collections=collections,
            collection=collection,
            client=client,
            publisher=publisher,
            handler=handler,
        )


def discovery(controls, object_id):
    messages = controls.client._client.publish.call_args_list
    for call in reversed(messages):
        if call.args[0].endswith(f"/{object_id}/config"):
            return json.loads(call.args[1])
    raise AssertionError(f"No discovery for {object_id}")


def test_active_page_discovery_includes_collections(controls):
    controls.client.publish_discovery()
    assert discovery(controls, "active_page")["options"] == ["None", "Weather", "Collection: Morning"]


@pytest.mark.parametrize("board_id", [None, "secondary"])
def test_selecting_collection_persists_its_reference_and_publishes_state(controls, board_id):
    payload = (
        "Collection: Morning"
        if board_id is None
        else json.dumps(
            {
                "page": "Collection: Morning",
                "board_id": board_id,
            }
        )
    )
    controls.handler.handle("active_page", payload)
    assert controls.settings.get_active_page_id(board_id=board_id) == controls.collection.id
    if board_id is None:
        assert controls.publisher._gather_state()["active_page"] == "Collection: Morning"
    else:
        assert controls.publisher._gather_attributes()["current_page"]["by_board"][board_id] == {
            "page_id": controls.collection.id,
            "page_name": "Collection: Morning",
        }


def test_collection_name_does_not_hide_page_with_same_name(controls):
    controls.collections.update_collection(controls.collection.id, CollectionUpdate(name="Weather"))
    controls.handler.handle("active_page", "Collection: Weather")
    assert controls.settings.get_active_page_id() == controls.collection.id
    controls.handler.handle("active_page", "Weather")
    assert controls.settings.get_active_page_id() == controls.page.id


def test_collection_label_collision_still_selects_collection(controls):
    controls.pages.create_page(PageCreate(name="Collection: Morning", type="template", template=["PAGE"]))
    controls.client.publish_discovery()
    option = f"Collection: Morning [{controls.collection.id}]"
    assert option in discovery(controls, "active_page")["options"]
    controls.handler.handle("active_page", option)
    assert controls.settings.get_active_page_id() == controls.collection.id
    assert controls.publisher._gather_state()["active_page"] == option


def test_sync_refreshes_discovery_after_collection_rename(controls):
    controls.client.publish_discovery()
    controls.client._client.reset_mock()
    controls.collections.update_collection(controls.collection.id, CollectionUpdate(name="Evening"))
    controls.client._running = True

    def tick(_seconds):
        # Stop after one connected sync iteration.
        if controls.client._client.publish.called:
            controls.client._running = False

    with patch("src.mqtt.client.time.sleep", side_effect=tick):
        controls.client._sync_loop()
    assert discovery(controls, "active_page")["options"] == ["None", "Weather", "Collection: Evening"]


def test_pause_switch_discovery_has_state_and_command_topics(controls):
    controls.client.publish_discovery()
    payload = discovery(controls, "board_paused")
    assert payload["state_topic"].endswith("/board_paused/state")
    assert payload["command_topic"].endswith("/board_paused/set")


@pytest.mark.parametrize("board_id", [None, "secondary"])
def test_mqtt_pause_and_resume_control_target_board(controls, board_id):
    def payload(value):
        return value if board_id is None else json.dumps({"value": value, "board_id": board_id})

    controls.handler.handle("board_paused", payload("ON"))
    assert controls.settings.is_paused(board_id=board_id) is True
    if board_id is None:
        assert controls.publisher._gather_state()["board_paused"] == "ON"
    else:
        assert controls.settings.is_paused() is False
    controls.handler.handle("board_paused", payload("OFF"))
    assert controls.settings.is_paused(board_id=board_id) is False


def test_invalid_pause_payload_does_not_resume_board(controls):
    controls.settings.set_paused(True)
    controls.handler.handle("board_paused", "oops")
    assert controls.settings.is_paused() is True


def test_mqtt_pause_blocks_manual_writes_and_collection_rotation(controls):
    from src.main import BoardRuntime, DisplayService

    service = DisplayService()
    transport = MagicMock()
    transport.render.return_value = (True, True)
    transport.send_characters.return_value = (True, True)
    runtime = BoardRuntime(client=transport, board_id="primary")
    service.runtimes = {"primary": runtime}
    service._primary_board_id = "primary"
    controls.settings.set_schedule_enabled(False)
    controls.settings.set_active_page_id(controls.collection.id)
    second_page = controls.pages.create_page(PageCreate(name="News", type="template", template=["NEWS"]))
    controls.collections.update_collection(
        controls.collection.id,
        CollectionUpdate(page_ids=[controls.page.id, second_page.id], time=TimeModeConfig(interval_seconds=5)),
    )
    with (
        patch("src.api_server.peek_service", return_value=service),
        patch("src.api_server.get_service", return_value=service),
        patch("src.api_server._get_board_client", return_value=transport),
        patch("src.main.get_settings_service", return_value=controls.settings),
        patch("src.main.get_page_service", return_value=controls.pages),
        patch("src.main.get_collection_service", return_value=controls.collections),
        patch("src.main.Config.is_silence_mode_active", return_value=False),
        patch("time.time", return_value=0) as clock,
    ):
        controls.handler.handle("active_page", "Collection: Morning")
        transport.render.assert_called_once()
        transport.reset_mock()
        controls.handler.handle("board_paused", "ON")
        assert controls.settings.is_paused() is True
        controls.handler.handle("active_page", "Collection: Morning")
        controls.handler.handle("refresh_display", "PRESS")
        controls.handler.handle("send_message", "HELLO")
        controls.handler.handle("blank_board", "PRESS")
        controls.handler.handle("next_page", "PRESS")
        controls.handler.handle("previous_page", "PRESS")
        # A collection boundary during an engine tick must stay hands-off too.
        clock.return_value = 6
        controls.settings.set_active_page_id(controls.collection.id)
        assert service.check_and_send_active_page() is False
        transport.render.assert_not_called()
        transport.send_characters.assert_not_called()
        controls.handler.handle("board_paused", "OFF")
        assert service.check_and_send_active_page() is True
        transport.render.assert_called_once()
