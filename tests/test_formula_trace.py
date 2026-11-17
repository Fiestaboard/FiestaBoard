"""H7 traces describe actual evaluation without changing its values or limits."""

from __future__ import annotations

import importlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

import pytest

from src.templates import expressions


@pytest.fixture(autouse=True)
def frozen_deadline(monkeypatch):
    monkeypatch.setattr(expressions, "_eval_clock", lambda: 0.0)


def _recorder():
    assert importlib.util.find_spec("src.templates.trace") is not None, "H7 FormulaTrace is not implemented"
    return importlib.import_module("src.templates.trace").FormulaTrace()


def _evaluate(source, context=None):
    trace = _recorder()
    outcome = expressions.evaluate_detailed(source, context, trace=trace)
    return outcome, trace, trace.to_json()["events"]


def test_trace_preserves_the_evaluation_and_reserves_parents_before_children():
    outcome, trace, events = _evaluate("1 + 2 * 3")

    assert outcome == expressions.Evaluation(value="7")
    assert trace.truncated is False
    assert len(trace.events) == 5
    assert set(trace.to_json()) == {"events", "truncated"}
    assert [event["kind"] for event in events] == ["binary", "literal", "binary", "literal", "literal"]
    assert [event["value"] for event in events] == ["7", "1", "6", "2", "3"]
    root, one, product, two, three = events
    assert root["parent"] is None
    assert one["parent"] == product["parent"] == root["id"]
    assert two["parent"] == three["parent"] == product["id"]
    assert len({event["id"] for event in events}) == 5
    assert all(event["error"] is None for event in events)


def test_escaped_strings_have_source_spans_not_decoded_value_lengths():
    source = 'CONCAT("a\\"b", "🦊")'
    outcome, _, events = _evaluate(source)

    assert outcome.value == 'a"b🦊'
    assert [(event["start"], event["end"]) for event in events] == [(0, 19), (7, 13), (15, 18)]
    assert [source[event["start"] : event["end"]] for event in events] == [source, '"a\\"b"', '"🦊"']
    assert set(events[0]) == {"id", "parent", "kind", "label", "start", "end", "value", "value_truncated", "error"}


def test_unary_and_grouped_nodes_keep_their_authored_spans():
    source = "NOT (1 + -2 > 0)"
    outcome, _, events = _evaluate(source)

    assert outcome.value == "Yes"
    assert (events[0]["kind"], events[0]["label"], events[0]["start"], events[0]["end"]) == ("unary", "NOT", 0, 16)
    minus = next(event for event in events if event["kind"] == "unary" and event["label"] == "-")
    assert source[minus["start"] : minus["end"]] == "-2"


@pytest.mark.parametrize("source,value", [("FALSE AND missing.x", "No"), ("TRUE OR missing.x", "Yes")])
def test_short_circuit_operands_have_no_execution_event(source, value):
    outcome, _, events = _evaluate(source)

    assert outcome.value == value
    assert len(events) == 2
    assert all(event["kind"] != "variable" for event in events)


def test_if_keeps_eager_arguments_and_the_selected_successful_result():
    outcome, _, events = _evaluate("IF(TRUE, 1, missing.x)")

    assert outcome == expressions.Evaluation(value="1")
    assert events[0]["value"] == "1"
    assert events[0]["error"] is None
    assert events[-1]["label"] == "missing.x"
    assert events[-1]["error"] == "#REF"


def test_let_does_not_evaluate_binding_names_or_repeat_the_bound_expression():
    source = "LET(x, p.n * 2, x + x)"
    outcome, _, events = _evaluate(source, {"p": {"n": 3}})

    assert outcome.value == "12"
    assert sum(event["label"] == "p.n" for event in events) == 1
    uses = [event for event in events if event["kind"] == "variable" and event["label"] == "x"]
    assert [(event["start"], event["end"], event["value"]) for event in uses] == [(16, 17, "6"), (20, 21, "6")]


def test_foreach_repeated_source_spans_have_distinct_execution_ids():
    outcome, _, events = _evaluate('FOREACH(p.items, item & "!")', {"p": {"items": ["A", "B"]}})

    assert outcome.value == "A!\nB!"
    uses = [event for event in events if event["kind"] == "variable" and event["label"] == "item"]
    assert [(event["start"], event["end"], event["value"]) for event in uses] == [(17, 21, "A"), (17, 21, "B")]
    assert uses[0]["id"] != uses[1]["id"]
    assert uses[0]["parent"] != uses[1]["parent"]


def test_event_cap_preserves_the_completed_root_and_does_not_stop_evaluation():
    outcome, trace, events = _evaluate("COUNT(FILTER(p.items, TRUE))", {"p": {"items": list(range(1000))}})

    assert outcome.value == "1000"
    assert trace.truncated is True
    assert trace.to_json()["truncated"] is True
    assert len(events) == 256
    assert events[0]["parent"] is None
    assert events[0]["value"] == "1000"
    assert all(event["value"] is not None for event in events)
    seen = set()
    for event in events:
        assert event["parent"] is None or event["parent"] in seen
        seen.add(event["id"])


def test_scalar_values_and_labels_are_bounded_without_truncating_the_result():
    source = '"' + "🦊" * 200 + '"'
    outcome, _, events = _evaluate(source)

    assert outcome.value == "🦊" * 200
    assert len(events[0]["label"]) <= 128
    assert events[0]["value"] == "🦊" * 128
    assert events[0]["value_truncated"] is True


def test_collection_previews_never_traverse_or_serialize_plugin_contents():
    class Opaque:
        def __repr__(self):
            raise AssertionError("trace traversed plugin contents")

        __str__ = __repr__

    cyclic = []
    cyclic.append(cyclic)
    outcome, _, events = _evaluate(
        "COUNT(p.items) + LEN(TEXT(p.object))", {"p": {"items": [Opaque(), cyclic], "object": {"secret": Opaque()}}}
    )

    assert outcome.error == "#VALUE"  # TEXT rejects the object in the existing evaluator.
    items = next(event for event in events if event["label"] == "p.items")
    obj = next(event for event in events if event["label"] == "p.object")
    assert items["value"] == "list(2)"
    assert obj["value"] == "dict(1)"
    assert "secret" not in json.dumps(events)
    assert len(json.dumps(events)) < 4096


def test_parse_failure_has_no_execution_events():
    outcome, trace, events = _evaluate("1 + )")

    assert outcome.error == "#SYNTAX"
    assert outcome.error_at == 4
    assert events == []
    assert trace.truncated is False


def test_trace_preserves_untrappable_step_exhaustion(monkeypatch):
    monkeypatch.setattr(expressions, "MAX_FORMULA_STEPS", 8)
    outcome, _, events = _evaluate("IFERROR(SUM(1, 2, 3, 4, 5, 6, 7, 8), 99)")

    assert outcome.error == "#VALUE"
    assert "too much work" in outcome.message
    assert events[0]["error"] == "#VALUE"
    assert events[0]["value"] == "#VALUE"


def test_trace_preserves_untrappable_deadline_exhaustion(monkeypatch):
    reads = iter([0.0, 2.0])
    monkeypatch.setattr(expressions, "DEADLINE_CHECK_STEPS", 1)
    monkeypatch.setattr(expressions, "_eval_clock", lambda: next(reads, 2.0))
    outcome, _, events = _evaluate("IFERROR(1 + 2, 99)")

    assert outcome.error == "#VALUE"
    assert "took too long" in outcome.message
    assert events[0]["error"] == "#VALUE"


def test_tracing_keeps_shared_render_step_charges_unchanged():
    context = {expressions.RENDER_CLOCK_KEY: datetime(2026, 1, 1)}
    plain_context = expressions.ensure_render_clock(context)
    trace_context = expressions.ensure_render_clock(context)
    source = 'LEN(REPT("a", 1024)) + 2'
    plain = expressions.evaluate_detailed(source, plain_context)
    traced, _, _ = _evaluate(source, trace_context)

    assert traced == plain == expressions.Evaluation(value="1026")
    assert plain_context[expressions._RENDER_BUDGET_KEY].steps == trace_context[expressions._RENDER_BUDGET_KEY].steps


def test_tracing_does_not_reset_an_expired_render_deadline(monkeypatch):
    context = expressions.ensure_render_clock({expressions.RENDER_CLOCK_KEY: datetime(2026, 1, 1)})
    monkeypatch.setattr(expressions, "_eval_clock", lambda: 4.0)
    outcome, _, _ = _evaluate("1", context)

    assert outcome.error == "#VALUE"
    assert "one render" in outcome.message


def test_recorder_state_is_restored_after_failure_and_untraced_evaluation():
    outcome, trace, _ = _evaluate('1 + "not a number"')
    snapshot = trace.to_json()
    assert outcome.error == "#VALUE"

    assert expressions.evaluate_detailed("40 + 2").value == "42"
    assert trace.to_json() == snapshot
    later, _, events = _evaluate("3 + 4")
    assert later.value == "7"
    assert len(events) == 3
    assert events[0]["parent"] is None


def test_concurrent_traces_keep_their_events_and_contexts_separate():
    barrier = Barrier(2)

    class ConcurrentValue(dict):
        def __getitem__(self, key):
            barrier.wait(timeout=5)
            return super().__getitem__(key)

    def evaluate_one(value):
        return _evaluate("p.value + 1", {"p": ConcurrentValue(value=value)})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(evaluate_one, [10, 20]))

    assert [outcome.value for outcome, _, _ in results] == ["11", "21"]
    assert [[event["value"] for event in events] for _, _, events in results] == [["11", "10", "1"], ["21", "20", "1"]]
    assert all(events[0]["parent"] is None for _, _, events in results)
