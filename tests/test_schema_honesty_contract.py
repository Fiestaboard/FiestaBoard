"""Value-level contract goldens for the three schema-honesty fixes.

Three defects, one file, because each is a promise the *published schema*
makes (or fails to make) about a request:

1. ``POST /send-message`` could not address a secondary board. The MCP
   executor (``src.ops.executors.send_message``) has taken a ``board_id``
   since #1765; the HTTP surface had no spelling for it, so on a multi-board
   install board 2 was unreachable over HTTP.
2. Two routes announced their own deprecation in prose only, so Swagger
   rendered them first-class.
3. Request-body fields whose names promise a controlled vocabulary were
   typed as bare ``str``, so a consumer had to read Python to learn the
   legal values.

Every assertion below was **first recorded against the unmodified tree** and
passed there. Each assertion this branch deliberately re-pinned carries a
``CHANGED:`` comment naming the change; anything without one is a promise
this branch kept.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. POST /send-message board targeting
# ---------------------------------------------------------------------------


class FakeBoardClient:
    """A board client that records what was rendered on it.

    Not a ``Mock``: the handler's throttle guard reads
    ``last_send_throttled`` with an ``is True`` check precisely so that a
    Mock's truthy attributes do not put every send on the 429 path, and a
    fake with real attributes keeps that guard honest here too.
    """

    def __init__(self, name: str):
        self.name = name
        self.rendered: list[tuple] = []
        self.last_send_throttled = False
        self.min_send_interval_ms = 0
        self.use_cloud = False
        self._last_characters = None
        self.skip_unchanged = True

    def render(self, board_array, **kwargs):
        self.rendered.append((board_array, kwargs))
        return True, True


PRIMARY = {"id": "board-primary", "device_type": "flagship", "notes_wide": 1, "notes_tall": 1}
SECONDARY = {"id": "board-second", "device_type": "note", "notes_wide": 1, "notes_tall": 1}


@pytest.fixture
def two_boards():
    """A two-board install with a distinct fake client behind each board."""
    clients = {"board-primary": FakeBoardClient("primary"), "board-second": FakeBoardClient("second")}

    service = Mock()
    service.vb_client = clients["board-primary"]
    service.get_board_client = lambda board_id: clients.get(board_id)
    service.request_board_refresh = Mock()
    service.mark_showing_out_of_band = Mock()

    settings_service = Mock()
    board_settings = Mock()
    board_settings.boards = [PRIMARY, SECONDARY]
    settings_service.get_board_settings.return_value = board_settings
    settings_service.get_primary_board_id.return_value = "board-primary"
    settings_service.is_paused.return_value = False
    transition = Mock()
    transition.strategy = None
    transition.step_interval_ms = 0
    transition.step_size = 1
    settings_service.get_transition_settings.return_value = transition

    with (
        patch("src.display_runtime.get_service", return_value=service),
        patch("src.display_runtime.peek_service", return_value=service),
        patch("src.display_runtime.get_settings_service", return_value=settings_service),
        patch("src.board_guards.get_settings_service", return_value=settings_service),
        patch("src.board_guards.Config.is_silence_mode_active", return_value=False),
        patch("src.display_runtime._publish_mqtt_state_update"),
    ):
        yield clients, service, settings_service


class TestSendMessageBoardTargeting:
    def test_omitting_board_id_sends_to_the_primary_board(self, client, two_boards):
        clients, _service, _ss = two_boards
        response = client.post("/send-message", json={"text": "HELLO"})
        assert response.status_code == 200
        assert response.json() == {"message": "Message sent successfully", "sent": True}
        assert len(clients["board-primary"].rendered) == 1
        assert clients["board-second"].rendered == []

    def test_the_default_send_is_sized_to_the_primary_boards_geometry(self, client, two_boards):
        clients, _service, _ss = two_boards
        client.post("/send-message", json={"text": "HELLO"})
        grid = clients["board-primary"].rendered[0][0]
        # Primary is a flagship: 6 rows of 22.
        assert (len(grid), len(grid[0])) == (6, 22)

    # CHANGED: board_id is new on this endpoint. On the unmodified tree
    # MessageRequest had no such field and the extra key was dropped, so this
    # POST wrote to the PRIMARY board — board 2 was unreachable over HTTP.
    def test_board_id_sends_to_that_board_and_not_the_primary(self, client, two_boards):
        clients, _service, _ss = two_boards
        response = client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
        assert response.status_code == 200
        assert response.json() == {"message": "Message sent successfully", "sent": True}
        assert len(clients["board-second"].rendered) == 1
        assert clients["board-primary"].rendered == []

    # CHANGED: new — the send is sized to the *target* board, not the primary.
    def test_a_targeted_send_is_sized_to_the_target_boards_geometry(self, client, two_boards):
        clients, _service, _ss = two_boards
        client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
        grid = clients["board-second"].rendered[0][0]
        # The secondary is a Note: 3 rows of 15.
        assert (len(grid), len(grid[0])) == (3, 15)

    # CHANGED: new. Writes 404 on an unknown board is the rule
    # API_CONVENTIONS.md records for board-scoped writes (#1888); the same
    # verdict the MCP executor already gives as "Board not found: <id>".
    def test_an_unknown_board_id_is_a_404(self, client, two_boards):
        clients, _service, _ss = two_boards
        response = client.post("/send-message", json={"text": "HELLO", "board_id": "no-such-board"})
        assert response.status_code == 404
        assert response.json() == {"detail": "Board not found: no-such-board"}
        assert clients["board-primary"].rendered == []
        assert clients["board-second"].rendered == []

    # CHANGED: new. Silence is per board since #1788; a targeted send must
    # resolve the *target* board's window, exactly as the executor does.
    def test_silence_on_the_target_board_blocks_a_targeted_send(self, client, two_boards):
        clients, _service, _ss = two_boards
        with patch("src.board_guards.Config.is_silence_mode_active", side_effect=lambda b: b == "board-second"):
            blocked = client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
            allowed = client.post("/send-message", json={"text": "HELLO"})
        assert blocked.status_code == 409
        assert allowed.status_code == 200
        assert clients["board-second"].rendered == []
        assert len(clients["board-primary"].rendered) == 1

    # CHANGED: new — same per-board resolution for the pause gate (#970).
    def test_pause_on_the_target_board_blocks_a_targeted_send(self, client, two_boards):
        clients, _service, settings_service = two_boards
        settings_service.is_paused.side_effect = lambda board_id=None: board_id == "board-second"
        blocked = client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
        allowed = client.post("/send-message", json={"text": "HELLO"})
        assert blocked.status_code == 409
        assert allowed.status_code == 200
        assert clients["board-second"].rendered == []

    # CHANGED: new. The adaptive post-send refresh tracks the primary board
    # only (#1243), so a targeted send to a secondary must not request one —
    # the divergence the MCP executor already encodes.
    def test_a_secondary_send_does_not_request_the_primary_board_refresh(self, client, two_boards):
        _clients, service, _ss = two_boards
        client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
        assert service.request_board_refresh.call_count == 0
        client.post("/send-message", json={"text": "HELLO"})
        assert service.request_board_refresh.call_count == 1

    def test_a_throttled_send_is_still_a_429_with_retry_after(self, client, two_boards):
        """The gate the MCP executor does NOT have; it must survive this change."""
        clients, _service, _ss = two_boards
        target = clients["board-second"]
        target.render = lambda board_array, **kwargs: (True, False)
        target.last_send_throttled = True
        target.min_send_interval_ms = 15000
        response = client.post("/send-message", json={"text": "HELLO", "board_id": "board-second"})
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "15"


# ---------------------------------------------------------------------------
# 2. Deprecation is declared, not merely narrated
# ---------------------------------------------------------------------------


def _operation(spec: dict, method: str, path: str) -> dict:
    return spec["paths"][path][method]


@pytest.fixture(scope="module")
def openapi() -> dict:
    """The **internal** document, not the published one.

    Every operation this file asserts on — ``/config/board``, ``/settings/*``,
    ``/templates/render`` — is internal, and ``src/v1/visibility.py`` took all
    of them out of ``app.openapi()``. Reading the published document here
    would not fail loudly; the two "the rule, not the instances" tests below
    iterate ``paths`` and would simply find nothing to object to. A green,
    vacuous ratchet is worse than a red one.
    """
    from src.api_server import app
    from src.v1.visibility import build_internal_openapi

    return build_internal_openapi(app)


class TestDeprecationIsDeclared:
    # CHANGED: both /config/board operations already served the
    # Deprecation/Link header pair and opened their description with
    # "Deprecated: use ... instead (issue #1760)", but carried no
    # deprecated=True, so Swagger rendered them first-class.
    @pytest.mark.parametrize("method", ["get", "put"])
    def test_config_board_is_flagged_deprecated_in_the_schema(self, openapi, method):
        assert _operation(openapi, method, "/config/board")["deprecated"] is True

    @pytest.mark.parametrize(
        ("method", "path", "successor"),
        [
            ("get", "/config/board", '</settings/board>; rel="successor-version"'),
            ("put", "/config/board", '</settings/board>; rel="successor-version"'),
        ],
    )
    def test_a_deprecated_route_still_names_its_successor_in_the_headers(self, client, method, path, successor):
        response = getattr(client, method)(path, **({"json": {}} if method == "put" else {}))
        assert response.status_code == 200
        assert response.headers["Deprecation"] == "true"
        assert response.headers["Link"] == successor

    def test_every_operation_whose_description_says_deprecated_carries_the_flag(self, openapi):
        """The rule, not the instances: prose and schema may not disagree.

        ``GET /cache-status`` is deliberately excluded — it lives in
        ``src/debug/routes.py``, is owned by another slice this wave, and its
        own description records that collapsing it onto
        ``GET /debug/cache-status`` is future work rather than done.
        """
        offenders = []
        for path, operations in openapi["paths"].items():
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "delete", "patch"}:
                    continue
                if path == "/cache-status":
                    continue
                description = (operation.get("description") or "").lower()
                if description.lstrip().startswith("deprecated") and not operation.get("deprecated"):
                    offenders.append(f"{method.upper()} {path}")
        assert offenders == []


# ---------------------------------------------------------------------------
# 3. Fields that promise a vocabulary declare one
# ---------------------------------------------------------------------------


def _field_enum(openapi: dict, schema_name: str, field: str) -> list | None:
    """The enum on ``schema_name.field``, unwrapping Pydantic's anyOf-null."""
    prop = openapi["components"]["schemas"][schema_name]["properties"][field]
    for candidate in [prop, *prop.get("anyOf", [])]:
        if candidate.get("enum"):
            return candidate["enum"]
    return None


class TestDeclaredVocabularies:
    # CHANGED: every entry below was a bare `string` in the published schema.
    # The vocabularies are derived from the codebase constants that already
    # hold them (src.devices.DeviceType / VALID_API_MODES, src.config.
    # SilenceMode, src.settings.service.VALID_OUTPUT_TARGETS) rather than
    # retyped. Two tiers, and the split is deliberate: where nothing else
    # validated the field it became a real Literal, and where a handler
    # already owned the verdict the vocabulary is published without moving
    # that verdict (see TestVocabulariesAreEnforcedNotJustDocumented).
    @pytest.mark.parametrize(
        ("schema_name", "field", "expected"),
        [
            ("AddBoardRequest", "device_type", ["flagship", "note", "note_array"]),
            ("TemplateRenderRequest", "device_type", ["flagship", "note", "note_array"]),
            ("TemplateRenderLiveRequest", "device_type", ["flagship", "note", "note_array"]),
            ("TemporaryOverrideRequest", "device_type", ["flagship", "note", "note_array"]),
            ("TransitionPreviewRequest", "device_type", ["flagship", "note", "note_array"]),
            ("DetectBoardSizeResponse", "device_type", ["flagship", "note", "note_array"]),
            ("PageSendRequest", "target", ["ui", "board", "both"]),
            ("OutputSettingsUpdate", "target", ["ui", "board", "both"]),
            ("BoardConfigUpdate", "api_mode", ["local", "cloud", "virtual"]),
            ("SilenceScheduleRequest", "mode", ["indicator", "freeze", "page"]),
            ("GeneralConfigUpdate", "time_format", ["12h", "24h"]),
        ],
    )
    def test_the_field_publishes_its_vocabulary(self, openapi, schema_name, field, expected):
        assert _field_enum(openapi, schema_name, field) == expected

    def test_device_type_was_already_declared_on_the_page_models(self, openapi):
        """The two that were right stay right — this is the shape being copied."""
        for schema_name in ("PageCreate", "PageUpdate"):
            assert _field_enum(openapi, schema_name, "device_type") == ["flagship", "note", "note_array"]

    def test_transition_strategy_stays_an_open_string(self, openapi):
        """Deliberately NOT an enum: the vocabulary is open.

        ``src.settings.service.is_valid_strategy`` accepts the six built-ins
        *or* any ``plugin:<id>`` reference, so a closed enum would refuse
        every transition plugin. Pinned so a later pass does not "finish the
        job" and break the beta.
        """
        assert _field_enum(openapi, "PageCreate", "transition_strategy") is None
        assert _field_enum(openapi, "TransitionSettingsUpdate", "strategy") is None


class TestVocabulariesAreEnforcedNotJustDocumented:
    """A published enum the server does not enforce is the same lie inverted."""

    # CHANGED: 201 -> 422. BoardInstance.__post_init__ silently rewrote an
    # unknown device_type to "flagship", so `{"device_type": "bogus"}`
    # created a *flagship* board and answered 201.
    def test_add_board_rejects_an_unknown_device_type(self, client):
        response = client.post("/settings/board/add", json={"device_type": "bogus", "name": "x"})
        assert response.status_code == 422

    def test_add_board_still_accepts_every_real_device_type(self, client):
        for device_type in ("flagship", "note", "note_array"):
            response = client.post("/settings/board/add", json={"device_type": device_type})
            assert response.status_code == 201, device_type

    # CHANGED: 200 -> 422. The renderer fell back to flagship geometry for an
    # unknown device_type, so a typo silently rendered at the wrong size.
    def test_template_render_rejects_an_unknown_device_type(self, client):
        response = client.post("/templates/render", json={"template": ["hi"], "device_type": "bogus"})
        assert response.status_code == 422

    def test_template_render_still_renders_a_note(self, client):
        response = client.post("/templates/render", json={"template": ["hi"], "device_type": "note"})
        assert response.status_code == 200
        assert len(response.json()["lines"]) == 3

    # CHANGED: 200 -> 422. `time_format` was stored verbatim, so "bogus"
    # round-tripped through GET /config/general and reached the web UI.
    def test_general_config_rejects_an_unknown_time_format(self, client):
        response = client.put("/config/general", json={"time_format": "bogus"})
        assert response.status_code == 422
        assert client.get("/config/general").json()["time_format"] == "12h"

    def test_a_stale_time_format_already_on_disk_still_reads_back(self, client):
        """Why the RESPONSE model kept ``str``.

        An install that PUT a bad time_format before this branch still has it
        stored. Narrowing the response field too would turn that value into a
        500 on every read of ``GET /config/general`` — an upgrade that bricks
        the settings page. Requests reject; reads tolerate.
        """
        from src.config_manager import get_config_manager

        manager = get_config_manager()
        general = dict(manager.get_general())
        general["time_format"] = "12-hour"
        manager.set_general(general)

        response = client.get("/config/general")
        assert response.status_code == 200
        assert response.json()["time_format"] == "12-hour"

    def test_general_config_still_accepts_24h(self, client):
        assert client.put("/config/general", json={"time_format": "24h"}).status_code == 200
        assert client.get("/config/general").json()["time_format"] == "24h"

    # CHANGED: 200 -> 422. An unknown silence mode was coerced to "freeze",
    # so a client asking for "indicater" got a frozen board and a 200.
    def test_silence_schedule_rejects_an_unknown_mode(self, client):
        response = client.put(
            "/settings/silence-schedule",
            json={"enabled": True, "start_time": "22:00", "end_time": "07:00", "mode": "bogus"},
        )
        assert response.status_code == 422

    def test_silence_schedule_still_accepts_indicator(self, client):
        response = client.put(
            "/settings/silence-schedule",
            json={"enabled": True, "start_time": "22:00", "end_time": "07:00", "mode": "indicator"},
        )
        assert response.status_code == 200
        assert response.json()["config"]["mode"] == "indicator"

    # CHANGED: 200 -> 422. `api_mode` was written into the boards store and
    # normalised back to "local" by BoardInstance, so the caller's value was
    # accepted and discarded in the same request.
    def test_legacy_board_config_rejects_an_unknown_api_mode(self, client):
        assert client.put("/config/board", json={"api_mode": "bogus"}).status_code == 422

    def test_legacy_board_config_still_accepts_cloud(self, client):
        assert client.put("/config/board", json={"api_mode": "cloud"}).status_code == 200

    def test_output_target_still_400s_on_an_unknown_target(self, client):
        """NOT re-pinned. The vocabulary moved into the schema; the verdict did not.

        ``target`` is documented but still typed ``str``, so the service's
        own refusal — a 400 whose detail names the valid set — is what a
        caller keeps getting. See ``OutputSettingsUpdate`` for why.
        """
        response = client.put("/settings/output", json={"target": "bogus"})
        assert response.status_code == 400
        assert response.json() == {"detail": "Invalid target: bogus. Must be one of ['ui', 'board', 'both']"}

    def test_output_target_still_accepts_ui(self, client):
        response = client.put("/settings/output", json={"target": "ui"})
        assert response.status_code == 200
        assert response.json()["target"] == "ui"

    def test_transition_preview_still_400s_on_an_unknown_device_type(self, client):
        """NOT re-pinned, for the same reason plus a recorded one.

        ``src/transitions/models.py`` states outright that its request models
        keep the endpoints' own 400s rather than letting Pydantic widen them
        into 422s. Publishing the vocabulary does not overturn that.
        """
        client.put("/settings/beta", json={"transition_plugins_enabled": True})
        response = client.post(
            "/transitions/preview",
            json={"plugin_id": "nope", "device_type": "bogus"},
        )
        # 404 (unknown plugin) is checked before device_type; the point is
        # simply that Pydantic did not reject the body first.
        assert response.status_code in (400, 404)
        assert "detail" in response.json()
        assert isinstance(response.json()["detail"], str)


# ---------------------------------------------------------------------------
# 4. The 422 the /settings router declared had an empty schema
# ---------------------------------------------------------------------------


SEVEN_STRAGGLERS = [
    ("put", "/settings/mqtt"),
    ("put", "/settings/ai"),
    ("put", "/settings/beta"),
    ("post", "/settings/temporary-override"),
    ("post", "/settings/board/{board_id}/pause"),
    ("post", "/settings/board/{board_id}/detect-size"),
    ("post", "/settings/hdmi-kiosk"),
]


class TestValidationErrorBodyIsDeclared:
    # CHANGED: all seven published {"description": "Validation error"} with
    # no content at all — a hand-written entry that *overrode* the
    # HTTPValidationError body FastAPI publishes automatically with an empty
    # one. Deleting the hand-written entry restores the automatic one.
    @pytest.mark.parametrize(("method", "path"), SEVEN_STRAGGLERS)
    def test_the_422_names_the_validation_error_body(self, openapi, method, path):
        response = _operation(openapi, method, path)["responses"]["422"]
        schema = response["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("HTTPValidationError")

    def test_no_settings_route_publishes_a_422_with_an_empty_schema(self, openapi):
        offenders = []
        for path, operations in openapi["paths"].items():
            if not path.startswith("/settings"):
                continue
            for method, operation in operations.items():
                if method not in {"get", "post", "put", "delete", "patch"}:
                    continue
                declared = (operation.get("responses") or {}).get("422")
                if declared is not None and not declared.get("content"):
                    offenders.append(f"{method.upper()} {path}")
        assert offenders == []
