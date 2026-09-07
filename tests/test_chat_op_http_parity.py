"""The chat op path over HTTP vs. what the browser used to do itself.

Phase 2, Task 11. Until this slice the web drawer executed every chat
operation from a ``switch (call.op)`` of its own, calling a different REST
endpoint per op. ``POST /ai/operations`` replaces those branches with the
shared executors (:mod:`src.ops.executors`) MCP already used.

Every test here runs the SAME logical operation twice against two fresh,
isolated stores — once as the **browser sequence** (the exact REST calls
``global-ai-chat-drawer.tsx`` made before this slice) and once through the
new endpoint — and compares the persisted bytes with
``tests/test_op_parity.py``'s snapshot harness.

Why this shape: the zero-regression requirement is "what got created,
changed or deleted must not move". The browser-sequence half of every
test passes unmodified against the pre-slice trunk (it *is* the pre-slice
behavior), so a parity assertion pins the new path to the old effect
rather than to a freshly-written expectation.

Three operations do **not** reach parity, and must not: the browser and
the executor already disagreed, which is the bug this task exists to
surface. Those three have their own tests below, each asserting both
sides explicitly and naming which one was wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("mcp", reason="shared harness imports tests.test_mcp_state_effects")

from fastapi.testclient import TestClient

from src.collections.models import CollectionCreate, TimeModeConfig, VariableModeConfig, VariableRule
from src.schedules.models import ScheduleCreate
from tests.test_mcp_state_effects import PLUGIN_ID, UNINSTALLED_PLUGIN_ID
from tests.test_op_parity import _make_page, assert_parity, isolated_env, snapshot


def _client() -> TestClient:
    from src.api_server import app

    return TestClient(app)


def op(client: TestClient, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute one chat op through the new endpoint, asserting it succeeded."""
    response = client.post("/ai/operations", json={"op": name, "args": args})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["op"] == name
    return body


def _ok(response: Any) -> Any:
    assert response.status_code in (200, 201), response.text
    return response


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


def test_create_schedule_persists_what_the_browser_rest_call_persisted(tmp_path):
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["page_id"] = _make_page(env)

    def browser(env):
        # drawer: handleCreateSchedule -> api.createSchedule(...)
        _ok(
            _client().post(
                "/schedules",
                json={
                    "page_id": ctx["page_id"],
                    "start_time": "07:00",
                    "end_time": "09:00",
                    "day_pattern": "weekdays",
                    "enabled": True,
                },
            )
        )

    def endpoint(env):
        op(
            _client(),
            "create_schedule",
            {
                "page_id": ctx["page_id"],
                "start_time": "07:00",
                "end_time": "09:00",
                "day_pattern": "weekdays",
                "enabled": True,
            },
        )

    assert_parity(tmp_path, browser, endpoint, setup=setup)


def test_create_schedule_with_custom_days_persists_identically(tmp_path):
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["page_id"] = _make_page(env)

    args = lambda: {  # noqa: E731 - one shape, spelled once
        "page_id": ctx["page_id"],
        "start_time": "18:30",
        "end_time": None,
        "day_pattern": "custom",
        "custom_days": ["monday", "thursday"],
        "enabled": False,
    }

    def browser(env):
        _ok(_client().post("/schedules", json=args()))

    def endpoint(env):
        op(_client(), "create_schedule", args())

    assert_parity(tmp_path, browser, endpoint, setup=setup)


def test_delete_schedule_removes_the_same_entry(tmp_path):
    ctx: dict[str, str] = {}

    def setup(env):
        page_id = _make_page(env)
        keep = env.schedules.create_schedule(
            ScheduleCreate(page_id=page_id, start_time="06:00", end_time="07:00", day_pattern="all")
        )
        doomed = env.schedules.create_schedule(
            ScheduleCreate(page_id=page_id, start_time="20:00", end_time="21:00", day_pattern="all")
        )
        ctx["keep_id"] = keep.id
        ctx["doomed_id"] = doomed.id

    def browser(env):
        _ok(_client().delete(f"/schedules/{ctx['doomed_id']}"))

    def endpoint(env):
        op(_client(), "delete_schedule", {"schedule_id": ctx["doomed_id"]})

    assert_parity(tmp_path, browser, endpoint, setup=setup)


def test_update_schedule_applies_the_same_supplied_fields(tmp_path):
    """A partial update the browser and the executor agree on.

    ``end_time`` is deliberately absent from the tool call here — the case
    where they *disagree* is
    ``test_update_schedule_null_end_time_divergence`` below.
    """
    ctx: dict[str, str] = {}

    def setup(env):
        page_id = _make_page(env)
        entry = env.schedules.create_schedule(
            ScheduleCreate(page_id=page_id, start_time="07:00", end_time="09:00", day_pattern="weekdays")
        )
        ctx["schedule_id"] = entry.id

    def browser(env):
        # drawer: only the non-null fields are forwarded.
        _ok(_client().put(f"/schedules/{ctx['schedule_id']}", json={"start_time": "08:00", "enabled": False}))

    def endpoint(env):
        op(_client(), "update_schedule", {"schedule_id": ctx["schedule_id"], "start_time": "08:00", "enabled": False})

    assert_parity(tmp_path, browser, endpoint, setup=setup)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def test_create_collection_persists_what_the_browser_rest_call_persisted(tmp_path):
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["p1"] = _make_page(env, "P1")
        ctx["p2"] = _make_page(env, "P2")

    def browser(env):
        # drawer: handleCreateCollection pinned selection_mode "time".
        _ok(
            _client().post(
                "/collections",
                json={
                    "name": "Morning",
                    "page_ids": [ctx["p1"], ctx["p2"]],
                    "selection_mode": "time",
                    "time": {"interval_seconds": 45},
                },
            )
        )

    def endpoint(env):
        op(
            _client(),
            "create_collection",
            {"name": "Morning", "page_ids": [ctx["p1"], ctx["p2"]], "interval_seconds": 45},
        )

    assert_parity(tmp_path, browser, endpoint, setup=setup)


def test_update_collection_page_list_persists_identically(tmp_path):
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["p1"] = _make_page(env, "P1")
        ctx["p2"] = _make_page(env, "P2")
        collection = env.collections.create_collection(
            CollectionCreate(
                name="Morning",
                page_ids=[ctx["p1"], ctx["p2"]],
                selection_mode="time",
                time=TimeModeConfig(interval_seconds=30),
            )
        )
        ctx["collection_id"] = collection.id

    def browser(env):
        _ok(_client().put(f"/collections/{ctx['collection_id']}", json={"page_ids": [ctx["p2"], ctx["p1"]]}))

    def endpoint(env):
        op(_client(), "update_collection", {"collection_id": ctx["collection_id"], "page_ids": [ctx["p2"], ctx["p1"]]})

    assert_parity(tmp_path, browser, endpoint, setup=setup)


# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


def test_enable_and_disable_plugin_persist_identically(tmp_path):
    def browser(env):
        client = _client()
        _ok(client.post(f"/plugins/{PLUGIN_ID}/disable"))
        _ok(client.post(f"/plugins/{PLUGIN_ID}/enable"))

    def endpoint(env):
        client = _client()
        op(client, "disable_plugin", {"plugin_id": PLUGIN_ID})
        op(client, "enable_plugin", {"plugin_id": PLUGIN_ID})

    assert_parity(tmp_path, browser, endpoint, with_plugins=True)


def test_uninstall_plugin_persists_identically(tmp_path):
    def browser(env):
        _ok(_client().delete(f"/plugins/{PLUGIN_ID}/uninstall"))

    def endpoint(env):
        op(_client(), "uninstall_plugin", {"plugin_id": PLUGIN_ID})

    assert_parity(tmp_path, browser, endpoint, with_plugins=True)


def test_install_plugin_persists_identically(tmp_path):
    def browser(env):
        # drawer: handleInstallPlugin -> install, then enable when
        # auto_enable is not explicitly false.
        client = _client()
        _ok(client.post(f"/plugins/registry/{UNINSTALLED_PLUGIN_ID}/install"))
        _ok(client.post(f"/plugins/{UNINSTALLED_PLUGIN_ID}/enable"))

    def endpoint(env):
        op(_client(), "install_plugin", {"plugin_id": UNINSTALLED_PLUGIN_ID, "auto_enable": True})

    assert_parity(tmp_path, browser, endpoint, with_plugins=True)


def test_configure_plugin_first_write_persists_identically(tmp_path):
    """On a *first* write there is nothing to merge, so both agree.

    The second write is where they part company — see
    ``test_update_plugin_config_merge_divergence``.
    """

    def browser(env):
        _ok(_client().put(f"/plugins/{PLUGIN_ID}/config", json={"config": {"station_id": "9447427"}}))

    def endpoint(env):
        op(_client(), "update_plugin_config", {"plugin_id": PLUGIN_ID, "config": {"station_id": "9447427"}})

    assert_parity(tmp_path, browser, endpoint, with_plugins=True)


# ---------------------------------------------------------------------------
# The three divergences the browser dispatcher was hiding
# ---------------------------------------------------------------------------


def _stored_schedule(env, schedule_id: str) -> dict[str, Any]:
    entry = env.schedules.get_schedule(schedule_id)
    assert entry is not None
    return entry.model_dump()


def test_update_schedule_null_end_time_divergence(tmp_path):
    """DIVERGENCE 1 — the browser wiped ``end_time`` on every partial update.

    ``src/ai/chat.py`` emits the tool call as
    ``tool.args.model_dump(mode="json")``, so an ``update_schedule`` the
    model wrote without ``end_time`` still arrives at the browser as
    ``end_time: null``. The drawer forwarded it with an ``"end_time" in
    update`` test — present-and-null passes — turning every partial update
    into "make this entry open-ended".

    The executor was fixed for exactly this in #1764 (``None`` means
    "unchanged"; ``clear_end_time`` is the explicit escape hatch), but
    nothing on the chat path called the executor, so the defect stayed
    live in the shipped UI. Routing chat through
    ``POST /ai/operations`` retires it: the executor is correct, the
    browser was wrong.
    """
    with isolated_env(tmp_path / "browser") as env:
        page_id = _make_page(env)
        entry = env.schedules.create_schedule(
            ScheduleCreate(page_id=page_id, start_time="07:00", end_time="09:00", day_pattern="weekdays")
        )
        # The pre-slice drawer's body for {"schedule_id": ..., "start_time": "08:00"}
        # after the SSE frame filled in every unset field as null.
        _ok(_client().put(f"/schedules/{entry.id}", json={"start_time": "08:00", "end_time": None}))
        assert _stored_schedule(env, entry.id)["end_time"] is None, (
            "fixture no longer reproduces the browser behavior this test pins"
        )

    with isolated_env(tmp_path / "endpoint") as env:
        page_id = _make_page(env)
        entry = env.schedules.create_schedule(
            ScheduleCreate(page_id=page_id, start_time="07:00", end_time="09:00", day_pattern="weekdays")
        )
        op(
            _client(),
            "update_schedule",
            {"schedule_id": entry.id, "start_time": "08:00", "end_time": None},
        )
        stored = _stored_schedule(env, entry.id)
        assert stored["start_time"] == "08:00"
        assert stored["end_time"] == "09:00", "the endpoint must not wipe an end_time the caller did not send"


def test_update_plugin_config_merge_divergence(tmp_path):
    """DIVERGENCE 2 — the browser replaced the stored config; the executor merges.

    ``PUT /plugins/{id}/config`` is the settings *form* endpoint: replace
    is right there, because the form posts every field. A chat op sends
    only the keys it is changing, so replace dropped everything the user
    had configured earlier — and, when one of the dropped keys was
    required, the second write did not even land: the endpoint answered
    400 and the drawer surfaced "Failed" to the model.
    ``configure_plugin`` merges — the semantics #1764 decided on and
    ``tests/test_mcp_state_effects.py`` already pinned for MCP. The
    browser was wrong.
    """
    with isolated_env(tmp_path / "browser", with_plugins=True) as env:
        client = _client()
        _ok(client.put(f"/plugins/{PLUGIN_ID}/config", json={"config": {"station_id": "9447427"}}))
        second = client.put(f"/plugins/{PLUGIN_ID}/config", json={"config": {"api_key": "test_secret"}})
        assert second.status_code == 400, "fixture no longer reproduces the browser's replace semantics"
        assert "station_id is required" in str(second.json()["detail"])
        stored = env.config.get_plugin_config(PLUGIN_ID, include_env_overrides=False) or {}
        assert "api_key" not in stored, "the browser's second write was rejected, so nothing was stored"

    with isolated_env(tmp_path / "endpoint", with_plugins=True) as env:
        client = _client()
        op(client, "update_plugin_config", {"plugin_id": PLUGIN_ID, "config": {"station_id": "9447427"}})
        op(client, "update_plugin_config", {"plugin_id": PLUGIN_ID, "config": {"api_key": "test_secret"}})
        stored = env.config.get_plugin_config(PLUGIN_ID, include_env_overrides=False) or {}
        assert stored.get("station_id") == "9447427", "a partial chat config write must not drop earlier keys"
        assert stored.get("api_key") == "test_secret"


def test_update_collection_interval_only_divergence(tmp_path):
    """DIVERGENCE 3 — the browser forced a variable-mode collection back to time mode.

    ``handleUpdateCollection`` sent ``selection_mode: "time"`` alongside
    any ``interval_seconds``, so asking the AI to "make that collection
    rotate every 45 seconds" silently destroyed its variable rules. The
    executor changes only the time config. Same defect
    ``tests/test_op_parity.py`` recorded as fail-first divergence 2 for
    the transcribed chat path; it was still live in the browser.
    """
    for name, run in (("browser", "browser"), ("endpoint", "endpoint")):
        with isolated_env(tmp_path / name) as env:
            page_id = _make_page(env)
            collection = env.collections.create_collection(
                CollectionCreate(
                    name="VarCol",
                    page_ids=[page_id],
                    selection_mode="variable",
                    time=TimeModeConfig(interval_seconds=30),
                    variable=VariableModeConfig(
                        rules=[VariableRule(expression="1", page_id=page_id)],
                        default_page_id=page_id,
                        poll_seconds=10,
                    ),
                )
            )
            if run == "browser":
                _ok(
                    _client().put(
                        f"/collections/{collection.id}",
                        json={"selection_mode": "time", "time": {"interval_seconds": 45}},
                    )
                )
                after = env.collections.get_collection(collection.id)
                assert after is not None
                assert after.selection_mode == "time", (
                    "fixture no longer reproduces the browser's mode-forcing behavior"
                )
            else:
                op(_client(), "update_collection", {"collection_id": collection.id, "interval_seconds": 45})
                after = env.collections.get_collection(collection.id)
                assert after is not None
                assert after.selection_mode == "variable", "an interval-only change must not flip the selection mode"
                assert after.time.interval_seconds == 45


# ---------------------------------------------------------------------------
# The endpoint's own contract
# ---------------------------------------------------------------------------


def test_unknown_op_is_a_404_naming_the_op():
    response = _client().post("/ai/operations", json={"op": "make_coffee", "args": {}})
    assert response.status_code == 404
    assert "make_coffee" in response.json()["detail"]


def test_mcp_only_op_is_not_reachable_over_the_chat_endpoint():
    """``send_message`` has an executor but no chat spelling — 404, not a send."""
    response = _client().post("/ai/operations", json={"op": "send_message", "args": {"text": "HI"}})
    assert response.status_code == 404
    assert "chat operation grammar" in response.json()["detail"]


@pytest.mark.parametrize(
    "client_side_op",
    ["apply_patch", "suggest_variables", "navigate_to_page", "navigate_to_schedule", "update_task_list"],
)
def test_client_side_op_is_a_4xx_naming_the_op_and_the_browser(client_side_op):
    response = _client().post("/ai/operations", json={"op": client_side_op, "args": {}})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert client_side_op in detail
    assert "browser" in detail


def test_invalid_args_are_a_422_carrying_the_pydantic_detail():
    response = _client().post("/ai/operations", json={"op": "enable_plugin", "args": {}})
    assert response.status_code == 422
    assert "plugin_id" in response.json()["detail"]


def test_a_failing_executor_is_a_4xx_not_a_200_carrying_an_error(tmp_path):
    with isolated_env(tmp_path / "missing"):
        response = _client().post(
            "/ai/operations",
            json={"op": "delete_schedule", "args": {"schedule_id": "does-not-exist"}},
        )
    assert response.status_code == 400
    assert "does-not-exist" in response.json()["detail"]


def test_the_success_envelope_carries_the_executor_fields(tmp_path):
    with isolated_env(tmp_path / "created") as env:
        page_id = _make_page(env)
        body = op(
            _client(),
            "create_schedule",
            {"page_id": page_id, "start_time": "07:00", "day_pattern": "all"},
        )
        schedule_id = body["result"]["schedule_id"]
        assert env.schedules.get_schedule(schedule_id) is not None
        assert body["message"].startswith("Schedule created")


def test_extra_top_level_keys_are_rejected():
    response = _client().post("/ai/operations", json={"op": "enable_plugin", "args": {}, "board_id": "b1"})
    assert response.status_code == 422


def test_parity_harness_can_fail(tmp_path):
    """Non-vacuity: the snapshot comparison must be able to see a difference."""
    ctx: dict[str, str] = {}

    def setup(env):
        ctx["page_id"] = _make_page(env)

    with pytest.raises(AssertionError, match="persisted different state"):
        assert_parity(
            tmp_path,
            lambda env: op(
                _client(), "create_schedule", {"page_id": ctx["page_id"], "start_time": "07:00", "day_pattern": "all"}
            ),
            lambda env: None,
            setup=setup,
        )


def test_snapshot_sees_the_stores_the_endpoint_writes(tmp_path):
    """Guard the guard: an op executed over HTTP must show up in the snapshot."""
    with isolated_env(tmp_path / "seen") as env:
        before = snapshot(env)
        page_id = _make_page(env)
        op(_client(), "create_schedule", {"page_id": page_id, "start_time": "07:00", "day_pattern": "all"})
        assert snapshot(env) != before
