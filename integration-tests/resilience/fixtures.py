"""Bounded test fixtures; run only inside an exclusively reserved test runtime.

These fixtures do not import the application, manipulate Docker, change clocks
or host networking, or own any process they did not launch. A ``responded``
receipt means the server wrote a response, not that its client received it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import socket
import subprocess
import threading
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MAX_EVENTS = 4096
MAX_BODY_BYTES = 65536
SOCKET_TIMEOUT = 1.0
_PHASES = {"before_accept", "after_accept", "offline"}
_EVENTS = {"received", "accepted", "responded", "barrier_timeout", "rejected"}


def _seconds(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("time bounds must be numbers, not booleans")
    if not math.isfinite(value) or not 0 < value <= 10:
        raise ValueError("time bounds must be finite and within (0, 10] seconds")
    return float(value)


def _exclusive_file(path: Path):
    """Create evidence without overwriting or following existing symlinks.

    The caller must supply a private, existing scratch directory. This check
    rejects existing symlink components; it is not a hostile-filesystem sandbox.
    After opening, writes use only the owned descriptor, never reopen the path.
    """
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("evidence paths must not contain symlinks")
    if not path.parent.is_dir():
        raise ValueError("evidence parent must be an existing private directory")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(fd, "wb", buffering=0)


def _valid_frame(body) -> bool:
    if not isinstance(body, dict):
        return False
    frame = body.get("characters")
    if not isinstance(frame, list) or len(frame) not in (3, 6):
        return False
    cols = 15 if len(frame) == 3 else 22
    return all(
        isinstance(row, list)
        and len(row) == cols
        and all(type(code) is int and 0 <= code <= 71 for code in row)
        for row in frame
    )


class BarrierBoard:
    """One bounded request thread and in-process controls for one fake board.

    ``arm`` affects the next valid POST only. ``offline`` is an HTTP 503 fault,
    not a TCP refusal or physical disconnection. No controls are network routes.
    A barrier's deadline is never extended by reads. The journal is exclusive,
    bounded and fsynced per receipt; it does not promise power-loss durability.
    """

    def __init__(self, journal_path: Path, gate_timeout: float = 5.0):
        self._path = Path(journal_path)
        self._timeout = _seconds(gate_timeout)
        self._condition = threading.Condition(threading.RLock())
        self._release = threading.Event()
        self._closing = threading.Event()
        self._mode = None
        self._reached = set()
        self._records = []
        self._frame = None
        self._request_id = 0
        self._inflight = False
        self._journal = None
        self._server = None
        self._thread = None
        self._started = False
        self._active_socket = None
        self._journal_failed = False
        self._origin = time.monotonic()

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("receiver is not running")
        return f"http://127.0.0.1:{self._server.server_port}"

    @property
    def frame(self):
        with self._condition:
            return copy.deepcopy(self._frame)

    def events(self) -> list[dict]:
        with self._condition:
            return copy.deepcopy(self._records)

    def arm(self, phase: str) -> None:
        if phase not in _PHASES:
            raise ValueError("unknown receiver phase")
        with self._condition:
            if self._server is None or self._closing.is_set():
                raise RuntimeError("receiver is not running")
            if self._inflight:
                raise RuntimeError("cannot change an in-flight request")
            self._mode = phase
            self._reached.clear()
            self._release.clear()

    def release(self) -> None:
        with self._condition:
            self._mode = None
            self._release.set()

    def wait_for(self, phase: str, timeout: float = 1.0) -> bool:
        if phase not in _PHASES | _EVENTS:
            raise ValueError("unknown receiver phase")
        with self._condition:
            return self._condition.wait_for(lambda: phase in self._reached, _seconds(timeout))

    def _record(self, event, request_id, frame_hash, **extra):
        with self._condition:
            if len(self._records) >= MAX_EVENTS:
                raise OSError("receipt journal limit reached")
            record = {
                "event": event,
                "request_id": request_id,
                "frame_sha256": frame_hash,
                "elapsed_s": time.monotonic() - self._origin,
                "utc": datetime.now(timezone.utc).isoformat(),
                **extra,
            }
            encoded = (json.dumps(record, separators=(",", ":")) + "\n").encode()
            try:
                view = memoryview(encoded)
                while view:
                    written = self._journal.write(view)
                    if not written:
                        raise OSError("receipt journal write made no progress")
                    view = view[written:]
                os.fsync(self._journal.fileno())
            except OSError:
                # Never append another success after an uncertain partial
                # receipt. Preserve the damaged file for the probe's evidence.
                self._journal_failed = True
                raise
            self._records.append(record)
            self._reached.add(event)
            self._condition.notify_all()

    def _gate(self, phase, request_id, frame_hash) -> bool:
        with self._condition:
            self._reached.add(phase)
            self._condition.notify_all()
        if not self._release.wait(self._timeout):
            self._record("barrier_timeout", request_id, frame_hash, phase=phase)
            return False
        return not self._closing.is_set()

    def __enter__(self):
        if self._started:
            raise RuntimeError("a receiver instance can only be started once")
        self._started = True
        self._journal = _exclusive_file(self._path)
        board = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(SOCKET_TIMEOUT)
                with board._condition:
                    board._active_socket = self.request
                # An inactivity timeout alone permits indefinitely trickled
                # headers/body. Close this socket at an absolute read deadline.
                self._read_deadline = threading.Timer(SOCKET_TIMEOUT, self.abort_read)
                self._read_deadline.daemon = True
                self._read_deadline.start()
                super().setup()

            def abort_read(self):
                try:
                    self.request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            def finish(self):
                self._read_deadline.cancel()
                try:
                    super().finish()
                finally:
                    with board._condition:
                        board._active_socket = None

            def log_message(self, *_args):
                pass

            def respond(self, status, body):
                encoded = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                self.wfile.flush()

            def do_GET(self):  # noqa: N802
                self._read_deadline.cancel()
                if self.path != "/local-api/message":
                    self.respond(404, {"error": "not found"})
                    return
                self.respond(200, board.frame or [[0] * 22 for _ in range(6)])

            def do_POST(self):  # noqa: N802
                if self.path != "/local-api/message":
                    self.respond(404, {"error": "not found"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.respond(400, {"error": "invalid content length"})
                    return
                if length > MAX_BODY_BYTES:
                    self.respond(413, {"error": "body exceeds fixture limit"})
                    return
                if length <= 0 or self.headers.get("Transfer-Encoding"):
                    self.respond(400, {"error": "bounded content length required"})
                    return
                try:
                    body = json.loads(self.rfile.read(length))
                except (ValueError, OSError):
                    self.respond(400, {"error": "invalid or incomplete JSON body"})
                    return
                if not _valid_frame(body):
                    self.respond(400, {"error": "invalid character frame"})
                    return
                self._read_deadline.cancel()
                frame = body["characters"]
                frame_hash = hashlib.sha256(json.dumps(frame, separators=(",", ":")).encode()).hexdigest()
                with board._condition:
                    # Reserve the longest path: received, accepted, timeout,
                    # responded. Refuse before acceptance when evidence is full.
                    if len(board._records) + 4 > MAX_EVENTS or board._closing.is_set() or board._journal_failed:
                        self.respond(503, {"error": "receiver unavailable or journal full"})
                        return
                    board._request_id += 1
                    request_id = board._request_id
                    mode, board._mode = board._mode, None
                    board._inflight = True
                try:
                    board._record("received", request_id, frame_hash)
                    if mode == "offline":
                        board._record("rejected", request_id, frame_hash)
                        status = 503
                    elif mode == "before_accept" and not board._gate(mode, request_id, frame_hash):
                        status = 504
                    else:
                        with board._condition:
                            board._record("accepted", request_id, frame_hash)
                            board._frame = copy.deepcopy(frame)
                        status = 200
                        if mode == "after_accept" and not board._gate(mode, request_id, frame_hash):
                            status = 504
                    self.respond(status, {"ok": True} if status == 200 else {"error": "injected fixture fault"})
                    board._record("responded", request_id, frame_hash, http_status=status)
                except OSError:
                    # Acceptance already persisted remains evidence even when
                    # a disconnected client cannot receive its response.
                    self.close_connection = True
                finally:
                    with board._condition:
                        board._inflight = False
                        board._condition.notify_all()

        try:
            self._server = HTTPServer(("127.0.0.1", 0), Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                kwargs={"poll_interval": 0.05},
                name="resilience-board",
                daemon=True,
            )
            self._thread.start()
        except BaseException:
            if self._server is not None:
                self._server.server_close()
            self._journal.close()
            raise
        return self

    def __exit__(self, *_exc):
        if self._server is None:
            return
        self._closing.set()
        self.release()
        with self._condition:
            if self._active_socket is not None:
                try:
                    self._active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        self._server.shutdown()
        self._thread.join(timeout=SOCKET_TIMEOUT + 1)
        if self._thread.is_alive():
            raise RuntimeError("receiver thread failed to stop")
        self._server.server_close()
        self._server = None
        self._journal.close()


class OwnedProcess:
    """Bounded ownership of one foreground child, never arbitrary descendants.

    Commands must run in the foreground and must not daemonize or spawn children
    that outlive them. This is not a hub/supervisord process-tree controller.
    """

    def __init__(self, command: Sequence[str], *, cwd: Path, log_path: Path, shutdown_timeout: float = 1.0):
        if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
            raise TypeError("command must be an argument sequence")
        if not command or not all(isinstance(arg, str) and "\x00" not in arg for arg in command) or not command[0]:
            raise ValueError("command must contain nonempty executable and string arguments")
        self._command = list(command)
        self._cwd = Path(cwd)
        self._path = Path(log_path)
        self._timeout = _seconds(shutdown_timeout)
        self._process = None
        self._log = None

    @property
    def pid(self) -> int:
        if self._process is None:
            raise RuntimeError("child is not started")
        return self._process.pid

    @property
    def returncode(self):
        return None if self._process is None else self._process.poll()

    def __enter__(self):
        if self._process is not None:
            raise RuntimeError("a process instance can only be started once")
        self._log = _exclusive_file(self._path)
        try:
            self._process = subprocess.Popen(
                self._command,
                cwd=self._cwd,
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except BaseException:
            self._log.close()
            raise
        return self

    def wait(self, timeout: float = 1.0) -> int:
        if self._process is None:
            raise RuntimeError("child is not started")
        return self._process.wait(timeout=_seconds(timeout))

    def stop(self):
        if self._process is None:
            return None
        if self._process.poll() is None:
            self._process.terminate()
            try:
                return self._process.wait(timeout=self._timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
        return self._process.wait(timeout=self._timeout)

    def __exit__(self, *_exc):
        try:
            self.stop()
        finally:
            if self._log is not None:
                self._log.close()
