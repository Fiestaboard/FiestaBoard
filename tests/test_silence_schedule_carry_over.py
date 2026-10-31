"""Saving the silence schedule never silently turns ``show_queued_on_exit`` off (#1944).

``SilenceScheduleRequest.show_queued_on_exit`` defaulted to ``False``, so any
client that omitted the key — the MCP ``update_setting('silence_schedule',
{start_time})`` path, an older web build, a script — wiped the option on
every save. Omitted now means "keep what is stored"; an explicit value wins.

The board layer also has to *store* it: ``set_silence_schedule_for_board``
filters to the known silence keys, and this one was missing from the list.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

WINDOW = {"enabled": True, "start_time": "22:00+00:00", "end_time": "07:00+00:00", "mode": "freeze"}


@pytest.fixture
def client():
    from src.api_server import app

    return TestClient(app)


def _boards(*ids):
    from src.settings.service import get_settings_service

    get_settings_service().set_boards([{"id": b, "device_type": "flagship", "name": b} for b in ids])


def _resolved(board_id):
    from src.config import resolve_silence_schedule
    from src.config_manager import get_config_manager

    return resolve_silence_schedule(get_config_manager().get_feature("silence_schedule"), board_id)


def _put(client, **body):
    resp = client.put("/settings/silence-schedule", json={**WINDOW, **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_board_write_stores_show_queued_on_exit(client):
    _boards("b1", "b2")
    _put(client, board_id="b2", show_queued_on_exit=True)
    assert _resolved("b2")["show_queued_on_exit"] is True
    assert _resolved("b1")["show_queued_on_exit"] is False


def test_board_write_without_the_key_keeps_the_stored_value(client):
    _boards("b1", "b2")
    _put(client, board_id="b2", show_queued_on_exit=True)
    body = _put(client, board_id="b2", start_time="23:00+00:00")
    assert _resolved("b2")["show_queued_on_exit"] is True
    assert body["config"]["show_queued_on_exit"] is True


def test_new_board_write_without_the_key_keeps_its_own_default(client):
    _boards("b1", "b2")
    _put(client, show_queued_on_exit=True)
    _put(client, board_id="b2", start_time="23:00+00:00")
    assert _resolved("b2")["show_queued_on_exit"] is False


def test_single_board_install_wide_write_carries_it_over_before_the_prune(client):
    # The form writes the board layer; an install-wide write then prunes it on
    # a single-board install. The value must survive that.
    _boards("b1")
    _put(client, board_id="b1", show_queued_on_exit=True)
    _put(client, start_time="23:00+00:00")
    assert _resolved("b1")["show_queued_on_exit"] is True


def test_explicit_false_still_clears_it(client):
    _boards("b1", "b2")
    _put(client, board_id="b2", show_queued_on_exit=True)
    _put(client, board_id="b2", show_queued_on_exit=False)
    assert _resolved("b2")["show_queued_on_exit"] is False


def test_mcp_update_setting_preserves_it(client):
    from src.ops import executors

    _boards("b1")
    _put(client, show_queued_on_exit=True)
    result = asyncio.run(executors.update_setting("silence_schedule", {**WINDOW, "start_time": "21:00+00:00"}))
    assert result["status"] == "success", result
    assert _resolved("b1")["show_queued_on_exit"] is True
    assert _resolved("b1")["start_time"] == "21:00+00:00"
