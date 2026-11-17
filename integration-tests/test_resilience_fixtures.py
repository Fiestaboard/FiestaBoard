"""Contract tests for disposable, loopback-only resilience probe fixtures.

These exercise the fixture machinery, not production recovery. A receiver's
``responded`` event records a successful socket write, not proof that a client
received an acknowledgment. Process ownership covers the direct child only.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import Future
from contextlib import contextmanager
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlsplit

import pytest

import resilience.fixtures as fixtures
from resilience.fixtures import BarrierBoard, OwnedProcess


def _frame(rows=3, cols=15, fill=1):
    return [[fill for _ in range(cols)] for _ in range(rows)]


def _hash(frame):
    canonical = json.dumps(frame, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _request(url, payload=None, *, path="/local-api/message", body=None):
    target = urlsplit(url)
    connection = HTTPConnection(target.hostname, target.port, timeout=3)
    try:
        if body is None:
            body = json.dumps(payload).encode("utf-8")
        connection.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


@contextmanager
def _in_flight(url, frame):
    """A bounded client with explicit cleanup even when an assertion fails."""
    result = Future()

    def request():
        try:
            result.set_result(_request(url, {"characters": frame}))
        except BaseException as exc:
            result.set_exception(exc)

    worker = Thread(target=request, daemon=True)
    worker.start()
    try:
        yield result
    finally:
        worker.join(timeout=4)
        assert not worker.is_alive(), "fixture client exceeded its socket timeout"


def _journal(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def _names(events):
    return [event["event"] for event in events]


def _await_text(path, expected, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and expected in path.read_text():
            return
        time.sleep(0.01)
    pytest.fail(f"child did not write {expected!r} within {timeout}s")


@pytest.mark.parametrize("rows,cols", [(3, 15), (6, 22)])
def test_normal_send_records_frame_hash_and_ordered_receipts(tmp_path, rows, cols):
    journal = tmp_path / "receipts.jsonl"
    frame = _frame(rows, cols, 71)
    with BarrierBoard(journal) as board:
        parsed = urlsplit(board.url)
        assert parsed.scheme == "http"
        assert parsed.hostname == "127.0.0.1"
        assert parsed.port > 0
        assert board.frame is None
        status, body = _request(board.url, {"characters": frame})
        assert status == 200
        assert json.loads(body) == {"ok": True}
        assert board.wait_for("responded", timeout=1)
        assert board.frame == frame
        events = board.events()
        assert _names(events) == ["received", "accepted", "responded"]
        assert _journal(journal) == events
        assert len({event["request_id"] for event in events}) == 1
        assert type(events[0]["request_id"]) is int
        assert all(event["frame_sha256"] == _hash(frame) for event in events)
        elapsed = [event["elapsed_s"] for event in events]
        assert elapsed == sorted(elapsed)
        assert all(value >= 0 for value in elapsed)
        assert all(datetime.fromisoformat(event["utc"].replace("Z", "+00:00")).utcoffset() is not None for event in events)
        # Reads return independent snapshots; control-thread mutation must not
        # silently rewrite the frame or previously persisted evidence.
        snapshot = board.frame
        snapshot[0][0] = 0
        events[0]["event"] = "changed-by-caller"
        frame[0][0] = 0
        assert board.frame == _frame(rows, cols, 71)
        assert board.events()[0]["event"] == "received"


def test_before_accept_barrier_has_no_acceptance_until_released(tmp_path):
    journal = tmp_path / "receipts.jsonl"
    frame = _frame()
    with BarrierBoard(journal, gate_timeout=2) as board:
        board.arm("before_accept")
        with _in_flight(board.url, frame) as response:
            assert board.wait_for("before_accept", timeout=1)
            assert not response.done()
            assert board.frame is None
            assert _names(_journal(journal)) == ["received"]
            board.release()
            assert response.result(timeout=3)[0] == 200
        assert board.frame == frame
        assert board.wait_for("responded", timeout=1)
        assert _names(board.events()) == ["received", "accepted", "responded"]


def test_after_accept_barrier_persists_acceptance_before_ack(tmp_path):
    journal = tmp_path / "receipts.jsonl"
    frame = _frame(fill=2)
    with BarrierBoard(journal, gate_timeout=2) as board:
        board.arm("after_accept")
        with _in_flight(board.url, frame) as response:
            assert board.wait_for("after_accept", timeout=1)
            assert not response.done()
            assert board.frame == frame
            assert _names(_journal(journal)) == ["received", "accepted"]
            board.release()
            assert response.result(timeout=3)[0] == 200


def test_after_accept_disconnect_preserves_acceptance_without_claiming_client_ack(tmp_path):
    journal = tmp_path / "receipts.jsonl"
    frame = _frame(fill=3)
    with BarrierBoard(journal, gate_timeout=2) as board:
        board.arm("after_accept")
        target = urlsplit(board.url)
        body = json.dumps({"characters": frame}).encode()
        with socket.create_connection((target.hostname, target.port), timeout=2) as client:
            client.sendall(
                b"POST /local-api/message HTTP/1.1\r\nHost: localhost\r\n"
                + f"Content-Length: {len(body)}\r\nContent-Type: application/json\r\n\r\n".encode()
                + body
            )
            assert board.wait_for("after_accept", timeout=1)
            assert board.frame == frame
            assert _names(_journal(journal)) == ["received", "accepted"]
            client.shutdown(socket.SHUT_RDWR)
        board.release()
        # A later socket write may succeed despite disconnect (kernel buffers).
        # Neither its presence nor absence changes the durable acceptance fact.
        assert _request(board.url, {"characters": _frame(fill=4)})[0] == 200
        first = [event for event in board.events() if event["request_id"] == 1]
        assert _names(first)[:2] == ["received", "accepted"]
        assert all(event["frame_sha256"] == _hash(frame) for event in first)


@pytest.mark.parametrize("phase,accepted", [("before_accept", False), ("after_accept", True)])
def test_gate_timeout_fails_closed_and_records_actual_acceptance(tmp_path, phase, accepted):
    frame = _frame()
    with BarrierBoard(tmp_path / "receipts.jsonl", gate_timeout=0.1) as board:
        board.arm(phase)
        status, _ = _request(board.url, {"characters": frame})
        assert status == 504
        assert board.wait_for("responded", timeout=1)
        names = _names(board.events())
        assert "barrier_timeout" in names
        assert ("accepted" in names) is accepted
        assert board.frame == (frame if accepted else None)
        assert _request(board.url, {"characters": _frame(fill=6)})[0] == 200


def test_offline_rejects_without_acceptance_then_recovers(tmp_path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        board.arm("offline")
        assert _request(board.url, {"characters": _frame()})[0] == 503
        assert board.wait_for("offline", timeout=1)
        assert board.frame is None
        assert "accepted" not in _names(board.events())
        assert "rejected" in _names(board.events())
        board.release()
        recovered = _frame(fill=7)
        assert _request(board.url, {"characters": recovered})[0] == 200
        assert board.frame == recovered
        accepted = [event for event in board.events() if event["event"] == "accepted"]
        assert len(accepted) == 1
        assert accepted[0]["request_id"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"characters": []},
        {"characters": _frame(3, 14)},
        {"characters": _frame(6, 15)},
        {"characters": [[1] * 15, [1] * 14, [1] * 15]},
        {"characters": _frame(fill=-1)},
        {"characters": _frame(fill=72)},
        {"characters": _frame(fill=True)},
        {"characters": _frame(fill=1.0)},
        {"characters": _frame(fill="1")},
        {"characters": None},
    ],
)
def test_invalid_frames_are_rejected_before_acceptance(tmp_path, payload):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        board.arm("after_accept")
        assert _request(board.url, payload)[0] == 400
        assert board.frame is None
        assert "accepted" not in _names(board.events())
        assert not board.wait_for("after_accept", timeout=0.05)
        board.release()


def test_malformed_json_is_rejected_before_acceptance(tmp_path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        assert _request(board.url, body=b"{bad json")[0] == 400
        assert board.frame is None
        assert "accepted" not in _names(board.events())


def test_oversized_declared_body_is_rejected_without_reading_it(tmp_path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        target = urlsplit(board.url)
        connection = HTTPConnection(target.hostname, target.port, timeout=2)
        try:
            connection.putrequest("POST", "/local-api/message")
            connection.putheader("Content-Length", str(2**30))
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 413
            response.read()
        finally:
            connection.close()
        assert board.frame is None
        assert "accepted" not in _names(board.events())


def test_incomplete_declared_body_never_accepts_a_parseable_frame(tmp_path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        target = urlsplit(board.url)
        body = json.dumps({"characters": _frame()}).encode()
        with socket.create_connection((target.hostname, target.port), timeout=2) as client:
            client.sendall(
                b"POST /local-api/message HTTP/1.1\r\nHost: localhost\r\n"
                + f"Content-Length: {len(body) + 1}\r\n\r\n".encode()
                + body
            )
            client.shutdown(socket.SHUT_WR)
            response = client.recv(4096)
            assert b" 400 " in response
        assert board.frame is None
        assert "accepted" not in _names(board.events())


def test_trickled_headers_have_an_absolute_read_deadline(tmp_path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        target = urlsplit(board.url)
        with socket.create_connection((target.hostname, target.port), timeout=3) as client:
            client.sendall(b"POST /local-api/message HTTP/1.1\r\nX-Slow: ")
            stop = Event()

            def trickle():
                # Every chunk is inside the socket's inactivity timeout. Only
                # the absolute deadline can close this unfinished header.
                for _ in range(25):
                    if stop.wait(0.1):
                        return
                    try:
                        client.sendall(b"x")
                    except OSError:
                        return

            sender = Thread(target=trickle, daemon=True)
            sender.start()
            try:
                try:
                    assert client.recv(1) == b""
                except ConnectionResetError:
                    pass
            finally:
                stop.set()
                sender.join(timeout=1)
                assert not sender.is_alive()
        assert board.frame is None
        assert _request(board.url, {"characters": _frame()})[0] == 200


def test_journal_sync_failure_prevents_acceptance_and_further_writes(tmp_path, monkeypatch):
    journal = tmp_path / "receipts.jsonl"

    def fail_sync(_fd):
        raise OSError(errno.ENOSPC, "synthetic full evidence store")

    with BarrierBoard(journal) as board:
        monkeypatch.setattr(fixtures.os, "fsync", fail_sync)
        with pytest.raises(OSError):
            _request(board.url, {"characters": _frame()})
        before = journal.read_bytes()
        assert board.frame is None
        assert "accepted" not in _names(board.events())
        assert _request(board.url, {"characters": _frame(fill=2)})[0] == 503
        assert journal.read_bytes() == before
        assert board.frame is None


@pytest.mark.parametrize("path", ["/mock/reset", "/mock/configure", "/control", "/release", "/arm"])
def test_http_routes_cannot_control_the_fixture(tmp_path, path):
    with BarrierBoard(tmp_path / "receipts.jsonl") as board:
        board.arm("offline")
        assert _request(board.url, {"phase": "normal"}, path=path)[0] == 404
        assert _request(board.url, {"characters": _frame()})[0] == 503
        assert board.frame is None


def test_context_exit_releases_blocked_request_without_waiting_for_gate_deadline(tmp_path):
    board = BarrierBoard(tmp_path / "receipts.jsonl", gate_timeout=10)
    board.__enter__()
    exited = False
    try:
        board.arm("before_accept")
        with _in_flight(board.url, _frame()) as response:
            assert board.wait_for("before_accept", timeout=1)
            started = time.monotonic()
            board.__exit__(None, None, None)
            exited = True
            assert time.monotonic() - started < 2
            try:
                response.result(timeout=4)
            except OSError:
                pass  # Teardown may deliberately close rather than acknowledge.
    finally:
        if not exited:
            board.__exit__(None, None, None)


def test_each_receipt_is_fsynced_before_barrier_is_visible(tmp_path, monkeypatch):
    calls = []
    real_fsync = os.fsync

    def fsync(fd):
        calls.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(fixtures.os, "fsync", fsync)
    journal = tmp_path / "receipts.jsonl"
    with BarrierBoard(journal, gate_timeout=2) as board:
        board.arm("after_accept")
        with _in_flight(board.url, _frame()) as response:
            assert board.wait_for("after_accept", timeout=1)
            assert _names(_journal(journal)) == ["received", "accepted"]
            assert len(calls) >= 2
            board.release()
            assert response.result(timeout=3)[0] == 200
        assert board.wait_for("responded", timeout=1)
        assert len(calls) >= len(board.events())


def test_full_journal_refuses_new_acceptance_without_growing(tmp_path, monkeypatch):
    monkeypatch.setattr(fixtures, "MAX_EVENTS", 4)
    journal = tmp_path / "receipts.jsonl"
    with BarrierBoard(journal) as board:
        first = _frame(fill=1)
        assert _request(board.url, {"characters": first})[0] == 200
        assert board.wait_for("responded", timeout=1)
        assert _request(board.url, {"characters": _frame(fill=2)})[0] >= 400
        assert board.frame == first
        assert len(_journal(journal)) <= 4
        assert len([event for event in board.events() if event["event"] == "accepted"]) == 1


@pytest.mark.parametrize("kind", ["existing", "symlink", "symlink-parent"])
@pytest.mark.parametrize("fixture_name", ["board", "process"])
def test_evidence_files_never_overwrite_or_follow_symlinks(tmp_path, kind, fixture_name):
    original = tmp_path / "original"
    original.write_text("keep evidence\n")
    target = original
    if kind == "symlink":
        target = tmp_path / "linked"
        target.symlink_to(original)
    elif kind == "symlink-parent":
        actual = tmp_path / "actual"
        actual.mkdir()
        linked = tmp_path / "linked-dir"
        linked.symlink_to(actual, target_is_directory=True)
        target = linked / "new-log"
    with pytest.raises((OSError, ValueError)):
        if fixture_name == "board":
            with BarrierBoard(target):
                pytest.fail("unsafe journal path was accepted")
        else:
            command = [sys.executable, "-c", "raise SystemExit(0)"]
            with OwnedProcess(command, cwd=tmp_path, log_path=target):
                pytest.fail("unsafe log path was accepted")
    assert original.read_text() == "keep evidence\n"
    if kind == "symlink-parent":
        assert not (actual / "new-log").exists()


@pytest.mark.parametrize("value", [True, False, 0, -1, float("nan"), float("inf"), -float("inf"), 10.1])
@pytest.mark.parametrize("fixture_name", ["board", "process"])
def test_invalid_lifecycle_time_bounds_fail_before_start(tmp_path, value, fixture_name):
    with pytest.raises((TypeError, ValueError)):
        if fixture_name == "board":
            with BarrierBoard(tmp_path / "journal", gate_timeout=value):
                pytest.fail("invalid gate timeout accepted")
        else:
            with OwnedProcess(
                [sys.executable, "-c", "raise SystemExit(0)"],
                cwd=tmp_path,
                log_path=tmp_path / "log",
                shutdown_timeout=value,
            ):
                pytest.fail("invalid shutdown timeout accepted")


def test_owned_process_preserves_argv_cwd_output_and_natural_status(tmp_path):
    log = tmp_path / "child.log"
    literal = "$(touch should-not-exist); *"
    command = [
        sys.executable,
        "-c",
        "import os,sys; print(os.getcwd(), flush=True); print(sys.argv[1], flush=True); "
        "print('stderr-marker', file=sys.stderr, flush=True); raise SystemExit(7)",
        literal,
    ]
    with OwnedProcess(command, cwd=tmp_path, log_path=log) as child:
        assert type(child.pid) is int
        assert child.pid != os.getpid()
        assert child.wait(timeout=3) == 7
        assert child.returncode == 7
    output = log.read_text()
    assert str(tmp_path) in output
    assert literal in output
    assert "stderr-marker" in output
    assert not (tmp_path / "should-not-exist").exists()


@pytest.mark.parametrize("command", ["echo unsafe", b"echo unsafe", [], [1]])
def test_owned_process_rejects_shell_strings_and_invalid_argv(tmp_path, command):
    with pytest.raises((TypeError, ValueError)):
        with OwnedProcess(command, cwd=tmp_path, log_path=tmp_path / "child.log"):
            pytest.fail("invalid argv accepted")


def test_owned_process_wait_timeout_leaves_child_owned_and_stop_is_idempotent(tmp_path):
    with OwnedProcess(
        [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
        cwd=tmp_path,
        log_path=tmp_path / "child.log",
        shutdown_timeout=0.1,
    ) as child:
        _await_text(tmp_path / "child.log", "ready")
        with pytest.raises(subprocess.TimeoutExpired):
            child.wait(timeout=0.05)
        assert child.returncode is None
        first = child.stop()
        assert first is not None
        assert child.stop() == first
        assert child.wait(timeout=1) == first


@pytest.mark.skipif(os.name != "posix", reason="POSIX signal escalation contract")
def test_owned_process_kills_and_reaps_sigterm_ignoring_direct_child(tmp_path):
    log = tmp_path / "child.log"
    command = [
        sys.executable,
        "-c",
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "print('ready', flush=True); time.sleep(30)",
    ]
    with OwnedProcess(command, cwd=tmp_path, log_path=log, shutdown_timeout=0.1) as child:
        _await_text(log, "ready")
        started = time.monotonic()
        assert child.stop() == -signal.SIGKILL
        assert time.monotonic() - started < 2
        assert child.returncode == -signal.SIGKILL
        with pytest.raises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)


def test_owned_process_context_exit_terminates_its_child_only(tmp_path):
    command = [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"]
    unrelated = subprocess.Popen(command, cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with OwnedProcess(command, cwd=tmp_path, log_path=tmp_path / "child.log", shutdown_timeout=0.1) as child:
            _await_text(tmp_path / "child.log", "ready")
            owned_pid = child.pid
            assert owned_pid != unrelated.pid
        assert child.returncode is not None
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        try:
            unrelated.wait(timeout=1)
        except subprocess.TimeoutExpired:
            unrelated.kill()
            unrelated.wait(timeout=1)
