"""The ``auto_restore`` setting and the overwrite signal over HTTP (#2354)."""

from __future__ import annotations

from tests.test_board_api_external_frame import (  # noqa: F401  (fixtures)
    DETECTED_AT,
    client,
    service,
    settings,
)


def test_v1_reports_auto_restore_on_by_default(client, service):  # noqa: F811
    response = client.get("/v1/boards/b2")

    assert response.status_code == 200, response.text
    assert response.json()["auto_restore"] is True


def test_v1_patch_turns_auto_restore_off(client, service, settings):  # noqa: F811
    response = client.patch("/v1/boards/b2", json={"auto_restore": False})

    assert response.status_code == 200, response.text
    assert response.json()["auto_restore"] is False
    assert settings.is_auto_restore(board_id="b2") is False
    assert settings.is_auto_restore(board_id="b1") is True


def test_v1_patch_auto_restore_must_be_a_boolean(client, service):  # noqa: F811
    response = client.patch("/v1/boards/b2", json={"auto_restore": "no"})

    assert response.status_code == 422


def test_settings_board_carries_auto_restore_for_the_web_app(client, service):  # noqa: F811
    boards = client.get("/settings/board").json()["boards"]

    assert [b["auto_restore"] for b in boards] == [True, True]


def test_current_message_says_when_a_device_was_overwritten(client, service):  # noqa: F811
    service.runtimes["b2"].overwritten_at = DETECTED_AT

    body = client.get("/board/current-message?board_id=b2").json()

    assert body["overwritten_at"] == "2023-11-14T22:13:20+00:00"


def test_current_message_has_no_overwrite_key_when_none_was_seen(client, service):  # noqa: F811
    body = client.get("/board/current-message?board_id=b2").json()

    assert "overwritten_at" not in body


def test_an_overwritten_device_without_read_back_answers_its_last_sent_frame_and_the_mark(client, service):  # noqa: F811
    """The pairing the web banner sees for a Pixoo (#2354 review): with no read-back,
    ``characters`` is the last frame FiestaBoard sent — equal to ``expected_characters``
    — so ``overwritten_at`` is the only sign another app wrote it."""
    rt = service.runtimes["b2"]
    rt.polled_characters = None
    rt.polled_at = None
    sent = [[5] * 15 for _ in range(3)]
    rt.output.frames.record_sent(sent)
    rt.overwritten_at = DETECTED_AT

    body = client.get("/board/current-message?board_id=b2").json()

    assert body["characters"] == sent
    assert body["expected_characters"] == sent
    assert body["overwritten_at"] == "2023-11-14T22:13:20+00:00"
