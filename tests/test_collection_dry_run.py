"""H8: ``POST /collections/{id}/dry-run``, which page a collection would pick.

The 2.11 rule tester ("Which page wins tomorrow at 3:00 PM? Rain 70%"):
every rule evaluated (so "rule 2 is true too, but rule 1 is checked first"
can be said), the winner, a timeline over a window, and the boards whose
schedule shows the collection then. Sample and missing data, ``at`` and the
data mode are H6's preview. Read-only: nothing is stored, no board touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest

from tests.test_schedule_at import _at, _collection, _schedule, board, la_hub, quiet  # noqa: F401
from tests.test_v1_contract import _seed_page, board_client, boards, client  # noqa: F401 - fixtures

RAIN = "weather.precip_chance > 60"
LATE = "HOUR(NOW()) >= 15"


@pytest.fixture
def menu(client, board):  # noqa: F811
    board_id, pages = board
    rules = [
        {"expression": RAIN, "page_id": pages["Evening"]},
        {"expression": LATE, "page_id": pages["Work"]},
    ]
    collection = _collection(
        [pages["Breakfast"], pages["Work"], pages["Evening"]],
        selection_mode="variable",
        variable={"rules": rules, "default_page_id": pages["Breakfast"], "poll_seconds": 60},
    )
    return board_id, pages, collection


def _dry(client, collection_id, **body):  # noqa: F811
    return client.post(f"/collections/{collection_id}/dry-run", json=body)


def _ok(client, collection_id, **body):  # noqa: F811
    response = _dry(client, collection_id, **body)
    assert response.status_code == 200, response.text
    return response.json()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


# ── the rules ───────────────────────────────────────────────────────────────


def test_nothing_matching_gives_the_default_with_every_rule_shown(client, menu):
    _, pages, collection = menu

    body = _ok(client, collection.id, at=_at(11, 5).isoformat(), values={"weather.precip_chance": 20})

    assert body["page_id"] == pages["Breakfast"]
    assert body["matched_rule"] is None
    assert [(r["index"], r["expression"], r["matched"]) for r in body["rules"]] == [(0, RAIN, False), (1, LATE, False)]
    assert body["rules"][1]["value"] in {"No", "FALSE", "false", "False"}


def test_the_first_true_rule_wins_and_a_later_true_one_is_still_shown(client, menu):
    _, pages, collection = menu

    body = _ok(client, collection.id, at=_at(15, 0).isoformat(), values={"weather.precip_chance": 70})

    assert (body["page_id"], body["matched_rule"]) == (pages["Evening"], 0)
    assert [r["matched"] for r in body["rules"]] == [True, True]


def test_the_clock_alone_can_change_the_winner(client, menu):
    _, pages, collection = menu
    dry = {"values": {"weather.precip_chance": 10}}

    assert _ok(client, collection.id, at=_at(15, 0).isoformat(), **dry)["page_id"] == pages["Work"]
    assert _ok(client, collection.id, at=_at(9, 0).isoformat(), **dry)["page_id"] == pages["Breakfast"]


def test_missing_data_is_an_error_that_does_not_match(client, menu):
    _, pages, collection = menu

    body = _ok(client, collection.id, at=_at(9, 0).isoformat(), missing=["weather"])

    assert body["rules"][0]["error"] == "#REF" and body["rules"][0]["matched"] is False
    assert body["page_id"] == pages["Breakfast"]
    assert "weather" in body["sources"]


# ── the timeline ────────────────────────────────────────────────────────────


def test_a_formula_collection_timeline_follows_the_clock_over_the_window(client, menu):
    _, pages, collection = menu
    start = _at(12, 0)

    body = _ok(
        client,
        collection.id,
        at=start.isoformat(),
        window_seconds=6 * 3600,
        step_seconds=1800,
        values={"weather.precip_chance": 10},
    )

    assert body["timeline"] == [
        {"from": _iso(start), "until": _iso(_at(15, 0)), "page_id": pages["Breakfast"]},
        {"from": _iso(_at(15, 0)), "until": _iso(_at(18, 0)), "page_id": pages["Work"]},
    ]


def test_a_rotation_timeline_has_its_exact_boundaries(client, board):
    _, pages = board
    members = [pages["Breakfast"], pages["Work"]]
    collection = _collection(members, selection_mode="time", time={"interval_seconds": 600})
    start = _at(12, 5)

    body = _ok(client, collection.id, at=start.isoformat(), window_seconds=1800)

    froms = [segment["from"] for segment in body["timeline"]]
    assert froms == [_iso(start), _iso(_at(12, 10)), _iso(_at(12, 20)), _iso(_at(12, 30))]
    assert [s["page_id"] for s in body["timeline"]] == [
        collection.current_page_id_time(datetime.fromisoformat(f).timestamp()) for f in froms
    ]
    assert body["timeline"][-1]["until"] == _iso(start + timedelta(seconds=1800))
    assert body["rules"] is None and body["truncated"] is False


def test_a_random_timeline_matches_the_engine_at_every_boundary(client, board):
    _, pages = board
    members = [pages["Breakfast"], pages["Work"], pages["Evening"]]
    collection = _collection(members, selection_mode="random", random={"interval_seconds": 300})
    start = _at(9, 0)

    body = _ok(client, collection.id, at=start.isoformat(), window_seconds=3600)

    for segment in body["timeline"]:
        stamp = datetime.fromisoformat(segment["from"]).timestamp()
        assert segment["page_id"] == collection.current_page_id_random(stamp)


def test_a_fast_rotation_over_a_long_window_is_truncated(client, board):
    _, pages = board
    collection = _collection([pages["Breakfast"], pages["Work"]], selection_mode="time", time={"interval_seconds": 5})

    body = _ok(client, collection.id, at=_at(9, 0).isoformat(), window_seconds=3600)

    assert len(body["timeline"]) == 96 and body["truncated"] is True


# ── where it shows ──────────────────────────────────────────────────────────


def test_shown_on_names_the_boards_whose_schedule_shows_it(client, menu):
    board_id, _, collection = menu
    _schedule(board_id, collection.id, "14:00", "20:00")

    assert _ok(client, collection.id, at=_at(15, 0).isoformat())["shown_on"] == [board_id]
    assert _ok(client, collection.id, at=_at(9, 0).isoformat())["shown_on"] == []


# ── bounds, read-only, reach ────────────────────────────────────────────────


def test_an_unknown_collection_is_a_404(client, board):
    assert _dry(client, "collection:00000000-0000-0000-0000-000000000000").status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"window_seconds": 8 * 86400},
        {"window_seconds": 86400, "step_seconds": 600},
        {"step_seconds": 30},
        {"values": {"__now__": 1}},
    ],
    ids=["window-too-long", "too-many-points", "step-too-short", "reserved-path"],
)
def test_an_out_of_bounds_dry_run_is_rejected(client, menu, body):
    _, _, collection = menu

    assert _dry(client, collection.id, **body).status_code == 422


def test_a_dry_run_changes_nothing(client, menu):
    from src.collections.service import get_collection_service

    _, _, collection = menu
    before = get_collection_service().get_collection(collection.id).model_dump()

    _ok(client, collection.id, at=_at(15, 0).isoformat(), values={"weather.precip_chance": 99}, window_seconds=3600)

    assert get_collection_service().get_collection(collection.id).model_dump() == before


def test_the_phone_control_scope_reaches_the_dry_run():
    from src.auth.scopes import CONTROL, permits

    assert permits(CONTROL, "POST", "/collections/collection:abc/dry-run")
    assert not permits(CONTROL, "POST", "/collections/collection:abc/other")
