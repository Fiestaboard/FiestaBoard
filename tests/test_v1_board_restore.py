"""``POST /v1/boards/{board}/restore`` — put back what this board should show (#2354).

Another client (a phone app uploading a picture to a Pixoo, the Vestaboard
app) can overwrite a board behind FiestaBoard's back. The display loop's
dedupe then believes the board still shows the intended content and never
writes it again; re-pinning the same page is a no-op in manual mode. The only
recovery was a ``force`` page send, which needs the caller to know which page
is intended. The web "Restore" button (#1945) went through the install-wide
``/force-refresh``, so restoring one display resent every display.

Restore is the board-scoped recovery: forget what this one board was last sent
and run its own display pass. It changes no selection or override, and it
honours pause, silence and the output target exactly like a write does.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.board_guards import SILENCE_DETAIL
from tests.silence_helpers import silenced
from tests.test_v1_contract import RUNTIME_SERVICE, SERVICE, boards, client  # noqa: F401  (fixtures)


@pytest.fixture
def service():
    """A DisplayService stub whose per-board pass reports a successful send."""
    svc = Mock()
    svc.get_runtime.return_value = Mock()
    svc.check_and_send_for_board_with_status.return_value = (True, None)
    with patch(SERVICE, return_value=svc), patch(RUNTIME_SERVICE, return_value=svc):
        yield svc


def _restore(client, board="primary"):  # noqa: F811
    return client.post(f"/v1/boards/{board}/restore")


def test_restore_forgets_only_this_boards_last_sent_content(client, boards, service):  # noqa: F811
    _restore(client, boards[1])

    service.invalidate_board_content.assert_called_once_with(boards[1])
    service.invalidate_all_board_content.assert_not_called()


def test_restore_runs_this_boards_display_pass(client, boards, service):  # noqa: F811
    response = _restore(client, boards[1])

    assert response.status_code == 200, response.text
    args, kwargs = service.check_and_send_for_board_with_status.call_args
    assert args[0] == boards[1]
    assert kwargs["is_primary"] is False
    assert response.json()["sent"] is True
    assert response.json()["board_id"] == boards[1]


def test_restore_accepts_the_primary_alias(client, boards, service):  # noqa: F811
    response = _restore(client, "primary")

    assert response.status_code == 200, response.text
    assert response.json()["board_id"] == boards[0]
    assert service.check_and_send_for_board_with_status.call_args.kwargs["is_primary"] is True


def test_restore_reports_the_pinned_page_it_restored(client, boards, service):  # noqa: F811
    from src.settings.service import get_settings_service

    get_settings_service().set_active_page_id("page-abc", board_id=boards[0])

    body = _restore(client).json()

    assert body["page_id"] == "page-abc"


def test_restore_keeps_the_pinned_page(client, boards, service):  # noqa: F811
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    settings.set_active_page_id("page-abc", board_id=boards[0])

    _restore(client)

    assert settings.get_active_page_id(board_id=boards[0]) == "page-abc"


def test_restore_keeps_a_timed_message(client, boards, service):  # noqa: F811
    from src.settings.service import TemporaryOverride, get_settings_service

    settings = get_settings_service()
    settings.set_temporary_override(TemporaryOverride(template=["HELLO"]))

    _restore(client)

    override = settings.get_temporary_override()
    assert override is not None
    assert override.template == ["HELLO"]


def test_restore_says_the_device_state_was_not_observed(client, boards, service):  # noqa: F811
    """A device acknowledging a write is not proof of its pixels (#2354)."""
    body = _restore(client).json()

    assert body["device_observed"] is False


def test_restore_to_a_paused_board_is_refused(client, boards, service):  # noqa: F811
    from src.settings.service import get_settings_service

    get_settings_service().set_paused(True, board_id=boards[0])

    response = _restore(client)

    assert response.status_code == 409
    assert response.json() == {"detail": "Board is paused — sends are blocked until it is resumed."}
    service.check_and_send_for_board_with_status.assert_not_called()
    service.invalidate_board_content.assert_not_called()


def test_restore_to_a_silenced_board_is_refused(client, boards, service):  # noqa: F811
    with silenced(board=boards[0]):
        response = _restore(client)

    assert response.status_code == 409
    assert response.json()["detail"].startswith(SILENCE_DETAIL)
    service.check_and_send_for_board_with_status.assert_not_called()
    service.invalidate_board_content.assert_not_called()


def test_restore_with_ui_only_output_writes_nothing(client, boards, service):  # noqa: F811
    from src.settings.service import get_settings_service

    get_settings_service().set_output_target("ui")

    response = _restore(client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] is False
    assert "UI only" in body["reason"]
    service.check_and_send_for_board_with_status.assert_not_called()


def test_restore_that_wrote_nothing_says_why(client, boards, service):  # noqa: F811
    service.check_and_send_for_board_with_status.return_value = (False, None)

    body = _restore(client).json()

    assert body["sent"] is False
    assert body["reason"]


def test_restore_failure_is_a_500_naming_the_reason(client, boards, service):  # noqa: F811
    service.check_and_send_for_board_with_status.return_value = (False, "device unreachable")

    response = _restore(client)

    assert response.status_code == 500
    assert "device unreachable" in response.json()["detail"]


def test_restore_to_an_unknown_board_is_404(client, boards, service):  # noqa: F811
    response = _restore(client, "no-such-board")

    assert response.status_code == 404
    service.check_and_send_for_board_with_status.assert_not_called()
