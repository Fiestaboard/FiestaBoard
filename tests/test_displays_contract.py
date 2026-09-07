"""Value-level contract goldens for the /displays API (Phase 2 §2, slice 8).

Deliberately *values*, not shapes: the shape corpus records key sets and type
names, so it cannot see a 503 that became a 400, an error string that stopped
naming the unknown display type, or a ``total`` that stopped counting the list
it sits next to.

Every assertion below is a promise this domain makes to the web client
(``web/src/lib/api/misc.ts``) and to the plugin-preview batch fetcher.

Recorded against the UNCONVERTED trunk, then re-pinned by the conventions pass
in this same PR. What deliberately changed, and nothing else:

* ``POST /displays/raw/batch`` with a non-list ``display_types`` answers
  **422** (was 400 ``{"detail": "display_types must be a list"}``): the
  hand-rolled ``isinstance`` check is now a Pydantic ``list[str]`` field, so
  FastAPI rejects the body before the handler runs. The omitted and empty
  cases keep their 400 and its exact detail string.

Every other assertion — status codes, error strings, body keys and their
values, the ``Deprecation``/``Link`` headers — is unchanged from the
pre-conversion recording. None was weakened.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# A plugin that is always installed in a test data dir but never *enabled*,
# so the "installed but unavailable" branch is reachable without fixtures.
INSTALLED_PLUGIN = "date_time"
UNKNOWN_PLUGIN = "no_such_display_source"


@pytest.fixture
def client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


@pytest.fixture
def available_source(monkeypatch):
    """Make ``INSTALLED_PLUGIN`` answer as an available source.

    Patched on ``DisplayService`` itself rather than on an accessor bound in
    some module, so the stub survives the handlers moving out of
    ``src.api_server`` into ``src/displays/routes.py``.
    """
    from src.displays.service import DisplayResult, DisplayService

    def _fake(self, display_type, board=None):
        return DisplayResult(
            display_type=display_type,
            formatted="MON 01 JAN\n12:00",
            raw={"date": "MON 01 JAN", "time": "12:00"},
            available=True,
            error=None,
        )

    monkeypatch.setattr(DisplayService, "get_display", _fake)


# ---------------------------------------------------------------------------
# GET /displays
# ---------------------------------------------------------------------------


def test_list_reports_every_installed_plugin_with_its_availability(client):
    response = client.get("/displays")
    assert response.status_code == 200
    body = response.json()

    types = [entry["type"] for entry in body["displays"]]
    assert INSTALLED_PLUGIN in types
    assert types == sorted(types), "the list is served in plugin-id order"

    entry = next(e for e in body["displays"] if e["type"] == INSTALLED_PLUGIN)
    assert set(entry) == {"type", "available", "description", "source"}
    assert entry["source"] == "plugin"
    assert entry["available"] is False, "nothing is enabled in a fresh data dir"
    assert entry["description"] == "Display current date and time in configurable formats"


def test_list_totals_count_the_list_they_are_served_with(client):
    body = client.get("/displays").json()
    assert body["total"] == len(body["displays"])
    assert body["available_count"] == sum(1 for e in body["displays"] if e["available"])


# ---------------------------------------------------------------------------
# GET /displays/{display_type}
# ---------------------------------------------------------------------------


def test_unknown_display_type_is_a_400_naming_the_valid_types(client):
    response = client.get(f"/displays/{UNKNOWN_PLUGIN}")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail.startswith(f"Unknown display type: {UNKNOWN_PLUGIN}. Valid types: [")
    assert f"'{INSTALLED_PLUGIN}'" in detail


def test_a_known_but_disabled_display_is_a_503_naming_the_plugin(client):
    response = client.get(f"/displays/{INSTALLED_PLUGIN}")
    assert response.status_code == 503
    assert response.json()["detail"] == f"Plugin not enabled: {INSTALLED_PLUGIN}"


def test_an_available_display_returns_its_message_split_into_lines(client, available_source):
    response = client.get(f"/displays/{INSTALLED_PLUGIN}")
    assert response.status_code == 200
    assert response.json() == {
        "display_type": INSTALLED_PLUGIN,
        "message": "MON 01 JAN\n12:00",
        "lines": ["MON 01 JAN", "12:00"],
        "line_count": 2,
        "available": True,
    }


def test_an_available_raw_source_returns_its_data_and_a_null_error(client, available_source):
    response = client.get(f"/displays/{INSTALLED_PLUGIN}/raw")
    assert response.status_code == 200
    assert response.json() == {
        "display_type": INSTALLED_PLUGIN,
        "data": {"date": "MON 01 JAN", "time": "12:00"},
        "available": True,
        "error": None,
    }


# ---------------------------------------------------------------------------
# GET /displays/{display_type}/raw  (deprecated in favour of /plugins/{id}/data)
# ---------------------------------------------------------------------------


def test_raw_declares_itself_deprecated_and_points_at_its_successor(client, available_source):
    response = client.get(f"/displays/{INSTALLED_PLUGIN}/raw")
    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == f'</plugins/{INSTALLED_PLUGIN}/data>; rel="successor-version"'


def test_raw_reports_an_unavailable_source_as_503_not_as_an_empty_200(client):
    """Both the unknown type and the disabled plugin are 503 here.

    Asymmetric with GET /displays/{type}, which 400s the unknown type. Pinned
    as the pre-existing contract, not endorsed: see the PR body.
    """
    assert client.get(f"/displays/{INSTALLED_PLUGIN}/raw").status_code == 503
    unknown = client.get(f"/displays/{UNKNOWN_PLUGIN}/raw")
    assert unknown.status_code == 503
    assert unknown.json()["detail"].startswith(f"Unknown display type: {UNKNOWN_PLUGIN}.")


# ---------------------------------------------------------------------------
# POST /displays/raw/batch
# ---------------------------------------------------------------------------


def test_batch_without_display_types_is_a_400_with_its_exact_detail(client):
    response = client.post("/displays/raw/batch", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "display_types parameter required"


def test_batch_with_an_empty_list_is_the_same_400(client):
    response = client.post("/displays/raw/batch", json={"display_types": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "display_types parameter required"


def test_batch_with_a_non_list_display_types_is_rejected(client):
    # RE-PINNED: 422 (Pydantic) replaces the hand-rolled 400
    # {"detail": "display_types must be a list"}. See the module docstring.
    response = client.post("/displays/raw/batch", json={"display_types": "date_time"})
    assert response.status_code == 422


def test_batch_reports_each_requested_source_with_its_error(client):
    response = client.post(
        "/displays/raw/batch",
        json={"display_types": [INSTALLED_PLUGIN], "enabled_only": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["successful"] == 0
    assert body["displays"] == {
        INSTALLED_PLUGIN: {
            "data": {},
            "available": False,
            "error": f"Plugin not enabled: {INSTALLED_PLUGIN}",
        }
    }


def test_batch_enabled_only_drops_unavailable_sources_but_still_counts_them(client):
    response = client.post(
        "/displays/raw/batch",
        json={"display_types": [INSTALLED_PLUGIN], "enabled_only": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["displays"] == {}
    assert body["total"] == 1, "total counts what was asked for, not what came back"
    assert body["successful"] == 0


# ---------------------------------------------------------------------------
# POST /displays/{display_type}/send
# ---------------------------------------------------------------------------


def test_send_rejects_an_unknown_target_before_touching_the_service(client):
    response = client.post(f"/displays/{INSTALLED_PLUGIN}/send?target=nowhere")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid target: nowhere. Valid targets: ['ui', 'board', 'both']"


def test_send_without_a_running_service_is_a_503(client):
    response = client.post(f"/displays/{INSTALLED_PLUGIN}/send?target=ui")
    assert response.status_code == 503
    assert response.json()["detail"] == "Service not initialized"


def test_batch_does_not_coerce_a_truthy_string_into_enabled_only(client):
    """``enabled_only`` is a StrictBool, so "yes"/1/"on" are rejected.

    A plain ``bool`` field would have silently *widened* the contract the
    hand-rolled dict access had: Pydantic's lax mode coerces all three to
    True, so a client sending ``"enabled_only": "no"`` would have started
    filtering instead of erroring.
    """
    for truthy in ("yes", 1, "on"):
        response = client.post(
            "/displays/raw/batch",
            json={"display_types": [INSTALLED_PLUGIN], "enabled_only": truthy},
        )
        assert response.status_code == 422, truthy
