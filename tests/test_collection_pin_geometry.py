"""A mixed collection's non-fitting member must not reach an immediate send."""

import json
import os
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.board_chars import characters_to_message
from src.text_to_board import text_to_board_array


class RecordingPinClient:
    """Only the external device is replaced; keep the actual projected frame."""

    is_virtual = True

    def __init__(self, rows=3, cols=15):
        self.frames = []
        self.current = text_to_board_array("KEEP", rows=rows, cols=cols)

    def render(self, frame, **kwargs):
        self.current = [row[:] for row in frame]
        self.frames.append(self.current)
        return True, True


@contextmanager
def mixed_pin_client(*, now=0, variable=False, silenced=False):
    """Actual settings/pages/collections/rendering and both HTTP adapters."""
    import src.api_server as api
    import src.collections.service as collection_module
    import src.config_manager as config_module
    import src.pages.service as pages_module
    import src.plugins.registry as registry_module
    import src.settings.service as settings_module
    import src.templates.engine as template_module
    from src.collections.models import CollectionCreate
    from src.main import BoardRuntime, DisplayService
    from src.pages.models import PageCreate
    from src.settings.routes import router
    from src.v1.router import router as v1_router

    with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        (root / "config.json").write_text(json.dumps({"schema_version": 2, "general": {}, "plugins": {}}))
        stack.enter_context(patch.dict(os.environ, {"FIESTABOARD_DATA_DIR": directory}))
        stack.enter_context(patch.object(config_module.ConfigManager, "_instance", None))
        for module, attribute in (
            (settings_module, "_settings_service"),
            (pages_module, "_page_service"),
            (collection_module, "_collection_service"),
            (template_module, "_template_engine"),
            (registry_module, "_registry"),
        ):
            stack.enter_context(patch.object(module, attribute, None))
        settings = settings_module.get_settings_service()
        settings.set_boards(
            [
                {"id": "small-primary", "name": "Small primary", "device_type": "note"},
                {"id": "small-secondary", "name": "Small secondary", "device_type": "note"},
                {"id": "big-unrelated", "name": "Big", "device_type": "flagship"},
            ]
        )
        pages = pages_module.get_page_service()
        large = pages.create_page(PageCreate(name="Large member", type="template", template=["ABCDEFGHIJKLMNOPQRSTUV"]))
        small = pages.create_page(
            PageCreate(name="Small member", type="template", device_type="note", template=["FITS"])
        )
        for board_id in ("small-primary", "small-secondary"):
            settings.set_active_page_id(small.id, board_id)
        collection = collection_module.get_collection_service().create_collection(
            CollectionCreate(
                name="Mixed",
                page_ids=[large.id, small.id],
                selection_mode="variable" if variable else "time",
                variable={"default_page_id": large.id} if variable else None,
            )
        )
        clients = {
            "small-primary": RecordingPinClient(),
            "small-secondary": RecordingPinClient(),
            "big-unrelated": RecordingPinClient(rows=6, cols=22),
        }
        service = DisplayService()
        service.runtimes = {board_id: BoardRuntime(client, board_id) for board_id, client in clients.items()}
        service._primary_board_id = "small-primary"
        stack.enter_context(patch.object(api, "get_service", return_value=service))
        # Trigger dismissal is orthogonal; no providers/triggers run in this fixture.
        stack.enter_context(patch.object(api, "PLUGIN_SYSTEM_AVAILABLE", False))
        stack.enter_context(patch("src.collections.service.time.time", return_value=now))
        if silenced:
            # Drive the real silence verdict/override logic with an active window.
            stack.enter_context(patch("src.board_guards._silence_active", return_value=True))
        app = FastAPI()
        app.include_router(router)
        app.include_router(v1_router)
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                settings=settings,
                clients=clients,
                collection=collection,
                large=large,
                small=small,
                service=service,
                root=root,
            )


class TestMixedCollectionImmediateSend(unittest.TestCase):
    def assert_pinned_without_send(self, fixture, response, target, sent_field):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertFalse(body[sent_field], body)
        self.assertIsNone(body["error"])
        self.assertTrue(any("Large member" in warning and "will be skipped" in warning for warning in body["warnings"]))
        for recorder in fixture.clients.values():
            self.assertEqual(recorder.frames, [])
            self.assertTrue(characters_to_message(recorder.current).startswith("KEEP"))
        self.assertEqual(fixture.settings.get_active_page_id(target), fixture.collection.id)
        other = "small-secondary" if target == "small-primary" else "small-primary"
        self.assertEqual(fixture.settings.get_active_page_id(other), fixture.small.id)
        self.assertTrue(fixture.service.take_wake())
        from src.settings.service import SettingsService

        reloaded = SettingsService(str(fixture.root / "settings.json"))
        self.assertEqual(reloaded.get_active_page_id(target), fixture.collection.id)

    def test_implicit_primary_skips_the_nonfitting_member(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_explicit_secondary_skips_the_nonfitting_member(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put(
                "/settings/active-page", json={"page_id": fixture.collection.id, "board_id": "small-secondary"}
            )
            self.assert_pinned_without_send(fixture, response, "small-secondary", "sent_to_board")

    def test_v1_primary_alias_skips_the_nonfitting_member(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put("/v1/boards/primary/active-page", json={"page_id": fixture.collection.id})
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent")

    def test_v1_secondary_skips_the_nonfitting_member(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put(
                "/v1/boards/small-secondary/active-page", json={"page_id": fixture.collection.id}
            )
            self.assert_pinned_without_send(fixture, response, "small-secondary", "sent")

    def test_variable_collection_default_also_skips_the_nonfitting_member(self):
        with mixed_pin_client(variable=True) as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_fitting_collection_member_still_sends_immediately(self):
        with mixed_pin_client(now=30) as fixture:
            response = fixture.client.put(
                "/settings/active-page", json={"page_id": fixture.collection.id, "board_id": "small-secondary"}
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["sent_to_board"])
            self.assertTrue(characters_to_message(fixture.clients["small-secondary"].current).startswith("FITS"))
            self.assertEqual(fixture.clients["small-primary"].frames, [])

    def test_plain_incompatible_page_is_still_rejected(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.large.id})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(fixture.settings.get_active_page_id(), fixture.small.id)
            self.assertEqual(fixture.clients["small-primary"].frames, [])

    def test_plain_fitting_page_still_sends(self):
        with mixed_pin_client() as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.small.id})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["sent_to_board"])
            self.assertTrue(characters_to_message(fixture.clients["small-primary"].current).startswith("FITS"))

    def test_pause_remains_reported_when_the_member_does_not_fit(self):
        with mixed_pin_client() as fixture:
            fixture.settings.set_paused(True, board_id="small-primary")
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assertTrue(response.json()["paused"])
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_ui_only_output_keeps_the_selection_without_sending(self):
        with mixed_pin_client() as fixture:
            fixture.settings.set_output_target("ui")
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_silence_remains_reported_for_the_nonfitting_member(self):
        with mixed_pin_client(silenced=True) as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assertTrue(response.json()["silenced"])
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_silence_still_holds_a_fitting_member(self):
        with mixed_pin_client(now=30, silenced=True) as fixture:
            response = fixture.client.put("/settings/active-page", json={"page_id": fixture.collection.id})
            self.assertTrue(response.json()["silenced"])
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_silence_override_cannot_send_the_nonfitting_member(self):
        with mixed_pin_client(silenced=True) as fixture:
            response = fixture.client.put(
                "/settings/active-page", json={"page_id": fixture.collection.id, "override_silence": True}
            )
            self.assertFalse(response.json()["silenced"])
            self.assert_pinned_without_send(fixture, response, "small-primary", "sent_to_board")

    def test_silence_override_still_sends_a_fitting_member(self):
        with mixed_pin_client(now=30, silenced=True) as fixture:
            response = fixture.client.put(
                "/settings/active-page", json={"page_id": fixture.collection.id, "override_silence": True}
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()["sent_to_board"])
            self.assertFalse(response.json()["silenced"])
            self.assertTrue(characters_to_message(fixture.clients["small-primary"].current).startswith("FITS"))
