"""Behavioral tests for the per-board send worker (issue #1755).

The golden corpus (tests/test_engine_equivalence.py) proves the engine drives
boards identically through the workers; these tests pin the queue discipline
itself — latest-wins replacement, waiter adoption, idle tracking, stop
semantics — where the harness would only exercise it indirectly.
"""

from __future__ import annotations

import threading

from src.displays.send_worker import BoardSendWorker, SendJob


def make_job(
    key,
    result=True,
    gate: threading.Event | None = None,
    log: list | None = None,
    started: threading.Event | None = None,
) -> SendJob:
    def run() -> bool:
        if started is not None:
            started.set()
        if gate is not None:
            gate.wait(timeout=10)
        if log is not None:
            log.append(key)
        return result

    return SendJob(key=key, run=run)


def test_pending_job_is_replaced_latest_wins():
    """While one job executes, later submissions collapse to the newest one."""
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    started = threading.Event()
    log: list = []
    worker.submit(make_job(("page", "1"), gate=gate, log=log, started=started))
    assert started.wait(timeout=5), "first job should be executing before the next ones are queued"
    worker.submit(make_job(("page", "2"), log=log))
    worker.submit(make_job(("page", "3"), log=log))
    gate.set()
    assert worker.wait_idle(timeout=5)
    assert log == [("page", "1"), ("page", "3")], "the stale middle frame must never reach the board"


def test_replaced_jobs_waiter_resolves_with_replacement_outcome():
    """A wait-mode caller whose job was superseded sees the newer send's result."""
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    started = threading.Event()
    worker.submit(make_job(("busy",), gate=gate, started=started))
    assert started.wait(timeout=5)
    superseded = worker.submit(make_job(("old",), result=True))
    replacement = worker.submit(make_job(("new",), result=False))
    gate.set()
    assert superseded.wait(timeout=5), "the superseded job must still resolve"
    assert superseded.return_value is replacement.return_value is False


def test_active_keys_reports_executing_and_pending_jobs():
    worker = BoardSendWorker("b1")
    started = threading.Event()
    gate = threading.Event()

    def run_blocking() -> bool:
        started.set()
        gate.wait(timeout=10)
        return True

    worker.submit(SendJob(key=("current",), run=run_blocking))
    assert started.wait(timeout=5)
    worker.submit(make_job(("queued",)))
    assert worker.active_keys() == {("current",), ("queued",)}
    gate.set()
    assert worker.wait_idle(timeout=5)
    assert worker.active_keys() == set()


def test_stop_fails_the_pending_job_and_refuses_new_work():
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    started = threading.Event()
    worker.submit(make_job(("busy",), gate=gate, started=started))
    assert started.wait(timeout=5)
    pending = worker.submit(make_job(("pending",), result=True))
    worker.stop(timeout=0.1)
    assert pending.wait(timeout=5)
    assert pending.return_value is False, "a stopped worker must fail, not run, its pending job"

    late = worker.submit(make_job(("late",), result=True))
    assert late.wait(timeout=5)
    assert late.return_value is False
    gate.set()


def test_wait_idle_times_out_while_a_job_is_wedged():
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    worker.submit(make_job(("wedged",), gate=gate))
    assert worker.wait_idle(timeout=0.05) is False
    gate.set()
    assert worker.wait_idle(timeout=5) is True


def test_job_whose_run_raises_still_resolves_false():
    """A raising job must resolve its waiters and leave the worker usable."""
    worker = BoardSendWorker("b1")

    def explode() -> bool:
        raise RuntimeError("boom")

    job = worker.submit(SendJob(key=("bad",), run=explode))
    assert job.wait(timeout=5)
    assert job.return_value is False
    ok = worker.submit(make_job(("good",), result=True))
    assert ok.wait(timeout=5)
    assert ok.return_value is True


def test_replacement_failure_reason_reaches_the_adopted_jobs_sink():
    """An adopted waiter's sink receives the replacement's failure reason.

    (#1867 review: the adopted job inherited only the boolean; its submitter's
    error capture stayed empty, so API callers saw sent:false, reason:None.)
    """
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    started = threading.Event()
    worker.submit(make_job(("busy",), gate=gate, started=started))
    assert started.wait(timeout=5)

    sink: list = []
    adopted = SendJob(key=("old",), run=lambda: True, sink=sink, board_id="b1")
    worker.submit(adopted)

    def failing_run() -> bool:
        # What the engine's job-scoped bookkeeping does on failure (#1867).
        replacement.fail_reason = "hardware said no"
        return False

    replacement = SendJob(key=("new",), run=failing_run)
    worker.submit(replacement)
    gate.set()

    assert adopted.wait(timeout=5)
    assert adopted.return_value is False
    assert adopted.fail_reason == "hardware said no"
    assert sink == [("b1", "hardware said no")]


def test_stop_delivers_a_failure_reason_to_the_pending_jobs_sink():
    """A pending job failed by stop() carries a reason into its sink."""
    worker = BoardSendWorker("b1")
    gate = threading.Event()
    started = threading.Event()
    worker.submit(make_job(("busy",), gate=gate, started=started))
    assert started.wait(timeout=5)

    sink: list = []
    pending = SendJob(key=("pending",), run=lambda: True, sink=sink, board_id="b1")
    worker.submit(pending)
    worker.stop(timeout=0.1)
    gate.set()

    assert pending.wait(timeout=5)
    assert pending.return_value is False
    assert pending.fail_reason, "a job failed by stop() must carry a reason"
    assert sink == [("b1", pending.fail_reason)]
